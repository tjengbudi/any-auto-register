"""Cerebras Cloud 注册协议核心实现 (Stytch Email OTP 流程)。

流程:
  1. POST Stytch OTP send → 发送验证码到邮箱
  2. POST Stytch OTP authenticate → 验证 OTP，获取 session
  3. GET /api/api-keys → 获取已有 API Key
  4. POST /api/api-keys → 创建新 API Key（如果没有）
"""
from __future__ import annotations

import json
import re
from typing import Callable, Optional

from platforms.cerebras._i18n_helpers import _emit_log_key, _raise_keyed

CLOUD_BASE = "https://cloud.cerebras.ai"

# Stytch public token (embedded in the Cerebras frontend JS)
STYTCH_PUBLIC_TOKEN = "public-token-live-149c2fe0-f8dc-4569-8e3e-e04161a8475e"
STYTCH_ENV = "https://web.stytch.com"


class CerebrasRegister:
    """Cerebras Cloud 协议注册。"""

    def __init__(
        self,
        *,
        executor,
        log_fn: Callable[[str], None] = print,
        log_key_fn: Optional[Callable[[str, dict], None]] = None,
    ):
        self.ex = executor
        self.log = log_fn
        self._log_key_fn = log_key_fn
        self._session_token = ""
        self._session_jwt = ""

    def log_key(self, key: str, **params) -> None:
        _emit_log_key(self.log, self._log_key_fn, key, **params)

    def step1_send_otp(self, email: str) -> str:
        """发送 OTP 到邮箱，返回 method_id。"""
        self.log_key("cerebras.4959d22c", email=email)
        # was: self.log(f"发送验证码到 {email}...")
        r = self.ex.post(
            f"{STYTCH_ENV}/sdk/v1/otps/email/login_or_create",
            headers={
                "content-type": "application/json",
                "authorization": f"Basic {STYTCH_PUBLIC_TOKEN}",
                "x-sdk-client": "eyJldmVudF9pZCI6ImV2ZW50LWlkLTEiLCJhcHBfc2Vzc2lvbl9pZCI6IiIsInBlcnNpc3RlbnRfaWQiOiIiLCJjbGllbnRfc2RrX3R5cGUiOiJqYXZhc2NyaXB0IiwiY2xpZW50X3Nka192ZXJzaW9uIjoiNS4xLjAifQ==",
            },
            data=json.dumps({
                "email": email,
                "login_expiration_minutes": 30,
                "signup_expiration_minutes": 30,
            }),
        )
        try:
            data = r.json()
        except Exception:
            _raise_keyed(RuntimeError, "cerebras.80c84930", status_code=r.status_code)
            # was: raise RuntimeError(f"Stytch OTP 发送失败: HTTP {r.status_code}")

        if r.status_code != 200:
            error = data.get("error_message", "") or data.get("error_type", "")
            _raise_keyed(RuntimeError, "cerebras.df22fccf", error=error)
            # was: raise RuntimeError(f"Stytch OTP 发送失败: {error}")

        method_id = data.get("email_id", "")
        self.log_key("cerebras.c53d6313", method_id=method_id[:20])
        # was: self.log(f"验证码已发送 (method_id={method_id[:20]}...)")
        return method_id

    def step2_verify_otp(self, email: str, code: str, method_id: str) -> dict:
        """验证 OTP，返回 session 信息。"""
        self.log_key("cerebras.3508be33")
        # was: self.log("验证 OTP...")
        r = self.ex.post(
            f"{STYTCH_ENV}/sdk/v1/otps/authenticate",
            headers={
                "content-type": "application/json",
                "authorization": f"Basic {STYTCH_PUBLIC_TOKEN}",
            },
            data=json.dumps({
                "code": code,
                "method_id": method_id,
                "session_duration_minutes": 60 * 24 * 7,
            }),
        )
        try:
            data = r.json()
        except Exception:
            _raise_keyed(RuntimeError, "cerebras.6e9a60f4", status_code=r.status_code)
            # was: raise RuntimeError(f"OTP 验证失败: HTTP {r.status_code}")

        if r.status_code != 200:
            error = data.get("error_message", "") or data.get("error_type", "")
            _raise_keyed(RuntimeError, "cerebras.7f445322", error=error)
            # was: raise RuntimeError(f"OTP 验证失败: {error}")

        self._session_token = data.get("session_token", "")
        self._session_jwt = data.get("session_jwt", "")
        user = data.get("user", {})
        user_id = user.get("user_id", "")
        self.log_key("cerebras.63da20cd", user_id=user_id)
        # was: self.log(f"OTP 验证成功 (user_id={user_id})")
        return {
            "session_token": self._session_token,
            "session_jwt": self._session_jwt,
            "user_id": user_id,
            "email": email,
        }

    def step3_get_or_create_api_key(self) -> str:
        """获取或创建 API Key。"""
        if not self._session_jwt:
            _raise_keyed(RuntimeError, "cerebras.a56b812f")
            # was: raise RuntimeError("未登录，无法获取 API Key")

        headers = {
            "authorization": f"Bearer {self._session_jwt}",
            "accept": "application/json",
            "content-type": "application/json",
        }

        # Try to get existing keys
        self.log_key("cerebras.f4bc415b")
        # was: self.log("获取 API Key...")
        r = self.ex.get(f"{CLOUD_BASE}/api/api-keys", headers=headers)
        try:
            data = r.json()
            if isinstance(data, list) and data:
                key = data[0].get("key", "") or data[0].get("api_key", "")
                if key:
                    self.log_key("cerebras.dd2cf36c")
                    # was: self.log(f"使用已有 API Key")
                    return key
            if isinstance(data, dict):
                keys = data.get("keys", []) or data.get("api_keys", []) or data.get("data", [])
                if isinstance(keys, list) and keys:
                    key = keys[0].get("key", "") or keys[0].get("api_key", "")
                    if key:
                        self.log_key("cerebras.dd2cf36c")
                        # was: self.log(f"使用已有 API Key")
                        return key
        except Exception:
            pass

        # Create a new key
        self.log_key("cerebras.95f1bde6")
        # was: self.log("创建新 API Key...")
        r = self.ex.post(
            f"{CLOUD_BASE}/api/api-keys",
            headers=headers,
            data=json.dumps({"name": "auto-register"}),
        )
        try:
            data = r.json()
            key = (
                data.get("key", "")
                or data.get("api_key", "")
                or data.get("secret", "")
                or (data.get("data", {}) or {}).get("key", "")
            )
            if key:
                self.log_key("cerebras.c0088f3b")
                # was: self.log(f"API Key 创建成功")
                return key
        except Exception:
            pass

        _raise_keyed(RuntimeError, "cerebras.48a7a9d6", status_code=r.status_code)
        # was: raise RuntimeError(f"创建 API Key 失败: HTTP {r.status_code}")
