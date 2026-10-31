"""The exceptions of the engine.  They follow the Jinja2 names and messages so that the same template fails in the same way."""
from __future__ import annotations

from typing import Optional


class TemplateError(Exception):
    """The base class of everything the engine raises on purpose."""

    def __init__(self, message: Optional[str] = None) -> None:
        super().__init__(message)

    @property
    def message(self) -> Optional[str]:
        return self.args[0] if self.args else None


class TemplateNotFound(IOError, LookupError, TemplateError):
    """The loader has no template of that name."""

    message: Optional[str] = None

    def __init__(self, name, message: Optional[str] = None) -> None:
        IOError.__init__(self, name)
        if message is None:
            from .runtime import Undefined
            if isinstance(name, Undefined):
                name._fail_with_undefined_error()
            message = name
        self.message = message
        self.name = name
        self.templates = [name]

    def __str__(self) -> str:
        return str(self.message)


class TemplatesNotFound(TemplateNotFound):
    """None of the templates of a list exists (``select_template``, ``include [..]``)."""

    def __init__(self, names=(), message: Optional[str] = None) -> None:
        if message is None:
            from .runtime import Undefined
            parts = []
            for name in names:
                if isinstance(name, Undefined):
                    parts.append(name._undefined_message)
                else:
                    parts.append(name)
            parts_str = ", ".join(map(str, parts))
            message = "none of the templates given were found: %s" % parts_str
        TemplateNotFound.__init__(self, names[-1] if names else None, message)
        self.templates = list(names)


class TemplateSyntaxError(TemplateError):
    """The source of the template is not valid; ``lineno`` is where the parser gave up."""

    def __init__(self, message: str, lineno: int, name: Optional[str] = None, filename: Optional[str] = None) -> None:
        super().__init__(message)
        self.lineno = lineno
        self.name = name
        self.filename = filename
        self.source: Optional[str] = None

    def __str__(self) -> str:
        if self.source is None and self.lineno is None:
            return str(self.message)
        location = "line %d" % self.lineno
        name = self.filename or self.name
        if name:
            location = 'File "%s", %s' % (name, location)
        lines = [self.message, "  " + location]
        if self.source is not None:
            try:
                line = self.source.splitlines()[self.lineno - 1]
            except IndexError:
                pass
            else:
                lines.append("    " + line.strip())
        return "\n".join(lines)


class TemplateAssertionError(TemplateSyntaxError):
    """The template parses but breaks a rule that is checked before rendering (a block defined twice, an unknown filter)."""


class TemplateRuntimeError(TemplateError):
    """Something went wrong while a template was rendered."""


class UndefinedError(TemplateRuntimeError):
    """An undefined value was used in a way that needs a value."""


class FilterArgumentError(TemplateRuntimeError):
    """A filter or test was called with arguments that it cannot use."""
