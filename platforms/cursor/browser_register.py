"""Cursor 浏览器注册流程（Camoufox）。

实际流程：
  1. https://authenticator.cursor.sh/sign-up
  2. 填写 FirstName / LastName / Email（同一页面）
  3. 提交 → Cloudflare Turnstile 验证（自动/注入）
  4. 收取邮箱验证码（6位）→ 输入
  5. 跳转 cursor.com → 获取 WorkosCursorSessionToken
"""
import random, string, time, uuid
from typing import Callable, Optional
from urllib.parse import unquote, urlparse

from camoufox.sync_api import Camoufox

from platforms.cursor._i18n_helpers import _emit_log_key, _raise_keyed

AUTH = "https://authenticator.cursor.sh"
CURSOR = "https://cursor.com"
TURNSTILE_SITEKEY = "0x4AAAAAAAMNIvC45A4Wjjln"


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


def _get_turnstile_sitekey(page) -> str:
    try:
        sitekey = page.evaluate(
            """() => {
                const node = document.querySelector('[data-sitekey], .cf-turnstile, [data-captcha-sitekey]');
                return node ? (node.getAttribute('data-sitekey') || node.getAttribute('data-captcha-sitekey') || '') : '';
            }"""
        )
        if sitekey:
            return sitekey.strip()
    except Exception:
        pass
    return TURNSTILE_SITEKEY


def _inject_turnstile(page, token: str) -> bool:
    """注入 Turnstile token，兼容 explicit 渲染模式（Cursor 使用此模式）。"""
    safe = token.replace("\\", "\\\\").replace("'", "\\'")
    script = f"""(function() {{
        const token = '{safe}';

        // 1. override window.turnstile API（explicit 模式下服务端会调用 getResponse）
        if (window.turnstile) {{
            const orig = window.turnstile;
            window.turnstile = new Proxy(orig, {{
                get(target, prop) {{
                    if (prop === 'getResponse') return () => token;
                    if (prop === 'isExpired') return () => false;
                    return Reflect.get(target, prop);
                }}
            }});
        }}

        // 2. 触发所有已注册的 callback
        const fns = [
            window._turnstileTokenCallback,
            window.turnstileCallback,
            window.onTurnstileSuccess,
            window.cfTurnstileCallback,
        ];
        fns.forEach(fn => {{ if (typeof fn === 'function') {{ try {{ fn(token); }} catch(e) {{}} }} }});

        // 3. 注入 hidden input（兼容 form submit 模式）
        const names = ['captcha', 'cf-turnstile-response'];
        const form = document.querySelector('form') || document.body;
        names.forEach(name => {{
            let f = document.querySelector('input[name="' + name + '"], textarea[name="' + name + '"]');
            if (!f) {{ f = document.createElement('input'); f.type = 'hidden'; f.name = name; form.appendChild(f); }}
            f.value = token;
            f.dispatchEvent(new Event('input', {{bubbles: true}}));
            f.dispatchEvent(new Event('change', {{bubbles: true}}));
        }});

        // 4. 尝试直接触发 Turnstile 内部 callback（通过 iframe postMessage）
        try {{
            document.querySelectorAll('iframe').forEach(iframe => {{
                if (iframe.src && iframe.src.includes('cloudflare.com')) {{
                    iframe.contentWindow.postMessage(JSON.stringify({{
                        source: 'cloudflare-challenge',
                        token: token,
                    }}), '*');
                }}
            }});
        }} catch(e) {{}}

        return true;
    }})();"""
    return bool(page.evaluate(script))


def _click_continue(page) -> bool:
    """尝试点击 Continue/Next/Sign up 按钮，兜底用 Enter。"""
    for sel in [
        'button[data-action-button-primary="true"]',
        'button[type="submit"]:not([aria-hidden="true"])',
        'button:has-text("Continue")',
        'button:has-text("Next")',
        'button:has-text("Sign up")',
        'button[type="submit"]',
        'button',
    ]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible() and el.is_enabled():
                el.click(timeout=3000)
                return True
        except Exception:
            continue
    return False


def _get_token_from_cookies(page) -> str:
    for cookie in page.context.cookies():
        if cookie["name"] == "WorkosCursorSessionToken":
            return unquote(cookie["value"])
    return ""


def _wait_for_token(page, timeout: int = 120) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        tok = _get_token_from_cookies(page)
        if tok:
            return tok
        time.sleep(1)
    return ""


