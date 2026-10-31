# template-engine-from-scratch

A template engine with the syntax of [Jinja2](https://jinja.palletsprojects.com/), written from scratch in pure Python (3.9+, no dependencies):
variables, filters, tests, conditions, loops, macros, includes, imports, template inheritance, autoescaping, whitespace control.

It is not a wrapper and does not import Jinja2 or MarkupSafe. Jinja2 is only used by the tests, as the **oracle**: the same templates are rendered by
both engines and the results (the text, or the exception with its message and line number) have to be equal.

```python
from kendi_sablon import Environment, DictLoader

env = Environment(loader=DictLoader({
    "base.html": "<h1>{% block title %}{% endblock %}</h1>{% block body %}{% endblock %}",
    "page.html": """{% extends "base.html" %}
{% block title %}{{ title|title }}{% endblock %}
{% block body %}
{%- for u in users if u.age >= 18 %}
  <li class="{{ loop.cycle('odd', 'even') }}">{{ u.name|e }} ({{ u.age }})</li>
{%- else %}
  <li>nobody</li>
{%- endfor %}
{% endblock %}""",
}), autoescape=True)

print(env.get_template("page.html").render(title="our users", users=[{"name": "Ann <3", "age": 31}, {"name": "Bob", "age": 12}, {"name": "Cy", "age": 40}]))
```

```
<h1>Our Users</h1>
  <li class="odd">Ann &lt;3 (31)</li>
  <li class="even">Cy (40)</li>
```

There is also a command line tool: `sablon page.html data.json -D title=hello -I templates/ --autoescape`.

## What it can do

| | |
|---|---|
| **Syntax** | `{{ expression }}`, `{% statement %}`, `{# comment #}`, `{% raw %}`; `-` and `+` marks on the tags, `trim_blocks`, `lstrip_blocks`, `keep_trailing_newline`, `newline_sequence`, your own delimiters |
| **Expressions** | numbers (hex, octal, binary, `1_000`, `1e3`), strings and escapes, lists, tuples, dicts, `+ - * / // % **`, `~`, comparisons (chained), `in`, `not in`, `and or not`, `a if b else c`, attribute and item lookup (`a.b`, `a['b']`, `a.0`), slices, calls with `*args` and `**kwargs`, filters `x\|f(1)`, tests `x is odd` |
| **Statements** | `if / elif / else`, `for` (`else`, `if` filter, tuple targets, `recursive`, the `loop` object: `index revindex first last length cycle changed previtem nextitem depth`), `set` (also with tuples, with `namespace` attributes, and as a block with a filter), `with`, `macro` (defaults, `varargs`, `kwargs`), `call` (with arguments), `filter` blocks, `print`, `autoescape` |
| **Composition** | `extends` / `block` (`super()`, `self.name()`, `scoped`, `required`), `include` (`with` / `without context`, `ignore missing`, a list of names), `import`, `from ... import ... as` |
| **Filters (51)** | `abs attr batch capitalize center count default dictsort escape filesizeformat first float forceescape format groupby indent int items join last length list lower map max min pprint random reject rejectattr replace reverse round safe select selectattr slice sort string striptags sum title tojson trim truncate unique upper urlencode wordcount wordwrap xmlattr` (and the short names `d`, `e`) |
| **Tests (39)** | `boolean callable defined divisibleby eq equalto escaped even false filter float ge greaterthan gt in integer iterable le lessthan lower lt mapping ne none number odd sameas sequence string test true undefined upper` and `== != < <= > >=` |
| **Globals** | `range dict cycler joiner namespace` |
| **Escaping** | `autoescape=True`, a function of the template's name, or `select_autoescape()`; `Markup`, `\|safe`, `\|e`; the filters keep or escape correctly (`join`, `replace`, `format`, `indent`, `xmlattr`, `tojson` ...) |
| **Undefined values** | `Undefined`, `StrictUndefined`, `ChainableUndefined`, `DebugUndefined` |
| **Loaders** | `DictLoader`, `FileSystemLoader` (cannot leave its folder), `FunctionLoader`, `PrefixLoader`, `ChoiceLoader`; cache of compiled templates with `cache_size` and `auto_reload` |
| **Extending** | your own filters, tests and globals; `pass_context`, `pass_eval_context`, `pass_environment`; a `getattr` / `getitem` / `join_path` of your own in a subclass of `Environment` |
| **Errors** | `TemplateSyntaxError` (message and line), `TemplateAssertionError`, `TemplateNotFound`, `UndefinedError`, ... with the messages of Jinja2; an error while rendering has `template_name` and `template_lineno` (and a note with them on Python 3.11+) |

## How it works

```
source ──Lexer──▶ tokens ──Parser──▶ syntax tree ──Compiler──▶ closures ──render──▶ text
```

* `lexer.py`: a generator of tokens. Data between tags, the tags, and inside a tag names, numbers, strings and operators. The whitespace marks and the
  `trim_blocks` / `lstrip_blocks` options act here. Because it is a generator, a syntax error near the start of a template is found before a bad
  character at the end, as in Jinja2.
* `parser.py`: recursive descent, one method per level of precedence (`or` → `and` → `not` → comparison → `+ -` → `~` → `* / // %` → `**` → unary →
  postfix → filters and tests). `nodes.py` has the node classes.
* `compiler.py`: turns every node into a Python closure: an expression into `fn(frame) -> value`, a statement into `fn(frame, out)`. Nothing is
  generated as source text. What is decided while compiling (which filter, which escape function, which kind of scope) is not decided again for every
  render. A `frame` is one scope of variables with a link to the scope around it.
* `runtime.py`: the `Context`, the undefined values, `LoopContext` (`loop`), `Macro`, `BlockReference` (`super()`). `environment.py`: the settings,
  the cache, `Template`. `markup.py`, `filters.py`, `tests.py`, `loaders.py`, `utils.py`, `cli.py`.

## How it was checked

There are 378 tests. The expected values in the hand-written ones are not what this engine happens to do: the helper `expect()` checks that **Jinja2
gives the same text too**. On top of that, the engines are compared on whole families of templates (`tests/test_differential.py`):

* a corpus of 213 small templates, most of them wrong in some way, each rendered under 7 settings (autoescape, `trim_blocks` + `lstrip_blocks`,
  the four kinds of undefined values, `keep_trailing_newline` with `\r\n`);
* **random expressions** (nested operators, comparisons, filters with arguments, tests, slices, calls, attribute and item lookup);
* **random whitespace**: sources of text, indentation, line breaks, comments, raw blocks and tags with every combination of `-` and `+` marks, under
  all combinations of `trim_blocks`, `lstrip_blocks`, `keep_trailing_newline`, `newline_sequence`;
* **random documents**: nested `if / for / set / with / macro / call / filter / autoescape / include / import` with output in between;
* **random inheritance**: child templates with blocks, `super()`, `self.block()`, `scoped`, `required`, `set` before and after `extends`;
* **damaged templates**: a valid one with a few characters or tokens deleted, inserted or swapped, to compare the syntax errors (message *and* line);
* the **tokens** (type, value and line number) of random and damaged sources, from the lexer of Jinja2 and from this one.

During development more than 250,000 random templates were compared; the random sources are seeded (`KENDI_FUZZ_START=<seed> KENDI_FUZZ=1 pytest
tests/test_differential.py` repeats one). The CI runs 800 per generator on Python 3.9, 3.12 and 3.13.

### What Jinja2 taught me

The oracle found a lot of behaviour that is not in the documentation. All of it is now a test.

* `2 ** 3 ** 2` is 64: `**` is left-associative in Jinja2, unlike in Python. `-a ** 2` is `(-a) ** 2`.
* `d.items` is the method and `d['items']` the key; a slice (`x[1:]`) goes straight to the object, without the fallback to an attribute or to an undefined value.
* `{% for a, in x %}` does not work: the rule that ends a tuple in a `for` target never matches (a bug that is kept so that the same templates are accepted).
* After `{% extends %}` the text and `{{ }}` of the child outside of blocks are dropped *when it is compiled*; top-level blocks too, but a block inside a
  `for` is still rendered, and so is the output of `include` and `call`. If `extends` is inside an `if`, the same is decided when it is rendered.
* An unknown filter is an error when the template is compiled, except in a branch that might not run (`if`, `a if b else c`), where it fails when it
  is called, and with another message (`No filter named 'x' found.`). A `for`, `with` or macro inside such a branch is checked when compiling again.
* `loop` is a variable only if the body of the loop mentions it, so an included template does not get it.
* The undefined value of `a if false` is always the plain `Undefined`, whatever `undefined=` says.
* In `{% autoescape x %}` where `x` is a variable, `~` never makes markup (Jinja2 looks at the wrong flag), so `s ~ md` is escaped as a whole.
* A macro returns markup if its **caller** escapes, not if the template it was defined in does.
* The source `{# ` at the very end of a template is not an error, a `{# ` followed by anything is.
* `{% include 'x' without context %}` inside a macro gives a generator object instead of text in Jinja2 3.1.6 (not copied here).

### Known differences

* **Constants are not folded.** Jinja2 evaluates constant expressions while it compiles. The visible results: the part of `1 or x|nosuchfilter` that a constant
  decides is thrown away, so the unknown filter is never noticed (here it is an error); `7[1:]` prints nothing (here a `TypeError`, as for a variable);
  `-2 ** x` with a variable `x` is `-(2 ** x)` there and `(-2) ** x` here; a strict undefined value that comes out of a constant raises at compile time there; in an `autoescape` block whose option is a variable, a literal that is printed (`{{ "<" }}`) is not escaped there and is here.
* Not implemented: the sandbox, async rendering, extensions (`i18n`, `do`, `loopcontrols`), line statements and line comments, `finalize`, bytecode
  cache, `Environment.overlay`, `compile_expression`, `template.stream()`, the `urlize` filter and the `lipsum` function.
* Python's messages that name Jinja's generated functions (`f(**x)` with something that is not a mapping, keyword arguments for an unknown filter) differ.
* The depth of recursion (macro calling itself) is about 160 here and 250 in Jinja2 with Python's default limit, because a closure interpreter uses more
  Python frames per template call.
* **Security**: like Jinja2 without its sandbox, a template can call anything that is reachable from the values it is given. Do not render templates that
  come from people you do not trust.

## Speed

`python benchmarks/bench.py 2000` (2000 rows of data; best of 5; Jinja2 3.1.6 compiles templates to Python source, this engine to closures):

| template | this engine | Jinja2 | ratio |
|---|---:|---:|---:|
| text and 600 variables | 0.34 ms | 0.08 ms | 4.1× |
| loop with output | 2.68 ms | 5.01 ms | 0.5× |
| loop with filters | 14.11 ms | 10.95 ms | 1.3× |
| conditions in a loop | 5.27 ms | 4.37 ms | 1.2× |
| autoescape | 2.70 ms | 2.78 ms | 1.0× |
| macro calls | 16.78 ms | 13.74 ms | 1.2× |
| nested loops (1600 items) | 1.17 ms | 0.60 ms | 1.9× |
| `set` and `namespace` | 3.11 ms | 2.61 ms | 1.2× |
| **compile** 300 blocks | 187.56 ms | 520.20 ms | 0.4× |

Where it is faster: loops that do not use `loop` run as plain Python `for` loops with one scope for all the items, the filters are called without building
argument lists, `escape` is five `str.replace` calls (faster than `translate` or a regular expression), and compiling to closures is cheaper than
generating and compiling source code. Where it is slower: a template that is mostly text with a lot of variables (Jinja2 merges them into one `yield`).

## Development

```bash
pip install -e ".[dev]"        # pytest and jinja2 (the oracle)
pytest                          # 378 tests, about 40 seconds
KENDI_FUZZ=5000 pytest tests/test_differential.py    # more random templates
python benchmarks/bench.py
```

MIT licence.
