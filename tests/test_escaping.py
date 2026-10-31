"""Escaping: autoescape on and off, ``Markup`` (what ``|safe`` makes), and which filters keep it or take it away.  Expected text from Jinja2."""
import pytest

from oracle import expect

AUTOESCAPE_OFF = [
    ('{{ u }}|{{ u|safe }}|{{ md }}|{{ u|e }}|{{ md|e }}|{{ u|forceescape }}|{{ md|forceescape }}', '<b>é&"\'</b>|<b>é&"\'</b>|<i>safe</i>|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;|<i>safe</i>|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;|&lt;i&gt;safe&lt;/i&gt;'),
    ('{{ "<" ~ md }}|{{ md ~ "<" }}|{{ "a" ~ "<" }}|{{ md ~ md }}|{{ md + "<" }}|{{ "<" + md }}', '<<i>safe</i>|<i>safe</i><|a<|<i>safe</i><i>safe</i>|<i>safe</i>&lt;|&lt;<i>safe</i>'),
    ('{{ [u, md]|join(",") }}|{{ [u, u]|join("<") }}|{{ [md, md]|join("<") }}|{{ [u, md]|join(md) }}', '<b>é&"\'</b>,<i>safe</i>|<b>é&"\'</b><<b>é&"\'</b>|<i>safe</i><<i>safe</i>|<b>é&"\'</b><i>safe</i><i>safe</i>'),
    ('{{ u|upper }}|{{ md|upper }}|{{ u|title }}|{{ md|capitalize }}|{{ u|trim }}|{{ u|truncate(5) }}|{{ u|center(20) }}', '<B>É&"\'</B>|<I>SAFE</I>|<B>é&"\'</b>|<i>safe</i>|<b>é&"\'</b>|<b...|    <b>é&"\'</b>     '),
    ('{{ u|replace("<", "(") }}|{{ md|replace("<", "(") }}|{{ md|replace("i", "<") }}|{{ u|replace("b", md) }}', '(b>é&"\'(/b>|(i>safe(/i>|<<>safe</<>|<<i>safe</i>>é&"\'</<i>safe</i>>'),
    ('{{ "%s"|format(u) }}|{{ "%s"|format(md) }}|{{ md|format() }}', '<b>é&"\'</b>|<i>safe</i>|<i>safe</i>'),
    ('{{ u|striptags }}|{{ md|striptags }}|{{ html|striptags }}', 'é&"\'|safe|Hello, World & bye'),
    ('{{ u|length }}|{{ md|length }}|{{ md|list|length }}', '11|11|11'),
    ('{{ u|urlencode }}|{{ u|wordcount }}|{{ n }}|{{ none }}|{{ 5 }}|{{ [u] }}|{{ {"k": u} }}|{{ (u,) }}', '%3Cb%3E%C3%A9%26%22%27%3C/b%3E|3|None|None|5|[\'<b>é&"\\\'</b>\']|{\'k\': \'<b>é&"\\\'</b>\'}|(\'<b>é&"\\\'</b>\',)'),
    ('{{ nosuch }}|{{ nosuch|e }}|{{ nosuch|default(u) }}|{{ nosuch|default(md) }}', '||<b>é&"\'</b>|<i>safe</i>'),
    ('{% set s = u %}{{ s }}|{% set m = u|safe %}{{ m }}|{% set blk %}{{ u }}<b>{% endset %}{{ blk }}|{{ blk|e }}', '<b>é&"\'</b>|<b>é&"\'</b>|<b>é&"\'</b><b>|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;&lt;b&gt;'),
    ('{% macro mac(x) %}<m>{{ x }}</m>{% endmacro %}{{ mac(u) }}|{{ mac(md) }}|{{ mac("a")|e }}|{{ (mac("a")|string) is escaped }}', '<m><b>é&"\'</b></m>|<m><i>safe</i></m>|&lt;m&gt;a&lt;/m&gt;|False'),
    ('{% for i in [u, md] %}{{ i }}{% endfor %}|{% filter upper %}{{ u }}{% endfilter %}|{% filter e %}<{% endfilter %}', '<b>é&"\'</b><i>safe</i>|<B>É&"\'</B>|&lt;'),
    ('{{ u if T else md }}|{{ (u, md)[1] }}|{{ {"a": md}.a }}|{{ [u][0] }}', '<b>é&"\'</b>|<i>safe</i>|<i>safe</i>|<b>é&"\'</b>'),
    ('{{ {"a": "<", "b": md}|xmlattr }}|{{ {"a": "<"}|xmlattr(false) }}|{{ [u]|tojson }}|{{ u|tojson }}', ' a="&lt;" b="<i>safe</i>"|a="&lt;"|["\\u003cb\\u003e\\u00e9\\u0026\\"\\u0027\\u003c/b\\u003e"]|"\\u003cb\\u003e\\u00e9\\u0026\\"\\u0027\\u003c/b\\u003e"'),
    ('{% autoescape false %}{{ u }}{% endautoescape %}|{% autoescape true %}{{ u }}{% endautoescape %}|{% autoescape c %}{{ u }}{% endautoescape %}|{% autoescape a %}{{ u }}{% endautoescape %}', '<b>é&"\'</b>|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;|<b>é&"\'</b>|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;'),
    ('{% raw %}<&>{% endraw %}|<&>|{{ "<&>" }}|{# <&> #}', '<&>|<&>|<&>|'),
    ('{{ (u|safe) is escaped }}|{{ u is escaped }}|{{ md is escaped }}|{{ u|e is escaped }}', 'True|False|True|True'),
    ('{% for x in tree recursive %}{{ x.name }}{{ loop(x.children) }}{% endfor %}|{% for x in [u] recursive %}{{ x }}{{ loop([]) }}{% endfor %}', 'rc1c2g|<b>é&"\'</b>'),
    ('{{ self }}|{{ cycler(u, md).next() }}|{% set j = joiner(u) %}{{ j() }}{{ j() }}', '<TemplateReference None>|<b>é&"\'</b>|<b>é&"\'</b>'),
]

