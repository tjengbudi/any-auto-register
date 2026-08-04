"""story 4.6a -- kiro/core.py's profile and signup steps.

Covers the I/O & Edge-Case Matrix from this story's spec
(`_bmad-output/implementation-artifacts/spec-4-6a-kiro-core-py-the-profile-and-signup-steps.md`):
  - `KiroRegister.log_key` wired -- calls the sink positionally with (key, dict);
  - `KiroRegister.log_key` unwired -- falls back to `self.log(t(key, "zh", **params))`,
    the identical Chinese string it rendered before this story;
  - `KiroProtocolMailboxWorker.__init__`'s `log_key_fn` wiring reaches
    `self.client._log_key_fn`.

Mirrors tests/test_chatgpt_i18n_log_errors.py's scope discipline: one test
per distinct mechanism, not one test per call site. No test makes a network
call.
"""
from __future__ import annotations

from i18n import t
from platforms.kiro.core import KiroRegister
from platforms.kiro.protocol_mailbox import KiroProtocolMailboxWorker


# --- KiroRegister.log_key -- wired vs unwired -----------------------------


def test_kiro_register_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    reg = KiroRegister(tag="TEST")
    reg._log_key_fn = lambda key, params: calls.append((key, params))
    reg.log = lambda msg: (_ for _ in ()).throw(AssertionError("should not fall back"))

    reg.log_key("kiro.8dd84f04")

    assert calls == [("kiro.8dd84f04", {})]


def test_kiro_register_log_key_wired_forwards_params_positionally():
    calls: list[tuple[str, dict]] = []
    reg = KiroRegister(tag="TEST")
    reg._log_key_fn = lambda key, params: calls.append((key, params))

    reg.log_key("kiro.fdd9ccc7", signup_token="abc123")

    assert calls == [("kiro.fdd9ccc7", {"signup_token": "abc123"})]


def test_kiro_register_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    reg = KiroRegister(tag="TEST")
    reg.log = plain_calls.append

    reg.log_key("kiro.8dd84f04")

    assert plain_calls == [t("kiro.8dd84f04", "zh")]


def test_kiro_register_log_key_unwired_renders_params_in_fallback():
    plain_calls: list[str] = []
    reg = KiroRegister(tag="TEST")
    reg.log = plain_calls.append

    reg.log_key("kiro.fdd9ccc7", signup_token="abc123")

    assert plain_calls == [t("kiro.fdd9ccc7", "zh", signup_token="abc123")]


def test_kiro_register_constructed_directly_defaults_log_key_fn_to_none():
    reg = KiroRegister(tag="TEST")

    assert reg._log_key_fn is None


# --- KiroProtocolMailboxWorker wiring reaches self.client._log_key_fn ----


def test_protocol_mailbox_worker_wires_log_key_fn_onto_client():
    def sink(key, params):
        pass

    worker = KiroProtocolMailboxWorker(tag="TEST", log_key_fn=sink)

    assert worker.client._log_key_fn is sink


def test_protocol_mailbox_worker_defaults_log_key_fn_to_none():
    worker = KiroProtocolMailboxWorker(tag="TEST")

    assert worker.client._log_key_fn is None
