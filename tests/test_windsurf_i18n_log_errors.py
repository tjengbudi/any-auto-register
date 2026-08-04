"""story 4.8 -- windsurf's first-ever keyed-logging mechanism and keyed
raise-site coverage.

Covers the I/O & Edge-Case Matrix from this story's spec
(`_bmad-output/implementation-artifacts/spec-4-8-windsurf.md`):
  - `WindsurfClient.log_key` wired -- calls the sink positionally with
    (key, dict);
  - `WindsurfClient.log_key` unwired -- falls back to rendering the
    identical pre-migration Chinese string via `self.log`;
  - `WindsurfBrowserRegister.log_key` wired vs unwired -- the class's
    first-ever keyed-logging mechanism;
  - `WindsurfProtocolMailboxWorker.__init__`'s `log_key_fn` wiring reaches
    `self.client._log_key_fn` (`WindsurfClient` embedded in the worker);
  - a windsurf raise-site test asserting `_raise_keyed`'s exception carries
    `.i18n_key`/`.i18n_params` and `str(exc)` renders the `zh` text;
  - the duplicate-text edge case: `WindsurfBrowserRegister._extract_code`
    and `WindsurfProtocolMailboxWorker._extract_code` share the identical
    OTP-extraction-failure text and therefore the same minted key.

Mirrors tests/test_kiro_i18n_log_errors.py's scope discipline: one test per
distinct mechanism, not one test per call site. No test makes a network call
or touches Playwright/Camoufox.
"""
from __future__ import annotations

import pytest

from i18n import t
from platforms.windsurf import browser_register as browser_register_module
from platforms.windsurf.core import WindsurfClient
from platforms.windsurf.protocol_mailbox import WindsurfProtocolMailboxWorker


# --- WindsurfClient.log_key -- wired vs unwired ---------------------------
# WindsurfClient's first-ever keyed-logging mechanism.


def test_windsurf_client_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    client = WindsurfClient(
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    client.log_key("windsurf.7a91e427")

    assert calls == [("windsurf.7a91e427", {})]


def test_windsurf_client_log_key_wired_forwards_params_positionally():
    calls: list[tuple[str, dict]] = []
    client = WindsurfClient(log_key_fn=lambda key, params: calls.append((key, params)))

    client.log_key("windsurf.0cf7bbe1", email="a@b.com")

    assert calls == [("windsurf.0cf7bbe1", {"email": "a@b.com"})]


def test_windsurf_client_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    client = WindsurfClient(log_fn=plain_calls.append)

    client.log_key("windsurf.7a91e427")

    assert plain_calls == [t("windsurf.7a91e427", "zh")]


def test_windsurf_client_log_key_unwired_renders_params_in_fallback():
    plain_calls: list[str] = []
    client = WindsurfClient(log_fn=plain_calls.append)

    client.log_key("windsurf.0cf7bbe1", email="a@b.com")

    assert plain_calls == [t("windsurf.0cf7bbe1", "zh", email="a@b.com")]


def test_windsurf_client_constructed_directly_defaults_log_key_fn_to_none():
    client = WindsurfClient()

    assert client._log_key_fn is None


# --- WindsurfBrowserRegister.log_key -- wired vs unwired ------------------
# WindsurfBrowserRegister's first-ever keyed-logging mechanism.


def test_browser_register_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    worker = browser_register_module.WindsurfBrowserRegister(
        headless=True,
        proxy=None,
        otp_callback=None,
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    worker.log_key("windsurf.42ca2eab")

    assert calls == [("windsurf.42ca2eab", {})]


def test_browser_register_log_key_wired_forwards_params_positionally():
    calls: list[tuple[str, dict]] = []
    worker = browser_register_module.WindsurfBrowserRegister(
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    worker.log_key("windsurf.3dfa2d66", code="123456")

    assert calls == [("windsurf.3dfa2d66", {"code": "123456"})]


def test_browser_register_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    worker = browser_register_module.WindsurfBrowserRegister(log_fn=plain_calls.append)

    worker.log_key("windsurf.42ca2eab")

    assert plain_calls == [t("windsurf.42ca2eab", "zh")]


def test_browser_register_constructed_directly_defaults_log_key_fn_to_none():
    worker = browser_register_module.WindsurfBrowserRegister()

    assert worker._log_key_fn is None


# --- WindsurfProtocolMailboxWorker wiring reaches self.client._log_key_fn -


def test_protocol_mailbox_worker_wires_log_key_fn_onto_client():
    def sink(key, params):
        pass

    worker = WindsurfProtocolMailboxWorker(log_key_fn=sink)

    assert worker.client._log_key_fn is sink
    assert worker._log_key_fn is sink


def test_protocol_mailbox_worker_defaults_log_key_fn_to_none():
    worker = WindsurfProtocolMailboxWorker()

    assert worker.client._log_key_fn is None
    assert worker._log_key_fn is None


# --- windsurf raise sites -- _raise_keyed's exception shape ---------------
# windsurf's first-ever keyed raise-site coverage. `_extract_code` is a
# staticmethod that never touches Playwright or the network, so it is safe
# to call directly.


def test_browser_register_extract_code_raises_keyed_exception_with_params():
    with pytest.raises(RuntimeError) as exc_info:
        browser_register_module.WindsurfBrowserRegister._extract_code("no digits here")

    assert exc_info.value.i18n_key == "windsurf.fc3d5c97"
    assert exc_info.value.i18n_params == {"snippet": "no digits here"}
    assert str(exc_info.value) == t("windsurf.fc3d5c97", "zh", snippet="no digits here")


def test_browser_register_extract_code_returns_match_without_raising():
    assert browser_register_module.WindsurfBrowserRegister._extract_code("code: 123456!") == "123456"


def test_protocol_mailbox_worker_extract_code_shares_key_with_browser_register():
    # Duplicate-text edge case: browser_register.py's WindsurfBrowserRegister
    # and protocol_mailbox.py's WindsurfProtocolMailboxWorker both raise the
    # identical OTP-extraction-failure text and must share one minted key.
    with pytest.raises(RuntimeError) as exc_info:
        WindsurfProtocolMailboxWorker._extract_code("no digits here")

    assert exc_info.value.i18n_key == "windsurf.fc3d5c97"
    assert exc_info.value.i18n_params == {"snippet": "no digits here"}
    assert str(exc_info.value) == t("windsurf.fc3d5c97", "zh", snippet="no digits here")
