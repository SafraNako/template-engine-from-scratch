"""``Markup`` and ``escape``: the strings that are already safe.  The behaviour is compared with markupsafe (which Jinja2 uses) on the same calls."""
import markupsafe
import pytest

from kendi_sablon import Markup, escape, soft_str

M = markupsafe.Markup


def outcome(call, cls, esc):
    try:
        return call(cls, esc)
    except Exception as exc:                                    # noqa: BLE001 - a call that fails has to fail in the same way
        return exc


def same(call):
    """The same call on both classes gives the same text, and a Markup of the same kind where it is one (or fails in the same way)."""
    mine, theirs = outcome(call, Markup, escape), outcome(call, M, markupsafe.escape)
    if isinstance(theirs, Exception):
        assert type(mine) is type(theirs) and str(mine) == str(theirs)
    elif isinstance(mine, (list, tuple)):
        assert [str(x) for x in mine] == [str(x) for x in theirs]
        assert [type(x).__name__ for x in mine] == [type(x).__name__ for x in theirs]
    else:
        assert str(mine) == str(theirs), (mine, theirs)
        assert type(mine).__name__ == type(theirs).__name__


def test_escape_replaces_the_five_characters():
    assert escape("<a href=\"x\" title='y'>&</a>") == "&lt;a href=&#34;x&#34; title=&#39;y&#39;&gt;&amp;&lt;/a&gt;"
    assert type(escape("x")) is Markup


def test_escape_does_not_escape_markup_twice():
    assert escape(Markup("<b>")) == "<b>" and escape(escape("<")) == "&lt;"


def test_escape_uses_html_method_and_str_of_other_objects():
    class Safe:
        def __html__(self):
            return "<safe>"

    assert escape(Safe()) == "<safe>" and escape(5) == "5" and escape(None) == "None"


def test_soft_str():
    assert type(soft_str(Markup("a"))) is Markup and soft_str(5) == "5" and type(soft_str("a")) is str


@pytest.mark.parametrize("call", [
    lambda M, e: M("<b>") + "<i>",
    lambda M, e: "<i>" + M("<b>"),
    lambda M, e: M("<b>") + M("<i>"),
    lambda M, e: M("<b>") * 2,
    lambda M, e: 2 * M("<b>"),
    lambda M, e: M("<b>%s</b>") % "<x>",
    lambda M, e: M("<b>%s %s</b>") % ("<x>", M("<y>")),
    lambda M, e: M("<b>%(a)s</b>") % {"a": "<x>"},
    lambda M, e: M("<b>%d</b>") % 5,
    lambda M, e: M("{} and {x}").format("<a>", x=M("<b>")),
    lambda M, e: M("{0!r}").format("<a>"),
    lambda M, e: M(",").join(["<a>", M("<b>"), 3]),
    lambda M, e: M("a b  c").split(),
    lambda M, e: M("a,b").rsplit(","),
    lambda M, e: M("a\nb").splitlines(),
    lambda M, e: M("a<b").partition("<"),
    lambda M, e: M("<A>").lower(),
    lambda M, e: M("<a>").upper(),
    lambda M, e: M(" <a> ").strip(),
    lambda M, e: M("<a>").replace("a", "<b>"),
    lambda M, e: M("<a>").center(9, "<"),
    lambda M, e: M("<a>").ljust(5, "&"),
    lambda M, e: M("<a>")[1:2],
    lambda M, e: M("<a> b").title(),
    lambda M, e: M("<a>").capitalize(),
    lambda M, e: M("a  b").expandtabs(),
    lambda M, e: M("<a>").zfill(6),
    lambda M, e: M("<a>").upper("x"),
    lambda M, e: M("<a>").strip(1),
    lambda M, e: M("<p>One <b>two</b> &amp; <!-- c --> three</p>").striptags(),
    lambda M, e: M("&lt;a&gt; &amp; &eacute;").unescape(),
    lambda M, e: repr(M("<a>")),
    lambda M, e: M.escape("<a>"),
    lambda M, e: M(5),
])
def test_same_as_markupsafe(call):
    same(call)


def test_markup_of_an_object_with_html_method():
    class Safe:
        def __html__(self):
            return "<safe>"

    assert Markup(Safe()) == "<safe>" and type(Markup(Safe())) is Markup


def test_html_format_with_a_spec_fails():
    with pytest.raises(ValueError):
        Markup("{:>5}").format(Markup("x"))


def test_markup_is_hashable_and_equal_to_the_same_text():
    assert Markup("a") == "a" and hash(Markup("a")) == hash("a") and {Markup("a"): 1}["a"] == 1
