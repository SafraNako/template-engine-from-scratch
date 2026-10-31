"""The environment: the settings of the engine, the filters, tests and globals, the loader and the cache of compiled templates; and the template."""
from __future__ import annotations

from collections import ChainMap
from typing import Any, Callable, Dict, Iterable, List, Optional, Union

from . import nodes
from .compiler import Compiler
from .errors import TemplateNotFound, TemplateRuntimeError, TemplatesNotFound, UndefinedError
from .filters import FILTERS
from .lexer import Lexer
from .markup import Markup
from .parser import Parser
from .runtime import Context, EvalContext, Undefined, new_context
from .tests import TESTS
from .utils import Cycler, Joiner, LRUCache, Namespace, pass_arg_of

DEFAULT_NAMESPACE = {"range": range, "dict": dict, "cycler": Cycler, "joiner": Joiner, "namespace": Namespace}
DEFAULT_POLICIES = {"truncate.leeway": 5, "json.dumps_function": None, "json.dumps_kwargs": {"sort_keys": True}}


def select_autoescape(enabled_extensions: Iterable[str] = ("html", "htm", "xml"), disabled_extensions: Iterable[str] = (),
                      default_for_string: bool = True, default: bool = False) -> Callable[[Optional[str]], bool]:
    """An ``autoescape`` setting that decides by the extension of the template's name."""
    enabled = tuple("." + x.lstrip(".").lower() for x in enabled_extensions)
    disabled = tuple("." + x.lstrip(".").lower() for x in disabled_extensions)

    def autoescape(template_name: Optional[str]) -> bool:
        if template_name is None:
            return default_for_string
        template_name = template_name.lower()
        if template_name.endswith(enabled):
            return True
        if template_name.endswith(disabled):
            return False
        return default
    return autoescape


