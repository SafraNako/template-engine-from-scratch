"""A small template engine with the syntax of Jinja2 (variables, filters, tests, conditions, loops, macros, includes, inheritance), written from scratch."""
from .environment import Environment, Template, TemplateModule, select_autoescape
from .errors import (FilterArgumentError, TemplateAssertionError, TemplateError, TemplateNotFound, TemplateRuntimeError, TemplatesNotFound,
                     TemplateSyntaxError, UndefinedError)
from .loaders import BaseLoader, ChoiceLoader, DictLoader, FileSystemLoader, FunctionLoader, PrefixLoader
from .markup import Markup, escape, soft_str
from .runtime import ChainableUndefined, Context, DebugUndefined, StrictUndefined, Undefined
from .utils import Namespace, pass_context, pass_environment, pass_eval_context

__version__ = "0.1.0"

__all__ = [
    "Environment", "Template", "TemplateModule", "select_autoescape", "TemplateError", "TemplateSyntaxError", "TemplateAssertionError",
    "TemplateRuntimeError", "TemplateNotFound", "TemplatesNotFound", "UndefinedError", "FilterArgumentError", "BaseLoader", "ChoiceLoader",
    "DictLoader", "FileSystemLoader", "FunctionLoader", "PrefixLoader", "Markup", "escape", "soft_str", "Undefined", "ChainableUndefined",
    "DebugUndefined", "StrictUndefined", "Context", "Namespace", "pass_context", "pass_environment", "pass_eval_context",
]
