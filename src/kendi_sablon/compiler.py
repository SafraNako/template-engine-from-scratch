"""Turns the syntax tree into Python closures.

Every expression becomes a function of the current scope (``fn(frame) -> value``), every statement a function of the scope and the list that the output
is appended to (``fn(frame, out)``).  Nothing is generated as source text: a template is a tree of closures that is built once and run many times.
"""
from __future__ import annotations

import operator
from typing import Any, Callable, Dict, List, Optional

from . import nodes
from .errors import TemplateAssertionError, TemplateNotFound, TemplateRuntimeError, TemplateSyntaxError
from .markup import Markup, escape_to_str
from .runtime import Frame, LoopContext, Macro, RootState, TemplateReference, Undefined, markup_join, str_join
from .utils import Namespace, missing, pass_arg_of

COMPARE = {
    "eq": operator.eq, "ne": operator.ne, "lt": operator.lt, "lteq": operator.le, "gt": operator.gt, "gteq": operator.ge,
    "in": lambda a, b: a in b, "notin": lambda a, b: a not in b,
}
DICT_ATTRIBUTES = frozenset(dir(dict))
BINARY = {
    nodes.Add: operator.add, nodes.Sub: operator.sub, nodes.Mul: operator.mul, nodes.Div: operator.truediv,
    nodes.FloorDiv: operator.floordiv, nodes.Mod: operator.mod, nodes.Pow: operator.pow,
}


class State:
    """What the compiler has to know about the place of a node: how output is written there, and which kind of scope it is in."""

    __slots__ = ("autoescape", "toplevel", "rootlevel", "output_check", "soft", "block", "volatile")

    def __init__(self, autoescape: bool, toplevel: bool = True, rootlevel: bool = True, output_check: bool = False, soft: bool = False,
                 block: Optional[tuple] = None, volatile: bool = False) -> None:
        self.autoescape = autoescape
        self.toplevel = toplevel            # the template's own statements: the root and the branches of its conditions (they export what they assign)
        self.rootlevel = rootlevel          # the root itself, not a branch of a condition
        self.output_check = output_check    # the output written here is dropped once the template has extended another one
        self.soft = soft                    # inside a branch that might never run
        self.block = block
        self.volatile = volatile            # inside an ``autoescape`` block whose option is only known when it runs

    def replace(self, **changes: Any) -> "State":
        new = State(self.autoescape, self.toplevel, self.rootlevel, self.output_check, self.soft, self.block, self.volatile)
        for key, value in changes.items():
            setattr(new, key, value)
        return new

    def inner(self) -> "State":
        """A scope of its own: it can read the variables around it, what it assigns is gone after it."""
        return self.replace(toplevel=False, rootlevel=False, soft=False)

    def branch(self) -> "State":
        """A branch of a condition: the same scope, but the statements in it may not run."""
        return self.replace(rootlevel=False, soft=True)

    def function(self) -> "State":
        """The body of a macro or a block: it runs on its own, whenever it is called."""
        return self.replace(toplevel=False, rootlevel=False, output_check=False, soft=False)


def _noop(frame: Frame, out: List[Any]) -> None:
    return None


def _names_loaded(statements, wanted) -> set:
    """Which of the ``wanted`` names does the code read?  (A macro that reads ``varargs`` or ``caller`` is given them.)"""
    found = set()
    todo = list(statements)
    while todo:
        node = todo.pop()
        if isinstance(node, nodes.Name) and node.ctx == "load" and node.name in wanted:
            found.add(node.name)
        if isinstance(node, nodes.Block):
            continue
        todo.extend(node.iter_child_nodes())
    return found


def _contains(statements, classes) -> bool:
    """Is there a node of one of the classes anywhere in the statements?"""
    for statement in statements:
        if isinstance(statement, classes) or any(True for _ in statement.find_all(classes)):
            return True
    return False


def unpack(value: Any, count: int) -> list:
    """``a, b = value`` with the same errors as Python's."""
    try:
        iterator = iter(value)
    except TypeError:
        raise TypeError("cannot unpack non-iterable %s object" % type(value).__name__) from None
    values = []
    for item in iterator:
        values.append(item)
        if len(values) > count:
            raise ValueError("too many values to unpack (expected %d)" % count)
    if len(values) < count:
        raise ValueError("not enough values to unpack (expected %d, got %d)" % (count, len(values)))
    return values


