"""story 4.6a -- kiro/core.py's profile and signup steps; story 4.7 adds
`KiroBrowserRegister.log_key` (its first-ever keyed-logging mechanism) and
kiro's first-ever keyed raise-site coverage.

Covers the I/O & Edge-Case Matrix from this story's spec
(`_bmad-output/implementation-artifacts/spec-4-6a-kiro-core-py-the-profile-and-signup-steps.md`):
  - `KiroRegister.log_key` wired -- calls the sink positionally with (key, dict);
  - `KiroRegister.log_key` unwired -- falls back to `self.log(t(key, "zh", **params))`,
    the identical Chinese string it rendered before this story;
  - `KiroProtocolMailboxWorker.__init__`'s `log_key_fn` wiring reaches
    `self.client._log_key_fn`.

Story 4.7 (`_bmad-output/implementation-artifacts/spec-4-7-the-rest-of-kiro.md`)
adds:
  - `KiroBrowserRegister.log_key` wired vs unwired -- the class's first-ever
    keyed-logging mechanism;
  - a kiro raise-site test asserting `_raise_keyed`'s exception carries
    `.i18n_key`/`.i18n_params` and `str(exc)` renders the `zh` text.

Mirrors tests/test_chatgpt_i18n_log_errors.py's scope discipline: one test
per distinct mechanism, not one test per call site. No test makes a network
call.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from i18n import t
from platforms.kiro import browser_oauth as browser_oauth_module
from platforms.kiro import browser_register as browser_register_module
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


# --- story 4.7: KiroBrowserRegister.log_key -- wired vs unwired ----------
# KiroBrowserRegister's first-ever keyed-logging mechanism.


def test_browser_register_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    worker = browser_register_module.KiroBrowserRegister(
        headless=True,
        proxy=None,
        otp_callback=None,
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    worker.log_key("kiro.67562fc8")

    assert calls == [("kiro.67562fc8", {})]


def test_browser_register_log_key_wired_forwards_params_positionally():
    calls: list[tuple[str, dict]] = []
    worker = browser_register_module.KiroBrowserRegister(
        headless=True,
        proxy=None,
        otp_callback=None,
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    worker.log_key("kiro.eaa92c19", email="a@b.com")

    assert calls == [("kiro.eaa92c19", {"email": "a@b.com"})]


def test_browser_register_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    worker = browser_register_module.KiroBrowserRegister(
        headless=True,
        proxy=None,
        otp_callback=None,
        log_fn=plain_calls.append,
    )

    worker.log_key("kiro.67562fc8")

    assert plain_calls == [t("kiro.67562fc8", "zh")]


def test_browser_register_constructed_directly_defaults_log_key_fn_to_none():
    worker = browser_register_module.KiroBrowserRegister(headless=True)

    assert worker._log_key_fn is None


# --- story 4.7: kiro raise sites -- _raise_keyed's exception shape -------
# kiro's first-ever keyed raise-site coverage. `_exchange_callback_tokens`
# (platforms/kiro/browser_oauth.py) is exercised directly since it never
# touches Playwright and only reaches the network for a still-valid
# callback URL -- neither test below gets that far.


def test_exchange_callback_tokens_raises_keyed_exception_without_params():
    reg = KiroRegister(tag="TEST")

    with pytest.raises(RuntimeError) as exc_info:
        browser_oauth_module._exchange_callback_tokens(
            reg, "https://app.kiro.dev/signin/oauth"
        )

    assert exc_info.value.i18n_key == "kiro.6f57fe44"
    assert exc_info.value.i18n_params == {}
    assert str(exc_info.value) == t("kiro.6f57fe44", "zh")


def test_exchange_callback_tokens_raises_keyed_exception_with_params():
    reg = KiroRegister(tag="TEST")
    reg.s.post = lambda *args, **kwargs: SimpleNamespace(status_code=500)

    with pytest.raises(RuntimeError) as exc_info:
        browser_oauth_module._exchange_callback_tokens(
            reg, "https://app.kiro.dev/signin/oauth?code=abc123"
        )

    assert exc_info.value.i18n_key == "kiro.77e70637"
    assert exc_info.value.i18n_params == {"status_code": 500}
    assert str(exc_info.value) == t("kiro.77e70637", "zh", status_code=500)


def test_protocol_mailbox_worker_defaults_log_key_fn_to_none():
    worker = KiroProtocolMailboxWorker(tag="TEST")

    assert worker.client._log_key_fn is None
