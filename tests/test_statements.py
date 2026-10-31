"""Statements: if, for (and loop), set, with, macro, call, filter, raw, print, autoescape, and the scopes of all of them."""
import pytest

from oracle import expect, expect_error

CASES = [
    ('{% if a > 2 %}big{% elif a > 1 %}mid{% else %}small{% endif %}|{% if c %}x{% elif b %}y{% endif %}|{% if n %}n{% else %}no{% endif %}', 'big|y|no'),
    ('{% for i in l %}{{ i }}{% else %}none{% endfor %}|{% for i in e %}{{ i }}{% else %}none{% endfor %}', '312|none'),
    ('{% for i in range(5) if i is odd %}{{ loop.index }}:{{ i }} {% endfor %}', '1:1 2:3 '),
    ('{% for i in l %}{{ loop.index }}{{ loop.index0 }}{{ loop.revindex }}{{ loop.revindex0 }}{{ loop.first }}{{ loop.last }}{{ loop.length }} {% endfor %}', '1032TrueFalse3 2121FalseFalse3 3210FalseTrue3 '),
    ('{% for i in l %}{{ loop.previtem }}|{{ loop.nextitem }} {% endfor %}', '|1 3|2 1| '),
    ('{% for i in l %}{{ loop.cycle("a", "b") }}{% endfor %}|{% for i in l %}{{ "x" if loop.changed(i > 1) }}{% endfor %}', 'aba|xxx'),
    ('{% for k, v in d2|dictsort %}{{ k }}={{ v }},{% endfor %}|{% for a, (b, c) in [(1, (2, 3))] %}{{ a }}{{ b }}{{ c }}{% endfor %}', 'a=1,b=2,C=3,|123'),
    ('{% for i in "abc" %}{{ i }}{% endfor %}|{% for i in d %}{{ i }} {% endfor %}|{% for i in nosuch %}x{% else %}empty{% endfor %}', 'abc|k j items |empty'),
    ('{% for x in tree recursive %}{{ x.name }}{% if x.children %}[{{ loop(x.children) }}]{% endif %}{% endfor %}', 'r[c1c2[g]]'),
    ('{% for x in tree recursive %}{{ loop.depth }}{{ x.name }}{{ loop(x.children) }}{% endfor %}', '1r2c12c23g'),
    ('{% for i in l %}{% for j in l %}{{ loop.index }}{% endfor %}{{ loop.index }}|{% endfor %}', '1231|1232|1233|'),
    ('{% set x = 1 %}{% for i in l %}{% set x = i %}{{ x }}{% endfor %}{{ x }}', '3121'),
    ('{% set ns = namespace(total=0, seen=[]) %}{% for i in l %}{% set ns.total = ns.total + i %}{% set _ = ns.seen.append(i) %}{% endfor %}{{ ns.total }}{{ ns.seen }}', '6[3, 1, 2]'),
    ('{% for i in l %}{% endfor %}{{ i is defined }}|{{ loop is defined }}', 'False|False'),
    ('{% set a, b = 1, 2 %}{{ a }}{{ b }}|{% set (c, d) = [3, 4] %}{{ c }}{{ d }}|{% set t = 1, 2 %}{{ t }}', '12|34|(1, 2)'),
    ('{% set x %}in{{ a }}{% endset %}[{{ x }}]|{% set y | upper %}up{% endset %}{{ y }}', '[in3]|UP'),
    ('{% with a = 10, b = a + 1 %}{{ a }},{{ b }}{% endwith %}|{{ a }}|{% with %}{% set z = 1 %}{{ z }}{% endwith %}{{ z is defined }}', '10,4|3|1True'),
    ('{% if true %}{% set inside = 1 %}{% endif %}{{ inside }}', '1'),
    ('{% macro m(p, q=2) %}{{ p }}-{{ q }}{% endmacro %}{{ m(1) }} {{ m(1, 3) }} {{ m(q=5, p=0) }}', '1-2 1-3 0-5'),
    ('{% macro m(p) %}{{ p is defined }}{% endmacro %}{{ m() }}', 'False'),
    ('{% macro m() %}{{ varargs }}{{ kwargs }}{% endmacro %}{{ m(1, 2, k=3) }}', "(1, 2){'k': 3}"),
    ('{% macro m(a, b=a) %}{{ a }}{{ b }}{% endmacro %}{{ m(1) }}', '11'),
    ('{% macro f(n) %}{% if n %}{{ n }}{{ f(n - 1) }}{% endif %}{% endmacro %}{{ f(3) }}', '321'),
    ('{% macro m() %}x{% endmacro %}{{ m.name }} {{ m.arguments }} {{ m.catch_kwargs }} {{ m.catch_varargs }} {{ m.caller }}', 'm () False False False'),
    ('{% macro wrap() %}<{{ caller() }}>{% endmacro %}{% call wrap() %}inner {{ a }}{% endcall %}', '<inner 3>'),
    ('{% macro each(items) %}{% for i in items %}{{ caller(i, loop.index) }}{% endfor %}{% endmacro %}{% call(item, n) each([10, 20]) %}{{ n }}={{ item }} {% endcall %}', '1=10 2=20 '),
    ('{% macro m() %}{{ caller is defined }}{% endmacro %}{{ m() }}|{% call m() %}{% endcall %}', 'False|True'),
    ('{% macro a() %}A{% endmacro %}{% macro b() %}{{ a() }}B{% endmacro %}{{ b() }}', 'AB'),
    ('{% set v = 1 %}{% macro m() %}{{ v }}{% endmacro %}{% set v = 2 %}{{ m() }}', '2'),
    ('{% macro m(x) %}{% set x = x * 2 %}{{ x }}{% endmacro %}{% set x = 5 %}{{ m(x) }}{{ x }}', '105'),
    ('{% filter upper %}shout {{ s }}{% endfilter %}|{% filter replace("a", "b") %}banana{% endfilter %}', 'SHOUT HELLO WORLD|bbnbnb'),
    ('{{ self }}', '<TemplateReference None>'),
    ('{% block b %}x{% endblock %}|{% block c %}{{ self.b() }}{% endblock %}|{% block b2 %}y{% endblock %}', 'x|x|y'),
    ('{% raw %}{{ a }}{% endraw %}{# no #}{% raw %}{% if %}{% endraw %}', '{{ a }}{% if %}'),
    ('{% print a, b %}|{% print 1 + 2 %}', '3-2|3'),
    ('{% autoescape true %}{{ u }}{% endautoescape %}|{{ u }}|{% autoescape false %}{{ u }}{% endautoescape %}', '&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;|<b>é&"\'</b>|<b>é&"\'</b>'),
    ('{{ cycler("a", "b").next() }}{% set c2 = cycler("x", "y") %}{{ c2.next() }}{{ c2.next() }}{{ c2.next() }}{{ c2.current }}', 'axyxy'),
    ('{% set j = joiner(", ") %}{% for i in l %}{{ j() }}{{ i }}{% endfor %}', '3, 1, 2'),
    ('{{ namespace(a=1, b=2).b }}|{{ dict(a=1, b=2) }}|{{ range(2, 10, 3)|list }}', "2|{'a': 1, 'b': 2}|[2, 5, 8]"),
]