def _is_cf_full_block(page) -> bool:
    """检测是否被 CF 全页拦截（区别于表单内嵌 Turnstile widget）。
    
    全页拦截特征：页面只有 CF 挑战，没有正常的表单内容。
    内嵌 Turnstile：页面表单正常显示，只是其中有 CF iframe。
    """
    try:
        content = page.content().lower()
        # 全页拦截的关键词（不含 challenges.cloudflare.com，因为那是 widget 的 script） — Full-block keywords (excludes challenges.cloudflare.com, which belongs to the widget's own script)
        full_block_signals = [
            "just a moment",
            "checking your browser",
            "verifying you are human",
            "verify you are human",
            "performing security verification",
            "security check to access",
            "ray id",
        ]
        if any(kw in content for kw in full_block_signals):
            # 同时确认没有正常表单（有表单=只是内嵌 widget，不是全页拦截） — Also confirm there's no normal form (a form present means it's just an inline widget, not a full-page block)
            has_form = bool(page.query_selector('input[name="email"], input[name="firstName"], input[name="otp"], input[name="code"]'))
            if not has_form:
                return True
    except Exception:
        pass
    return False


def _wait_cf_full_block_clear(
    page,
    timeout: int = 120,
    log_fn=print,
    log_key: Optional[Callable[[str, dict], None]] = None,
) -> None:
    """等待 CF 全页拦截消失，并主动点击 Interstitial Turnstile checkbox。
    
    CF 全页拦截分两种：
    1. Interactive Turnstile：显示 checkbox，需要点击
    2. Managed Challenge： no-checkbox 被动验证，显示圆圈/加载中，就等
    """
    deadline = time.time() + timeout
    warned = False
    clicked = False
    while time.time() < deadline:
        if not _is_cf_full_block(page):
            break
        if not warned:
            _emit_log_key(log_fn, log_key, "cursor.df7412e9")
            # was: log_fn("检测到 Cloudflare 全页拦截，尝试点击验证 checkbox...") — was: log_fn("Detected Cloudflare full-page block, trying to click the verification checkbox...")
            warned = True
        # 模拟人类鼠标移动（CF 被动检测会观察鼠标行为） — Simulate human mouse movement (CF's passive detection watches mouse behavior)
        try:
            w = page.viewport_size or {"width": 1280, "height": 720}
            for _ in range(3):
                page.mouse.move(
                    random.randint(100, w["width"] - 100),
                    random.randint(100, w["height"] - 100)
                )
                time.sleep(random.uniform(0.1, 0.3))
        except Exception:
            pass
        # 尝试找 CF interstitial Turnstile iframe 并点击 — Try to find the CF interstitial Turnstile iframe and click it
        if not clicked:
            try:
                for frame in page.frames:
                    if "challenges.cloudflare.com" in frame.url:
                        iframe_el = frame.frame_element()
                        box = iframe_el.bounding_box()
                        if box:
                            cx = box["x"] + 24
                            cy = box["y"] + box["height"] / 2
                            # 模拟人类行为：先等几秒"看页面"，再缓慢移动到目标 — Simulate human behavior: wait a few seconds "looking at the page" first, then move slowly to the target
                            time.sleep(random.uniform(1.5, 3.0))
                            # 从当前位置平滑移动到 checkbox（分多步） — Smoothly move from the current position to the checkbox (in multiple steps)
                            w = page.viewport_size or {"width": 1280, "height": 720}
                            cur_x = random.randint(200, w["width"] - 200)
                            cur_y = random.randint(200, w["height"] - 200)
                            page.mouse.move(cur_x, cur_y)
                            steps = random.randint(8, 15)
                            for i in range(steps):
                                t = (i + 1) / steps
                                # 贝塞尔曲线平滑插值 — Bezier-curve smoothing interpolation
                                mid_x = cur_x + (cx - cur_x) * t + random.randint(-15, 15)
                                mid_y = cur_y + (cy - cur_y) * t + random.randint(-8, 8)
                                page.mouse.move(mid_x, mid_y)
                                time.sleep(random.uniform(0.02, 0.07))
                            # 最终移到目标并点击 — Finally move to the target and click
                            page.mouse.move(cx, cy)
                            time.sleep(random.uniform(0.1, 0.3))
                            page.mouse.down()
                            time.sleep(random.uniform(0.08, 0.15))
                            page.mouse.up()
                            _emit_log_key(log_fn, log_key, "cursor.4552f07c", cx=f"{cx:.0f}", cy=f"{cy:.0f}")
                            # was: log_fn(f"✅ 点击 Interstitial checkbox 坐标: ({cx:.0f}, {cy:.0f})") — was: log_fn(f"Clicked interstitial checkbox at: ({cx:.0f}, {cy:.0f})")
                            clicked = True
                            time.sleep(3)
                            break
            except Exception:
                pass
            if not clicked:
                # iframe 还没加载，稍等再试 — iframe hasn't loaded yet, wait and retry
                time.sleep(1)
        else:
            # 已点击，等待 CF 被动验证完成（Managed Challenge 可能需要较長时间） — Already clicked; wait for CF's passive verification to finish (a Managed Challenge can take a while)
            time.sleep(2)