AUTOESCAPE_ON = [
    ('{{ u }}|{{ u|safe }}|{{ md }}|{{ u|e }}|{{ md|e }}|{{ u|forceescape }}|{{ md|forceescape }}', '&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;|<b>é&"\'</b>|<i>safe</i>|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;|<i>safe</i>|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;|&lt;i&gt;safe&lt;/i&gt;'),
    ('{{ "<" ~ md }}|{{ md ~ "<" }}|{{ "a" ~ "<" }}|{{ md ~ md }}|{{ md + "<" }}|{{ "<" + md }}', '&lt;<i>safe</i>|<i>safe</i>&lt;|a&lt;|<i>safe</i><i>safe</i>|<i>safe</i>&lt;|&lt;<i>safe</i>'),
    ('{{ [u, md]|join(",") }}|{{ [u, u]|join("<") }}|{{ [md, md]|join("<") }}|{{ [u, md]|join(md) }}', '&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;,<i>safe</i>|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;&lt;&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;|<i>safe</i>&lt;<i>safe</i>|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;<i>safe</i><i>safe</i>'),
    ('{{ u|upper }}|{{ md|upper }}|{{ u|title }}|{{ md|capitalize }}|{{ u|trim }}|{{ u|truncate(5) }}|{{ u|center(20) }}', '&lt;B&gt;É&amp;&#34;&#39;&lt;/B&gt;|<I>SAFE</I>|&lt;B&gt;é&amp;&#34;&#39;&lt;/b&gt;|<i>safe</i>|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;|&lt;b...|    &lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;     '),
    ('{{ u|replace("<", "(") }}|{{ md|replace("<", "(") }}|{{ md|replace("i", "<") }}|{{ u|replace("b", md) }}', '(b&gt;é&amp;&#34;&#39;(/b&gt;|(i>safe(/i>|<&lt;>safe</&lt;>|&lt;<i>safe</i>&gt;é&amp;&#34;&#39;&lt;/<i>safe</i>&gt;'),
    ('{{ "%s"|format(u) }}|{{ "%s"|format(md) }}|{{ md|format() }}', '&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;|&lt;i&gt;safe&lt;/i&gt;|<i>safe</i>'),
    ('{{ u|striptags }}|{{ md|striptags }}|{{ html|striptags }}', 'é&amp;&#34;&#39;|safe|Hello, World &amp; bye'),
    ('{{ u|length }}|{{ md|length }}|{{ md|list|length }}', '11|11|11'),
    ('{{ u|urlencode }}|{{ u|wordcount }}|{{ n }}|{{ none }}|{{ 5 }}|{{ [u] }}|{{ {"k": u} }}|{{ (u,) }}', '%3Cb%3E%C3%A9%26%22%27%3C/b%3E|3|None|None|5|[&#39;&lt;b&gt;é&amp;&#34;\\&#39;&lt;/b&gt;&#39;]|{&#39;k&#39;: &#39;&lt;b&gt;é&amp;&#34;\\&#39;&lt;/b&gt;&#39;}|(&#39;&lt;b&gt;é&amp;&#34;\\&#39;&lt;/b&gt;&#39;,)'),
    ('{{ nosuch }}|{{ nosuch|e }}|{{ nosuch|default(u) }}|{{ nosuch|default(md) }}', '||&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;|<i>safe</i>'),
    ('{% set s = u %}{{ s }}|{% set m = u|safe %}{{ m }}|{% set blk %}{{ u }}<b>{% endset %}{{ blk }}|{{ blk|e }}', '&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;|<b>é&"\'</b>|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;<b>|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;<b>'),
    ('{% macro mac(x) %}<m>{{ x }}</m>{% endmacro %}{{ mac(u) }}|{{ mac(md) }}|{{ mac("a")|e }}|{{ (mac("a")|string) is escaped }}', '<m>&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;</m>|<m><i>safe</i></m>|<m>a</m>|True'),
    ('{% for i in [u, md] %}{{ i }}{% endfor %}|{% filter upper %}{{ u }}{% endfilter %}|{% filter e %}<{% endfilter %}', '&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;<i>safe</i>|&LT;B&GT;É&AMP;&#34;&#39;&LT;/B&GT;|<'),
    ('{{ u if T else md }}|{{ (u, md)[1] }}|{{ {"a": md}.a }}|{{ [u][0] }}', '&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;|<i>safe</i>|<i>safe</i>|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;'),
    ('{{ {"a": "<", "b": md}|xmlattr }}|{{ {"a": "<"}|xmlattr(false) }}|{{ [u]|tojson }}|{{ u|tojson }}', ' a="&lt;" b="<i>safe</i>"|a="&lt;"|["\\u003cb\\u003e\\u00e9\\u0026\\"\\u0027\\u003c/b\\u003e"]|"\\u003cb\\u003e\\u00e9\\u0026\\"\\u0027\\u003c/b\\u003e"'),
    ('{% autoescape false %}{{ u }}{% endautoescape %}|{% autoescape true %}{{ u }}{% endautoescape %}|{% autoescape c %}{{ u }}{% endautoescape %}|{% autoescape a %}{{ u }}{% endautoescape %}', '<b>é&"\'</b>|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;|<b>é&"\'</b>|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;'),
    ('{% raw %}<&>{% endraw %}|<&>|{{ "<&>" }}|{# <&> #}', '<&>|<&>|&lt;&amp;&gt;|'),
    ('{{ (u|safe) is escaped }}|{{ u is escaped }}|{{ md is escaped }}|{{ u|e is escaped }}', 'True|False|True|True'),
    ('{% for x in tree recursive %}{{ x.name }}{{ loop(x.children) }}{% endfor %}|{% for x in [u] recursive %}{{ x }}{{ loop([]) }}{% endfor %}', 'rc1c2g|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;'),
    ('{{ self }}|{{ cycler(u, md).next() }}|{% set j = joiner(u) %}{{ j() }}{{ j() }}', '&lt;TemplateReference None&gt;|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;|&lt;b&gt;é&amp;&#34;&#39;&lt;/b&gt;'),
]


