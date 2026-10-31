"""Random templates for the differential tests (a seeded random generator, so that every failure can be reproduced from its seed).

Three generators: ``Expr`` makes expressions out of the variables of ``oracle.make_context``, ``Whitespace`` makes sources that are mostly text and tags with
all kinds of ``-`` / ``+`` marks and line breaks, and ``Doc`` makes whole templates with statements, nested and with output in between.
"""
import random

NAMES_INT = ["a", "b", "c"]
NAMES_FLOAT = ["x", "y", "z"]
NAMES_STR = ["s", "t", "u", "empty", "digits", "sp", "html"]
NAMES_SEQ = ["l", "l2", "e", "tup", "nested", "words", "users", "gen"]
NAMES_MAP = ["d", "d2"]
NAMES_OTHER = ["n", "T", "F", "o", "r", "md", "tree", "f", "kw", "cf", "ef", "xf"]
ALL_NAMES = NAMES_INT + NAMES_FLOAT + NAMES_STR + NAMES_SEQ + NAMES_MAP + NAMES_OTHER
UNDEFINED_NAMES = ["q1", "q2"]

STRINGS = ['"abc"', "'a b'", '"<&>"', '""', '"x,y"', '"Hello World"', '"é"', '"a\\nb"', '"3"', '"3.5"', '"  "', '"o"', '"a\'b"', '"-"', '"k"', '"name"', '"age"']
NUMBERS = ["0", "1", "2", "3", "10", "100", "0.5", "2.5", "1e3", "0x10", "1_000", "7"]
ATTRS = ["name", "age", "tags", "k", "items", "n", "prop", "method", "upper", "nosuch", "real", "index", "index0", "revindex", "revindex0", "first", "last",
         "length", "previtem", "nextitem", "depth", "depth0"]


