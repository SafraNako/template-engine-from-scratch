"""What exists while a template renders: the context, the values that stand for "nothing there", the loop object, macros."""
from __future__ import annotations

from itertools import chain
from typing import Any, Callable, Dict, Iterator, List, Optional

from .errors import UndefinedError
from .markup import Markup, soft_str
from .utils import missing, object_type_repr, pass_arg_of


def markup_join(seq) -> str:
    """Joins the items; if one of them is safe markup, the others are escaped and the result is markup too."""
    buf = []
    iterator = map(soft_str, seq)
    for arg in iterator:
        buf.append(arg)
        if hasattr(arg, "__html__"):
            return Markup("").join(chain(buf, iterator))
    return "".join(buf)


def str_join(seq) -> str:
    return "".join(map(str, seq))


class EvalContext:
    """The state that decides how output is turned into text: so far only ``autoescape``.  The ``autoescape`` block changes it for its body."""

    def __init__(self, environment, template_name: Optional[str] = None) -> None:
        self.environment = environment
        if callable(environment.autoescape):
            self.autoescape = environment.autoescape(template_name)
        else:
            self.autoescape = environment.autoescape
        self.volatile = False


# values that are not there

class Undefined:
    """What a name that does not exist is worth.  Printing it gives "", iterating gives nothing, it is false; any other use raises ``UndefinedError``."""

    __slots__ = ("_undefined_hint", "_undefined_obj", "_undefined_name", "_undefined_exception")

    def __init__(self, hint: Optional[str] = None, obj: Any = missing, name: Optional[str] = None, exc=UndefinedError) -> None:
        self._undefined_hint = hint
        self._undefined_obj = obj
        self._undefined_name = name
        self._undefined_exception = exc

    @property
    def _undefined_message(self) -> str:
        if self._undefined_hint:
            return self._undefined_hint
        if self._undefined_obj is missing:
            return "%r is undefined" % self._undefined_name
        if not isinstance(self._undefined_name, str):
            return "%s has no element %r" % (object_type_repr(self._undefined_obj), self._undefined_name)
        return "%r has no attribute %r" % (object_type_repr(self._undefined_obj), self._undefined_name)

    def _fail_with_undefined_error(self, *args: Any, **kwargs: Any):
        raise self._undefined_exception(self._undefined_message)

    def __getattr__(self, name: str) -> Any:
        if name[:2] == "__" and name[-2:] == "__":              # let Python's own probing (copy, pickle, ...) see that it is not implemented
            raise AttributeError(name)
        return self._fail_with_undefined_error()

    __add__ = __radd__ = __sub__ = __rsub__ = _fail_with_undefined_error
    __mul__ = __rmul__ = __div__ = __rdiv__ = _fail_with_undefined_error
    __truediv__ = __rtruediv__ = _fail_with_undefined_error
    __floordiv__ = __rfloordiv__ = _fail_with_undefined_error
    __mod__ = __rmod__ = _fail_with_undefined_error
    __pos__ = __neg__ = _fail_with_undefined_error
    __call__ = __getitem__ = _fail_with_undefined_error
    __lt__ = __le__ = __gt__ = __ge__ = _fail_with_undefined_error
    __int__ = __float__ = __complex__ = _fail_with_undefined_error
    __pow__ = __rpow__ = _fail_with_undefined_error

    def __eq__(self, other: Any) -> bool:
        return type(self) is type(other)

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return id(type(self))

    def __str__(self) -> str:
        return ""

    def __len__(self) -> int:
        return 0

    def __iter__(self) -> Iterator[Any]:
        yield from ()

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "Undefined"


class ChainableUndefined(Undefined):
    """An undefined that stays undefined when an attribute or an item of it is asked for: ``{{ a.b.c }}`` is "" and not an error."""

    __slots__ = ()

    def __html__(self) -> str:
        return str(self)

    def __getattr__(self, name: str) -> "ChainableUndefined":
        if name[:2] == "__" and name[-2:] == "__":
            raise AttributeError(name)
        return self

    def __getitem__(self, _name: Any) -> "ChainableUndefined":
        return self


