"""Templates that use other templates: extends / block / super, include, import, from ... import."""
import pytest

from oracle import expect, expect_error

T = {
    "base.html": "<html>{% block head %}<title>{% block title %}Base{% endblock %}</title>{% endblock %}|{% block body %}base body{% endblock %}|{% block footer %}(c){% endblock %}</html>",
    "child.html": "{% extends 'base.html' %}{% block title %}Child - {{ super() }}{% endblock %}{% block body %}[{{ self.title() }}] {{ page }}{% endblock %}",
    "grandchild.html": "{% extends 'child.html' %}{% block body %}<{{ super() }}>{% endblock %}{% block footer %}{{ super() }}!{% endblock %}",
    "macros.html": "{% macro field(name, value='') %}<input name='{{ name }}' value='{{ value }}'>{% endmacro %}{% macro twice(x) %}{{ x }}{{ x }}{% endmacro %}"
                   "{% set version = '1.0' %}{% set _private = 'p' %}",
    "greeting.txt": "Hello {{ name|default('stranger') }}{% set leaked = 1 %}",
    "ctx.txt": "[{{ a }}|{{ v|default('nov') }}|{{ i|default('noi') }}]",
    "loopblocks": "{% for i in items %}{% block item scoped %}{{ i }}{% endblock %}{% endfor %}",
    "loopchild": "{% extends 'loopblocks' %}{% block item %}<{{ i }}>{% endblock %}",
    "required_base": "{% block content required %}{% endblock %}",
    "required_ok": "{% extends 'required_base' %}{% block content %}filled{% endblock %}",
    "bad": "{% if %}",
}

RENDERED = [
    ("child.html", {"page": "P"}, "<html><title>Child - Base</title>|[Child - Base] P|(c)</html>"),
    ("grandchild.html", {"page": "G"}, "<html><title>Child - Base</title>|<[Child - Base] G>|(c)!</html>"),
    ("{% extends 'base.html' %}{% block body %}inline{% endblock %}", {}, "<html><title>Base</title>|inline|(c)</html>"),
    ("{% include 'greeting.txt' %}|{{ leaked }}", {"name": "Ann"}, "Hello Ann|"),
    ("{% include 'greeting.txt' %}", {}, "Hello stranger"),
    ("{% set name = 'Local' %}{% include 'greeting.txt' %}", {}, "Hello Local"),
    ("{% include 'greeting.txt' without context %}", {"name": "Ann"}, "Hello stranger"),
    ("{% for v in [1, 2] %}{% include 'ctx.txt' %}{% endfor %}", {"a": 1}, "[1|1|noi][1|2|noi]"),
    ("{% for v in [1, 2] %}{% include 'ctx.txt' without context %}{% endfor %}", {"a": 1}, "[|nov|noi][|nov|noi]"),
    ("{% include 'nosuch' ignore missing %}after", {}, "after"),
    ("{% include ['nosuch', 'greeting.txt'] %}", {}, "Hello stranger"),
    ("{% import 'macros.html' as m %}{{ m.field('n', 'v') }}{{ m.twice('ab') }}{{ m.version }}|{{ m._private is defined }}", {}, "<input name='n' value='v'>abab1.0|False"),
    ("{% from 'macros.html' import field, twice as tw, version %}{{ field('x') }}{{ tw(3) }}{{ version }}", {}, "<input name='x' value=''>331.0"),
    ("{% from 'macros.html' import nosuch %}{{ nosuch }}|{{ nosuch is defined }}", {}, "|False"),
    ("{% import 'macros.html' as m %}{{ m }}|{{ m.nosuch }}", {}, "|"),
    ("{% import 'greeting.txt' as g with context %}{{ g.leaked }}[{{ g }}]", {"name": "Ann"}, "1[Hello Ann]"),
    ("{% import 'greeting.txt' as g %}[{{ g }}]", {"name": "Ann"}, "[Hello stranger]"),
    ("loopchild", {"items": [1, 2]}, "<1><2>"),
    ("required_ok", {}, "filled"),
    ("{% extends 'base.html' %}{% block nosuch %}x{% endblock %}", {}, "<html><title>Base</title>|base body|(c)</html>"),
    ("{% set layout = 'base.html' %}{% extends layout %}{% block body %}dyn{% endblock %}", {}, "<html><title>Base</title>|dyn|(c)</html>"),
    ("pre {% extends 'base.html' %} ignored {% block body %}b{% endblock %} ignored", {}, "pre <html><title>Base</title>|b|(c)</html>"),
    ("{% extends 'base.html' %}{% block title %}{{ super() }}{{ super.super is defined }}{% endblock %}", {}, "<html><title>BaseFalse</title>|base body|(c)</html>"),
    ("{% set v = 5 %}{% extends 'ctx.txt' %}", {}, "[|5|noi]"),
]