class Environment:
    """Holds the settings; the templates that it compiles share its filters, tests and globals.

    Do not change the options that are about the syntax (delimiters, whitespace) after the first template was compiled."""

    def __init__(self, block_start_string: str = "{%", block_end_string: str = "%}", variable_start_string: str = "{{", variable_end_string: str = "}}",
                 comment_start_string: str = "{#", comment_end_string: str = "#}", trim_blocks: bool = False, lstrip_blocks: bool = False,
                 newline_sequence: str = "\n", keep_trailing_newline: bool = False, undefined: type = Undefined,
                 autoescape: Union[bool, Callable[[Optional[str]], bool]] = False, loader=None, cache_size: int = 400, auto_reload: bool = True) -> None:
        self.block_start_string = block_start_string
        self.block_end_string = block_end_string
        self.variable_start_string = variable_start_string
        self.variable_end_string = variable_end_string
        self.comment_start_string = comment_start_string
        self.comment_end_string = comment_end_string
        if len({block_start_string, variable_start_string, comment_start_string}) != 3:
            raise AssertionError("block, variable and comment start strings must be different.")
        if newline_sequence not in ("\n", "\r\n", "\r"):
            raise ValueError("'newline_sequence' must be one of '\\n', '\\r\\n', or '\\r'.")
        if not (isinstance(undefined, type) and issubclass(undefined, Undefined)):
            raise AssertionError("'undefined' must be a subclass of 'Undefined'.")
        self.trim_blocks = trim_blocks
        self.lstrip_blocks = lstrip_blocks
        self.newline_sequence = newline_sequence
        self.keep_trailing_newline = keep_trailing_newline
        self.undefined = undefined
        self.autoescape = autoescape
        self.filters: Dict[str, Callable] = dict(FILTERS)
        self.tests: Dict[str, Callable] = dict(TESTS)
        self.globals: Dict[str, Any] = dict(DEFAULT_NAMESPACE)
        self.policies: Dict[str, Any] = dict(DEFAULT_POLICIES)
        self.loader = loader
        self.cache: Optional[LRUCache] = LRUCache(cache_size) if cache_size > 0 else None
        self.auto_reload = auto_reload
        self._lexer: Optional[Lexer] = None

    @property
    def lexer(self) -> Lexer:
        if self._lexer is None:
            self._lexer = Lexer(self)
        return self._lexer

    # looking up in objects

    def getitem(self, obj: Any, argument: Any) -> Any:
        """``obj[argument]``; a name that is not an item is tried as an attribute; nothing is found: an undefined value."""
        try:
            return obj[argument]
        except (AttributeError, TypeError, LookupError):
            if isinstance(argument, str):
                try:
                    return getattr(obj, str(argument))
                except AttributeError:
                    pass
            return self.undefined(obj=obj, name=argument)

    def getattr(self, obj: Any, attribute: str) -> Any:
        """``obj.attribute``; if there is no such attribute, the item of that name (so ``dict.items`` is the method, ``dict['items']`` the key)."""
        try:
            return getattr(obj, attribute)
        except AttributeError:
            pass
        try:
            return obj[attribute]
        except (TypeError, LookupError, AttributeError):
            return self.undefined(obj=obj, name=attribute)

    def _call_filter_or_test(self, name, value, args, kwargs, context, eval_ctx, is_filter: bool):
        env_map = self.filters if is_filter else self.tests
        type_name = "filter" if is_filter else "test"
        func = env_map.get(name)
        if func is None:
            msg = "No %s named %r." % (type_name, name)
            if isinstance(name, Undefined):
                try:
                    name._fail_with_undefined_error()
                except Exception as e:
                    msg = "%s (%s; did you forget to quote the callable name?)" % (msg, e)
            raise TemplateRuntimeError(msg)
        args = [value, *(args if args is not None else ())]
        kwargs = kwargs if kwargs is not None else {}
        pass_arg = pass_arg_of(func)
        if pass_arg == "context":
            if context is None:
                raise TemplateRuntimeError("Attempted to invoke a context %s without context." % type_name)
            args.insert(0, context)
        elif pass_arg == "eval_context":
            if eval_ctx is None:
                eval_ctx = context.eval_ctx if context is not None else EvalContext(self)
            args.insert(0, eval_ctx)
        elif pass_arg == "environment":
            args.insert(0, self)
        return func(*args, **kwargs)

    def call_filter(self, name: str, value: Any, args=None, kwargs=None, context: Optional[Context] = None, eval_ctx: Optional[EvalContext] = None) -> Any:
        """Calls a filter by its name (what a filter that takes the name of another filter, like ``map``, does)."""
        return self._call_filter_or_test(name, value, args, kwargs, context, eval_ctx, True)

    def call_test(self, name: str, value: Any, args=None, kwargs=None, context: Optional[Context] = None, eval_ctx: Optional[EvalContext] = None) -> Any:
        return self._call_filter_or_test(name, value, args, kwargs, context, eval_ctx, False)

    # compiling

    def parse(self, source: str, name: Optional[str] = None, filename: Optional[str] = None) -> nodes.Template:
        """The syntax tree of a source."""
        try:
            return Parser(self, str(source), name, filename).parse()
        except Exception as exc:
            if hasattr(exc, "source") and getattr(exc, "source", 1) is None:
                exc.source = source
            raise

    def compile(self, source: Union[str, nodes.Template], name: Optional[str] = None, filename: Optional[str] = None):
        """``(root_render, blocks)``: the closures of a template."""
        tree = self.parse(source, name, filename) if isinstance(source, str) else source
        try:
            return Compiler(self, name, filename).compile_template(tree)
        except Exception as exc:
            if hasattr(exc, "source") and getattr(exc, "source", 1) is None and isinstance(source, str):
                exc.source = source
            raise

    def from_string(self, source: str, globals: Optional[Dict[str, Any]] = None) -> "Template":
        return self.template_class.from_source(self, source, None, None, self.make_globals(globals), None)

    def make_globals(self, d: Optional[Dict[str, Any]]):
        return ChainMap(d if d is not None else {}, self.globals)

    # templates by name

    def join_path(self, template: str, parent: str) -> str:
        """Gives the name of a template that another one includes or extends; override it to have relative names."""
        return template

    def _load_template(self, name: str, globals_) -> "Template":
        if self.loader is None:
            raise TypeError("no loader for this environment specified")
        cache_key = (id(self.loader), name)
        if self.cache is not None:
            template = self.cache.get(cache_key)
            if template is not None and (not self.auto_reload or template.is_up_to_date):
                if globals_:
                    template.globals.update(globals_)
                return template
        template = self.loader.load(self, name, self.make_globals(globals_))
        if self.cache is not None:
            self.cache[cache_key] = template
        return template

    def get_template(self, name: Union[str, "Template"], parent: Optional[str] = None, globals: Optional[Dict[str, Any]] = None) -> "Template":
        if isinstance(name, Template):
            return name
        if parent is not None:
            name = self.join_path(name, parent)
        return self._load_template(name, globals)

    def select_template(self, names: Iterable[Union[str, "Template"]], parent: Optional[str] = None, globals: Optional[Dict[str, Any]] = None) -> "Template":
        """The first of the names that exists."""
        if isinstance(names, Undefined):
            names._fail_with_undefined_error()
        if not names:
            raise TemplatesNotFound(message="Tried to select from an empty list of templates.")
        for name in names:
            if isinstance(name, Template):
                return name
            if parent is not None:
                name = self.join_path(name, parent)
            try:
                return self._load_template(name, globals)
            except (TemplateNotFound, UndefinedError):
                pass
        raise TemplatesNotFound(names)

    def get_or_select_template(self, template_name_or_list, parent: Optional[str] = None, globals: Optional[Dict[str, Any]] = None) -> "Template":
        if isinstance(template_name_or_list, (str, Undefined)):
            return self.get_template(template_name_or_list, parent, globals)
        if isinstance(template_name_or_list, Template):
            return template_name_or_list
        return self.select_template(template_name_or_list, parent, globals)

    def list_templates(self) -> List[str]:
        if self.loader is None:
            raise TypeError("no loader for this environment specified")
        return self.loader.list_templates()


