"""Expressions: operators and their precedence, literals, lookup of attributes and items, calls, tests.  The expected text is what Jinja2 gives."""
import pytest

from oracle import expect, expect_error

CASES = [
    ('{{ 1 + 2 }}|{{ 7 - 10 }}|{{ 3 * 4 }}|{{ 7 / 2 }}|{{ 7 // 2 }}|{{ -7 // 2 }}|{{ 7 % 3 }}|{{ -7 % 3 }}|{{ 2 ** 10 }}|{{ 2 ** -1 }}|{{ 4 / 2 }}', '3|-3|12|3.5|3|-4|1|2|1024|0.5|2.0'),
    ('{{ 2 + 3 * 4 }}|{{ (2 + 3) * 4 }}|{{ 2 * 3 + 4 }}|{{ 10 - 2 - 3 }}|{{ 2 ** 3 ** 2 }}|{{ -a ** 2 }}|{{ 100 / 10 / 5 }}', '14|20|10|5|64|9|2.0'),
    ('{{ "a" ~ 1 ~ none ~ true ~ [1] }}|{{ 2 * 3 ~ 4 }}|{{ "x" * 3 }}|{{ [0] * 3 }}|{{ "%s-%s" % (1, 2) }}', 'a1NoneTrue[1]|64|xxx|[0, 0, 0]|1-2'),
    ('{{ a < b }}|{{ a > b }}|{{ a == 3 }}|{{ a != 3 }}|{{ a <= 3 }}|{{ a >= 4 }}|{{ 1 < 2 < 3 }}|{{ 1 < 3 < 2 }}|{{ 3 > 2 > 1 }}|{{ 1 == 1 == 1 }}', 'False|True|True|False|True|False|True|False|True|True'),
    ('{{ 2 in [1, 2] }}|{{ 3 in [1, 2] }}|{{ 3 not in [1, 2] }}|{{ "a" in "abc" }}|{{ "k" in d }}|{{ 1 in nosuch }}', 'True|False|True|True|True|False'),
    ('{{ true and false }}|{{ true or false }}|{{ not true }}|{{ 0 or "x" }}|{{ 1 and "y" }}|{{ "" and 1 }}|{{ none or 0 or [] }}|{{ not 0 and 1 }}|{{ a and b or c }}', 'False|True|False|x|y||[]|1|-2'),
    ('{{ "yes" if a else "no" }}|{{ "yes" if c else "no" }}|{{ ("yes" if c) }}|{{ 1 if c else 2 if a else 3 }}', 'yes|no||2'),
    ('{{ a is odd }}|{{ a is even }}|{{ a is not even }}|{{ not a is even }}|{{ 6 is divisibleby 3 }}|{{ 6 is divisibleby(4) }}|{{ x is number }}|{{ s is string }}|{{ nosuch is defined }}|{{ nosuch is undefined }}|{{ n is none }}|{{ T is true }}|{{ 1 is sameas 1 }}|{{ [] is sameas [] }}', 'True|False|True|True|True|False|True|True|False|True|True|True|True|False'),
    ('{{ 3 is eq 3 }}|{{ 3 is ne 3 }}|{{ 3 is lt 4 }}|{{ 3 is le 3 }}|{{ 3 is gt 4 }}|{{ 3 is ge 3 }}|{{ 3 is in [3] }}|{{ "a" is in "abc" }}|{{ \'x\' is lower }}|{{ \'X\' is upper }}|{{ l is iterable }}|{{ 5 is iterable }}|{{ d is mapping }}|{{ l is sequence }}|{{ f is callable }}|{{ 1 is integer }}|{{ 1.5 is float }}|{{ md is escaped }}|{{ \'upper\' is filter }}|{{ \'odd\' is test }}', 'True|False|True|True|False|True|True|True|True|True|True|False|True|True|True|True|True|True|True|True'),
    ('{{ [1, 2, 3] }}|{{ (1, 2) }}|{{ (1,) }}|{{ () }}|{{ {"a": 1} }}|{{ {} }}|{{ [] }}|{{ [1, [2, 3]][1][0] }}|{{ {"a": {"b": 2}}.a.b }}|{{ 1, 2 }}', "[1, 2, 3]|(1, 2)|(1,)|()|{'a': 1}|{}|[]|2|2|(1, 2)"),
    ('{{ l[0] }}|{{ l[-1] }}|{{ l[1:] }}|{{ l[:2] }}|{{ l[::-1] }}|{{ l[::2] }}|{{ l[5] }}|{{ s[1:4] }}|{{ s[-3:] }}|{{ nested[1][0] }}|{{ nested.1.0 }}|{{ tup[1] }}', '3|2|[1, 2]|[3, 1]|[2, 1, 3]|[3, 2]||ell|rld|3|3|2'),
    ('{{ d.k }}|{{ d["j"] }}|{{ d.items }}|{{ d["items"] }}|{{ d.zz }}|{{ d["zz"] }}|{{ o.name }}|{{ o["name"] }}|{{ o.method() }}|{{ o.method(5) }}|{{ o.prop }}|{{ o.nosuch }}|{{ o.items }}', '1|2|<built-in method items of dict object at 0xADDR>|shadow|||obj|obj|method:1|method:5|prop||[1, 2]'),
    ('{{ l.index(1) }}|{{ s.upper() }}|{{ s.split()|length }}|{{ "a,b".split(",") }}|{{ d.get("k") }}|{{ d.keys()|list }}|{{ "{} {}".format(1, 2) }}', "1|HELLO WORLD|2|['a', 'b']|1|['k', 'j', 'items']|1 2"),
    ('{{ f(4) }}|{{ f(a) + 1 }}|{{ kw(1) }}|{{ kw(1, 2, 3, z=4) }}|{{ kw(*[1, 2], **{"y": 3}) }}|{{ kw(b=7, a=1) }}', "8|7|a=1 b=2 rest=() kw=[]|a=1 b=2 rest=(3,) kw=[('z', 4)]|a=1 b=2 rest=() kw=[('y', 3)]|a=1 b=7 rest=() kw=[]"),
    ('{{ true }}|{{ True }}|{{ false }}|{{ False }}|{{ none }}|{{ None }}|{{ TRUE }}', 'True|True|False|False|None|None|'),
    ('{{ 1_000 }}|{{ 0x1F }}|{{ 0b11 }}|{{ 0o17 }}|{{ 1e3 }}|{{ 1.5E-2 }}|{{ 12.50 }}|{{ 10 ** 20 }}', '1000|31|3|15|1000.0|0.015|12.5|100000000000000000000'),
    ('{{ "a" "b" }}|{{ \'x\' \'y\' "z" }}|{{ "tab\\t|" }}|{{ \'q\\\'q\' }}|{{ "é" }}', "ab|xyz|tab\t||q'q|é"),
    ('{{ range(3) }}|{{ range(3)|list }}|{{ range(1, 5)|sum }}|{{ range(0)|list }}', 'range(0, 3)|[0, 1, 2]|10|[]'),
    ('{{ a if a else b }}|{{ (a, b)|max }}|{{ [a, b]|sum }}|{{ a ~ b }}|{{ a|string ~ b|string }}', '3|3|1|3-2|3-2'),
]