class DebugUndefined(Undefined):
    """Prints what is missing, as ``{{ name }}``, instead of nothing."""

    __slots__ = ()

    def __str__(self) -> str:
        if self._undefined_hint:
            message = "undefined value printed: %s" % self._undefined_hint
        elif self._undefined_obj is missing:
            message = self._undefined_name
        else:
            message = "no such element: %s[%r]" % (object_type_repr(self._undefined_obj), self._undefined_name)
        return "{{ %s }}" % message


class StrictUndefined(Undefined):
    """Fails on every use except ``is defined`` (printing, iterating, comparing, a truth test)."""

    __slots__ = ()
    __iter__ = __str__ = __len__ = Undefined._fail_with_undefined_error
    __eq__ = __ne__ = __bool__ = __hash__ = Undefined._fail_with_undefined_error
    __contains__ = Undefined._fail_with_undefined_error


# scopes

class Frame:
    """One scope of variables.  The chain of ``parent`` frames ends at the template's top level, whose ``vars`` are those of the context."""

    __slots__ = ("ctx", "vars", "parent", "state")

    def __init__(self, ctx: "Context", vars: Dict[str, Any], parent: Optional["Frame"]) -> None:
        self.ctx = ctx
        self.vars = vars
        self.parent = parent
        self.state = parent.state if parent is not None else None

    def locals(self) -> Dict[str, Any]:
        """Every variable that this scope can see, except what the render call and the globals gave (those are in ``ctx.parent``)."""
        chain_ = []
        frame: Optional[Frame] = self
        while frame is not None:
            chain_.append(frame.vars)
            frame = frame.parent
        merged: Dict[str, Any] = {}
        for vars_ in reversed(chain_):
            merged.update(vars_)
        return merged


class RootState:
    """Per run of a template's top level: has it been told to extend another template?"""

    __slots__ = ("parent_template",)

    def __init__(self) -> None:
        self.parent_template = None


class Context:
    """The variables of one rendering.  ``parent`` holds what the render call gave (plus the globals), ``vars`` what the template's top level assigned."""

    def __init__(self, environment, parent: Dict[str, Any], name: Optional[str], blocks: Dict[str, Callable], globals_=None) -> None:
        self.parent = parent
        self.vars: Dict[str, Any] = {}
        self.environment = environment
        self.eval_ctx = EvalContext(environment, name)
        self.exported_vars: set = set()
        self.name = name
        self.globals_keys = set() if globals_ is None else set(globals_)
        self.blocks: Dict[str, List[Callable]] = {k: [v] for k, v in blocks.items()}
        self.root_frame = Frame(self, self.vars, None)

    def super(self, name: str, current: Callable):
        """The block of the same name in the template that this one extends."""
        try:
            blocks = self.blocks[name]
            index = blocks.index(current) + 1
            blocks[index]
        except LookupError:
            return self.environment.undefined("there is no parent block called %r." % name, name="super")
        return BlockReference(name, self, blocks, index)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def resolve(self, key: str) -> Any:
        rv = self.resolve_or_missing(key)
        if rv is missing:
            return self.environment.undefined(name=key)
        return rv

    def resolve_or_missing(self, key: str) -> Any:
        if key in self.vars:
            return self.vars[key]
        if key in self.parent:
            return self.parent[key]
        return missing

    def get_exported(self) -> Dict[str, Any]:
        return {k: self.vars[k] for k in self.exported_vars}

    def get_all(self) -> Dict[str, Any]:
        if not self.vars:
            return self.parent
        if not self.parent:
            return self.vars
        return dict(self.parent, **self.vars)

    def derived(self, locals_: Optional[Dict[str, Any]] = None) -> "Context":
        """A context that sees the same variables but can be changed without changing this one."""
        context = new_context(self.environment, self.name, {}, self.get_all(), True, None, locals_)
        context.eval_ctx = self.eval_ctx
        context.blocks.update((k, list(v)) for k, v in self.blocks.items())
        return context

    def call(__self, __obj: Callable, *args: Any, **kwargs: Any) -> Any:
        """Calls ``__obj``; a function marked with ``pass_context`` and friends gets the context, the evaluation context or the environment first."""
        pass_arg = pass_arg_of(__obj) or pass_arg_of(getattr(__obj, "__call__", None))
        if pass_arg == "context":
            local_vars = kwargs.pop("_local_vars", None)
            ctx = __self.derived(local_vars) if local_vars else __self
            args = (ctx,) + args
        elif pass_arg == "eval_context":
            args = (__self.eval_ctx,) + args
        elif pass_arg == "environment":
            args = (__self.environment,) + args
        kwargs.pop("_local_vars", None)
        try:
            return __obj(*args, **kwargs)
        except StopIteration:
            return __self.environment.undefined("value was undefined because a callable raised a StopIteration exception")

    def keys(self):
        return self.get_all().keys()

    def values(self):
        return self.get_all().values()

    def items(self):
        return self.get_all().items()

    def __contains__(self, name: str) -> bool:
        return name in self.vars or name in self.parent

    def __getitem__(self, key: str) -> Any:
        item = self.resolve_or_missing(key)
        if item is missing:
            raise KeyError(key)
        return item

    def __repr__(self) -> str:
        return "<%s %r of %r>" % (type(self).__name__, self.get_all(), self.name)


