"""The lexing of the source: delimiters, comments, raw blocks, whitespace control, the options trim_blocks and lstrip_blocks, line breaks, literals."""
import pytest

from oracle import expect, expect_error

TRIM = {"trim_blocks": True}
LSTRIP = {"lstrip_blocks": True}
BOTH = {"trim_blocks": True, "lstrip_blocks": True}


def test_plain_text_is_copied():
    expect("just text, no tags", "just text, no tags")
    expect("", "")
    expect("{ { } } { % % } { #", "{ { } } { % % } { #")


def test_variable_tags_print_str_of_the_value():
    expect("{{ 1 }}|{{ 1.5 }}|{{ 'a' }}|{{ none }}|{{ true }}|{{ [1, 'a'] }}|{{ (1, 2) }}|{{ {'a': 1} }}", "1|1.5|a|None|True|[1, 'a']|(1, 2)|{'a': 1}")


def test_comments_vanish():
    expect("a{# hidden {{ x }} {% if %} #}b", "ab")
    expect("a{#}b#}c", "ac")
    expect("{# multi\nline #}x", "x")


def test_minus_strips_all_whitespace_on_that_side():
    expect("a  \n {%- if true -%}  \n b  \n {%- endif -%} \n c", "abc")
    expect("a  {{- 'x' -}}  b", "axb")
    expect("a  {#- c -#}  b", "ab")


def test_minus_only_strips_on_its_side():
    expect("a  {{- 'x' }}  b", "ax  b")
    expect("a  {{ 'x' -}}  b", "a  xb")


def test_plus_cancels_lstrip_and_trim_blocks():
    expect("a\n  {%+ if true %}x{% endif %}", "a\n  x", options=LSTRIP)
    expect("{% if true +%}\nx{% endif %}", "\nx", options=TRIM)


def test_trim_blocks_removes_the_newline_after_a_block_tag_only():
    expect("{% if true %}\nx\n{% endif %}\ny", "x\ny", options=TRIM)
    expect("{{ 1 }}\nx", "1\nx", options=TRIM)
    expect("{# c #}\nx", "x", options=TRIM)


def test_lstrip_blocks_strips_indentation_before_a_block_tag():
    expect("a\n    {% if true %}\n    x\n    {% endif %}\nb", "a\n\n    x\n\nb", options=LSTRIP)
    expect("a    {% if true %}x{% endif %}", "a    x", options=LSTRIP)          # not at the start of a line: kept
    expect("a\n    {{ 1 }}", "a\n    1", options=LSTRIP)                         # a print is not a block


def test_both_options_make_block_lines_disappear():
    expect("a\n  {% if true %}\n  x\n  {% endif %}\nb", "a\n  x\nb", options=BOTH)


def test_line_breaks_are_normalized():
    expect("a\r\nb\rc\nd", "a\nb\nc\nd")
    expect("a\r\nb", "a\r\nb", options={"newline_sequence": "\r\n"})


def test_the_last_line_break_is_dropped_unless_asked_for():
    expect("a\n", "a")
    expect("a\n\n", "a\n")
    expect("a\n", "a\n", options={"keep_trailing_newline": True})
    expect("{{ 1 }}\n", "1")


def test_raw_blocks():
    expect("{% raw %}{{ a }} {% if %}{% endraw %}", "{{ a }} {% if %}")
    expect("a {%- raw -%} {{ b }} {%- endraw -%} c", "a{{ b }}c")
    expect("{% raw %}{% raw %}{% endraw %}", "{% raw %}")


def test_custom_delimiters():
    options = {"block_start_string": "<%", "block_end_string": "%>", "variable_start_string": "${", "variable_end_string": "}",
               "comment_start_string": "<#", "comment_end_string": "#>"}
    expect("<% if true %>${ 1 + 1 }<# c #>{{ x }}<% endif %>", "2{{ x }}", options=options)


def test_string_literals_and_escapes():
    expect(r"{{ 'it\'s' }}|{{ 'a\tb' }}|{{ '\x41é' }}|{{ 'a' 'b' }}", "it's|a\tb|Aé|ab")
    expect("{{ 'a\nb' }}", "a\nb")


def test_number_literals():
    expect("{{ 0x1f }} {{ 0b101 }} {{ 0o17 }} {{ 1_000 }} {{ 1e3 }} {{ 1.5e-2 }}", "31 5 15 1000 1000.0 0.015")


def test_a_number_followed_by_a_dot_is_not_a_float():
    expect("{{ 3.real }}", "3")           # the integer 3, then the attribute real
    expect_error("{{ 3. }}", "TemplateSyntaxError", "expected name or number", 1)


def test_unicode_names():
    expect("{{ é }}|{{ é is defined }}", "|False")


@pytest.mark.parametrize("source, message, lineno", [
    ("{{ a", "unexpected end of template, expected 'end of print statement'.", 1),
    ("{% if x %}", "Unexpected end of template. Jinja was looking for the following tags: 'elif' or 'else' or 'endif'. The innermost block that needs to be closed is 'if'.", 1),
    ("a\n{# open", "Missing end of comment tag", 2),
    ("{% raw %} x", "Missing end of raw directive", 1),
    ("{{ 'abc }}", "unexpected char \"'\" at 3", 1),
    ("{{ @ }}", "unexpected char '@' at 3", 1),
    ("{{ a) }}", "unexpected ')'", 1),
    ("{{ (a] }}", "unexpected ']', expected ')'", 1),
    ("\n\n{{ ( }}", "unexpected '}', expected ')'", 3),
    ("{% foo %}", "Encountered unknown tag 'foo'.", 1),
    ("{% endif %}", "Encountered unknown tag 'endif'.", 1),
    ("{% if a %}{% endfor %}", "Encountered unknown tag 'endfor'. Jinja was looking for the following tags: 'elif' or 'else' or 'endif'. The innermost block that needs to be closed is 'if'.", 1),
    ("{% for i in x %}{% if a %}{% endfor %}", "Encountered unknown tag 'endfor'. You probably made a nesting mistake. Jinja is expecting this tag, but currently looking for 'elif' or 'else' or 'endif'. The innermost block that needs to be closed is 'if'.", 1),
])
def test_syntax_errors(source, message, lineno):
    expect_error(source, "TemplateSyntaxError", message, lineno)
