"""story 4.9 -- openblocklabs' first-ever keyed-logging mechanism and keyed
raise-site coverage.

Covers the I/O & Edge-Case Matrix from this story's spec
(`_bmad-output/implementation-artifacts/spec-4-9-openblocklabs-and-blink.md`):
  - `OpenBlockLabsRegister.log_key` wired -- calls the sink positionally with
    (key, dict);
  - `OpenBlockLabsRegister.log_key` unwired -- falls back to rendering the
    identical pre-migration Chinese string via `self.log`;
  - `OpenBlockLabsBrowserRegister.log_key` wired vs unwired -- the class's
    first-ever keyed-logging mechanism;
  - `OpenBlockLabsProtocolMailboxWorker.__init__`'s `log_key_fn` wiring
    reaches `self.client._log_key_fn` (`OpenBlockLabsRegister` embedded in
    the worker);
  - openblocklabs raise-site tests asserting `_raise_keyed`'s exception
    carries `.i18n_key`/`.i18n_params` and `str(exc)` renders the `zh` text;
  - the duplicate-text edge cases: `未进入验证码页面: {page_url}` (two sites in
    browser_register.py), `已填写密码: {used_pwd_sel}` (two sites in
    browser_register.py) and `注册成功: {email}` (browser_register.py plus
    protocol_mailbox.py) each land on one shared key;
  - the cross-platform boundary: near-identical blink text never reuses an
    `openblocklabs.*` key.

Mirrors tests/test_windsurf_i18n_log_errors.py's scope discipline: one test
per distinct mechanism, not one test per call site. No test makes a network
call or touches Playwright/Camoufox.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from i18n import t
from platforms.openblocklabs import browser_register as browser_register_module
from platforms.openblocklabs.core import OpenBlockLabsRegister
from platforms.openblocklabs.protocol_mailbox import OpenBlockLabsProtocolMailboxWorker

_PLATFORM_DIR = Path(__file__).resolve().parent.parent / "platforms" / "openblocklabs"


# --- OpenBlockLabsRegister.log_key -- wired vs unwired --------------------
# OpenBlockLabsRegister's first-ever keyed-logging mechanism. The class has no
# `log_fn` constructor parameter (callers reassign `client.log` after
# construction, as protocol_mailbox.py does), so these tests do the same.


def test_register_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    client = OpenBlockLabsRegister(log_key_fn=lambda key, params: calls.append((key, params)))
    client.log = lambda message: (_ for _ in ()).throw(AssertionError("should not fall back"))

    client.log_key("openblocklabs.a26ce2a1", status_code=403, attempt=1)

    assert calls == [("openblocklabs.a26ce2a1", {"status_code": 403, "attempt": 1})]


def test_register_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    client = OpenBlockLabsRegister()
    client.log = plain_calls.append

    client.log_key("openblocklabs.a26ce2a1", status_code=403, attempt=1)

    assert plain_calls == [t("openblocklabs.a26ce2a1", "zh", status_code=403, attempt=1)]


def test_register_constructed_directly_defaults_log_key_fn_to_none():
    assert OpenBlockLabsRegister()._log_key_fn is None


# --- OpenBlockLabsBrowserRegister.log_key -- wired vs unwired -------------
# OpenBlockLabsBrowserRegister's first-ever keyed-logging mechanism.


def test_browser_register_log_key_wired_calls_sink_with_positional_dict():
    calls: list[tuple[str, dict]] = []
    worker = browser_register_module.OpenBlockLabsBrowserRegister(
        headless=True,
        proxy=None,
        otp_callback=None,
        log_fn=lambda message: (_ for _ in ()).throw(AssertionError("should not fall back")),
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    worker.log_key("openblocklabs.16ff6530")

    assert calls == [("openblocklabs.16ff6530", {})]


def test_browser_register_log_key_wired_forwards_params_positionally():
    calls: list[tuple[str, dict]] = []
    worker = browser_register_module.OpenBlockLabsBrowserRegister(
        headless=True,
        log_key_fn=lambda key, params: calls.append((key, params)),
    )

    worker.log_key("openblocklabs.d557cd8c", used_email_sel='input[name="email"]')

    assert calls == [("openblocklabs.d557cd8c", {"used_email_sel": 'input[name="email"]'})]


def test_browser_register_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    worker = browser_register_module.OpenBlockLabsBrowserRegister(
        headless=True, log_fn=plain_calls.append
    )

    worker.log_key("openblocklabs.16ff6530")

    assert plain_calls == [t("openblocklabs.16ff6530", "zh")]


def test_browser_register_constructed_directly_defaults_log_key_fn_to_none():
    worker = browser_register_module.OpenBlockLabsBrowserRegister(headless=True)

    assert worker._log_key_fn is None


# --- OpenBlockLabsProtocolMailboxWorker wiring reaches the embedded client -


def test_protocol_mailbox_worker_wires_log_key_fn_onto_client():
    def sink(key, params):
        pass

    worker = OpenBlockLabsProtocolMailboxWorker(log_key_fn=sink)

    assert worker.client._log_key_fn is sink
    assert worker._log_key_fn is sink


def test_protocol_mailbox_worker_defaults_log_key_fn_to_none():
    worker = OpenBlockLabsProtocolMailboxWorker()

    assert worker.client._log_key_fn is None
    assert worker._log_key_fn is None


def test_protocol_mailbox_worker_log_key_unwired_falls_back_to_rendered_log():
    plain_calls: list[str] = []
    worker = OpenBlockLabsProtocolMailboxWorker(log_fn=plain_calls.append)

    worker.log_key("openblocklabs.d9dbdf1a", email="a@b.com")

    assert plain_calls == [t("openblocklabs.d9dbdf1a", "zh", email="a@b.com")]


# --- openblocklabs raise sites -- _raise_keyed's exception shape ----------
# openblocklabs' first-ever keyed raise-site coverage. Each helper below is
# driven with `timeout=0` so its wait loop never runs, which keeps the test
# free of Playwright, Camoufox and the network.


def test_wait_for_visible_element_raises_keyed_exception_with_params():
    with pytest.raises(RuntimeError) as exc_info:
        browser_register_module._wait_for_visible_element(None, ["a", "b"], timeout=0)

    assert exc_info.value.i18n_key == "openblocklabs.da836b61"
    assert exc_info.value.i18n_params == {"selectors": "a | b"}
    assert str(exc_info.value) == t("openblocklabs.da836b61", "zh", selectors="a | b")


def test_wait_cf_full_block_clear_raises_keyed_exception_with_params():
    page = SimpleNamespace(url="https://auth.openblocklabs.com/sign-up")

    with pytest.raises(RuntimeError) as exc_info:
        browser_register_module._wait_cf_full_block_clear(page, timeout=0)

    assert exc_info.value.i18n_key == "openblocklabs.8ef9c157"
    assert exc_info.value.i18n_params == {"page_url": page.url}
    assert str(exc_info.value) == t("openblocklabs.8ef9c157", "zh", page_url=page.url)


def test_advance_to_email_verification_raises_keyed_exception_with_params():
    page = SimpleNamespace(url="https://auth.openblocklabs.com/sign-up/password")

    with pytest.raises(RuntimeError) as exc_info:
        browser_register_module._advance_to_email_verification(page, [], timeout=0)

    assert exc_info.value.i18n_key == "openblocklabs.e12970a4"
    assert exc_info.value.i18n_params == {"page_url": page.url}
    assert str(exc_info.value) == t("openblocklabs.e12970a4", "zh", page_url=page.url)


# --- duplicate-text edge cases -- one shared key per identical text -------
# The three duplicate texts this story's spec calls out are emitted from
# inside `OpenBlockLabsBrowserRegister.run`, which needs a live Camoufox
# browser, so they are asserted against the migrated source text instead of
# by execution -- the property under test ("both sites reference the same
# minted key") is a static one.


def _key_reference_count(filename: str, key: str) -> int:
    source = (_PLATFORM_DIR / filename).read_text(encoding="utf-8")
    # `# was: ...` comments reproduce the pre-migration literal, never a key,
    # so no comment stripping is needed for an exact quoted-key count.
    return len(re.findall(re.escape(f'"{key}"'), source))


def test_verification_page_raise_sites_share_one_key():
    assert _key_reference_count("browser_register.py", "openblocklabs.e12970a4") == 2


def test_password_filled_log_sites_share_one_key():
    assert _key_reference_count("browser_register.py", "openblocklabs.3fdb7528") == 2


def test_signup_success_log_sites_share_one_key_across_files():
    assert _key_reference_count("browser_register.py", "openblocklabs.d9dbdf1a") == 1
    assert _key_reference_count("protocol_mailbox.py", "openblocklabs.d9dbdf1a") == 1


def test_openblocklabs_never_reuses_a_blink_key():
    # The two namespaces are separate: near-identical text on either side
    # still mints its own key (spec AC: "no cross-platform key sharing").
    for filename in ("core.py", "browser_oauth.py", "browser_register.py",
                     "protocol_mailbox.py", "plugin.py"):
        source = (_PLATFORM_DIR / filename).read_text(encoding="utf-8")
        assert "blink." not in source


# --- review-pass fixes: field-carried Chinese literals and a dropped key --
# _fill_visible_input's `label` argument used to carry the raw Chinese noun
# ("邮箱"/"密码") straight into an i18n_param, leaking untranslated text into
# an otherwise-keyed message under a non-zh locale. Fixed by minting one key
# per field instead of parameterizing by a caller-supplied Chinese literal.


def test_fill_visible_input_call_sites_use_distinct_per_field_keys():
    assert _key_reference_count("browser_register.py", "openblocklabs.262c78a0") == 1
    assert _key_reference_count("browser_register.py", "openblocklabs.7673f03f") == 2
    # the old shared, label-parameterized key must be gone entirely
    assert _key_reference_count("browser_register.py", "openblocklabs.21cc66da") == 0


def test_reopen_session_forwards_inner_i18n_key_instead_of_stringifying():
    # AD-8: a handler wrapping an inner exception must re-raise/forward the
    # inner key rather than discarding it via str(exc). Before this fix,
    # `if not session_id: raise RuntimeError(str(last_open_error))` always
    # dropped `last_open_error`'s `.i18n_key` even when it was itself a
    # `_raise_keyed(...)` exception (e.g. from `_wait_cf_full_block_clear`).
    from platforms.openblocklabs._i18n_helpers import _raise_keyed

    last_open_error = None
    try:
        _raise_keyed(RuntimeError, "openblocklabs.8ef9c157", page_url="https://x")
    except RuntimeError as exc:
        last_open_error = exc

    # the guard this fix added, exercised directly against a real keyed
    # exception rather than a live Camoufox session (see the duplicate-text
    # tests above for why this file asserts source shape for browser-only
    # paths):
    assert getattr(last_open_error, "i18n_key", None) == "openblocklabs.8ef9c157"

    source = (_PLATFORM_DIR / "browser_register.py").read_text(encoding="utf-8")
    assert 'if getattr(last_open_error, "i18n_key", None):' in source
    assert "raise last_open_error" in source
