"""blink.new 协议邮箱注册 worker。 — blink.new protocol mailbox registration worker."""
from __future__ import annotations

import re
from typing import Callable, Optional

from platforms.blink._i18n_helpers import _emit_log_key, _raise_keyed
from platforms.blink.core import BLINK_BASE, BLINK_PRICE_IDS, BlinkRegister, summarize_blink_account_state


class BlinkProtocolMailboxWorker:
    def __init__(
        self,
        *,
        proxy: str | None = None,
        log_fn: Callable[[str], None] = print,
        log_key_fn: Optional[Callable[[str, dict], None]] = None,
    ):
        self.client = BlinkRegister(proxy=proxy)
        self.client._log = log_fn
        self.client._log_key_fn = log_key_fn
        self.log = log_fn
        self._log_key_fn = log_key_fn

    def log_key(self, key: str, **params) -> None:
        _emit_log_key(self.log, self._log_key_fn, key, **params)

    def run(
        self,
        *,
        email: str,
        link_callback: Optional[Callable[[], str]] = None,
    ) -> dict:
        """完整注册流程，返回持久化所需的 Blink 账号字段。 — Full registration flow; returns the Blink account fields needed for persistence."""
        # Step 1: 触发魔法链接邮件 — Step 1: trigger the magic link email
        ok = self.client.step1_send_magic_link(email)
        if not ok:
            _raise_keyed(RuntimeError, "blink.3e4d828d")
            # was: raise RuntimeError("发送魔法链接失败")
            # was: raise RuntimeError("Failed to send magic link")

        # Step 2: 等待邮件并提取 token — Step 2: wait for the email and extract the token
        if not link_callback:
            raise RuntimeError("link_callback is required")
        self.log_key("blink.2cdad0a9")
        # was: self.log("等待魔法链接...")
        # was: self.log("Waiting for magic link...")
        raw = link_callback()
        if not raw:
            _raise_keyed(RuntimeError, "blink.a36a12f6")
            # was: raise RuntimeError("获取魔法链接超时")
            # was: raise RuntimeError("Timed out waiting for magic link")

        # otp_callback 可能返回完整 URL 或纯 token — otp_callback may return either a full URL or a raw token
        token = self._extract_token(raw)
        self.log(f"magic_token={token[:16]}...")

        # Step 3: 兑换 customToken — Step 3: redeem the customToken
        auth_data = self.client.step2_redeem_magic_link(token, email)
        custom_token = auth_data["customToken"]
        user = auth_data["user"]
        workspace_slug = auth_data.get("workspaceSlug", "")

        # Step 4: Firebase 登录获取 idToken — Step 4: Firebase sign-in to get the idToken
        firebase_data = self.client.step3_firebase_signin(custom_token)
        id_token = firebase_data["idToken"]
        firebase_refresh_token = firebase_data["refreshToken"]

        # Step 5: 获取 Blink app token — Step 5: get the Blink app token
        app_token_data = self.client.step4_exchange_app_token(id_token, workspace_slug=workspace_slug)
        access_token = app_token_data.get("access_token", "")
        refresh_token = app_token_data.get("refresh_token", "")

        # Step 6: 获取 session cookie（浏览器登录用） — Step 6: get the session cookie (used for browser login)
        session_token = self.client.step5_get_session_token(id_token, workspace_slug=workspace_slug)

        # Step 7: 创建用户记录 — Step 7: create the user record
        user_info = self.client.step6_create_user(
            id_token,
            email,
            user_id=user.get("id", ""),
            workspace_slug=workspace_slug,
        )
        workspace_id = user_info.get("active_workspace_id", "")

        # Step 8: 注册后续（积分迁移 + 推荐码） — Step 8: post-registration steps (credit migration + referral code)
        post_register = self.client.step7_post_register(
            id_token,
            user_id=user.get("id", ""),
            workspace_id=workspace_id,
            workspace_slug=workspace_slug,
        )

        # Step 9: 拉取一次 session-data，保存归一化套餐/额度摘要
        # Step 9: fetch session-data once and save a normalized plan/quota summary
        session_data = self.client.fetch_session_data(
            id_token,
            session_token=session_token,
            workspace_slug=workspace_slug,
        )
        summary = summarize_blink_account_state(session_data, fallback_email=email)
        overview = summary["account_overview"]
        resolved_workspace_id = str(workspace_id or summary.get("workspace_id") or "").strip()
        cashier_url, checkout_session_id = self._maybe_create_checkout_link(
            id_token=id_token,
            session_token=session_token,
            workspace_id=resolved_workspace_id,
            workspace_slug=workspace_slug,
        )
        if cashier_url:
            overview["cashier_url"] = cashier_url
        if checkout_session_id:
            overview["checkout_session_id"] = checkout_session_id

        result = {
            "success": True,
            "email": email,
            "password": "",
            "user_id": user.get("id", ""),
            "id_token": id_token,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "firebase_refresh_token": firebase_refresh_token,
            "session_token": session_token,
            "workspace_slug": workspace_slug,
            "workspace_id": resolved_workspace_id,
            "customer_id": summary.get("customer_id", ""),
            "referral_code": post_register.get("referral_code", "") or summary.get("referral_code", ""),
            "cashier_url": cashier_url,
            "checkout_session_id": checkout_session_id,
            "account_overview": overview,
        }
        self.log_key(
            "blink.a6d714dc",
            email=email,
            workspace=workspace_slug,
            plan=overview.get("plan_name", "unknown"),
            billing_limit=overview.get("billing_period_credits_limit", 0),
        )
        # was: self.log( f"注册成功: {email} workspace={workspace_slug} " f"plan={overview.get('plan_name', 'unknown')} " f"billing_limit={overview.get('billing_period_credits_limit', 0)}" )
        # was: self.log( f"Registration successful: {email} workspace={workspace_slug} " f"plan={overview.get('plan_name', 'unknown')} " f"billing_limit={overview.get('billing_period_credits_limit', 0)}" )
        if cashier_url:
            self.log_key("blink.50241905", cashier_url=cashier_url)
            # was: self.log(f"自动生成支付链接: {cashier_url}")
            # was: self.log(f"Auto-generated payment link: {cashier_url}")
        return result

    def _maybe_create_checkout_link(
        self,
        *,
        id_token: str,
        session_token: str,
        workspace_id: str,
        workspace_slug: str,
    ) -> tuple[str, str]:
        price_id = str(BLINK_PRICE_IDS.get("pro") or "").strip()
        if not workspace_id:
            self.log_key("blink.972c89f1")
            # was: self.log("跳过自动生成支付链接: 缺少 workspace_id")
            # was: self.log("Skipping auto-generation of payment link: missing workspace_id")
            return "", ""
        if not price_id:
            self.log_key("blink.c7277b79")
            # was: self.log("跳过自动生成支付链接: 未配置 Blink Pro price_id")
            # was: self.log("Skipping auto-generation of payment link: Blink Pro price_id not configured")
            return "", ""

        cancel_url = (
            f"{BLINK_BASE}/{workspace_slug}?showPricing=true"
            if workspace_slug
            else f"{BLINK_BASE}/?showPricing=true"
        )
        try:
            checkout = self.client.create_checkout(
                id_token,
                price_id=price_id,
                plan_id="pro",
                workspace_id=workspace_id,
                cancel_url=cancel_url,
                session_token=session_token,
                workspace_slug=workspace_slug,
            )
        except Exception as exc:
            self.log_key("blink.5e8b4b62", exc=str(exc))
            # was: self.log(f"自动生成支付链接失败，忽略并继续: {exc}")
            # was: self.log(f"Failed to auto-generate payment link, ignoring and continuing: {exc}")
            return "", ""

        cashier_url = str(checkout.get("url") or "").strip()
        checkout_session_id = str(checkout.get("sessionId") or "").strip()
        return cashier_url, checkout_session_id

    @staticmethod
    def _extract_token(raw: str) -> str:
        """从完整 URL 或原始字符串中提取 magic_token。 — Extract the magic_token from a full URL or a raw string."""
        m = re.search(r'magic_token=([a-f0-9]{64})', raw)
        if m:
            return m.group(1)
        # 若直接是 64 位 hex token — If it's already a raw 64-char hex token
        raw = raw.strip()
        if re.fullmatch(r'[a-f0-9]{64}', raw):
            return raw
        _raise_keyed(RuntimeError, "blink.e6b4e29a", raw=raw[:200])
        # was: raise RuntimeError(f"无法从邮件内容中提取 magic_token: {raw[:200]}")
        # was: raise RuntimeError(f"Could not extract magic_token from the email content: {raw[:200]}")
