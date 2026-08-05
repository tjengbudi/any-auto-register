"""Kiro 协议邮箱注册 worker。 — Kiro protocol mailbox registration worker."""
from __future__ import annotations

from typing import Callable

from platforms.kiro._i18n_helpers import _raise_keyed
from platforms.kiro.core import KiroRegister, _pwd, wait_for_otp


class KiroProtocolMailboxWorker:
    def __init__(
        self,
        *,
        proxy: str | None = None,
        tag: str = "KIRO",
        log_fn: Callable[[str], None] = print,
        log_key_fn: Callable[[str, dict], None] | None = None,
    ):
        self.client = KiroRegister(proxy=proxy, tag=tag)
        self.client.log = lambda msg: log_fn(msg)
        self.client._log_key_fn = log_key_fn

    def run(
        self,
        *,
        email: str,
        password: str | None = None,
        name: str = "Kiro User",
        mail_token: str | None = None,
        otp_timeout: int = 120,
        otp_callback=None,
    ) -> dict:
        use_password = password or _pwd()
        if password:
            self.client.log_key("kiro.1aba49b7", use_password=use_password)
            # was: self.client.log(f"  使用传入密码: {use_password}") —
            # was: self.client.log(f"  Using the provided password: {use_password}")
        else:
            self.client.log_key("kiro.78694aa2", use_password=use_password)
            # was: self.client.log(f"  自动生成密码: {use_password}") —
            # was: self.client.log(f"  Auto-generated password: {use_password}")
        self.client.log_key("kiro.63816c08", email=email)
        # was: self.client.log(f"========== 开始注册: {email} ==========") —
        # was: self.client.log(f"========== Starting registration: {email} ==========")

        redir = self.client.step1_kiro_init()
        if not redir:
            raise RuntimeError("InitiateLogin failed")
        if not self.client.step2_get_wsh(redir):
            _raise_keyed(RuntimeError, "kiro.9d1b5599")
            # was: raise RuntimeError("获取wsh失败") — was: raise RuntimeError("Failed to get wsh")
        if not self.client.step3_signin_flow(email):
            _raise_keyed(RuntimeError, "kiro.7c3a828f")
            # was: raise RuntimeError("signin flow失败") — was: raise RuntimeError("signin flow failed")
        if not self.client.step4_signup_flow(email):
            _raise_keyed(RuntimeError, "kiro.f9d7de5d")
            # was: raise RuntimeError("signup flow失败") — was: raise RuntimeError("signup flow failed")
        if not self.client.profile_wf_id:
            _raise_keyed(RuntimeError, "kiro.07d3ea15")
            # was: raise RuntimeError("未获取到workflowID") — was: raise RuntimeError("Failed to obtain workflowID")
        tes = self.client.step5_get_tes_token()
        if not tes:
            self.client.log_key("kiro.88856468")
            # was: self.client.log("  ⚠️ TES token获取失败, 继续...") —
            # was: self.client.log("  ⚠️ Failed to get TES token, continuing...")
        if not self.client.step6_profile_load():
            _raise_keyed(RuntimeError, "kiro.cb74e694")
            # was: raise RuntimeError("profile start失败") — was: raise RuntimeError("profile start failed")
        if self.client.step7_send_otp(email) is None:
            _raise_keyed(RuntimeError, "kiro.d9c07bc6")
            # was: raise RuntimeError("send OTP失败") — was: raise RuntimeError("send OTP failed")

        if otp_callback:
            self.client.log_key("kiro.b5961439")
            # was: self.client.log("  自动获取验证码...") — was: self.client.log("  Auto-fetching verification code...")
            otp = otp_callback()
        elif mail_token:
            self.client.log_key("kiro.b5961439")
            # was: self.client.log("  自动获取验证码...") — was: self.client.log("  Auto-fetching verification code...")
            otp = wait_for_otp(mail_token, timeout=otp_timeout, tag=self.client.tag)
        else:
            otp = input(f"[{self.client.tag}] 请输入验证码: ").strip()
        if not otp:
            _raise_keyed(RuntimeError, "kiro.13939cce")
            # was: raise RuntimeError("未获取到验证码") — was: raise RuntimeError("Failed to obtain verification code")

        identity = self.client.step8_create_identity(otp, email, name)
        if not identity:
            _raise_keyed(RuntimeError, "kiro.e8d8079c")
            # was: raise RuntimeError("create-identity失败") — was: raise RuntimeError("create-identity failed")
        reg_code = identity["registrationCode"]
        sign_in_state = identity["signInState"]

        signup_registration = self.client.step9_signup_registration(reg_code, sign_in_state)
        if not signup_registration:
            _raise_keyed(RuntimeError, "kiro.9b0de3fa")
            # was: raise RuntimeError("signup registration失败") — was: raise RuntimeError("signup registration failed")
        password_state = self.client.step10_set_password(use_password, email, signup_registration)
        if not password_state:
            _raise_keyed(RuntimeError, "kiro.bda26a4c")
            # was: raise RuntimeError("设置密码失败") — was: raise RuntimeError("Failed to set password")

        login_result = self.client.step11_final_login(email, password_state)
        if not login_result:
            self.client.log_key("kiro.ddccb8d1")
            # was: self.client.log("  ⚠️ 最终登录步骤失败, 但账号可能已创建成功") —
            # was: self.client.log("  ⚠️ Final login step failed, but the account may already have been created")

        tokens = self.client.step12_get_tokens()
        if not tokens:
            self.client.log_key("kiro.567e0d2c")
            # was: self.client.log("🎉 注册完成! (但 token 获取失败, 账号可用)") —
            # was: self.client.log("🎉 Registration complete! (token fetch failed, account still usable)")
            return {"email": email, "password": use_password, "name": name}

        bearer_token = tokens["sessionToken"]
        device_tokens = self.client.step12f_device_auth(bearer_token)
        if device_tokens:
            self.client.log_key("kiro.41fb5601")
            # was: self.client.log("🎉 注册完成! (含 accessToken + sessionToken + refreshToken)") —
            # was: self.client.log("🎉 Registration complete! (includes accessToken + sessionToken + refreshToken)")
            return {
                "email": email,
                "password": use_password,
                "name": name,
                "accessToken": tokens["accessToken"],
                "sessionToken": tokens["sessionToken"],
                "clientId": device_tokens["clientId"],
                "clientSecret": device_tokens["clientSecret"],
                "refreshToken": device_tokens["refreshToken"],
            }

        self.client.log_key("kiro.a0a0e097")
        # was: self.client.log("🎉 注册完成! (含 accessToken + sessionToken, 但 refreshToken 获取失败)") —
        # was: self.client.log("🎉 Registration complete! (includes accessToken + sessionToken, but refreshToken fetch failed)")
        return {
            "email": email,
            "password": use_password,
            "name": name,
            "accessToken": tokens["accessToken"],
            "sessionToken": tokens["sessionToken"],
        }
