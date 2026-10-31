"""Builds the syntax tree from the tokens (recursive descent; one method per level of precedence)."""
from __future__ import annotations

from typing import List, Optional, Tuple

from . import nodes
from .errors import TemplateAssertionError, TemplateSyntaxError
from .lexer import describe_token, describe_token_expr

STATEMENTS = frozenset(["for", "if", "block", "extends", "print", "macro", "include", "from", "import", "set", "with", "autoescape", "call", "filter"])
COMPARE_OPERATORS = frozenset(["eq", "ne", "lt", "lteq", "gt", "gteq"])
MATH = {"add": nodes.Add, "sub": nodes.Sub, "mul": nodes.Mul, "div": nodes.Div, "floordiv": nodes.FloorDiv, "mod": nodes.Mod}


class Parser:
    def __init__(self, environment, source: str, name: Optional[str] = None, filename: Optional[str] = None) -> None:
        self.environment = environment
        self.stream = environment.lexer.tokenize(source, name, filename)
        self.name = name
        self.filename = filename
        self._tag_stack: List[str] = []
        self._end_token_stack: List[Tuple[str, ...]] = []

    # errors

    def fail(self, msg: str, lineno: Optional[int] = None, exc=TemplateSyntaxError):
        if lineno is None:
            lineno = self.stream.current.lineno
        raise exc(msg, lineno, self.name, self.filename)

    def _fail_ut_eof(self, name: Optional[str], end_token_stack: List[Tuple[str, ...]], lineno: Optional[int]):
        expected = set()
        for exprs in end_token_stack:
            expected.update(map(describe_token_expr, exprs))
        currently_looking = " or ".join(map(repr, map(describe_token_expr, end_token_stack[-1]))) if end_token_stack else None
        message = ["Unexpected end of template."] if name is None else ["Encountered unknown tag %r." % name]
        if currently_looking:
            if name is not None and name in expected:
                message.append("You probably made a nesting mistake. Jinja is expecting this tag, but currently looking for %s." % currently_looking)
            else:
                message.append("Jinja was looking for the following tags: %s." % currently_looking)
        if self._tag_stack:
            message.append("The innermost block that needs to be closed is %r." % self._tag_stack[-1])
        self.fail(" ".join(message), lineno)

    def fail_eof(self, end_tokens: Optional[Tuple[str, ...]] = None, lineno: Optional[int] = None):
        stack = list(self._end_token_stack)
        if end_tokens is not None:
            stack.append(end_tokens)
        self._fail_ut_eof(None, stack, lineno)

    def is_tuple_end(self, extra_end_rules: Optional[Tuple[str, ...]] = None) -> bool:
        if self.stream.current.type in ("variable_end", "block_end", "rparen"):
            return True
        # Jinja passes the rules to ``test_any`` as one argument, so they never match: ``{% for a, in x %}`` reads ``in`` as a name.  Kept as it is,
        # because a template that Jinja rejects should not be accepted here.
        return False

    # statements

    def parse_statement(self):
        token = self.stream.current
        if token.type != "name":
            self.fail("tag name expected", token.lineno)
        self._tag_stack.append(token.value)
        pop_tag = True
        try:
            if token.value in STATEMENTS:
                return getattr(self, "parse_" + token.value)()
            self._tag_stack.pop()
            pop_tag = False
            self._fail_ut_eof(token.value, self._end_token_stack, token.lineno)
        finally:
            if pop_tag:
                self._tag_stack.pop()

    def parse_statements(self, end_tokens: Tuple[str, ...], drop_needle: bool = False):
        self.stream.skip_if("colon")                        # {% if x: %} is allowed
        self.stream.expect("block_end")
        result = self.subparse(end_tokens)
        if self.stream.current.type == "eof":
            self.fail_eof(end_tokens)
        if drop_needle:
            next(self.stream)
        return result

    def parse_set(self):
        lineno = next(self.stream).lineno
        target = self.parse_assign_target(with_namespace=True)
        if self.stream.skip_if("assign"):
            return nodes.Assign(target, self.parse_tuple(), lineno=lineno)
        filter_node = self.parse_filter_chain(None)
        body = self.parse_statements(("name:endset",), drop_needle=True)
        return nodes.AssignBlock(target, filter_node, body, lineno=lineno)

    def parse_for(self):
        lineno = self.stream.expect("name:for").lineno
        target = self.parse_assign_target(extra_end_rules=("name:in",))
        self.stream.expect("name:in")
        iter_ = self.parse_tuple(with_condexpr=False, extra_end_rules=("name:recursive",))
        test = None
        if self.stream.skip_if("name:if"):
            test = self.parse_expression()
        recursive = self.stream.skip_if("name:recursive")
        body = self.parse_statements(("name:endfor", "name:else"))
        if next(self.stream).value == "endfor":
            else_ = []
        else:
            else_ = self.parse_statements(("name:endfor",), drop_needle=True)
        return nodes.For(target, iter_, body, else_, test, recursive, lineno=lineno)

    def parse_if(self):
        node = result = nodes.If(lineno=self.stream.expect("name:if").lineno)
        while True:
            node.test = self.parse_tuple(with_condexpr=False)
            node.body = self.parse_statements(("name:elif", "name:else", "name:endif"))
            node.elif_ = []
            node.else_ = []
            token = next(self.stream)
            if token.test("name:elif"):
                node = nodes.If(lineno=self.stream.current.lineno)
                result.elif_.append(node)
                continue
            if token.test("name:else"):
                result.else_ = self.parse_statements(("name:endif",), drop_needle=True)
            break
        return result

    def parse_with(self):
        node = nodes.With(lineno=next(self.stream).lineno)
        targets, values = [], []
        while self.stream.current.type != "block_end":
            if targets:
                self.stream.expect("comma")
            target = self.parse_assign_target()
            target.set_ctx("param")
            targets.append(target)
            self.stream.expect("assign")
            values.append(self.parse_expression())
        node.targets, node.values = targets, values
        node.body = self.parse_statements(("name:endwith",), drop_needle=True)
        return node

    def parse_autoescape(self):
        node = nodes.AutoescapeBlock(lineno=next(self.stream).lineno)
        node.option = self.parse_expression()
        node.body = self.parse_statements(("name:endautoescape",), drop_needle=True)
        return node

    def parse_block(self):
        node = nodes.Block(lineno=next(self.stream).lineno)
        node.name = self.stream.expect("name").value
        node.scoped = self.stream.skip_if("name:scoped")
        node.required = self.stream.skip_if("name:required")
        if self.stream.current.type == "sub":
            self.fail("Block names in Jinja have to be valid Python identifiers and may not contain hyphens, use an underscore instead.")
        node.body = self.parse_statements(("name:endblock",), drop_needle=True)
        if node.required:                                   # a required block holds nothing but whitespace and comments
            for body_node in node.body:
                if not isinstance(body_node, nodes.Output) or any(not isinstance(n, nodes.TemplateData) or not n.data.isspace() for n in body_node.nodes):
                    self.fail("Required blocks can only contain comments or whitespace")
        self.stream.skip_if("name:" + node.name)
        return node

    def parse_extends(self):
        node = nodes.Extends(lineno=next(self.stream).lineno)
        node.template = self.parse_expression()
        return node

    def parse_import_context(self, node, default: bool):
        if self.stream.current.test_any("name:with", "name:without") and self.stream.look().test("name:context"):
            node.with_context = next(self.stream).value == "with"
            self.stream.skip()
        else:
            node.with_context = default
        return node

    def parse_include(self):
        node = nodes.Include(lineno=next(self.stream).lineno)
        node.template = self.parse_expression()
        if self.stream.current.test("name:ignore") and self.stream.look().test("name:missing"):
            node.ignore_missing = True
            self.stream.skip(2)
        else:
            node.ignore_missing = False
        return self.parse_import_context(node, True)

    def parse_import(self):
        node = nodes.Import(lineno=next(self.stream).lineno)
        node.template = self.parse_expression()
        self.stream.expect("name:as")
        node.target = self.parse_assign_target(name_only=True).name
        return self.parse_import_context(node, False)

    def parse_from(self):
        node = nodes.FromImport(lineno=next(self.stream).lineno)
        node.template = self.parse_expression()
        self.stream.expect("name:import")
        node.names = []

        def parse_context() -> bool:
            if self.stream.current.value in {"with", "without"} and self.stream.look().test("name:context"):
                node.with_context = next(self.stream).value == "with"
                self.stream.skip()
                return True
            return False

        while True:
            if node.names:
                self.stream.expect("comma")
            if self.stream.current.type == "name":
                if parse_context():
                    break
                target = self.parse_assign_target(name_only=True)
                if target.name.startswith("_"):
                    self.fail("names starting with an underline can not be imported", target.lineno, exc=TemplateAssertionError)
                if self.stream.skip_if("name:as"):
                    alias = self.parse_assign_target(name_only=True)
                    node.names.append((target.name, alias.name))
                else:
                    node.names.append(target.name)
                if parse_context() or self.stream.current.type != "comma":
                    break
            else:
                self.stream.expect("name")
        if node.with_context is None:
            node.with_context = False
        return node

    def parse_signature(self, node) -> None:
        args = node.args = []
        defaults = node.defaults = []
        self.stream.expect("lparen")
        while self.stream.current.type != "rparen":
            if args:
                self.stream.expect("comma")
            arg = self.parse_assign_target(name_only=True)
            arg.set_ctx("param")
            if self.stream.skip_if("assign"):
                defaults.append(self.parse_expression())
            elif defaults:
                self.fail("non-default argument follows default argument")
            args.append(arg)
        self.stream.expect("rparen")

    def parse_call(self):
        """The ``call`` statement; a call inside an expression is :meth:`parse_call_expr`."""
        node = nodes.CallBlock(lineno=next(self.stream).lineno)
        if self.stream.current.type == "lparen":
            self.parse_signature(node)
        else:
            node.args, node.defaults = [], []
        call_node = self.parse_expression()
        if not isinstance(call_node, nodes.Call):
            self.fail("expected call", node.lineno)
        node.call = call_node
        node.body = self.parse_statements(("name:endcall",), drop_needle=True)
        return node

    def parse_filter(self):
        """The ``filter`` statement; a filter inside an expression is :meth:`parse_filter_chain`."""
        node = nodes.FilterBlock(lineno=next(self.stream).lineno)
        node.filter = self.parse_filter_chain(None, start_inline=True)
        node.body = self.parse_statements(("name:endfilter",), drop_needle=True)
        return node

    def parse_filter_chain(self, node, start_inline: bool = False):
        while self.stream.current.type == "pipe" or start_inline:
            if not start_inline:
                next(self.stream)
            token = self.stream.expect("name")
            name = token.value
            while self.stream.current.type == "dot":
                next(self.stream)
                name += "." + self.stream.expect("name").value
            if self.stream.current.type == "lparen":
                args, kwargs, dyn_args, dyn_kwargs = self.parse_call_args()
            else:
                args, kwargs, dyn_args, dyn_kwargs = [], [], None, None
            node = nodes.Filter(node, name, args, kwargs, dyn_args, dyn_kwargs, lineno=token.lineno)
            start_inline = False
        return node

    def parse_macro(self):
        node = nodes.Macro(lineno=next(self.stream).lineno)
        node.name = self.parse_assign_target(name_only=True).name
        self.parse_signature(node)
        node.body = self.parse_statements(("name:endmacro",), drop_needle=True)
        return node

    def parse_print(self):
        node = nodes.Output(lineno=next(self.stream).lineno)
        node.nodes = []
        while self.stream.current.type != "block_end":
            if node.nodes:
                self.stream.expect("comma")
            node.nodes.append(self.parse_expression())
        return node

    def parse_assign_target(self, with_tuple: bool = True, name_only: bool = False, extra_end_rules=None, with_namespace: bool = False):
        if name_only:
            token = self.stream.expect("name")
            target = nodes.Name(token.value, "store", lineno=token.lineno)
        else:
            if with_tuple:
                target = self.parse_tuple(simplified=True, extra_end_rules=extra_end_rules, with_namespace=with_namespace)
            else:
                target = self.parse_primary(with_namespace=with_namespace)
            target.set_ctx("store")
        if not target.can_assign():
            self.fail("can't assign to %r" % type(target).__name__.lower(), target.lineno)
        return target

    # expressions

    def parse_expression(self, with_condexpr: bool = True):
        return self.parse_condexpr() if with_condexpr else self.parse_or()

    def parse_condexpr(self):
        lineno = self.stream.current.lineno
        expr1 = self.parse_or()
        while self.stream.skip_if("name:if"):
            expr2 = self.parse_or()
            expr3 = self.parse_condexpr() if self.stream.skip_if("name:else") else None
            expr1 = nodes.CondExpr(expr2, expr1, expr3, lineno=lineno)
            lineno = self.stream.current.lineno
        return expr1

    def parse_or(self):
        lineno = self.stream.current.lineno
        left = self.parse_and()
        while self.stream.skip_if("name:or"):
            left = nodes.Or(left, self.parse_and(), lineno=lineno)
            lineno = self.stream.current.lineno
        return left

    def parse_and(self):
        lineno = self.stream.current.lineno
        left = self.parse_not()
        while self.stream.skip_if("name:and"):
            left = nodes.And(left, self.parse_not(), lineno=lineno)
            lineno = self.stream.current.lineno
        return left

    def parse_not(self):
        if self.stream.current.test("name:not"):
            lineno = next(self.stream).lineno
            return nodes.Not(self.parse_not(), lineno=lineno)
        return self.parse_compare()

    def parse_compare(self):
        lineno = self.stream.current.lineno
        expr = self.parse_math1()
        ops = []
        while True:
            token_type = self.stream.current.type
            if token_type in COMPARE_OPERATORS:
                next(self.stream)
                ops.append(nodes.Operand(token_type, self.parse_math1()))
            elif self.stream.skip_if("name:in"):
                ops.append(nodes.Operand("in", self.parse_math1()))
            elif self.stream.current.test("name:not") and self.stream.look().test("name:in"):
                self.stream.skip(2)
                ops.append(nodes.Operand("notin", self.parse_math1()))
            else:
                break
            lineno = self.stream.current.lineno
        if not ops:
            return expr
        return nodes.Compare(expr, ops, lineno=lineno)

    def parse_math1(self):
        lineno = self.stream.current.lineno
        left = self.parse_concat()
        while self.stream.current.type in ("add", "sub"):
            cls = MATH[self.stream.current.type]
            next(self.stream)
            left = cls(left, self.parse_concat(), lineno=lineno)
            lineno = self.stream.current.lineno
        return left

    def parse_concat(self):
        lineno = self.stream.current.lineno
        args = [self.parse_math2()]
        while self.stream.current.type == "tilde":
            next(self.stream)
            args.append(self.parse_math2())
        return args[0] if len(args) == 1 else nodes.Concat(args, lineno=lineno)

    def parse_math2(self):
        lineno = self.stream.current.lineno
        left = self.parse_pow()
        while self.stream.current.type in ("mul", "div", "floordiv", "mod"):
            cls = MATH[self.stream.current.type]
            next(self.stream)
            left = cls(left, self.parse_pow(), lineno=lineno)
            lineno = self.stream.current.lineno
        return left

    def parse_pow(self):
        lineno = self.stream.current.lineno
        left = self.parse_unary()
        while self.stream.current.type == "pow":
            next(self.stream)
            left = nodes.Pow(left, self.parse_unary(), lineno=lineno)
            lineno = self.stream.current.lineno
        return left

    def parse_unary(self, with_filter: bool = True):
        token_type = self.stream.current.type
        lineno = self.stream.current.lineno
        if token_type == "sub":
            next(self.stream)
            node = nodes.Neg(self.parse_unary(False), lineno=lineno)
        elif token_type == "add":
            next(self.stream)
            node = nodes.Pos(self.parse_unary(False), lineno=lineno)
        else:
            node = self.parse_primary()
        node = self.parse_postfix(node)
        if with_filter:
            node = self.parse_filter_expr(node)
        return node

    def parse_primary(self, with_namespace: bool = False):
        token = self.stream.current
        if token.type == "name":
            next(self.stream)
            if token.value in ("true", "false", "True", "False"):
                return nodes.Const(token.value in ("true", "True"), lineno=token.lineno)
            if token.value in ("none", "None"):
                return nodes.Const(None, lineno=token.lineno)
            if with_namespace and self.stream.current.type == "dot":
                next(self.stream)
                attr = self.stream.expect("name")
                return nodes.NSRef(token.value, attr.value, lineno=token.lineno)
            return nodes.Name(token.value, "load", lineno=token.lineno)
        if token.type == "string":
            next(self.stream)
            buf = [token.value]
            while self.stream.current.type == "string":         # "a" 'b' is "ab"
                buf.append(self.stream.current.value)
                next(self.stream)
            return nodes.Const("".join(buf), lineno=token.lineno)
        if token.type in ("integer", "float"):
            next(self.stream)
            return nodes.Const(token.value, lineno=token.lineno)
        if token.type == "lparen":
            next(self.stream)
            node = self.parse_tuple(explicit_parentheses=True)
            self.stream.expect("rparen")
            return node
        if token.type == "lbracket":
            return self.parse_list()
        if token.type == "lbrace":
            return self.parse_dict()
        self.fail("unexpected %r" % describe_token(token), token.lineno)

    def parse_tuple(self, simplified: bool = False, with_condexpr: bool = True, extra_end_rules=None, explicit_parentheses: bool = False, with_namespace: bool = False):
        lineno = self.stream.current.lineno
        if simplified:
            def parse():
                return self.parse_primary(with_namespace=with_namespace)
        else:
            def parse():
                return self.parse_expression(with_condexpr=with_condexpr)
        args = []
        is_tuple = False
        while True:
            if args:
                self.stream.expect("comma")
            if self.is_tuple_end(extra_end_rules):
                break
            args.append(parse())
            if self.stream.current.type == "comma":
                is_tuple = True
            else:
                break
            lineno = self.stream.current.lineno
        if not is_tuple:
            if args:
                return args[0]
            if not explicit_parentheses:                        # () is a tuple, nothing at all is not an expression
                self.fail("Expected an expression, got %r" % describe_token(self.stream.current))
        return nodes.Tuple(args, "load", lineno=lineno)

    def parse_list(self):
        token = self.stream.expect("lbracket")
        items = []
        while self.stream.current.type != "rbracket":
            if items:
                self.stream.expect("comma")
            if self.stream.current.type == "rbracket":
                break
            items.append(self.parse_expression())
        self.stream.expect("rbracket")
        return nodes.List(items, lineno=token.lineno)

    def parse_dict(self):
        token = self.stream.expect("lbrace")
        items = []
        while self.stream.current.type != "rbrace":
            if items:
                self.stream.expect("comma")
            if self.stream.current.type == "rbrace":
                break
            key = self.parse_expression()
            self.stream.expect("colon")
            value = self.parse_expression()
            items.append(nodes.Pair(key, value, lineno=key.lineno))
        self.stream.expect("rbrace")
        return nodes.Dict(items, lineno=token.lineno)

    def parse_postfix(self, node):
        while True:
            token_type = self.stream.current.type
            if token_type in ("dot", "lbracket"):
                node = self.parse_subscript(node)
            elif token_type == "lparen":
                node = self.parse_call_expr(node)
            else:
                break
        return node

    def parse_filter_expr(self, node):
        while True:
            token_type = self.stream.current.type
            if token_type == "pipe":
                node = self.parse_filter_chain(node)
            elif token_type == "name" and self.stream.current.value == "is":
                node = self.parse_test(node)
            elif token_type == "lparen":                        # a call is allowed after a filter or a test too
                node = self.parse_call_expr(node)
            else:
                break
        return node

    def parse_subscript(self, node):
        token = next(self.stream)
        if token.type == "dot":
            attr_token = self.stream.current
            next(self.stream)
            if attr_token.type == "name":
                return nodes.Getattr(node, attr_token.value, "load", lineno=token.lineno)
            if attr_token.type != "integer":
                self.fail("expected name or number", attr_token.lineno)
            return nodes.Getitem(node, nodes.Const(attr_token.value, lineno=attr_token.lineno), "load", lineno=token.lineno)
        if token.type == "lbracket":
            args = []
            while self.stream.current.type != "rbracket":
                if args:
                    self.stream.expect("comma")
                args.append(self.parse_subscribed())
            self.stream.expect("rbracket")
            arg = args[0] if len(args) == 1 else nodes.Tuple(args, "load", lineno=token.lineno)
            return nodes.Getitem(node, arg, "load", lineno=token.lineno)
        self.fail("expected subscript expression", token.lineno)

    def parse_subscribed(self):
        lineno = self.stream.current.lineno
        if self.stream.current.type == "colon":
            next(self.stream)
            args = [None]
        else:
            node = self.parse_expression()
            if self.stream.current.type != "colon":
                return node
            next(self.stream)
            args = [node]
        if self.stream.current.type == "colon":
            args.append(None)
        elif self.stream.current.type not in ("rbracket", "comma"):
            args.append(self.parse_expression())
        else:
            args.append(None)
        if self.stream.current.type == "colon":
            next(self.stream)
            if self.stream.current.type not in ("rbracket", "comma"):
                args.append(self.parse_expression())
            else:
                args.append(None)
        else:
            args.append(None)
        return nodes.Slice(*args, lineno=lineno)

    def parse_call_args(self):
        token = self.stream.expect("lparen")
        args, kwargs = [], []
        dyn_args = dyn_kwargs = None
        require_comma = False

        def ensure(ok: bool) -> None:
            if not ok:
                self.fail("invalid syntax for function call expression", token.lineno)

        while self.stream.current.type != "rparen":
            if require_comma:
                self.stream.expect("comma")
                if self.stream.current.type == "rparen":        # a trailing comma
                    break
            if self.stream.current.type == "mul":
                ensure(dyn_args is None and dyn_kwargs is None)
                next(self.stream)
                dyn_args = self.parse_expression()
            elif self.stream.current.type == "pow":
                ensure(dyn_kwargs is None)
                next(self.stream)
                dyn_kwargs = self.parse_expression()
            elif self.stream.current.type == "name" and self.stream.look().type == "assign":
                ensure(dyn_kwargs is None)
                key = self.stream.current.value
                self.stream.skip(2)
                value = self.parse_expression()
                kwargs.append(nodes.Keyword(key, value, lineno=value.lineno))
            else:
                ensure(dyn_args is None and dyn_kwargs is None and not kwargs)
                args.append(self.parse_expression())
            require_comma = True
        self.stream.expect("rparen")
        return args, kwargs, dyn_args, dyn_kwargs

    def parse_call_expr(self, node):
        token = self.stream.current
        args, kwargs, dyn_args, dyn_kwargs = self.parse_call_args()
        return nodes.Call(node, args, kwargs, dyn_args, dyn_kwargs, lineno=token.lineno)

    def parse_test(self, node):
        token = next(self.stream)
        negated = False
        if self.stream.current.test("name:not"):
            next(self.stream)
            negated = True
        name = self.stream.expect("name").value
        while self.stream.current.type == "dot":
            next(self.stream)
            name += "." + self.stream.expect("name").value
        dyn_args = dyn_kwargs = None
        kwargs = []
        if self.stream.current.type == "lparen":
            args, kwargs, dyn_args, dyn_kwargs = self.parse_call_args()
        elif self.stream.current.type in {"name", "string", "integer", "float", "lparen", "lbracket", "lbrace"} and not self.stream.current.test_any("name:else", "name:or", "name:and"):
            if self.stream.current.test("name:is"):
                self.fail("You cannot chain multiple tests with is")
            args = [self.parse_postfix(self.parse_primary())]
        else:
            args = []
        node = nodes.Test(node, name, args, kwargs, dyn_args, dyn_kwargs, lineno=token.lineno)
        if negated:
            node = nodes.Not(node, lineno=token.lineno)
        return node

    # the body of a template or of a statement

    def subparse(self, end_tokens: Optional[Tuple[str, ...]] = None):
        body = []
        data_buffer = []

        def flush_data() -> None:
            if data_buffer:
                body.append(nodes.Output(data_buffer[:], lineno=data_buffer[0].lineno))
                del data_buffer[:]

        if end_tokens is not None:
            self._end_token_stack.append(end_tokens)
        try:
            while self.stream:
                token = self.stream.current
                if token.type == "data":
                    if token.value:
                        data_buffer.append(nodes.TemplateData(token.value, lineno=token.lineno))
                    next(self.stream)
                elif token.type == "variable_begin":
                    next(self.stream)
                    data_buffer.append(self.parse_tuple(with_condexpr=True))
                    self.stream.expect("variable_end")
                elif token.type == "block_begin":
                    flush_data()
                    next(self.stream)
                    if end_tokens is not None and self.stream.current.test_any(*end_tokens):
                        return body
                    rv = self.parse_statement()
                    if isinstance(rv, list):
                        body.extend(rv)
                    else:
                        body.append(rv)
                    self.stream.expect("block_end")
                else:
                    raise AssertionError("internal parsing error")
            flush_data()
        finally:
            if end_tokens is not None:
                self._end_token_stack.pop()
        return body

    def parse(self) -> nodes.Template:
        result = nodes.Template(self.subparse(), lineno=1)
        return result
