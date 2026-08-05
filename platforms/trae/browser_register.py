"""Trae.ai 浏览器注册流程（Camoufox）。

注册流程：
  1. 打开 trae.ai/sign-up
  2. 填写邮箱 → 点击 "Send Code"
  3. 等待邮箱验证码（6位）→ 填写
  4. 填写密码 → 点击 "Sign Up"
  5. 等待跳转到 trae.ai 主页
  6. 从 Cookie / localStorage 提取 token

注意：Trae 使用 ByteDance Passport 系统，API 请求带有 X-Bogus/X-Gnarly 签名头，
浏览器模式自动生成这些头，无需额外处理。

Trae.ai browser registration flow (Camoufox).

Registration flow:
  1. Open trae.ai/sign-up
  2. Fill in the email → click "Send Code"
  3. Wait for the email verification code (6 digits) → enter it
  4. Fill in the password → click "Sign Up"
  5. Wait for the redirect to the trae.ai homepage
  6. Extract the token from Cookie / localStorage

Note: Trae uses the ByteDance Passport system; API requests carry X-Bogus/X-Gnarly
signature headers, which browser mode generates automatically with no extra
handling needed.
"""
import random
import string
import time
from typing import Callable, Optional
from urllib.parse import urlparse

from camoufox.sync_api import Camoufox

from platforms.trae._i18n_helpers import _emit_log_key, _raise_keyed

TRAE_URL = "https://www.trae.ai"
TRAE_PASSPORT_DOMAIN = "ug-normal.trae.ai"


def _build_proxy_config(proxy: Optional[str]) -> Optional[dict]:
    if not proxy:
        return None
    parsed = urlparse(proxy)
    if not parsed.scheme or not parsed.hostname or not parsed.port:
        return {"server": proxy}
    config = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
    if parsed.username:
        config["username"] = parsed.username
    if parsed.password:
        config["password"] = parsed.password
    return config


