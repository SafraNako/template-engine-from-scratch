"""Turns the source of a template into tokens.

The source is text with tags in it: ``{{ ... }}`` prints, ``{% ... %}`` is a statement, ``{# ... #}`` is a comment.  Everything between the tags is ``data``.
Inside a tag the text is cut into names, numbers, strings and operators.

The tokens come out of a generator: a character that cannot be lexed is only reported when the parser asks for the token, so a syntax error in the
first line is found before a lexing error in the last one.
"""
from __future__ import annotations

import re
from bisect import bisect_left
from typing import Any, Iterator, List, NamedTuple, Optional

from .errors import TemplateSyntaxError

whitespace_re = re.compile(r"\s+")
newline_re = re.compile(r"(\r\n|\r|\n)")
name_re = re.compile(r"[\w·]+")
string_re = re.compile(r"""('([^'\\]*(?:\\.[^'\\]*)*)'|"([^"\\]*(?:\\.[^"\\]*)*)")""", re.S)
integer_re = re.compile(
    r"""
    (
        0b(_?[0-1])+        # binary
    |
        0o(_?[0-7])+        # octal
    |
        0x(_?[\da-f])+      # hex
    |
        [1-9](_?\d)*        # decimal
    |
        0(_?0)*             # zero
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
float_re = re.compile(
    r"""
    (?<!\.)                 # not the part after a dot (x.1.5 is x.1 then .5)
    (\d+_)*\d+              # digits, maybe separated by _
    (
        (\.(\d+_)*\d+)?     # an optional fraction
        e[+\-]?(\d+_)*\d+   # and an exponent
    |
        \.(\d+_)*\d+        # or a fraction (and no exponent)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

OPERATORS = {
    "+": "add", "-": "sub", "/": "div", "//": "floordiv", "*": "mul", "%": "mod", "**": "pow", "~": "tilde",
    "[": "lbracket", "]": "rbracket", "(": "lparen", ")": "rparen", "{": "lbrace", "}": "rbrace",
    "==": "eq", "!=": "ne", ">": "gt", ">=": "gteq", "<": "lt", "<=": "lteq", "=": "assign",
    ".": "dot", ":": "colon", ",": "comma", ";": "semicolon", "|": "pipe",
}
REVERSE_OPERATORS = {v: k for k, v in OPERATORS.items()}
operator_re = re.compile("(%s)" % "|".join(re.escape(x) for x in sorted(OPERATORS, key=len, reverse=True)))

DESCRIPTIONS = {
    "block_begin": "begin of statement block",
    "block_end": "end of statement block",
    "variable_begin": "begin of print statement",
    "variable_end": "end of print statement",
    "data": "template data / text",
    "eof": "end of template",
}


class Token(NamedTuple):
    lineno: int
    type: str
    value: Any

    def test(self, expr: str) -> bool:
        """``expr`` is a token type, or ``type:value`` (for example ``name:endif``)."""
        if self.type == expr:
            return True
        if ":" in expr:
            return expr.split(":", 1) == [self.type, self.value]
        return False

    def test_any(self, *exprs: str) -> bool:
        return any(self.test(e) for e in exprs)


def describe_type(token_type: str) -> str:
    return REVERSE_OPERATORS.get(token_type) or DESCRIPTIONS.get(token_type, token_type)


def describe_token(token: Token) -> str:
    return token.value if token.type == "name" else describe_type(token.type)


def describe_token_expr(expr: str) -> str:
    if ":" in expr:
        kind, value = expr.split(":", 1)
        if kind == "name":
            return value
    else:
        kind = expr
    return describe_type(kind)


class TokenStream:
    """The parser's view of the tokens: ``current`` is the token that is looked at, ``next(stream)`` moves on and returns the one it left."""

    def __init__(self, tokens: Iterator[Token], name: Optional[str], filename: Optional[str]) -> None:
        self._iter = iter(tokens)
        self._pushed: List[Token] = []
        self.name = name
        self.filename = filename
        self.current = Token(1, "initial", "")
        next(self)

    def __bool__(self) -> bool:
        return bool(self._pushed) or self.current.type != "eof"

    def __next__(self) -> Token:
        rv = self.current
        if self._pushed:
            self.current = self._pushed.pop(0)
        elif self.current.type != "eof":
            try:
                self.current = next(self._iter)
            except StopIteration:
                self.close()
        return rv

    def close(self) -> None:
        self.current = Token(self.current.lineno, "eof", "")
        self._iter = iter(())

    def look(self) -> Token:
        old = next(self)
        result = self.current
        self._pushed.append(result)
        self.current = old
        return result

    def skip(self, n: int = 1) -> None:
        for _ in range(n):
            next(self)

    def next_if(self, expr: str) -> Optional[Token]:
        if self.current.test(expr):
            return next(self)
        return None

    def skip_if(self, expr: str) -> bool:
        return self.next_if(expr) is not None

    def expect(self, expr: str) -> Token:
        if not self.current.test(expr):
            expr = describe_token_expr(expr)
            if self.current.type == "eof":
                raise TemplateSyntaxError("unexpected end of template, expected %r." % expr, self.current.lineno, self.name, self.filename)
            raise TemplateSyntaxError("expected token %r, got %r" % (expr, describe_token(self.current)), self.current.lineno, self.name, self.filename)
        return next(self)


class Lexer:
    """Cuts a source into tokens; the delimiters and the whitespace options come from the environment."""

    def __init__(self, environment) -> None:
        e = re.escape
        self.environment = environment
        self.block_start = e(environment.block_start_string)
        block_end = e(environment.block_end_string)
        self.variable_start = e(environment.variable_start_string)
        variable_end = e(environment.variable_end_string)
        self.comment_start = e(environment.comment_start_string)
        comment_end = e(environment.comment_end_string)
        self.lstrip_blocks = environment.lstrip_blocks
        self.newline_sequence = environment.newline_sequence
        self.keep_trailing_newline = environment.keep_trailing_newline
        suffix = "\\n?" if environment.trim_blocks else ""
        flags = re.M | re.S

        # the delimiters that are longer are tried first; for the same length: variable, comment, block
        starts = sorted([(len(environment.comment_start_string), "comment_begin", self.comment_start),
                         (len(environment.block_start_string), "block_begin", self.block_start),
                         (len(environment.variable_start_string), "variable_begin", self.variable_start)], reverse=True)
        raw_begin = r"(?P<raw_begin>%s(\-|\+|)\s*raw\s*(?:\-%s\s*|%s))" % (self.block_start, block_end, block_end)
        self.root_re = re.compile("|".join([raw_begin] + [r"(?P<%s>%s(\-|\+|))" % (n, r) for _, n, r in starts]), flags)
        self.comment_end_re = re.compile(r"(.*?)((?:\+%s|\-%s\s*|%s%s))" % (comment_end, comment_end, comment_end, suffix), flags)
        self.raw_end_re = re.compile(r"(.*?)((?:%s(\-|\+|))\s*endraw\s*(?:\+%s|\-%s\s*|%s%s))" % (self.block_start, block_end, block_end, block_end, suffix), flags)
        self.block_end_re = re.compile(r"(?:\+%s|\-%s\s*|%s%s)" % (block_end, block_end, block_end, suffix), flags)
        self.variable_end_re = re.compile(r"\-%s\s*|%s" % (variable_end, variable_end), flags)

    def normalize_newlines(self, value: str) -> str:
        return newline_re.sub(self.newline_sequence, value)

    def tokenize(self, source: str, name: Optional[str] = None, filename: Optional[str] = None) -> TokenStream:
        return TokenStream(self._tokens(source, name, filename), name, filename)

    def _tokens(self, source: str, name: Optional[str], filename: Optional[str]) -> Iterator[Token]:
        lines = newline_re.split(source)[::2]
        if not self.keep_trailing_newline and lines[-1] == "":
            del lines[-1]
        source = "\n".join(lines)
        end = len(source)
        newlines = [i for i, c in enumerate(source) if c == "\n"]

        def line_at(pos: int) -> int:
            return 1 + bisect_left(newlines, pos)

        def fail(message: str, pos: int):
            raise TemplateSyntaxError(message, line_at(pos), name, filename)

        pos = 0
        line_starting = True            # does the position follow a newline (or start the source)?
        while pos < end:
            m = self.root_re.search(source, pos)
            if m is None:
                yield Token(line_at(pos), "data", self.normalize_newlines(source[pos:]))
                return
            text = source[pos:m.start()]
            groups = m.groupdict()
            kind = next(k for k in ("raw_begin", "comment_begin", "variable_begin", "block_begin") if groups.get(k) is not None)
            opener = {"raw_begin": self.environment.block_start_string, "block_begin": self.environment.block_start_string,
                      "comment_begin": self.environment.comment_start_string, "variable_begin": self.environment.variable_start_string}[kind]
            sign = m.group(kind)[len(opener):][:1]
            text = self._strip(text, sign if sign in ("-", "+") else "", kind != "variable_begin", line_starting)
            if text:
                yield Token(line_at(pos), "data", self.normalize_newlines(text))
            tag_start = m.start()
            line_starting = m.group()[-1:] == "\n"
            pos = m.end()

            if kind == "raw_begin":
                raw = self.raw_end_re.match(source, pos)
                if raw is None:
                    if pos >= end:                  # the source ends right after the tag: nothing is wrong yet, the parser finds out
                        return
                    fail("Missing end of raw directive", pos)
                text = self._strip(raw.group(1), raw.group(3), True, line_starting)
                if text:
                    yield Token(line_at(pos), "data", self.normalize_newlines(text))
                line_starting = raw.group()[-1:] == "\n"
                pos = raw.end()
            elif kind == "comment_begin":
                comment = self.comment_end_re.match(source, pos)
                if comment is None:
                    if pos >= end:
                        return
                    fail("Missing end of comment tag", pos)
                line_starting = comment.group()[-1:] == "\n"
                pos = comment.end()
            else:
                begin_type = kind
                end_type = "variable_end" if kind == "variable_begin" else "block_end"
                end_re = self.variable_end_re if kind == "variable_begin" else self.block_end_re
                yield Token(line_at(tag_start), begin_type, m.group(kind))
                pos, line_starting = yield from self._tag(source, pos, end_re, end_type, line_at, fail, name, filename)
                if pos is None:
                    return

    def _strip(self, text: str, sign: str, is_block: bool, line_starting: bool) -> str:
        """Applies ``-`` / ``+`` and the lstrip_blocks option to the data in front of a tag."""
        if sign == "-":
            return text.rstrip()
        if sign != "+" and self.lstrip_blocks and is_block:
            start = text.rfind("\n") + 1
            if (start > 0 or line_starting) and whitespace_re.fullmatch(text, start):
                return text[:start]
        return text

    def _tag(self, source, pos, end_re, end_type, line_at, fail, name, filename):
        """The tokens inside one tag.  Returns the position after the tag (None at the end of the source) and whether that follows a newline."""
        end = len(source)
        balancing: List[str] = []
        while pos < end:
            if not balancing:
                m = end_re.match(source, pos)
                if m:
                    yield Token(line_at(pos), end_type, m.group())
                    return m.end(), m.group()[-1:] == "\n"
            m = whitespace_re.match(source, pos)
            if m:
                pos = m.end()
                continue
            lineno = line_at(pos)
            m = float_re.match(source, pos)
            if m:
                yield Token(lineno, "float", float(m.group().replace("_", "")))
                pos = m.end()
                continue
            m = integer_re.match(source, pos)
            if m:
                yield Token(lineno, "integer", int(m.group().replace("_", ""), 0))
                pos = m.end()
                continue
            m = name_re.match(source, pos)
            if m:
                value = m.group()
                if not value.isidentifier():
                    raise TemplateSyntaxError("Invalid character in identifier", lineno, name, filename)
                yield Token(lineno, "name", value)
                pos = m.end()
                continue
            m = string_re.match(source, pos)
            if m:
                raw = self.normalize_newlines(m.group()[1:-1])
                try:
                    value = raw.encode("ascii", "backslashreplace").decode("unicode-escape")
                except Exception as exc:
                    raise TemplateSyntaxError(str(exc).split(":")[-1].strip(), lineno, name, filename) from exc
                yield Token(lineno, "string", value)
                pos = m.end()
                continue
            m = operator_re.match(source, pos)
            if m:
                op = m.group()
                if op in "{([":
                    balancing.append({"{": "}", "(": ")", "[": "]"}[op])
                elif op in "})]":
                    if not balancing:
                        raise TemplateSyntaxError("unexpected '%s'" % op, lineno, name, filename)
                    expected = balancing.pop()
                    if expected != op:
                        raise TemplateSyntaxError("unexpected '%s', expected '%s'" % (op, expected), lineno, name, filename)
                yield Token(lineno, OPERATORS[op], op)
                pos = m.end()
                continue
            raise TemplateSyntaxError("unexpected char %r at %d" % (source[pos], pos), lineno, name, filename)
        return None, False
