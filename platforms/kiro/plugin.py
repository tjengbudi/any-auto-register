"""Kiro 平台插件 - 基于 AWS Builder ID 注册"""
import json

from core.base_platform import BasePlatform, Account, AccountStatus, RegisterConfig
from core.base_mailbox import BaseMailbox
from core.registration import BrowserRegistrationAdapter, OtpSpec, ProtocolMailboxAdapter, ProtocolOAuthAdapter, RegistrationCapability, RegistrationResult
from core.registration.helpers import resolve_timeout
from core.registry import register


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 12:
        return value
    return f"{value[:6]}...{value[-4:]}"


def _marker(key: str, **params) -> str:
    # worker 线程无请求上下文，写入标记字符串，由读边界渲染 (AD-3/AD-8) —
    # No request context in a worker thread; write a marker string, rendered
    # at the read boundary (AD-3/AD-8).
    return json.dumps({"i18n_key": key, "i18n_params": params}, ensure_ascii=False)


_REFRESH_FAILED_MARKER = _marker("kiro.6106f0a1")
_QUOTA_NOTE_MARKER = _marker("kiro.04b73b69")


def _kiro_local_matches_target(current: dict, access_token: str, refresh_token: str) -> bool:
    current_refresh = current.get("refreshToken", "")
    if current_refresh and refresh_token:
        return current_refresh == refresh_token
    current_access = current.get("accessToken", "")
    if current_access and access_token:
        return current_access == access_token
    return False


