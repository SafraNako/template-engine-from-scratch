"""Every filter with its arguments: the text that comes out is what Jinja2 gives (the ``expect`` helper checks both engines against it)."""
import pytest

from oracle import expect, expect_error

CASES = [
    ('{{ -3|abs }} {{ 2.5|abs }}', '3 2.5'),
    ('{{ users|map(attribute="name")|join(", ") }}', 'ann, Bob, cy'),
    ('{{ [[1, 2], [3]]|map("sum")|list }}', '[3, 3]'),
    ('{{ "abc"|attr("upper")() }}', 'ABC'),
    ('{{ [1, 2, 3, 4, 5]|batch(2)|list }}', '[[1, 2], [3, 4], [5]]'),
    ('{{ [1, 2, 3, 4, 5]|batch(2, 0)|list }}', '[[1, 2], [3, 4], [5, 0]]'),
    ('{{ "hello world"|capitalize }}|{{ "HELLO"|capitalize }}', 'Hello world|Hello'),
    ('{{ "ab"|center(6) }}|{{ "ab"|center(5) }}', '  ab  |  ab '),
    ('{{ [1, 2, 3]|count }}|{{ "abc"|count }}|{{ d|count }}', '3|3|3'),
    ('{{ nosuch|default("fallback") }}|{{ n|default("fallback") }}|{{ ""|default("fallback", true) }}|{{ 0|default("fallback", boolean=true) }}', 'fallback|None|fallback|fallback'),
    ('{{ d2|dictsort }}|{{ d2|dictsort(true) }}|{{ d2|dictsort(by="value", reverse=true) }}', "[('a', 1), ('b', 2), ('C', 3)]|[('C', 3), ('a', 1), ('b', 2)]|[('C', 3), ('b', 2), ('a', 1)]"),
    ('{{ "<a&b>"|e }}|{{ "<a&b>"|escape }}|{{ md|e }}|{{ 5|e }}', '&lt;a&amp;b&gt;|&lt;a&amp;b&gt;|<i>safe</i>|5'),
    ('{{ 0|filesizeformat }}|{{ 1|filesizeformat }}|{{ 999|filesizeformat }}|{{ 1000|filesizeformat }}|{{ 1500000|filesizeformat }}|{{ 1500|filesizeformat(true) }}|{{ (10**30)|filesizeformat }}', '0 Bytes|1 Byte|999 Bytes|1.0 kB|1.5 MB|1.5 KiB|1000000.0 YB'),
    ('{{ [3, 2, 1]|first }}|{{ []|first }}|{{ "abc"|first }}', '3||a'),
    ('{{ "3.5"|float }}|{{ "x"|float }}|{{ "x"|float(1.5) }}|{{ 3|float }}', '3.5|0.0|1.5|3.0'),
    ('{{ md|forceescape }}|{{ "<"|forceescape }}', '&lt;i&gt;safe&lt;/i&gt;|&lt;'),
    ('{{ "%s and %s"|format("a", "b") }}|{{ "%(x)d"|format(x=3) }}|{{ "%.2f"|format(3.14159) }}', 'a and b|3|3.14'),
    ('{{ users|groupby("age") }}', "[(25, [{'name': 'Bob', 'age': 25, 'tags': []}]), (30, [{'name': 'ann', 'age': 30, 'tags': ['x', 'y']}, {'name': 'cy', 'age': 30, 'tags': ['z']}])]"),
    ('{% for age, group in users|groupby("age") %}{{ age }}:{{ group|map(attribute="name")|join("+") }};{% endfor %}', '25:Bob;30:ann+cy;'),
    ('{{ "a\\nb\\n\\nc"|indent(2) }}|{{ "a\\nb"|indent(2, true) }}|{{ "a\\n\\nb"|indent(2, false, true) }}|{{ "a\\nb"|indent("--") }}', 'a\n  b\n\n  c|  a\n  b|a\n  \n  b|a\n--b'),
    ('{{ "12"|int }}|{{ "x"|int }}|{{ "x"|int(7) }}|{{ 3.9|int }}|{{ "ff"|int(base=16) }}|{{ "0x1f"|int(0, 16) }}|{{ "3.9"|int }}|{{ none|int }}', '12|0|7|3|255|31|3|0'),
    ('{{ [1, 2, 3]|join }}|{{ [1, 2, 3]|join(", ") }}|{{ users|join("/", "name") }}|{{ ["<", ">"]|join("&") }}', '123|1, 2, 3|ann/Bob/cy|<&>'),
    ('{{ [3, 2, 1]|last }}|{{ []|last }}|{{ "abc"|last }}', '1||c'),
    ('{{ "abc"|length }}|{{ [1, 2]|length }}|{{ {}|length }}', '3|2|0'),
    ('{{ "abc"|list }}|{{ d|list }}|{{ range(3)|list }}', "['a', 'b', 'c']|['k', 'j', 'items']|[0, 1, 2]"),
    ('{{ "ABC"|lower }}|{{ md|lower }}', 'abc|<i>safe</i>'),
    ('{{ d2|items|list }}|{{ nosuch|items|list }}', "[('b', 2), ('a', 1), ('C', 3)]|[]"),
    ('{{ [1, 2, 3]|map("string")|list }}|{{ ["a", "b"]|map("upper")|join }}|{{ [1, 2]|map("float")|list }}', "['1', '2', '3']|AB|[1.0, 2.0]"),
    ('{{ ["a", "B"]|min }}|{{ ["a", "B"]|min(case_sensitive=true) }}|{{ []|min }}|{{ users|max(attribute="age") |attr("name") }}|{{ [1, 5, 3]|max }}', 'a|B|||5'),
    ('{{ {"a": [1, 2]}|pprint }}', "{'a': [1, 2]}"),
    ('{{ [1, 2, 3, 4]|reject("odd")|list }}|{{ users|rejectattr("tags")|map(attribute="name")|list }}|{{ [0, 1, ""]|reject|list }}', "[2, 4]|['Bob']|[0, '']"),
    ('{{ "aaa"|replace("a", "b") }}|{{ "aaa"|replace("a", "b", 2) }}|{{ "abc"|replace("", "-") }}|{{ 123|replace("2", "x") }}', 'bbb|bba|-a-b-c-|1x3'),
    ('{{ [1, 2, 3]|reverse|list }}|{{ "abc"|reverse }}', '[3, 2, 1]|cba'),
    ('{{ 2.5|round }}|{{ 3.5|round }}|{{ 1.2345|round(2) }}|{{ 1.21|round(1, "ceil") }}|{{ 1.29|round(1, "floor") }}|{{ 1234|round(-2) }}', '2.0|4.0|1.23|1.3|1.2|1200'),
    ('{{ "<b>"|safe }}|{{ "<b>"|safe|e }}|{{ ("<b>"|safe) ~ "<i>" }}', '<b>|<b>|<b><i>'),
    ('{{ [1, 2, 3, 4]|select("odd")|list }}|{{ users|selectattr("tags")|map(attribute="name")|list }}|{{ users|selectattr("age", "eq", 30)|list|length }}|{{ [0, 1, ""]|select|list }}|{{ [1, 2, 3]|select("gt", 1)|list }}', "[1, 3]|['ann', 'cy']|2|[1]|[2, 3]"),
    ('{{ [1, 2, 3, 4, 5]|slice(2)|list }}|{{ [1, 2, 3]|slice(2, "-")|list }}', "[[1, 2, 3], [4, 5]]|[[1, 2], [3, '-']]"),
    ('{{ [3, 1, 2]|sort }}|{{ [3, 1, 2]|sort(reverse=true) }}|{{ ["b", "A", "c"]|sort }}|{{ ["b", "A", "c"]|sort(case_sensitive=true) }}|{{ users|sort(attribute="age,name")|map(attribute="name")|list }}', "[1, 2, 3]|[3, 2, 1]|['A', 'b', 'c']|['A', 'b', 'c']|['Bob', 'ann', 'cy']"),
    ('{{ 5|string }}|{{ [1]|string }}|{{ md|string }}', '5|[1]|<i>safe</i>'),
    ('{{ "<p>Hello   <b>there</b>  &amp; <!-- no --> you</p>"|striptags }}', 'Hello there & you'),
    ('{{ [1, 2, 3]|sum }}|{{ [1.5, 2]|sum }}|{{ users|sum(attribute="age") }}|{{ [1, 2]|sum(start=10) }}|{{ []|sum }}', '6|3.5|85|13|0'),
    ('{{ "hello big world"|title }}|{{ "it\'s a dog-friendly (test) [x]"|title }}', "Hello Big World|It's A Dog-Friendly (Test) [X]"),
    ('{{ "  x  "|trim }}|{{ "xxaxx"|trim("x") }}', 'x|a'),
    ('{{ "short"|truncate(10) }}|{{ "a long sentence here"|truncate(12) }}|{{ "a long sentence here"|truncate(12, true) }}|{{ "a long sentence here"|truncate(12, false, "~") }}|{{ "a long sentence here"|truncate(15, leeway=10) }}', 'short|a long...|a long se...|a long~|a long sentence here'),
    ('{{ ["a", "B", "b", "a"]|unique|list }}|{{ ["a", "B", "b"]|unique(true)|list }}|{{ users|unique(attribute="age")|map(attribute="name")|list }}', "['a', 'B']|['a', 'B', 'b']|['ann', 'Bob']"),
    ('{{ "abc"|upper }}|{{ md|upper }}', 'ABC|<I>SAFE</I>'),
    ('{{ "a b/c?d=é"|urlencode }}|{{ {"a": "b c", "d": 1}|urlencode }}|{{ [("x", "y z")]|urlencode }}', 'a%20b/c%3Fd%3D%C3%A9|a=b+c&d=1|x=y+z'),
    ('{{ "one two, three"|wordcount }}', '3'),
    ('{{ "the quick brown fox jumps over"|wordwrap(10) }}|{{ "averyveryverylongword"|wordwrap(8) }}|{{ "averyverylongword"|wordwrap(8, false) }}|{{ "a b c d"|wordwrap(3, wrapstring="<br>") }}', 'the quick\nbrown fox\njumps over|averyver\nyverylon\ngword|averyverylongword|a b<br>c d'),
    ('{{ {"class": "x y", "id": 3, "none": none, "q": "<"}|xmlattr }}|{{ {"a": 1}|xmlattr(false) }}', ' class="x y" id="3" q="&lt;"|a="1"'),
    ('{{ {"a": [1, "<"], "b": none}|tojson }}|{{ [1, 2]|tojson(2) }}|{{ "</script>"|tojson }}', '{"a": [1, "\\u003c"], "b": null}|[\n  1,\n  2\n]|"\\u003c/script\\u003e"'),
    ('{{ "a-b"|replace("-", "_")|upper|trim|length }}', '3'),
]


