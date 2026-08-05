"""Kiro (AWS Builder ID) 浏览器注册流程（Camoufox）。

注册流程：
  1. 打开 app.kiro.dev/signin
  2. 点击 "AWS Builder ID" 选项
  3. 跳转到 us-east-1.signin.aws → profile.aws.amazon.com
  4. AWS Builder ID 注册 SPA：
     a. enter-email 步：确认/填写邮箱 → Continue
     b. enter-name 步：填写姓名 → Continue
     c. verify-email 步：填写 OTP → Continue
     d. create-password 步：设置密码 → Continue
  5. 跳回 app.kiro.dev，从 localStorage 提取 Cognito tokens

Kiro (AWS Builder ID) browser registration flow (Camoufox).

Registration flow:
  1. Open app.kiro.dev/signin
  2. Click the "AWS Builder ID" option
  3. Redirect to us-east-1.signin.aws → profile.aws.amazon.com
  4. AWS Builder ID registration SPA:
     a. enter-email step: confirm/fill in email → Continue
     b. enter-name step: fill in name → Continue
     c. verify-email step: fill in OTP → Continue
     d. create-password step: set password → Continue
  5. Redirect back to app.kiro.dev, extract Cognito tokens from localStorage
"""
import random
import string
import time
from typing import Callable, Optional
from urllib.parse import urlparse

from camoufox.sync_api import Camoufox

from platforms.kiro._i18n_helpers import _emit_log_key, _raise_keyed

KIRO_URL = "https://app.kiro.dev"
AWS_SIGNIN_DOMAIN = "signin.aws"
AWS_PROFILE_DOMAIN = "profile.aws.amazon.com"


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


def _js_click_by_text(page, *texts) -> bool:
    """用 JS 找到 textContent 精确匹配的最小叶节点并点击。 — Use JS to find the smallest leaf node whose textContent matches exactly, and click it."""
    for text in texts:
        try:
            clicked = page.evaluate(f"""
            () => {{
                const walker = document.createTreeWalker(
                    document.body, NodeFilter.SHOW_TEXT, null
                );
                let node;
                while (node = walker.nextNode()) {{
                    if (node.textContent.trim() === {repr(text)}) {{
                        const el = node.parentElement;
                        if (el) {{ el.click(); return true; }}
                    }}
                }}
                return false;
            }}
            """)
            if clicked:
                return True
        except Exception:
            pass
    return False