def _wait_for_url(page, substring: str, timeout: int = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if substring in page.url:
            return True
        time.sleep(1)
    return False


def _click_element(page, *selectors, timeout: int = 10) -> bool:
    """按选择器列表尝试点击第一个可见元素。
    Try clicking the first visible element from a selector list."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    return False


def _get_trae_cloudide_token(page, log_fn=print, *, log_key: Optional[Callable[[str, dict], None]] = None) -> tuple:
    """注册完成后，用浏览器 session 调用 Trae API 获取 Cloud-IDE JWT token。

    流程同 core.py：
      step4: POST /cloudide/api/v3/trae/Login    （建立 IDE session）
      step5: POST /cloudide/api/v3/common/GetUserToken  →  Result.Token = Cloud-IDE JWT
      step6: POST /cloudide/api/v3/trae/CheckLogin  →  Region / UserId 等

    After registration completes, use the browser session to call the Trae API
    and obtain the Cloud-IDE JWT token.

    Same flow as core.py:
      step4: POST /cloudide/api/v3/trae/Login    (establishes the IDE session)
      step5: POST /cloudide/api/v3/common/GetUserToken  →  Result.Token = Cloud-IDE JWT
      step6: POST /cloudide/api/v3/trae/CheckLogin  →  Region / UserId, etc.
    """
    BASE_URL = "https://ug-normal.trae.ai"
    API_SG = "https://api-sg-central.trae.ai"

    token = ""
    user_id = ""
    region = ""

    # step4: Trae Login（建立 IDE session） — step4: Trae Login (establishes the IDE session)
    try:
        _emit_log_key(log_fn, log_key, "trae.8540e9d6")
        # was: log_fn("调用 Trae Login API...")
        # was: log_fn("Calling Trae Login API...")
        page.evaluate(f"""
        async () => {{
            await fetch("{BASE_URL}/cloudide/api/v3/trae/Login?type=email", {{
                method: "POST",
                headers: {{"content-type": "application/json"}},
                credentials: "include",
                body: JSON.stringify({{
                    "UtmSource": "", "UtmMedium": "", "UtmCampaign": "",
                    "UtmTerm": "", "UtmContent": "", "BDVID": "",
                    "LoginChannel": "ide_platform"
                }})
            }});
        }}
        """)
        time.sleep(1)
    except Exception as e:
        _emit_log_key(log_fn, log_key, "trae.840a8f81", exc=str(e))
        # was: log_fn(f"⚠️ Trae Login 失败: {e}")
        # was: log_fn(f"⚠️ Trae Login failed: {e}")

    # step5: GetUserToken → Cloud-IDE JWT
    try:
        _emit_log_key(log_fn, log_key, "trae.25ab66d1")
        # was: log_fn("获取 Cloud-IDE JWT token...")
        # was: log_fn("Fetching Cloud-IDE JWT token...")
        result = page.evaluate(f"""
        async () => {{
            const r = await fetch("{API_SG}/cloudide/api/v3/common/GetUserToken", {{
                method: "POST",
                headers: {{"content-type": "application/json"}},
                credentials: "include",
                body: JSON.stringify({{}})
            }});
            return await r.json();
        }}
        """)
        token = (result or {}).get("Result", {}).get("Token", "") or ""
        if token:
            _emit_log_key(log_fn, log_key, "trae.ea48c704", token_len=len(token))
            # was: log_fn(f"✅ 获取到 Cloud-IDE JWT (长度={len(token)})")
            # was: log_fn(f"✅ Obtained Cloud-IDE JWT (length={len(token)})")
    except Exception as e:
        _emit_log_key(log_fn, log_key, "trae.51b21c4b", exc=str(e))
        # was: log_fn(f"⚠️ GetUserToken 失败: {e}")
        # was: log_fn(f"⚠️ GetUserToken failed: {e}")

    # step6: CheckLogin → userId / Region
    if token:
        try:
            result2 = page.evaluate(f"""
            async () => {{
                const r = await fetch("{BASE_URL}/cloudide/api/v3/trae/CheckLogin", {{
                    method: "POST",
                    headers: {{
                        "content-type": "application/json",
                        "Authorization": "Cloud-IDE-JWT {token}"
                    }},
                    credentials: "include",
                    body: JSON.stringify({{"GetAIPayHost": true, "GetNickNameEditStatus": true}})
                }});
                return await r.json();
            }}
            """)
            res = (result2 or {}).get("Result", {})
            user_id = str(res.get("UserId", "") or res.get("userId", ""))
            region = res.get("Region", "")
        except Exception as e:
            _emit_log_key(log_fn, log_key, "trae.d3842706", exc=str(e))
            # was: log_fn(f"⚠️ CheckLogin 失败: {e}")
            # was: log_fn(f"⚠️ CheckLogin failed: {e}")

    # 兜底：从 Cookie 提取 user_id — Fallback: extract user_id from the Cookie
    if not user_id:
        try:
            cookies = {c["name"]: c["value"] for c in page.context.cookies()}
            user_id = cookies.get("user_id", cookies.get("userId", ""))
        except Exception:
            pass

    # 终极兜底：从 JWT payload 解出 id — Last-resort fallback: decode the id from the JWT payload
    if not user_id and token:
        try:
            import base64, json as _json
            payload = token.split(".")[1]
            payload += "==" * (4 - len(payload) % 4)
            data = _json.loads(base64.urlsafe_b64decode(payload))
            user_id = str(data.get("data", {}).get("id", ""))
        except Exception:
            pass

    return token, user_id, region


class TraeBrowserRegister:
    def __init__(
        self,
        *,
        headless: bool = True,
        proxy: Optional[str] = None,
        otp_callback: Optional[Callable[[], str]] = None,
        log_fn: Callable[[str], None] = print,
        log_key_fn: Optional[Callable[[str, dict], None]] = None,
    ):
        self.headless = headless
        self.proxy = proxy
        self.otp_callback = otp_callback
        self.log = log_fn
        self._log_key_fn = log_key_fn

    def log_key(self, key: str, **params) -> None:
        _emit_log_key(self.log, self._log_key_fn, key, **params)

    def run(self, email: str, password: str) -> dict:
        if not self.otp_callback:
            _raise_keyed(RuntimeError, "trae.bfa130fd")
            # was: raise RuntimeError("Trae 注册需要邮箱验证码但未提供 otp_callback")
            # was: raise RuntimeError("Trae registration needs an email code but no otp_callback provided")

        # 生成密码（如果未提供） — Generate a password (if none was provided)
        if not password:
            password = (
                ''.join(random.choices(string.ascii_uppercase, k=2))
                + ''.join(random.choices(string.digits, k=3))
                + ''.join(random.choices(string.ascii_lowercase, k=5))
                + '!'
            )

        proxy = _build_proxy_config(self.proxy)
        launch_opts = {"headless": self.headless}
        if proxy:
            launch_opts["proxy"] = proxy

        with Camoufox(**launch_opts) as browser:
            page = browser.new_page()

            # 1. 打开注册页 — 1. Open the sign-up page
            self.log_key("trae.7ac7c313")
            # was: self.log("打开 Trae 注册页")
            # was: self.log("Opening Trae sign-up page")
            page.goto(f"{TRAE_URL}/sign-up", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            # 2. 填写邮箱 — 2. Fill in the email
            self.log_key("trae.eaa92c19", email=email)
            # was: self.log(f"填写邮箱: {email}")
            # was: self.log(f"Filling in email: {email}")
            email_selectors = [
                'input[placeholder="Email"]',
                'input[type="email"]',
                'input[name="email"]',
                'input[placeholder*="email" i]',
            ]
            email_el = None
            deadline_email = time.time() + 20
            while time.time() < deadline_email:
                for sel in email_selectors:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            email_el = el
                            break
                    except Exception:
                        pass
                if email_el:
                    break
                time.sleep(0.5)

            if not email_el:
                _raise_keyed(RuntimeError, "trae.aeaae40c", page_url=page.url)
                # was: raise RuntimeError(f"未找到邮箱输入框: {page.url}")
                # was: raise RuntimeError(f"Email input field not found: {page.url}")

            email_el.click()
            email_el.fill(email)
            time.sleep(0.5)

            # 3. 点击 "Send Code" 按钮 — 3. Click the "Send Code" button
            self.log_key("trae.8a956af4")
            # was: self.log("发送验证码...")
            # was: self.log("Sending verification code...")
            # 使用 JS 找到包含精确文本的最小 leaf 元素并点击
            # Use JS to find and click the smallest leaf element with the exact text
            send_clicked = False
            deadline_send = time.time() + 15
            while time.time() < deadline_send and not send_clicked:
                try:
                    # Playwright text= 选择器比 CSS has-text 更精确
                    # Playwright's text= selector is more precise than CSS has-text
                    el = page.locator('text="Send Code"').last
                    if el.is_visible():
                        el.click()
                        send_clicked = True
                        self.log_key("trae.0820a0f5")
                        # was: self.log("已点击 Send Code")
                        # was: self.log("Clicked Send Code")
                        break
                except Exception:
                    pass
                # 备用：JS 遍历找到精确包含 Send Code 文字的元素
                # Fallback: iterate via JS to find the element containing exactly "Send Code"
                if not send_clicked:
                    try:
                        page.evaluate("""
                        () => {
                            const all = document.querySelectorAll('*');
                            for (const el of all) {
                                if (el.children.length === 0 && el.textContent.trim() === 'Send Code') {
                                    el.click();
                                    return;
                                }
                            }
                        }
                        """)
                        send_clicked = True
                        self.log_key("trae.a036f186")
                        # was: self.log("已点击 Send Code (JS)")
                        # was: self.log("Clicked Send Code (JS)")
                    except Exception:
                        pass
                time.sleep(1)

            if not send_clicked:
                self.log_key("trae.747ccfbe")
                # was: self.log("⚠️ 未能点击 Send Code，尝试 Tab+Enter")
                # was: self.log("⚠️ Failed to click Send Code, trying Tab+Enter")
                page.keyboard.press("Tab")
                time.sleep(0.3)
                page.keyboard.press("Enter")

            time.sleep(2)

            # 4. 等待 OTP 输入框 — 4. Wait for the OTP input field
            self.log_key("trae.9f1ca065")
            # was: self.log("等待邮箱验证码...")
            # was: self.log("Waiting for email verification code...")
            otp_selectors = [
                'input[placeholder="Verification code"]',
                'input[placeholder*="verification" i]',
                'input[placeholder*="code" i]',
                'input[name="code"]',
                'input[autocomplete="one-time-code"]',
                'input[inputmode="numeric"]',
            ]
            otp_el = None
            deadline_otp = time.time() + 60
            while time.time() < deadline_otp:
                for sel in otp_selectors:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            otp_el = el
                            break
                    except Exception:
                        pass
                if otp_el:
                    break
                time.sleep(1)

            if not otp_el:
                _raise_keyed(RuntimeError, "trae.93392185", page_url=page.url)
                # was: raise RuntimeError(f"未出现验证码输入框: {page.url}")
                # was: raise RuntimeError(f"Verification code input field did not appear: {page.url}")

            code = self.otp_callback()
            if not code:
                _raise_keyed(RuntimeError, "trae.6d0d5d5f")
                # was: raise RuntimeError("未获取到邮箱验证码")
                # was: raise RuntimeError("Failed to obtain the email verification code")
            self.log_key("trae.905556a4", code=code)
            # was: self.log(f"填写验证码: {code}")
            # was: self.log(f"Filling in verification code: {code}")
            otp_el.click()
            otp_el.fill(str(code).strip())
            time.sleep(0.5)

            # 5. 填写密码 — 5. Fill in the password
            self.log_key("trae.4f30b5d0")
            # was: self.log("填写密码...")
            # was: self.log("Filling in password...")
            pwd_selectors = [
                'input[placeholder="Password"]',
                'input[type="password"]',
                'input[name="password"]',
            ]
            for sel in pwd_selectors:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        el.click()
                        el.fill(password)
                        time.sleep(0.3)
                        break
                except Exception:
                    pass

            # 6. 点击 "Sign Up" — 6. Click "Sign Up"
            self.log_key("trae.9707980e")
            # was: self.log("提交注册...")
            # was: self.log("Submitting registration...")
            signup_clicked = False
            deadline_signup = time.time() + 10
            while time.time() < deadline_signup and not signup_clicked:
                try:
                    el = page.locator('text="Sign Up"').last
                    if el.is_visible():
                        el.click()
                        signup_clicked = True
                        self.log_key("trae.101785a9")
                        # was: self.log("已点击 Sign Up")
                        # was: self.log("Clicked Sign Up")
                        break
                except Exception:
                    pass
                if not signup_clicked:
                    try:
                        page.evaluate("""
                        () => {
                            const all = document.querySelectorAll('*');
                            for (const el of all) {
                                const t = el.textContent.trim();
                                if (el.children.length === 0 && (t === 'Sign Up' || t === 'Sign up')) {
                                    el.click();
                                    return;
                                }
                            }
                        }
                        """)
                        signup_clicked = True
                        self.log_key("trae.90e61a07")
                        # was: self.log("已点击 Sign Up (JS)")
                        # was: self.log("Clicked Sign Up (JS)")
                    except Exception:
                        pass
                time.sleep(0.5)

            if not signup_clicked:
                self.log_key("trae.dd2c6074")
                # was: self.log("⚠️ 未能点击 Sign Up，尝试 Enter")
                # was: self.log("⚠️ Failed to click Sign Up, trying Enter")
                page.keyboard.press("Enter")

            time.sleep(3)

            # 7. 等待跳转（离开 sign-up 页） — 7. Wait for redirect (leaving the sign-up page)
            self.log_key("trae.e01ea3d4")
            # was: self.log("等待注册完成...")
            # was: self.log("Waiting for registration to complete...")
            deadline_done = time.time() + 30
            while time.time() < deadline_done:
                if "sign-up" not in page.url and "trae.ai" in page.url:
                    break
                time.sleep(1)

            time.sleep(2)

            # 8. 提取 token — 8. Extract the token
            self.log_key("trae.c42b714b")
            # was: self.log("提取 Trae token...")
            # was: self.log("Extracting Trae token...")
            token, user_id, region = _get_trae_cloudide_token(page, self.log, log_key=self._log_key_fn)

            if not token:
                self.log_key("trae.b7ab0160")
                # was: self.log("⚠️ 未从 Cookie 获取到 token，尝试等待...")
                # was: self.log("⚠️ Token not found in Cookie, waiting and retrying...")
                time.sleep(5)
                token, user_id, region = _get_trae_cloudide_token(page, self.log, log_key=self._log_key_fn)

            self.log_key("trae.90bedbfd", email=email)
            # was: self.log(f"✓ 注册成功: {email}")
            # was: self.log(f"✓ Registration successful: {email}")
            return {
                "email": email,
                "password": password,
                "token": token,
                "user_id": user_id,
                "region": region,
                "cashier_url": "",
                "ai_pay_host": "",
            }
