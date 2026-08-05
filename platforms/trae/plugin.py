"""Trae.ai 平台插件"""
import json

from core.base_platform import BasePlatform, Account, AccountStatus, RegisterConfig
from core.base_mailbox import BaseMailbox
from core.registration import BrowserRegistrationAdapter, OtpSpec, ProtocolMailboxAdapter, ProtocolOAuthAdapter, RegistrationCapability, RegistrationResult
from core.registration.helpers import resolve_timeout
from core.registry import register
from platforms.trae._i18n_helpers import _raise_keyed


def _marker(key: str, **params) -> str:
    # worker 线程无请求上下文，写入标记字符串，由读边界渲染 (AD-3/AD-8) —
    # No request context in a worker thread; write a marker string, rendered
    # at the read boundary (AD-3/AD-8).
    return json.dumps({"i18n_key": key, "i18n_params": params}, ensure_ascii=False)


@register
class TraePlatform(BasePlatform):
    name = "trae"
    display_name = "Trae.ai"
    version = "1.0.0"
    # 平台能力：首次启动时写入 platform_capability_overrides 表；
    # 后续启动做增量合并，不会覆盖运维在 DB 中禁用的项。
    # Platform capabilities: written to the platform_capability_overrides table
    # on first startup; later startups merge incrementally and never re-enable
    # entries that ops has disabled in the DB.
    supported_executors = ["protocol", "headless", "headed"]
    supported_identity_modes = ["mailbox", "oauth_browser"]
    supported_oauth_providers = ["google", "github"]

    def __init__(self, config: RegisterConfig = None, mailbox: BaseMailbox = None):
        super().__init__(config)
        self.mailbox = mailbox

    def _prepare_registration_password(self, password: str | None) -> str | None:
        return password or ""

    def _map_trae_result(self, result: dict, *, password: str = "") -> RegistrationResult:
        return RegistrationResult(
            email=result["email"],
            password=password or result.get("password", ""),
            user_id=result.get("user_id", ""),
            token=result.get("token", ""),
            region=result.get("region", ""),
            status=AccountStatus.REGISTERED,
            extra={
                "cashier_url": result.get("cashier_url", ""),
                "ai_pay_host": result.get("ai_pay_host", ""),
                "final_url": result.get("final_url", ""),
            },
        )

    def _run_protocol_oauth(self, ctx) -> dict:
        from platforms.trae.browser_oauth import register_with_browser_oauth

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
            result_mapper=lambda ctx, result: self._map_trae_result(result),
            browser_worker_builder=lambda ctx, artifacts: __import__("platforms.trae.browser_register", fromlist=["TraeBrowserRegister"]).TraeBrowserRegister(
                headless=(ctx.executor_type == "headless"),
                proxy=ctx.proxy,
                otp_callback=artifacts.otp_callback,
                log_fn=ctx.log,
                log_key_fn=ctx.log_key_fn,
            ),
            browser_register_runner=lambda worker, ctx, artifacts: worker.run(
                email=ctx.identity.email or "",
                password=ctx.password or "",
            ),
            oauth_runner=self._run_protocol_oauth,
            capability=RegistrationCapability(oauth_allowed_executor_types=("headed",)),
            otp_spec=OtpSpec(wait_message="等待验证码..."),
        )

    def build_protocol_oauth_adapter(self):
        return ProtocolOAuthAdapter(
            oauth_runner=self._run_protocol_oauth,
            result_mapper=lambda ctx, result: self._map_trae_result(result),
        )

    def build_protocol_mailbox_adapter(self):
        return ProtocolMailboxAdapter(
            result_mapper=lambda ctx, result: self._map_trae_result(result),
            worker_builder=lambda ctx, artifacts: __import__("platforms.trae.protocol_mailbox", fromlist=["TraeProtocolMailboxWorker"]).TraeProtocolMailboxWorker(
                executor=artifacts.executor,
                log_fn=ctx.log,
                log_key_fn=ctx.log_key_fn,
            ),
            register_runner=lambda worker, ctx, artifacts: worker.run(
                email=ctx.identity.email,
                password=ctx.password,
                otp_callback=artifacts.otp_callback,
            ),
            otp_spec=OtpSpec(wait_message="等待验证码..."),
            use_executor=True,
        )

    def check_valid(self, account: Account) -> bool:
        return bool(account.token)

    def get_platform_actions(self) -> list:
        """返回平台支持的操作列表"""
        return [
            {"id": "switch_account", "label": "trae.5b67f763", "params": []},
            {"id": "get_user_info", "label": "trae.3012e673", "params": []},
            {"id": "get_cashier_url", "label": "trae.c90d6d67", "params": []},
        ]

    def execute_action(self, action_id: str, account: Account, params: dict) -> dict:
        """执行平台操作"""
        if action_id == "switch_account":
            from platforms.trae.switch import switch_trae_account, restart_trae_ide
            
            token = account.token
            user_id = account.user_id or ""
            email = account.email or ""
            region = account.region or ""
            
            if not token:
                return {"ok": False, "error": _marker("trae.ba8781bf")}

            ok, msg = switch_trae_account(token, user_id, email, region)
            if not ok:
                return {"ok": False, "error": msg}

            restart_ok, restart_msg = restart_trae_ide()
            # msg/restart_msg 都已经是标记字符串；不能直接拼接两段还没渲染的
            # JSON，改用一个新的组合模板 key，把两个标记作为它的参数嵌套进去，
            # render_marker 会自底向上解析 (Design Notes: Composition example) —
            # msg/restart_msg are already marker strings; two still-encoded
            # markers must never be string-concatenated. Compose them instead
            # via a new template key whose params nest the two markers;
            # render_marker resolves them bottom-up.
            composed_message = (
                _marker("trae.9311bf9d", switch_msg=msg, restart_msg=restart_msg)
                if restart_ok
                else msg
            )
            return {
                "ok": True,
                "data": {
                    "message": composed_message,
                }
            }
        
        elif action_id == "get_user_info":
            from platforms.trae.switch import get_trae_user_info
            
            token = account.token
            if not token:
                return {"ok": False, "error": _marker("trae.ba8781bf")}

            user_info = get_trae_user_info(token)
            if user_info:
                return {"ok": True, "data": user_info}
            return {"ok": False, "error": _marker("trae.2339340a")}
        
        elif action_id == "get_cashier_url":
            from platforms.trae.core import TraeRegister
            with self._make_executor() as ex:
                reg = TraeRegister(executor=ex)
                # 重新登录刷新 session，再获取新 token 和 cashier_url — Re-login to refresh the session, then fetch a new token and cashier_url
                reg.step4_trae_login()
                token = reg.step5_get_token()
                if not token:
                    token = account.token
                cashier_url = reg.step7_create_order(token)
            if not cashier_url:
                return {"ok": False, "error": _marker("trae.4f63142e")}
            return {"ok": True, "data": {"cashier_url": cashier_url, "message": _marker("trae.2a2280d2")}}

        _raise_keyed(NotImplementedError, "trae.701d383a", action_id=action_id)
        # was: raise NotImplementedError(f"未知操作: {action_id}")
        # was: raise NotImplementedError(f"Unknown action: {action_id}")
