"""The Python side: Template, Environment, custom filters / tests / globals, the pass_* decorators, modules, error positions, Markup."""
import pytest

import kendi_sablon as ks
from kendi_sablon import nodes


def test_template_from_a_string():
    assert ks.Template("Hello {{ name }}!").render(name="World") == "Hello World!"
    assert ks.Template("{{ a }}{{ b }}").render({"a": 1}, b=2) == "12"
    assert ks.Template("x", keep_trailing_newline=True).render() == "x"
    assert ks.Template("{{ '<' }}", autoescape=True).render() == "&lt;"


def test_custom_filter_test_and_global():
    env = ks.Environment()
    env.filters["shout"] = lambda s, suffix="!": s.upper() + suffix
    env.tests["short"] = lambda s, n=3: len(s) <= n
    env.globals["answer"] = 42
    env.globals["twice"] = lambda x: x * 2
    t = env.from_string("{{ 'hi'|shout }}{{ 'hi'|shout('?') }} {{ 'abcd' is short }} {{ 'abcd' is short(5) }} {{ answer }} {{ twice(answer) }}")
    assert t.render() == "HI!HI? False True 42 84"


def test_a_filter_that_is_added_later_is_seen_by_templates_compiled_after_it():
    env = ks.Environment()
    with pytest.raises(ks.TemplateAssertionError):
        env.from_string("{{ 1|late }}")
    env.filters["late"] = str
    assert env.from_string("{{ 1|late }}").render() == "1"


def test_pass_context_pass_environment_pass_eval_context():
    seen = {}

    @ks.pass_context
    def with_context(context, x):
        seen["context"] = context
        return "%s:%s" % (x, context["name"])

    @ks.pass_environment
    def with_env(environment, x):
        seen["env"] = environment
        return x

    @ks.pass_eval_context
    def with_eval(eval_ctx, x):
        return "%s:%s" % (x, eval_ctx.autoescape)

    env = ks.Environment()
    env.filters.update(ctx=with_context, env=with_env, ev=with_eval)
    env.globals.update(cfn=with_context, efn=with_eval)
    env.tests["ctxtest"] = ks.pass_context(lambda context, v: context["name"] == v)
    t = env.from_string("{{ 1|ctx }} {{ 2|env }} {{ 3|ev }} {{ cfn(4) }} {{ efn(5) }} {{ 'bob' is ctxtest }}")
    assert t.render(name="bob") == "1:bob 2 3:False 4:bob 5:False True"
    assert seen["env"] is env


def test_a_context_function_sees_the_variables_of_a_loop():
    @ks.pass_context
    def names(context):
        return sorted(k for k in context.keys() if k in ("i", "outer", "name"))

    env = ks.Environment()
    env.globals["names"] = names
    assert env.from_string("{% set outer = 1 %}{% for i in [1] %}{{ names() }}{% endfor %}").render(name="n") == "['i', 'name', 'outer']"


def test_calling_a_callable_object_that_wants_the_context():
    class Greeter:
        @ks.pass_context
        def __call__(self, context, greeting):
            return "%s %s" % (greeting, context["who"])

    env = ks.Environment()
    env.globals["greet"] = Greeter()
    assert env.from_string("{{ greet('hi') }}").render(who="you") == "hi you"


def test_a_callable_that_raises_stop_iteration_gives_an_undefined_value():
    def stop():
        raise StopIteration

    assert ks.Template("[{{ f() }}]").render(f=stop) == "[]"


def test_parse_gives_the_syntax_tree():
    env = ks.Environment()
    tree = env.parse("{% if a %}x{{ b|upper }}{% endif %}")
    assert isinstance(tree, nodes.Template)
    if_node = tree.body[0]
    assert isinstance(if_node, nodes.If) and isinstance(if_node.test, nodes.Name) and if_node.test.name == "a"
    output = if_node.body[0]
    assert isinstance(output, nodes.Output)
    assert isinstance(output.nodes[0], nodes.TemplateData) and output.nodes[0].data == "x"
    assert isinstance(output.nodes[1], nodes.Filter) and output.nodes[1].name == "upper"
    assert [type(n).__name__ for n in tree.find_all(nodes.Name)] == ["Name", "Name"]


