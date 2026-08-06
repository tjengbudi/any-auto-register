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
  6. regression: run()/_retry_oauth_fresh_browser() must thread
     self._log_key_fn (the raw (key, dict) callable) into the free
     helper functions' log_key parameter, never self.log_key (the bound
     wrapper) -- _emit_log_key always invokes log_key(key, params) with
     params as one positional dict, which the wrapper's (self, key,
     **params) signature cannot accept.
  7. RegistrationEngine._set_error -- a newly-migrated result.error_message
     authoring site renders through the keyed catalog and forwards
     i18n_key/i18n_params onto the result, mirroring _raise_keyed.
  8. a newly-migrated dict "text" default (_submit_otp_via_page's
     empty-code early return) renders through the keyed catalog instead
     of a raw Chinese literal.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from i18n import t
from platforms.chatgpt import browser_register as browser_register_module
from platforms.chatgpt._i18n_helpers import _emit_log_key
from platforms.chatgpt.payment import _fetch_usage_data
from platforms.chatgpt.plugin import _assert_complete_oauth_callback
from platforms.chatgpt.register import RegistrationEngine, RegistrationResult


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


# --- 6. regression: run()/_retry_oauth_fresh_browser() must thread ------
# self._log_key_fn (the raw sink), never self.log_key (the bound wrapper),
# into a free helper function's log_key parameter.


def test_emit_log_key_rejects_the_bound_wrapper_method():
    """Reproduces the crash this story fixes: _emit_log_key always calls
    log_key(key, params) with params as one positional dict. A bound
    `log_key(self, key, **params)` method cannot accept that shape.
    """
    calls: list[tuple[str, dict]] = []
    worker = browser_register_module.ChatGPTBrowserRegister(
        headless=True,
        proxy=None,
        otp_callback=None,
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    with pytest.raises(TypeError):
        _emit_log_key(worker.log, worker.log_key, "chatgpt.1d89a161")


def test_emit_log_key_accepts_the_raw_log_key_fn():
    """The fixed shape: threading self._log_key_fn (not self.log_key) through
    a free helper function's log_key parameter works end-to-end.
    """
    calls: list[tuple[str, dict]] = []
    worker = browser_register_module.ChatGPTBrowserRegister(
        headless=True,
        proxy=None,
        otp_callback=None,
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    _emit_log_key(worker.log, worker._log_key_fn, "chatgpt.1d89a161")

    assert calls == [("chatgpt.1d89a161", {})]


def test_run_and_retry_oauth_fresh_browser_thread_the_raw_log_key_fn():
    """Locks down the actual fix at the two call sites named in the story:
    run() and _retry_oauth_fresh_browser() must pass self._log_key_fn into
    _browser_registration_flow/_do_codex_oauth's log_key parameter, not the
    self.log_key wrapper -- inspecting source is the only way to pin this
    without driving a real Camoufox browser.
    """
    import inspect

    run_source = inspect.getsource(browser_register_module.ChatGPTBrowserRegister.run)
    retry_source = inspect.getsource(
        browser_register_module.ChatGPTBrowserRegister._retry_oauth_fresh_browser
    )
    for source in (run_source, retry_source):
        assert "self._log_key_fn" in source
        assert "self.log_key,\n" not in source


# --- 7. RegistrationEngine._set_error -------------------------------------
# a newly-migrated result.error_message authoring site.


def test_registration_engine_set_error_renders_keyed_text_no_params():
    engine = object.__new__(RegistrationEngine)
    result = RegistrationResult(success=False)

    engine._set_error(result, "chatgpt.ba523ab8")  # "创建邮箱失败"

    assert result.error_message == t("chatgpt.ba523ab8", "zh")
    assert result.i18n_key == "chatgpt.ba523ab8"
    assert result.i18n_params == {}


def test_registration_engine_set_error_renders_keyed_text_with_params():
    engine = object.__new__(RegistrationEngine)
    result = RegistrationResult(success=False)

    engine._set_error(result, "chatgpt.ec914607", location="CN")

    assert result.error_message == t("chatgpt.ec914607", "zh", location="CN")
    assert result.i18n_key == "chatgpt.ec914607"
    assert result.i18n_params == {"location": "CN"}


# --- 8. a newly-migrated dict "text" default -------------------------------


def test_submit_otp_via_page_empty_code_uses_keyed_text_default():
    page = SimpleNamespace(url="https://chatgpt.com/onboarding")

    result = browser_register_module._submit_otp_via_page(page, "", lambda message: None)

    assert result == {
        "ok": False,
        "status": 400,
        "url": page.url,
        "data": None,
        "text": t("chatgpt.88b0dec0", "zh"),
    }