@pytest.mark.parametrize("source, expected", CASES)
def test_expression(source, expected):
    expect(source, expected)


def test_concatenation_binds_tighter_than_plus():
    expect_error("{{ 1 + 2 ~ 3 }}", "TypeError", "unsupported operand type(s) for +: 'int' and 'str'")
    expect_error("{{ 1 ~ 2 + 3 }}", "TypeError", 'can only concatenate str (not "int") to str')


def test_power_is_left_associative_and_a_variable_with_minus_is_negated_first():
    expect("{{ 2 ** 3 ** 2 }}|{{ 2 ** 2 ** 3 }}", "64|64")          # (2 ** 3) ** 2, unlike Python
    expect("{{ -a ** 2 }}|{{ -a|abs }}", "9|3")


def test_filter_binds_tighter_than_the_operators_around_it():
    expect("{{ '1' ~ 2|string }}", "12")
    expect("{{ -3|abs }}", "3")
    expect("{{ a * b|abs }}", "6")


def test_is_binds_tighter_than_not_and_comparison():
    expect("{{ not 3 is odd }}|{{ 1 == 1 is true }}", "False|False")         # not (3 is odd); 1 == (1 is true)


def test_a_call_after_a_filter_or_a_test_is_allowed():
    expect("{{ 'ab'|attr('upper')() }}", "AB")


@pytest.mark.parametrize("source, message", [
    ("{{ f(a=1, 2) }}", "invalid syntax for function call expression"),
    ("{{ f(**d, 1) }}", "invalid syntax for function call expression"),
    ("{{ f(*l, **d, *l) }}", "invalid syntax for function call expression"),
    ("{{ 1 is odd is even }}", "You cannot chain multiple tests with is"),
    ("{{ }}", "Expected an expression, got 'end of print statement'"),
    ("{{ a + }}", "unexpected 'end of print statement'"),
    ("{{ a b }}", "expected token 'end of print statement', got 'b'"),
    ("{{ 'a' if }}", "unexpected 'end of print statement'"),
    ("{{ [1, 2 }}", "unexpected '}', expected ']'"),
    ("{{ {1: 2, 3} }}", "expected token ':', got '}'"),
    ("{{ a.1b }}", "expected token 'end of print statement', got 'b'"),
    ("{{ a.'x' }}", "expected name or number"),
])
def test_expression_syntax_errors(source, message):
    expect_error(source, "TemplateSyntaxError", message, 1)