class Template:
    """A compiled template.  ``Template("source")`` works without an environment of your own (a shared one with the default settings is used)."""

    environment_class = Environment
    _spontaneous: Dict[tuple, Environment] = {}

    def __new__(cls, source: str, block_start_string: str = "{%", block_end_string: str = "%}", variable_start_string: str = "{{",
                variable_end_string: str = "}}", comment_start_string: str = "{#", comment_end_string: str = "#}", trim_blocks: bool = False,
                lstrip_blocks: bool = False, newline_sequence: str = "\n", keep_trailing_newline: bool = False, undefined: type = Undefined,
                autoescape: Union[bool, Callable] = False):
        options = (block_start_string, block_end_string, variable_start_string, variable_end_string, comment_start_string, comment_end_string,
                   trim_blocks, lstrip_blocks, newline_sequence, keep_trailing_newline, undefined, autoescape)
        env = cls._spontaneous.get(options)
        if env is None:
            env = cls._spontaneous[options] = Environment(*options[:6], trim_blocks, lstrip_blocks, newline_sequence, keep_trailing_newline, undefined, autoescape)
        return env.from_string(source)

    @classmethod
    def from_source(cls, environment: Environment, source: str, name: Optional[str], filename: Optional[str], globals_, uptodate: Optional[Callable]) -> "Template":
        root_render, blocks = environment.compile(source, name, filename)
        self = object.__new__(cls)
        self.environment = environment
        self.name = name
        self.filename = filename
        self.globals = globals_ if globals_ is not None else environment.make_globals(None)
        self.root_render = root_render
        self.blocks = blocks
        self._uptodate = uptodate
        self._module: Optional[TemplateModule] = None
        return self

    def render(self, *args: Any, **kwargs: Any) -> str:
        """Fills the template in with the variables (a dict, keyword arguments, or both) and returns the text."""
        ctx = self.new_context(dict(*args, **kwargs))
        out: list = []
        self.root_render(ctx, out)
        return "".join(out)

    def new_context(self, vars: Optional[Dict[str, Any]] = None, shared: bool = False, locals: Optional[Dict[str, Any]] = None) -> Context:
        return new_context(self.environment, self.name, self.blocks, vars, shared, self.globals, locals)

    def make_module(self, vars: Optional[Dict[str, Any]] = None, shared: bool = False, locals: Optional[Dict[str, Any]] = None) -> "TemplateModule":
        """Runs the template and gives what it exports (macros and top-level assignments) as attributes of an object."""
        return TemplateModule(self, self.new_context(vars, shared, locals))

    @property
    def module(self) -> "TemplateModule":
        if self._module is None:
            self._module = self.make_module()
        return self._module

    @property
    def is_up_to_date(self) -> bool:
        return True if self._uptodate is None else self._uptodate()

    def __repr__(self) -> str:
        name = "memory:%x" % id(self) if self.name is None else repr(self.name)
        return "<%s %s>" % (type(self).__name__, name)


class TemplateModule:
    """The result of ``{% import %}``: the macros and variables that a template exports; printed, it is the output of the template."""

    def __init__(self, template: Template, context: Context) -> None:
        body: list = []
        template.root_render(context, body)
        self._body = "".join(body)
        self.__dict__.update(context.get_exported())
        self.__name__ = template.name

    def __html__(self) -> Markup:
        return Markup(self._body)

    def __str__(self) -> str:
        return self._body

    def __repr__(self) -> str:
        name = "memory:%x" % id(self) if self.__name__ is None else repr(self.__name__)
        return "<%s %s>" % (type(self).__name__, name)


Environment.template_class = Template
