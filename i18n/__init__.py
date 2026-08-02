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

__all__ = ["t", "load", "selfcheck", "CatalogError", "LOCALES", "render_marker", "render_result"]

_logger = logging.getLogger(__name__)

# 语言解析由调用方完成，本模块从不猜测 lang —
# Callers resolve `lang` themselves; this module never guesses it (AD-3).

_SOURCE_LOCALE = "zh"
# en/vi 是翻译目标，回退目标始终是 zh —
# en/vi are the translation targets; the fallback target is always zh.
_TARGET_LOCALES = ("en", "vi")

# 公开的有序语言集合（源语言在前），供 main.py 打包提示等调用方使用 —
# The public ordered locale set (source first), exposed for callers like
# main.py's PyInstaller bundle-file hint.
LOCALES = (_SOURCE_LOCALE, *_TARGET_LOCALES)

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
        # 渲染沿用 JSON 自身的拼写，因为该值最终会被持久化为 JSON 再读出 —
        # Render using JSON's own spelling, since the value round-trips through
        # JSON storage: None -> null, bool -> true/false (checked before any
        # numeric branch, since bool is an int subclass), integral float ->
        # without its trailing .0. Everything else keeps today's str(value).
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
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


# story 3.6 新增：worker-thread 站点写入的标记字符串约定 —
# story 3.6 addition: the marker-string convention worker-thread sites write.
#
# 无请求上下文的 worker 线程（platforms/*/plugin.py、*/switch.py）不再在产生结果
# 的地方渲染，而是写入 json.dumps({"i18n_key", "i18n_params"})；读边界（已解析出
# lang 的地方）用 render_marker/render_result 在响应构建前统一渲染 ——
# Worker threads with no request context no longer render where a result is
# produced; they write json.dumps({"i18n_key", "i18n_params"}) instead, and a
# read boundary that already has `lang` renders it uniformly via
# render_marker/render_result before the response is built.
_MARKER_KEYS = frozenset({"i18n_key", "i18n_params"})

# 嵌套标记解析的深度上限，防止参数里循环/超深引用把渲染拖入无限递归 ——
# Depth cap for nested-marker resolution, guarding against a cyclic or overly
# deep param chain dragging the render into unbounded recursion.
_MAX_MARKER_DEPTH = 5


def _parse_marker(value: str) -> tuple[str, dict] | None:
    """把 value 解析为 (i18n_key, i18n_params)；形状不吻合时返回 None —
    Parse `value` into (i18n_key, i18n_params); returns None when the shape
    does not match exactly.

    "形状吻合"是精确匹配：解码后的对象必须恰好拥有 {"i18n_key", "i18n_params"}
    这两个键，不多也不少，i18n_key 必须是 str，i18n_params 必须是 dict —
    "Matches exactly" means an exact key set: the decoded object must have
    precisely the two keys `i18n_key` (str) and `i18n_params` (dict) -- no
    more, no fewer.

    这是刻意的精确形状匹配，不是类型收窄上的疏漏：一段碰巧解码成这个精确形状的
    字符串，即便不是任何标记生产站点写出来的，也会被当作标记渲染，这是设计使然 —
    This is deliberate exact-shape matching, not a type-narrowing gap: a
    string that happens to decode into this exact shape is rendered as a
    marker even when no marker-producing call site ever wrote it -- that is
    by design, not an accident.
    """
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict) or set(parsed.keys()) != _MARKER_KEYS:
        return None
    key = parsed["i18n_key"]
    params = parsed["i18n_params"]
    if not isinstance(key, str) or not isinstance(params, dict):
        return None
    return key, params


