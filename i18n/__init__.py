"""i18n 目录查找模块 — Catalog lookup module: t(key, lang, **params).

不依赖 core/application/api/customer_portal_api，只用标准库。
Imports nothing from core/, application/, api/, or customer_portal_api/; standard
library only (NFR1, AD-3).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = ["t", "load"]

# 语言解析由调用方完成，本模块从不猜测 lang —
# Callers resolve `lang` themselves; this module never guesses it (AD-3).

_SOURCE_LOCALE = "zh"
_FALLBACK_LOCALES = ("en", "vi")

# 模块级缓存，首次调用 load() 时填充 —
# Module-level cache, populated on the first load() call.
_catalogs: dict[str, dict[str, Any]] | None = None


def load() -> dict[str, dict[str, Any]]:
    """加载并缓存三个语言目录；zh 缺失/不可读/非法 JSON 时抛出 —
    Load and cache the three locale catalogs; raises if zh is missing, unreadable,
    not valid JSON, or not a JSON object. en/vi are treated as an empty catalog on
    the same failures.
    """
    global _catalogs
    if _catalogs is not None:
        return _catalogs

    base = Path(__file__).resolve().parent
    catalogs: dict[str, dict[str, Any]] = {}

    zh_path = base / f"{_SOURCE_LOCALE}.json"
    try:
        zh_parsed = json.loads(zh_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(
            f"i18n: required '{_SOURCE_LOCALE}' catalog is missing or unreadable at "
            f"{zh_path}"
        ) from exc
    except ValueError as exc:
        raise RuntimeError(
            f"i18n: required '{_SOURCE_LOCALE}' catalog at {zh_path} is not valid JSON"
        ) from exc
    if not isinstance(zh_parsed, dict):
        raise RuntimeError(
            f"i18n: required '{_SOURCE_LOCALE}' catalog at {zh_path} must be a JSON object"
        )
    catalogs[_SOURCE_LOCALE] = zh_parsed

    for locale in _FALLBACK_LOCALES:
        path = base / f"{locale}.json"
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            parsed = {}
        catalogs[locale] = parsed if isinstance(parsed, dict) else {}

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


def t(key: str, lang: str, **params: Any) -> str:
    """解析 key 并按 lang 渲染，永不抛出 —
    Resolve `key` for `lang` and render it with `{param}` interpolation; never raises.

    Fallback chain: lang value -> zh value -> raw key. A render failure (malformed
    placeholder, or a named param the caller did not supply) degrades the same way.
    """
    catalogs = load()
    owner, _, subkey = key.partition(".")

    zh_catalog = catalogs.get(_SOURCE_LOCALE, {})
    lang_catalog = catalogs.get(lang, {})

    value = _lookup(lang_catalog, owner, subkey)
    used_zh = False
    if value is None:
        value = _lookup(zh_catalog, owner, subkey)
        used_zh = True
    if value is None:
        return key

    try:
        return value.format(**params)
    except (KeyError, IndexError, ValueError, AttributeError, TypeError):
        pass

    # Already rendering the zh value above — re-fetching and re-formatting it
    # here would repeat the identical failure, so degrade straight to the key.
    if used_zh:
        return key

    zh_value = _lookup(zh_catalog, owner, subkey)
    if zh_value is not None:
        try:
            return zh_value.format(**params)
        except (KeyError, IndexError, ValueError, AttributeError, TypeError):
            pass

    return key
