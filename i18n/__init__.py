"""目录查找模块 t(key, lang, **params) — Catalog lookup: t(key, lang, **params).

只用标准库，不依赖 core/application/api/customer_portal_api（NFR1、AD-3）。
Standard library only; imports nothing from the application packages.
"""

from __future__ import annotations

import json
import logging
import string
from pathlib import Path
from typing import Any

__all__ = ["t", "load", "selfcheck", "CatalogError"]

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
    """必需的 zh 目录无法加载 — The required `zh` catalog could not be loaded.

    继承 RuntimeError，好让 Story 1.3 的启动守卫只捕获这一类 —
    Subclasses RuntimeError so Story 1.3's startup guard can catch this alone.
    """


class _StrictFormatter(string.Formatter):
    """只接受裸命名占位符 {param}，其余一律拒绝并走降级路径 —
    Accept bare named placeholders only; everything else raises and degrades.

    理由见 spec 的 Design Notes — Rationale lives in the spec's Design Notes.
    """

    def parse(self, format_string: str) -> Any:
        # 属性访问、下标、转换、格式规格（含嵌套 {x:{y}}）都在冻结约定之外 —
        # Attribute access, indexing, conversions and format specs (including a
        # nested `{x:{y}}`, which resolves before format_field ever sees it) all
        # sit outside catalog-conventions.md:39.
        for literal_text, field_name, format_spec, conversion in super().parse(format_string):
            if field_name is not None:
                if not field_name.isidentifier():
                    raise ValueError(f"i18n: 不支持的占位符 {field_name!r}")
                if conversion is not None:
                    raise ValueError(f"i18n: 不支持的占位符转换 {conversion!r}")
                if format_spec:
                    raise ValueError(f"i18n: 不支持的占位符格式规格 {format_spec!r}")
            yield literal_text, field_name, format_spec, conversion

    def get_field(self, field_name: str, args: Any, kwargs: Any) -> tuple[Any, str]:
        if not field_name.isidentifier():
            raise ValueError(f"i18n: 不支持的占位符 {field_name!r}")
        return kwargs[field_name], field_name

    def convert_field(self, value: Any, conversion: str | None) -> Any:
        if conversion is not None:
            raise ValueError(f"i18n: 不支持的占位符转换 {conversion!r}")
        return value

    def format_field(self, value: Any, format_spec: str) -> str:
        if format_spec:
            raise ValueError(f"i18n: 不支持的占位符格式规格 {format_spec!r}")
        # 参数值只能是 JSON 标量 (AD-7)；否则 str() 会把对象 repr 印到界面上 —
        # AD-7 restricts param values to JSON scalars. Without this guard str()
        # would render an object's repr — memory address included — as UI text.
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"i18n: 参数值必须是 JSON 标量，收到 {type(value).__name__}")
        return str(value)


_FORMATTER = _StrictFormatter()