class Expr:
    """Random expressions.  ``depth`` bounds the nesting; the same seed gives the same expression."""

    def __init__(self, rng: random.Random, names=None):
        self.rng = rng
        self.names = names or ALL_NAMES

    def pick(self, seq):
        return self.rng.choice(seq)

    def name(self):
        if self.rng.random() < 0.08:
            return self.pick(UNDEFINED_NAMES)
        return self.pick(self.names)

    def literal(self):
        r = self.rng.random()
        if r < 0.35:
            return self.pick(NUMBERS)
        if r < 0.65:
            return self.pick(STRINGS)
        if r < 0.75:
            return self.pick(["true", "false", "none", "True", "False", "None"])
        if r < 0.85:
            return "[%s]" % ", ".join(self.atom() for _ in range(self.rng.randint(0, 3)))
        if r < 0.9:
            return "(%s)" % ", ".join(self.atom() for _ in range(self.rng.randint(0, 3)))
        if r < 0.95:
            return "{%s}" % ", ".join("%s: %s" % (self.pick(STRINGS), self.atom()) for _ in range(self.rng.randint(0, 3)))
        return "range(%d)" % self.rng.randint(0, 4)

    def atom(self):
        return self.name() if self.rng.random() < 0.55 else self.literal()

    def filter_call(self, base, depth):
        r = self.rng
        sub = lambda: self.expr(depth - 1)      # noqa: E731
        simple = ["abs", "capitalize", "count", "e", "escape", "first", "float", "forceescape", "int", "last", "length", "list", "lower", "items", "pprint",
                  "reverse", "round", "safe", "string", "striptags", "sum", "title", "trim", "unique", "upper", "urlencode", "wordcount", "min", "max",
                  "sort", "tojson", "filesizeformat", "wordwrap", "center", "truncate", "indent", "batch", "slice", "dictsort", "xmlattr", "groupby",
                  "map", "select", "reject", "selectattr", "rejectattr", "join", "default", "replace", "format", "attr", "d"]
        name = self.pick(simple)
        args = {
            "batch": lambda: [str(r.randint(1, 3))] + ([sub()] if r.random() < 0.3 else []),
            "center": lambda: [str(r.randint(0, 25))],
            "default": lambda: [sub()] + (["true"] if r.random() < 0.4 else []),
            "d": lambda: [sub()] + (["true"] if r.random() < 0.4 else []),
            "dictsort": lambda: ([self.pick(["true", "false"])] if r.random() < 0.5 else []) + (['by="value"'] if r.random() < 0.3 else []) + (["reverse=true"] if r.random() < 0.3 else []),
            "filesizeformat": lambda: [self.pick(["true", "false"])] if r.random() < 0.5 else [],
            "float": lambda: [sub()] if r.random() < 0.3 else [],
            "int": lambda: ([sub()] if r.random() < 0.4 else []) + ([str(r.choice([2, 8, 16]))] if r.random() < 0.2 else []),
            "format": lambda: [sub() for _ in range(r.randint(0, 2))],
            "groupby": lambda: [self.pick(['"age"', '"name"', '"tags.0"', "0", "1"])] + (["default=1"] if r.random() < 0.2 else []),
            "indent": lambda: [self.pick(["2", "'>>'", "0", "4"])] + ([self.pick(["true", "false"])] if r.random() < 0.5 else []) + ([self.pick(["true", "false"])] if r.random() < 0.3 else []),
            "join": lambda: ([self.pick(STRINGS)] if r.random() < 0.8 else []) + ([self.pick(['"name"', '"age"', "0"])] if r.random() < 0.25 else []),
            "map": lambda: [self.pick(['"upper"', '"string"', '"length"', '"int"', '"abs"', '"nosuch"', '"default"', '"join"'])] + ([sub()] if r.random() < 0.2 else []) if r.random() < 0.7 else ["attribute=%s" % self.pick(['"name"', '"age"', '"tags"', "0"])] + (["default=%s" % sub()] if r.random() < 0.3 else []),
            "min": lambda: ([self.pick(["true", "false"])] if r.random() < 0.3 else []) + (['attribute="age"'] if r.random() < 0.2 else []),
            "max": lambda: ([self.pick(["true", "false"])] if r.random() < 0.3 else []) + (['attribute="age"'] if r.random() < 0.2 else []),
            "reject": lambda: ([self.pick(['"odd"', '"even"', '"none"', '"string"', '"divisibleby"', '"lt"', '"in"', '"eq"'])] + ([sub()] if r.random() < 0.5 else [])) if r.random() < 0.8 else [],
            "select": lambda: ([self.pick(['"odd"', '"even"', '"none"', '"string"', '"divisibleby"', '"lt"', '"in"', '"eq"'])] + ([sub()] if r.random() < 0.5 else [])) if r.random() < 0.8 else [],
            "selectattr": lambda: [self.pick(['"age"', '"name"', '"tags"', '"nosuch"', "0"])] + ([self.pick(['"eq"', '"gt"', '"in"', '"string"', '"odd"'])] + ([sub()] if r.random() < 0.6 else []) if r.random() < 0.7 else []),
            "rejectattr": lambda: [self.pick(['"age"', '"name"', '"tags"', '"nosuch"', "0"])] + ([self.pick(['"eq"', '"gt"', '"in"', '"string"', '"odd"'])] + ([sub()] if r.random() < 0.6 else []) if r.random() < 0.7 else []),
            "replace": lambda: [self.pick(STRINGS), self.pick(STRINGS)] + ([str(r.randint(0, 2))] if r.random() < 0.3 else []),
            "round": lambda: ([str(r.randint(-1, 2))] if r.random() < 0.6 else []) + ([self.pick(['"floor"', '"ceil"', '"common"', '"bad"'])] if r.random() < 0.3 else []),
            "slice": lambda: [str(r.randint(1, 3))] + ([sub()] if r.random() < 0.3 else []),
            "sort": lambda: ([("reverse=" + self.pick(["true", "false"]))] if r.random() < 0.3 else []) + (["case_sensitive=true"] if r.random() < 0.3 else []) + ([("attribute=" + self.pick(['"age"', '"name"', '"age,name"', "0"]))] if r.random() < 0.3 else []),
            "sum": lambda: ([('attribute=' + self.pick(['"age"', '"n"']))] if r.random() < 0.3 else []) + (["start=%s" % self.pick(["10", "0.5", '""'])] if r.random() < 0.2 else []),
            "tojson": lambda: [str(r.choice([2, 4]))] if r.random() < 0.3 else [],
            "trim": lambda: [self.pick(STRINGS)] if r.random() < 0.4 else [],
            "truncate": lambda: [str(r.randint(3, 20))] + ([self.pick(["true", "false"])] if r.random() < 0.5 else []) + ([self.pick(STRINGS)] if r.random() < 0.3 else []) + (["leeway=%d" % r.randint(0, 4)] if r.random() < 0.3 else []),
            "unique": lambda: ([("case_sensitive=" + self.pick(["true", "false"]))] if r.random() < 0.3 else []) + (['attribute="age"'] if r.random() < 0.2 else []),
            "wordwrap": lambda: [str(r.randint(3, 20))] + ([self.pick(["true", "false"])] if r.random() < 0.4 else []) + ([self.pick(STRINGS)] if r.random() < 0.3 else []),
            "attr": lambda: [self.pick(['"name"', '"k"', '"upper"', '"items"', '"nosuch"', '"prop"', '"real"'])],
            "xmlattr": lambda: ([self.pick(["true", "false"])] if r.random() < 0.3 else []),
        }.get(name, lambda: [])()
        return "%s|%s%s" % (base, name, "(%s)" % ", ".join(args) if args else ("()" if r.random() < 0.1 else ""))

    def test_expr(self, base, depth):
        r = self.rng
        name = self.pick(["odd", "even", "divisibleby", "defined", "undefined", "none", "boolean", "false", "true", "integer", "float", "lower", "upper",
                          "string", "mapping", "number", "sequence", "iterable", "callable", "sameas", "escaped", "in", "eq", "ne", "lt", "le", "gt", "ge",
                          "==", "!=", "<", ">", "filter", "test"])
        arg = ""
        if name in ("divisibleby", "sameas", "in", "eq", "ne", "lt", "le", "gt", "ge", "==", "!=", "<", ">", "filter", "test"):
            atom = self.atom()
            arg = (" " + atom) if atom[0].isalnum() or atom[0] in "'\"[({" else "(%s)" % atom
            if r.random() < 0.3:
                arg = "(%s)" % self.expr(depth - 1)
        return "%s is %s%s%s" % (base, "not " if r.random() < 0.25 else "", name, arg)

    def postfix(self, base, depth):
        r = self.rng.random()
        if r < 0.3:
            return "%s.%s" % (base, self.pick(ATTRS))
        if r < 0.55:
            return "%s[%s]" % (base, self.pick(["0", "1", "-1", "2", '"k"', '"name"', '"items"', "a", "b", "s", self.expr(depth - 1)]))
        if r < 0.7:                # (Jinja folds a slice of a literal while it compiles and does not fail on it; this engine fails when it renders)
            return "%s[%s]" % (self.name(), self.pick(["1:", ":2", "::2", "::-1", "1:2", ":-1", "0:3:2", ":"]))
        if r < 0.85:
            return "%s.%s(%s)" % (base, self.pick(["upper", "split", "items", "keys", "get", "count", "strip", "append", "method", "join", "format", "cycle", "changed"]),
                                  ", ".join(self.expr(depth - 1) for _ in range(self.rng.randint(0, 2))))
        return "%s(%s)" % (self.pick(["f", "kw", "cf", "ef", "xf", "range", "dict", "namespace", "o.method"]),
                           ", ".join(self.pick([self.expr(depth - 1), "%s=%s" % (self.pick(["a", "b", "x"]), self.expr(depth - 1))]) for _ in range(self.rng.randint(0, 3))))

    def expr(self, depth=3):
        r = self.rng
        if depth <= 0:
            return self.atom()
        k = r.random()
        if k < 0.18:
            return self.atom()
        if k < 0.30:
            return "(%s %s %s)" % (self.expr(depth - 1), self.pick(["+", "-", "*", "/", "//", "%", "~", "+", "*"]), self.expr(depth - 1))
        if k < 0.34:
            # (not a negative number to the left of **: Jinja turns -2 ** x into -(2 ** x) when it writes the Python code and (-2) ** x when it
            # evaluates a constant, so the same template can mean two things; this engine always reads it as (-2) ** x)
            # (and a small exponent: 3 ** (10 ** 20) would never finish, in either engine)
            return "%s ** %s" % (self.pick(["a", "b", "c", "x", "y", "z", "2", "3", "0.5"]), self.pick(["0", "1", "2", "3", "0.5", "a", "b", "x", "y"]))
        if k < 0.38:
            return "%s %s %s" % (self.expr(depth - 1), self.pick(["+", "-", "*", "/", "//", "%", "~"]), self.expr(depth - 1))
        if k < 0.46:
            ops = [self.pick(["==", "!=", "<", ">", "<=", ">=", "in", "not in"]) for _ in range(self.rng.choice([1, 1, 1, 2]))]
            return " ".join([self.expr(depth - 1)] + sum(([op, self.expr(depth - 1)] for op in ops), []))
        if k < 0.52:
            return "%s %s %s" % (self.expr(depth - 1), self.pick(["and", "or"]), self.expr(depth - 1))
        if k < 0.56:
            return "not %s" % self.expr(depth - 1)
        if k < 0.60:
            return "%s(%s)" % (self.pick(["-", "+"]), self.expr(depth - 1))
        if k < 0.66:
            return "(%s if %s else %s)" % (self.expr(depth - 1), self.expr(depth - 1), self.expr(depth - 1)) if r.random() < 0.8 else "(%s if %s)" % (self.expr(depth - 1), self.expr(depth - 1))
        if k < 0.84:
            return self.filter_call(self.atom_or_postfix(depth), depth)
        if k < 0.92:
            return "(%s)" % self.test_expr(self.atom_or_postfix(depth), depth)
        return self.postfix(self.atom_or_postfix(depth), depth)

    def atom_or_postfix(self, depth):
        base = self.atom()
        if self.rng.random() < 0.3 and depth > 1:
            base = self.postfix(base, depth - 1)
        if base[0] in "-+" or " " in base and not base.startswith(("(", "[", "{", '"', "'")):
            base = "(%s)" % base
        return base