def render_marker(value: str, lang: str, *, _depth: int = 0) -> str:
    """把一个可能是标记字符串的 value 渲染为 lang 对应的文本 —
    Render a possibly-marker string `value` into `lang`'s text.

    只有 value 精确解析为 {"i18n_key": str, "i18n_params": dict} 时才会被当作标记；
    其余任何值（普通文本、不相关的 JSON、格式不吻合）原样返回，因此这个函数可以
    安全地套用在任意字符串上，不需要调用方先判断类型 ——
    Only a value that parses to exactly {"i18n_key": str, "i18n_params": dict}
    is treated as a marker; anything else (plain text, unrelated JSON, a
    mismatched shape) passes through unchanged, so this is safe to apply to
    any string without the caller pre-checking its shape.

    i18n_params 里的值只能是 JSON 标量（AD-7），所以一个标记只能嵌套在字符串类型
    的参数里；如果某个参数值本身是 dict/list（哪怕里面又装着一个标记形状的字符串），
    下面的参数循环不会解析它，会原样传给 t()。只有当渲染出的目录字符串里的占位符
    确实引用了这个参数名时，_StrictFormatter.format_field 已有的标量守卫才会拦下
    它，把整体渲染降级为裸 i18n_key；如果占位符压根没引用这个参数名，这个值会被
    悄悄忽略——两种情况下都不会把 Python repr 泄漏到界面上 —
    `i18n_params` values must be JSON scalars (AD-7), so a marker can only ever
    nest inside a string-typed param. A dict/list param value -- even one that
    itself contains a marker-shaped string -- is not resolved by the loop
    below; it passes through unchanged to `t()`. Only when the rendered
    catalog string's placeholder actually references that param name does
    `_StrictFormatter.format_field`'s existing scalar guard catch it and
    degrade the whole render to the bare `i18n_key`; if no placeholder
    references that param name, the value is silently ignored instead.
    Either way, no Python repr ever leaks into the rendered text.

    这个形状没有 sentinel 字段去区分"有意的标记"和"碰巧长成这样"：这不是说参数值
    永远不会误吻合（一个自家调用点把未校验的调用方字符串塞进 i18n_params，那个
    字符串本身仍可能巧合成标记形状），而是说每一个标记信封都由自家代码写出，
    因此没有第三方能生产这个信封形状；加一个 sentinel 字段去堵上参数值那层的
    巧合风险，会是一次协议形状变更，牵连到 Epic 4 的 detail_json key 路径和
    Epic 5 还没建的 customer portal，代价大于这个窄范围问题本身 —
    The shape carries no sentinel field distinguishing an intentional marker
    from a coincidental one. This is not a claim that a param value can never
    coincidentally collide -- a first-party call site can embed an unvalidated
    caller-supplied string into `i18n_params`, and that string can itself
    happen to be marker-shaped. It is a claim that every marker *envelope* is
    written by first-party code, so no third party can produce this envelope
    shape. Adding a sentinel to close the param-value collision case too would
    be a wire-shape change rippling into Epic 4's `detail_json` key path and
    Epic 5's not-yet-built customer portal, a cost this narrow scope does not
    justify.
    """
    if not isinstance(value, str):
        return value
    parsed = _parse_marker(value)
    if parsed is None:
        return value
    key, params = parsed
    if _depth >= _MAX_MARKER_DEPTH:
        # 深度耗尽时仍尝试渲染外层 key（不解析更深的嵌套参数），避免把未解码的
        # 标记 JSON 当作文本片段展示给用户 ——
        # Even at the depth cap, still render the outer key (without resolving
        # deeper-nested params) instead of showing the raw, undecoded marker
        # JSON as a text fragment.
        _logger.debug("i18n: 标记嵌套超过最大深度，key=%s", key)
        return t(key, lang)

    # i18n_params 的值本身可能又是一个标记字符串（cursor 组合模板的例子）；
    # 先自底向上解析成纯文本，再作为标量参数喂给 t() ——
    # A param value may itself be another marker string (the cursor
    # composition template). Resolve bottom-up into plain text first, then
    # feed the result to t() as a scalar param.
    resolved_params: dict[str, Any] = {}
    for param_key, param_value in params.items():
        if isinstance(param_value, str):
            resolved_params[param_key] = render_marker(param_value, lang, _depth=_depth + 1)
        else:
            resolved_params[param_key] = param_value

    try:
        return t(key, lang, **resolved_params)
    except TypeError:
        # i18n_params 里若有和 t() 形参同名的键（如 "lang"/"key"），** 展开会在
        # 进入 t() 之前抛出；退化到裸 key（而不是原始标记 JSON），跟 t() 自身
        # 用尽回退链后的最终形态一致 ——
        # A params key shadowing t()'s own parameter names raises at the **
        # expansion, before t() is even entered. Degrade to the bare key
        # (not the raw marker JSON) to match the shape of t()'s own
        # exhausted-fallback-chain result.
        _logger.debug("i18n: 标记参数与 t() 形参冲突，key=%s", key)
        return key


def render_result(value: Any, lang: str) -> Any:
    """递归遍历 dict/list，对遇到的每个字符串套用 render_marker —
    Recursively walk dicts/lists, applying render_marker to every string found.

    非字符串、非 dict/list 的值（数字、布尔、None、日期字符串等）原样返回 ——
    Non-string, non-dict/list values (numbers, booleans, None, date strings,
    etc.) pass through unchanged.
    """
    if isinstance(value, dict):
        return {k: render_result(v, lang) for k, v in value.items()}
    if isinstance(value, list):
        return [render_result(v, lang) for v in value]
    if isinstance(value, str):
        return render_marker(value, lang)
    return value
