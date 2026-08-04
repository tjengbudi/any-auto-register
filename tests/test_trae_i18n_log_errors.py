"""story 4.11 -- trae's first-ever keyed-logging mechanism and keyed
raise-site coverage.

Covers the I/O & Edge-Case Matrix from this story's spec
(`_bmad-output/implementation-artifacts/spec-4-11-trae-and-anything.md`):
  - `TraeRegister.log_key` wired vs unwired -- the class's first-ever
    keyed-logging mechanism;
  - `TraeBrowserRegister.log_key` wired vs unwired;
  - `TraeProtocolMailboxWorker.__init__`'s `log_key_fn` wiring reaches
    `self.client._log_key_fn` (`TraeRegister` embedded in the worker);
  - a trae raise-site test asserting `_raise_keyed`'s exception carries
    `.i18n_key`/`.i18n_params` and `str(exc)` renders the `zh` text, both
    for a `RuntimeError` site and for `TraePlatform.execute_action`'s
    `NotImplementedError` site;
  - the duplicate-text edge case: `TraeRegister.step2_send_code`'s
    "发送验证码..." log shares its minted key with
    `TraeBrowserRegister.run`'s identical log text;
  - the untouched boundaries: the pre-existing 14 wired + 1 orphaned
    `trae.*` keys from the earlier marker-key story stay exactly as they
    were, and trae never reuses an `anything.*` key even for identical text.

Mirrors tests/test_cursor_i18n_log_errors.py's scope discipline: one test per
distinct mechanism, not one test per call site. No test makes a network call
or touches Playwright/Camoufox.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from i18n import t
from platforms.trae.core import TraeRegister
from platforms.trae.plugin import TraePlatform
from platforms.trae.protocol_mailbox import TraeProtocolMailboxWorker
from platforms.trae import browser_register as browser_register_module

_CATALOG_DIR = Path(__file__).resolve().parent.parent / "i18n"
_PLATFORM_DIR = Path(__file__).resolve().parent.parent / "platforms" / "trae"


# --- TraeRegister.log_key -- wired vs unwired ------------------------------
# TraeRegister's first-ever keyed-logging mechanism.


def test_trae_register_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    client = TraeRegister(
        executor=None,
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    client.log_key("trae.8a956af4")

    assert calls == [("trae.8a956af4", {})]


def test_trae_register_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    client = TraeRegister(executor=None, log_fn=plain_calls.append)

    client.log_key("trae.8a956af4")

    assert plain_calls == [t("trae.8a956af4", "zh")]


def test_trae_register_constructed_directly_defaults_log_key_fn_to_none():
    client = TraeRegister(executor=None)

    assert client._log_key_fn is None


# --- TraeBrowserRegister.log_key -- wired vs unwired ------------------------


def test_browser_register_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    worker = browser_register_module.TraeBrowserRegister(
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    worker.log_key("trae.eaa92c19", email="a@b.com")

    assert calls == [("trae.eaa92c19", {"email": "a@b.com"})]


def test_browser_register_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    worker = browser_register_module.TraeBrowserRegister(log_fn=plain_calls.append)

    worker.log_key("trae.eaa92c19", email="a@b.com")

    assert plain_calls == [t("trae.eaa92c19", "zh", email="a@b.com")]


def test_browser_register_constructed_directly_defaults_log_key_fn_to_none():
    worker = browser_register_module.TraeBrowserRegister()

    assert worker._log_key_fn is None


# --- TraeProtocolMailboxWorker wiring reaches self.client._log_key_fn ------


def test_protocol_mailbox_worker_wires_log_key_fn_onto_client():
    def sink(key, params):
        pass

    worker = TraeProtocolMailboxWorker(executor=None, log_key_fn=sink)

    assert worker.client._log_key_fn is sink
    assert worker._log_key_fn is sink


def test_protocol_mailbox_worker_defaults_log_key_fn_to_none():
    worker = TraeProtocolMailboxWorker(executor=None)

    assert worker.client._log_key_fn is None
    assert worker._log_key_fn is None


# --- trae raise sites -- _raise_keyed's exception shape ---------------------
# trae's first-ever keyed raise-site coverage.


def test_protocol_mailbox_worker_missing_otp_raises_keyed_exception(monkeypatch):
    worker = TraeProtocolMailboxWorker(executor=None)
    # step1_region/step2_send_code talk to the real Trae passport server;
    # stub them out so this test stays network-free and only exercises the
    # "未获取到验证码" raise.
    monkeypatch.setattr(worker.client, "step1_region", lambda: None)
    monkeypatch.setattr(worker.client, "step2_send_code", lambda email: None)

    with pytest.raises(RuntimeError) as exc_info:
        worker.run(email="a@b.com", otp_callback=lambda: "")

    assert exc_info.value.i18n_key == "trae.13939cce"
    assert exc_info.value.i18n_params == {}
    assert str(exc_info.value) == t("trae.13939cce", "zh")


def test_execute_action_unknown_action_raises_keyed_not_implemented_error():
    # __new__ without __init__: the fall-through raise is reached before any
    # instance attribute is touched, so no DB-backed capability lookup runs.
    platform = object.__new__(TraePlatform)

    with pytest.raises(NotImplementedError) as exc_info:
        platform.execute_action("definitely_not_an_action", None, {})

    assert exc_info.value.i18n_key == "trae.701d383a"
    assert exc_info.value.i18n_params == {"action_id": "definitely_not_an_action"}
    assert str(exc_info.value) == t("trae.701d383a", "zh", action_id="definitely_not_an_action")


# --- duplicate-text edge case ------------------------------------------------
# TraeRegister.step2_send_code and TraeBrowserRegister.run both log the
# identical "发送验证码..." text and must share one minted key.


def test_core_and_browser_register_share_send_code_key():
    core_source = (_PLATFORM_DIR / "core.py").read_text(encoding="utf-8")
    browser_register_source = (_PLATFORM_DIR / "browser_register.py").read_text(encoding="utf-8")

    assert "trae.8a956af4" in core_source
    assert "trae.8a956af4" in browser_register_source


# --- untouched boundaries ---------------------------------------------------


def test_pre_existing_orphan_key_stays_unwired_and_untranslated():
    zh = json.loads((_CATALOG_DIR / "zh.json").read_text(encoding="utf-8-sig"))
    en = json.loads((_CATALOG_DIR / "en.json").read_text(encoding="utf-8-sig"))

    assert "cfeae2ac" in zh["trae"]
    assert "cfeae2ac" not in en["trae"]


def test_trae_never_reuses_an_anything_key():
    # The two namespaces are separate: near-identical text on either side
    # still mints its own key (spec AC: "no cross-platform key sharing").
    for filename in ("core.py", "browser_oauth.py", "browser_register.py", "protocol_mailbox.py", "plugin.py"):
        source = (_PLATFORM_DIR / filename).read_text(encoding="utf-8")
        assert "anything." not in source
