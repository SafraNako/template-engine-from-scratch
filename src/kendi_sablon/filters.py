"""The filters of ``{{ value|name(arguments) }}``."""
from __future__ import annotations

import math
import random
import re
from collections import abc
from inspect import getattr_static
from itertools import chain, groupby
from typing import Any, Callable, Iterator, List, NamedTuple, Optional
from urllib.parse import quote_from_bytes

from .errors import FilterArgumentError
from .markup import Markup, escape, soft_str
from .runtime import Undefined
from .utils import htmlsafe_json_dumps, pass_context, pass_environment, pass_eval_context


def ignore_case(value: Any) -> Any:
    """The key function for the sorts that do not care about case."""
    return value.lower() if isinstance(value, str) else value


def _attribute_parts(attr) -> list:
    if attr is None:
        return []
    if isinstance(attr, str):
        return [int(x) if x.isdigit() else x for x in attr.split(".")]
    return [attr]


def make_attrgetter(environment, attribute, postprocess: Optional[Callable] = None, default: Any = None) -> Callable:
    """``attribute`` is a name, a number (an index) or a dotted path ``"a.b.0"``; a missing part gives ``default`` if there is one."""
    parts = _attribute_parts(attribute)

    def attrgetter(item: Any) -> Any:
        for part in parts:
            item = environment.getitem(item, part)
            if default is not None and isinstance(item, Undefined):
                item = default
        if postprocess is not None:
            item = postprocess(item)
        return item
    return attrgetter


def make_multi_attrgetter(environment, attribute, postprocess: Optional[Callable] = None) -> Callable:
    """Like :func:`make_attrgetter` for ``"a,b.c"``: a list of values, so that sorting by it sorts by a, then by b.c."""
    split = attribute.split(",") if isinstance(attribute, str) else [attribute]
    parts = [_attribute_parts(item) for item in split]

    def attrgetter(item: Any) -> list:
        items: list = [None] * len(parts)
        for i, attribute_part in enumerate(parts):
            item_i = item
            for part in attribute_part:
                item_i = environment.getitem(item_i, part)
            if postprocess is not None:
                item_i = postprocess(item_i)
            items[i] = item_i
        return items
    return attrgetter


def url_quote(obj: Any, charset: str = "utf-8", for_qs: bool = False) -> str:
    if not isinstance(obj, bytes):
        if not isinstance(obj, str):
            obj = str(obj)
        obj = obj.encode(charset)
    rv = quote_from_bytes(obj, b"" if for_qs else b"/")
    if for_qs:
        rv = rv.replace("%20", "+")
    return rv


def do_forceescape(value) -> Markup:
    if hasattr(value, "__html__"):
        value = value.__html__()
    return escape(str(value))


def do_urlencode(value) -> str:
    if isinstance(value, str) or not isinstance(value, abc.Iterable):
        return url_quote(value)
    items = value.items() if isinstance(value, dict) else value
    return "&".join("%s=%s" % (url_quote(k, for_qs=True), url_quote(v, for_qs=True)) for k, v in items)


@pass_eval_context
def do_replace(eval_ctx, s, old, new, count: Optional[int] = None):
    if count is None:
        count = -1
    if not eval_ctx.autoescape:
        return str(s).replace(str(old), str(new), count)
    if hasattr(old, "__html__") or (hasattr(new, "__html__") and not hasattr(s, "__html__")):
        s = escape(s)
    else:
        s = soft_str(s)
    return s.replace(soft_str(old), soft_str(new), count)


def do_upper(s) -> str:
    return soft_str(s).upper()


def do_lower(s) -> str:
    return soft_str(s).lower()


def do_items(value) -> Iterator:
    if isinstance(value, Undefined):
        return
    if not isinstance(value, abc.Mapping):
        raise TypeError("Can only get item pairs from a mapping.")
    yield from value.items()


_attr_key_re = re.compile(r"[\s/>=]", flags=re.ASCII)


@pass_eval_context
def do_xmlattr(eval_ctx, d, autospace: bool = True):
    items = []
    for key, value in d.items():
        if value is None or isinstance(value, Undefined):
            continue
        if _attr_key_re.search(key) is not None:
            raise ValueError("Invalid character in attribute name: %r" % key)
        items.append('%s="%s"' % (escape(key), escape(value)))
    rv = " ".join(items)
    if autospace and rv:
        rv = " " + rv
    if eval_ctx.autoescape:
        rv = Markup(rv)
    return rv


def do_capitalize(s) -> str:
    return soft_str(s).capitalize()


_word_beginning_split_re = re.compile(r"([-\s({\[<]+)")