def _has_turnstile_iframe(page) -> bool:
    """检测页面中是否有 Turnstile iframe（包括内嵌 widget）。"""
    try:
        for frame in page.frames:
            if "challenges.cloudflare.com" in frame.url:
                return True
        result = page.evaluate(
            """() => {
                const iframes = document.querySelectorAll('iframe');
                for (const f of iframes) {
                    if (f.src && f.src.includes('challenges.cloudflare.com')) return true;
                }
                return false;
            }"""
        )
        return bool(result)
    except Exception:
        return False

def _is_turnstile_modal_visible(page) -> bool:
    """检测 Turnstile 挑战是否可见（使用 body 文字，因为 iframe 延迟加载）。"""
    try:
        content = page.content().lower()
        signals = [
            "confirm you are human",
            "确认您是真人",
            "we need to confirm you are human",
            "需要确认您是真人",
        ]
        if any(s in content for s in signals):
            return True
        # 也检查 iframe（有些环境下 iframe 会有 src） — Also check the iframe (in some environments it will have a src)
        return _has_turnstile_iframe(page)
    except Exception:
        return False


def _click_turnstile_in_iframe(
    page,
    log_fn=print,
    log_key: Optional[Callable[[str, dict], None]] = None,
) -> bool:
    """在注册 Camoufox 浏览器里直接找到 Turnstile iframe 并点击 checkbox。
    
    Turnstile iframe 内部使用 closed Shadow DOM，JS querySelector 无法访问。
    改用 bounding box 坐标点击：checkbox 在 iframe 左侧约 1/4 处。
    返回 True 表示点击了（不代表 Turnstile 已通过）。
    """
    # 等待 iframe 的 frame 出现在 page.frames 列表中 — Wait for the iframe's frame to appear in page.frames
    deadline = time.time() + 15
    cf_frame_obj = None  # playwright Frame 对象 — playwright Frame object
    while time.time() < deadline:
        for frame in page.frames:
            if "challenges.cloudflare.com" in frame.url:
                cf_frame_obj = frame
                break
        if cf_frame_obj:
            break
        time.sleep(0.5)

    if not cf_frame_obj:
        _emit_log_key(log_fn, log_key, "cursor.d24e2d16")
        # was: log_fn("未找到 Cloudflare iframe frame，跳过直接点击") — was: log_fn("Cloudflare iframe frame not found, skipping direct click")
        return False

    _emit_log_key(log_fn, log_key, "cursor.8aa9560b", frame_url=cf_frame_obj.url[:80])
    # was: log_fn(f"找到 Turnstile frame: {cf_frame_obj.url[:80]}...") — was: log_fn(f"Found Turnstile frame: {cf_frame_obj.url[:80]}...")

    # 找到 iframe DOM 元素，获取 bounding box — Find the iframe DOM element and get its bounding box
    iframe_el = None
    for el in page.query_selector_all("iframe"):
        try:
            src = el.get_attribute("src") or ""
            if "cloudflare.com" in src:
                iframe_el = el
                break
        except Exception:
            continue

    if not iframe_el:
        # src 可能为空（动态设置），用 frame owner element — src may be empty (set dynamically); fall back to the frame's owner element
        try:
            iframe_el = cf_frame_obj.frame_element()
        except Exception:
            pass

    if iframe_el:
        try:
            # 等待 bounding box 有效（iframe 渲染需要时间，height=0 时不能点击） — Wait for a valid bounding box (iframe rendering takes time; can't click while height=0)
            box = None
            for _ in range(10):
                b = iframe_el.bounding_box()
                if b and b["height"] > 10 and b["y"] > 0:
                    box = b
                    break
                time.sleep(1)
            if box:
                # checkbox 在 iframe 左侧，大约 x=24, y=center — The checkbox sits near the left of the iframe, roughly x=24, y=center
                cx = box["x"] + 24
                cy = box["y"] + box["height"] / 2
                # 模拟人类点击：移动到目标再按下/松开 — Simulate a human click: move to the target, then press down/release
                page.mouse.move(cx + random.randint(-5, 5), cy + random.randint(-3, 3))
                time.sleep(random.uniform(0.1, 0.25))
                page.mouse.down()
                time.sleep(random.uniform(0.08, 0.15))
                page.mouse.up()
                _emit_log_key(log_fn, log_key, "cursor.88676147", cx=f"{cx:.0f}", cy=f"{cy:.0f}")
                # was: log_fn(f"✅ 点击 Turnstile checkbox 坐标: ({cx:.0f}, {cy:.0f})") — was: log_fn(f"Clicked Turnstile checkbox at: ({cx:.0f}, {cy:.0f})")
                time.sleep(1.5)
                # 如果还没通过，再试一次偏右 — If it still hasn't passed, try again slightly to the right
                if _is_turnstile_modal_visible(page):
                    page.mouse.move(cx + 12, cy)
                    time.sleep(0.1)
                    page.mouse.down()
                    time.sleep(0.1)
                    page.mouse.up()
                    time.sleep(1)
                return True
            else:
                _emit_log_key(log_fn, log_key, "cursor.22c71856")
                # was: log_fn("bounding box 无效（height=0），跳过点击") — was: log_fn("Invalid bounding box (height=0), skipping click")
        except Exception as e:
            _emit_log_key(log_fn, log_key, "cursor.cb9a61ec", exc=str(e))
            # was: log_fn(f"bounding box 点击失败: {e}") — was: log_fn(f"Bounding box click failed: {e}")

    # 兜底：用 Playwright frame 内坐标点击（相对于 frame） — Fallback: click using Playwright's frame-relative coordinates
    try:
        _emit_log_key(log_fn, log_key, "cursor.3b78975f")
        # was: log_fn("尝试 frame 内坐标点击...") — was: log_fn("Trying frame-relative coordinate click...")
        cf_frame_obj.locator("body").click(position={"x": 24, "y": 32}, timeout=5000)
        _emit_log_key(log_fn, log_key, "cursor.89db44e8")
        # was: log_fn("✅ frame 内坐标点击成功") — was: log_fn("Frame-relative coordinate click succeeded")
        return True
    except Exception as e:
        _emit_log_key(log_fn, log_key, "cursor.a5464204", exc=str(e))
        # was: log_fn(f"frame 内点击失败: {e}") — was: log_fn(f"Frame-relative click failed: {e}")

    _emit_log_key(log_fn, log_key, "cursor.649fde05")
    # was: log_fn("所有点击方式均失败") — was: log_fn("All click methods failed")
    return False


