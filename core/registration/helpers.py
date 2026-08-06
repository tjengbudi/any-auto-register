from __future__ import annotations

from typing import Any

from core.base_sms import create_phone_callbacks
from i18n import t

from .errors import BrowserReuseRequiredError, IdentityResolutionError, RegistrationUnsupportedError
from .models import RegistrationContext


def _raise_keyed(exc_cls, key: str, **params) -> None:
    # AD-17: 异常携带 i18n_key/i18n_params，供 application/tasks.py 的 _exc_key 转发 —
    # AD-17: the exception carries i18n_key/i18n_params for application/tasks.py's
    # _exc_key to forward at the catch site.
    exc = exc_cls(t(key, "zh", **params))
    exc.i18n_key = key
    exc.i18n_params = params
    raise exc


def has_reusable_oauth_browser(identity: Any) -> bool:
    return bool((getattr(identity, "chrome_user_data_dir", "") or "").strip() or (getattr(identity, "chrome_cdp_url", "") or "").strip())


def resolve_timeout(extra: dict[str, Any], keys: tuple[str, ...], default: int) -> int:
    for key in keys:
        value = extra.get(key)
        if value not in (None, ""):
            return int(value)
    return int(default)


def ensure_identity_email(ctx: RegistrationContext, key: str, **params) -> None:
    if not getattr(ctx.identity, "email", ""):
        _raise_keyed(IdentityResolutionError, key, **params)


def ensure_mailbox_identity(ctx: RegistrationContext, key: str, **params) -> None:
    if not getattr(ctx.identity, "has_mailbox", False):
        _raise_keyed(IdentityResolutionError, key, **params)


def ensure_oauth_executor_allowed(ctx: RegistrationContext, allowed_executor_types: tuple[str, ...] | None, key: str | None = None, **params) -> None:
    if not allowed_executor_types:
        return
    if ctx.executor_type not in allowed_executor_types:
        if key is None:
            key = "core.e180ad44"  # "{platform} 当前 OAuth 仅支持 executor_type={expected}"
            # "{platform} currently only supports OAuth with executor_type={expected}"
            params = {**params, "platform": ctx.platform_display_name, "expected": ", ".join(allowed_executor_types)}
        _raise_keyed(RegistrationUnsupportedError, key, **params)


def ensure_oauth_browser_reuse(ctx: RegistrationContext, key: str, **params) -> None:
    if not has_reusable_oauth_browser(ctx.identity):
        _raise_keyed(BrowserReuseRequiredError, key, **params)


