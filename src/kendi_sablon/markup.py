"""``Markup``: a string that is already safe to put into HTML, and ``escape``, which makes one out of any text."""
from __future__ import annotations

import string
from html import unescape as _unescape
from typing import Any

def _escape_text(text: str) -> str:
    # five ``replace`` calls are faster than ``translate`` or a regular expression (they only scan the text when nothing is to be replaced)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&#39;").replace('"', "&#34;")


def escape_to_str(value: Any) -> str:
    """What ``escape`` gives, as a plain ``str`` (for text that is going to be joined into the output, where the type does not matter)."""
    if value.__class__ is str:
        return _escape_text(value)
    if hasattr(value, "__html__"):
        return str(value.__html__())
    return _escape_text(str(value))


def escape(value: Any) -> "Markup":
    """Escapes ``& < > ' "``.  Something with an ``__html__`` method is trusted to be safe already."""
    if type(value) is str:
        return Markup(_escape_text(value))
    if hasattr(value, "__html__"):
        return Markup(value.__html__())
    return Markup(_escape_text(str(value)))


def escape_silent(value: Any) -> "Markup":
    return Markup() if value is None else escape(value)


def soft_str(value: Any) -> str:
    """``str(value)``, except that a ``Markup`` stays a ``Markup``."""
    return value if isinstance(value, str) else str(value)


class Markup(str):
    """Text that is not escaped again.  Adding plain text to it, or formatting plain text into it, escapes that text."""

    __slots__ = ()

    def __new__(cls, base: Any = "", encoding: Any = None, errors: str = "strict"):
        if hasattr(base, "__html__"):
            base = base.__html__()
        if encoding is None:
            return super().__new__(cls, base)
        return super().__new__(cls, base, encoding, errors)

    def __html__(self) -> "Markup":
        return self

    def __add__(self, other):
        if isinstance(other, str) or hasattr(other, "__html__"):
            return self.__class__(super().__add__(self.escape(other)))
        return NotImplemented

    def __radd__(self, other):
        if isinstance(other, str) or hasattr(other, "__html__"):
            return self.escape(other).__add__(self)
        return NotImplemented

    def __mul__(self, count):
        return self.__class__(super().__mul__(count))

    __rmul__ = __mul__

    def __mod__(self, arg):
        if isinstance(arg, tuple):
            arg = tuple(_EscapeHelper(x, self.escape) for x in arg)
        elif hasattr(type(arg), "__getitem__") and not isinstance(arg, str):
            arg = _EscapeHelper(arg, self.escape)
        else:
            arg = (_EscapeHelper(arg, self.escape),)
        return self.__class__(super().__mod__(arg))

    def __repr__(self) -> str:
        return "%s(%s)" % (self.__class__.__name__, super().__repr__())

    def join(self, iterable):
        return self.__class__(super().join(map(self.escape, iterable)))

    def split(self, sep=None, maxsplit=-1):
        return [self.__class__(v) for v in super().split(sep, maxsplit)]

    def rsplit(self, sep=None, maxsplit=-1):
        return [self.__class__(v) for v in super().rsplit(sep, maxsplit)]

    def splitlines(self, keepends=False):
        return [self.__class__(v) for v in super().splitlines(keepends)]

    def unescape(self) -> str:
        return _unescape(str(self))

    def striptags(self) -> str:
        """Unescapes the text, drops the tags and comments and makes every run of whitespace a single space."""
        value = str(self)
        parts = []
        pos = 0
        while (start := value.find("<", pos)) != -1:
            if value.startswith("<!--", start):
                end = value.find("-->", start + 4)
                if end == -1:
                    break
                end += 3
            else:
                end = value.find(">", start)
                if end == -1:
                    break
                end += 1
            parts.append(value[pos:start])
            pos = end
        if pos > 0:
            parts.append(value[pos:])
            value = "".join(parts)
        value = " ".join(value.split())
        return self.__class__(value).unescape()

    @classmethod
    def escape(cls, value: Any) -> "Markup":
        rv = escape(value)
        return rv if rv.__class__ is cls else cls(rv)

    def __getitem__(self, key):
        return self.__class__(super().__getitem__(key))

    def replace(self, old, new, count=-1):
        return self.__class__(super().replace(old, self.escape(new), count))

    def ljust(self, width, fillchar=" "):
        return self.__class__(super().ljust(width, self.escape(fillchar)))

    def rjust(self, width, fillchar=" "):
        return self.__class__(super().rjust(width, self.escape(fillchar)))

    def center(self, width, fillchar=" "):
        return self.__class__(super().center(width, self.escape(fillchar)))

    def partition(self, sep):
        left, sep, right = super().partition(sep)
        cls = self.__class__
        return cls(left), cls(sep), cls(right)

    def rpartition(self, sep):
        left, sep, right = super().rpartition(sep)
        cls = self.__class__
        return cls(left), cls(sep), cls(right)

    def format(self, *args, **kwargs):
        return self.__class__(_EscapeFormatter(self.escape).vformat(self, args, kwargs))

    def format_map(self, mapping):
        return self.__class__(_EscapeFormatter(self.escape).vformat(self, (), mapping))

    def __html_format__(self, format_spec):
        if format_spec:
            raise ValueError("Unsupported format specification for Markup.")
        return self


