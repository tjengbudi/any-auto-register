"""story 4.4 -- the `core/` log and error surface.

Covers the I/O & Edge-Case Matrix from this story's spec
(`_bmad-output/implementation-artifacts/spec-4-4-the-core-log-and-error-surface.md`):
  - `FallbackMailbox.get_email()` failing on some providers, with `log_key_fn`
    wired from a real registration path, turns every attempt/success/failure
    print into a `log_key` event that renders per `ui_language`;
  - the exact same call with `log_key_fn=None` (an unmigrated caller) falls
    back to the byte-identical `print(...)` output of before this story;
  - `core/registration/`'s `ensure_*` exception family carries `i18n_key`/
    `i18n_params` (AD-17) and is forwarded untouched by `application/tasks.py`'s
    existing `_exc_key` (story 4.3, unchanged, no code change needed there);
  - a platform-supplied (non-`None`) `wait_message`/`success_label` override
    keeps rendering via plain `ctx.log(...)`, unchanged, migration-tail state;
  - `core/registration/adapters.py`'s default (`None`) `wait_message`/
    `success_label` renders through `ctx.log_key(...)` instead.
"""
from __future__ import annotations

import pytest

from application.tasks import _exc_key
from core.base_mailbox import BaseMailbox, FallbackMailbox, MailboxAccount
from core.registration.errors import BrowserReuseRequiredError, IdentityResolutionError
from core.registration.helpers import (
    build_otp_callback,
    ensure_identity_email,
    ensure_oauth_browser_reuse,
)
from core.registration.models import RegistrationContext
from i18n import t


def _make_ctx(*, log_fn=None, log_key_fn=None, identity=None, platform=None, executor_type="protocol") -> RegistrationContext:
    class _Config:
        pass

    config = _Config()
    config.executor_type = executor_type
    return RegistrationContext(
        platform_name="test_platform",
        platform_display_name="Test Platform",
        platform=platform,
        identity=identity,
        config=config,
        email=None,
        password=None,
        log_fn=log_fn or (lambda message: None),
        log_key_fn=log_key_fn,
    )


# --- FallbackMailbox: log_key_fn wired, 2 of 3 providers fail -------------


class _AlwaysFailsMailbox(BaseMailbox):
    def get_email(self, *, log_key_fn=None):
        raise RuntimeError("boom")

    def wait_for_code(self, account, keyword="", timeout=120, before_ids=None, code_pattern=None, *, log_key_fn=None):
        raise NotImplementedError

    def wait_for_link(self, account, keyword="", timeout=120, before_ids=None, *, log_key_fn=None):
        raise NotImplementedError

    def get_current_ids(self, account):
        return set()


class _SucceedsMailbox(BaseMailbox):
    def get_email(self, *, log_key_fn=None):
        return MailboxAccount(email="ok@example.com")

    def wait_for_code(self, account, keyword="", timeout=120, before_ids=None, code_pattern=None, *, log_key_fn=None):
        return "123456"

    def wait_for_link(self, account, keyword="", timeout=120, before_ids=None, *, log_key_fn=None):
        return "https://example.com/verify"

    def get_current_ids(self, account):
        return set()


def _build_fallback_mailbox() -> FallbackMailbox:
    return FallbackMailbox(
        [
            ("provider_a", _AlwaysFailsMailbox()),
            ("provider_b", _AlwaysFailsMailbox()),
            ("provider_c", _SucceedsMailbox()),
        ]
    )


def test_fallback_mailbox_get_email_emits_log_key_events_for_each_attempt():
    calls: list[tuple[str, dict]] = []

    def log_key_fn(key: str, params: dict) -> None:
        calls.append((key, params))

    mailbox = _build_fallback_mailbox()
    account = mailbox.get_email(log_key_fn=log_key_fn)

    assert account.email == "ok@example.com"
    # 2 "trying" + 2 "failed" (provider_a, provider_b) + 1 "trying" + 1 "succeeded" (provider_c)
    attempt_keys = [key for key, _ in calls]
    assert attempt_keys.count("core.42add9d8") == 3  # "[Mailbox] 尝试 provider: {provider}"
    assert attempt_keys.count("core.0e91f5bb") == 2  # "[Mailbox] provider 失败: ..."
    assert attempt_keys.count("core.2e383f53") == 1  # "[Mailbox] 使用 provider 成功: ..."

    failed_providers = {params["provider"] for key, params in calls if key == "core.0e91f5bb"}
    assert failed_providers == {"provider_a", "provider_b"}

    succeeded = next(params for key, params in calls if key == "core.2e383f53")
    assert succeeded == {"provider": "provider_c", "email": "ok@example.com"}

    # Renders per ui_language, from the same recorded (key, params) pair.
    zh_message = t("core.2e383f53", "zh", **succeeded)
    en_message = t("core.2e383f53", "en", **succeeded)
    assert zh_message != en_message
    assert "provider_c" in zh_message and "provider_c" in en_message


