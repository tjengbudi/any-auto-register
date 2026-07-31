"""共享的 FastAPI 依赖 — Shared FastAPI dependencies.

`get_ui_language()` 是本故事新增的唯一读边界：每个请求只解析一次 `ui_language`，
渲染时把结果作为 `lang` 参数往下传，而不是每个渲染点各自查一次 config store
（AD-4）— The single new read boundary this story adds: `ui_language` is resolved
once per request, then threaded down as `lang`, instead of every render site
querying the config store on its own (AD-4).
"""
from __future__ import annotations

from core.config_store import config_store
from i18n import LOCALES


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