def do_title(s) -> str:
    return "".join(item[0].upper() + item[1:].lower() for item in _word_beginning_split_re.split(soft_str(s)) if item)


def do_dictsort(value, case_sensitive: bool = False, by: str = "key", reverse: bool = False) -> list:
    if by == "key":
        pos = 0
    elif by == "value":
        pos = 1
    else:
        raise FilterArgumentError('You can only sort by either "key" or "value"')

    def sort_func(item):
        key = item[pos]
        return key if case_sensitive else ignore_case(key)
    return sorted(value.items(), key=sort_func, reverse=reverse)


@pass_environment
def do_sort(environment, value, reverse: bool = False, case_sensitive: bool = False, attribute=None) -> list:
    key_func = make_multi_attrgetter(environment, attribute, postprocess=ignore_case if not case_sensitive else None)
    return sorted(value, key=key_func, reverse=reverse)


@pass_environment
def do_unique(environment, value, case_sensitive: bool = False, attribute=None) -> Iterator:
    getter = make_attrgetter(environment, attribute, postprocess=ignore_case if not case_sensitive else None)
    seen = set()
    for item in value:
        key = getter(item)
        if key not in seen:
            seen.add(key)
            yield item


def _min_or_max(environment, value, func, case_sensitive: bool, attribute):
    it = iter(value)
    try:
        first = next(it)
    except StopIteration:
        return environment.undefined("No aggregated item, sequence was empty.")
    key_func = make_attrgetter(environment, attribute, postprocess=ignore_case if not case_sensitive else None)
    return func(chain([first], it), key=key_func)


@pass_environment
def do_min(environment, value, case_sensitive: bool = False, attribute=None):
    return _min_or_max(environment, value, min, case_sensitive, attribute)


@pass_environment
def do_max(environment, value, case_sensitive: bool = False, attribute=None):
    return _min_or_max(environment, value, max, case_sensitive, attribute)


def do_default(value, default_value="", boolean: bool = False):
    if isinstance(value, Undefined) or (boolean and not value):
        return default_value
    return value


@pass_eval_context
def do_join(eval_ctx, value, d="", attribute=None):
    if attribute is not None:
        value = map(make_attrgetter(eval_ctx.environment, attribute), value)
    if not eval_ctx.autoescape:
        return str(d).join(map(str, value))
    # if the delimiter is not safe markup, the items are escaped only when one of them is markup (the result is markup then)
    if not hasattr(d, "__html__"):
        value = list(value)
        do_escape = False
        for idx, item in enumerate(value):
            if hasattr(item, "__html__"):
                do_escape = True
            else:
                value[idx] = str(item)
        d = escape(d) if do_escape else str(d)
        return d.join(value)
    return soft_str(d).join(map(soft_str, value))


def do_center(value, width: int = 80) -> str:
    return soft_str(value).center(width)


@pass_environment
def do_first(environment, seq):
    try:
        return next(iter(seq))
    except StopIteration:
        return environment.undefined("No first item, sequence was empty.")


@pass_environment
def do_last(environment, seq):
    try:
        return next(iter(reversed(seq)))
    except StopIteration:
        return environment.undefined("No last item, sequence was empty.")


@pass_context
def do_random(context, seq):
    try:
        return random.choice(seq)
    except IndexError:
        return context.environment.undefined("No random item, sequence was empty.")


def do_filesizeformat(value, binary: bool = False) -> str:
    bytes_ = float(value)
    base = 1024 if binary else 1000
    prefixes = ["KiB" if binary else "kB", "MiB" if binary else "MB", "GiB" if binary else "GB", "TiB" if binary else "TB",
                "PiB" if binary else "PB", "EiB" if binary else "EB", "ZiB" if binary else "ZB", "YiB" if binary else "YB"]
    if bytes_ == 1:
        return "1 Byte"
    if bytes_ < base:
        return "%d Bytes" % int(bytes_)
    for i, prefix in enumerate(prefixes):
        unit = base ** (i + 2)
        if bytes_ < unit:
            return "%.1f %s" % (base * bytes_ / unit, prefix)
    return "%.1f %s" % (base * bytes_ / unit, prefix)


def do_pprint(value) -> str:
    from pprint import pformat
    return pformat(value)


def do_indent(s, width=4, first: bool = False, blank: bool = False):
    indention = width if isinstance(width, str) else " " * width
    newline = "\n"
    if isinstance(s, Markup):
        indention = Markup(indention)
        newline = Markup(newline)
    s += newline                                    # this quirk keeps the last line break
    if blank:
        rv = (newline + indention).join(s.splitlines())
    else:
        lines = s.splitlines()
        rv = lines.pop(0)
        if lines:
            rv += newline + newline.join(indention + line if line else line for line in lines)
    if first:
        rv = indention + rv
    return rv


