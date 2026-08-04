"""story 4.9 -- blink's first-ever keyed-logging mechanism and keyed
raise-site coverage.

Covers the I/O & Edge-Case Matrix from this story's spec
(`_bmad-output/implementation-artifacts/spec-4-9-openblocklabs-and-blink.md`):
  - `BlinkRegister.log_key` wired vs unwired -- the one class in this story
    that gains `_log_key_fn` as a post-construction instance attribute
    instead of a constructor parameter, mirroring its existing `client._log`
    assignment shape;
  - `BlinkProtocolMailboxWorker.log_key` wired vs unwired, and its
    `log_key_fn` constructor parameter reaching `self.client._log_key_fn`;
  - `load_blink_account_state`'s sibling `log_key` parameter reaching
    `client._log_key_fn`;
  - blink raise-site tests asserting `_raise_keyed`'s exception carries
    `.i18n_key`/`.i18n_params` and `str(exc)` renders the `zh` text, for a
    `RuntimeError` site and for `BlinkPlatform.execute_action`'s
    `NotImplementedError` site;
  - the untouched boundaries: `blink/plugin.py`'s already-migrated
    returned-payload `i18n_key` markers and the 3 pre-existing orphaned
    `blink.*` keys stay exactly as they were.

Mirrors tests/test_windsurf_i18n_log_errors.py's scope discipline: one test
per distinct mechanism, not one test per call site. No test makes a network
call.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from i18n import t
from platforms.blink.core import BlinkRegister, load_blink_account_state
from platforms.blink.plugin import BlinkPlatform
from platforms.blink.protocol_mailbox import BlinkProtocolMailboxWorker

_CATALOG_DIR = Path(__file__).resolve().parent.parent / "i18n"


# --- BlinkRegister.log_key -- wired vs unwired ----------------------------
# BlinkRegister is this story's one exception to the constructor-parameter
# wiring shape: it has neither a `log_fn` nor a `log_key_fn` parameter, and
# every call site assigns `client._log` / `client._log_key_fn` after
# construction instead.


def test_blink_register_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    client = BlinkRegister()
    client._log = lambda message: (_ for _ in ()).throw(AssertionError("should not fall back"))
    client._log_key_fn = lambda key, params: calls.append((key, params))

    client.log_key("blink.09968493")

    assert calls == [("blink.09968493", {})]


def test_blink_register_log_key_wired_forwards_params_positionally():
    calls: list[tuple[str, dict]] = []
    client = BlinkRegister()
    client._log_key_fn = lambda key, params: calls.append((key, params))

    client.log_key("blink.e86abe70", email="a@b.com")

    assert calls == [("blink.e86abe70", {"email": "a@b.com"})]


def test_blink_register_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    client = BlinkRegister()
    client._log = plain_calls.append

    client.log_key("blink.e86abe70", email="a@b.com")

    assert plain_calls == [t("blink.e86abe70", "zh", email="a@b.com")]


def test_blink_register_constructed_directly_defaults_log_key_fn_to_none():
    assert BlinkRegister()._log_key_fn is None


# --- BlinkProtocolMailboxWorker -- wiring and log_key ---------------------


def test_protocol_mailbox_worker_wires_log_key_fn_onto_client():
    def sink(key, params):
        pass

    worker = BlinkProtocolMailboxWorker(log_key_fn=sink)

    assert worker.client._log_key_fn is sink
    assert worker._log_key_fn is sink


def test_protocol_mailbox_worker_defaults_log_key_fn_to_none():
    worker = BlinkProtocolMailboxWorker()

    assert worker.client._log_key_fn is None
    assert worker._log_key_fn is None


def test_protocol_mailbox_worker_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    worker = BlinkProtocolMailboxWorker(
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    worker.log_key("blink.2cdad0a9")

    assert calls == [("blink.2cdad0a9", {})]


def test_protocol_mailbox_worker_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    worker = BlinkProtocolMailboxWorker(log_fn=plain_calls.append)

    worker.log_key("blink.50241905", cashier_url="https://pay.example/x")

    assert plain_calls == [
        t("blink.50241905", "zh", cashier_url="https://pay.example/x")
    ]


# --- load_blink_account_state's sibling log_key parameter -----------------


def test_load_blink_account_state_threads_log_key_onto_the_client(monkeypatch):
    seen: dict[str, object] = {}

    class _CapturingRegister(BlinkRegister):
        def refresh_auth_session(self, firebase_refresh_token, *, workspace_slug=""):
            seen["log_key_fn"] = self._log_key_fn
            seen["log"] = self._log
            raise _Stop

    class _Stop(Exception):
        pass

    monkeypatch.setattr("platforms.blink.core.BlinkRegister", _CapturingRegister)

    def sink(key, params):
        pass

    account = SimpleNamespace(email="a@b.com", token="", extra={"firebase_refresh_token": "fr"})
    with pytest.raises(_Stop):
        load_blink_account_state(account, log_fn=print, log_key=sink)

    assert seen["log_key_fn"] is sink


def test_load_blink_account_state_raises_keyed_exception_when_refresh_token_missing():
    account = SimpleNamespace(email="a@b.com", token="", extra={})

    with pytest.raises(RuntimeError) as exc_info:
        load_blink_account_state(account)

    assert exc_info.value.i18n_key == "blink.dd24e96a"
    assert exc_info.value.i18n_params == {}
    assert str(exc_info.value) == t("blink.dd24e96a", "zh")


# --- blink raise sites -- _raise_keyed's exception shape ------------------
# blink's first-ever keyed raise-site coverage. `_extract_token` is a
# staticmethod that never touches the network, and `execute_action`'s
# fall-through raise is reached before any instance state is read, so both
# are safe to drive directly.


def test_protocol_mailbox_extract_token_raises_keyed_exception_with_params():
    with pytest.raises(RuntimeError) as exc_info:
        BlinkProtocolMailboxWorker._extract_token("no token here")

    assert exc_info.value.i18n_key == "blink.e6b4e29a"
    assert exc_info.value.i18n_params == {"raw": "no token here"}
    assert str(exc_info.value) == t("blink.e6b4e29a", "zh", raw="no token here")


def test_protocol_mailbox_extract_token_returns_match_without_raising():
    token = "a" * 64
    assert BlinkProtocolMailboxWorker._extract_token(f"https://blink.new/?magic_token={token}") == token


def test_execute_action_unknown_action_raises_keyed_not_implemented_error():
    # __new__ without __init__: the fall-through raise is reached before any
    # instance attribute is touched, so no DB-backed capability lookup runs.
    platform = object.__new__(BlinkPlatform)

    with pytest.raises(NotImplementedError) as exc_info:
        platform.execute_action("definitely_not_an_action", None, {})

    assert exc_info.value.i18n_key == "blink.701d383a"
    assert exc_info.value.i18n_params == {"action_id": "definitely_not_an_action"}
    assert str(exc_info.value) == t("blink.701d383a", "zh", action_id="definitely_not_an_action")


# --- untouched boundaries -------------------------------------------------


def test_platform_action_label_payload_markers_are_untouched():
    labels = [action["label"] for action in BlinkPlatform.get_platform_actions(object.__new__(BlinkPlatform))]

    assert labels == ["blink.a7517bf2", "blink.8e7f6e2f", "blink.3c077658"]


def test_pre_existing_orphan_keys_stay_unwired_and_untranslated():
    zh = json.loads((_CATALOG_DIR / "zh.json").read_text(encoding="utf-8-sig"))
    en = json.loads((_CATALOG_DIR / "en.json").read_text(encoding="utf-8-sig"))

    for orphan in ("16c77f12", "1f9daf02", "cb988942"):
        assert orphan in zh["blink"]
        assert orphan not in en["blink"]


def test_blink_never_reuses_an_openblocklabs_key():
    # The two namespaces are separate: near-identical text on either side
    # still mints its own key (spec AC: "no cross-platform key sharing").
    _platform_dir = Path(__file__).resolve().parent.parent / "platforms" / "blink"
    for filename in ("core.py", "protocol_mailbox.py", "plugin.py"):
        source = (_platform_dir / filename).read_text(encoding="utf-8")
        assert "openblocklabs." not in source
