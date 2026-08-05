"""Cursor 平台插件 — Cursor platform plugin"""
import json

from core.base_platform import BasePlatform, Account, AccountStatus, RegisterConfig
from core.base_mailbox import BaseMailbox
from core.registration import BrowserRegistrationAdapter, OtpSpec, ProtocolMailboxAdapter, ProtocolOAuthAdapter, RegistrationCapability, RegistrationResult
from core.registration.helpers import resolve_timeout
from core.registry import register
from platforms.cursor._i18n_helpers import _raise_keyed
from platforms.cursor.core import UA, CURSOR


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


_MISSING_TOKEN_MARKER = _marker("cursor.ba8781bf")
_QUOTA_NOTE_MARKER = _marker("cursor.e46763f7")


@register
class CursorPlatform(BasePlatform):
    name = "cursor"
    display_name = "Cursor"
    version = "1.0.0"
    supported_executors = ["protocol", "headless", "headed"]
    supported_identity_modes = ["mailbox"]
    protocol_captcha_order = ("2captcha", "capsolver", "auto")

    # Declarative capabilities
    capabilities = [
        "switch_desktop",   # Switch to desktop app
        "query_state",      # Query account state/quota
        "generate_link",    # Generate trial link
    ]

    def __init__(self, config: RegisterConfig = None, mailbox: BaseMailbox = None):
        super().__init__(config)
        self.mailbox = mailbox

    def _prepare_registration_password(self, password: str | None) -> str | None:
        return password

    def _map_mailbox_result(self, result: dict) -> RegistrationResult:
        return RegistrationResult(
            email=result["email"],
            password=result.get("password", ""),
            token=result.get("token", ""),
            status=AccountStatus.REGISTERED,
        )

    def _map_oauth_result(self, result: dict) -> RegistrationResult:
        return RegistrationResult(
            email=result["email"],
            password="",
            token=result.get("token", ""),
            status=AccountStatus.REGISTERED,
            extra={"user_info": result.get("user_info", {})},
        )

    def _run_browser_oauth(self, ctx) -> dict:
        from platforms.cursor.browser_oauth import register_with_browser_oauth

        return register_with_browser_oauth(
            proxy=ctx.proxy,
            oauth_provider=ctx.identity.oauth_provider,
            email_hint=ctx.identity.email,
            timeout=resolve_timeout(ctx.extra, ("browser_oauth_timeout", "manual_oauth_timeout"), 300),
            log_fn=ctx.log,
            log_key=ctx.log_key_fn,
            headless=(ctx.executor_type == "headless"),
            chrome_user_data_dir=ctx.identity.chrome_user_data_dir,
            chrome_cdp_url=ctx.identity.chrome_cdp_url,
        )

    def build_browser_registration_adapter(self):
        return BrowserRegistrationAdapter(
            result_mapper=lambda ctx, result: self._map_oauth_result(result) if ctx.identity.identity_provider == "oauth_browser" else self._map_mailbox_result(result),
            browser_worker_builder=lambda ctx, artifacts: __import__("platforms.cursor.browser_register", fromlist=["CursorBrowserRegister"]).CursorBrowserRegister(
                captcha=artifacts.captcha_solver,
                headless=(ctx.executor_type == "headless"),
                proxy=ctx.proxy,
                otp_callback=artifacts.otp_callback,
                phone_callback=artifacts.phone_callback,
                log_fn=ctx.log,
                log_key_fn=ctx.log_key_fn,
            ),
            browser_register_runner=lambda worker, ctx, artifacts: worker.run(
                email=ctx.identity.email,
                password=ctx.password or "",
            ),
            oauth_runner=self._run_browser_oauth,
            capability=RegistrationCapability(oauth_headless_requires_browser_reuse=True),
            otp_spec=OtpSpec(wait_message="等待 Cursor 邮箱验证码...", success_label="验证码"),
            use_captcha_for_mailbox=True,
        )

    def build_protocol_oauth_adapter(self):
        return ProtocolOAuthAdapter(
            oauth_runner=self._run_browser_oauth,
            result_mapper=lambda ctx, result: self._map_oauth_result(result),
        )

    def build_protocol_mailbox_adapter(self):
        return ProtocolMailboxAdapter(
            result_mapper=lambda ctx, result: self._map_mailbox_result(result),
            worker_builder=lambda ctx, artifacts: __import__("platforms.cursor.protocol_mailbox", fromlist=["CursorProtocolMailboxWorker"]).CursorProtocolMailboxWorker(
                proxy=ctx.proxy,
                log_fn=ctx.log,
                log_key_fn=ctx.log_key_fn,
            ),
            register_runner=lambda worker, ctx, artifacts: worker.run(
                email=ctx.identity.email,
                password=ctx.password,
                otp_callback=artifacts.otp_callback,
                captcha_solver=artifacts.captcha_solver,
            ),
            otp_spec=OtpSpec(wait_message="等待验证码..."),
            use_captcha=True,
        )

    def check_valid(self, account: Account) -> bool:
        from curl_cffi import requests as curl_req
        try:
            r = curl_req.get(
                f"{CURSOR}/api/auth/me",
                headers={"Cookie": f"WorkosCursorSessionToken={account.token}",
                         "user-agent": UA},
                impersonate="chrome124", timeout=15,
            )
            return r.status_code == 200
        except Exception:
            return False

    def get_platform_actions(self) -> list:
        """返回平台支持的操作列表 — Return the list of actions supported by the platform"""
        return [
            {"id": "switch_account", "label": "cursor.5b67f763", "params": []},
            {"id": "get_account_state", "label": "cursor.da0f5916", "params": []},
            {"id": "generate_trial_link", "label": "cursor.73608a10", "params": []},
        ]

    def get_desktop_state(self, lang: str = "zh") -> dict:
        from platforms.cursor.switch import get_cursor_desktop_state

        return get_cursor_desktop_state(lang)

    def execute_action(self, action_id: str, account: Account, params: dict) -> dict:
        """执行平台操作 — Execute a platform action"""
        if action_id == "switch_account":
            from platforms.cursor.switch import (
                get_cursor_billing_info,
                get_cursor_usage,
                get_cursor_user_info,
                has_cursor_valid_payment_method,
                read_current_cursor_account,
                restart_cursor_ide,
                summarize_cursor_usage,
                switch_cursor_account,
                get_cursor_desktop_state,
            )
            
            token = account.token
            if not token:
                return {"ok": False, "error": _MISSING_TOKEN_MARKER}
            
            ok, msg = switch_cursor_account(token)
            if not ok:
                return {"ok": False, "error": msg}
            
            user_info = get_cursor_user_info(token) or {}
            billing_info = get_cursor_billing_info(token) or {}
            has_payment_method = has_cursor_valid_payment_method(token)
            usage_info = get_cursor_usage(token, user_info.get("sub", "")) or {}
            usage_summary = summarize_cursor_usage(usage_info)
            current = read_current_cursor_account() or {}
            restart_ok, restart_msg = restart_cursor_ide()
            # msg/restart_msg 都已经是标记字符串；不能直接拼接两段还没渲染的
            # JSON，改用一个新的组合模板 key，把两个标记作为它的参数嵌套进去，
            # render_marker 会自底向上解析 (Design Notes: Composition example) —
            # msg/restart_msg are already marker strings; two still-encoded
            # markers must never be string-concatenated. Compose them instead
            # via a new template key whose params nest the two markers;
            # render_marker resolves them bottom-up.
            composed_message = (
                _marker("cursor.9311bf9d", switch_msg=msg, restart_msg=restart_msg)
                if restart_ok
                else msg
            )
            return {
                "ok": True,
                "data": {
                    "message": composed_message,
                    "valid": bool(user_info),
                    "remote_user": user_info,
                    "billing_info": billing_info,
                    "has_valid_payment_method": has_payment_method,
                    "usage_info": usage_info,
                    "usage_summary": usage_summary,
                    "local_app_account": {
                        "token_preview": _mask_secret(current.get("token", "")),
                        "matches_target": current.get("token") == token if current.get("token") else False,
                    },
                    "desktop_app_state": get_cursor_desktop_state(),
                    "restart": {"ok": restart_ok, "message": restart_msg},
                    "quota_note": _QUOTA_NOTE_MARKER,
                }
            }
        
        elif action_id in {"get_user_info", "get_account_state"}:
            from platforms.cursor.switch import (
                get_cursor_billing_info,
                get_cursor_usage,
                get_cursor_user_info,
                has_cursor_valid_payment_method,
                read_current_cursor_account,
                summarize_cursor_usage,
                get_cursor_desktop_state,
            )
            
            token = account.token
            if not token:
                return {"ok": False, "error": _MISSING_TOKEN_MARKER}
            
            user_info = get_cursor_user_info(token)
            if user_info:
                billing_info = get_cursor_billing_info(token) or {}
                has_payment_method = has_cursor_valid_payment_method(token)
                usage_info = get_cursor_usage(token, user_info.get("sub", "")) or {}
                usage_summary = summarize_cursor_usage(usage_info)
                current = read_current_cursor_account() or {}
                return {
                    "ok": True,
                    "data": {
                        "valid": True,
                        "remote_user": user_info,
                        "billing_info": billing_info,
                        "has_valid_payment_method": has_payment_method,
                        "trial_eligible": billing_info.get("trialEligible"),
                        "trial_length_days": billing_info.get("trialLengthDays"),
                        "membership_type": billing_info.get("membershipType") or billing_info.get("individualMembershipType", ""),
                        "usage_info": usage_info,
                        "usage_summary": usage_summary,
                        "local_app_account": {
                            "token_preview": _mask_secret(current.get("token", "")),
                            "matches_target": current.get("token") == token if current.get("token") else False,
                        },
                        "desktop_app_state": get_cursor_desktop_state(),
                        "quota_note": _QUOTA_NOTE_MARKER,
                    },
                }
            return {"ok": False, "error": _marker("cursor.2339340a")}

        elif action_id == "generate_trial_link":
            from platforms.cursor.switch import generate_cursor_checkout_link, get_cursor_billing_info

            token = account.token
            if not token:
                return {"ok": False, "error": _MISSING_TOKEN_MARKER}

            billing_info = get_cursor_billing_info(token) or {}
            checkout_url = generate_cursor_checkout_link(
                token,
                tier="pro",
                allow_trial=True,
                allow_automatic_payment=False,
                yearly=False,
            )
            if not checkout_url:
                return {"ok": False, "error": _marker("cursor.7de91b87")}
            return {
                "ok": True,
                "data": {
                    "url": checkout_url,
                    "message": _marker("cursor.ecfa3a44"),
                    "billing_info": billing_info,
                    "trial_eligible": billing_info.get("trialEligible"),
                    "trial_length_days": billing_info.get("trialLengthDays"),
                },
            }
        
        _raise_keyed(NotImplementedError, "cursor.701d383a", action_id=action_id)
        # was: raise NotImplementedError(f"未知操作: {action_id}") — was: raise NotImplementedError(f"Unknown action: {action_id}")