@pytest.mark.parametrize("source, expected", CASES)
def test_statement(source, expected):
    expect(source, expected)


@pytest.mark.parametrize("source, error, message, lineno", [
    ("{% for loop in l %}{% endfor %}", "TemplateAssertionError", "Can't assign to special loop variable in for-loop target", 1),
    ("{% set true = 1 %}", "TemplateSyntaxError", "can't assign to 'const'", 1),
    ("{% set a.b = 1 %}", "TemplateRuntimeError", "cannot assign attribute on non-namespace object", None),
    ("{% set d.k = 1 %}", "TemplateRuntimeError", "cannot assign attribute on non-namespace object", None),
    ("{% set a.b.c = 1 %}", "TemplateSyntaxError", "expected token 'end of statement block', got '.'", 1),
    ("{% set ns = 1 %}{% set ns.x = 1 %}", "TemplateRuntimeError", "cannot assign attribute on non-namespace object", None),
    ("{% set a, b = 1 %}", "TypeError", "cannot unpack non-iterable int object", None),
    ("{% for a, b in nested + [[1]] %}{% endfor %}", "ValueError", "not enough values to unpack (expected 2, got 1)", None),
    ("{% for a, b in [[1, 2, 3]] %}{% endfor %}", "ValueError", "too many values to unpack (expected 2)", None),
    ("{% for i in a %}{% endfor %}", "TypeError", "'int' object is not iterable", None),
    ("{% macro m(a=1, b) %}{% endmacro %}", "TemplateSyntaxError", "non-default argument follows default argument", 1),
    ("{% macro m(a) %}{% endmacro %}{{ m(1, 2) }}", "TypeError", "macro 'm' takes not more than 1 argument(s)", None),
    ("{% macro m(a) %}{% endmacro %}{{ m(b=2) }}", "TypeError", "macro 'm' takes no keyword argument 'b'", None),
    ("{% call foo %}{% endcall %}", "TemplateSyntaxError", "expected call", 1),
    ("{% for i in l %}", "TemplateSyntaxError", "Unexpected end of template. Jinja was looking for the following tags: 'endfor' or 'else'. The innermost block that needs to be closed is 'for'.", 1),
    ("{% if %}x{% endif %}", "TemplateSyntaxError", "Expected an expression, got 'end of statement block'", 1),
    ("{% for i in %}{% endfor %}", "TemplateSyntaxError", "Expected an expression, got 'end of statement block'", 1),
    ("{% else %}", "TemplateSyntaxError", "Encountered unknown tag 'else'.", 1),
    ("{% 1 %}", "TemplateSyntaxError", "tag name expected", 1),
    ("{% set x = %}", "TemplateSyntaxError", "Expected an expression, got 'end of statement block'", 1),
    ("{% for i in l if %}{% endfor %}", "TemplateSyntaxError", "unexpected 'end of statement block'", 1),
])
def test_statement_errors(source, error, message, lineno):
    expect_error(source, error, message, lineno)


