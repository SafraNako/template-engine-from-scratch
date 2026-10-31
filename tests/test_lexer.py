"""The tokens of a source: what the lexer cuts out, with their line numbers (compared with the lexer of Jinja2 on the same text)."""
import os

import jinja2
import pytest

import fuzzgen
import kendi_sablon as ks


def my_tokens(source, **options):
    env = ks.Environment(**options)
    return [(t.lineno, t.type, t.value) for t in iter_stream(env.lexer.tokenize(source))]


def iter_stream(stream):
    while stream.current.type != "eof":
        yield next(stream)


def their_tokens(source, **options):
    env = jinja2.Environment(**options)
    return [(t.lineno, t.type, t.value) for t in iter_stream(env.lexer.tokenize(source))]


def outcome(function, source, options):
    try:
        return ("ok", function(source, **options))
    except Exception as exc:                                    # noqa: BLE001
        return ("err", type(exc).__name__, getattr(exc, "message", str(exc)), getattr(exc, "lineno", None))


def test_a_small_source():
    assert my_tokens("a {{ b|c(1, 'd') }}\n{% if x %}") == [
        (1, "data", "a "), (1, "variable_begin", "{{"), (1, "name", "b"), (1, "pipe", "|"), (1, "name", "c"), (1, "lparen", "("), (1, "integer", 1),
        (1, "comma", ","), (1, "string", "d"), (1, "rparen", ")"), (1, "variable_end", "}}"), (1, "data", "\n"), (2, "block_begin", "{%"),
        (2, "name", "if"), (2, "name", "x"), (2, "block_end", "%}"),
    ]


def test_operators_get_the_names_the_parser_uses():
    kinds = [t[1] for t in my_tokens("{{ + - * / // % ** ~ == != < <= > >= = . : , | ; ( ) [ ] { } }}")][1:-1]
    assert kinds == ["add", "sub", "mul", "div", "floordiv", "mod", "pow", "tilde", "eq", "ne", "lt", "lteq", "gt", "gteq", "assign", "dot", "colon",
                     "comma", "pipe", "semicolon", "lparen", "rparen", "lbracket", "rbracket", "lbrace", "rbrace"]


def test_numbers_and_strings_are_converted():
    values = [t[2] for t in my_tokens(r"{{ 0x1F 0b11 0o7 1_0 1.5 1e2 2.5E-1 'a\tb' \"cé\" }}".replace('\\"', '"'))][1:-1]
    assert values == [31, 3, 7, 10, 1.5, 100.0, 0.25, "a\tb", "cé"]


def test_a_dot_between_digits_is_a_float_only_after_the_first_digits():
    assert [t[1:] for t in my_tokens("{{ 1.5.x }}")][1:-1] == [("float", 1.5), ("dot", "."), ("name", "x")]
    assert [t[1:] for t in my_tokens("{{ a.1.5 }}")][1:-1] == [("name", "a"), ("dot", "."), ("integer", 1), ("dot", "."), ("integer", 5)]


def test_the_lexer_is_lazy_so_an_early_syntax_error_wins_over_a_later_lexing_error():
    env = ks.Environment()
    with pytest.raises(ks.TemplateSyntaxError) as info:
        env.parse("{% if %}\n{{ @ }}")
    assert info.value.lineno == 1 and "Expected an expression" in info.value.message


@pytest.mark.parametrize("options", [{}, {"trim_blocks": True}, {"lstrip_blocks": True}, {"trim_blocks": True, "lstrip_blocks": True},
                                     {"keep_trailing_newline": True}, {"newline_sequence": "\r\n"}])
def test_same_tokens_as_jinja2_for_random_sources(options):
    count = int(os.environ.get("KENDI_FUZZ", "400"))
    for seed in range(count):
        source, _ = fuzzgen.whitespace_case(seed)
        mine, theirs = outcome(my_tokens, source, options), outcome(their_tokens, source, options)
        assert mine == theirs, "seed %d\nsource: %r\nmine:   %r\njinja2: %r" % (seed, source, mine, theirs)


def test_same_tokens_as_jinja2_for_damaged_sources():
    count = int(os.environ.get("KENDI_FUZZ", "400"))
    for seed in range(count):
        source, options, _ = fuzzgen.mutation_case(seed)
        options = {k: v for k, v in options.items() if k in ("trim_blocks", "lstrip_blocks", "keep_trailing_newline", "newline_sequence")}
        mine, theirs = outcome(my_tokens, source, options), outcome(their_tokens, source, options)
        assert mine == theirs, "seed %d\nsource: %r\nmine:   %r\njinja2: %r" % (seed, source, mine, theirs)
