"""i18n 目录查找模块 — Catalog lookup module: t(key, lang, **params).

不依赖 core/application/api/customer_portal_api，只用标准库。
Imports nothing from core/, application/, api/, or customer_portal_api/; standard
library only (NFR1, AD-3).
"""

from __future__ import annotations

import json
import logging
import string
from pathlib import Path
from typing import Any

__all__ = ["t", "load", "CatalogError"]

_logger = logging.getLogger(__name__)

# 语言解析由调用方完成，本模块从不猜测 lang —
# Callers resolve `lang` themselves; this module never guesses it (AD-3).

_SOURCE_LOCALE = "zh"
# en/vi 是翻译目标，回退目标始终是 zh —
# en/vi are the translation targets; the fallback target is always zh.
_TARGET_LOCALES = ("en", "vi")

# 模块级缓存，首次调用 load() 时填充 —
# Module-level cache, populated on the first load() call.
_catalogs: dict[str, dict[str, Any]] | None = None


class CatalogError(RuntimeError):
    """必需的 zh 目录无法加载 —
    Raised when the required `zh` catalog cannot be loaded. Subclasses
    `RuntimeError` so an `except RuntimeError` caller still catches it; exists so
    Story 1.3's startup guard can catch *this* rather than every RuntimeError
    raised deeper in the lifespan.
    """


class _StrictFormatter(string.Formatter):
    """只接受裸命名占位符 {param} —
    Permit bare named placeholders only.

    catalog-conventions.md:39 fixes interpolation at "single braces, named, never
    positional ... the intersection of Python's `str.format` and a trivial
    TypeScript replace". Attribute access (`{a.b}`), indexing (`{a[0]}`),
    conversions (`{a!r}`) and format specs (`{a:>10}`) all sit outside that
    intersection: the TypeScript side cannot express them, and on the Python side
    they let a catalog value reach into a caller's object or expand a two-character
    param into megabytes. Each one raises here and takes the same degrade path as
    any other render failure.
    """

    def get_field(self, field_name: str, args: Any, kwargs: Any) -> tuple[Any, str]:
        if not field_name.isidentifier():
            raise ValueError(f"i18n: unsupported placeholder {field_name!r}")
        return kwargs[field_name], field_name

    def convert_field(self, value: Any, conversion: str | None) -> Any:
        if conversion is not None:
            raise ValueError(f"i18n: unsupported placeholder conversion {conversion!r}")
        return value

    def format_field(self, value: Any, format_spec: str) -> str:
        if format_spec:
            raise ValueError(f"i18n: unsupported placeholder format spec {format_spec!r}")
        # 参数值只能是 JSON 标量 (AD-7)；否则 str() 会把对象 repr 印到界面上 —
        # AD-7 restricts param values to JSON scalars. Without this guard str()
        # would render an object's repr — memory address included — as UI text.
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError(
                f"i18n: param values must be JSON scalars, got {type(value).__name__}"
            )
        return str(value)


_FORMATTER = _StrictFormatter()


