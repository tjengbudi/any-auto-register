"""共享的、轻量的 keyed raise/log 辅助函数 —— 只依赖 i18n.t，不依赖 curl_cffi，
因此本平台目录下的每个文件都可以在模块顶层正常 import，无需惰性导入 ——
Shared, lightweight keyed raise/log helpers -- depends only on i18n.t, not
curl_cffi, so every file in this platform package can import it normally at
module scope, with no lazy/function-scoped import needed.
"""
from __future__ import annotations

from i18n import t


def _raise_keyed(exc_cls, key: str, **params) -> None:
    # AD-17: 异常携带 i18n_key/i18n_params，供 application/tasks.py 的 _exc_key 转发 —
    # AD-17: the exception carries i18n_key/i18n_params for application/tasks.py's
    # _exc_key to forward at the catch site.
    exc = exc_cls(t(key, "zh", **params))
    exc.i18n_key = key
    exc.i18n_params = params
    raise exc


def _emit_log_key(log, log_key, key: str, **params) -> None:
    if log_key is not None:
        log_key(key, params)  # positional (key, dict) -- not **params
    else:
        log(t(key, "zh", **params))