def expression_case(seed):
    """``(source, options)`` for the expression fuzz: print the expression, maybe with other settings."""
    rng = random.Random(seed)
    gen = Expr(rng)
    parts = ["{{ %s }}" % gen.expr(rng.randint(1, 4)) for _ in range(rng.randint(1, 3))]
    return "|".join(parts), random_options(rng, whitespace=False)


def random_options(rng, whitespace=True):
    options = {}
    if rng.random() < 0.25:
        options["autoescape"] = True
    if rng.random() < 0.15:
        # (not StrictUndefined: Jinja folds constant expressions while it compiles and a strict undefined value that comes out of one raises there,
        # so the error of a template that has one comes before the errors of the rest; the strict mode is tested with templates of its own)
        options["undefined"] = rng.choice(["ChainableUndefined", "DebugUndefined"])
    if whitespace:
        if rng.random() < 0.4:
            options["trim_blocks"] = True
        if rng.random() < 0.4:
            options["lstrip_blocks"] = True
        if rng.random() < 0.3:
            options["keep_trailing_newline"] = True
        if rng.random() < 0.05:
            options["newline_sequence"] = rng.choice(["\r\n", "\r"])
    return options


# whitespace and tags

TEXTS = ["a", "b c", " ", "  ", "\t", "\n", "\n\n", " \n", "\n ", "  \n  ", "\r\n", "\r", "x\ny", "é", "{", "}", "%", "#", "-", "+", "{x", "x}", " ", "\x0b"]
SIGNS = ["", "", "", "-", "+"]


