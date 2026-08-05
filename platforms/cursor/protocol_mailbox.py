"""Cursor 协议邮箱注册 worker。 — Cursor protocol mailbox registration worker."""
from __future__ import annotations

from typing import Callable, Optional

from platforms.cursor._i18n_helpers import _emit_log_key, _raise_keyed
from platforms.cursor.core import CursorRegister, _rand_password


class CursorProtocolMailboxWorker:
    def __init__(
        self,
        *,
        proxy: str | None = None,
        log_fn: Callable[[str], None] = print,
        log_key_fn: Optional[Callable[[str, dict], None]] = None,
    ):
        self.client = CursorRegister(proxy=proxy, log_fn=log_fn, log_key_fn=log_key_fn)
        self.log = log_fn
        self._log_key_fn = log_key_fn

    def log_key(self, key: str, **params) -> None:
        _emit_log_key(self.log, self._log_key_fn, key, **params)

    def run(
        self,
        *,
        email: str,
        password: str | None = None,
        otp_callback: Optional[Callable[[], str]] = None,
        captcha_solver=None,
    ) -> dict:
        use_password = password or _rand_password()
        self.log_key("cursor.1a4231de", email=email)
        # was: self.log(f"邮箱: {email}") — was: self.log(f"Email: {email}")
        self.log_key("cursor.29d78d50")
        # was: self.log("Step1: 获取 session...") — was: self.log("Step1: Get session...")
        state_encoded, _ = self.client.step1_get_session()
        self.log_key("cursor.1472fdb5")
        # was: self.log("Step2: 提交邮箱...") — was: self.log("Step2: Submit email...")
        self.client.step2_submit_email(email, state_encoded)
        self.log_key("cursor.03232ddc")
        # was: self.log("Step3: 提交密码 + Turnstile...") — was: self.log("Step3: Submit password + Turnstile...")
        self.client.step3_submit_password(use_password, email, state_encoded, captcha_solver)
        self.log_key("cursor.935efe8a")
        # was: self.log("等待 OTP 邮件...") — was: self.log("Waiting for OTP email...")
        otp = otp_callback() if otp_callback else input("OTP: ")
        if not otp:
            _raise_keyed(RuntimeError, "cursor.13939cce")
            # was: raise RuntimeError("未获取到验证码") — was: raise RuntimeError("OTP code not received")
        self.log_key("cursor.8f3b2133", otp=otp)
        # was: self.log(f"验证码: {otp}") — was: self.log(f"OTP code: {otp}")
        self.log_key("cursor.61f9ee7d")
        # was: self.log("Step4: 提交 OTP...") — was: self.log("Step4: Submit OTP...")
        auth_code = self.client.step4_submit_otp(otp, email, state_encoded)
        self.log_key("cursor.003bd597")
        # was: self.log("Step5: 获取 Token...") — was: self.log("Step5: Get token...")
        token = self.client.step5_get_token(auth_code, state_encoded)
        return {"email": email, "password": use_password, "token": token}