def new_context(environment, template_name: Optional[str], blocks: Dict[str, Callable], vars_: Optional[Dict[str, Any]] = None, shared: bool = False,
                globals_: Optional[Dict[str, Any]] = None, locals_: Optional[Dict[str, Any]] = None) -> Context:
    if vars_ is None:
        vars_ = {}
    if shared:
        parent = vars_
    else:
        parent = dict(globals_ or (), **vars_)
    if locals_:
        if shared:
            parent = dict(parent)
        for key, value in locals_.items():
            if value is not missing:
                parent[key] = value
    return Context(environment, parent, template_name, blocks, globals_)


class TemplateReference:
    """``self`` in a template: ``self.title()`` renders the block ``title``."""

    def __init__(self, context: Context) -> None:
        self.__context = context

    def __getitem__(self, name: str) -> "BlockReference":
        blocks = self.__context.blocks[name]
        return BlockReference(name, self.__context, blocks, 0)

    def __repr__(self) -> str:
        return "<%s %r>" % (type(self).__name__, self.__context.name)


class BlockReference:
    """A block that can be rendered by calling it (``self.name()`` and ``super()``)."""

    def __init__(self, name: str, context: Context, stack: List[Callable], depth: int) -> None:
        self.name = name
        self._context = context
        self._stack = stack
        self._depth = depth

    @property
    def super(self):
        if self._depth + 1 >= len(self._stack):
            return self._context.environment.undefined("there is no parent block called %r." % self.name, name="super")
        return BlockReference(self.name, self._context, self._stack, self._depth + 1)

    def __call__(self) -> str:
        out: List[str] = []
        self._stack[self._depth](self._context, out, None)
        rv = "".join(out)
        if self._context.eval_ctx.autoescape:
            return Markup(rv)
        return rv


# loops