class Whitespace:
    """Sources that are made of text, line breaks, indentation and the tags that interact with them."""

    def __init__(self, rng):
        self.rng = rng

    def sign(self):
        return self.rng.choice(SIGNS)

    def text(self):
        return "".join(self.rng.choice(TEXTS) for _ in range(self.rng.randint(0, 3)))

    def tag(self, body):
        """A block tag with random marks and random spacing."""
        sp = self.rng.choice([" ", "", "  "])
        return "{%" + self.sign() + sp + body + sp + self.sign() + "%}"

    def tag_pair(self, name, expr=""):
        return self.tag(name + (" " + expr if expr else ""))

    def piece(self, depth):
        r = self.rng.random()
        if r < 0.25:
            return self.text()
        if r < 0.40:
            left, right = self.sign(), self.rng.choice(["", "-"])
            return "{{%s %s %s}}" % (left if left != "+" else "", self.rng.choice(["a", "s", "l|length", "'q'", "n", "T"]), right)
        if r < 0.50:
            return "{#%s %s %s#}" % (self.sign(), self.rng.choice(["c", "", "x\ny"]), self.rng.choice(["", "-", "+"]))
        if r < 0.55:
            return "{%s raw %s}%s{%s endraw %s}" % ("%" + self.sign(), self.sign() + "%", self.rng.choice(["{{ a }}", " x\n ", "{% if %}", ""]), "%" + self.sign(), self.sign() + "%")
        if depth > 0 and r < 0.75:
            cond = self.rng.choice(["T", "F", "a", "c"])
            body = self.body(depth - 1)
            if self.rng.random() < 0.4:
                return self.tag_pair("if", cond) + body + self.tag_pair("else") + self.body(depth - 1) + self.tag_pair("endif")
            return self.tag_pair("if", cond) + body + self.tag_pair("endif")
        if depth > 0 and r < 0.9:
            return self.tag_pair("for", "i in " + self.rng.choice(["l", "e", "range(2)", "'ab'"])) + self.body(depth - 1) + self.tag_pair("endfor")
        return self.tag_pair("set", "v = %s" % self.rng.choice(["1", "a"]))

    def body(self, depth):
        return "".join(self.piece(depth) for _ in range(self.rng.randint(0, 4)))

    def source(self):
        return "".join(self.piece(2) for _ in range(self.rng.randint(1, 6)))


