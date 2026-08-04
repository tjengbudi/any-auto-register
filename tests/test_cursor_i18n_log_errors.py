"""story 4.10 -- cursor's first-ever keyed-logging mechanism and keyed
raise-site coverage.

Covers the I/O & Edge-Case Matrix from this story's spec
(`_bmad-output/implementation-artifacts/spec-4-10-cursor-and-tavily.md`):
  - `CursorRegister.log_key` wired vs unwired -- the class's first-ever
    keyed-logging mechanism;
  - `CursorBrowserRegister.log_key` wired vs unwired;
  - `CursorProtocolMailboxWorker.__init__`'s `log_key_fn` wiring reaches
    `self.client._log_key_fn` (`CursorRegister` embedded in the worker);
  - a cursor raise-site test asserting `_raise_keyed`'s exception carries
    `.i18n_key`/`.i18n_params` and `str(exc)` renders the `zh` text, both
    for a `RuntimeError` site and for `CursorPlatform.execute_action`'s
    `NotImplementedError` site;
  - the duplicate-text edge case: `CursorProtocolMailboxWorker.run`'s
    "未获取到验证码" raise shares its minted key with
    `CursorBrowserRegister.run`'s identical raise text;
  - the untouched boundaries: the pre-existing 14 wired + 7 orphaned
    `cursor.*` keys from the earlier marker-key story stay exactly as they
    were, and cursor never reuses a `tavily.*` key even for identical text.

Mirrors tests/test_blink_i18n_log_errors.py's scope discipline: one test per
distinct mechanism, not one test per call site. No test makes a network call
or touches Playwright/Camoufox.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from i18n import t
from platforms.cursor.core import CursorRegister
from platforms.cursor.plugin import CursorPlatform
from platforms.cursor.protocol_mailbox import CursorProtocolMailboxWorker
from platforms.cursor import browser_register as browser_register_module

_CATALOG_DIR = Path(__file__).resolve().parent.parent / "i18n"


# --- CursorRegister.log_key -- wired vs unwired ---------------------------
# CursorRegister's first-ever keyed-logging mechanism.


def test_cursor_register_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    client = CursorRegister(
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    client.log_key("cursor.f6167694")

    assert calls == [("cursor.f6167694", {})]


def test_cursor_register_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    client = CursorRegister(log_fn=plain_calls.append)

    client.log_key("cursor.f6167694")

    assert plain_calls == [t("cursor.f6167694", "zh")]


def test_cursor_register_constructed_directly_defaults_log_key_fn_to_none():
    client = CursorRegister()

    assert client._log_key_fn is None


# --- CursorBrowserRegister.log_key -- wired vs unwired ---------------------


def test_browser_register_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    worker = browser_register_module.CursorBrowserRegister(
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    worker.log_key("cursor.eaa92c19", email="a@b.com")

    assert calls == [("cursor.eaa92c19", {"email": "a@b.com"})]


def test_browser_register_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    worker = browser_register_module.CursorBrowserRegister(log_fn=plain_calls.append)

    worker.log_key("cursor.eaa92c19", email="a@b.com")

    assert plain_calls == [t("cursor.eaa92c19", "zh", email="a@b.com")]


def test_browser_register_constructed_directly_defaults_log_key_fn_to_none():
    worker = browser_register_module.CursorBrowserRegister()

    assert worker._log_key_fn is None


# --- CursorProtocolMailboxWorker wiring reaches self.client._log_key_fn ---


def test_protocol_mailbox_worker_wires_log_key_fn_onto_client():
    def sink(key, params):
        pass

    worker = CursorProtocolMailboxWorker(log_key_fn=sink)

    assert worker.client._log_key_fn is sink
    assert worker._log_key_fn is sink


def test_protocol_mailbox_worker_defaults_log_key_fn_to_none():
    worker = CursorProtocolMailboxWorker()

    assert worker.client._log_key_fn is None
    assert worker._log_key_fn is None


# --- cursor raise sites -- _raise_keyed's exception shape ------------------
# cursor's first-ever keyed raise-site coverage.


def test_protocol_mailbox_worker_missing_otp_raises_keyed_exception(monkeypatch):
    worker = CursorProtocolMailboxWorker()
    # step1/2/3 talk to the real Cursor auth server; stub them out so this
    # test stays network-free and only exercises the "未获取到验证码" raise.
    monkeypatch.setattr(worker.client, "step1_get_session", lambda: ("state", None))
    monkeypatch.setattr(worker.client, "step2_submit_email", lambda email, state_encoded: None)
    monkeypatch.setattr(worker.client, "step3_submit_password", lambda password, email, state_encoded, captcha_solver=None: None)

    with pytest.raises(RuntimeError) as exc_info:
        worker.run(email="a@b.com", otp_callback=lambda: "")

    assert exc_info.value.i18n_key == "cursor.13939cce"
    assert exc_info.value.i18n_params == {}
    assert str(exc_info.value) == t("cursor.13939cce", "zh")


def test_execute_action_unknown_action_raises_keyed_not_implemented_error():
    # __new__ without __init__: the fall-through raise is reached before any
    # instance attribute is touched, so no DB-backed capability lookup runs.
    platform = object.__new__(CursorPlatform)

    with pytest.raises(NotImplementedError) as exc_info:
        platform.execute_action("definitely_not_an_action", None, {})

    assert exc_info.value.i18n_key == "cursor.701d383a"
    assert exc_info.value.i18n_params == {"action_id": "definitely_not_an_action"}
    assert str(exc_info.value) == t("cursor.701d383a", "zh", action_id="definitely_not_an_action")


# --- duplicate-text edge case ----------------------------------------------
# CursorProtocolMailboxWorker.run and CursorBrowserRegister.run both raise
# the identical "未获取到验证码" text and must share one minted key.


def test_browser_register_and_protocol_mailbox_share_missing_otp_key(monkeypatch):
    worker = CursorProtocolMailboxWorker()
    monkeypatch.setattr(worker.client, "step1_get_session", lambda: ("state", None))
    monkeypatch.setattr(worker.client, "step2_submit_email", lambda email, state_encoded: None)
    monkeypatch.setattr(worker.client, "step3_submit_password", lambda password, email, state_encoded, captcha_solver=None: None)

    with pytest.raises(RuntimeError) as exc_info:
        worker.run(email="a@b.com", otp_callback=lambda: "")

    # Same key browser_register.py's CursorBrowserRegister.run raises when
    # otp_callback() returns an empty string -- confirmed by direct source
    # inspection (both sites reference "cursor.13939cce").
    assert exc_info.value.i18n_key == "cursor.13939cce"
    assert "cursor.13939cce" in (Path(__file__).resolve().parent.parent / "platforms" / "cursor" / "browser_register.py").read_text(encoding="utf-8")


# --- untouched boundaries ---------------------------------------------------


def test_pre_existing_orphan_keys_stay_unwired_and_untranslated():
    zh = json.loads((_CATALOG_DIR / "zh.json").read_text(encoding="utf-8-sig"))
    en = json.loads((_CATALOG_DIR / "en.json").read_text(encoding="utf-8-sig"))

    for orphan in ("77e79278", "acb1ec0b", "c2b97437", "fa61088a", "83cb9642", "bb015c60", "cfeae2ac"):
        assert orphan in zh["cursor"]
        assert orphan not in en["cursor"]


def test_cursor_never_reuses_a_tavily_key():
    # The two namespaces are separate: near-identical text on either side
    # still mints its own key (spec AC: "no cross-platform key sharing").
    _platform_dir = Path(__file__).resolve().parent.parent / "platforms" / "cursor"
    for filename in ("core.py", "browser_oauth.py", "browser_register.py", "protocol_mailbox.py", "plugin.py"):
        source = (_platform_dir / filename).read_text(encoding="utf-8")
        assert "tavily." not in source
