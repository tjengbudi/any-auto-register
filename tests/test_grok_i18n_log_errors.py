"""story 4.12 -- grok's first-ever keyed-logging mechanism and keyed
raise-site coverage.

Covers the I/O & Edge-Case Matrix from this story's spec
(`_bmad-output/implementation-artifacts/spec-4-12-grok-and-cerebras.md`):
  - `GrokRegister.log_key` wired vs unwired -- the class's first-ever
    keyed-logging mechanism;
  - `GrokBrowserRegister.log_key` wired vs unwired;
  - `GrokProtocolMailboxWorker.__init__`'s `log_key_fn` wiring reaches
    `self.client._log_key_fn` (`GrokRegister` embedded in the worker);
  - the within-platform duplicate-text edge case: `"未获取到验证码"` is raised
    both in `browser_register.py`'s `GrokBrowserRegister.run` and in
    `protocol_mailbox.py`'s `GrokProtocolMailboxWorker.run`, and both must
    share the same minted key (`grok.13939cce`);
  - a grok raise-site test asserting `_raise_keyed`'s exception carries
    `.i18n_key`/`.i18n_params` and `str(exc)` renders the `zh` text;
  - `register_with_browser_oauth`'s `log_key` kwarg threads into both its
    own direct `log_fn`/`log_key` sites and its raise site, with no
    internal register client constructed (only `OAuthBrowser`);
  - `grok/plugin.py`'s `execute_action` raise site;
  - the untouched boundary: grok never reuses another platform's key even
    for identical text (multiple platforms share several literal Chinese
    strings, e.g. tavily's "未获取到验证码").

Mirrors tests/test_tavily_i18n_log_errors.py's scope discipline: one test
per distinct mechanism, not one test per call site. No test makes a network
call or touches Playwright/Camoufox.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from i18n import t
from platforms.grok.core import GrokRegister
from platforms.grok.plugin import GrokPlatform
from platforms.grok.protocol_mailbox import GrokProtocolMailboxWorker
from platforms.grok import browser_oauth as browser_oauth_module
from platforms.grok import browser_register as browser_register_module

_PLATFORM_DIR = Path(__file__).resolve().parent.parent / "platforms" / "grok"


class _FakeOAuthBrowser:
    """Minimal OAuthBrowser double: no Playwright, no network."""

    def __init__(self, *, proxy=None, headless=False, chrome_user_data_dir="", chrome_cdp_url="", log_fn=print, log_key_fn=None):
        self.log_fn = log_fn
        self.log_key_fn = log_key_fn

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def goto(self, *args, **kwargs):
        pass

    def try_click_provider(self, provider):
        return True

    def auto_select_google_account(self):
        pass

    def wait_for_cookie_value(self, *args, **kwargs):
        return ""

    def cookie_value(self, *args, **kwargs):
        return ""


# --- GrokRegister.log_key -- wired vs unwired -------------------------------
# GrokRegister's first-ever keyed-logging mechanism.


def test_grok_register_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    client = GrokRegister(
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    client.log_key("grok.f6167694")

    assert calls == [("grok.f6167694", {})]


def test_grok_register_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    client = GrokRegister(log_fn=plain_calls.append)

    client.log_key("grok.f6167694")

    assert plain_calls == [t("grok.f6167694", "zh")]


def test_grok_register_constructed_directly_defaults_log_key_fn_to_none():
    client = GrokRegister()

    assert client._log_key_fn is None


# --- GrokBrowserRegister.log_key -- wired vs unwired ------------------------


def test_browser_register_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    worker = browser_register_module.GrokBrowserRegister(
        headless=True,
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    worker.log_key("grok.e3386d6c")

    assert calls == [("grok.e3386d6c", {})]


def test_browser_register_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    worker = browser_register_module.GrokBrowserRegister(headless=True, log_fn=plain_calls.append)

    worker.log_key("grok.e3386d6c")

    assert plain_calls == [t("grok.e3386d6c", "zh")]


def test_browser_register_constructed_directly_defaults_log_key_fn_to_none():
    worker = browser_register_module.GrokBrowserRegister(headless=True)

    assert worker._log_key_fn is None


# --- GrokProtocolMailboxWorker wiring reaches self.client._log_key_fn ------


def test_protocol_mailbox_worker_wires_log_key_fn_onto_client():
    def sink(key, params):
        pass

    worker = GrokProtocolMailboxWorker(log_key_fn=sink)

    assert worker.client._log_key_fn is sink
    assert worker._log_key_fn is sink


def test_protocol_mailbox_worker_defaults_log_key_fn_to_none():
    worker = GrokProtocolMailboxWorker()

    assert worker.client._log_key_fn is None
    assert worker._log_key_fn is None


# --- within-platform duplicate-text edge case -------------------------------
# "未获取到验证码" is raised both by GrokBrowserRegister.run (browser_register.py)
# and by GrokProtocolMailboxWorker.run (protocol_mailbox.py); both must share
# the same minted key.


def test_protocol_mailbox_worker_missing_otp_raises_keyed_exception(monkeypatch):
    worker = GrokProtocolMailboxWorker()
    # step1/2/3/4 talk to the real Grok/x.ai servers; stub the ones reached
    # before the "未获取到验证码" check so this test stays network-free.
    monkeypatch.setattr(worker.client, "step1_send_otp", lambda email: None)

    with pytest.raises(RuntimeError) as exc_info:
        worker.run(email="a@b.com", otp_callback=lambda: "")

    assert exc_info.value.i18n_key == "grok.13939cce"
    assert exc_info.value.i18n_params == {}
    assert str(exc_info.value) == t("grok.13939cce", "zh")


def test_browser_register_shares_the_same_missing_otp_key():
    # GrokBrowserRegister.run's equivalent raise sits deep inside a
    # Camoufox-driven flow that cannot run without a real browser; verify
    # the shared key at the source level instead, mirroring the duplicate
    # text's presence in both files.
    source = (_PLATFORM_DIR / "browser_register.py").read_text(encoding="utf-8")
    assert '_raise_keyed(RuntimeError, "grok.13939cce")' in source
    assert t("grok.13939cce", "zh") == "未获取到验证码"


# --- register_with_browser_oauth: log_fn/log_key sites + raise site --------
# grok's free function constructs no internal register client, only
# OAuthBrowser, unlike other platforms' equivalents.


def test_register_with_browser_oauth_emits_keyed_logs_and_keyed_raise(monkeypatch):
    monkeypatch.setattr(browser_oauth_module, "OAuthBrowser", _FakeOAuthBrowser)
    calls: list[tuple[str, dict]] = []

    with pytest.raises(RuntimeError) as exc_info:
        browser_oauth_module.register_with_browser_oauth(
            oauth_provider="",
            email_hint="a@b.com",
            timeout=1,
            log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
            log_key=lambda key, params: calls.append((key, params)),
            chrome_user_data_dir="",
            chrome_cdp_url="",
        )

    expected_method_text = browser_oauth_module.browser_login_method_text("")
    assert ("grok.a45d8569", {"method_text": expected_method_text, "timeout": 1}) in calls
    assert ("grok.18555deb", {"email_hint": "a@b.com"}) in calls
    assert exc_info.value.i18n_key == "grok.64764871"
    assert exc_info.value.i18n_params == {"timeout": 1}
    assert str(exc_info.value) == t("grok.64764871", "zh", timeout=1)


def test_register_with_browser_oauth_unwired_falls_back_to_rendered_log(monkeypatch):
    monkeypatch.setattr(browser_oauth_module, "OAuthBrowser", _FakeOAuthBrowser)
    plain_calls: list[str] = []

    with pytest.raises(RuntimeError):
        browser_oauth_module.register_with_browser_oauth(
            oauth_provider="",
            email_hint="",
            timeout=1,
            log_fn=plain_calls.append,
            chrome_user_data_dir="",
            chrome_cdp_url="",
        )

    expected_method_text = browser_oauth_module.browser_login_method_text("")
    assert t("grok.a45d8569", "zh", method_text=expected_method_text, timeout=1) in plain_calls


# --- grok/plugin.py's execute_action raise site -----------------------------


def test_execute_action_unknown_action_raises_keyed_exception():
    # __new__ without __init__: execute_action's raise site closes over no
    # instance state before it fires.
    platform = object.__new__(GrokPlatform)

    with pytest.raises(NotImplementedError) as exc_info:
        platform.execute_action("bogus", None, {})

    assert exc_info.value.i18n_key == "grok.701d383a"
    assert exc_info.value.i18n_params == {"action_id": "bogus"}
    assert str(exc_info.value) == t("grok.701d383a", "zh", action_id="bogus")


# --- untouched boundaries ----------------------------------------------------


def test_grok_never_reuses_another_platforms_key():
    # Separate namespaces: near-identical text on either side still mints
    # its own key (spec AC: "no cross-platform key sharing").
    for filename in ("core.py", "browser_oauth.py", "browser_register.py", "protocol_mailbox.py", "plugin.py"):
        source = (_PLATFORM_DIR / filename).read_text(encoding="utf-8")
        for other in ("tavily.", "cursor.", "cerebras.", "trae.", "anything."):
            assert other not in source