def whitespace_case(seed):
    rng = random.Random(seed)
    return Whitespace(rng).source(), random_options(rng)


# whole documents

class Doc:
    """Templates with statements: sets, conditions, loops, macros, call blocks, scopes, blocks, includes and imports."""

    def __init__(self, rng):
        self.rng = rng
        self.expr = Expr(rng)
        self.local_names = []           # names that were assigned so far (so that later expressions can use them)
        self.counter = 0

    def pick(self, seq):
        return self.rng.choice(seq)

    def e(self, depth=2):
        gen = self.expr
        saved = gen.names
        if self.local_names and self.rng.random() < 0.5:
            gen.names = self.local_names + ["loop", "loop"] * (self.rng.random() < 0.5) + ALL_NAMES[:8]
        out = gen.expr(depth)
        gen.names = saved
        return out

    def new_name(self):
        self.counter += 1
        return self.pick(["v", "w", "i", "j", "k", "p", "q"]) + str(self.counter % 3)

    def sp(self):
        return self.pick(["", "", "-", "+"]) if self.rng.random() < 0.3 else ""

    def open_tag(self, text):
        return "{%%%s %s %%}" % (self.sp(), text) if self.rng.random() < 0.9 else "{%%-%s -%%}" % (" " + text + " ")

    def stmt(self, depth):
        rng = self.rng
        r = rng.random()
        if r < 0.20:
            return "{{ %s }}" % self.e(2)
        if r < 0.28:
            return self.pick(["\n", " ", "text ", "\n  ", "<b>&</b>"])
        if r < 0.38:
            name = self.new_name()
            out = "{%% set %s = %s %%}" % (name, self.e(2))
            self.local_names.append(name)
            return out
        if r < 0.42:
            name = self.new_name()
            out = "{%% set %s, %s_ = %s %%}" % (name, name, self.pick(["l[:2]", "[1, 2]", "nested[0]", "(a, b)", "s", "d2.items()|first"]))
            self.local_names += [name, name + "_"]
            return out
        if depth <= 0:
            return "{{ %s }}" % self.e(1)
        if r < 0.52:
            out = "{%% if %s %%}%s" % (self.e(2), self.body(depth - 1))
            for _ in range(rng.choice([0, 0, 1])):
                out += "{%% elif %s %%}%s" % (self.e(1), self.body(depth - 1))
            if rng.random() < 0.5:
                out += "{% else %}" + self.body(depth - 1)
            return out + "{% endif %}"
        if r < 0.64:
            target = self.pick(["i", "k, v", "i, j", "x_"])
            saved = list(self.local_names)
            self.local_names += [t.strip() for t in target.split(",")] + ["loop"]
            it = self.pick(["l", "e", "range(3)", "users", "d2|dictsort", "d.items()", "nested", "words", "tup", "'ab'", "nosuch", "n", "range(a)", "l|reverse", self.e(1)])
            cond = (" if %s" % self.pick(["loop.index is odd", "true", "false", "i is defined", "i > 1", self.e(1)])) if rng.random() < 0.25 else ""
            out = "{%% for %s in %s%s %%}%s" % (target, it, cond, self.body(depth - 1))
            if rng.random() < 0.3:
                out += "{% else %}" + self.body(depth - 1)
            self.local_names = saved
            return out + "{% endfor %}"
        if r < 0.70:
            name = "m%d" % (self.counter % 3)
            self.counter += 1
            args = self.pick(["", "p", "p, q=2", "p=1, q=p", "a, b", "*x"][:5])
            saved = list(self.local_names)
            self.local_names += ["p", "q", "a", "b", "varargs", "kwargs", "caller"]
            body = self.body(depth - 1)
            self.local_names = saved
            call = "{{ %s(%s) }}" % (name, ", ".join(self.pick(["", "1", "'x'", "a", "p=2", "q=3", "1, 2", "1, 2, 3", "z=1"]) for _ in range(rng.randint(0, 1))))
            return "{%% macro %s(%s) %%}%s{%% endmacro %%}%s" % (name, args, body, call)
        if r < 0.74:
            return "{%% macro cm() %%}[{{ caller(%s) }}]{%% endmacro %%}{%% call%s cm() %%}%s{%% endcall %%}" % (
                self.pick(["", "1", "1, 2"]), self.pick(["", "(a)", "(a, b)"]), self.body(depth - 1))
        if r < 0.78:
            name = self.new_name()
            saved = list(self.local_names)
            self.local_names.append(name)
            out = "{%% with %s = %s %%}%s{%% endwith %%}" % (name, self.e(1), self.body(depth - 1))
            self.local_names = saved
            return out
        if r < 0.82:
            return "{%% filter %s %%}%s{%% endfilter %%}" % (self.pick(["upper", "trim", "e", "safe", "lower|title", "indent(2)", "replace('a', 'b')", "length"]), self.body(depth - 1))
        if r < 0.86:
            name = self.new_name()
            out = "{%% set %s%s %%}%s{%% endset %%}" % (name, self.pick(["", "", " | upper", " | trim"]), self.body(depth - 1))
            self.local_names.append(name)
            return out
        if r < 0.89:
            if rng.random() < 0.3:
                # an option that is only known when the template runs; in such a block Jinja does not escape what it can compute while it compiles (a
                # literal, a list of literals), so the body here only prints values that come from variables
                return "{%% autoescape %s %%}%s{%% endautoescape %%}" % (self.pick(["a", "c", "T", "n"]), "".join(
                    self.pick(["{{ u ~ md }}", "{{ md ~ u }}", "{{ s|upper }}", "{{ md }}", "{{ u }}", "{{ [u, md]|join('-') }}", "{{ u|replace('b', md) }}", "{% set q = u ~ 'x' %}{{ q }}"])
                    for _ in range(rng.randint(1, 3))))
            return "{%% autoescape %s %%}%s{%% endautoescape %%}" % (self.pick(["true", "false"]), self.body(depth - 1))
        if r < 0.93:
            return self.pick(["{% include 'inc' %}", "{% include ['none', 'inc'] %}", "{% include 'none' ignore missing %}",
                              "{% include 'inc' with context %}", "{% include 'none' %}"])
        if r < 0.97:
            return self.pick(["{% import 'mac' as mm %}{{ mm.greet('x') }}", "{% from 'mac' import greet, shout as sh %}{{ greet('y') }}{{ sh('z') }}",
                              "{% import 'mac' as mm with context %}{{ mm.greet(a) }}", "{% from 'mac' import nosuch %}{{ nosuch }}", "{% from 'mac' import greet with context %}{{ greet(s) }}",
                              "{% import 'mac' as mm %}{{ mm.top }}{{ mm._hidden }}"])
        return "{# %s #}" % self.pick(["c", "{{ a }}", ""])

    def body(self, depth):
        return "".join(self.stmt(depth) for _ in range(self.rng.randint(1, 3)))

    def source(self):
        return "".join(self.stmt(3) for _ in range(self.rng.randint(1, 5)))


