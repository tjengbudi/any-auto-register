"""共享的 FastAPI 依赖 — Shared FastAPI dependencies.

`get_ui_language()` 是本故事新增的唯一读边界：每个请求只解析一次 `ui_language`，
渲染时把结果作为 `lang` 参数往下传，而不是每个渲染点各自查一次 config store
（AD-4）— The single new read boundary this story adds: `ui_language` is resolved
once per request, then threaded down as `lang`, instead of every render site
querying the config store on its own (AD-4).
"""
from __future__ import annotations

from core.config_store import config_store
from i18n import LOCALES, t


def get_ui_language() -> str:
    """解析当前请求的界面语言，校验并回退到 zh —
    Resolve the current request's UI language, validating and falling back to zh.

    与 application/config.py::ConfigService.get_config() 的回退逻辑保持一致：
    未设置或不在 LOCALES 中的值一律回退为 "zh" —
    Mirrors ConfigService.get_config()'s fallback: unset or out-of-LOCALES
    values fall back to "zh".
    """
    lang = config_store.get("ui_language", "zh")
    if lang not in LOCALES:
        return "zh"
    return lang


def render_detail(exc: Exception, lang: str) -> str:
    """渲染一个被捕获异常的 detail 文本 —— 优先用它携带的 i18n_key/i18n_params，
    否则退回 str(exc) —— Render the detail text for a caught exception,
    preferring its carried `i18n_key`/`i18n_params` and falling back to
    `str(exc)` when absent (AD-8, AD-17).

    `providers/`/`infrastructure/` 目前不携带 i18n_key，此处的回退分支就是它们
    今天已有的行为，直到 story 4.13 补上键为止 —
    `providers/`/`infrastructure/` carry no `i18n_key` yet, so the fallback
    branch is exactly their behavior today, forward-compatible with story
    4.13 without a second change here.
    """
    key = getattr(exc, "i18n_key", None)
    if not isinstance(key, str) or not key:
        return str(exc)
    params = getattr(exc, "i18n_params", None)
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return str(exc)
    # t() 的 AD-7 约定要求参数值必须是 JSON 标量；否则它自己的读边界会吞下格式化
    # 异常并回退到裸 key，把内部标识符暴露给用户，比 str(exc) 更糟 ——
    # t()'s AD-7 contract requires JSON-scalar param values; otherwise its own
    # read boundary swallows the formatting error and falls back to the bare
    # key, leaking an internal identifier to the user, which is worse than
    # str(exc).
    if not all(v is None or isinstance(v, (str, int, float, bool)) for v in params.values()):
        return str(exc)
    try:
        return t(key, lang, **params)
    except TypeError:
        # params 里若含有与 t() 形参同名的键（如 "lang"/"key"），** 展开会在
        # 进入 t() 之前就抛出 —— t() 自身的"读边界永不抛出"保证覆盖不到这里 —
        # A params key shadowing t()'s own parameter names (e.g. "lang"/"key")
        # raises at the ** expansion, before t()'s own never-raises guarantee
        # can apply.
        return str(exc)
