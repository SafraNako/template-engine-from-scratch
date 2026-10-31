"""Speed of this engine against Jinja2 on the same templates (best of several runs).

    python benchmarks/bench.py [rows]       # rows: size of the data, default 2000
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import jinja2  # noqa: E402

import kendi_sablon  # noqa: E402

CASES = {
    "text and variables": ("Hello {{ name }}, you are {{ age }} years old and live in {{ city }}. " * 200, "plain"),
    "loop with output": ("{% for r in rows %}<li>{{ r.id }}: {{ r.name }} ({{ r.score }})</li>\n{% endfor %}", "rows"),
    "loop with filters": ("{% for r in rows %}{{ r.name|upper }} {{ r.name|title|truncate(8) }} {{ r.note|default('none') }} {{ r.score|round(1) }}\n{% endfor %}", "rows"),
    "conditions in a loop": ("{% for r in rows %}{% if r.score > 50 %}high{% elif r.score > 20 %}mid{% else %}low{% endif %} {{ loop.index }}{{ ',' if not loop.last }}{% endfor %}", "rows"),
    "autoescape": ("{% for r in rows %}<td>{{ r.html }}</td>{% endfor %}", "rows-escape"),
    "macro calls": ("{% macro cell(v, cls='c') %}<td class='{{ cls }}'>{{ v }}</td>{% endmacro %}{% for r in rows %}<tr>{{ cell(r.id) }}{{ cell(r.name, 'n') }}</tr>{% endfor %}", "rows"),
    "nested loops": ("{% for i in range(40) %}{% for j in range(40) %}{{ i * j }} {% endfor %}{% endfor %}", "plain"),
    "set and namespace": ("{% set ns = namespace(total=0) %}{% for r in rows %}{% set ns.total = ns.total + r.score %}{% endfor %}{{ ns.total }}", "rows"),
}


def data(rows):
    return {
        "name": "Ann", "age": 30, "city": "Paris",
        "rows": [{"id": i, "name": "name %d" % i, "score": (i * 7) % 100, "note": None if i % 3 else "n%d" % i, "html": "<b>%d</b> & co" % i} for i in range(rows)],
    }


def best(function, repeat=5, number=1):
    times = []
    for _ in range(repeat):
        start = time.perf_counter()
        for _ in range(number):
            function()
        times.append((time.perf_counter() - start) / number)
    return min(times)


def main():
    rows = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    context = data(rows)
    print("%-24s %12s %12s %8s" % ("render (%d rows)" % rows, "this engine", "jinja2", "ratio"))
    for title, (source, kind) in CASES.items():
        options = {"autoescape": True} if kind == "rows-escape" else {}
        mine = kendi_sablon.Environment(**options).from_string(source)
        theirs = jinja2.Environment(**options).from_string(source)
        assert mine.render(context) == theirs.render(context), title
        a, b = best(lambda: mine.render(context)), best(lambda: theirs.render(context))
        print("%-24s %10.2f ms %10.2f ms %7.1fx" % (title, a * 1000, b * 1000, a / b))
    big = "\n".join("{%% if v%d %%}line %d {{ v%d|upper }}{%% else %%}{%% for i in range(3) %%}{{ i + %d }}{%% endfor %%}{%% endif %%}" % (i, i, i, i) for i in range(300))
    a = best(lambda: kendi_sablon.Environment().from_string(big), repeat=3)
    b = best(lambda: jinja2.Environment().from_string(big), repeat=3)
    print("%-24s %10.2f ms %10.2f ms %7.1fx" % ("compile 300 blocks", a * 1000, b * 1000, a / b))


if __name__ == "__main__":
    main()
