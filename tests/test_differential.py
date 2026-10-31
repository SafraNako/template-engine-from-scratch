"""The same template through this engine and through Jinja2: the result (the text, or the exception with its message and line) must be the same.

Four kinds of input: a corpus of templates, written by hand, that is run under several settings; random expressions; random sources made of text and
tags with all kinds of whitespace marks; random whole templates with statements; random inheritance; and valid templates that were damaged (to compare the
syntax errors).  The random generators are seeded, so a failure can be reproduced with ``KENDI_FUZZ_START=<seed> KENDI_FUZZ=1``.
"""
import os

import pytest

import fuzzgen
import oracle
from corpus import CORPUS

SETTINGS = [
    {},
    {"autoescape": True},
    {"trim_blocks": True, "lstrip_blocks": True},
    {"undefined": "StrictUndefined"},
    {"undefined": "ChainableUndefined"},
    {"undefined": "DebugUndefined", "autoescape": True},
    {"keep_trailing_newline": True, "newline_sequence": "\r\n"},
]

FUZZ_COUNT = int(os.environ.get("KENDI_FUZZ", "400"))
FUZZ_START = int(os.environ.get("KENDI_FUZZ_START", "0"))


@pytest.mark.parametrize("options", SETTINGS, ids=lambda o: ",".join("%s=%s" % kv for kv in sorted(o.items())) or "default")
def test_corpus(options):
    failures = []
    for source in CORPUS:
        a, b = oracle.compare(source, options=options)
        if not oracle.agree(a, b):
            failures.append(oracle.explain(source, a, b, options))
    assert not failures, "%d of %d differ:\n\n%s" % (len(failures), len(CORPUS), "\n\n".join(failures[:5]))


def run_fuzz(case_function):
    failures = []
    for seed in range(FUZZ_START, FUZZ_START + FUZZ_COUNT):
        case = case_function(seed)
        source, options = case[0], case[1]
        templates = case[2] if len(case) > 2 else None
        a, b = oracle.compare(source, options=options, templates=templates)
        if not oracle.agree(a, b):
            failures.append("seed %d\n%s" % (seed, oracle.explain(source, a, b, options)))
    assert not failures, "%d of %d differ:\n\n%s" % (len(failures), FUZZ_COUNT, "\n\n".join(failures[:5]))


def test_random_expressions():
    run_fuzz(fuzzgen.expression_case)


def test_random_whitespace():
    run_fuzz(fuzzgen.whitespace_case)


def test_random_documents():
    run_fuzz(fuzzgen.doc_case)


def test_random_inheritance():
    run_fuzz(fuzzgen.inheritance_case)


def test_damaged_templates():
    run_fuzz(fuzzgen.mutation_case)