def _read_catalog(path: Path) -> Any:
    """读取并解析一个目录文件；utf-8-sig 容忍 Windows 编辑器写入的 BOM —
    Read and parse one catalog file; `utf-8-sig` tolerates a BOM.
    """
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load() -> dict[str, dict[str, Any]]:
    """加载并缓存三个语言目录；zh 有问题时抛 CatalogError，en/vi 降级为空目录 —
    Load and cache the three catalogs; `zh` failures raise, `en`/`vi` degrade.

    返回的是活的模块级缓存而非副本，调用方只读，改它会污染之后每一次 t() —
    Returns the live module-level cache, not a copy. Treat it as read-only.
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
        raise CatalogError(f"i18n: 必需的 '{_SOURCE_LOCALE}' 目录缺失或不可读：{zh_path}") from exc
    except UnicodeDecodeError as exc:
        # UnicodeDecodeError 是 ValueError 的子类，必须排在前面，
        # 否则编码错误会被报成 JSON 语法错误，操作者会去找不存在的语法问题 —
        # UnicodeDecodeError subclasses ValueError, so it must be caught first or
        # an encoding fault is reported as a JSON syntax fault.
        raise CatalogError(
            f"i18n: 必需的 '{_SOURCE_LOCALE}' 目录 {zh_path} 不是合法的 UTF-8 编码"
        ) from exc
    except ValueError as exc:
        raise CatalogError(
            f"i18n: 必需的 '{_SOURCE_LOCALE}' 目录 {zh_path} 不是合法的 JSON"
        ) from exc
    if not isinstance(zh_parsed, dict):
        raise CatalogError(
            f"i18n: 必需的 '{_SOURCE_LOCALE}' 目录 {zh_path} 必须是一个 JSON 对象"
        )
    catalogs[_SOURCE_LOCALE] = zh_parsed

    for locale in _TARGET_LOCALES:
        path = base / f"{locale}.json"
        try:
            parsed = _read_catalog(path)
        except OSError:
            _logger.warning(
                "i18n: '%s' 目录缺失或不可读（%s），该语言的每次查找都会回退到 '%s'",
                locale, path, _SOURCE_LOCALE,
            )
            parsed = {}
        except UnicodeDecodeError:
            _logger.warning(
                "i18n: '%s' 目录 %s 不是合法的 UTF-8 编码，该语言的每次查找都会回退到 '%s'",
                locale, path, _SOURCE_LOCALE,
            )
            parsed = {}
        except ValueError:
            _logger.warning(
                "i18n: '%s' 目录 %s 不是合法的 JSON，该语言的每次查找都会回退到 '%s'",
                locale, path, _SOURCE_LOCALE,
            )
            parsed = {}
        if not isinstance(parsed, dict):
            _logger.warning(
                "i18n: '%s' 目录 %s 不是 JSON 对象，该语言的每次查找都会回退到 '%s'",
                locale, path, _SOURCE_LOCALE,
            )
            parsed = {}
        catalogs[locale] = parsed

    _catalogs = catalogs
    return _catalogs


def selfcheck() -> None:
    """自检目录可加载性；委托给 load() —
    Verify the catalogs are loadable; delegates to `load()`.

    zh 目录缺失/损坏时抛出 CatalogError（与 load() 一致）；en/vi 缺失时静默降级，
    与 load() 今天的行为一致。供 main.py 的 --selfcheck-i18n 以及未来 customer
    portal 的自检复用 —
    Raises CatalogError when `zh` is missing/broken, matching `load()`; `en`/`vi`
    degrade silently, also matching `load()`'s current behavior. Reused by
    main.py's `--selfcheck-i18n` flag and, eventually, the customer portal's own
    self-check.
    """
    load()


def _lookup(catalog: dict[str, Any], owner: str, subkey: str) -> str | None:
    """在一个语言目录中查找 owner.subkey 的字符串值 —
    Look up the string value for owner.subkey inside one locale's catalog.
    """
    owner_map = catalog.get(owner)
    if not isinstance(owner_map, dict):
        return None
    value = owner_map.get(subkey)
    # 空串是"有结构、无译文"（catalog-conventions.md:11 的 vi 形态），
    # 是未翻译的槽位而不是译文，必须回退而不是让界面变空白 —
    # An empty value is the "structure, no value" shape vi ships as: an
    # untranslated slot, not a translation. Falling back beats a blank screen.
    if not isinstance(value, str) or not value:
        return None
    return value


def t(key: str, lang: str, **params: str | int | float | bool | None) -> str:
    """按 lang 解析 key 并渲染 {param}；load() 成功后永不抛出 —
    Resolve `key` for `lang` and render it; never raises once load() has succeeded.

    zh 目录本身缺失/损坏时 load() 抛 CatalogError 并穿过这里，这是 AD-10 设计的唯一
    致命情形，由 Story 1.3 的启动守卫捕获 —
    A broken `zh` catalog file raises CatalogError through this function: AD-10's
    one deliberate fatal case, caught by Story 1.3's startup guard.

    lang 是裸目录码（zh/en/vi），`en-US` 这类 BCP-47 标签在这里不解析，会全部回退
    到 zh 且没有任何报错（FR22 在上游校验）—
    `lang` is a bare catalog code; a BCP-47 tag misses every lookup silently.

    params 值是 JSON 标量（AD-7）；占位符只能是裸名字，属性访问/下标/转换/格式规格
    一律走降级路径。回退链：lang 值 -> zh 值 -> 原始 key —
    Params are JSON scalars; placeholders are bare names only. Fallback chain:
    lang value -> zh value -> raw key.
    """
    catalogs = load()
    owner, _, subkey = key.partition(".")

    zh_catalog = catalogs.get(_SOURCE_LOCALE, {})
    lang_catalog = catalogs.get(lang, {})

    value = _lookup(lang_catalog, owner, subkey)
    # 请求的就是源语言时，zh 回退在这一步之前就已经用尽 —
    # When the requested locale is the source locale the zh fallback below is
    # already exhausted before it is tried.
    used_zh = lang == _SOURCE_LOCALE
    if value is None:
        value = _lookup(zh_catalog, owner, subkey)
        used_zh = True
    if value is None:
        return key

    try:
        return _FORMATTER.vformat(value, (), params)
    except Exception:
        # 读边界永不抛出，连参数自身 __format__/__str__ 的异常也要吞下；
        # 但界面上出现原始 key 时必须留下一条线索 —
        # A read boundary never raises, but a raw key on screen needs a trail.
        _logger.debug("i18n: 渲染失败，key=%s lang=%s", key, lang, exc_info=True)

    # 上面渲染的已经是 zh 值，再取一次只会重复同一次失败 —
    # The value rendered above was already the zh one; re-fetching repeats it.
    if used_zh:
        return key

    zh_value = _lookup(zh_catalog, owner, subkey)
    if zh_value is not None:
        try:
            return _FORMATTER.vformat(zh_value, (), params)
        except Exception:
            _logger.debug("i18n: zh 回退渲染同样失败，key=%s", key, exc_info=True)

    return key