def _handle_turnstile(
    page,
    log_fn=print,
    solve_fn=None,
    wait_secs: int = 12,
    log_key: Optional[Callable[[str, dict], None]] = None,
) -> bool:
    """通用 Turnstile 处理：检测到 Turnstile 后点击 checkbox。
    
    可在表单提交后、密码提交后等任意阶段调用。
    返回 True 表示检测到并处理了 Turnstile。
    """
    # 检测 Turnstile 是否出现（最多等 wait_secs 秒） — Detect whether Turnstile appears (wait at most wait_secs seconds)
    deadline = time.time() + wait_secs
    has_turnstile = False
    while time.time() < deadline:
        if _is_turnstile_modal_visible(page):
            has_turnstile = True
            break
        if page.query_selector('input[name="otp"], input[name="code"], input[type="password"]'):
            # 已到达下一步，跳过 — Already reached the next step, skip
            return False
        time.sleep(1)

    if not has_turnstile:
        return False

    _emit_log_key(log_fn, log_key, "cursor.1d3354b3")
    # was: log_fn("检测到 Turnstile，尝试直接点击 iframe checkbox...") — was: log_fn("Detected Turnstile, trying to click the iframe checkbox directly...")
    solved = _click_turnstile_in_iframe(page, log_fn, log_key)
    if not solved:
        # 尝试 token solver 作为备选 — Try the token solver as a fallback
        if solve_fn:
            token = solve_fn(page.url, _get_turnstile_sitekey(page))
            if token:
                _emit_log_key(log_fn, log_key, "cursor.79923f41", token_prefix=token[:40])
                # was: log_fn(f"注入 Turnstile token ({token[:40]}...)") — was: log_fn(f"Injecting Turnstile token ({token[:40]}...)")
                _inject_turnstile(page, token)
                time.sleep(2)
                _click_continue(page)
                time.sleep(3)
                return True
        _emit_log_key(log_fn, log_key, "cursor.07bbce1e")
        # was: log_fn("⚠️ 自动解题失败，等待手动通过（最多90秒）...") — was: log_fn("Auto-solve failed, waiting for manual pass (up to 90s)...")
        dl = time.time() + 90
        while time.time() < dl:
            if not _is_turnstile_modal_visible(page):
                break
            time.sleep(2)
    else:
        time.sleep(3)
        if _is_turnstile_modal_visible(page):
            _emit_log_key(log_fn, log_key, "cursor.b4693307")
            # was: log_fn("Turnstile 仍在显示，等待自动通过...") — was: log_fn("Turnstile still showing, waiting for it to auto-pass...")
            time.sleep(5)
        # Turnstile 通过后如果还没下一步，尝试点 Continue — After Turnstile passes, if still not on the next step, try clicking Continue
        if not page.query_selector('input[name="otp"], input[name="code"]'):
            _click_continue(page)
            time.sleep(3)
    return True