def _click_submit_button(page, timeout: int = 8) -> bool:
    """点击 submit 按钮（AWS 页面用 button[type=submit]）。 — Click the submit button (AWS pages use button[type=submit])."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        # 1. 优先 Playwright locator text 精确匹配 — 1. First, try an exact-text match via Playwright locator
        for text in ["Continue", "Next", "Verify", "Create account", "Sign in", "Submit"]:
            try:
                el = page.locator(f'text="{text}"').last
                if el.is_visible():
                    el.click()
                    return True
            except Exception:
                pass
        # 2. button[type=submit]
        try:
            el = page.query_selector('button[type="submit"]:not([disabled])')
            if el and el.is_visible():
                el.click()
                return True
        except Exception:
            pass
        # 3. JS text walker
        if _js_click_by_text(page, "Continue", "Next", "Verify", "Create account"):
            return True
        time.sleep(0.5)
    return False


def _fill_input_wait(page, selectors: list, value: str, timeout: int = 20) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    el.fill(value)
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    return False


def _get_kiro_tokens(page, timeout: int = 30) -> dict:
    """从 localStorage 提取 Cognito accessToken / refreshToken。 — Extract the Cognito accessToken / refreshToken from localStorage."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = page.evaluate("""
            () => {
                const out = {};
                for (const k of Object.keys(localStorage)) {
                    out[k] = localStorage.getItem(k);
                }
                return out;
            }
            """)
            access = refresh = id_token = ""
            for k, v in result.items():
                kl = k.lower()
                if "accesstoken" in kl and not access:
                    access = v
                if "refreshtoken" in kl and not refresh:
                    refresh = v
                if "idtoken" in kl and not id_token:
                    id_token = v
            if access:
                return {"accessToken": access, "refreshToken": refresh, "idToken": id_token}
        except Exception:
            pass
        time.sleep(2)
    return {}


def _random_name() -> str:
    first = ''.join(random.choices(string.ascii_lowercase, k=random.randint(4, 7))).capitalize()
    last = ''.join(random.choices(string.ascii_lowercase, k=random.randint(4, 7))).capitalize()
    return f"{first} {last}"


class KiroBrowserRegister:
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

    def _handle_aws_profile_spa(self, page, email: str, password: str) -> None:
        """处理 profile.aws.amazon.com 上的多步注册 SPA。

        步骤对应 URL hash：
          #/signup/enter-email  → 填/确认邮箱 → Continue
          #/signup/enter-name   → 填姓名 → Continue
          #/signup/verify-email → 填 OTP → Continue
          #/signup/create-password → 填密码 → Continue (可选)

        Handle the multi-step registration SPA on profile.aws.amazon.com.

        Steps correspond to the URL hash:
          #/signup/enter-email  → fill/confirm email → Continue
          #/signup/enter-name   → fill in name → Continue
          #/signup/verify-email → fill in OTP → Continue
          #/signup/create-password → set password → Continue (optional)
        """
        deadline = time.time() + 300  # 最多等 5 分钟完成整个流程 — wait at most 5 minutes for the whole flow

        email_selectors = [
            'input[placeholder*="username@example.com"]',
            'input[type="email"]',
            'input[name="email"]',
            'input[name="username"]',
        ]
        name_selectors = [
            'input[placeholder*="Maria"]',
            'input[placeholder*="name" i]',
            'input[name="name"]',
            'input[name="fullName"]',
        ]
        otp_selectors = [
            'input[placeholder*="6"]',
            'input[name="otp"]',
            'input[name="code"]',
            'input[autocomplete="one-time-code"]',
            'input[inputmode="numeric"]',
            'input[maxlength="6"]',
        ]
        pwd_selectors = [
            'input[type="password"]',
            'input[name="password"]',
        ]

        handled_steps = set()
        enter_email_retries = 0
        prev_hash = None
        hash_stuck_since = None

        while time.time() < deadline:
            url = page.url
            hash_part = url.split("#")[-1] if "#" in url else ""

            # 跳回了 kiro.dev -> 完成 — jumped back to kiro.dev -> done
            if "kiro.dev" in url and "profile.aws" not in url and "signin.aws" not in url:
                return

            # 检测 hash 是否卡住（同一 hash 停留过久且已处理过）→ 允许重试 —
            # detect a stuck hash (same hash lingering too long and already handled) → allow retry
            if hash_part == prev_hash:
                if hash_stuck_since is None:
                    hash_stuck_since = time.time()
                elif time.time() - hash_stuck_since > 20:
                    step_key = hash_part.split("/")[-1]
                    if step_key in handled_steps:
                        self.log_key("kiro.201f7fb5", step_key=step_key)
                        # was: self.log(f"⚠️ 步骤 {step_key} 卡住 20 秒，移除标记以重试") — was: self.log(f"Step {step_key} stuck for 20s; clearing its marker to retry")
                        handled_steps.discard(step_key)
                        hash_stuck_since = None
            else:
                prev_hash = hash_part
                hash_stuck_since = None

            # --- enter-email 步（邮箱+姓名在同一页）--- — enter-email step (email and name on the same page)
            if "enter-email" in hash_part and "enter-email" not in handled_steps:
                enter_email_retries += 1
                if enter_email_retries > 5:
                    _raise_keyed(RuntimeError, "kiro.a32a53fb", url=page.url)
                    # was: raise RuntimeError(
                    #     f"AWS enter-email 步骤重试超 5 次仍无法前进 — "
                    #     f"邮箱域名可能被 AWS 拒绝 (url={page.url})"
                    # )
                    # was: raise RuntimeError(
                    #     f"AWS enter-email step retried more than 5 times with no progress — "
                    #     f"the email domain may be rejected by AWS (url={page.url})"
                    # )
                self.log_key("kiro.d701bc86", retries=enter_email_retries)
                # was: self.log(f"AWS 步骤: 确认邮箱 + 填写姓名 (第{enter_email_retries}次)") —
                # was: self.log(f"AWS step: confirm email + fill name (attempt {enter_email_retries})")
                time.sleep(1.5)  # 给 SPA 渲染时间 — give the SPA time to render
                # 填邮箱（若为空）— fill the email field (if empty)
                for sel in email_selectors:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            cur = el.input_value() or ""
                            if not cur:
                                el.fill(email)
                            break
                    except Exception:
                        pass
                # 等待姓名输入框出现（最多 15 秒）— wait for the name input to appear (up to 15s)
                name = _random_name()
                name_filled = False
                name_deadline = time.time() + 15
                while time.time() < name_deadline and not name_filled:
                    for sel in name_selectors:
                        try:
                            el = page.query_selector(sel)
                            if el and el.is_visible():
                                el.click()
                                time.sleep(0.2)
                                el.fill(name)
                                time.sleep(0.2)
                                # 确认填入成功 — confirm the fill succeeded
                                if el.input_value():
                                    self.log_key("kiro.201e3d4e", name=name)
                                    # was: self.log(f"填写姓名: {name}") — was: self.log(f"Filled name: {name}")
                                    name_filled = True
                                    break
                        except Exception:
                            pass
                    if not name_filled:
                        time.sleep(0.5)

                if not name_filled:
                    self.log_key("kiro.50f26819")
                    # was: self.log("⚠️ 未能填写姓名，尝试 JS 方式") —
                    # was: self.log("⚠️ Failed to fill name, trying the JS approach")
                    try:
                        page.evaluate(f"""
                        () => {{
                            const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
                            for (const inp of inputs) {{
                                const ph = inp.placeholder || '';
                                if (ph.includes('Maria') || inp.closest('[class*="name"]') || 
                                    inp.closest('[class*="Name"]')) {{
                                    inp.focus();
                                    inp.value = {repr(name)};
                                    inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                                    inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                                    return;
                                }}
                            }}
                        }}
                        """)
                        time.sleep(0.3)
                    except Exception:
                        pass

                time.sleep(0.5)
                _click_submit_button(page, timeout=8)
                handled_steps.add("enter-email")
                # 等待 hash 变化（最多 12 秒），若未变则清除标记允许重试 —
                # wait for the hash to change (up to 12s); if unchanged, clear the marker to allow retry
                start_wait = time.time()
                while time.time() - start_wait < 12:
                    time.sleep(0.5)
                    new_url = page.url
                    new_hash = new_url.split("#")[-1] if "#" in new_url else ""
                    if new_hash != hash_part:
                        break  # hash 变了，进入下一步 — hash changed, move to the next step
                else:
                    # 12 秒后 hash 未变，提交可能失败，允许重试 — hash unchanged after 12s; the submit may have failed, allow retry
                    self.log_key("kiro.c26ff0a8")
                    # was: self.log("⚠️ enter-email 提交后 URL 未变化，将重试") —
                    # was: self.log("⚠️ URL unchanged after enter-email submit, will retry")
                    handled_steps.discard("enter-email")
                    hash_stuck_since = time.time()
                continue

            # --- enter-name 步 --- — enter-name step
            if "enter-name" in hash_part and "enter-name" not in handled_steps:
                self.log_key("kiro.53456c06")
                # was: self.log("AWS 步骤: 填写姓名") — was: self.log("AWS step: fill in name")
                time.sleep(1.5)
                name = _random_name()
                name_filled = False
                name_deadline = time.time() + 15
                while time.time() < name_deadline and not name_filled:
                    for sel in name_selectors:
                        try:
                            el = page.query_selector(sel)
                            if el and el.is_visible():
                                el.click()
                                time.sleep(0.2)
                                el.fill(name)
                                if el.input_value():
                                    self.log_key("kiro.201e3d4e", name=name)
                                    # was: self.log(f"填写姓名: {name}") — was: self.log(f"Filled name: {name}")
                                    name_filled = True
                                    break
                        except Exception:
                            pass
                    if not name_filled:
                        time.sleep(0.5)
                _click_submit_button(page, timeout=5)
                handled_steps.add("enter-name")
                time.sleep(2)
                continue

            # --- verify-email 步 --- — verify-email step
            if "verify-email" in hash_part and "verify-email" not in handled_steps:
                self.log_key("kiro.294a541a")
                # was: self.log("AWS 步骤: 填写验证码") — was: self.log("AWS step: fill in the verification code")
                # 等待 OTP 输入框出现 — wait for the OTP input to appear
                otp_el = None
                otp_deadline = time.time() + 30
                while time.time() < otp_deadline:
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
                    _raise_keyed(RuntimeError, "kiro.c4bf09d7", url=page.url)
                    # was: raise RuntimeError(f"未出现验证码输入框: {page.url}") —
                    # was: raise RuntimeError(f"OTP input never appeared: {page.url}")

                if not self.otp_callback:
                    _raise_keyed(RuntimeError, "kiro.7765a848")
                    # was: raise RuntimeError("Kiro 注册需要邮箱验证码但未提供 otp_callback") —
                    # was: raise RuntimeError("Kiro registration needs an email OTP but no otp_callback was provided")

                code = self.otp_callback()
                if not code:
                    _raise_keyed(RuntimeError, "kiro.6d0d5d5f")
                    # was: raise RuntimeError("未获取到邮箱验证码") —
                    # was: raise RuntimeError("Failed to obtain the email verification code")
                self.log_key("kiro.905556a4", code=code)
                # was: self.log(f"填写验证码: {code}") — was: self.log(f"Filled verification code: {code}")
                otp_el.click()
                for digit in str(code).strip():
                    page.keyboard.press(digit)
                    time.sleep(0.1)
                time.sleep(0.5)
                _click_submit_button(page, timeout=5)
                handled_steps.add("verify-email")
                time.sleep(2)
                continue

            # --- create-password 步 --- — create-password step
            if "create-password" in hash_part and "create-password" not in handled_steps:
                self.log_key("kiro.878378ee")
                # was: self.log("AWS 步骤: 设置密码") — was: self.log("AWS step: set password")
                time.sleep(1)
                pwd_fields = []
                for sel in pwd_selectors:
                    try:
                        els = page.query_selector_all(sel)
                        pwd_fields.extend([e for e in els if e.is_visible()])
                    except Exception:
                        pass
                if pwd_fields:
                    for f in pwd_fields:
                        try:
                            f.click()
                            f.fill(password)
                            time.sleep(0.2)
                        except Exception:
                            pass
                    time.sleep(0.5)
                    _click_submit_button(page, timeout=5)
                handled_steps.add("create-password")
                time.sleep(2)
                continue

            # 没有 hash 的情况：可能在中间跳转页，等待 — no hash case: possibly an intermediate redirect page, wait
            time.sleep(1)

        _raise_keyed(RuntimeError, "kiro.27aef757", url=page.url)
        # was: raise RuntimeError(f"AWS Builder ID 注册未在规定时间内完成: {page.url}") —
        # was: raise RuntimeError(f"AWS Builder ID registration did not finish in time: {page.url}")

    def run(self, email: str, password: str) -> dict:
        if not self.otp_callback:
            _raise_keyed(RuntimeError, "kiro.7765a848")
            # was: raise RuntimeError("Kiro 注册需要邮箱验证码但未提供 otp_callback") —
            # was: raise RuntimeError("Kiro registration needs an email OTP but no otp_callback was provided")

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

            # 1. 打开 Kiro 登录页 — 1. Open the Kiro sign-in page
            self.log_key("kiro.67562fc8")
            # was: self.log("打开 Kiro 登录页") — was: self.log("Opening the Kiro sign-in page")
            page.goto(f"{KIRO_URL}/signin", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            # 2. 点击 AWS Builder ID 选项 — 2. Click the AWS Builder ID option
            self.log_key("kiro.6ecb47e9")
            # was: self.log("选择 AWS Builder ID 登录方式") — was: self.log("Selecting the AWS Builder ID sign-in method")
            builder_clicked = False
            deadline_builder = time.time() + 15
            while time.time() < deadline_builder and not builder_clicked:
                # Playwright locator 文本精确匹配 — exact match via Playwright locator text
                for text in ["Builder ID", "AWS Builder ID"]:
                    try:
                        el = page.locator(f'text="{text}"').last
                        if el.is_visible():
                            el.click()
                            builder_clicked = True
                            self.log_key("kiro.c1bdce0c", text=text)
                            # was: self.log(f"点击了 {text}") — was: self.log(f"Clicked {text}")
                            break
                    except Exception:
                        pass
                if not builder_clicked:
                    # JS walker fallback
                    builder_clicked = _js_click_by_text(page, "Builder ID", "AWS Builder ID")
                    if builder_clicked:
                        self.log_key("kiro.d2a1034a")
                        # was: self.log("点击了 Builder ID (JS)") — was: self.log("Clicked Builder ID (JS)")
                if not builder_clicked:
                    time.sleep(0.5)

            time.sleep(2)

            # 3. 可能有二级 "Sign in" 箭头（Kiro 的选项卡 UI）— 3. There may be a secondary "Sign in" arrow (Kiro's tab UI)
            _click_submit_button(page, timeout=5)
            time.sleep(2)

            # 4. 等待进入 AWS 域名 — 4. Wait to land on the AWS domain
            self.log_key("kiro.88e2e944")
            # was: self.log("等待 AWS 登录页...") — was: self.log("Waiting for the AWS sign-in page...")
            if not _wait_for_url(page, AWS_SIGNIN_DOMAIN, timeout=30):
                if AWS_PROFILE_DOMAIN not in page.url:
                    _raise_keyed(RuntimeError, "kiro.fc411519", url=page.url)
                    # was: raise RuntimeError(f"未跳转到 AWS 登录页: {page.url}") —
                    # was: raise RuntimeError(f"Did not redirect to the AWS sign-in page: {page.url}")

            time.sleep(2)

            # 5. 如果落在 signin.aws（已有账号登录页），先填邮箱提交 —
            # 5. If we land on signin.aws (existing-account sign-in page), fill and submit email first
            if AWS_SIGNIN_DOMAIN in page.url:
                self.log_key("kiro.eaa92c19", email=email)
                # was: self.log(f"填写邮箱: {email}") — was: self.log(f"Filling in email: {email}")
                email_selectors = [
                    'input[placeholder*="username@example.com"]',
                    'input[type="email"]',
                    'input[name="email"]',
                    'input[name="username"]',
                ]
                if not _fill_input_wait(page, email_selectors, email, timeout=15):
                    _raise_keyed(RuntimeError, "kiro.7b397433", url=page.url)
                    # was: raise RuntimeError(f"未找到邮箱输入框: {page.url}") —
                    # was: raise RuntimeError(f"Email input not found: {page.url}")
                time.sleep(0.5)
                _click_submit_button(page, timeout=8)
                time.sleep(3)

            # 6. 等待进入 profile.aws.amazon.com（新账号注册流程）
            # AWS 重定向可能需要较长时间，等待最多 60 秒
            # 6. Wait to land on profile.aws.amazon.com (new-account signup flow)
            # AWS redirects can take a while; wait up to 60 seconds
            self.log_key("kiro.6ab049a5")
            # was: self.log("等待进入 AWS 注册流程...") — was: self.log("Waiting to enter the AWS registration flow...")
            deadline_profile = time.time() + 60
            while time.time() < deadline_profile:
                if AWS_PROFILE_DOMAIN in page.url:
                    break
                if "kiro.dev" in page.url:
                    break
                time.sleep(1)

            if AWS_PROFILE_DOMAIN in page.url:
                self.log_key("kiro.a42dd43b")
                # was: self.log("进入 AWS Builder ID 注册流程...") —
                # was: self.log("Entered the AWS Builder ID registration flow...")
                self._handle_aws_profile_spa(page, email, password)
            elif "kiro.dev" in page.url:
                # 已有账号直接登录成功 — existing account signed in directly
                self.log_key("kiro.b1c61663")
                # was: self.log("已有账号，直接登录成功") — was: self.log("Existing account, signed in directly")
            elif AWS_SIGNIN_DOMAIN in page.url:
                # 还在 signin.aws：可能是已有账号密码步骤 — still on signin.aws: likely the existing-account password step
                self.log_key("kiro.f5a67d0d")
                # was: self.log("检测到密码输入页，填写密码...") —
                # was: self.log("Detected the password page, filling in password...")
                pwd_selectors = ['input[type="password"]', 'input[name="password"]']
                _fill_input_wait(page, pwd_selectors, password, timeout=10)
                time.sleep(0.5)
                _click_submit_button(page, timeout=5)
                time.sleep(3)
                # 密码提交后再等一次 profile.aws 或 kiro.dev —
                # after submitting the password, wait once more for profile.aws or kiro.dev
                deadline2 = time.time() + 60
                while time.time() < deadline2:
                    if AWS_PROFILE_DOMAIN in page.url:
                        self.log_key("kiro.517c4bdf")
                        # was: self.log("密码后跳转到 AWS 注册流程...") —
                        # was: self.log("Redirected to the AWS registration flow after password...")
                        self._handle_aws_profile_spa(page, email, password)
                        break
                    if "kiro.dev" in page.url:
                        break
                    time.sleep(1)

            # 7. 等待跳回 kiro.dev — 7. Wait to jump back to kiro.dev
            self.log_key("kiro.d356e389")
            # was: self.log("等待跳回 Kiro...") — was: self.log("Waiting to jump back to Kiro...")
            if not _wait_for_url(page, "kiro.dev", timeout=60):
                _raise_keyed(RuntimeError, "kiro.1350e13c", url=page.url)
                # was: raise RuntimeError(f"Kiro 注册未跳转回应用: {page.url}") —
                # was: raise RuntimeError(f"Kiro registration did not redirect back to the app: {page.url}")

            time.sleep(3)

            # 8. 提取 Cognito tokens — 8. Extract Cognito tokens
            self.log_key("kiro.47ec52c6")
            # was: self.log("提取 Kiro 访问令牌...") — was: self.log("Extracting the Kiro access token...")
            tokens = _get_kiro_tokens(page, timeout=20)

            self.log_key("kiro.90bedbfd", email=email)
            # was: self.log(f"✓ 注册成功: {email}") — was: self.log(f"✓ Registration succeeded: {email}")
            return {
                "email": email,
                "password": password,
                "accessToken": tokens.get("accessToken", ""),
                "refreshToken": tokens.get("refreshToken", ""),
                "idToken": tokens.get("idToken", ""),
                "sessionToken": "",
                "clientId": "",
                "clientSecret": "",
            }