def test_a_colon_after_a_tag_is_allowed():
    expect("{% if true: %}x{% endif %}", "x")


def test_the_scope_of_a_for_loop_set_with_and_macro():
    expect("{% set v = 1 %}{% for i in l %}{% set v = 2 %}{% endfor %}{{ v }}", "1")
    expect("{% set v = 1 %}{% if true %}{% set v = 2 %}{% endif %}{{ v }}", "2")
    expect("{% set v = 1 %}{% with %}{% set v = 2 %}{% endwith %}{{ v }}", "1")
    expect("{% set v = 1 %}{% macro m() %}{% set v = 2 %}{% endmacro %}{{ m() }}{{ v }}", "1")
    expect("{% set v = 1 %}{% filter upper %}{% set v = 2 %}{% endfilter %}{{ v }}", "1")
    expect("{% set v = 1 %}{% set y %}{% set v = 2 %}{% endset %}{{ v }}", "1")
    expect("{% set v = 1 %}{% autoescape false %}{% set v = 2 %}{% endautoescape %}{{ v }}", "1")
    expect("{% for i in [1] %}{% set v = i %}{% endfor %}{{ v is defined }}", "False")


def test_a_variable_read_before_it_is_set_in_a_loop_comes_from_outside():
    expect("{% set v = 'out' %}{% for i in [1, 2] %}{{ v }}{% set v = i %}{{ v }}{% endfor %}", "out1out2")


def test_namespace_is_how_a_loop_changes_a_variable():
    expect("{% set ns = namespace(n=0) %}{% for i in [1, 2, 3] %}{% set ns.n = ns.n + i %}{% endfor %}{{ ns.n }}", "6")


def test_the_loop_of_the_loop_is_the_inner_one():
    expect("{% for i in 'ab' %}{% for j in 'xy' %}{{ loop.index }}{% endfor %}{{ loop.index }}{% endfor %}", "121122")