class CursorBrowserRegister:
    """Cursor 浏览器填表注册（Camoufox + mailbox OTP）。"""

    def __init__(
        self,
        *,
        captcha=None,
        headless: bool = True,
        proxy: Optional[str] = None,
        otp_callback: Optional[Callable[[], str]] = None,
        phone_callback: Optional[Callable[[], str]] = None,
        log_fn: Callable[[str], None] = print,
        log_key_fn: Optional[Callable[[str, dict], None]] = None,
    ):
        self.captcha = captcha
        self.headless = headless
        self.proxy = proxy
        self.otp_callback = otp_callback
        self.phone_callback = phone_callback
        self.log = log_fn
        self._log_key_fn = log_key_fn

    def log_key(self, key: str, **params) -> None:
        _emit_log_key(self.log, self._log_key_fn, key, **params)

    def _solve_turnstile(self, url: str, sitekey: str) -> Optional[str]:
        """调用 Captcha Solver 解决 Turnstile，返回 token 或 None。"""
        if not self.captcha:
            self.log_key("cursor.f4c4d88f")
            # was: self.log("未配置 Captcha Solver，跳过自动解题") — was: self.log("No Captcha Solver configured, skipping auto-solve")
            return None
        try:
            self.log_key("cursor.303469c2", sitekey_prefix=sitekey[:20])
            # was: self.log(f"调用 Captcha Solver 解题 ({sitekey[:20]}...)...") — was: self.log(f"Calling Captcha Solver ({sitekey[:20]}...)...")
            token = self.captcha.solve_turnstile(url, sitekey or TURNSTILE_SITEKEY)
            if token:
                self.log_key("cursor.30c13c08", token_prefix=token[:50])
                # was: self.log(f"✅ Solver 返回 token: {token[:50]}...") — was: self.log(f"Solver returned token: {token[:50]}...")
            return token
        except Exception as e:
            self.log_key("cursor.15569914", exc=str(e))
            # was: self.log(f"⚠️ Captcha Solver 失败: {e}") — was: self.log(f"Captcha Solver failed: {e}")
            return None

    def run(self, email: str, password: str = "") -> dict:
        first = ''.join(random.choices(string.ascii_lowercase, k=5)).capitalize()
        last = ''.join(random.choices(string.ascii_lowercase, k=5)).capitalize()

        proxy = _build_proxy_config(self.proxy)
        launch_opts = {"headless": self.headless}
        if proxy:
            launch_opts["proxy"] = proxy

        with Camoufox(**launch_opts) as browser:
            page = browser.new_page()

            # 注入 MouseEvent screenX/screenY patcher
            # CF Turnstile 会检测 CDP 触发的 MouseEvent.screenX == clientX（Chrome bug）
            # 即使在 Firefox/Camoufox 中，Playwright 内部鼠标事件也可能有相同问题
            # 通过 add_init_script 在每个页面加载前注入覆盖，欺骗 Turnstile 的检测
            # 来源: https://github.com/Xewdy444/CDP-bug-MouseEvent-.screenX-.screenY-patcher
            # Inject a MouseEvent screenX/screenY patcher
            # CF Turnstile flags CDP-triggered events where MouseEvent.screenX == clientX (a Chrome bug)
            # Even in Firefox/Camoufox, Playwright's internal mouse events can trigger the same tell
            # Override it via add_init_script before each page load, to spoof Turnstile's detection
            # Source: https://github.com/Xewdy444/CDP-bug-MouseEvent-.screenX-.screenY-patcher
            page.add_init_script("""
(function() {
    var screenX = Math.floor(Math.random() * (1200 - 800 + 1)) + 800;
    var screenY = Math.floor(Math.random() * (600 - 400 + 1)) + 400;
    Object.defineProperty(MouseEvent.prototype, 'screenX', {
        get: function() { return this.clientX + screenX; },
        configurable: true
    });
    Object.defineProperty(MouseEvent.prototype, 'screenY', {
        get: function() { return this.clientY + screenY; },
        configurable: true
    });
    // 同时 patch PointerEvent（CF 也检测这个）
    Object.defineProperty(PointerEvent.prototype, 'screenX', {
        get: function() { return this.clientX + screenX; },
        configurable: true
    });
    Object.defineProperty(PointerEvent.prototype, 'screenY', {
        get: function() { return this.clientY + screenY; },
        configurable: true
    });
})();
""")

            self.log_key("cursor.d008a97b")
            # was: self.log("打开 Cursor 注册页") — was: self.log("Opening the Cursor sign-up page")
            # 必须带 state(含随机 nonce)访问，WorkOS 才会生成 authorization_session_id
            # 没有 authorization_session_id，form POST 到 /user_management/initiate_login 会 404
            # Must visit with a state param (containing a random nonce), or WorkOS won't generate an authorization_session_id
            # Without authorization_session_id, the form POST to /user_management/initiate_login returns 404
            import json, urllib.parse as _up
            _nonce = str(uuid.uuid4())
            _state = _up.quote(json.dumps({"returnTo": "/dashboard", "nonce": _nonce}))
            _redirect = _up.quote("https://cursor.com/api/auth/callback", safe="")
            _signup_url = (
                f"{AUTH}/sign-up"
                f"?client_id=client_01GS6W3C96KW4WRS6Z93JCE2RJ"
                f"&redirect_uri={_redirect}"
                f"&state={_state}"
            )
            page.goto(_signup_url, wait_until="domcontentloaded", timeout=30000)

            # 仅等待真正的 CF 全页拦截（不会被内嵌 Turnstile widget 误触发） — Only wait for a genuine CF full-page block (won't be falsely triggered by an inline Turnstile widget)
            _wait_cf_full_block_clear(page, log_fn=self.log, log_key=self._log_key_fn)  # 默认 120s — defaults to 120s
            # CF 通过后等待页面完全加载（CF 通过会触发重定向） — After CF passes, wait for the page to fully load (passing CF triggers a redirect)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass

            # 等待注册表单出现 — Wait for the sign-up form to appear
            self.log_key("cursor.47b30058")
            # was: self.log("等待注册表单...") — was: self.log("Waiting for the sign-up form...")
            try:
                page.wait_for_selector(
                    'input[name="firstName"], input[name="first_name"], input[name="email"]',
                    timeout=60000,  # 60s - CF Managed Challenge 可能需要较长时间 — 60s: a CF Managed Challenge can take a while
                )
            except Exception:
                _raise_keyed(RuntimeError, "cursor.375fcee3", page_url=page.url)
                # was: raise RuntimeError(f"Cursor 注册页未加载表单: {page.url}") — was: raise RuntimeError(f"Cursor sign-up page did not load a form: {page.url}")

            # 填 FirstName / LastName — Fill in FirstName / LastName
            for sel, val in [
                ('input[name="firstName"]', first),
                ('input[name="first_name"]', first),
                ('input[name="lastName"]', last),
                ('input[name="last_name"]', last),
            ]:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.fill(val)
                    time.sleep(0.3)

            # 填邮箱 — Fill in the email
            email_sel = 'input[name="email"]'
            try:
                page.wait_for_selector(email_sel, timeout=5000)
            except Exception:
                _raise_keyed(RuntimeError, "cursor.62a0424a")
                # was: raise RuntimeError("未找到邮箱输入框") — was: raise RuntimeError("Email input not found")
            self.log_key("cursor.eaa92c19", email=email)
            # was: self.log(f"填写邮箱: {email}") — was: self.log(f"Filling email: {email}")
            page.fill(email_sel, email)
            time.sleep(0.5)

            # 点 Continue 提交表单 — Click Continue to submit the form
            self.log_key("cursor.138af2e7")
            # was: self.log("点击 Continue") — was: self.log("Clicking Continue")
            clicked = _click_continue(page)
            if not clicked:
                self.log_key("cursor.4b48a01b")
                # was: self.log("未找到按钮，使用 Enter 提交") — was: self.log("Button not found, submitting with Enter")
                page.keyboard.press("Enter")

            # --- Turnstile 处理 ---
            # 策略：在注册 Camoufox 浏览器里直接点击 iframe 内的 checkbox
            # 外部 Solver 无效（它自己开浏览器，但不会提交表单，看不到 Turnstile）
            # --- Turnstile handling ---
            # Strategy: click the checkbox inside the iframe directly, in the same Camoufox browser doing the registration
            # An external solver doesn't work here (it opens its own browser and never submits this form, so it can't see the Turnstile)
            self.log_key("cursor.4fa4393e")
            # was: self.log("等待 Turnstile 验证...") — was: self.log("Waiting for Turnstile verification...")
            turnstile_deadline = time.time() + 15
            has_turnstile = False
            while time.time() < turnstile_deadline:
                if _is_turnstile_modal_visible(page):
                    has_turnstile = True
                    break
                if page.query_selector('input[name="otp"], input[name="code"]'):
                    self.log_key("cursor.6ff239b3")
                    # was: self.log("已直接跳转到验证码页，跳过 Turnstile") — was: self.log("Jumped straight to the verification-code page, skipping Turnstile")
                    break
                time.sleep(1)

            if has_turnstile:
                self.log_key("cursor.1d3354b3")
                # was: self.log("检测到 Turnstile，尝试直接点击 iframe checkbox...") — was: self.log("Detected Turnstile, trying to click the iframe checkbox directly...")
                solved = _click_turnstile_in_iframe(page, self.log, self._log_key_fn)
                if not solved:
                    token = self._solve_turnstile(page.url, _get_turnstile_sitekey(page))
                    if token:
                        self.log_key("cursor.79923f41", token_prefix=token[:40])
                        # was: self.log(f"注入 Turnstile token ({token[:40]}...)") — was: self.log(f"Injecting Turnstile token ({token[:40]}...)")
                        _inject_turnstile(page, token)
                        time.sleep(2)
                        _click_continue(page)
                        time.sleep(3)
                    else:
                        self.log_key("cursor.07bbce1e")
                        # was: self.log("⚠️ 自动解题失败，等待手动通过（最多90秒）...") — was: self.log("Auto-solve failed, waiting for manual pass (up to 90s)...")
                        dl = time.time() + 90
                        while time.time() < dl:
                            if not _is_turnstile_modal_visible(page):
                                break
                            if page.query_selector('input[name="otp"], input[name="code"]'):
                                break
                            time.sleep(2)
                else:
                    # 点击成功后等待 Turnstile 处理完成 — After a successful click, wait for Turnstile to finish processing
                    time.sleep(3)
                    if _is_turnstile_modal_visible(page):
                        self.log_key("cursor.b4693307")
                        # was: self.log("Turnstile 仍在显示，等待自动通过...") — was: self.log("Turnstile still showing, waiting for it to auto-pass...")
                        time.sleep(5)

            # --- 处理密码设置页（Turnstile 通过后 Cursor 要求设置密码）--- — --- Handle the password-setup page (Cursor requires a password after Turnstile passes) ---
            try:
                page.wait_for_selector('input[type="password"]', timeout=8000)
                use_password = password or (
                    ''.join(random.choices(string.ascii_uppercase, k=2))
                    + ''.join(random.choices(string.digits, k=3))
                    + ''.join(random.choices(string.ascii_lowercase, k=5))
                    + '!'
                )
                self.log_key("cursor.34081b9f")
                # was: self.log("检测到密码设置页，填写密码...") — was: self.log("Detected password-setup page, filling password...")
                for el in page.query_selector_all('input[type="password"]'):
                    if el.is_visible():
                        el.fill(use_password)
                        time.sleep(0.3)
                password = use_password
                time.sleep(0.5)
                _click_continue(page)
                time.sleep(2)
            except Exception:
                pass  # 无密码页，跳过 — no password page, skip

            # --- 密码提交后可能再次出现 Turnstile（如"Welcome to Cursor"页面）--- — --- Turnstile may appear again after password submission (e.g. the "Welcome to Cursor" page) ---
            _handle_turnstile(page, self.log, self._solve_turnstile, log_key=self._log_key_fn)

            # --- 检测手机号验证页（"Phone number" + "Send verification code"）--- — --- Detect the phone-verification page ("Phone number" + "Send verification code") ---
            try:
                phone_input = page.query_selector('input[type="tel"], input[placeholder*="555"], input[autocomplete="tel"]')
                if not phone_input:
                    # 等几秒看是否跳转到手机号页 — Wait a few seconds to see whether it redirects to the phone page
                    page.wait_for_selector('input[type="tel"]', timeout=4000)
                    phone_input = page.query_selector('input[type="tel"]')
            except Exception:
                phone_input = None

            if phone_input and phone_input.is_visible():
                if self.phone_callback:
                    phone_number = self.phone_callback()
                    if phone_number:
                        self.log_key("cursor.1b2350d0", phone_prefix=phone_number[:4])
                        # was: self.log(f"检测到手机号验证页，填写手机号: {phone_number[:4]}****") — was: self.log(f"Detected phone-verification page, filling phone: {phone_number[:4]}****")
                        phone_input.click()
                        phone_input.fill(str(phone_number).strip())
                        time.sleep(0.5)
                        _click_continue(page)
                        time.sleep(3)
                        # 等待手机验证码输入框（6位数字） — Wait for the phone verification-code input (6 digits)
                        try:
                            page.wait_for_selector(
                                'input[autocomplete="one-time-code"], input[inputmode="numeric"], input[maxlength="1"]',
                                timeout=30000
                            )
                            sms_code = self.phone_callback()  # 复用 callback 获取短信码 — reuse the callback to get the SMS code
                            if sms_code:
                                self.log_key("cursor.73be4e51", sms_code=sms_code)
                                # was: self.log(f"填写短信验证码: {sms_code}") — was: self.log(f"Filling SMS code: {sms_code}")
                                for digit in str(sms_code).strip():
                                    page.keyboard.press(digit)
                                    time.sleep(0.1)
                                time.sleep(1)
                                page.keyboard.press("Enter")
                                time.sleep(3)
                        except Exception as e:
                            self.log_key("cursor.34ff3305", exc=str(e))
                            # was: self.log(f"⚠️ 等待短信验证码失败: {e}") — was: self.log(f"Waiting for SMS code failed: {e}")
                else:
                    _raise_keyed(RuntimeError, "cursor.8f383f94")
                    # was: raise RuntimeError("Cursor 注册需要手机号验证，但未配置 phone_callback。" "请在 RegisterConfig.extra 中配置接码服务，或手动完成手机号验证。") —
                    # was: raise RuntimeError("Cursor registration requires phone verification, but phone_callback isn't configured." "Configure an SMS-receiving service in RegisterConfig.extra, or complete phone verification manually.")

            # 等待验证码输入框（WorkOS email-verification 页面用 6 个独立格子） — Wait for the verification-code input (the WorkOS email-verification page uses 6 separate boxes)
            self.log_key("cursor.482bc0b5")
            # was: self.log("等待验证码输入框...") — was: self.log("Waiting for the verification-code input...")
            OTP_SELECTORS = [
                'input[name="otp"]',
                'input[name="code"]',
                'input[autocomplete="one-time-code"]',
                'input[inputmode="numeric"]',
                'input[maxlength="1"]',
                'input[type="text"]',
                'input[type="number"]',
            ]
            otp_input = None
            deadline_otp = time.time() + 60
            while time.time() < deadline_otp:
                # 也判断 URL 是否已到 email-verification — Also check whether the URL has already reached email-verification
                if "email-verification" in page.url or "verify" in page.url:
                    for sel in OTP_SELECTORS:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            otp_input = el
                            break
                    if otp_input:
                        break
                else:
                    for sel in OTP_SELECTORS[:2]:  # 快速检查前两个 — quickly check the first two
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            otp_input = el
                            break
                    if otp_input:
                        break
                time.sleep(1)

            if not otp_input:
                _raise_keyed(RuntimeError, "cursor.284aec86", page_url=page.url)
                # was: raise RuntimeError(f"未出现验证码输入框 (url={page.url})") — was: raise RuntimeError(f"Verification-code input never appeared (url={page.url})")

            if not self.otp_callback:
                _raise_keyed(RuntimeError, "cursor.d704251c")
                # was: raise RuntimeError("Cursor 注册需要邮箱验证码但未提供 otp_callback") — was: raise RuntimeError("Cursor registration requires an email verification code but otp_callback wasn't provided")
            self.log_key("cursor.c1aefad5")
            # was: self.log("等待邮箱验证码") — was: self.log("Waiting for the email verification code")
            otp = self.otp_callback()
            if not otp:
                _raise_keyed(RuntimeError, "cursor.13939cce")
                # was: raise RuntimeError("未获取到验证码") — was: raise RuntimeError("Failed to obtain verification code")
            self.log_key("cursor.8f3b2133", otp=otp)
            # was: self.log(f"验证码: {otp}") — was: self.log(f"Verification code: {otp}")

            # WorkOS 6格子 OTP：点击第一个格子然后逐键输入 — WorkOS 6-box OTP: click the first box, then type each digit in sequence
            try:
                otp_input.click()
                time.sleep(0.3)
            except Exception:
                pass
            for digit in str(otp).strip():
                page.keyboard.press(digit)
                time.sleep(random.uniform(0.08, 0.2))
            time.sleep(1)
            # WorkOS 自动提交，无需点 Continue；如果没提交就按 Enter — WorkOS auto-submits, no need to click Continue; press Enter if it didn't submit
            if "email-verification" in page.url:
                page.keyboard.press("Enter")
            time.sleep(5)

            # 等待 Session Token — Wait for the session token
            self.log_key("cursor.e13519e0")
            # was: self.log("等待 WorkosCursorSessionToken") — was: self.log("Waiting for WorkosCursorSessionToken")
            tok = _wait_for_token(page, timeout=60)
            if not tok:
                _raise_keyed(RuntimeError, "cursor.93470dc0")
                # was: raise RuntimeError("未获取到 WorkosCursorSessionToken") — was: raise RuntimeError("Failed to obtain WorkosCursorSessionToken")

            from platforms.cursor.switch import get_cursor_user_info
            user_info = get_cursor_user_info(tok) or {}
            resolved_email = user_info.get("email", email)
            self.log_key("cursor.f5afbbc0", resolved_email=resolved_email)
            # was: self.log(f"注册成功: {resolved_email}") — was: self.log(f"Registration succeeded: {resolved_email}")
            return {"email": resolved_email, "password": "", "token": tok}
