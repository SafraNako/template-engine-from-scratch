"""``sablon``: renders a template file with data from a JSON file and from ``-D name=value`` options."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from . import __version__
from .environment import Environment
from .errors import TemplateError, TemplateSyntaxError
from .loaders import FileSystemLoader
from .runtime import ChainableUndefined, DebugUndefined, StrictUndefined, Undefined

UNDEFINED = {"default": Undefined, "strict": StrictUndefined, "chainable": ChainableUndefined, "debug": DebugUndefined}


def parse_assignment(text: str):
    if "=" not in text:
        raise argparse.ArgumentTypeError("%r is not name=value" % text)
    name, value = text.split("=", 1)
    try:
        value = json.loads(value)               # 3 is a number, "x" a string, [1, 2] a list; anything that is not JSON stays text
    except ValueError:
        pass
    return name, value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sablon", description="Render a template with data (the template language is a subset of Jinja2).")
    parser.add_argument("template", help="the template file ('-' reads it from standard input)")
    parser.add_argument("data", nargs="?", help="a JSON file with the variables ('-' reads standard input); it must hold an object")
    parser.add_argument("-D", "--define", action="append", default=[], type=parse_assignment, metavar="NAME=VALUE",
                        help="one more variable; the value is read as JSON if it is JSON, as text if it is not")
    parser.add_argument("-o", "--output", help="write the result to this file instead of standard output")
    parser.add_argument("-I", "--include", action="append", default=[], metavar="DIR",
                        help="a folder to look for the templates of include, import and extends in (the folder of the template is always searched last)")
    parser.add_argument("--autoescape", action="store_true", help="escape < > & ' \" in the values that are printed")
    parser.add_argument("--undefined", choices=sorted(UNDEFINED), default="default", help="what a missing variable is (default: prints nothing)")
    parser.add_argument("--trim-blocks", action="store_true", help="remove the first line break after a block tag")
    parser.add_argument("--lstrip-blocks", action="store_true", help="remove the spaces before a block tag at the start of a line")
    parser.add_argument("--keep-trailing-newline", action="store_true", help="keep the line break at the end of the template")
    parser.add_argument("--version", action="version", version="sablon %s" % __version__)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.template == "-":
            source, name, folder = sys.stdin.read(), None, os.getcwd()
        else:
            with open(args.template, encoding="utf-8") as f:
                source = f.read()
            name, folder = os.path.basename(args.template), os.path.dirname(os.path.abspath(args.template))
        data = {}
        if args.data:
            raw = sys.stdin.read() if args.data == "-" else open(args.data, encoding="utf-8").read()
            data = json.loads(raw)
            if not isinstance(data, dict):
                print("sablon: error: the data must be a JSON object", file=sys.stderr)
                return 2
        data.update(dict(args.define))
        environment = Environment(loader=FileSystemLoader(args.include + [folder]), autoescape=args.autoescape, undefined=UNDEFINED[args.undefined],
                                  trim_blocks=args.trim_blocks, lstrip_blocks=args.lstrip_blocks, keep_trailing_newline=args.keep_trailing_newline)
        template = environment.from_string(source) if name is None else environment.get_template(name)
        result = template.render(data)
    except TemplateSyntaxError as exc:
        print("sablon: syntax error: %s (line %s of %s)" % (exc.message, exc.lineno, exc.filename or exc.name or "<stdin>"), file=sys.stderr)
        return 1
    except TemplateError as exc:                    # (before OSError: a missing template is an OSError too)
        where = getattr(exc, "template_lineno", None)
        print("sablon: error: %s%s" % (exc, " (line %s)" % where if where else ""), file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print("sablon: error: %s" % exc, file=sys.stderr)
        return 2
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(result)
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
