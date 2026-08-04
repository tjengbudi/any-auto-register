"""story 4.10 -- tavily's first-ever keyed-logging mechanism and keyed
raise-site coverage.

Covers the I/O & Edge-Case Matrix from this story's spec
(`_bmad-output/implementation-artifacts/spec-4-10-cursor-and-tavily.md`):
  - `TavilyRegister.log_key` wired vs unwired -- the class's first-ever
    keyed-logging mechanism;
  - `TavilyBrowserRegister.log_key` wired vs unwired;
  - `TavilyProtocolMailboxWorker.__init__`'s `log_key_fn` wiring reaches
    `self.client._log_key_fn` (`TavilyRegister` embedded in the worker);
  - the cross-file duplicate-text edge case: `_finalize_api_key` raises the
    identical "未找到 Tavily API Key" text as both a free function in
    `browser_oauth.py` and a class method in `browser_register.py`, and
    both must share the same minted key;
  - a tavily raise-site test asserting `_raise_keyed`'s exception carries
    `.i18n_key`/`.i18n_params` and `str(exc)` renders the `zh` text;
  - `tavily/plugin.py:91`'s raise-in-lambda `oauth_runner`, simplified from
    `(_ for _ in ()).throw(...)` to `_raise_keyed(...)`;
  - the untouched boundary: tavily never reuses a `cursor.*` key even for
    identical text (both platforms share several literal Chinese strings).

Mirrors tests/test_blink_i18n_log_errors.py's scope discipline: one test per
distinct mechanism, not one test per call site. No test makes a network call
or touches Playwright/Camoufox.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from i18n import t
from platforms.tavily.core import TavilyRegister
from platforms.tavily.plugin import TavilyPlatform
from platforms.tavily.protocol_mailbox import TavilyProtocolMailboxWorker
from platforms.tavily import browser_oauth as browser_oauth_module
from platforms.tavily import browser_register as browser_register_module

_PLATFORM_DIR = Path(__file__).resolve().parent.parent / "platforms" / "tavily"


class _FakePage:
    """Minimal page double: no Chinese content, no network."""

    def query_selector(self, selector):
        return None

    def content(self):
        return ""

    def goto(self, *args, **kwargs):
        raise RuntimeError("no network access in tests")


# --- TavilyRegister.log_key -- wired vs unwired ----------------------------
# TavilyRegister's first-ever keyed-logging mechanism.


def test_tavily_register_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    client = TavilyRegister(
        executor=None,
        captcha=None,
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    client.log_key("tavily.f6167694")

    assert calls == [("tavily.f6167694", {})]


def test_tavily_register_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    client = TavilyRegister(executor=None, captcha=None, log_fn=plain_calls.append)

    client.log_key("tavily.f6167694")

    assert plain_calls == [t("tavily.f6167694", "zh")]


def test_tavily_register_constructed_directly_defaults_log_key_fn_to_none():
    client = TavilyRegister(executor=None, captcha=None)

    assert client._log_key_fn is None


# --- TavilyBrowserRegister.log_key -- wired vs unwired ---------------------


def test_browser_register_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    worker = browser_register_module.TavilyBrowserRegister(
        captcha=None,
        headless=True,
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    worker.log_key("tavily.75567364")

    assert calls == [("tavily.75567364", {})]


def test_browser_register_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    worker = browser_register_module.TavilyBrowserRegister(captcha=None, headless=True, log_fn=plain_calls.append)

    worker.log_key("tavily.75567364")

    assert plain_calls == [t("tavily.75567364", "zh")]


def test_browser_register_constructed_directly_defaults_log_key_fn_to_none():
    worker = browser_register_module.TavilyBrowserRegister(captcha=None, headless=True)

    assert worker._log_key_fn is None


# --- TavilyProtocolMailboxWorker wiring reaches self.client._log_key_fn ---


def test_protocol_mailbox_worker_wires_log_key_fn_onto_client():
    def sink(key, params):
        pass

    worker = TavilyProtocolMailboxWorker(executor=None, captcha=None, log_key_fn=sink)

    assert worker.client._log_key_fn is sink
    assert worker._log_key_fn is sink


def test_protocol_mailbox_worker_defaults_log_key_fn_to_none():
    worker = TavilyProtocolMailboxWorker(executor=None, captcha=None)

    assert worker.client._log_key_fn is None
    assert worker._log_key_fn is None


# --- cross-file duplicate-text edge case -----------------------------------
# _finalize_api_key raises the identical "未找到 Tavily API Key" text as both
# a free function in browser_oauth.py and a class method in
# browser_register.py; both must share one minted key.


def test_browser_oauth_finalize_api_key_raises_keyed_exception():
    with pytest.raises(RuntimeError) as exc_info:
        browser_oauth_module._finalize_api_key(_FakePage(), timeout=0)

    assert exc_info.value.i18n_key == "tavily.465ac145"
    assert exc_info.value.i18n_params == {}
    assert str(exc_info.value) == t("tavily.465ac145", "zh")


def test_browser_register_finalize_api_key_shares_the_same_key():
    register = browser_register_module.TavilyBrowserRegister(captcha=None, headless=True, api_key_timeout=0)

    with pytest.raises(RuntimeError) as exc_info:
        register._finalize_api_key(_FakePage())

    assert exc_info.value.i18n_key == "tavily.465ac145"
    assert str(exc_info.value) == t("tavily.465ac145", "zh")


# --- tavily raise sites -- _raise_keyed's exception shape ------------------
# tavily's first-ever keyed raise-site coverage.


def test_protocol_mailbox_worker_missing_otp_raises_keyed_exception(monkeypatch):
    worker = TavilyProtocolMailboxWorker(executor=None, captcha=None)
    # step1/2/3 talk to the real Tavily/Auth0 servers; stub them out so this
    # test stays network-free and only exercises the "未获取到验证码" raise.
    monkeypatch.setattr(worker.client, "step1_authorize", lambda: "state")
    monkeypatch.setattr(worker.client, "step2_solve_captcha", lambda: "captcha-token")
    monkeypatch.setattr(worker.client, "step3_submit_email", lambda email, state, captcha_token: "challenge-state")

    with pytest.raises(RuntimeError) as exc_info:
        worker.run(email="a@b.com", password="pw", otp_callback=lambda: "")

    assert exc_info.value.i18n_key == "tavily.13939cce"
    assert exc_info.value.i18n_params == {}
    assert str(exc_info.value) == t("tavily.13939cce", "zh")


# --- tavily/plugin.py:91's raise-in-lambda oauth_runner --------------------


def test_protocol_oauth_adapter_oauth_runner_raises_keyed_exception():
    # __new__ without __init__: the adapter's oauth_runner lambda closes over
    # no instance state, so no DB-backed capability lookup runs.
    platform = object.__new__(TavilyPlatform)
    adapter = platform.build_protocol_oauth_adapter()

    with pytest.raises(RuntimeError) as exc_info:
        adapter.oauth_runner(None)

    assert exc_info.value.i18n_key == "tavily.de051424"
    assert exc_info.value.i18n_params == {}
    assert str(exc_info.value) == t("tavily.de051424", "zh")


# --- untouched boundaries ---------------------------------------------------


def test_tavily_never_reuses_a_cursor_key():
    # The two namespaces are separate: near-identical text on either side
    # still mints its own key (spec AC: "no cross-platform key sharing").
    for filename in ("core.py", "browser_oauth.py", "browser_register.py", "protocol_mailbox.py", "plugin.py"):
        source = (_PLATFORM_DIR / filename).read_text(encoding="utf-8")
        assert "cursor." not in source
