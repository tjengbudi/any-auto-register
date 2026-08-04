"""story: platforms/chatgpt/* Chinese raise/log sites -> keyed i18n mechanism.

Mirrors tests/test_core_i18n_log_errors.py's scope discipline: one test per
distinct mechanism, not one test per call site.

Mechanisms covered:
  1. a raise site fires with i18n_key/i18n_params attached, no params;
  2. a raise site fires with i18n_key/i18n_params attached, with params;
  3. ChatGPTBrowserRegister.log_key -- wired (positional (key, dict) sink
     call) vs unwired (falls back to rendered zh text via self.log);
  4. a free-helper-function's log/log_key params via _emit_log_key --
     wired vs unwired, exercised through _select_phone_country_ui's
     early-return branch (which never touches `page`, so no Playwright
     fake is needed);
  5. RegistrationEngine._log_key -- wired vs unwired (falls back to
     ._log, which appends to .logs and calls .callback_logger).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from i18n import t
from platforms.chatgpt import browser_register as browser_register_module
from platforms.chatgpt.payment import _fetch_usage_data
from platforms.chatgpt.plugin import _assert_complete_oauth_callback
from platforms.chatgpt.register import RegistrationEngine


# --- 1. raise site, no params -------------------------------------------


def test_fetch_usage_data_raises_keyed_exception_without_params():
    account = SimpleNamespace(access_token="")

    with pytest.raises(ValueError) as exc_info:
        _fetch_usage_data(account)

    assert exc_info.value.i18n_key == "chatgpt.9fbc4659"
    assert exc_info.value.i18n_params == {}
    assert str(exc_info.value) == t("chatgpt.9fbc4659", "zh")


# --- 2. raise site, with params ------------------------------------------


def test_assert_complete_oauth_callback_raises_keyed_exception_with_params():
    with pytest.raises(RuntimeError) as exc_info:
        _assert_complete_oauth_callback({"account_id": "acct_123", "access_token": ""})

    assert exc_info.value.i18n_key == "chatgpt.eb25e25d"
    assert exc_info.value.i18n_params == {"missing": "access_token"}
    assert str(exc_info.value) == t("chatgpt.eb25e25d", "zh", missing="access_token")


# --- 3. ChatGPTBrowserRegister.log_key -- wired vs unwired ---------------


def test_browser_register_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    worker = browser_register_module.ChatGPTBrowserRegister(
        headless=True,
        proxy=None,
        otp_callback=None,
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    worker.log_key("chatgpt.1d89a161")

    assert calls == [("chatgpt.1d89a161", {})]


def test_browser_register_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    worker = browser_register_module.ChatGPTBrowserRegister(
        headless=True,
        proxy=None,
        otp_callback=None,
        log_fn=plain_calls.append,
    )

    worker.log_key("chatgpt.1d89a161")

    assert plain_calls == [t("chatgpt.1d89a161", "zh")]


# --- 4. free-helper-function log/log_key via _emit_log_key ---------------
# `_select_phone_country_ui`'s "can't identify country code" early return
# never touches `page`, so `page=None` is enough -- no Playwright fake needed.


def test_select_phone_country_ui_emits_log_key_when_wired():
    calls: list[tuple[str, dict]] = []

    result = browser_register_module._select_phone_country_ui(
        None,
        "",
        "",
        lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key=lambda key, params: calls.append((key, params)),
    )

    assert result is False
    assert calls == [("chatgpt.814efd3f", {})]


def test_select_phone_country_ui_falls_back_to_log_when_unwired():
    plain_calls: list[str] = []

    result = browser_register_module._select_phone_country_ui(
        None,
        "",
        "",
        plain_calls.append,
        log_key=None,
    )

    assert result is False
    assert plain_calls == [t("chatgpt.814efd3f", "zh")]


# --- 5. RegistrationEngine._log_key -- wired vs unwired -------------------


def _make_minimal_engine(*, log_key_fn=None, callback_logger=None) -> RegistrationEngine:
    # __init__ builds an HTTP client + OAuth manager; bypass it and set only
    # the attributes `_log`/`_log_key` actually touch.
    engine = object.__new__(RegistrationEngine)
    engine.logs = []
    engine.callback_logger = callback_logger or (lambda message: None)
    engine.task_uuid = None
    engine._log_key_fn = log_key_fn
    return engine


def test_registration_engine_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    engine = _make_minimal_engine(log_key_fn=lambda key, params: calls.append((key, params)))

    engine._log_key("chatgpt.3576aeea", status_code=200)

    assert calls == [("chatgpt.3576aeea", {"status_code": 200})]
    assert engine.logs == []


def test_registration_engine_log_key_unwired_falls_back_to_log():
    plain_calls: list[str] = []
    engine = _make_minimal_engine(callback_logger=plain_calls.append)

    engine._log_key("chatgpt.3576aeea", status_code=200)

    rendered = t("chatgpt.3576aeea", "zh", status_code=200)
    assert plain_calls == [rendered]
    assert len(engine.logs) == 1
    assert engine.logs[0].endswith(rendered)