def _same_type_methods(cls):
    """The methods of ``str`` that give a ``Markup`` when they are called on one (written out, so that a call with the wrong arguments says the same as
    markupsafe: a method that takes ``*args`` would not)."""
    def capitalize(self):
        return self.__class__(str.capitalize(self))

    def title(self):
        return self.__class__(str.title(self))

    def lower(self):
        return self.__class__(str.lower(self))

    def upper(self):
        return self.__class__(str.upper(self))

    def lstrip(self, chars=None):
        return self.__class__(str.lstrip(self, chars))

    def rstrip(self, chars=None):
        return self.__class__(str.rstrip(self, chars))

    def strip(self, chars=None):
        return self.__class__(str.strip(self, chars))

    def translate(self, table):
        return self.__class__(str.translate(self, table))

    def expandtabs(self, tabsize=8):
        return self.__class__(str.expandtabs(self, tabsize))

    def swapcase(self):
        return self.__class__(str.swapcase(self))

    def zfill(self, width):
        return self.__class__(str.zfill(self, width))

    def casefold(self):
        return self.__class__(str.casefold(self))

    def removeprefix(self, prefix):
        return self.__class__(str.removeprefix(self, prefix))

    def removesuffix(self, suffix):
        return self.__class__(str.removesuffix(self, suffix))

    for function in (capitalize, title, lower, upper, lstrip, rstrip, strip, translate, expandtabs, swapcase, zfill, casefold, removeprefix, removesuffix):
        function.__qualname__ = "Markup." + function.__name__
        setattr(cls, function.__name__, function)


_same_type_methods(Markup)


class _EscapeFormatter(string.Formatter):
    def __init__(self, escape_function) -> None:
        self.escape = escape_function
        super().__init__()

    def format_field(self, value, format_spec):
        if hasattr(value, "__html_format__"):
            rv = value.__html_format__(format_spec)
        elif hasattr(value, "__html__"):
            if format_spec:
                raise ValueError("Format specifier %s given, but %s does not define __html_format__. A class that defines __html__ must define "
                                 "__html_format__ to work with format specifiers." % (format_spec, type(value)))
            rv = value.__html__()
        else:
            rv = super().format_field(value, str(format_spec))
        return str(self.escape(rv))


class _EscapeHelper:
    """What ``Markup % arguments`` gives to ``%`` so that every argument is escaped when it is turned into text."""

    __slots__ = ("obj", "escape")

    def __init__(self, obj, escape_function) -> None:
        self.obj = obj
        self.escape = escape_function

    def __getitem__(self, key):
        return self.__class__(self.obj[key], self.escape)

    def __str__(self) -> str:
        return str(self.escape(self.obj))

    def __repr__(self) -> str:
        return str(self.escape(repr(self.obj)))

    def __int__(self) -> int:
        return int(self.obj)

    def __float__(self) -> float:
        return float(self.obj)
