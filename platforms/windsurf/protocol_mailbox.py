"""Windsurf 协议邮箱注册 worker。"""
from __future__ import annotations

import re
from typing import Callable, Optional

from platforms.windsurf._i18n_helpers import _emit_log_key, _raise_keyed
from platforms.windsurf.core import WindsurfClient


class WindsurfProtocolMailboxWorker:
    def __init__(
        self,
        *,
        proxy: str | None = None,
        log_fn: Callable[[str], None] = print,
        log_key_fn: Optional[Callable[[str, dict], None]] = None,
    ):
        self.client = WindsurfClient(proxy=proxy, log_fn=log_fn, log_key_fn=log_key_fn)
        self.log = log_fn
        self._log_key_fn = log_key_fn

    def log_key(self, key: str, **params) -> None:
        _emit_log_key(self.log, self._log_key_fn, key, **params)

    def run(
        self,
        *,
        email: str,
        password: str,
        name: str,
        otp_callback: Optional[Callable[[], str]] = None,
    ) -> dict:
        if not otp_callback:
            raise RuntimeError("otp_callback is required")

        try:
            self.client.fetch_connections(email)
            self.client.check_user_login_method(email)
        except Exception as exc:
            self.log_key("windsurf.98c50992", exc=str(exc))
            # was: self.log(f"Windsurf 注册预检失败，继续尝试邮箱验证码流程: {exc}")

        verification_token = self.client.start_email_signup(email)
        raw_code = otp_callback()
        code = self._extract_code(raw_code)
        self.log_key("windsurf.3dfa2d66", code=code)
        # was: self.log(f"获取 Windsurf 验证码: {code}")

        complete = self.client.complete_email_signup(
            email=email,
            verification_token=verification_token,
            code=code,
            password=password,
            name=name,
        )
        auth_token = str(complete.get("token") or "")
        auth = self.client.post_auth(auth_token)
        session_token = auth["session_token"]
        account_id = auth.get("account_id", "")
        org_id = auth.get("org_id", "")
        state = self.client.load_account_state(
            session_token=session_token,
            account_id=account_id,
            org_id=org_id,
            fallback_email=email,
        )
        summary = dict(state.get("summary") or {})
        overview = dict(summary.get("account_overview") or {})
        self.log_key(
            "windsurf.6683dc17",
            email=email,
            plan_name=str(overview.get("plan_name", "unknown")),
            remaining_credits=str(overview.get("remaining_credits", "-")),
        )
        # was: self.log(f"Windsurf 注册成功: {email} " f"plan={overview.get('plan_name', 'unknown')} " f"quota={overview.get('remaining_credits', '-')}")
        return {
            "email": str(complete.get("email") or email),
            "password": password,
            "name": name,
            "user_id": str(complete.get("user_id") or (overview.get("remote_user") or {}).get("user_id") or ""),
            "auth_token": auth_token,
            "session_token": session_token,
            "account_id": account_id,
            "org_id": org_id,
            "account_overview": overview,
            "state_summary": summary,
        }

    @staticmethod
    def _extract_code(raw: str) -> str:
        text = str(raw or "")
        match = re.search(r"\b(\d{6})\b", text)
        if match:
            return match.group(1)
        _raise_keyed(RuntimeError, "windsurf.fc3d5c97", snippet=text[:200])
        # was: raise RuntimeError(f"无法从邮件内容中提取 Windsurf 6 位验证码: {text[:200]}")

