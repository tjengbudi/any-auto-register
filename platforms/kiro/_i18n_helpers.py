"""共享的、轻量的 keyed log 辅助函数 —— 只依赖 i18n.t，不依赖 camoufox，
因此本平台目录下的每个文件都可以在模块顶层正常 import，无需惰性导入 ——
Shared, lightweight keyed log helper -- depends only on i18n.t, not
camoufox, so every file in this platform package can import it normally at
module scope, with no lazy/function-scoped import needed.

只有 _emit_log_key，没有 _raise_keyed —— 本story涉及的范围内没有 raise 站点；
第一个铸键 raise 站点由未来的 kiro story (4.7) 落地时再加进来 ——
Only _emit_log_key, no _raise_keyed -- nothing in this story's scope raises;
whichever future kiro story mints the first raise site (4.7) adds
_raise_keyed to this same module then.
"""
from __future__ import annotations

from i18n import t


def _emit_log_key(log, log_key, key: str, **params) -> None:
    if log_key is not None:
        log_key(key, params)  # positional (key, dict) -- not **params
    else:
        log(t(key, "zh", **params))
