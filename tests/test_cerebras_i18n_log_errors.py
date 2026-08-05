"""story 4.12 -- cerebras's first-ever keyed-logging mechanism and keyed
raise-site coverage.

Covers the I/O & Edge-Case Matrix from this story's spec
(`_bmad-output/implementation-artifacts/spec-4-12-grok-and-cerebras.md`):
  - `CerebrasRegister.log_key` wired vs unwired -- the class's first-ever
    keyed-logging mechanism;
  - `CerebrasProtocolMailboxWorker.__init__`'s `log_key_fn` wiring reaches
    `self.client._log_key_fn` (`CerebrasRegister` embedded in the worker);
  - the within-platform duplicate-text edge case: `"使用已有 API Key"` is
    logged from both response-shape branches of
    `CerebrasRegister.step3_get_or_create_api_key`, and both must share the
    same minted key (`cerebras.dd2cf36c`);
  - the ternary-log split at `protocol_mailbox.py:31` (mirroring
    `platforms/tavily/protocol_mailbox.py:44-49`'s precedent): the truthy
    branch stays a plain, unwired `self.log`, the falsy branch emits
    `cerebras.bdfd8fe2`;
  - a cerebras raise-site test asserting `_raise_keyed`'s exception carries
    `.i18n_key`/`.i18n_params` and `str(exc)` renders the `zh` text, both
    for a `core.py` raise site and for the protocol worker's missing-OTP
    raise;
  - `cerebras/plugin.py`'s `execute_action` raise site;
  - the untouched boundaries: cerebras never reuses another platform's key
    even for identical text, and this story never touches the pre-existing
    `cerebras.3a43d2c8` (wired marker) or `cerebras.f57df6b5` (orphan,
    matching the untouched `OtpSpec` override) keys.

Cerebras has no browser-register or browser-oauth classes, so this file
mirrors only the protocol-worker/raise-site/`execute_action` subset of
tests/test_tavily_i18n_log_errors.py's shape, with cerebras's own
mechanisms (the shared-branch duplicate, the ternary split) added in their
place. No test makes a network call.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from i18n import t
from platforms.cerebras.core import CerebrasRegister
from platforms.cerebras.plugin import CerebrasPlatform
from platforms.cerebras.protocol_mailbox import CerebrasProtocolMailboxWorker

_PLATFORM_DIR = Path(__file__).resolve().parent.parent / "platforms" / "cerebras"


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data


class _FakeExecutor:
    """Minimal executor double: returns a canned GET response, never POSTs."""

    def __init__(self, get_response):
        self._get_response = get_response

    def get(self, *args, **kwargs):
        return self._get_response

    def post(self, *args, **kwargs):
        raise AssertionError("should not POST when an existing key is already found")


# --- CerebrasRegister.log_key -- wired vs unwired ---------------------------
# CerebrasRegister's first-ever keyed-logging mechanism.


def test_cerebras_register_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    client = CerebrasRegister(
        executor=None,
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    client.log_key("cerebras.f4bc415b")

    assert calls == [("cerebras.f4bc415b", {})]


def test_cerebras_register_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    client = CerebrasRegister(executor=None, log_fn=plain_calls.append)

    client.log_key("cerebras.f4bc415b")

    assert plain_calls == [t("cerebras.f4bc415b", "zh")]


def test_cerebras_register_constructed_directly_defaults_log_key_fn_to_none():
    client = CerebrasRegister(executor=None)

    assert client._log_key_fn is None


# --- CerebrasProtocolMailboxWorker wiring reaches self.client._log_key_fn --


def test_protocol_mailbox_worker_wires_log_key_fn_onto_client():
    def sink(key, params):
        pass

    worker = CerebrasProtocolMailboxWorker(executor=None, log_key_fn=sink)

    assert worker.client._log_key_fn is sink
    assert worker._log_key_fn is sink


def test_protocol_mailbox_worker_defaults_log_key_fn_to_none():
    worker = CerebrasProtocolMailboxWorker(executor=None)

    assert worker.client._log_key_fn is None
    assert worker._log_key_fn is None


# --- within-platform duplicate-text edge case -------------------------------
# "使用已有 API Key" is logged from both response-shape branches of
# step3_get_or_create_api_key (list-shaped vs dict-shaped JSON); both must
# share the same minted key.


def test_step3_shares_the_same_key_for_list_shaped_response():
    calls: list[tuple[str, dict]] = []
    client = CerebrasRegister(
        executor=_FakeExecutor(_FakeResponse([{"key": "existing-list-key"}])),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )
    client._session_jwt = "fake-jwt"

    key = client.step3_get_or_create_api_key()

    assert key == "existing-list-key"
    assert calls == [("cerebras.f4bc415b", {}), ("cerebras.dd2cf36c", {})]


def test_step3_shares_the_same_key_for_dict_shaped_response():
    calls: list[tuple[str, dict]] = []
    client = CerebrasRegister(
        executor=_FakeExecutor(_FakeResponse({"keys": [{"key": "existing-dict-key"}]})),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )
    client._session_jwt = "fake-jwt"

    key = client.step3_get_or_create_api_key()

    assert key == "existing-dict-key"
    assert calls == [("cerebras.f4bc415b", {}), ("cerebras.dd2cf36c", {})]


# --- the protocol_mailbox.py:31 ternary split -------------------------------
# Truthy branch stays plain, unwired self.log; falsy branch emits
# cerebras.bdfd8fe2. Mirrors platforms/tavily/protocol_mailbox.py:44-49.


def test_protocol_worker_run_logs_plain_when_api_key_present(monkeypatch):
    plain_calls: list[str] = []
    key_calls: list[tuple[str, dict]] = []
    worker = CerebrasProtocolMailboxWorker(executor=None, log_fn=plain_calls.append, log_key_fn=lambda key, params: key_calls.append((key, params)))
    monkeypatch.setattr(worker.client, "step1_send_otp", lambda email: "method-id")
    monkeypatch.setattr(worker.client, "step2_verify_otp", lambda email, otp, method_id: {"user_id": "u1", "session_token": "st", "session_jwt": "sj"})
    monkeypatch.setattr(worker.client, "step3_get_or_create_api_key", lambda: "abcdefghij0123456789")

    result = worker.run(email="a@b.com", password="", otp_callback=lambda: "123456")

    assert result["api_key"] == "abcdefghij0123456789"
    assert "API Key: abcdefghij0123456789..." in plain_calls
    assert not any(key == "cerebras.bdfd8fe2" for key, _ in key_calls)


def test_protocol_worker_run_emits_keyed_log_when_api_key_missing(monkeypatch):
    key_calls: list[tuple[str, dict]] = []
    worker = CerebrasProtocolMailboxWorker(executor=None, log_key_fn=lambda key, params: key_calls.append((key, params)))
    monkeypatch.setattr(worker.client, "step1_send_otp", lambda email: "method-id")
    monkeypatch.setattr(worker.client, "step2_verify_otp", lambda email, otp, method_id: {"user_id": "u1", "session_token": "st", "session_jwt": "sj"})
    monkeypatch.setattr(worker.client, "step3_get_or_create_api_key", lambda: "")

    result = worker.run(email="a@b.com", password="", otp_callback=lambda: "123456")

    assert result["api_key"] == ""
    assert ("cerebras.bdfd8fe2", {}) in key_calls


# --- cerebras raise sites -- _raise_keyed's exception shape ----------------


def test_core_not_logged_in_raises_keyed_exception():
    client = CerebrasRegister(executor=None)

    with pytest.raises(RuntimeError) as exc_info:
        client.step3_get_or_create_api_key()

    assert exc_info.value.i18n_key == "cerebras.a56b812f"
    assert exc_info.value.i18n_params == {}
    assert str(exc_info.value) == t("cerebras.a56b812f", "zh")


def test_protocol_mailbox_worker_missing_otp_raises_keyed_exception(monkeypatch):
    worker = CerebrasProtocolMailboxWorker(executor=None)
    monkeypatch.setattr(worker.client, "step1_send_otp", lambda email: "method-id")

    with pytest.raises(RuntimeError) as exc_info:
        worker.run(email="a@b.com", password="", otp_callback=lambda: "")

    assert exc_info.value.i18n_key == "cerebras.13939cce"
    assert exc_info.value.i18n_params == {}
    assert str(exc_info.value) == t("cerebras.13939cce", "zh")


# --- cerebras/plugin.py's execute_action raise site -------------------------


def test_execute_action_unknown_action_raises_keyed_exception():
    platform = object.__new__(CerebrasPlatform)

    with pytest.raises(NotImplementedError) as exc_info:
        platform.execute_action("bogus", None, {})

    assert exc_info.value.i18n_key == "cerebras.701d383a"
    assert exc_info.value.i18n_params == {"action_id": "bogus"}
    assert str(exc_info.value) == t("cerebras.701d383a", "zh", action_id="bogus")


# --- untouched boundaries ----------------------------------------------------


def test_cerebras_never_reuses_another_platforms_key():
    for filename in ("core.py", "protocol_mailbox.py", "plugin.py"):
        source = (_PLATFORM_DIR / filename).read_text(encoding="utf-8")
        for other in ("grok.", "tavily.", "cursor.", "trae.", "anything."):
            assert other not in source


def test_cerebras_never_wires_the_preexisting_orphan_or_marker_keys():
    core_source = (_PLATFORM_DIR / "core.py").read_text(encoding="utf-8")
    protocol_source = (_PLATFORM_DIR / "protocol_mailbox.py").read_text(encoding="utf-8")
    plugin_source = (_PLATFORM_DIR / "plugin.py").read_text(encoding="utf-8")

    # cerebras.f57df6b5 stays an unreferenced orphan (matches the OtpSpec
    # wait_message override text) -- never appears as a log_key/_raise_keyed
    # argument anywhere in the platform package.
    assert "f57df6b5" not in core_source
    assert "f57df6b5" not in protocol_source
    assert "f57df6b5" not in plugin_source

    # cerebras.3a43d2c8 stays exactly the pre-existing get_platform_actions()
    # label, out of this story's log/raise scope.
    assert 'label": "cerebras.3a43d2c8"' in plugin_source