@pytest.mark.parametrize("source, expected", AUTOESCAPE_OFF)
def test_autoescape_off(source, expected):
    expect(source, expected)


@pytest.mark.parametrize("source, expected", AUTOESCAPE_ON)
def test_autoescape_on(source, expected):
    expect(source, expected, options={"autoescape": True})


def test_autoescape_can_depend_on_the_name_of_the_template():
    import kendi_sablon as ks
    env = ks.Environment(loader=ks.DictLoader({"a.html": "{{ '<' }}", "a.txt": "{{ '<' }}", "a.xml": "{{ '<' }}"}), autoescape=ks.select_autoescape())
    assert env.get_template("a.html").render() == "&lt;"
    assert env.get_template("a.xml").render() == "&lt;"
    assert env.get_template("a.txt").render() == "<"
    assert env.from_string("{{ '<' }}").render() == "&lt;"            # a template from a string has no name: the default for strings is True
    env2 = ks.Environment(autoescape=ks.select_autoescape(default_for_string=False))
    assert env2.from_string("{{ '<' }}").render() == "<"


def test_autoescape_can_be_a_function():
    import kendi_sablon as ks
    env = ks.Environment(loader=ks.DictLoader({"yes": "{{ '<' }}", "no": "{{ '<' }}"}), autoescape=lambda name: name == "yes")
    assert env.get_template("yes").render() == "&lt;"
    assert env.get_template("no").render() == "<"


def test_a_block_whose_autoescape_option_is_a_variable_does_not_make_markup_with_the_tilde():
    # Jinja2 asks the wrong flag there: the join of ``~`` is a plain string join, so the result is escaped as a whole when it is printed
    source = "{% autoescape a %}{{ s ~ md }}|{{ md ~ md }}{% endautoescape %}|{% autoescape true %}{{ s ~ md }}|{{ md ~ md }}{% endautoescape %}"
    expect(source, "hello world&lt;i&gt;safe&lt;/i&gt;|&lt;i&gt;safe&lt;/i&gt;&lt;i&gt;safe&lt;/i&gt;|hello world<i>safe</i>|<i>safe</i><i>safe</i>")
