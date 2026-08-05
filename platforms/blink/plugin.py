"""blink.new 平台插件"""
import json

from core.base_mailbox import BaseMailbox
from core.base_platform import Account, AccountStatus, BasePlatform, RegisterConfig
from core.registration import LinkSpec, ProtocolMailboxAdapter, RegistrationResult
from core.registry import register
from platforms.blink._i18n_helpers import _raise_keyed
from platforms.blink.core import BLINK_BASE, BLINK_PRICE_IDS, BlinkRegister, load_blink_account_state


def _status_from_overview(overview: dict) -> AccountStatus:
    plan_state = str((overview or {}).get("plan_state") or "").strip().lower()
    if plan_state == "subscribed":
        return AccountStatus.SUBSCRIBED
    if plan_state == "trial":
        return AccountStatus.TRIAL
    if plan_state == "expired":
        return AccountStatus.EXPIRED
    return AccountStatus.REGISTERED


@register
class BlinkPlatform(BasePlatform):
    name = "blink"
    display_name = "Blink.new"
    version = "1.0.0"
    # 平台能力：首次启动时写入 platform_capability_overrides 表；
    # 后续启动做增量合并，不会覆盖运维在 DB 中禁用的项。
    # Platform capabilities: written to the platform_capability_overrides table
    # on first startup; later startups merge incrementally and never re-enable
    # entries that ops has disabled in the DB.
    supported_executors = ["protocol"]
    supported_identity_modes = ["mailbox"]

    def __init__(self, config: RegisterConfig = None, mailbox: BaseMailbox = None):
        super().__init__(config)
        self.mailbox = mailbox

    def _prepare_registration_password(self, password: str | None) -> str | None:
        # blink.new 无密码，magic link 登录 — blink.new has no password; login is via magic link
        return ""

    def _map_blink_result(self, result: dict) -> RegistrationResult:
        overview = dict(result.get("account_overview") or {})
        return RegistrationResult(
            email=result["email"],
            password="",
            user_id=result.get("user_id", ""),
            token=result.get("firebase_refresh_token") or result.get("refresh_token", ""),
            status=_status_from_overview(overview),
            extra={
                "access_token": result.get("access_token", ""),
                "refresh_token": result.get("refresh_token", ""),
                "id_token": result.get("id_token", ""),
                "firebase_refresh_token": result.get("firebase_refresh_token", ""),
                "session_token": result.get("session_token", ""),
                "workspace_slug": result.get("workspace_slug", ""),
                "workspace_id": result.get("workspace_id", ""),
                "customer_id": result.get("customer_id", ""),
                "referral_code": result.get("referral_code", ""),
                "cashier_url": result.get("cashier_url", ""),
                "account_overview": overview,
            },
        )

    def build_protocol_mailbox_adapter(self):
        def _build_worker(ctx, artifacts):
            from platforms.blink.protocol_mailbox import BlinkProtocolMailboxWorker

            return BlinkProtocolMailboxWorker(proxy=ctx.proxy, log_fn=ctx.log, log_key_fn=ctx.log_key_fn)

        def _run_worker(worker, ctx, artifacts):
            return worker.run(
                email=ctx.identity.email,
                link_callback=artifacts.verification_link_callback,
            )

        return ProtocolMailboxAdapter(
            result_mapper=lambda ctx, result: self._map_blink_result(result),
            worker_builder=_build_worker,
            register_runner=_run_worker,
            link_spec=LinkSpec(
                keyword="magic_token",
                wait_message="等待魔法链接邮件...",
                success_label="魔法链接",
            ),
        )

    def _load_state(self, account: Account, *, force_refresh: bool = False) -> dict:
        return load_blink_account_state(
            account,
            proxy=self.config.proxy if self.config else None,
            log_fn=self.log,
            log_key=self._log_key_fn,
            force_refresh=force_refresh,
        )

    def check_valid(self, account: Account) -> bool:
        try:
            state = self._load_state(account)
        except Exception:
            return False
        return bool((state.get("summary") or {}).get("valid"))

    def get_platform_actions(self) -> list:
        return [
            {"id": "get_account_state", "label": "blink.a7517bf2", "params": []},
            {"id": "generate_checkout_link", "label": "blink.8e7f6e2f", "params": []},
            {
                "id": "create_api_key",
                "label": "blink.3c077658",
                "params": [
                    {"key": "name", "label": "blink.c073886a", "type": "text"},
                ],
            },
        ]

    def execute_action(self, action_id: str, account: Account, params: dict) -> dict:
        if action_id in {"get_user_info", "get_account_state"}:
            state = self._load_state(account)
            return {"ok": True, "data": state.get("summary", {})}

        if action_id in {"generate_checkout_link", "payment_link", "get_cashier_url"}:
            state = self._load_state(account, force_refresh=True)
            summary = dict(state.get("summary") or {})
            workspace_id = str(state.get("workspace_id") or summary.get("workspace_id") or "")
            if not workspace_id:
                # worker 线程无请求上下文，写入标记字符串，读边界渲染 (AD-3/AD-8) —
                # No request context in a worker thread; write a marker string,
                # rendered at the read boundary (AD-3/AD-8).
                return {"ok": False, "error": json.dumps({"i18n_key": "blink.41497ce5", "i18n_params": {}}, ensure_ascii=False)}

            plan_id = str(params.get("plan_id") or "pro").strip().lower() or "pro"
            price_id = str(params.get("price_id") or BLINK_PRICE_IDS.get(plan_id) or "").strip()
            if not price_id:
                # worker 线程无请求上下文，写入标记字符串，读边界渲染 (AD-3/AD-8) —
                # No request context in a worker thread; write a marker string,
                # rendered at the read boundary (AD-3/AD-8).
                return {
                    "ok": False,
                    "error": json.dumps(
                        {"i18n_key": "blink.74e4501a", "i18n_params": {"plan_id": plan_id}},
                        ensure_ascii=False,
                    ),
                }

            workspace_slug = str(state.get("workspace_slug") or summary.get("workspace_slug") or "").strip()
            cancel_url = str(
                params.get("cancel_url")
                or (f"{BLINK_BASE}/{workspace_slug}?showPricing=true" if workspace_slug else f"{BLINK_BASE}/?showPricing=true")
            ).strip()

            client = BlinkRegister(proxy=self.config.proxy if self.config else None)
            client._log = self.log
            client._log_key_fn = self._log_key_fn
            checkout = client.create_checkout(
                state.get("id_token", ""),
                price_id=price_id,
                plan_id=plan_id,
                workspace_id=workspace_id,
                cancel_url=cancel_url,
                session_token=str(state.get("session_token") or ""),
                workspace_slug=workspace_slug,
                tolt_referral_id=params.get("tolt_referral_id"),
            )
            url = str(checkout.get("url") or "").strip()
            if not url:
                return {"ok": False, "error": json.dumps({"i18n_key": "blink.8932cb51", "i18n_params": {}}, ensure_ascii=False)}
            return {
                "ok": True,
                "data": {
                    "url": url,
                    "cashier_url": url,
                    "session_id": str(checkout.get("sessionId") or ""),
                    "workspace_id": workspace_id,
                    "workspace_slug": workspace_slug,
                    "plan_id": plan_id,
                    "price_id": price_id,
                    "account_state": summary,
                    "message": json.dumps({"i18n_key": "blink.efe9de30", "i18n_params": {}}, ensure_ascii=False),
                },
            }

        if action_id == "create_api_key":
            state = self._load_state(account, force_refresh=True)
            summary = dict(state.get("summary") or {})
            workspace_id = str(state.get("workspace_id") or summary.get("workspace_id") or "").strip()
            if not workspace_id:
                return {"ok": False, "error": json.dumps({"i18n_key": "blink.8594c2fa", "i18n_params": {}}, ensure_ascii=False)}

            workspace_slug = str(state.get("workspace_slug") or summary.get("workspace_slug") or "").strip()
            raw_name = str(params.get("name") or "").strip()
            key_name = raw_name or "开发 Key"

            client = BlinkRegister(proxy=self.config.proxy if self.config else None)
            client._log = self.log
            client._log_key_fn = self._log_key_fn
            payload = client.create_api_key(
                state.get("id_token", ""),
                workspace_id=workspace_id,
                name=key_name,
                session_token=str(state.get("session_token") or ""),
                workspace_slug=workspace_slug,
            )
            api_key = str(payload.get("key_value") or "").strip()
            if not api_key:
                return {"ok": False, "error": json.dumps({"i18n_key": "blink.4ae438e0", "i18n_params": {}}, ensure_ascii=False)}
            return {
                "ok": True,
                "data": {
                    "id": str(payload.get("id") or ""),
                    "name": str(payload.get("name") or key_name),
                    "key_prefix": str(payload.get("key_prefix") or ""),
                    "key_value": api_key,
                    "api_key": api_key,
                    "workspace_id": workspace_id,
                    "workspace_slug": workspace_slug,
                    "message": json.dumps({"i18n_key": "blink.58f150e3", "i18n_params": {}}, ensure_ascii=False),
                },
            }

        _raise_keyed(NotImplementedError, "blink.701d383a", action_id=action_id)
        # was: raise NotImplementedError(f"未知操作: {action_id}")
        # was: raise NotImplementedError(f"Unknown action: {action_id}")
