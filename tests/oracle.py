"""Runs the same template through this engine and through Jinja2 (the oracle) and says whether they agree.

Nothing here is mocked: both engines parse, compile and render the template for real.  A result is either ``("ok", text)`` or ``("err", exception class
name, message, line number)``; two results agree when they are equal (for the exceptions of the engines the message and the line are compared, for
Python's own exceptions the class and the message).
"""
import re

import jinja2
import markupsafe

import kendi_sablon as mine

LIBS = {"mine": mine, "jinja": jinja2}


class Obj:
    """A plain object for the tests of attribute lookup."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def method(self, x=1):
        return "method:%s" % x

    @property
    def prop(self):
        return "prop"

    def __repr__(self):
        return "Obj(%s)" % ", ".join("%s=%r" % kv for kv in sorted(self.__dict__.items()))


class Raising:
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        raise KeyError(name)


def double(x):
    return x * 2


def kw_function(a, b=2, *rest, **kw):
    return "a=%r b=%r rest=%r kw=%r" % (a, b, rest, sorted(kw.items()))


def make_context(lib):
    """The variables that the templates of the tests (and of the fuzzers) can use; the same values for both engines."""
    M = markupsafe.Markup if lib is jinja2 else lib.Markup
    pass_context = lib.pass_context
    pass_eval_context = lib.pass_eval_context
    pass_environment = lib.pass_environment

    @pass_context
    def ctx_function(context, x=0):
        return "ctx:%s:%s" % (x, sorted(k for k in context.keys() if len(k) == 1)[:3])

    @pass_environment
    def env_function(environment, x=0):
        return "env:%s:%s" % (x, type(environment).__name__)

    @pass_eval_context
    def eval_function(eval_ctx, x=0):
        return "eval:%s:%s" % (x, eval_ctx.autoescape)

    return {
        "a": 3, "b": -2, "c": 0, "big": 10 ** 20,
        "x": 2.5, "y": -0.75, "z": 1e-7,
        "s": "hello world", "t": "Foo Bar", "u": "<b>é&\"'</b>", "empty": "", "digits": "12345", "sp": "  padded  ",
        "n": None, "T": True, "F": False,
        "l": [3, 1, 2], "l2": ["b", "A", "c"], "e": [], "tup": (1, 2, 3), "nested": [[1, 2], [3, 4], [5, 6]],
        "d": {"k": 1, "j": 2, "items": "shadow"}, "d2": {"b": 2, "a": 1, "C": 3},
        "users": [{"name": "ann", "age": 30, "tags": ["x", "y"]}, {"name": "Bob", "age": 25, "tags": []}, {"name": "cy", "age": 30, "tags": ["z"]}],
        "o": Obj(name="obj", n=5, items=[1, 2]), "r": Raising(),
        "md": M("<i>safe</i>"), "words": ["apple", "Banana", "cherry", "apple"],
        "html": "<p>Hello, <b>World</b> &amp; <!-- c --> bye</p>",
        "tree": [{"name": "r", "children": [{"name": "c1", "children": []}, {"name": "c2", "children": [{"name": "g", "children": []}]}]}],
        "f": double, "kw": kw_function, "cf": ctx_function, "ef": env_function, "xf": eval_function,
        "gen": (i for i in range(3)),
    }


def make_env(lib, options, templates=None):
    opts = dict(options)
    undefined_name = opts.pop("undefined", "Undefined")
    opts["undefined"] = getattr(lib, undefined_name)
    if templates is not None:
        opts["loader"] = lib.DictLoader(templates)
    return lib.Environment(**opts)


_ADDRESS = re.compile(r"0[xX][0-9a-fA-F]+")


def normalize(text):
    """Object addresses and the name of the package are not part of what has to agree."""
    return _ADDRESS.sub("0xADDR", text.replace("kendi_sablon.markup", "markupsafe").replace("kendi_sablon", "jinja2").replace("sync_do_", "do_").replace("SYNC_DO_", "DO_"))


def describe(exc):
    name = type(exc).__name__
    if isinstance(exc, (jinja2.TemplateError, mine.TemplateError)):
        message = str(exc.message) if name not in ("TemplateNotFound", "TemplatesNotFound") else str(exc)
        lineno = getattr(exc, "lineno", None)
        return ("err", name, normalize(message), lineno)
    return ("err", name, normalize(str(exc)), None)


def render(lib, source, context=None, options=None, templates=None, name=None):
    """The result of rendering ``source`` with the engine ``lib`` (``mine`` or ``jinja2``)."""
    try:
        env = make_env(lib, options or {}, templates)
        if name is not None:
            template = env.get_template(name)
        else:
            template = env.from_string(source)
        ctx = make_context(lib) if context is None else context(lib)
        return ("ok", normalize(template.render(ctx)))
    except Exception as exc:                        # noqa: BLE001 - every exception is a result to compare
        return describe(exc)


def compare(source, context=None, options=None, templates=None, name=None):
    """``(mine result, jinja result)``."""
    return (render(mine, source, context, options, templates, name), render(jinja2, source, context, options, templates, name))


def agree(a, b):
    # Jinja lets Python's compiler find a repeated keyword argument of a call, and a SyntaxError comes out; this engine says it in its own words
    if b[0] == "err" and b[1] == "SyntaxError" and b[2].startswith("keyword argument repeated"):
        return a[0] == "err" and a[1] == "TemplateSyntaxError" and a[2].startswith("keyword argument repeated")
    # a filter that does not exist, called with keyword arguments: Jinja's stand-in for it takes none and Python's message names a generated function
    if b[0] == "err" and b[1] == "TypeError" and "root.<locals>.t_" in b[2] and "unexpected keyword argument" in b[2]:
        return a[0] == "err" and a[1] == "TemplateRuntimeError" and a[2].endswith(" found.")
    # Jinja evaluates the constants of a template while it compiles it, and throws away the part of an ``or`` / ``and`` / inline ``if`` that a constant
    # decides, so an unknown filter or test in that part is never noticed; this engine compiles every part
    if a[0] == "err" and a[1] == "TemplateAssertionError" and a[2].startswith(("No filter named", "No test named")) and not (b[0] == "err" and b[1:3] == a[1:3]):
        return True
    # ``f(**x)`` with something that is not a mapping: Python's message names the function that makes the call, which is a different one in each engine
    if a[0] == b[0] == "err" and a[1] == b[1] == "TypeError" and "argument after *" in a[2] and "argument after *" in b[2]:
        return True
    # a template that calls itself without end runs out of stack in both; where exactly, and so the words of the message, depend on the Python version
    if a[0] == b[0] == "err" and a[1] == b[1] == "RecursionError":
        return True
    if a[0] != b[0]:
        return False
    if a[0] == "ok":
        if "enerator" in a[1] or "ENERATOR" in a[1]:           # the name of a generator function is in its repr, and Jinja's has "sync_" in front
            return a[1].lower().replace("sync_", "") == b[1].lower().replace("sync_", "")
        return a[1] == b[1]
    return a == b


def explain(source, a, b, options=None):
    return "template: %r\noptions:  %r\nmine:     %r\njinja2:   %r" % (source, options, a, b)


def check(source, context=None, options=None, templates=None, name=None):
    a, b = compare(source, context, options, templates, name)
    assert agree(a, b), explain(source, a, b, options)
    return a


def expect(source, expected, context=None, options=None, templates=None, name=None):
    """The text of the template is ``expected`` - for this engine and for Jinja2, so that the expected text is not just what this engine does."""
    a, b = compare(source, context, options, templates, name)
    assert a == ("ok", expected), "mine gave %r, wanted %r\ntemplate: %r" % (a, expected, source)
    assert b == ("ok", expected), "the expectation is wrong, Jinja2 gave %r, wanted %r\ntemplate: %r" % (b, expected, source)


def expect_error(source, error, message=None, lineno=None, context=None, options=None, templates=None, name=None):
    """Both engines fail with the exception class ``error`` (a name), with the same message and line number (``message`` / ``lineno`` if given)."""
    a, b = compare(source, context, options, templates, name)
    assert agree(a, b), explain(source, a, b, options)
    assert a[0] == "err" and a[1] == error, "wanted %s, got %r\ntemplate: %r" % (error, a, source)
    if message is not None:
        assert a[2] == message, "wanted message %r, got %r" % (message, a[2])
    if lineno is not None:
        assert a[3] == lineno, "wanted line %r, got %r" % (lineno, a[3])