def build_otp_callback(
    ctx: RegistrationContext,
    *,
    keyword: str = "",
    timeout: int | None = None,
    code_pattern: str | None = None,
    wait_message: str | None = None,
    success_label: str | None = None,
):
    mailbox = getattr(ctx.platform, "mailbox", None)
    mail_acct = getattr(ctx.identity, "mailbox_account", None)
    if not mailbox or not mail_acct:
        return None

    def otp_cb():
        if wait_message is not None:
            ctx.log(wait_message)
        else:
            ctx.log_key("core.cfeae2ac")  # "等待验证码..." — "Waiting for the verification code..."
        kwargs = {
            "keyword": keyword,
            "before_ids": getattr(ctx.identity, "before_ids", set()),
            # ctx.log_key_fn (raw (key, params) callable) -- ctx.log_key
            # itself is a (key, **params) method and would crash the
            # log_key_fn: Callable[[str, dict], None] contract when the
            # mailbox layer calls it as fn(key, params_dict).
            "log_key_fn": ctx.log_key_fn,
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        if code_pattern:
            kwargs["code_pattern"] = code_pattern
        code = mailbox.wait_for_code(mail_acct, **kwargs)
        if code:
            if success_label is not None:
                ctx.log(f"{success_label}: {code}")
            else:
                ctx.log_key("core.52bc9ea2", code=code)  # "验证码: {code}" — "Verification code: {code}"
        return code

    return otp_cb


def build_phone_callbacks(ctx: RegistrationContext, *, service: str | None = None):
    from infrastructure.provider_definitions_repository import ProviderDefinitionsRepository
    from infrastructure.provider_settings_repository import ProviderSettingsRepository

    extra = ctx.extra
    requested_provider_key = str(
        extra.get("sms_provider")
        or extra.get("phone_provider")
        or ""
    ).strip()
    settings_repo = ProviderSettingsRepository()
    definitions_repo = ProviderDefinitionsRepository()

    provider_key = requested_provider_key
    source = "task params"
    if not provider_key:
        provider_key = str(settings_repo.get_default_provider_key("sms") or "").strip()
        source = "global default"
    if not provider_key:
        if extra.get("sms_activate_api_key"):
            provider_key = "sms_activate"
            source = "legacy sms_activate_api_key"
    if not provider_key:
        ctx.log_key("core.ea0e6bf1")  # "[SMS] 未配置 SMS provider（...），phone_callback=None — 注册到 add_phone 步骤将抛错"
        # "[SMS] no SMS provider configured (...), phone_callback=None -- registration will raise at the add_phone step"
        return None, None

    definition = definitions_repo.get_by_key("sms", provider_key)
    merged = settings_repo.resolve_runtime_settings("sms", provider_key, extra) if definition else dict(extra)

    auth_fields = []
    if definition:
        auth_fields = [
            str(field.get("key") or "").strip()
            for field in definition.get_fields()
            if str(field.get("category") or "").strip() == "auth"
        ]
    if auth_fields and not any(str(merged.get(field_key, "")).strip() for field_key in auth_fields):
        ctx.log_key("core.97cd10fd", provider=provider_key, source=source, fields=str(auth_fields))
        return None, None

    if ctx.proxy and not str(merged.get("sms_proxy") or merged.get("proxy") or "").strip():
        merged["sms_proxy"] = ctx.proxy

    country = str(
        merged.get("sms_country")
        or merged.get("phone_country")
        or merged.get("sms_activate_country")
        or merged.get("sms_activate_default_country")
        or merged.get("herosms_country")
        or merged.get("herosms_default_country")
        or merged.get("smsbower_country")
        or merged.get("smsbower_default_country")
        or ""
    ).strip()
    sms_service = str(
        merged.get("sms_service")
        or merged.get("herosms_service")
        or merged.get("herosms_default_service")
        or merged.get("smsbower_service")
        or merged.get("smsbower_default_service")
        or merged.get("sms_activate_service")
        or merged.get("sms_activate_default_service")
        or service
        or ctx.platform_name
    ).strip() or ctx.platform_name
    ctx.log_key("core.789e66e3", provider=provider_key, source=source, service=sms_service, country=country or "default")
    return create_phone_callbacks(
        provider_key,
        merged,
        service=sms_service,
        country=country,
        log_fn=ctx.log,
        # ctx.log_key_fn, not ctx.log_key -- see build_otp_callback's kwargs above.
        log_key_fn=ctx.log_key_fn,
    )


def build_link_callback(
    ctx: RegistrationContext,
    *,
    keyword: str = "",
    timeout: int | None = None,
    wait_message: str | None = None,
    success_label: str | None = None,
    preview_chars: int = 80,
):
    mailbox = getattr(ctx.platform, "mailbox", None)
    mail_acct = getattr(ctx.identity, "mailbox_account", None)
    if not mailbox or not mail_acct:
        return None

    def link_cb():
        if wait_message is not None:
            ctx.log(wait_message)
        else:
            ctx.log_key("core.479bedce")  # "等待验证链接邮件..." — "Waiting for the verification link email..."
        before_ids = mailbox.get_current_ids(mail_acct)
        # ctx.log_key_fn, not ctx.log_key -- see build_otp_callback's kwargs above.
        kwargs = {"keyword": keyword, "before_ids": before_ids, "log_key_fn": ctx.log_key_fn}
        if timeout is not None:
            kwargs["timeout"] = timeout
        link = mailbox.wait_for_link(mail_acct, **kwargs)
        if link:
            preview = link if len(link) <= preview_chars else f"{link[:preview_chars]}..."
            if success_label is not None:
                ctx.log(f"{success_label}: {preview}")
            else:
                ctx.log_key("core.015a4247", preview=preview)  # "验证链接: {preview}" — "Verification link: {preview}"
        return link

    return link_cb