@register
class KiroPlatform(BasePlatform):
    name = "kiro"
    display_name = "Kiro"
    version = "1.0.0"
    supported_executors = ["protocol", "headless", "headed"]
    supported_identity_modes = ["mailbox"]
    protocol_captcha_order = ("2captcha", "capsolver", "auto")

    # Declarative capabilities
    capabilities = [
        "switch_desktop",   # Switch to desktop app
        "refresh_token",    # Refresh token
        "query_state",      # Query account state/quota
    ]

    def __init__(self, config: RegisterConfig = None, mailbox: BaseMailbox = None):
        super().__init__(config)
        self.mailbox = mailbox

    def _prepare_registration_password(self, password: str | None) -> str | None:
        return password or ""

    def _map_kiro_result(self, result: dict, *, password: str = "", oauth_provider: str = "") -> RegistrationResult:
        return RegistrationResult(
            email=result["email"],
            password=password or result.get("password", ""),
            token=result.get("accessToken", ""),
            status=AccountStatus.REGISTERED,
            extra={
                "name": result.get("name", ""),
                "accessToken": result.get("accessToken", ""),
                "sessionToken": result.get("sessionToken", ""),
                "csrfToken": result.get("csrfToken", ""),
                "oauthProvider": oauth_provider or result.get("oauthProvider", ""),
                "clientId": result.get("clientId", ""),
                "clientSecret": result.get("clientSecret", ""),
                "refreshToken": result.get("refreshToken", ""),
            },
        )

    def _run_protocol_oauth(self, ctx) -> dict:
        from platforms.kiro.browser_oauth import register_with_browser_oauth

        return register_with_browser_oauth(
            proxy=ctx.proxy,
            oauth_provider=ctx.identity.oauth_provider,
            email_hint=ctx.identity.email,
            timeout=resolve_timeout(ctx.extra, ("browser_oauth_timeout", "manual_oauth_timeout"), 300),
            log_fn=ctx.log,
            headless=(ctx.executor_type == "headless"),
            chrome_user_data_dir=ctx.identity.chrome_user_data_dir,
            chrome_cdp_url=ctx.identity.chrome_cdp_url,
        )

    def build_browser_registration_adapter(self):
        return BrowserRegistrationAdapter(
            result_mapper=lambda ctx, result: self._map_kiro_result(result, oauth_provider=ctx.identity.oauth_provider),
            browser_worker_builder=lambda ctx, artifacts: __import__("platforms.kiro.browser_register", fromlist=["KiroBrowserRegister"]).KiroBrowserRegister(
                headless=(ctx.executor_type == "headless"),
                proxy=ctx.proxy,
                otp_callback=artifacts.otp_callback,
                log_fn=ctx.log,
            ),
            browser_register_runner=lambda worker, ctx, artifacts: worker.run(
                email=ctx.identity.email or "",
                password=ctx.password or "",
            ),
            oauth_runner=self._run_protocol_oauth,
            capability=RegistrationCapability(oauth_headless_requires_browser_reuse=True),
            otp_spec=OtpSpec(wait_message="等待验证码..."),
        )

    def build_protocol_oauth_adapter(self):
        return ProtocolOAuthAdapter(
            oauth_runner=self._run_protocol_oauth,
            result_mapper=lambda ctx, result: self._map_kiro_result(result, oauth_provider=ctx.identity.oauth_provider),
        )

    def build_protocol_mailbox_adapter(self):
        def _build_worker(ctx, artifacts):
            from platforms.kiro.protocol_mailbox import KiroProtocolMailboxWorker

            return KiroProtocolMailboxWorker(proxy=ctx.proxy, tag="KIRO", log_fn=ctx.log)

        def _run_worker(worker, ctx, artifacts):
            return worker.run(
                email=ctx.identity.email,
                password=ctx.password,
                name=ctx.extra.get("name", "Kiro User"),
                mail_token=getattr(ctx.identity.mailbox_account, "account_id", "") or None,
                otp_timeout=resolve_timeout(ctx.extra, ("otp_timeout",), 120),
                otp_callback=artifacts.otp_callback,
            )

        return ProtocolMailboxAdapter(
            result_mapper=lambda ctx, result: self._map_kiro_result(result),
            worker_builder=_build_worker,
            register_runner=_run_worker,
            otp_spec=OtpSpec(
                wait_message="等待验证码...",
                timeout=resolve_timeout(self.config.extra or {}, ("otp_timeout",), 120),
            ),
        )

    def check_valid(self, account: Account) -> bool:
        """通过 refreshToken 检测账号是否有效"""
        extra = account.extra or {}
        refresh_token = extra.get("refreshToken", "")
        if not refresh_token:
            return bool(extra.get("accessToken", "") or account.token)
        try:
            from platforms.kiro.switch import refresh_kiro_token
            ok, _ = refresh_kiro_token(
                refresh_token,
                extra.get("clientId", ""),
                extra.get("clientSecret", ""),
            )
            return ok
        except Exception:
            return False

    def get_platform_actions(self) -> list:
        return [
            {"id": "switch_account", "label": "kiro.5b67f763", "params": []},
            {"id": "refresh_token", "label": "kiro.26dc9dcc", "params": []},
            {"id": "get_account_state", "label": "kiro.da0f5916", "params": []},
        ]

    def get_desktop_state(self, lang: str = "zh") -> dict:
        from platforms.kiro.switch import get_kiro_desktop_state

        return get_kiro_desktop_state(lang)

    def execute_action(self, action_id: str, account: Account, params: dict) -> dict:
        extra = account.extra or {}

        if action_id == "switch_account":
            from platforms.kiro.switch import (
                get_kiro_portal_state,
                read_current_kiro_account,
                refresh_kiro_token,
                restart_kiro_ide,
                summarize_kiro_usage,
                switch_kiro_account,
                get_kiro_desktop_state,
            )

            access_token = extra.get("accessToken", "") or account.token
            refresh_token = extra.get("refreshToken", "")
            client_id = extra.get("clientId", "")
            client_secret = extra.get("clientSecret", "")
            session_token = extra.get("sessionToken", "")
            profile_arn = extra.get("profileArn", "")
            oauth_provider = (extra.get("oauthProvider", "") or "").strip().lower()
            refresh_result = {"ok": False, "message": _marker("kiro.cfa125f5")}

            if refresh_token and client_id and client_secret:
                ok, result = refresh_kiro_token(refresh_token, client_id, client_secret)
                if ok:
                    access_token = result["accessToken"]
                    refresh_token = result.get("refreshToken", refresh_token)
                    refresh_result = {
                        "ok": True,
                        "expiresIn": result.get("expiresIn", 0),
                        "refreshTokenUpdated": refresh_token != extra.get("refreshToken", ""),
                    }
                else:
                    refresh_result = {"ok": False, "message": result.get("error", _REFRESH_FAILED_MARKER)}

            switch_kwargs = {}
            if oauth_provider in ("google", "github"):
                switch_kwargs["auth_method"] = "social"
                switch_kwargs["provider"] = "Google" if oauth_provider == "google" else "GitHub"

            ok, msg = switch_kiro_account(
                access_token=access_token,
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
                **switch_kwargs,
            )
            if not ok:
                return {"ok": False, "error": msg}

            current = read_current_kiro_account() or {}
            portal_state = get_kiro_portal_state(access_token, session_token, profile_arn=profile_arn) or {}
            usage_summary = summarize_kiro_usage(portal_state)
            restart_ok, restart_msg = restart_kiro_ide()
            # msg/restart_msg 都已经是标记字符串；不能直接拼接两段还没渲染的
            # JSON，改用一个新的组合模板 key，把两个标记作为它的参数嵌套进去，
            # render_marker 会自底向上解析 (Design Notes: Composition example) —
            # msg/restart_msg are already marker strings; two still-encoded
            # markers must never be string-concatenated. Compose them instead
            # via a new template key whose params nest the two markers;
            # render_marker resolves them bottom-up.
            composed_message = (
                _marker("kiro.9311bf9d", switch_msg=msg, restart_msg=restart_msg)
                if restart_ok
                else msg
            )
            return {"ok": True, "data": {
                "message": composed_message,
                "access_token": access_token,
                "accessToken": access_token,
                "refreshToken": refresh_token,
                "remote_validation": refresh_result,
                "portal_user": portal_state.get("user_info", {}),
                "usage_limits": portal_state.get("usage_limits", {}),
                "available_subscription_plans": portal_state.get("available_subscription_plans", {}),
                "usage_summary": usage_summary,
                "portal_session": {
                    "has_session_token": bool(session_token),
                    "user_id": portal_state.get("user_id", ""),
                    "profile_arn": portal_state.get("profile_arn", profile_arn),
                    "available": portal_state.get("available", False),
                    "error": portal_state.get("error", ""),
                },
                "local_app_account": {
                    "provider": current.get("provider", ""),
                    "authMethod": current.get("authMethod", ""),
                    "accessTokenPreview": _mask_secret(current.get("accessToken", "")),
                    "matches_target": _kiro_local_matches_target(current, access_token, refresh_token),
                },
                "desktop_app_state": get_kiro_desktop_state(),
                "restart": {"ok": restart_ok, "message": restart_msg},
                "quota_note": _QUOTA_NOTE_MARKER,
            }}

        elif action_id == "refresh_token":
            from platforms.kiro.switch import refresh_kiro_token

            refresh_token = extra.get("refreshToken", "")
            client_id = extra.get("clientId", "")
            client_secret = extra.get("clientSecret", "")

            ok, result = refresh_kiro_token(refresh_token, client_id, client_secret)
            if ok:
                new_access = result["accessToken"]
                new_refresh = result.get("refreshToken", refresh_token)
                return {
                    "ok": True,
                    "data": {
                        "access_token": new_access,
                        "accessToken": new_access,
                        "refreshToken": new_refresh,
                    },
                }
            return {"ok": False, "error": result.get("error", _REFRESH_FAILED_MARKER)}

        elif action_id == "get_account_state":
            from platforms.kiro.switch import (
                get_kiro_portal_state,
                read_current_kiro_account,
                refresh_kiro_token,
                summarize_kiro_usage,
                get_kiro_desktop_state,
            )

            refresh_token = extra.get("refreshToken", "")
            client_id = extra.get("clientId", "")
            client_secret = extra.get("clientSecret", "")
            session_token = extra.get("sessionToken", "")
            profile_arn = extra.get("profileArn", "")
            current = read_current_kiro_account() or {}
            refresh_state = {"ok": False, "message": _marker("kiro.42414eea")}
            access_token = extra.get("accessToken", "") or account.token
            if refresh_token and client_id and client_secret:
                ok, result = refresh_kiro_token(refresh_token, client_id, client_secret)
                if ok:
                    access_token = result["accessToken"]
                    refresh_state = {"ok": True, "expiresIn": result.get("expiresIn", 0)}
                else:
                    refresh_state = {"ok": False, "message": result.get("error", _REFRESH_FAILED_MARKER)}
            portal_state = get_kiro_portal_state(access_token, session_token, profile_arn=profile_arn) or {}
            usage_summary = summarize_kiro_usage(portal_state)
            return {
                "ok": True,
                "data": {
                    "access_token": access_token,
                    "accessToken": access_token,
                    "remote_validation": refresh_state,
                    "portal_user": portal_state.get("user_info", {}),
                    "usage_limits": portal_state.get("usage_limits", {}),
                    "available_subscription_plans": portal_state.get("available_subscription_plans", {}),
                    "usage_summary": usage_summary,
                    "portal_session": {
                        "has_session_token": bool(session_token),
                        "user_id": portal_state.get("user_id", ""),
                        "profile_arn": portal_state.get("profile_arn", profile_arn),
                        "available": portal_state.get("available", False),
                        "error": portal_state.get("error", ""),
                    },
                    "local_app_account": {
                        "provider": current.get("provider", ""),
                        "authMethod": current.get("authMethod", ""),
                        "accessTokenPreview": _mask_secret(current.get("accessToken", "")),
                        "matches_target": _kiro_local_matches_target(current, access_token, refresh_token),
                    },
                    "desktop_app_state": get_kiro_desktop_state(),
                    "quota_note": _QUOTA_NOTE_MARKER,
                },
            }

        raise NotImplementedError(f"未知操作: {action_id}")