def test_fallback_mailbox_get_email_all_providers_fail_raises_keyed_exception():
    calls: list[tuple[str, dict]] = []
    mailbox = FallbackMailbox([("provider_a", _AlwaysFailsMailbox()), ("provider_b", _AlwaysFailsMailbox())])

    with pytest.raises(RuntimeError) as excinfo:
        mailbox.get_email(log_key_fn=lambda key, params: calls.append((key, params)))

    exc = excinfo.value
    assert exc.i18n_key == "core.3ea3c220"
    assert "provider_a" in exc.i18n_params["errors"]
    assert "provider_b" in exc.i18n_params["errors"]
    assert t(exc.i18n_key, "zh", **exc.i18n_params) == str(exc)


# --- FallbackMailbox: no sink wired -- byte-identical print() fallback ---


def test_fallback_mailbox_get_email_no_sink_falls_back_to_print(capsys):
    mailbox = _build_fallback_mailbox()

    account = mailbox.get_email()

    assert account.email == "ok@example.com"
    out = capsys.readouterr().out
    assert "[Mailbox] 尝试 provider: provider_a" in out
    assert "[Mailbox] provider 失败: provider_a -> boom" in out
    assert "[Mailbox] provider 失败: provider_b -> boom" in out
    assert "[Mailbox] 尝试 provider: provider_c" in out
    assert "[Mailbox] 使用 provider 成功: provider_c -> ok@example.com" in out


# --- ensure_identity_email / ensure_oauth_browser_reuse: AD-17 keying ----


def test_ensure_identity_email_raises_with_i18n_key_and_params():
    ctx = _make_ctx(identity=None)
    ctx.identity = type("Identity", (), {"email": ""})()

    with pytest.raises(IdentityResolutionError) as excinfo:
        ensure_identity_email(ctx, "core.51eed862", platform="Test Platform")

    exc = excinfo.value
    assert exc.i18n_key == "core.51eed862"
    assert exc.i18n_params == {"platform": "Test Platform"}
    assert str(exc) == t("core.51eed862", "zh", platform="Test Platform")


def test_ensure_oauth_browser_reuse_raises_under_headless_executor():
    ctx = _make_ctx(executor_type="headless")
    ctx.identity = type("Identity", (), {"chrome_user_data_dir": "", "chrome_cdp_url": ""})()

    with pytest.raises(BrowserReuseRequiredError) as excinfo:
        ensure_oauth_browser_reuse(ctx, "core.727d286a", platform="Test Platform")

    exc = excinfo.value
    assert exc.i18n_key == "core.727d286a"
    assert exc.i18n_params == {"platform": "Test Platform"}


def test_ensure_identity_email_keyed_exception_forwarded_by_exc_key():
    """End-to-end AC: an ensure_* exception's i18n_key/i18n_params are
    forwarded untouched by application/tasks.py's existing _exc_key (story
    4.3), with zero code change needed there."""
    ctx = _make_ctx()
    ctx.identity = type("Identity", (), {"email": ""})()

    try:
        ensure_identity_email(ctx, "core.6814ed3f", platform="Test Platform")
        assert False, "expected IdentityResolutionError"
    except IdentityResolutionError as exc:
        key, params = _exc_key(exc, "application.fallback-key", detail=str(exc))

    assert key == "core.6814ed3f"
    assert params == {"platform": "Test Platform"}
    # Renders in both languages from the forwarded key/params.
    assert t(key, "en", **params) != t(key, "zh", **params)


# --- OtpSpec default-vs-override split (Design Notes' critical wrinkle) --


class _FakeMailboxForOtp(BaseMailbox):
    def __init__(self, code: str = "654321"):
        self._code = code

    def get_email(self, *, log_key_fn=None):
        return MailboxAccount(email="otp@example.com")

    def wait_for_code(self, account, keyword="", timeout=120, before_ids=None, code_pattern=None, *, log_key_fn=None):
        if log_key_fn is not None:
            log_key_fn("core.e9750390", {"code": self._code})
        return self._code

    def wait_for_link(self, account, keyword="", timeout=120, before_ids=None, *, log_key_fn=None):
        raise NotImplementedError

    def get_current_ids(self, account):
        return set()