class Compiler:
    def __init__(self, environment, name: Optional[str], filename: Optional[str]) -> None:
        self.env = environment
        self.name = name
        self.filename = filename
        self.blocks: Dict[str, Callable] = {}
        self.deferred_error: Optional[Exception] = None
        self.extends_so_far = 0             # how many {% extends %} came before in the source
        self.known_extends = False          # one of them is at the root of the template, so the template certainly extends

    def fail(self, message: str, lineno: Optional[int]):
        raise TemplateAssertionError(message, lineno, self.name, self.filename)

    # the template

    def compile_template(self, tree: nodes.Template):
        autoescape = self.env.autoescape(self.name) if callable(self.env.autoescape) else self.env.autoescape
        has_extends = any(True for _ in tree.find_all(nodes.Extends))
        body = self.seq(tree.body, State(bool(autoescape), True, True, output_check=has_extends))
        if self.deferred_error is not None:
            raise self.deferred_error

        def root_render(ctx, out) -> None:
            frame = Frame(ctx, ctx.vars, None)
            frame.state = RootState()
            body(frame, out)
            parent = frame.state.parent_template
            if parent is not None:
                parent.root_render(ctx, out)

        return root_render, self.blocks

    def seq(self, statements, st: State):
        """The statements of a body, run one after the other."""
        fns = [self.stmt(s, st) for s in statements]
        if not fns:
            return _noop
        if len(fns) == 1:
            return fns[0]

        def run(frame: Frame, out: list) -> None:
            for fn in fns:
                fn(frame, out)
        return run

    def annotate(self, exc: Exception, lineno: Optional[int]) -> None:
        """Records on the exception the template and the line that was running; Python 3.11 and later also print it as a note."""
        if isinstance(exc, TemplateSyntaxError) or getattr(exc, "template_lineno", None) is not None:
            return
        exc.template_name = self.name
        exc.template_filename = self.filename
        exc.template_lineno = lineno
        if hasattr(exc, "add_note"):
            exc.add_note("in template %s, line %s" % (repr(self.filename or self.name) if (self.filename or self.name) else "<string>", lineno))

    def stmt(self, node, st: State):
        return getattr(self, "s_" + type(node).__name__)(node, st)

    def expr(self, node, st: State):
        return getattr(self, "x_" + type(node).__name__)(node, st)

    # storing

    def store(self, target, st: State):
        """A function ``(frame, value)`` that assigns to the target of a ``set``, a ``for`` or a macro argument."""
        if isinstance(target, nodes.Name):
            name = target.name
            if st.toplevel and not name.startswith("_"):
                def store_exported(frame: Frame, value: Any) -> None:
                    frame.vars[name] = value
                    frame.ctx.exported_vars.add(name)
                return store_exported
            if st.toplevel:
                def store_private(frame: Frame, value: Any) -> None:
                    frame.vars[name] = value
                return store_private

            def store_local(frame: Frame, value: Any) -> None:
                frame.vars[name] = value
            return store_local
        if isinstance(target, nodes.Tuple):
            subs = [self.store(item, st) for item in target.items]
            count = len(subs)

            def store_tuple(frame: Frame, value: Any) -> None:
                for sub, item in zip(subs, unpack(value, count)):
                    sub(frame, item)
            return store_tuple
        if isinstance(target, nodes.NSRef):
            lookup = self.x_Name(nodes.Name(target.name, "load", lineno=target.lineno), st)
            attr = target.attr

            def store_namespace(frame: Frame, value: Any) -> None:
                ns = lookup(frame)
                if not isinstance(ns, Namespace):
                    raise TemplateRuntimeError("cannot assign attribute on non-namespace object")
                ns[attr] = value
            return store_namespace
        self.fail("can't assign to %r" % type(target).__name__.lower(), target.lineno)

    # expressions

    def x_Const(self, node, st: State):
        value = node.value
        return lambda frame: value

    def x_Name(self, node, st: State):
        name = node.name
        if name == "self":
            return lambda frame: TemplateReference(frame.ctx)
        if name == "super" and st.block is not None:
            block_name, cell = st.block
            return lambda frame: frame.ctx.super(block_name, cell[0])

        def load(frame: Frame) -> Any:
            fr = frame
            while fr is not None:
                vars_ = fr.vars
                if name in vars_:
                    return vars_[name]
                fr = fr.parent
            ctx = frame.ctx
            if name in ctx.parent:
                return ctx.parent[name]
            return ctx.environment.undefined(name=name)
        return load

    def x_Tuple(self, node, st: State):
        fns = [self.expr(item, st) for item in node.items]
        return lambda frame: tuple([fn(frame) for fn in fns])

    def x_List(self, node, st: State):
        fns = [self.expr(item, st) for item in node.items]
        return lambda frame: [fn(frame) for fn in fns]

    def x_Dict(self, node, st: State):
        pairs = [(self.expr(p.key, st), self.expr(p.value, st)) for p in node.items]
        return lambda frame: {k(frame): v(frame) for k, v in pairs}

    def x_Getattr(self, node, st: State):
        obj_fn = self.expr(node.node, st)
        attr = node.attr
        from .environment import Environment
        if type(self.env).getattr is not Environment.getattr:           # the environment has its own way to look up an attribute
            return lambda frame: frame.ctx.environment.getattr(obj_fn(frame), attr)
        is_dict_attribute = attr in DICT_ATTRIBUTES

        def getattr_(frame: Frame) -> Any:
            obj = obj_fn(frame)
            if obj.__class__ is dict and not is_dict_attribute:         # (a dict has no such attribute: skip the failing lookup)
                try:
                    return obj[attr]
                except KeyError:
                    return frame.ctx.environment.undefined(obj=obj, name=attr)
            return frame.ctx.environment.getattr(obj, attr)
        return getattr_

    def x_Getitem(self, node, st: State):
        obj_fn = self.expr(node.node, st)
        arg_fn = self.expr(node.arg, st)
        if isinstance(node.arg, nodes.Slice):               # a slice goes straight to the object: no attribute, no undefined value
            return lambda frame: obj_fn(frame)[arg_fn(frame)]
        return lambda frame: frame.ctx.environment.getitem(obj_fn(frame), arg_fn(frame))

    def x_Slice(self, node, st: State):
        parts = [self.expr(p, st) if p is not None else None for p in (node.start, node.stop, node.step)]
        return lambda frame: slice(*[p(frame) if p is not None else None for p in parts])

    def x_Concat(self, node, st: State):
        fns = [self.expr(n, st) for n in node.nodes]
        # (in a block whose autoescape option is a variable, Jinja checks ``eval_ctx.volatile`` where it should check ``autoescape``: ``~`` never makes markup)
        join = markup_join if st.autoescape and not st.volatile else str_join
        return lambda frame: join([fn(frame) for fn in fns])

    def x_Compare(self, node, st: State):
        first = self.expr(node.expr, st)
        ops = [(COMPARE[op.op], self.expr(op.expr, st)) for op in node.ops]
        if len(ops) == 1:
            func, right_fn = ops[0]
            return lambda frame: func(first(frame), right_fn(frame))

        def compare(frame: Frame) -> Any:
            left = first(frame)
            result = True
            for func, right_fn in ops:
                right = right_fn(frame)
                result = func(left, right)
                if not result:
                    return result
                left = right
            return result
        return compare

    def _binary(self, node, st: State):
        func = BINARY[type(node)]
        left, right = self.expr(node.left, st), self.expr(node.right, st)
        return lambda frame: func(left(frame), right(frame))

    x_Add = x_Sub = x_Mul = x_Div = x_FloorDiv = x_Mod = x_Pow = _binary

    def x_And(self, node, st: State):
        left, right = self.expr(node.left, st), self.expr(node.right, st)
        return lambda frame: left(frame) and right(frame)

    def x_Or(self, node, st: State):
        left, right = self.expr(node.left, st), self.expr(node.right, st)
        return lambda frame: left(frame) or right(frame)

    def x_Not(self, node, st: State):
        fn = self.expr(node.node, st)
        return lambda frame: not fn(frame)

    def x_Neg(self, node, st: State):
        fn = self.expr(node.node, st)
        return lambda frame: -fn(frame)

    def x_Pos(self, node, st: State):
        fn = self.expr(node.node, st)
        return lambda frame: +fn(frame)

    def x_CondExpr(self, node, st: State):
        st = st.replace(soft=True)
        test = self.expr(node.test, st)
        expr1 = self.expr(node.expr1, st)
        expr2 = self.expr(node.expr2, st) if node.expr2 is not None else None
        lineno = node.lineno

        def conditional(frame: Frame) -> Any:
            if test(frame):
                return expr1(frame)
            if expr2 is not None:
                return expr2(frame)
            # (always the plain Undefined, whatever the environment's undefined is)
            return Undefined("the inline if-expression on line %d evaluated to false and no else section was defined." % lineno)
        return conditional

    def arguments(self, node, st: State):
        """A function ``(frame) -> (args, kwargs)`` for the arguments of a call, a filter or a test."""
        arg_fns = [self.expr(a, st) for a in node.args]
        seen_keys = set()
        for k in node.kwargs:
            if k.key in seen_keys:                          # (Jinja lets Python's compiler find this one, after everything else was checked)
                if self.deferred_error is None:
                    self.deferred_error = TemplateSyntaxError("keyword argument repeated: %s" % k.key, k.lineno, self.name, self.filename)
            seen_keys.add(k.key)
        kw_fns = [(k.key, self.expr(k.value, st)) for k in node.kwargs]
        dyn_args = self.expr(node.dyn_args, st) if node.dyn_args is not None else None
        dyn_kwargs = self.expr(node.dyn_kwargs, st) if node.dyn_kwargs is not None else None

        def evaluate(frame: Frame):
            args = [fn(frame) for fn in arg_fns]
            kwargs = {key: fn(frame) for key, fn in kw_fns}
            if dyn_args is not None:
                args.extend(dyn_args(frame))
            if dyn_kwargs is not None:
                kwargs.update(dyn_kwargs(frame))
            return args, kwargs
        return evaluate

    def x_Call(self, node, st: State):
        func_fn = self.expr(node.node, st)
        evaluate = self.arguments(node, st)

        def call(frame: Frame) -> Any:
            func = func_fn(frame)
            args, kwargs = evaluate(frame)
            return call_object(frame, func, args, kwargs)
        return call

    def pre_args(self, func: Callable, frame: Frame) -> tuple:
        pass_arg = pass_arg_of(func)
        if pass_arg == "context":
            return (frame.ctx,)
        if pass_arg == "eval_context":
            return (frame.ctx.eval_ctx,)
        if pass_arg == "environment":
            return (frame.ctx.environment,)
        return ()

    def x_Filter(self, node, st: State):
        step = self.filter_step(node, st)               # (the outermost filter is looked up first, so an unknown one is reported in that order)
        value_fn = self.expr(node.node, st)
        return lambda frame: step(frame, value_fn(frame))

    def filter_step(self, node, st: State):
        """A function ``(frame, value) -> filtered value`` for one filter of a chain."""
        func = self.env.filters.get(node.name)
        if func is None:
            return self.missing_step("filter", node, st)
        return self.call_step(func, node, st)

    def call_step(self, func: Callable, node, st: State):
        """The call of a filter or a test: ``func(value, *arguments)``, with the context, the evaluation context or the environment in front if the
        function asks for it.  The common shapes (no arguments, positional arguments only) have a function of their own, which is a good deal faster."""
        pass_arg = pass_arg_of(func)
        simple = not node.kwargs and node.dyn_args is None and node.dyn_kwargs is None
        if simple and not node.args:
            if pass_arg is None:
                return lambda frame, value: func(value)
            if pass_arg == "context":
                return lambda frame, value: func(frame.ctx, value)
            if pass_arg == "eval_context":
                return lambda frame, value: func(frame.ctx.eval_ctx, value)
            return lambda frame, value: func(frame.ctx.environment, value)
        if simple and pass_arg is None:
            arg_fns = [self.expr(a, st) for a in node.args]
            return lambda frame, value: func(value, *[fn(frame) for fn in arg_fns])
        evaluate = self.arguments(node, st)
        pre_args = self.pre_args

        def step(frame: Frame, value: Any) -> Any:
            args, kwargs = evaluate(frame)
            return func(*pre_args(func, frame), value, *args, **kwargs)
        return step

    def missing_step(self, kind: str, node, st: State):
        """A filter or test that does not exist: an error when the template is compiled; inside a condition one only when it is called."""
        if not st.soft:
            self.fail("No %s named %r." % (kind, node.name), node.lineno)
        evaluate = self.arguments(node, st)
        message = "No %s named %r found." % (kind, node.name)

        def step(frame: Frame, value: Any) -> Any:
            evaluate(frame)                                 # (the arguments are evaluated before the call fails)
            raise TemplateRuntimeError(message)
        return step

    def filter_chain(self, node, st: State):
        """A function ``(frame, value)`` that applies the filters of a ``Filter`` node whose innermost input is the given value."""
        chain = []
        while node is not None:
            chain.append(node)
            node = node.node
        steps = [self.filter_step(n, st) for n in chain]
        steps.reverse()

        def apply(frame: Frame, value: Any) -> Any:
            for step in steps:
                value = step(frame, value)
            return value
        return apply

    def x_Test(self, node, st: State):
        func = self.env.tests.get(node.name)
        if func is None:
            step = self.missing_step("test", node, st)
            value_fn = self.expr(node.node, st)
            return lambda frame: step(frame, value_fn(frame))
        value_fn = self.expr(node.node, st)
        step = self.call_step(func, node, st)
        return lambda frame: step(frame, value_fn(frame))

    # statements

    def s_Output(self, node, st: State):
        if st.output_check and self.known_extends:
            return _noop                    # the template extends another one: what it writes outside of blocks is not output
        run = self.output(node, st)
        if st.output_check and self.extends_so_far:
            def run_unless_extended(frame: Frame, out: list) -> None:
                if frame.state.parent_template is None:
                    run(frame, out)
            return run_unless_extended
        return run

    def output(self, node, st: State):
        convert = escape_to_str if st.autoescape else str
        annotate = self.annotate
        items: list = []                        # constant text, or (the function of an expression, its line)
        for child in node.nodes:
            if isinstance(child, nodes.TemplateData):
                if items and isinstance(items[-1], str):
                    items[-1] += child.data
                else:
                    items.append(child.data)
            else:
                items.append((self.expr(child, st), child.lineno))
        if len(items) == 1 and isinstance(items[0], str):
            text = items[0]
            return lambda frame, out: out.append(text)
        if len(items) == 1:
            fn, lineno = items[0]

            def output_one(frame: Frame, out: list) -> None:
                try:
                    out.append(convert(fn(frame)))
                except Exception as exc:
                    annotate(exc, lineno)
                    raise
            return output_one

        def output(frame: Frame, out: list) -> None:
            for item in items:
                if item.__class__ is str:
                    out.append(item)
                else:
                    fn, lineno = item
                    try:
                        out.append(convert(fn(frame)))
                    except Exception as exc:
                        annotate(exc, lineno)       # (the line of the expression, not of the text before it)
                        raise
        return output

    def s_If(self, node, st: State):
        annotate = self.annotate
        soft = st.branch()                                  # (the tests too: an unknown filter in a condition only fails when it is called)
        branches = [(self.expr(node.test, soft), self.seq(node.body, soft), node.test.lineno)]
        for elif_ in node.elif_:
            branches.append((self.expr(elif_.test, soft), self.seq(elif_.body, soft), elif_.test.lineno))
        else_ = self.seq(node.else_, soft) if node.else_ else None

        def run(frame: Frame, out: list) -> None:
            for test, body, lineno in branches:
                try:
                    chosen = test(frame)
                except Exception as exc:
                    annotate(exc, lineno)
                    raise
                if chosen:
                    body(frame, out)
                    return
            if else_ is not None:
                else_(frame, out)
        return run

    def s_For(self, node, st: State):
        annotate, lineno = self.annotate, node.lineno
        inner = st.inner()
        if "loop" in {n.name for n in ([node.target] if isinstance(node.target, nodes.Name) else list(node.target.find_all(nodes.Name)))}:
            self.fail("Can't assign to special loop variable in for-loop target", node.lineno)
        target_store = self.store(node.target, inner)
        iter_fn = self.expr(node.iter, st)
        test_fn = self.expr(node.test, inner) if node.test is not None else None
        body = self.seq(node.body, inner)
        else_ = self.seq(node.else_, inner) if node.else_ else None
        recursive = node.recursive
        # ``loop`` is a variable of the body only if the body mentions it (so an included template does not get it: Jinja does the same)
        uses_loop = recursive or bool(_names_loaded(node.body, ("loop",)))

        # A scope is made per item - or one for the whole loop, when nothing in the body can keep it after the item (a macro or a call block that
        # is defined in the body, and called later, would see the values of a later item).
        reuse = not _contains(node.body, (nodes.Macro, nodes.CallBlock))
        clear = _contains(node.body, (nodes.Assign, nodes.AssignBlock, nodes.Import, nodes.FromImport))
        target_name = node.target.name if isinstance(node.target, nodes.Name) else None

        def run_loop(frame: Frame, out: list, iterable: Any, depth0: int, recurse: Optional[Callable]) -> None:
            ctx = frame.ctx
            if test_fn is not None:
                source = iterable

                def filtered():
                    for item in source:
                        test_frame = Frame(ctx, {}, frame)
                        target_store(test_frame, item)
                        if test_fn(test_frame):
                            yield item
                iterable = filtered()
            seen = False
            if uses_loop:
                loop = LoopContext(iterable, ctx.environment.undefined, recurse, depth0)
                iterator: Any = loop
            else:                                       # no ``loop`` object is needed: iterate directly
                loop = None
                iterator = iterable
            loop_frame = Frame(ctx, {}, frame)
            vars_ = loop_frame.vars
            for entry in iterator:
                if uses_loop:
                    item, loop = entry
                else:
                    item = entry
                seen = True
                if not reuse:
                    loop_frame = Frame(ctx, {}, frame)
                    vars_ = loop_frame.vars
                elif clear:
                    vars_.clear()
                if uses_loop:
                    vars_["loop"] = loop
                if target_name is not None:
                    vars_[target_name] = item
                else:
                    target_store(loop_frame, item)
                body(loop_frame, out)
            if not seen and else_ is not None:
                else_(Frame(ctx, {}, frame), out)

        def run(frame: Frame, out: list) -> None:
            try:
                iterable = iter_fn(frame)
                recurse = None
                if recursive:
                    def recurse_here(sub_iterable: Any, depth: int = 0) -> Any:
                        buf: list = []
                        run_loop(frame, buf, sub_iterable, depth, recurse_here)
                        rv = "".join(buf)
                        return Markup(rv) if st.autoescape else rv
                    recurse = recurse_here
                run_loop(frame, out, iterable, 0, recurse)
            except Exception as exc:
                annotate(exc, lineno)
                raise
        return run

    def s_Assign(self, node, st: State):
        annotate, lineno = self.annotate, node.lineno
        store = self.store(node.target, st)
        value_fn = self.expr(node.node, st)

        def run(frame: Frame, out: list) -> None:
            try:
                store(frame, value_fn(frame))
            except Exception as exc:
                annotate(exc, lineno)
                raise
        return run

    def s_AssignBlock(self, node, st: State):
        annotate, lineno = self.annotate, node.lineno
        store = self.store(node.target, st)
        body = self.seq(node.body, st.inner())
        chain = self.filter_chain(node.filter, st.inner()) if node.filter is not None else None
        autoescape = st.autoescape

        def run(frame: Frame, out: list) -> None:
            try:
                buf: list = []
                body(Frame(frame.ctx, {}, frame), buf)
                value = "".join(buf)
                if autoescape:
                    value = Markup(value)
                if chain is not None:
                    value = chain(frame, value)
                store(frame, value)
            except Exception as exc:
                annotate(exc, lineno)
                raise
        return run

    def s_With(self, node, st: State):
        annotate, lineno = self.annotate, node.lineno
        inner = st.inner()
        stores = [self.store(t, inner) for t in node.targets]
        value_fns = [self.expr(v, st) for v in node.values]
        body = self.seq(node.body, inner)

        def run(frame: Frame, out: list) -> None:
            try:
                with_frame = Frame(frame.ctx, {}, frame)
                values = [fn(frame) for fn in value_fns]            # the values see the variables around the block, not each other
                for store, value in zip(stores, values):
                    store(with_frame, value)
                body(with_frame, out)
            except Exception as exc:
                annotate(exc, lineno)
                raise
        return run

    def s_FilterBlock(self, node, st: State):
        annotate, lineno = self.annotate, node.lineno
        body = self.seq(node.body, st.inner())
        chain = self.filter_chain(node.filter, st.inner())
        autoescape = st.autoescape

        def run(frame: Frame, out: list) -> None:
            try:
                buf: list = []
                body(Frame(frame.ctx, {}, frame), buf)
                text = "".join(buf)
                out.append(chain(frame, Markup(text) if autoescape else text))
            except Exception as exc:
                annotate(exc, lineno)
                raise
        return run

    def macro_maker(self, node, st: State, name: Optional[str]):
        """A function ``(frame) -> Macro`` for a ``macro`` or the body of a ``call`` block."""
        arg_names = [a.name for a in node.args]
        defaults = [self.expr(d, st) for d in node.defaults]
        first_default = len(arg_names) - len(defaults)
        body = self.seq(node.body, st.function())
        used = _names_loaded(node.body, ("caller", "kwargs", "varargs"))
        catch_kwargs = "kwargs" in used and "kwargs" not in arg_names
        catch_varargs = "varargs" in used and "varargs" not in arg_names
        wants_caller = "caller" in used and "caller" not in arg_names
        env = self.env

        def make(frame: Frame) -> Macro:
            def func(*arguments: Any) -> str:
                macro_frame = Frame(frame.ctx, {}, frame)
                macro_frame.state = None
                vars_ = macro_frame.vars
                for i, arg in enumerate(arg_names):
                    value = arguments[i]
                    if value is missing:
                        if i >= first_default:
                            value = defaults[i - first_default](macro_frame)
                        else:
                            value = env.undefined("parameter %r was not provided" % arg, name=arg)
                    vars_[arg] = value
                extra = iter(arguments[len(arg_names):])
                if wants_caller:
                    vars_["caller"] = next(extra)
                if catch_kwargs:
                    vars_["kwargs"] = next(extra)
                if catch_varargs:
                    vars_["varargs"] = next(extra)
                buf: list = []
                body(macro_frame, buf)
                return "".join(buf)
            return Macro(env, func, name, arg_names, catch_kwargs, catch_varargs, wants_caller, st.autoescape)
        return make

    def s_Macro(self, node, st: State):
        make = self.macro_maker(node, st, node.name)
        store = self.store(nodes.Name(node.name, "store", lineno=node.lineno), st)

        def run(frame: Frame, out: list) -> None:
            store(frame, make(frame))
        return run

    def s_CallBlock(self, node, st: State):
        annotate, lineno = self.annotate, node.lineno
        make_caller = self.macro_maker(node, st, None)
        func_fn = self.expr(node.call.node, st)
        evaluate = self.arguments(node.call, st)

        def run(frame: Frame, out: list) -> None:
            try:
                caller = make_caller(frame)
                func = func_fn(frame)
                args, kwargs = evaluate(frame)
                kwargs["caller"] = caller
                out.append(call_object(frame, func, args, kwargs))
            except Exception as exc:
                annotate(exc, lineno)
                raise
        return run

    def s_Block(self, node, st: State):
        annotate, lineno = self.annotate, node.lineno
        name = node.name
        if name in self.blocks:
            self.fail("block %r defined twice" % name, node.lineno)
        cell: list = [None]
        self.blocks[name] = None            # (reserved: nested blocks are compiled before this one is finished)
        body = self.seq(node.body, st.function().replace(block=(name, cell)))

        def block(ctx, out: list, outer: Optional[Frame]) -> None:
            frame = Frame(ctx, {}, outer if outer is not None else ctx.root_frame)
            frame.state = None
            body(frame, out)
        cell[0] = block
        self.blocks[name] = block
        scoped, required = node.scoped, node.required

        def run(frame: Frame, out: list) -> None:
            try:
                ctx = frame.ctx
                if required and len(ctx.blocks[name]) <= 1:
                    raise TemplateRuntimeError("Required block %r not found" % name)
                ctx.blocks[name][0](ctx, out, frame if scoped else None)
            except Exception as exc:
                annotate(exc, lineno)
                raise
        if st.toplevel and self.known_extends:
            return _noop                    # the template extends another one: the parent decides where the block goes
        if st.toplevel and self.extends_so_far:
            def run_unless_extended(frame: Frame, out: list) -> None:
                if frame.state.parent_template is None:
                    run(frame, out)
            return run_unless_extended
        return run

    def s_Extends(self, node, st: State):
        annotate, lineno = self.annotate, node.lineno
        if not st.toplevel:
            self.fail("cannot use extend from a non top-level scope", node.lineno)
        template_fn = self.expr(node.template, st)
        parent_name = self.name
        if st.rootlevel:
            self.known_extends = True
        self.extends_so_far += 1

        def run(frame: Frame, out: list) -> None:
            try:
                state = frame.state
                if state.parent_template is not None:
                    raise TemplateRuntimeError("extended multiple times")
                ctx = frame.ctx
                parent = ctx.environment.get_template(template_fn(frame), parent_name)
                state.parent_template = parent
                for block_name, block in parent.blocks.items():
                    ctx.blocks.setdefault(block_name, []).append(block)
            except Exception as exc:
                annotate(exc, lineno)
                raise
        return run

    def s_Include(self, node, st: State):
        annotate, lineno = self.annotate, node.lineno
        template_fn = self.expr(node.template, st)
        ignore_missing, with_context = node.ignore_missing, node.with_context
        parent_name = self.name

        def run(frame: Frame, out: list) -> None:
            try:
                ctx = frame.ctx
                try:
                    template = ctx.environment.get_or_select_template(template_fn(frame), parent_name)
                except TemplateNotFound:
                    if ignore_missing:
                        return
                    raise
                if with_context:
                    variables = dict(ctx.parent)
                    variables.update(frame.locals())
                    new_ctx = template.new_context(variables, shared=True)
                else:
                    new_ctx = template.new_context()
                template.root_render(new_ctx, out)
            except Exception as exc:
                annotate(exc, lineno)
                raise
        return run

    def _module(self, frame: Frame, template, with_context: bool):
        if with_context:
            variables = dict(frame.ctx.parent)
            variables.update(frame.locals())
            return template.make_module(variables, shared=True)
        return template.module

    def s_Import(self, node, st: State):
        annotate, lineno = self.annotate, node.lineno
        template_fn = self.expr(node.template, st)
        store = self.store(nodes.Name(node.target, "store", lineno=node.lineno), st)
        with_context = node.with_context
        parent_name = self.name

        def run(frame: Frame, out: list) -> None:
            try:
                template = frame.ctx.environment.get_template(template_fn(frame), parent_name)
                store(frame, self._module(frame, template, with_context))
            except Exception as exc:
                annotate(exc, lineno)
                raise
        return run

    def s_FromImport(self, node, st: State):
        annotate, lineno = self.annotate, node.lineno
        template_fn = self.expr(node.template, st)
        with_context = node.with_context
        parent_name = self.name
        items = []
        for entry in node.names:
            name, alias = entry if isinstance(entry, tuple) else (entry, entry)
            items.append((name, self.store(nodes.Name(alias, "store", lineno=node.lineno), st)))
        lineno = node.lineno

        def run(frame: Frame, out: list) -> None:
            try:
                template = frame.ctx.environment.get_template(template_fn(frame), parent_name)
                module = self._module(frame, template, with_context)
                for name, store in items:
                    value = getattr(module, name, missing)
                    if value is missing:
                        value = frame.ctx.environment.undefined(
                            "the template %r (imported on line %d) does not export the requested name %r" % (module.__name__, lineno, name), name=name)
                    store(frame, value)
            except Exception as exc:
                annotate(exc, lineno)
                raise
        return run

    def s_AutoescapeBlock(self, node, st: State):
        annotate, lineno = self.annotate, node.lineno
        option = self.expr(node.option, st)
        volatile = not isinstance(node.option, nodes.Const)
        body_on = self.seq(node.body, st.inner().replace(autoescape=True, volatile=volatile))
        body_off = self.seq(node.body, st.inner().replace(autoescape=False, volatile=volatile))

        def run(frame: Frame, out: list) -> None:
            try:
                eval_ctx = frame.ctx.eval_ctx
                saved = eval_ctx.autoescape
                value = bool(option(frame))
                eval_ctx.autoescape = value
                try:
                    (body_on if value else body_off)(Frame(frame.ctx, {}, frame), out)
                finally:
                    eval_ctx.autoescape = saved
            except Exception as exc:
                annotate(exc, lineno)
                raise
        return run


def call_object(frame: Frame, func: Any, args: list, kwargs: dict) -> Any:
    """Calls a value of the template: a macro, a function of the globals, a method of an object."""
    pass_arg = pass_arg_of(func) or pass_arg_of(getattr(func, "__call__", None))
    try:
        if pass_arg is None:
            return func(*args, **kwargs)
        if pass_arg == "eval_context":                      # (a macro: it wants to know if its caller escapes)
            return func(frame.ctx.eval_ctx, *args, **kwargs)
        if pass_arg == "environment":
            return func(frame.ctx.environment, *args, **kwargs)
        kwargs["_local_vars"] = frame.locals() if frame.parent is not None else None
        return frame.ctx.call(func, *args, **kwargs)
    except StopIteration:
        return frame.ctx.environment.undefined("value was undefined because a callable raised a StopIteration exception")
