"""Small helpers that the engine and the templates share."""
from __future__ import annotations

import json
from collections import deque
from threading import Lock
from typing import Any, Callable, Optional


class _Missing:
    """The marker for "there is no value" where ``None`` is a value."""

    def __repr__(self) -> str:
        return "missing"

    def __reduce__(self) -> str:
        return "missing"


missing: Any = _Missing()


def pass_context(f: Callable) -> Callable:
    """The function gets the :class:`~kendi_sablon.runtime.Context` as its first argument (filters, tests and globals)."""
    f._pass_arg = "context"
    return f


def pass_eval_context(f: Callable) -> Callable:
    """The function gets the evaluation context (``autoescape``) as its first argument."""
    f._pass_arg = "eval_context"
    return f


def pass_environment(f: Callable) -> Callable:
    """The function gets the environment as its first argument."""
    f._pass_arg = "environment"
    return f


def pass_arg_of(obj: Any) -> Optional[str]:
    return getattr(obj, "_pass_arg", None)


def object_type_repr(obj: Any) -> str:
    """The type of an object as it is named in error messages: ``None``, ``dict object``, ``mymodule.Thing object``."""
    if obj is None:
        return "None"
    if obj is Ellipsis:
        return "Ellipsis"
    cls = type(obj)
    if cls.__module__ == "builtins":
        return "%s object" % cls.__name__
    return "%s.%s object" % (cls.__module__, cls.__name__)


class Namespace:
    """A dict that ``{% set ns.name = value %}`` can write to from inside a loop or a block, where a plain ``set`` would only change a copy."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.__attrs = dict(*args, **kwargs)

    def __getattribute__(self, name: str) -> Any:
        if name in {"_Namespace__attrs", "__class__"}:
            return object.__getattribute__(self, name)
        try:
            return self.__attrs[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setitem__(self, name: str, value: Any) -> None:
        self.__attrs[name] = value

    def __repr__(self) -> str:
        return "<Namespace %r>" % self.__attrs


class Cycler:
    """Walks over its items again and again: ``{% set c = cycler('odd', 'even') %}`` then ``c.next()``."""

    def __init__(self, *items: Any) -> None:
        if not items:
            raise RuntimeError("at least one item has to be provided")
        self.items = items
        self.pos = 0

    def reset(self) -> None:
        self.pos = 0

    @property
    def current(self) -> Any:
        return self.items[self.pos]

    def next(self) -> Any:
        rv = self.current
        self.pos = (self.pos + 1) % len(self.items)
        return rv

    __next__ = next


class Joiner:
    """Gives "" the first time it is called and the separator after that."""

    def __init__(self, sep: str = ", ") -> None:
        self.sep = sep
        self.used = False

    def __call__(self) -> str:
        if not self.used:
            self.used = True
            return ""
        return self.sep


class LRUCache:
    """The cache of the compiled templates: a dict that forgets the template that was used the longest ago."""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._data: dict = {}
        self._queue: deque = deque()
        self._lock = Lock()

    def get(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            if key in self._data:
                self._queue.remove(key)
                self._queue.append(key)
                return self._data[key]
        return default

    def __setitem__(self, key: Any, value: Any) -> None:
        with self._lock:
            if key in self._data:
                self._queue.remove(key)
            elif len(self._data) >= self.capacity:
                del self._data[self._queue.popleft()]
            self._data[key] = value
            self._queue.append(key)

    def __contains__(self, key: Any) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._queue.clear()


def htmlsafe_json_dumps(obj: Any, dumps: Optional[Callable] = None, **kwargs: Any):
    """JSON that is safe to put inside a ``<script>`` element or an attribute quoted with ' or ": ``< > & '`` become ``\\u003c`` and so on."""
    from .markup import Markup
    if dumps is None:
        dumps = json.dumps
    return Markup(
        dumps(obj, **kwargs).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("'", "\\u0027")
    )