def _ctx_with_otp_mailbox(*, log_key_fn=None, log_fn=None) -> RegistrationContext:
    platform = type("Platform", (), {"mailbox": _FakeMailboxForOtp()})()
    identity = type("Identity", (), {"mailbox_account": MailboxAccount(email="otp@example.com"), "before_ids": set()})()
    return _make_ctx(platform=platform, identity=identity, log_key_fn=log_key_fn, log_fn=log_fn)


def test_otp_spec_platform_override_uses_plain_log_unchanged():
    """A platform-supplied (non-None) wait_message/success_label stays plain
    ctx.log(...) text, unchanged -- that text is platform-owned and out of
    this story's scope."""
    plain_calls: list[str] = []
    key_calls: list[tuple[str, dict]] = []
    ctx = _ctx_with_otp_mailbox(
        log_key_fn=lambda key, params: key_calls.append((key, params)),
        log_fn=plain_calls.append,
    )

    otp_cb = build_otp_callback(
        ctx,
        wait_message="等待 TestPlatform 邮箱验证码...",
        success_label="验证码",
    )
    code = otp_cb()

    assert code == "654321"
    assert "等待 TestPlatform 邮箱验证码..." in plain_calls
    assert "验证码: 654321" in plain_calls
    # The mailbox-layer log_key_fn is still threaded through and fires
    # independently of the wait/success text choice.
    assert ("core.e9750390", {"code": "654321"}) in key_calls


def test_otp_spec_no_override_uses_keyed_log():
    """core/registration/adapters.py's default (None) wait_message/
    success_label renders through ctx.log_key(...) instead of plain text."""
    key_calls: list[tuple[str, dict]] = []
    ctx = _ctx_with_otp_mailbox(log_key_fn=lambda key, params: key_calls.append((key, params)))

    otp_cb = build_otp_callback(ctx)  # wait_message/success_label default to None
    code = otp_cb()

    assert code == "654321"
    keys = [key for key, _ in key_calls]
    assert "core.cfeae2ac" in keys  # "等待验证码..."
    assert ("core.52bc9ea2", {"code": "654321"}) in key_calls  # "验证码: {code}"


# --- OtpSpec/LinkSpec default() fields are None (Design Notes) ----------


def test_otp_spec_and_link_spec_defaults_are_none():
    from core.registration.adapters import LinkSpec, OtpSpec

    assert OtpSpec().wait_message is None
    assert OtpSpec().success_label is None
    assert LinkSpec().wait_message is None
    assert LinkSpec().success_label is None


# --- Reserved-name guard: a template param must never shadow t()'s/       ---
# --- _raise_keyed()'s own `key`/`lang` positional parameters (DW-44/45)  ---
# --- Review-round regression: 4 call sites minted `key=...` as a param   ---
# --- name, colliding with `_raise_keyed(exc_cls, key: str, **params)`'s ---
# --- and `t(key: str, lang: str, **params)`'s own `key` parameter --     ---
# --- `TypeError: got multiple values for argument 'key'` on every call. ---


def test_create_captcha_solver_unknown_provider_raises_keyed_not_typeerror():
    from core.base_captcha import create_captcha_solver

    with pytest.raises(RuntimeError) as excinfo:
        create_captcha_solver("nonexistent_captcha_provider_xyz")

    exc = excinfo.value
    assert exc.i18n_key == "core.293461f5"
    assert exc.i18n_params == {"provider": "nonexistent_captcha_provider_xyz"}
    assert t(exc.i18n_key, "zh", **exc.i18n_params) == str(exc)


def test_create_mailbox_unknown_provider_raises_keyed_not_typeerror():
    from core.base_mailbox import create_mailbox

    with pytest.raises(RuntimeError) as excinfo:
        create_mailbox("nonexistent_mailbox_provider_xyz")

    exc = excinfo.value
    assert exc.i18n_key == "core.2d7459e5"
    assert exc.i18n_params == {"provider": "nonexistent_mailbox_provider_xyz"}
    assert t(exc.i18n_key, "zh", **exc.i18n_params) == str(exc)


# --- _log_key_or_print never lets a sink failure mask the caller's real ---
# --- outcome: a success miscast as a failure, or an intended raise that ---
# --- never fires (review-round regression). -----------------------------


def test_fallback_mailbox_get_email_survives_a_raising_log_key_fn():
    def raising_log_key_fn(key: str, params: dict) -> None:
        raise ValueError("sink is broken")

    mailbox = _build_fallback_mailbox()
    account = mailbox.get_email(log_key_fn=raising_log_key_fn)

    assert account.email == "ok@example.com"