@pytest.mark.parametrize("source, expected", CASES)
def test_filter(source, expected):
    expect(source, expected)


def test_filters_that_do_not_exist():
    expect_error("{{ 1|nosuch }}", "TemplateAssertionError", "No filter named 'nosuch'.", 1)
    expect_error("{{ [1]|map('nosuch')|list }}", "TemplateRuntimeError", "No filter named 'nosuch'.")


def test_filter_argument_errors():
    expect_error("{{ d2|dictsort(by='x') }}", "FilterArgumentError", 'You can only sort by either "key" or "value"')
    expect_error("{{ 1.5|round(method='x') }}", "FilterArgumentError", "method must be common, ceil or floor")
    expect_error("{{ '%s %s'|format(1, x=2) }}", "FilterArgumentError", "can't handle positional and keyword arguments at the same time")
    expect_error("{{ [1]|map|list }}", "FilterArgumentError", "map requires a filter argument")
    expect_error("{{ [1]|selectattr|list }}", "FilterArgumentError", "Missing parameter for attribute name")
    expect_error("{{ 5|reverse }}", "FilterArgumentError", "argument must be iterable")


def test_filters_in_blocks_and_chains():
    expect("{% filter upper|replace('A', '4') %}banana{% endfilter %}", "B4N4N4")
    expect("{% set x | upper %}abc{% endset %}{{ x }}", "ABC")
    expect("{{ 'abc'|upper|length }}|{{ 'abc'|length|string|length }}", "3|1")


def test_filter_arguments_can_be_keywords_and_unpacked():
    expect("{{ 'abcdefghijkl'|truncate(length=4, end='!') }}", "abc!")
    expect("{{ 'abc'|replace(*['a', 'x']) }}", "xbc")
    expect("{{ 'abcdefghijkl'|truncate(**{'length': 4, 'end': '!'}) }}", "abc!")