@pass_environment
def do_truncate(env, s, length: int = 255, killwords: bool = False, end: str = "...", leeway: Optional[int] = None):
    if leeway is None:
        leeway = env.policies["truncate.leeway"]
    assert length >= len(end), "expected length >= %d, got %d" % (len(end), length)
    assert leeway >= 0, "expected leeway >= 0, got %d" % leeway
    if len(s) <= length + leeway:
        return s
    if killwords:
        return s[:length - len(end)] + end
    result = s[:length - len(end)].rsplit(" ", 1)[0]
    return result + end


@pass_environment
def do_wordwrap(environment, s, width: int = 79, break_long_words: bool = True, wrapstring: Optional[str] = None, break_on_hyphens: bool = True) -> str:
    import textwrap
    if wrapstring is None:
        wrapstring = environment.newline_sequence
    # a paragraph at a time: textwrap would join the lines of the text
    return wrapstring.join([wrapstring.join(textwrap.wrap(line, width=width, expand_tabs=False, replace_whitespace=False,
                                                          break_long_words=break_long_words, break_on_hyphens=break_on_hyphens))
                            for line in s.splitlines()])


_word_re = re.compile(r"\w+")


def do_wordcount(s) -> int:
    return len(_word_re.findall(soft_str(s)))


def do_int(value, default: int = 0, base: int = 10) -> int:
    try:
        if isinstance(value, str):
            return int(value, base)
        return int(value)
    except (TypeError, ValueError):
        try:                                        # "1.5" is not an int but its int() is 1
            return int(float(value))
        except (TypeError, ValueError, OverflowError):
            return default


def do_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def do_format(value, *args, **kwargs):
    if args and kwargs:
        raise FilterArgumentError("can't handle positional and keyword arguments at the same time")
    return soft_str(value) % (kwargs or args)


def do_trim(value, chars: Optional[str] = None) -> str:
    return soft_str(value).strip(chars)


def do_striptags(value) -> str:
    if hasattr(value, "__html__"):
        value = value.__html__()
    return Markup(str(value)).striptags()


def do_slice(value, slices: int, fill_with=None) -> Iterator[list]:
    seq = list(value)
    length = len(seq)
    items_per_slice = length // slices
    slices_with_extra = length % slices
    offset = 0
    for slice_number in range(slices):
        start = offset + slice_number * items_per_slice
        if slice_number < slices_with_extra:
            offset += 1
        end = offset + (slice_number + 1) * items_per_slice
        tmp = seq[start:end]
        if fill_with is not None and slice_number >= slices_with_extra:
            tmp.append(fill_with)
        yield tmp


def do_batch(value, linecount: int, fill_with=None) -> Iterator[list]:
    tmp: list = []
    for item in value:
        if len(tmp) == linecount:
            yield tmp
            tmp = []
        tmp.append(item)
    if tmp:
        if fill_with is not None and len(tmp) < linecount:
            tmp += [fill_with] * (linecount - len(tmp))
        yield tmp


def do_round(value, precision: int = 0, method: str = "common"):
    if method not in {"common", "ceil", "floor"}:
        raise FilterArgumentError("method must be common, ceil or floor")
    if method == "common":
        return round(value, precision)
    func = getattr(math, method)
    return func(value * 10 ** precision) / 10 ** precision


class _GroupTuple(NamedTuple):
    grouper: Any
    list: List[Any]

    def __repr__(self) -> str:
        return tuple.__repr__(self)

    def __str__(self) -> str:
        return tuple.__str__(self)


@pass_environment
def do_groupby(environment, value, attribute, default=None, case_sensitive: bool = False) -> list:
    expr = make_attrgetter(environment, attribute, postprocess=ignore_case if not case_sensitive else None, default=default)
    out = [_GroupTuple(key, list(values)) for key, values in groupby(sorted(value, key=expr), expr)]
    if not case_sensitive:                          # the groups were found without case; show the first spelling of each
        output_expr = make_attrgetter(environment, attribute, default=default)
        out = [_GroupTuple(output_expr(values[0]), values) for _, values in out]
    return out


@pass_environment
def do_sum(environment, iterable, attribute=None, start=0):
    if attribute is not None:
        iterable = map(make_attrgetter(environment, attribute), iterable)
    return sum(iterable, start)


def do_list(value) -> list:
    return list(value)


def do_mark_safe(value) -> Markup:
    return Markup(value)


def do_mark_unsafe(value) -> str:
    return str(value)