TEMPLATES = {
    "inc": "<inc {{ a }}|{{ v0|default('nov') }}|{{ i|default('noi') }}>{% set leaked = 1 %}",
    "mac": ("{% macro greet(n) %}hello {{ n }} {{ a|default('noa') }}{% endmacro %}{% macro shout(n) %}{{ greet(n)|upper }}{% endmacro %}"
            "{% set top = 'T' %}{% set _hidden = 'H' %}"),
    "base": "[{% block head %}H{% endblock %}|{% block body %}B{{ a }}{% endblock %}|{% block foot %}F{% endblock %}]",
    "mid": "{% extends 'base' %}{% block body %}<{{ super() }}>{% block inner %}I{% endblock %}{% endblock %}",
}


def doc_case(seed):
    rng = random.Random(seed)
    return Doc(rng).source(), random_options(rng), TEMPLATES


INHERIT_PARTS = [
    "{% block head %}{{ super() }}+h{% endblock %}", "{% block body %}b{{ self.head() }}{% endblock %}", "{% block foot %}{% endblock %}",
    "{% block inner %}in{{ super() }}{% endblock %}", "{% set title = 'T' %}", "{{ a }}", "text", "{% macro m() %}M{% endmacro %}{{ m() }}",
    "{% block head scoped %}{% for i in l %}{% block loopy scoped %}{{ i }}{% endblock %}{% endfor %}{% endblock %}",
    "{% for i in l %}{% block loopy2 %}{{ i|default('-') }}{% endblock %}{% endfor %}", "{% block extra %}X{% endblock %}",
    "{% block head required %}{% endblock %}", "{% block body %}{% block inner %}J{{ super() }}{% endblock %}{% endblock %}",
]