class LoopContext:
    """``loop`` inside a ``for``: the position in the sequence and the neighbours of the current item."""

    index0 = -1
    _length: Optional[int] = None
    _after: Any = missing
    _current: Any = missing
    _before: Any = missing
    _last_changed_value: Any = missing

    def __init__(self, iterable, undefined, recurse: Optional[Callable] = None, depth0: int = 0) -> None:
        self._iterable = iterable
        self._iterator = iter(iterable)
        self._undefined = undefined
        self._recurse = recurse
        self.depth0 = depth0

    @property
    def length(self) -> int:
        if self._length is not None:
            return self._length
        try:
            self._length = len(self._iterable)
        except TypeError:                                       # a generator: read the rest to know how long it is
            iterable = list(self._iterator)
            self._iterator = iter(iterable)
            self._length = len(iterable) + self.index + (self._after is not missing)
        return self._length

    def __len__(self) -> int:
        return self.length

    @property
    def depth(self) -> int:
        return self.depth0 + 1

    @property
    def index(self) -> int:
        return self.index0 + 1

    @property
    def revindex0(self) -> int:
        return self.length - self.index

    @property
    def revindex(self) -> int:
        return self.length - self.index0

    @property
    def first(self) -> bool:
        return self.index0 == 0

    def _peek_next(self) -> Any:
        """The next item, or ``missing``; it is kept for the next step, so that asking does not lose it."""
        if self._after is not missing:
            return self._after
        self._after = next(self._iterator, missing)
        return self._after

    @property
    def last(self) -> bool:
        return self._peek_next() is missing

    @property
    def previtem(self) -> Any:
        if self.first:
            return self._undefined("there is no previous item")
        return self._before

    @property
    def nextitem(self) -> Any:
        rv = self._peek_next()
        if rv is missing:
            return self._undefined("there is no next item")
        return rv

    def cycle(self, *args: Any) -> Any:
        if not args:
            raise TypeError("no items for cycling given")
        return args[self.index0 % len(args)]

    def changed(self, *value: Any) -> bool:
        if self._last_changed_value != value:
            self._last_changed_value = value
            return True
        return False

    def __iter__(self) -> "LoopContext":
        return self

    def __next__(self):
        if self._after is not missing:
            rv = self._after
            self._after = missing
        else:
            rv = next(self._iterator)
        self.index0 += 1
        self._before = self._current
        self._current = rv
        return rv, self

    def __call__(self, iterable) -> str:
        if self._recurse is None:
            raise TypeError("The loop must have the 'recursive' marker to be called recursively.")
        return self._recurse(iterable, depth=self.depth)

    def __repr__(self) -> str:
        return "<%s %d/%d>" % (type(self).__name__, self.index, self.length)


# macros

class Macro:
    """A ``{% macro %}`` (or the body of a ``{% call %}``) as a callable value."""

    _pass_arg = "eval_context"

    def __init__(self, environment, func: Callable, name: Optional[str], arguments: List[str], catch_kwargs: bool, catch_varargs: bool, caller: bool,
                 default_autoescape: Optional[bool] = None) -> None:
        self._environment = environment
        self._func = func
        self._argument_count = len(arguments)
        self.name = name
        self.arguments = tuple(arguments)
        self.catch_kwargs = catch_kwargs
        self.catch_varargs = catch_varargs
        self.caller = caller
        self.explicit_caller = "caller" in arguments
        if default_autoescape is None:
            default_autoescape = environment.autoescape(None) if callable(environment.autoescape) else environment.autoescape
        self._default_autoescape = default_autoescape

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        # the caller's evaluation context decides if the result is markup; calling a macro from Python gives no such context
        if args and isinstance(args[0], EvalContext):
            autoescape = args[0].autoescape
            args = args[1:]
        else:
            autoescape = self._default_autoescape
        arguments = list(args[: self._argument_count])
        off = len(arguments)
        found_caller = False
        if off != self._argument_count:                         # fill in the rest from the keywords; what is left over is left to the defaults
            for name in self.arguments[len(arguments):]:
                value = kwargs.pop(name, missing)
                if name == "caller":
                    found_caller = True
                arguments.append(value)
        else:
            found_caller = self.explicit_caller
        if self.caller and not found_caller:
            caller = kwargs.pop("caller", None)
            if caller is None:
                caller = self._environment.undefined("No caller defined", name="caller")
            arguments.append(caller)
        if self.catch_kwargs:
            arguments.append(kwargs)
        elif kwargs:
            if "caller" in kwargs:
                raise TypeError("macro %r was invoked with two values for the special caller argument. This is most likely a bug." % self.name)
            raise TypeError("macro %r takes no keyword argument %r" % (self.name, next(iter(kwargs))))
        if self.catch_varargs:
            arguments.append(args[self._argument_count:])
        elif len(args) > self._argument_count:
            raise TypeError("macro %r takes not more than %d argument(s)" % (self.name, len(self.arguments)))
        rv = self._func(*arguments)
        if autoescape:
            rv = Markup(rv)
        return rv

    def __repr__(self) -> str:
        return "<%s %s>" % (type(self).__name__, "anonymous" if self.name is None else repr(self.name))
