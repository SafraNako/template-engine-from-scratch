"""The syntax tree.  Every node knows the names of its fields, so that a walker can visit the children without a class of its own."""
from __future__ import annotations

from typing import Any, Iterator, Optional


class Node:
    fields: tuple = ()

    def __init__(self, *args: Any, lineno: Optional[int] = None, **kwargs: Any) -> None:
        if args:
            if len(args) != len(self.fields):
                raise TypeError("%s takes %d arguments, %d given" % (type(self).__name__, len(self.fields), len(args)))
            for name, value in zip(self.fields, args):
                setattr(self, name, value)
        for name in self.fields[len(args):]:
            setattr(self, name, kwargs.pop(name, None))
        if kwargs:
            raise TypeError("unknown fields %s for %s" % (", ".join(kwargs), type(self).__name__))
        self.lineno = lineno

    def iter_child_nodes(self) -> Iterator["Node"]:
        for name in self.fields:
            value = getattr(self, name)
            if isinstance(value, Node):
                yield value
            elif isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, Node):
                        yield item
                    elif isinstance(item, (list, tuple)):
                        yield from (x for x in item if isinstance(x, Node))

    def find_all(self, cls) -> Iterator["Node"]:
        for child in self.iter_child_nodes():
            if isinstance(child, cls):
                yield child
            yield from child.find_all(cls)

    def __repr__(self) -> str:
        return "%s(%s)" % (type(self).__name__, ", ".join("%s=%r" % (f, getattr(self, f, None)) for f in self.fields))


class Stmt(Node):
    pass


class Expr(Node):
    def can_assign(self) -> bool:
        return False

    def set_ctx(self, ctx: str) -> "Expr":
        return self


# statements

class Template(Node):
    fields = ("body",)


class Output(Stmt):
    fields = ("nodes",)


class For(Stmt):
    fields = ("target", "iter", "body", "else_", "test", "recursive")


class If(Stmt):
    fields = ("test", "body", "elif_", "else_")


class Macro(Stmt):
    fields = ("name", "args", "defaults", "body")


class CallBlock(Stmt):
    fields = ("call", "args", "defaults", "body")


class FilterBlock(Stmt):
    fields = ("body", "filter")


class With(Stmt):
    fields = ("targets", "values", "body")


class Block(Stmt):
    fields = ("name", "body", "scoped", "required")


class Include(Stmt):
    fields = ("template", "with_context", "ignore_missing")


class Import(Stmt):
    fields = ("template", "target", "with_context")


class FromImport(Stmt):
    fields = ("template", "names", "with_context")


class Extends(Stmt):
    fields = ("template",)


class Assign(Stmt):
    fields = ("target", "node")


class AssignBlock(Stmt):
    fields = ("target", "filter", "body")


class Scope(Stmt):
    """Statements that get a scope of their own (``autoescape`` blocks)."""
    fields = ("body",)


class AutoescapeBlock(Stmt):
    fields = ("option", "body")


# expressions

class Name(Expr):
    fields = ("name", "ctx")

    def can_assign(self) -> bool:
        return self.name not in ("true", "false", "none", "True", "False", "None")

    def set_ctx(self, ctx: str) -> "Expr":
        self.ctx = ctx
        return self


class NSRef(Expr):
    """``ns.attr`` as the target of ``set``."""
    fields = ("name", "attr")

    def can_assign(self) -> bool:
        return True


class Const(Expr):
    fields = ("value",)


class TemplateData(Expr):
    fields = ("data",)


class Tuple(Expr):
    fields = ("items", "ctx")

    def can_assign(self) -> bool:
        return all(item.can_assign() for item in self.items)

    def set_ctx(self, ctx: str) -> "Expr":
        self.ctx = ctx
        for item in self.items:
            item.set_ctx(ctx)
        return self


class List(Expr):
    fields = ("items",)


class Dict(Expr):
    fields = ("items",)


class Pair(Expr):
    fields = ("key", "value")


class Keyword(Expr):
    fields = ("key", "value")


class CondExpr(Expr):
    fields = ("test", "expr1", "expr2")


class Filter(Expr):
    fields = ("node", "name", "args", "kwargs", "dyn_args", "dyn_kwargs")


class Test(Expr):
    fields = ("node", "name", "args", "kwargs", "dyn_args", "dyn_kwargs")


class Call(Expr):
    fields = ("node", "args", "kwargs", "dyn_args", "dyn_kwargs")


class Getitem(Expr):
    fields = ("node", "arg", "ctx")


class Getattr(Expr):
    fields = ("node", "attr", "ctx")


class Slice(Expr):
    fields = ("start", "stop", "step")


class Concat(Expr):
    fields = ("nodes",)


class Compare(Expr):
    fields = ("expr", "ops")


class Operand(Node):
    fields = ("op", "expr")


class BinExpr(Expr):
    fields = ("left", "right")


class Add(BinExpr):
    pass


class Sub(BinExpr):
    pass


class Mul(BinExpr):
    pass


class Div(BinExpr):
    pass


class FloorDiv(BinExpr):
    pass


class Pow(BinExpr):
    pass


class Mod(BinExpr):
    pass


class And(BinExpr):
    pass


class Or(BinExpr):
    pass


class UnaryExpr(Expr):
    fields = ("node",)


class Not(UnaryExpr):
    pass


class Neg(UnaryExpr):
    pass


class Pos(UnaryExpr):
    pass