def inheritance_case(seed):
    rng = random.Random(seed)
    parent = rng.choice(["base", "mid"])
    parts = [rng.choice(INHERIT_PARTS) for _ in range(rng.randint(1, 4))]
    if rng.random() < 0.3:
        parts.insert(rng.randint(0, len(parts)), "{% set s = 'child' %}")
    source = rng.choice(["", "pre", "{# c #}"]) + "{%% extends '%s' %%}" % parent + "".join(parts)
    return source, random_options(rng), TEMPLATES


# damaged templates: valid sources with a few characters or tokens deleted, inserted or swapped

JUNK = ["{{", "}}", "{%", "%}", "{#", "#}", "(", ")", "[", "]", "{", "}", ",", ":", "|", ".", "=", "==", "-", "+", "~", "'", '"', "\\", "if", "else",
        "elif", "endif", "for", "endfor", "in", "is", "not", "and", "or", "set", "block", "endblock", "macro", "endmacro", "raw", "endraw", "\n", " ",
        "extends", "include", "import", "from", "as", "with", "endwith", "call", "endcall", "filter", "endfilter", "1", "a", "x.y", "%", "*", "**", "//", ";", "@", "$", "!", "?"]


def mutation_case(seed):
    rng = random.Random(seed)
    kind = rng.choice(["doc", "doc", "expr", "ws"])
    if kind == "doc":
        source, options, templates = doc_case(rng.randrange(10 ** 6))
    elif kind == "expr":
        source, options = expression_case(rng.randrange(10 ** 6))
        templates = None
    else:
        source, options = whitespace_case(rng.randrange(10 ** 6))
        templates = None
    for _ in range(rng.choice([1, 1, 1, 2, 3])):
        if not source:
            break
        pos = rng.randrange(len(source) + 1)
        r = rng.random()
        if r < 0.3:
            source = source[:pos] + source[pos + rng.randint(1, 8):]
        elif r < 0.7:
            source = source[:pos] + rng.choice(JUNK) + source[pos:]
        elif r < 0.85:
            end = min(len(source), pos + rng.randint(1, 6))
            source = source[:pos] + rng.choice(JUNK) + source[end:]
        else:
            other = rng.randrange(len(source))
            source = source[:pos] + source[other:other + rng.randint(1, 10)] + source[pos:]
    return source, options, templates