def _read_catalog(path: Path) -> Any:
    """读取并解析一个目录文件；utf-8-sig 容忍 BOM —
    Read and parse one catalog file. `utf-8-sig` decodes BOM-less UTF-8 identically
    but also tolerates the BOM a Windows editor adds, which plain `utf-8` would
    surface as invalid JSON.
    """
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load() -> dict[str, dict[str, Any]]:
    """加载并缓存三个语言目录；zh 缺失/不可读/非法 JSON 时抛出 CatalogError —
    Load and cache the three locale catalogs. Raises `CatalogError` if `zh` is
    missing, unreadable, not valid JSON, or not a JSON object; `en`/`vi` degrade to
    an empty catalog on the same failures, with a warning.

    Returns the live module-level cache, not a copy — treat it as read-only.
    Mutating it corrupts every later `t()` in the process.
    """
    global _catalogs
    if _catalogs is not None:
        return _catalogs

    base = Path(__file__).resolve().parent
    catalogs: dict[str, dict[str, Any]] = {}

    zh_path = base / f"{_SOURCE_LOCALE}.json"
    try:
        zh_parsed = _read_catalog(zh_path)
    except OSError as exc:
        raise CatalogError(
            f"i18n: required '{_SOURCE_LOCALE}' catalog is missing or unreadable at "
            f"{zh_path}"
        ) from exc
    except ValueError as exc:
        raise CatalogError(
            f"i18n: required '{_SOURCE_LOCALE}' catalog at {zh_path} is not valid JSON"
        ) from exc
    if not isinstance(zh_parsed, dict):
        raise CatalogError(
            f"i18n: required '{_SOURCE_LOCALE}' catalog at {zh_path} must be a JSON object"
        )
    catalogs[_SOURCE_LOCALE] = zh_parsed

    for locale in _TARGET_LOCALES:
        path = base / f"{locale}.json"
        try:
            parsed = _read_catalog(path)
        except OSError:
            _logger.warning(
                "i18n: '%s' catalog missing or unreadable at %s — every '%s' lookup "
                "will fall back to '%s'",
                locale, path, locale, _SOURCE_LOCALE,
            )
            parsed = {}
        except ValueError:
            _logger.warning(
                "i18n: '%s' catalog at %s is not valid JSON — every '%s' lookup will "
                "fall back to '%s'",
                locale, path, locale, _SOURCE_LOCALE,
            )
            parsed = {}
        if not isinstance(parsed, dict):
            _logger.warning(
                "i18n: '%s' catalog at %s is not a JSON object — every '%s' lookup "
                "will fall back to '%s'",
                locale, path, locale, _SOURCE_LOCALE,
            )
            parsed = {}
        catalogs[locale] = parsed

    _catalogs = catalogs
    return _catalogs


def _lookup(catalog: dict[str, Any], owner: str, subkey: str) -> str | None:
    """在给定目录中查找 owner.subkey 对应的字符串值 —
    Look up the string value for owner.subkey inside one locale's catalog.
    """
    owner_map = catalog.get(owner)
    if not isinstance(owner_map, dict):
        return None
    value = owner_map.get(subkey)
    return value if isinstance(value, str) else None


def t(key: str, lang: str, **params: str | int | float | bool | None) -> str:
    """解析 key 并按 lang 渲染，永不抛出 —
    Resolve `key` for `lang` and render it with `{param}` interpolation; never raises.

    `lang` is a bare catalog code — `zh`, `en` or `vi`. A BCP-47 tag such as
    `en-US` is not resolved here and misses every lookup, leaving the whole UI in
    `zh` with no error (FR22 validates the stored value upstream, in Epic 2).

    `params` values are JSON scalars (AD-7). Placeholders are bare names only:
    attribute access, indexing, conversions and format specs are rejected and take
    the degrade path, so a catalog value can never reach into a caller's object.

    Fallback chain: lang value -> zh value -> raw key. A render failure (malformed
    placeholder, or a named param the caller did not supply) degrades the same way.
    """
    catalogs = load()
    owner, _, subkey = key.partition(".")

    zh_catalog = catalogs.get(_SOURCE_LOCALE, {})
    lang_catalog = catalogs.get(lang, {})

    value = _lookup(lang_catalog, owner, subkey)
    # lang == "zh" 时两个目录是同一个对象，回退已经用尽 —
    # When lang is the source locale the two catalogs are the same object, so the
    # zh fallback below is already exhausted before it is tried.
    used_zh = lang_catalog is zh_catalog
    if value is None:
        value = _lookup(zh_catalog, owner, subkey)
        used_zh = True
    if value is None:
        return key

    try:
        return _FORMATTER.vformat(value, (), params)
    except Exception:
        # 读边界永不抛出，连参数自身 __format__/__str__ 的异常也要吞下 —
        # A read boundary never raises: an enumerated exception tuple would miss
        # whatever a param's own __format__/__str__ decides to raise.
        pass

    # Already rendering the zh value above — re-fetching and re-formatting it
    # here would repeat the identical failure, so degrade straight to the key.
    if used_zh:
        return key

    zh_value = _lookup(zh_catalog, owner, subkey)
    if zh_value is not None:
        try:
            return _FORMATTER.vformat(zh_value, (), params)
        except Exception:
            pass

    return key
