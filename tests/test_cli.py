"""The ``sablon`` command, run as a real process."""
import json
import os
import subprocess
import sys

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")


def run(*args, stdin=None, cwd=None):
    env = dict(os.environ, PYTHONPATH=SRC)
    return subprocess.run([sys.executable, "-m", "kendi_sablon", *args], input=stdin, capture_output=True, text=True, env=env, cwd=cwd, timeout=30)


def test_renders_a_file_with_json_data(tmp_path):
    (tmp_path / "t.txt").write_text("Hello {{ name }}! {% for i in items %}{{ i }}{% endfor %}\n", encoding="utf-8")
    (tmp_path / "d.json").write_text(json.dumps({"name": "World", "items": [1, 2, 3]}), encoding="utf-8")
    result = run(str(tmp_path / "t.txt"), str(tmp_path / "d.json"))
    assert result.returncode == 0 and result.stdout == "Hello World! 123" and result.stderr == ""


def test_define_overrides_the_file_and_reads_json_values(tmp_path):
    (tmp_path / "t.txt").write_text("{{ a }}|{{ b + 1 }}|{{ c }}|{{ d|length }}", encoding="utf-8")
    (tmp_path / "d.json").write_text('{"a": "file", "c": "file"}', encoding="utf-8")
    result = run(str(tmp_path / "t.txt"), str(tmp_path / "d.json"), "-D", "a=cli", "-D", "b=41", "-D", "d=[1, 2]")
    assert result.stdout == "cli|42|file|2"


def test_reads_the_template_and_the_data_from_standard_input(tmp_path):
    result = run("-", "-D", "x=5", stdin="x is {{ x }}")
    assert result.stdout == "x is 5"
    (tmp_path / "t.txt").write_text("{{ k }}", encoding="utf-8")
    assert run(str(tmp_path / "t.txt"), "-", stdin='{"k": "from stdin"}').stdout == "from stdin"


def test_include_and_extends_find_templates_next_to_the_template_and_in_i_folders(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "shared").mkdir()
    (tmp_path / "pages" / "page.html").write_text("{% extends 'layout.html' %}{% block body %}{% include 'part.html' %}!{% endblock %}", encoding="utf-8")
    (tmp_path / "pages" / "part.html").write_text("part", encoding="utf-8")
    (tmp_path / "shared" / "layout.html").write_text("[{% block body %}{% endblock %}]", encoding="utf-8")
    result = run(str(tmp_path / "pages" / "page.html"), "-I", str(tmp_path / "shared"))
    assert result.returncode == 0 and result.stdout == "[part!]"


def test_options(tmp_path):
    (tmp_path / "t.txt").write_text("{% if true %}\n  {{ v }}\n{% endif %}\n", encoding="utf-8")
    assert run(str(tmp_path / "t.txt"), "-D", "v=<b>", "--autoescape", "--trim-blocks", "--lstrip-blocks", "--keep-trailing-newline").stdout == "  &lt;b&gt;\n"
    assert run(str(tmp_path / "t.txt"), "-D", "v=1").stdout == "\n  1\n"
    (tmp_path / "u.txt").write_text("[{{ nosuch }}]", encoding="utf-8")
    assert run(str(tmp_path / "u.txt")).stdout == "[]"
    assert run(str(tmp_path / "u.txt"), "--undefined", "debug").stdout == "[{{ nosuch }}]"
    strict = run(str(tmp_path / "u.txt"), "--undefined", "strict")
    assert strict.returncode == 1 and "'nosuch' is undefined" in strict.stderr and "line 1" in strict.stderr


def test_output_file(tmp_path):
    (tmp_path / "t.txt").write_text("{{ 1 + 1 }}", encoding="utf-8")
    result = run(str(tmp_path / "t.txt"), "-o", str(tmp_path / "out.txt"))
    assert result.returncode == 0 and result.stdout == "" and (tmp_path / "out.txt").read_text(encoding="utf-8") == "2"


def test_errors_have_a_message_and_an_exit_code(tmp_path):
    (tmp_path / "bad.txt").write_text("a\n{% if %}", encoding="utf-8")
    result = run(str(tmp_path / "bad.txt"))
    assert result.returncode == 1 and "syntax error" in result.stderr and "line 2" in result.stderr and result.stdout == ""
    assert run(str(tmp_path / "missing.txt")).returncode == 2
    (tmp_path / "d.json").write_text("[1]", encoding="utf-8")
    (tmp_path / "ok.txt").write_text("x", encoding="utf-8")
    result = run(str(tmp_path / "ok.txt"), str(tmp_path / "d.json"))
    assert result.returncode == 2 and "JSON object" in result.stderr
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    assert run(str(tmp_path / "ok.txt"), str(tmp_path / "broken.json")).returncode == 2
    (tmp_path / "inc.txt").write_text("{% include 'nosuch' %}", encoding="utf-8")
    result = run(str(tmp_path / "inc.txt"))
    assert result.returncode == 1 and "nosuch" in result.stderr


def test_version_and_help():
    assert run("--version").stdout.startswith("sablon ")
    assert "usage: sablon" in run("--help").stdout
