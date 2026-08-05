"""Tavily 协议邮箱注册 worker。"""
from __future__ import annotations

from typing import Callable, Optional

from platforms.tavily._i18n_helpers import _emit_log_key, _raise_keyed
from platforms.tavily.core import TavilyRegister


class TavilyProtocolMailboxWorker:
    def __init__(
        self,
        *,
        executor,
        captcha,
        log_fn: Callable[[str], None] = print,
        log_key_fn: Optional[Callable[[str, dict], None]] = None,
    ):
        self.client = TavilyRegister(executor=executor, captcha=captcha, log_fn=log_fn, log_key_fn=log_key_fn)
        self.log = log_fn
        self._log_key_fn = log_key_fn

    def log_key(self, key: str, **params) -> None:
        _emit_log_key(self.log, self._log_key_fn, key, **params)

    def run(
        self,
        *,
        email: str,
        password: str,
        otp_callback: Optional[Callable[[], str]] = None,
    ) -> dict:
        state = self.client.step1_authorize()
        captcha_token = self.client.step2_solve_captcha()
        challenge_state = self.client.step3_submit_email(email, state, captcha_token)
        otp = otp_callback() if otp_callback else input("OTP: ")
        if not otp:
            _raise_keyed(RuntimeError, "tavily.13939cce")
            # was: raise RuntimeError("未获取到验证码") — was: raise RuntimeError("Failed to obtain the verification code")
        self.log_key("tavily.8f3b2133", otp=otp)
        # was: self.log(f"验证码: {otp}") — was: self.log(f"Verification code: {otp}")
        pw_state = self.client.step4_submit_otp(otp, challenge_state)
        resume_state = self.client.step5_submit_password(email, password, pw_state)
        api_key = self.client.step6_resume_and_get_key(resume_state)
        if api_key:
            self.log(f"API Key: {api_key[:20]}...")
        else:
            self.log_key("tavily.bdfd8fe2")
            # was: self.log(f"API Key: {api_key[:20]}..." if api_key else "未获取到 API Key")
            # was: self.log(f"API Key: {api_key[:20]}..." if api_key else "API Key not obtained")
        return {"email": email, "password": password, "api_key": api_key}
