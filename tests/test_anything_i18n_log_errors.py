"""story 4.11 -- anything's first-ever keyed-logging mechanism and keyed
raise-site coverage.

Covers the I/O & Edge-Case Matrix from this story's spec
(`_bmad-output/implementation-artifacts/spec-4-11-trae-and-anything.md`):
  - `AnythingClient.log_key` wired vs unwired -- the class's first-ever
    keyed-logging mechanism (all 13 of anything's raise sites live inside
    this one class);
  - `AnythingProtocolMailboxWorker.__init__`'s `log_key_fn` wiring reaches
    `self.client._log_key_fn` (`AnythingClient` embedded in the worker);
  - an anything raise-site test asserting `_raise_keyed`'s exception carries
    `.i18n_key`/`.i18n_params` and `str(exc)` renders the `zh` text, both
    for a `RuntimeError` site and for `AnythingPlatform.execute_action`'s
    `NotImplementedError` site;
  - the duplicate-text edge case: `AnythingClient.resolve_magic_link`'s
    "空 magic link" raise shares its minted key with both raises inside
    `AnythingProtocolMailboxWorker._resolve_magic_link`/`_extract_magic_link`;
  - the untouched boundaries: the pre-existing 5 wired + 2 orphaned
    `anything.*` keys from the earlier marker-key story stay exactly as they
    were, and anything never reuses a `trae.*` key even for identical text.

Mirrors tests/test_cursor_i18n_log_errors.py's scope discipline: one test per
distinct mechanism, not one test per call site. No test makes a network call.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from i18n import t
from platforms.anything.core import AnythingClient
from platforms.anything.plugin import AnythingPlatform
from platforms.anything.protocol_mailbox import AnythingProtocolMailboxWorker

_CATALOG_DIR = Path(__file__).resolve().parent.parent / "i18n"
_PLATFORM_DIR = Path(__file__).resolve().parent.parent / "platforms" / "anything"


# --- AnythingClient.log_key -- wired vs unwired -----------------------------
# AnythingClient's first-ever keyed-logging mechanism.


def test_anything_client_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    client = AnythingClient(
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    client.log_key("anything.8495c215", email="a@b.com")

    assert calls == [("anything.8495c215", {"email": "a@b.com"})]


def test_anything_client_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    client = AnythingClient(log_fn=plain_calls.append)

    client.log_key("anything.8495c215", email="a@b.com")

    assert plain_calls == [t("anything.8495c215", "zh", email="a@b.com")]


def test_anything_client_constructed_directly_defaults_log_key_fn_to_none():
    client = AnythingClient()

    assert client._log_key_fn is None


# --- AnythingProtocolMailboxWorker wiring reaches self.client._log_key_fn --


def test_protocol_mailbox_worker_wires_log_key_fn_onto_client():
    def sink(key, params):
        pass

    worker = AnythingProtocolMailboxWorker(log_key_fn=sink)

    assert worker.client._log_key_fn is sink
    assert worker._log_key_fn is sink


def test_protocol_mailbox_worker_defaults_log_key_fn_to_none():
    worker = AnythingProtocolMailboxWorker()

    assert worker.client._log_key_fn is None
    assert worker._log_key_fn is None


def test_protocol_mailbox_worker_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    worker = AnythingProtocolMailboxWorker(
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    worker.log_key("anything.8c028503")

    assert calls == [("anything.8c028503", {})]


def test_protocol_mailbox_worker_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    worker = AnythingProtocolMailboxWorker(log_fn=plain_calls.append)

    worker.log_key("anything.8c028503")

    assert plain_calls == [t("anything.8c028503", "zh")]


# --- anything raise sites -- _raise_keyed's exception shape -----------------
# anything's first-ever keyed raise-site coverage.


def test_anything_client_empty_magic_link_raises_keyed_exception():
    client = AnythingClient()

    with pytest.raises(RuntimeError) as exc_info:
        client.resolve_magic_link("")

    assert exc_info.value.i18n_key == "anything.989ea928"
    assert exc_info.value.i18n_params == {}
    assert str(exc_info.value) == t("anything.989ea928", "zh")


def test_execute_action_unknown_action_raises_keyed_not_implemented_error():
    # __new__ without __init__: the fall-through raise is reached before any
    # instance attribute is touched, so no DB-backed capability lookup runs.
    platform = object.__new__(AnythingPlatform)

    with pytest.raises(NotImplementedError) as exc_info:
        platform.execute_action("definitely_not_an_action", None, {})

    assert exc_info.value.i18n_key == "anything.701d383a"
    assert exc_info.value.i18n_params == {"action_id": "definitely_not_an_action"}
    assert str(exc_info.value) == t("anything.701d383a", "zh", action_id="definitely_not_an_action")


# --- duplicate-text edge case ------------------------------------------------
# AnythingClient.resolve_magic_link, AnythingProtocolMailboxWorker's
# _resolve_magic_link and _extract_magic_link all raise the identical
# "空 magic link" text and must share one minted key.


def test_worker_resolve_and_extract_magic_link_share_empty_link_key():
    worker = AnythingProtocolMailboxWorker()

    with pytest.raises(RuntimeError) as resolve_exc:
        worker._resolve_magic_link("")
    with pytest.raises(RuntimeError) as extract_exc:
        worker._extract_magic_link("")

    assert resolve_exc.value.i18n_key == "anything.989ea928"
    assert extract_exc.value.i18n_key == "anything.989ea928"
    core_source = (_PLATFORM_DIR / "core.py").read_text(encoding="utf-8")
    assert "anything.989ea928" in core_source


# --- untouched boundaries ---------------------------------------------------


def test_pre_existing_orphan_keys_stay_unwired_and_untranslated():
    zh = json.loads((_CATALOG_DIR / "zh.json").read_text(encoding="utf-8-sig"))
    en = json.loads((_CATALOG_DIR / "en.json").read_text(encoding="utf-8-sig"))

    for orphan in ("27343818", "cb988942"):
        assert orphan in zh["anything"]
        assert orphan not in en["anything"]


def test_anything_never_reuses_a_trae_key():
    # The two namespaces are separate: near-identical text on either side
    # still mints its own key (spec AC: "no cross-platform key sharing").
    for filename in ("core.py", "protocol_mailbox.py", "plugin.py"):
        source = (_PLATFORM_DIR / filename).read_text(encoding="utf-8")
        assert "trae." not in source
