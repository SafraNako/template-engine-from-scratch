"""Loaders, the cache of compiled templates, and the names of templates that must not leave their folder."""
import os
import time

import pytest

import kendi_sablon as ks
from kendi_sablon.loaders import split_template_path


def test_dict_loader():
    env = ks.Environment(loader=ks.DictLoader({"a": "A{{ x }}", "b": "{% include 'a' %}B"}))
    assert env.get_template("a").render(x=1) == "A1"
    assert env.get_template("b").render(x=2) == "A2B"
    with pytest.raises(ks.TemplateNotFound) as info:
        env.get_template("c")
    assert str(info.value) == "c" and info.value.name == "c"
    assert env.list_templates() == ["a", "b"]


def test_file_system_loader(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "page.html").write_text("page {{ x }}{% include 'sub/part.html' %}", encoding="utf-8")
    (tmp_path / "sub" / "part.html").write_text(" part é", encoding="utf-8")
    env = ks.Environment(loader=ks.FileSystemLoader(str(tmp_path)))
    template = env.get_template("page.html")
    assert template.render(x=1) == "page 1 part é"
    assert template.filename == os.path.join(str(tmp_path), "page.html")
    assert env.list_templates() == ["page.html", "sub/part.html"]
    with pytest.raises(ks.TemplateNotFound):
        env.get_template("nosuch.html")


def test_file_system_loader_searches_several_folders_in_order(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    (tmp_path / "one" / "a").write_text("one", encoding="utf-8")
    (tmp_path / "two" / "a").write_text("two", encoding="utf-8")
    (tmp_path / "two" / "b").write_text("only two", encoding="utf-8")
    env = ks.Environment(loader=ks.FileSystemLoader([str(tmp_path / "one"), str(tmp_path / "two")]))
    assert env.get_template("a").render() == "one"
    assert env.get_template("b").render() == "only two"


@pytest.mark.parametrize("name", ["../secret", "a/../../secret", "/etc/passwd", "a/../..", ".."])
def test_a_template_name_cannot_leave_the_folder(tmp_path, name):
    (tmp_path / "inside").mkdir()
    (tmp_path / "secret").write_text("secret", encoding="utf-8")
    env = ks.Environment(loader=ks.FileSystemLoader(str(tmp_path / "inside")))
    with pytest.raises(ks.TemplateNotFound):
        env.get_template(name)


def test_split_template_path():
    assert split_template_path("a/b/c.html") == ["a", "b", "c.html"]
    assert split_template_path("./a//b/./c") == ["a", "b", "c"]
    with pytest.raises(ks.TemplateNotFound):
        split_template_path("a/../b")
    with pytest.raises(ks.TemplateNotFound):
        split_template_path("a\\..\\b" if os.path.sep == "\\" else "a/..")


def test_the_template_is_reloaded_when_the_file_changes(tmp_path):
    path = tmp_path / "t"
    path.write_text("one", encoding="utf-8")
    env = ks.Environment(loader=ks.FileSystemLoader(str(tmp_path)))
    first = env.get_template("t")
    assert env.get_template("t") is first                       # cached
    assert first.render() == "one"
    time.sleep(0.01)
    path.write_text("two", encoding="utf-8")
    os.utime(path, (time.time() + 5, time.time() + 5))
    second = env.get_template("t")
    assert second is not first and second.render() == "two"


def test_auto_reload_off_keeps_the_old_template(tmp_path):
    path = tmp_path / "t"
    path.write_text("one", encoding="utf-8")
    env = ks.Environment(loader=ks.FileSystemLoader(str(tmp_path)), auto_reload=False)
    first = env.get_template("t")
    path.write_text("two", encoding="utf-8")
    os.utime(path, (time.time() + 5, time.time() + 5))
    assert env.get_template("t") is first


def test_cache_size():
    loader = ks.DictLoader({str(i): str(i) for i in range(5)})
    env = ks.Environment(loader=loader, cache_size=2)
    a = env.get_template("0")
    env.get_template("1")
    assert env.get_template("0") is a
    env.get_template("2")                                       # forgets "1", the one that was used the longest ago
    assert env.get_template("0") is a
    assert len(env.cache) == 2
    nocache = ks.Environment(loader=loader, cache_size=0)
    assert nocache.get_template("0") is not nocache.get_template("0")


def test_choice_prefix_and_function_loaders():
    choice = ks.ChoiceLoader([ks.DictLoader({"a": "first"}), ks.DictLoader({"a": "second", "b": "only second"})])
    env = ks.Environment(loader=choice)
    assert env.get_template("a").render() == "first"
    assert env.get_template("b").render() == "only second"
    assert env.list_templates() == ["a", "b"]
    prefix = ks.PrefixLoader({"x": ks.DictLoader({"a": "x-a"}), "y": ks.DictLoader({"a": "y-a"})})
    env = ks.Environment(loader=prefix)
    assert env.get_template("x/a").render() == "x-a" and env.get_template("y/a").render() == "y-a"
    with pytest.raises(ks.TemplateNotFound):
        env.get_template("z/a")
    with pytest.raises(ks.TemplateNotFound):
        env.get_template("a")
    func = ks.FunctionLoader(lambda name: "hi " + name if name != "no" else None)
    env = ks.Environment(loader=func)
    assert env.get_template("bob").render() == "hi bob"
    with pytest.raises(ks.TemplateNotFound):
        env.get_template("no")


def test_select_template_and_the_error_for_none():
    env = ks.Environment(loader=ks.DictLoader({"b": "B"}))
    assert env.select_template(["a", "b"]).render() == "B"
    with pytest.raises(ks.TemplatesNotFound) as info:
        env.select_template(["a", "c"])
    assert str(info.value) == "none of the templates given were found: a, c"
    with pytest.raises(ks.TemplatesNotFound):
        env.select_template([])


def test_no_loader():
    with pytest.raises(TypeError, match="no loader"):
        ks.Environment().get_template("a")


def test_join_path_lets_an_environment_have_relative_names():
    class Relative(ks.Environment):
        def join_path(self, template, parent):
            if template.startswith("./"):
                return parent.rsplit("/", 1)[0] + "/" + template[2:]
            return template

    env = Relative(loader=ks.DictLoader({"dir/main": "{% include './part' %}", "dir/part": "part", "part": "wrong"}))
    assert env.get_template("dir/main").render() == "part"


def test_global_variables_of_a_template_are_found_in_included_ones():
    env = ks.Environment(loader=ks.DictLoader({"a": "{{ g }}{% include 'b' %}", "b": "{{ g }}"}))
    env.globals["g"] = "G"
    assert env.get_template("a").render() == "GG"
