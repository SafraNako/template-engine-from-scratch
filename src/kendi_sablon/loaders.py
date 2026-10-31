"""Where templates come from: a dict, a folder, a function, or several of those tried in turn."""
from __future__ import annotations

import os
import posixpath
from typing import Callable, Dict, List, Optional, Tuple

from .errors import TemplateNotFound


def split_template_path(template: str) -> List[str]:
    """``a/b/c.html`` into pieces; a piece that could leave the folder of the loader (``..``, or a path separator inside a piece) is refused."""
    pieces = []
    for piece in template.split("/"):
        if os.path.sep in piece or (os.path.altsep and os.path.altsep in piece) or piece == os.path.pardir:
            raise TemplateNotFound(template)
        elif piece and piece != ".":
            pieces.append(piece)
    return pieces


class BaseLoader:
    """A loader answers ``get_source(environment, name)`` with ``(source, filename or None, uptodate or None)``, or raises ``TemplateNotFound``."""

    has_source_access = True

    def get_source(self, environment, template: str) -> Tuple[str, Optional[str], Optional[Callable[[], bool]]]:
        if not self.has_source_access:
            raise RuntimeError("%s cannot provide access to the source" % type(self).__name__)
        raise TemplateNotFound(template)

    def list_templates(self) -> List[str]:
        raise TypeError("this loader cannot iterate over all templates")

    def load(self, environment, name: str, globals_=None):
        source, filename, uptodate = self.get_source(environment, name)
        return environment.template_class.from_source(environment, source, name, filename, globals_, uptodate)


class FileSystemLoader(BaseLoader):
    """Loads templates from the folders of a search path."""

    def __init__(self, searchpath, encoding: str = "utf-8", followlinks: bool = False) -> None:
        if not isinstance(searchpath, (list, tuple)):
            searchpath = [searchpath]
        self.searchpath = [os.fspath(p) for p in searchpath]
        self.encoding = encoding
        self.followlinks = followlinks

    def get_source(self, environment, template: str):
        pieces = split_template_path(template)
        for searchpath in self.searchpath:
            filename = posixpath.join(searchpath, *pieces)
            if os.path.isfile(filename):
                break
        else:
            raise TemplateNotFound(template)
        with open(filename, encoding=self.encoding) as f:
            contents = f.read()
        mtime = os.path.getmtime(filename)

        def uptodate() -> bool:
            try:
                return os.path.getmtime(filename) == mtime
            except OSError:
                return False

        return contents, os.path.normpath(filename), uptodate

    def list_templates(self) -> List[str]:
        found = set()
        for searchpath in self.searchpath:
            walk_dir = os.walk(searchpath, followlinks=self.followlinks)
            for dirpath, _, filenames in walk_dir:
                for filename in filenames:
                    template = os.path.relpath(os.path.join(dirpath, filename), searchpath).replace(os.path.sep, "/")
                    if template[:2] == "./":
                        template = template[2:]
                    found.add(template)
        return sorted(found)


class DictLoader(BaseLoader):
    """Templates that are the values of a dict."""

    def __init__(self, mapping: Dict[str, str]) -> None:
        self.mapping = mapping

    def get_source(self, environment, template: str):
        if template in self.mapping:
            source = self.mapping[template]
            return source, None, lambda: source == self.mapping.get(template)
        raise TemplateNotFound(template)

    def list_templates(self) -> List[str]:
        return sorted(self.mapping)


class FunctionLoader(BaseLoader):
    """Asks a function; it returns the source, or ``(source, filename, uptodate)``, or ``None`` for "no such template"."""

    def __init__(self, load_func: Callable) -> None:
        self.load_func = load_func

    def get_source(self, environment, template: str):
        rv = self.load_func(template)
        if rv is None:
            raise TemplateNotFound(template)
        if isinstance(rv, str):
            return rv, None, None
        return rv


class PrefixLoader(BaseLoader):
    """``prefix/name`` is looked up in the loader that goes with ``prefix``."""

    def __init__(self, mapping: Dict[str, BaseLoader], delimiter: str = "/") -> None:
        self.mapping = mapping
        self.delimiter = delimiter

    def get_loader(self, template: str):
        try:
            prefix, name = template.split(self.delimiter, 1)
            loader = self.mapping[prefix]
        except (ValueError, KeyError) as exc:
            raise TemplateNotFound(template) from exc
        return loader, name

    def get_source(self, environment, template: str):
        loader, name = self.get_loader(template)
        try:
            return loader.get_source(environment, name)
        except TemplateNotFound as exc:
            raise TemplateNotFound(template) from exc

    def load(self, environment, name: str, globals_=None):
        loader, local_name = self.get_loader(name)
        try:
            return loader.load(environment, local_name, globals_)
        except TemplateNotFound as exc:
            raise TemplateNotFound(name) from exc

    def list_templates(self) -> List[str]:
        result = []
        for prefix, loader in self.mapping.items():
            for template in loader.list_templates():
                result.append(prefix + self.delimiter + template)
        return result


class ChoiceLoader(BaseLoader):
    """Tries the loaders one after the other."""

    def __init__(self, loaders: List[BaseLoader]) -> None:
        self.loaders = loaders

    def get_source(self, environment, template: str):
        for loader in self.loaders:
            try:
                return loader.get_source(environment, template)
            except TemplateNotFound:
                pass
        raise TemplateNotFound(template)

    def load(self, environment, name: str, globals_=None):
        for loader in self.loaders:
            try:
                return loader.load(environment, name, globals_)
            except TemplateNotFound:
                pass
        raise TemplateNotFound(name)

    def list_templates(self) -> List[str]:
        found = set()
        for loader in self.loaders:
            found.update(loader.list_templates())
        return sorted(found)