def render_by_name_or_source(source, ctx, expected):
    name = source if source in T else None
    expect(None if name else source, expected, context=lambda lib: ctx, templates=T, name=name)


@pytest.mark.parametrize("source, ctx, expected", RENDERED)
def test_rendered(source, ctx, expected):
    render_by_name_or_source(source, ctx, expected)


ERRORS = [
    ("{% include 'bad' %}", "TemplateSyntaxError", "Expected an expression, got 'end of statement block'", 1),
    ("required_base", "TemplateRuntimeError", "Required block 'content' not found", None),
    ("{% extends 'nosuch' %}", "TemplateNotFound", "nosuch", None),
    ("{% include 'nosuch' %}", "TemplateNotFound", "nosuch", None),
    ("{% include ['a', 'b'] %}", "TemplatesNotFound", "none of the templates given were found: a, b", None),
    ("{% extends 'base.html' %}{% extends 'base.html' %}", "TemplateRuntimeError", "extended multiple times", None),
    ("{% extends ['nosuch', 'base.html'] %}", "TypeError", "unhashable type: 'list'", None),
    ("{% block a %}1{% endblock %}{% block a %}2{% endblock %}", "TemplateAssertionError", "block 'a' defined twice", 1),
    ("{% block x %}{{ super() }}{% endblock %}", "UndefinedError", "there is no parent block called 'x'.", None),
    ("{% for i in [1] %}{% extends 'base.html' %}{% endfor %}", "TemplateAssertionError", "cannot use extend from a non top-level scope", 1),
    ("{% from 'macros.html' import _private %}", "TemplateAssertionError", "names starting with an underline can not be imported", 1),
    ("{% block b-c %}{% endblock %}", "TemplateSyntaxError", "Block names in Jinja have to be valid Python identifiers and may not contain hyphens, use an underscore instead.", 1),
    ("{% block b required %}text{% endblock %}", "TemplateSyntaxError", "Required blocks can only contain comments or whitespace", 1),
]


@pytest.mark.parametrize("source, error, message, lineno", ERRORS)
def test_errors(source, error, message, lineno):
    name = source if source in T else None
    expect_error(None if name else source, error, message, lineno, templates=T, name=name)


def test_output_outside_blocks_of_a_child_is_dropped_but_output_before_extends_is_kept():
    expect("{% extends 'base.html' %}text{{ 1 }}{% block body %}b{% endblock %}", "<html><title>Base</title>|b|(c)</html>", templates=T)
    expect("before{% extends 'base.html' %}", "before<html><title>Base</title>|base body|(c)</html>", templates=T)


def test_set_in_child_is_visible_in_the_parent():
    t = dict(T, parent="{{ title }}|{% block b %}{% endblock %}", child="{% extends 'parent' %}{% set title = 'T' %}{% block b %}{{ title }}{% endblock %}")
    expect(None, "T|T", templates=t, name="child")


def test_blocks_do_not_see_the_loop_variables_unless_scoped():
    t = {"p": "{% for i in [1, 2] %}{% block b %}{{ i|default('-') }}{% endblock %}{% endfor %}|{% for i in [1, 2] %}{% block s scoped %}{{ i|default('-') }}{% endblock %}{% endfor %}",
         "c": "{% extends 'p' %}"}
    expect(None, "--|12", templates=t, name="p")
    expect(None, "--|12", templates=t, name="c")


def test_included_template_gets_the_loop_variable_only_if_the_loop_mentions_loop():
    t = {"item": "<{{ x }}|{{ loop is defined }}>"}
    expect("{% for x in 'ab' %}{% include 'item' %}{% endfor %}", "<a|False><b|False>", templates=t)
    expect("{% for x in 'ab' %}{{ loop.index }}{% include 'item' %}{% endfor %}", "1<a|True>2<b|True>", templates=t)