def test_syntax_error_has_message_line_and_name():
    env = ks.Environment(loader=ks.DictLoader({"bad.html": "line one\n{% if %}\n"}))
    with pytest.raises(ks.TemplateSyntaxError) as info:
        env.get_template("bad.html")
    error = info.value
    assert error.lineno == 2 and error.name == "bad.html" and error.message == "Expected an expression, got 'end of statement block'"
    assert 'line 2' in str(error) and "{% if %}" in str(error)


def test_runtime_errors_say_where_in_the_template_they_happened():
    env = ks.Environment(loader=ks.DictLoader({"t.txt": "one\n{{ 1 }}\n{% for i in [1] %}\n  {{ i / 0 }}\n{% endfor %}"}))
    with pytest.raises(ZeroDivisionError) as info:
        env.get_template("t.txt").render()
    assert info.value.template_name == "t.txt" and info.value.template_lineno == 4
    try:
        env.from_string("a\n{{ nosuch.x }}").render()
    except ks.UndefinedError as error:
        assert error.template_lineno == 2 and error.template_name is None


def test_template_module_exports_macros_and_variables():
    env = ks.Environment(loader=ks.DictLoader({"m": "{% macro hi(n) %}hi {{ n }}{% endmacro %}{% set v = 5 %}{% set _hidden = 1 %}text"}))
    module = env.get_template("m").module
    assert module.hi("bob") == "hi bob" and module.v == 5 and not hasattr(module, "_hidden")
    assert str(module) == "text"
    assert env.get_template("m").module is module                # made once
    assert "m" in repr(module)


def test_environment_getattr_and_getitem_can_be_overridden():
    class Lowercase(ks.Environment):
        def getattr(self, obj, attribute):
            return super().getattr(obj, attribute.lower())

    assert Lowercase().from_string("{{ d.KEY }}").render(d={"key": 1}) == "1"


def test_undefined_classes_in_python():
    u = ks.Undefined(name="x")
    assert str(u) == "" and not u and list(u) == [] and len(u) == 0 and u == ks.Undefined() and repr(u) == "Undefined"
    with pytest.raises(ks.UndefinedError, match="'x' is undefined"):
        u + 1
    with pytest.raises(ks.UndefinedError):
        u.attr
    assert ks.DebugUndefined(name="x").__str__() == "{{ x }}"
    strict = ks.StrictUndefined(name="x")
    for use in (str, bool, len, list, lambda v: v == 1, lambda v: 1 in v):
        with pytest.raises(ks.UndefinedError):
            use(strict)
    assert str(ks.ChainableUndefined(name="x").a.b["c"]) == ""
    with pytest.raises(AttributeError):
        u.__nosuchdunder__                                          # Python's own probing (copy, pickle) is not answered with an undefined value


def test_environment_checks_its_settings():
    with pytest.raises(AssertionError):
        ks.Environment(block_start_string="{{")
    with pytest.raises(ValueError):
        ks.Environment(newline_sequence="x")
    with pytest.raises(AssertionError):
        ks.Environment(undefined=dict)


def test_namespace_cycler_joiner():
    ns = ks.Namespace(a=1)
    ns["b"] = 2
    assert ns.a == 1 and ns.b == 2 and "a" in repr(ns)
    with pytest.raises(AttributeError):
        ns.c
    from kendi_sablon.utils import Cycler, Joiner
    c = Cycler(1, 2, 3)
    assert [c.next() for _ in range(4)] == [1, 2, 3, 1] and c.current == 2
    c.reset()
    assert c.current == 1
    with pytest.raises(RuntimeError):
        Cycler()
    j = Joiner("|")
    assert [j(), j(), j()] == ["", "|", "|"]


def test_exceptions_hierarchy():
    assert issubclass(ks.TemplateNotFound, LookupError) and issubclass(ks.TemplateNotFound, ks.TemplateError)
    assert issubclass(ks.TemplateAssertionError, ks.TemplateSyntaxError)
    assert issubclass(ks.UndefinedError, ks.TemplateRuntimeError)
    assert issubclass(ks.TemplatesNotFound, ks.TemplateNotFound)


def test_render_is_repeatable_and_independent():
    t = ks.Template("{% set n = n + 1 %}{{ n }}")
    assert t.render(n=1) == "2" and t.render(n=1) == "2" and t.render(n=10) == "11"
    data = {"items": [1, 2]}
    assert ks.Template("{% set _ = items.append(3) %}{{ items }}").render(data) == "[1, 2, 3]"