def do_reverse(value):
    if isinstance(value, str):
        return value[::-1]
    try:
        return reversed(value)
    except TypeError:
        try:
            rv = list(value)
            rv.reverse()
            return rv
        except TypeError as e:
            raise FilterArgumentError("argument must be iterable") from e


@pass_environment
def do_attr(environment, obj, name: str):
    try:
        getattr_static(obj, name)
    except AttributeError:
        # a property or __getattr__ may still know it; an item of a dict is not an attribute
        if not hasattr(obj, name):
            return environment.undefined(obj=obj, name=name)
    return environment.getattr(obj, name)


def prepare_map(context, args, kwargs) -> Callable:
    if not args and "attribute" in kwargs:
        attribute = kwargs.pop("attribute")
        default = kwargs.pop("default", None)
        if kwargs:
            raise FilterArgumentError("Unexpected keyword argument %r" % next(iter(kwargs)))
        return make_attrgetter(context.environment, attribute, default=default)
    try:
        name = args[0]
        args = args[1:]
    except LookupError:
        raise FilterArgumentError("map requires a filter argument") from None

    def func(item: Any) -> Any:
        return context.environment.call_filter(name, item, args, kwargs, context=context)
    return func


@pass_context
def do_map(context, value, *args, **kwargs) -> Iterator:
    if value:
        func = prepare_map(context, args, kwargs)
        for item in value:
            yield func(item)


def prepare_select_or_reject(context, args, kwargs, modfunc: Callable, lookup_attr: bool) -> Callable:
    if lookup_attr:
        try:
            attr = args[0]
        except LookupError:
            raise FilterArgumentError("Missing parameter for attribute name") from None
        transfunc = make_attrgetter(context.environment, attr)
        off = 1
    else:
        off = 0

        def transfunc(x: Any) -> Any:
            return x
    try:
        name = args[off]
        args = args[1 + off:]

        def func(item: Any) -> Any:
            return context.environment.call_test(name, item, args, kwargs, context)
    except LookupError:
        func = bool
    return lambda item: modfunc(func(transfunc(item)))


def select_or_reject(context, value, args, kwargs, modfunc: Callable, lookup_attr: bool) -> Iterator:
    if value:
        func = prepare_select_or_reject(context, args, kwargs, modfunc, lookup_attr)
        for item in value:
            if func(item):
                yield item


@pass_context
def do_select(context, value, *args, **kwargs):
    return select_or_reject(context, value, args, kwargs, lambda x: x, False)


@pass_context
def do_reject(context, value, *args, **kwargs):
    return select_or_reject(context, value, args, kwargs, lambda x: not x, False)


@pass_context
def do_selectattr(context, value, *args, **kwargs):
    return select_or_reject(context, value, args, kwargs, lambda x: x, True)


@pass_context
def do_rejectattr(context, value, *args, **kwargs):
    return select_or_reject(context, value, args, kwargs, lambda x: not x, True)


@pass_eval_context
def do_tojson(eval_ctx, value, indent: Optional[int] = None) -> Markup:
    import json
    policies = eval_ctx.environment.policies
    dumps = policies["json.dumps_function"] or json.dumps
    kwargs = policies["json.dumps_kwargs"]
    if indent is not None:
        kwargs = dict(kwargs, indent=indent)
    return htmlsafe_json_dumps(value, dumps=dumps, **kwargs)


FILTERS = {
    "abs": abs, "attr": do_attr, "batch": do_batch, "capitalize": do_capitalize, "center": do_center, "count": len, "d": do_default,
    "default": do_default, "dictsort": do_dictsort, "e": escape, "escape": escape, "filesizeformat": do_filesizeformat, "first": do_first,
    "float": do_float, "forceescape": do_forceescape, "format": do_format, "groupby": do_groupby, "indent": do_indent, "int": do_int,
    "join": do_join, "last": do_last, "length": len, "list": do_list, "lower": do_lower, "items": do_items, "map": do_map, "min": do_min,
    "max": do_max, "pprint": do_pprint, "random": do_random, "reject": do_reject, "rejectattr": do_rejectattr, "replace": do_replace,
    "reverse": do_reverse, "round": do_round, "safe": do_mark_safe, "select": do_select, "selectattr": do_selectattr, "slice": do_slice,
    "sort": do_sort, "string": soft_str, "striptags": do_striptags, "sum": do_sum, "title": do_title, "trim": do_trim, "truncate": do_truncate,
    "unique": do_unique, "upper": do_upper, "urlencode": do_urlencode, "wordcount": do_wordcount, "wordwrap": do_wordwrap, "xmlattr": do_xmlattr,
    "tojson": do_tojson,
}
