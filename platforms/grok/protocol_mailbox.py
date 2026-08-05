"""Grok 协议邮箱注册 worker。"""
from __future__ import annotations

from typing import Callable, Optional

from platforms.grok._i18n_helpers import _emit_log_key, _raise_keyed
from platforms.grok.core import GrokRegister, _rand_name, _rand_password


class GrokProtocolMailboxWorker:
    def __init__(
        self,
        *,
        captcha_solver=None,
        proxy: str | None = None,
        log_fn: Callable[[str], None] = print,
        log_key_fn: Optional[Callable[[str, dict], None]] = None,
    ):
        self.client = GrokRegister(captcha_solver=captcha_solver, proxy=proxy, log_fn=log_fn, log_key_fn=log_key_fn)
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
    ) -> dict:
        use_password = password or _rand_password()
        given_name = _rand_name()
        family_name = _rand_name()

        self.client.step1_send_otp(email)
        code = otp_callback() if otp_callback else input("验证码: ")
        if not code:
            _raise_keyed(RuntimeError, "grok.13939cce")
            # was: raise RuntimeError("未获取到验证码")

        self.client.step2_verify_otp(email, code)
        signup_body = self.client.step3_signup(email, use_password, code, given_name, family_name)
        self.client.step4_set_cookies(signup_body)

        cookies = {cookie.name: cookie.value for cookie in self.client.s.cookies}
        sso = cookies.get("sso", "")
        if sso:
            self.log(f"  ✅ sso={sso[:40]}...")
        else:
            self.log_key("grok.a991998c")
            # was: self.log("  ⚠️ 未获取到 sso cookie")

        return {
            "email": email,
            "password": use_password,
            "given_name": given_name,
            "family_name": family_name,
            "sso": sso,
            "sso_rw": cookies.get("sso-rw", ""),
        }
