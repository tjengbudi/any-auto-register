"""ChatGPT 浏览器注册流程（Camoufox）。 — ChatGPT browser registration flow (Camoufox)."""
import base64
import json
import random
import re
import secrets
import time
import uuid
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

from camoufox.sync_api import Camoufox

from i18n import t
from platforms.chatgpt._i18n_helpers import _emit_log_key, _raise_keyed

from .constants import (
    OPENAI_AUTH,
    CHATGPT_APP,
    PLATFORM_LOGIN_ENTRY,
    SENTINEL_SDK_URL,
    SENTINEL_REQ_URL,
    SENTINEL_FRAME_URL,
    SENTINEL_BASE,
    OAUTH_CONSENT_FORM_SELECTOR,
)

EMAIL_INPUT_SELECTORS = [
    'input#login-email',
    'input[type="email"]',
    'input[name="email"]',
    'input[name="username"]',
    'input[autocomplete="username"]',
    'input[autocomplete*="username"]',
    'input[inputmode="email"]',
    'input[id*="email"]',
]

PASSWORD_INPUT_SELECTORS = [
    'input[type="password"]',
    'input[name="password"]',
    'input[autocomplete="new-password"]',
]

EMAIL_SUBMIT_SELECTORS = [
    'button[type="submit"]',
    'button[data-testid="continue-button"]',
    'button:has-text("Continue")',
    'button:has-text("continue")',
    'button:has-text("Next")',
    'button:has-text("next")',
]

PASSWORD_SUBMIT_SELECTORS = [
    'button[type="submit"]',
    'button[data-testid="continue-button"]',
    'button:has-text("Continue")',
    'button:has-text("continue")',
    'button:has-text("Sign up")',
    'button:has-text("sign up")',
    'button:has-text("Create account")',
    'button:has-text("create account")',
]

OTP_INPUT_SELECTORS = [
    "input[inputmode='numeric']",
    "input[autocomplete='one-time-code']",
    "input[type='tel']",
    "input[type='number']",
    "input[name*='code' i]",
    "input[id*='code' i]",
]

SIGNUP_RECOVERY_SELECTORS = [
    'a:has-text("Sign up")',
    'button:has-text("Sign up")',
    'a:has-text("sign up")',
    'button:has-text("sign up")',
    'a:has-text("Register")',
    'button:has-text("Register")',
    'a:has-text("Create account")',
    'button:has-text("Create account")',
    'a:has-text("创建账号")',
    'button:has-text("创建账号")',
    'a:has-text("注册")',
    'button:has-text("注册")',
]

PASSWORDLESS_LOGIN_SELECTORS = [
    'button[name="intent"][value="passwordless_login_send_otp"]',
    'button[value="passwordless_login_send_otp"]',
    'button:has-text("one-time code")',
    'button:has-text("one time code")',
    'button:has-text("passwordless")',
    'button:has-text("一次性验证码")',
    'button:has-text("驗證碼")',
    'button:has-text("验证码")',
    'button:has-text("código único")',
    'button:has-text("code unique")',
    'button:has-text("Einmalcode")',
    'button:has-text("código de uso único")',
]

# add-phone 页面国际拨号码 -> 国家名映射（用于 UI 下拉选择） —
# add-phone page international dial code -> country name mapping (for UI dropdown selection)
PHONE_COUNTRY_CODE_MAP = {
    "1": "United States", "7": "Russia", "20": "Egypt", "27": "South Africa",
    "30": "Greece", "31": "Netherlands", "32": "Belgium", "33": "France",
    "34": "Spain", "36": "Hungary", "39": "Italy", "40": "Romania",
    "44": "United Kingdom", "45": "Denmark", "46": "Sweden", "47": "Norway",
    "48": "Poland", "49": "Germany", "51": "Peru", "52": "Mexico",
    "53": "Cuba", "54": "Argentina", "55": "Brazil", "56": "Chile",
    "57": "Colombia", "58": "Venezuela", "60": "Malaysia", "61": "Australia",
    "62": "Indonesia", "63": "Philippines", "64": "New Zealand",
    "65": "Singapore", "66": "Thailand", "81": "Japan", "82": "South Korea",
    "84": "Vietnam", "86": "China", "90": "Turkey", "91": "India",
    "92": "Pakistan", "93": "Afghanistan", "94": "Sri Lanka", "95": "Myanmar",
    "98": "Iran", "212": "Morocco", "213": "Algeria", "216": "Tunisia",
    "218": "Libya", "220": "Gambia", "221": "Senegal", "234": "Nigeria",
    "254": "Kenya", "255": "Tanzania", "256": "Uganda", "260": "Zambia",
    "263": "Zimbabwe", "351": "Portugal", "353": "Ireland", "354": "Iceland",
    "358": "Finland", "370": "Lithuania", "371": "Latvia", "372": "Estonia",
    "374": "Armenia", "375": "Belarus", "380": "Ukraine", "381": "Serbia",
    "385": "Croatia", "420": "Czech Republic", "421": "Slovakia",
    "855": "Cambodia", "856": "Laos", "880": "Bangladesh", "886": "Taiwan",
    "960": "Maldives", "966": "Saudi Arabia", "971": "United Arab Emirates",
    "972": "Israel", "977": "Nepal", "992": "Tajikistan",
    "993": "Turkmenistan", "994": "Azerbaijan", "995": "Georgia",
    "996": "Kyrgyzstan", "998": "Uzbekistan",
}

# 拨号码 -> ISO 3166-1 alpha-2 国家代码（用于 React Aria <select> 的 value 匹配） —
# dial code -> ISO 3166-1 alpha-2 country code (for matching React Aria <select> values)
PHONE_DIAL_TO_ISO = {
    "1": "US", "7": "RU", "20": "EG", "27": "ZA",
    "30": "GR", "31": "NL", "32": "BE", "33": "FR",
    "34": "ES", "36": "HU", "39": "IT", "40": "RO",
    "44": "GB", "45": "DK", "46": "SE", "47": "NO",
    "48": "PL", "49": "DE", "51": "PE", "52": "MX",
    "53": "CU", "54": "AR", "55": "BR", "56": "CL",
    "57": "CO", "58": "VE", "60": "MY", "61": "AU",
    "62": "ID", "63": "PH", "64": "NZ",
    "65": "SG", "66": "TH", "81": "JP", "82": "KR",
    "84": "VN", "86": "CN", "90": "TR", "91": "IN",
    "92": "PK", "93": "AF", "94": "LK", "95": "MM",
    "98": "IR", "212": "MA", "213": "DZ", "216": "TN",
    "218": "LY", "220": "GM", "221": "SN", "234": "NG",
    "254": "KE", "255": "TZ", "256": "UG", "260": "ZM",
    "263": "ZW", "351": "PT", "353": "IE", "354": "IS",
    "358": "FI", "370": "LT", "371": "LV", "372": "EE",
    "374": "AM", "375": "BY", "380": "UA", "381": "RS",
    "385": "HR", "420": "CZ", "421": "SK",
    "855": "KH", "856": "LA", "880": "BD", "886": "TW",
    "960": "MV", "966": "SA", "971": "AE",
    "972": "IL", "977": "NP", "992": "TJ",
    "993": "TM", "994": "AZ", "995": "GE",
    "996": "KG", "998": "UZ",
}

PHONE_INPUT_SELECTORS = [
    'input[type="tel"]',
    'input[name="phone"]',
    'input[name="phone_number"]',
    'input[name="phoneNumber"]',
    'input[id*="phone" i]',
    'input[placeholder*="phone" i]',
    'input[autocomplete="tel"]',
    'input[autocomplete="tel-national"]',
]

PHONE_SEND_SELECTORS = [
    'button:has-text("Send code via SMS")',
    'button:has-text("Send code")',
    'button:has-text("Send via SMS")',
    'button:has-text("Send link via SMS")',
    'button:has-text("Send")',
    'button[type="submit"]',
    'button:has-text("Continue")',
    'button:has-text("continue")',
    'button:has-text("发送")',
]

PHONE_VERIFY_SELECTORS = [
    'button:has-text("Verify")',
    'button:has-text("verify")',
    'button:has-text("Check")',
    'button[type="submit"]',
    'button:has-text("Continue")',
    'button:has-text("continue")',
    'button:has-text("验证")',
    'button:has-text("确认")',
]


def _parse_phone_country_and_local(phone_number: str) -> tuple[str, str, str]:
    """从完整手机号解析出 (拨号码, 本地号码, 国家名)。

    例: +66959075673 -> ("66", "959075673", "Thailand")

    Parse (dial code, local number, country name) from a full phone number.

    Example: +66959075673 -> ("66", "959075673", "Thailand")
    """
    num = str(phone_number or "").lstrip("+").strip()
    for length in (3, 2, 1):
        if length > len(num):
            continue
        prefix = num[:length]
        if prefix in PHONE_COUNTRY_CODE_MAP:
            return prefix, num[length:], PHONE_COUNTRY_CODE_MAP[prefix]
    return "", num, ""


def _select_phone_country_ui(page, dial_code: str, country_name: str, log, log_key: Optional[Callable[[str, dict], None]] = None) -> bool:
    """在 add-phone 页面的国家下拉框中选择对应国家。

    OpenAI add-phone 页面使用 React Aria Select 组件，底层有一个隐藏的原生 <select>
    和一个可视的 button trigger + listbox 弹出层。

    Select the matching country in the add-phone page's country dropdown.

    The OpenAI add-phone page uses a React Aria Select component: a hidden
    native <select> underneath, plus a visible button trigger and listbox
    popup on top.
    """
    if not dial_code and not country_name:
        _emit_log_key(log, log_key, "chatgpt.814efd3f")
        # was: log("  无法识别国家码，跳过国家选择") — was: log("  Could not identify country code, skipping country selection")
        return False

    iso_code = PHONE_DIAL_TO_ISO.get(dial_code, "")
    _emit_log_key(log, log_key, "chatgpt.2d5ea266", country_name=country_name, dial_code=dial_code, iso_code=iso_code)
    # was: log(f"  目标国家: {country_name} (+{dial_code}) ISO={iso_code}") — was: log(f"  Target country: {country_name} (+{dial_code}) ISO={iso_code}")

    # 先检查当前下拉框是否已经是目标国家 — Check first whether the dropdown already shows the target country
    dial_pattern = f"(+{dial_code})"
    already = page.evaluate(
        """
        (dialPattern) => {
          const visible = (el) => {
            if (!el) return false;
            const s = window.getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return s && s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
          };
          const all = Array.from(document.querySelectorAll('button, div, span, a, [role="button"], [role="combobox"], select'));
          for (const el of all) {
            if (!visible(el)) continue;
            const text = (el.innerText || el.textContent || '').trim();
            if (text.includes(dialPattern) && text.length < 80) return true;
          }
          return false;
        }
        """,
        dial_pattern,
    )
    if already:
        _emit_log_key(log, log_key, "chatgpt.a18d1fbf", dial_code=dial_code)
        # was: log(f"  国家已是目标值: (+{dial_code})") — was: log(f"  Country is already the target value: (+{dial_code})")
        return True

    # ═══════════════════════════════════════════════════════════════════
    # 策略 1: 通过底层原生 <select> 直接设置值（最可靠）
    # React Aria Select 底层会有一个隐藏的 <select> 用于表单提交和无障碍。
    # 直接修改它的值并触发 change 事件可以同步 React 状态。
    # Strategy 1: set the value directly via the underlying native <select> (most reliable).
    # React Aria Select has a hidden native <select> underneath for form submission and
    # accessibility; modifying its value and firing a change event syncs React's state.
    # ═══════════════════════════════════════════════════════════════════
    native_selected = page.evaluate(
        """
        ({ isoCode, dialCode, countryName }) => {
          const selects = document.querySelectorAll('select');
          for (const sel of selects) {
            if (sel.options.length < 10) continue;  // 排除非国家的 select

            // 尝试多种匹配策略找到目标 option
            let targetValue = null;
            for (const opt of sel.options) {
              const v = (opt.value || '').trim();
              const t = (opt.text || opt.label || '').trim();
              // 匹配 ISO 代码 (如 "TH")
              if (isoCode && v === isoCode) { targetValue = v; break; }
              // 匹配拨号码 (如 value 包含 "66" 或 text 包含 "+66")
              if (t.includes('(+' + dialCode + ')')) { targetValue = v; break; }
              if (t.includes(countryName)) { targetValue = v; break; }
            }

            if (targetValue !== null) {
              // 使用 React 兼容的方式设置值
              const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLSelectElement.prototype, 'value'
              )?.set;
              if (nativeInputValueSetter) {
                nativeInputValueSetter.call(sel, targetValue);
              } else {
                sel.value = targetValue;
              }
              sel.dispatchEvent(new Event('change', { bubbles: true }));
              sel.dispatchEvent(new Event('input', { bubbles: true }));
              return { ok: true, value: targetValue, method: 'native_setter' };
            }
          }
          return { ok: false };
        }
        """,
        {"isoCode": iso_code, "dialCode": dial_code, "countryName": country_name},
    )
    if native_selected and native_selected.get("ok"):
        _emit_log_key(log, log_key, "chatgpt.637d261b", value=native_selected.get('value'))
        # was: log(f"  ✓ 通过原生 <select> 选择成功: value={native_selected.get('value')}") —
        # was: log(f"  ✓ Selected successfully via the native <select>: value={native_selected.get('value')}")
        time.sleep(0.5)
        # 验证 UI 是否同步更新 — Verify whether the UI updated in sync
        verify = page.evaluate(
            "(dp) => { const b = document.querySelector('button[aria-haspopup=\"listbox\"]'); return b ? (b.innerText || '').trim() : ''; }",
            dial_pattern,
        )
        if f"+{dial_code}" in (verify or ""):
            _emit_log_key(log, log_key, "chatgpt.0a9b0d89", verify=verify)
            # was: log(f"  ✓ UI 已同步: {verify}") — was: log(f"  ✓ UI is in sync: {verify}")
            return True
        _emit_log_key(log, log_key, "chatgpt.29bc148a", verify=verify)
        # was: log(f"  原生 select 已设置但 UI 未同步 ({verify})，尝试 UI 交互...") —
        # was: log(f"  Native select was set but UI didn't sync ({verify}), trying UI interaction...")

    # ═══════════════════════════════════════════════════════════════════
    # 策略 2: 通过 React Aria 的 key 属性直接操作
    # Strategy 2: operate directly via React Aria's key attribute
    # ═══════════════════════════════════════════════════════════════════
    key_selected = page.evaluate(
        """
        ({ isoCode, dialCode, countryName }) => {
          // 找到 React Aria Select 的隐藏 <select> 并通过 selectOption 模拟
          const selects = document.querySelectorAll('select');
          for (const sel of selects) {
            if (sel.options.length < 10) continue;
            for (const opt of sel.options) {
              const v = (opt.value || '').trim();
              const t = (opt.text || opt.label || '').trim();
              if ((isoCode && v === isoCode) || t.includes('(+' + dialCode + ')') || t.includes(countryName)) {
                sel.value = v;
                // 触发 React 合成事件
                const ev = new Event('change', { bubbles: true });
                Object.defineProperty(ev, 'target', { writable: false, value: sel });
                sel.dispatchEvent(ev);
                return { ok: true, value: v, text: t };
              }
            }
          }
          return { ok: false };
        }
        """,
        {"isoCode": iso_code, "dialCode": dial_code, "countryName": country_name},
    )

    # ═══════════════════════════════════════════════════════════════════
    # 策略 3: 使用 Playwright 的 selectOption API（对原生 select 最可靠）
    # Strategy 3: use Playwright's selectOption API (most reliable for native select)
    # ═══════════════════════════════════════════════════════════════════
    try:
        select_el = page.query_selector("select")
        if select_el:
            # 尝试用 ISO 代码选择 — Try selecting by ISO code
            if iso_code:
                try:
                    select_el.select_option(value=iso_code)
                    _emit_log_key(log, log_key, "chatgpt.350b0dae", iso_code=iso_code)
                    # was: log(f"  ✓ Playwright selectOption(value={iso_code}) 成功") — was: log(f"  ✓ Playwright selectOption(value={iso_code}) succeeded")
                    time.sleep(0.5)
                    return True
                except Exception:
                    pass
            # 尝试用 label 匹配（包含国家名或拨号码） — Try matching by label (containing country name or dial code)
            try:
                # 获取所有 option 的 value 和 text，找到匹配的 — Get all option values and texts to find a match
                match_value = page.evaluate(
                    """
                    ({ dialCode, countryName }) => {
                      const sel = document.querySelector('select');
                      if (!sel) return '';
                      for (const opt of sel.options) {
                        const t = (opt.text || opt.label || '').trim();
                        const v = (opt.value || '').trim();
                        if (t.includes('(+' + dialCode + ')') || t.includes(countryName)) return v;
                      }
                      return '';
                    }
                    """,
                    {"dialCode": dial_code, "countryName": country_name},
                )
                if match_value:
                    select_el.select_option(value=match_value)
                    _emit_log_key(log, log_key, "chatgpt.00d39a57", match_value=match_value)
                    # was: log(f"  ✓ Playwright selectOption(value={match_value}) 成功") — was: log(f"  ✓ Playwright selectOption(value={match_value}) succeeded")
                    time.sleep(0.5)
                    return True
            except Exception as e:
                _emit_log_key(log, log_key, "chatgpt.20f1525a", e=e)
                # was: log(f"  selectOption label 匹配失败: {e}") — was: log(f"  selectOption label match failed: {e}")
    except Exception as e:
        _emit_log_key(log, log_key, "chatgpt.e7f720d7", e=e)
        # was: log(f"  Playwright selectOption 策略失败: {e}") — was: log(f"  Playwright selectOption strategy failed: {e}")

    # ═══════════════════════════════════════════════════════════════════
    # 策略 4: 点击 trigger 按钮打开 listbox，然后在 listbox 中选择
    # Strategy 4: click the trigger button to open the listbox, then select within it
    # ═══════════════════════════════════════════════════════════════════
    trigger = None
    for sel in [
        'button[aria-haspopup="listbox"]',
        '.react-aria-Select button',
        'button[class*="select" i]',
        'button[class*="country" i]',
    ]:
        trigger = page.query_selector(sel)
        if trigger:
            break

    if not trigger:
        trigger = page.evaluate(
            r"""
            () => {
              const pattern = /\(\+\d{1,4}\)/;
              const all = document.querySelectorAll('button, [role="button"], [role="combobox"]');
              for (const el of all) {
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) continue;
                const text = (el.innerText || '').trim();
                if (pattern.test(text)) {
                  el.scrollIntoView({ block: 'center' });
                  el.click();
                  return true;
                }
              }
              return false;
            }
            """,
        )
        if not trigger:
            _emit_log_key(log, log_key, "chatgpt.1a97a00b")
            # was: log("  ⚠️ 未找到国家选择器触发按钮") — was: log("  ⚠️ Country selector trigger button not found")
            return False
        _emit_log_key(log, log_key, "chatgpt.edc586ff")
        # was: log("  已通过 JS 点击触发按钮") — was: log("  Clicked the trigger button via JS")
    else:
        trigger.scroll_into_view_if_needed()
        trigger.click()
        _emit_log_key(log, log_key, "chatgpt.7cf94fd9")
        # was: log("  已点击国家选择器下拉框") — was: log("  Clicked the country selector dropdown")

    time.sleep(0.8)

    # 等待 listbox 出现 — Wait for the listbox to appear
    listbox = None
    for _ in range(10):
        listbox = page.query_selector('[role="listbox"]')
        if listbox:
            break
        time.sleep(0.3)

    if not listbox:
        _emit_log_key(log, log_key, "chatgpt.f897b7cf")
        # was: log("  ⚠️ 下拉框 listbox 未出现") — was: log("  ⚠️ Dropdown listbox did not appear")
        return False

    _emit_log_key(log, log_key, "chatgpt.0283a45e")
    # was: log("  listbox 已出现") — was: log("  listbox has appeared")

    # 在 listbox 中查找并点击目标 option — Find and click the target option within the listbox
    option = None
    if iso_code:
        for attr in ["data-key", "data-value", "value", "id"]:
            # 尝试精确匹配和包含匹配 — Try exact match and substring match
            option = page.query_selector(f'[role="option"][{attr}="{iso_code}"]')
            if not option:
                option = page.query_selector(f'[role="option"][{attr}*="{iso_code}"]')
            if option:
                _emit_log_key(log, log_key, "chatgpt.a5c5cbaf", attr=attr, iso_code=iso_code)
                # was: log(f"  找到 option: [{attr} 含 {iso_code}]") — was: log(f"  Found option: [{attr} contains {iso_code}]")
                break

    if not option:
        option_idx = page.evaluate(
            """
            ({ countryName, dialCode }) => {
              const options = document.querySelectorAll('[role="option"]');
              for (let i = 0; i < options.length; i++) {
                const text = (options[i].innerText || options[i].textContent || '').trim();
                if (text.includes(countryName) || text.includes('(+' + dialCode + ')') || text.includes('+' + dialCode)) {
                  return i;
                }
              }
              // 宽松匹配：只匹配拨号码数字
              for (let i = 0; i < options.length; i++) {
                const text = (options[i].innerText || options[i].textContent || '').trim();
                if (text.includes(dialCode)) {
                  return i;
                }
              }
              return -1;
            }
            """,
            {"countryName": country_name, "dialCode": dial_code},
        )
        if option_idx >= 0:
            options = page.query_selector_all('[role="option"]')
            if option_idx < len(options):
                option = options[option_idx]
                _emit_log_key(log, log_key, "chatgpt.f82635a3", option_idx=option_idx)
                # was: log(f"  找到 option: 文本匹配 index={option_idx}") — was: log(f"  Found option: text match index={option_idx}")

    if option:
        option.scroll_into_view_if_needed()
        option.click()
        time.sleep(0.5)
        new_text = page.evaluate(
            """() => {
              const btn = document.querySelector('button[aria-haspopup="listbox"]') ||
                          document.querySelector('.react-aria-Select button');
              return btn ? (btn.innerText || '').trim() : '';
            }""",
        )
        _emit_log_key(log, log_key, "chatgpt.038dbb02", new_text=new_text)
        # was: log(f"  选择后下拉框显示: {new_text}") — was: log(f"  Dropdown shows after selection: {new_text}")
        if f"+{dial_code}" in (new_text or ""):
            _emit_log_key(log, log_key, "chatgpt.7c783696", new_text=new_text)
            # was: log(f"  ✓ 国家选择成功: {new_text}") — was: log(f"  ✓ Country selection succeeded: {new_text}")
            return True

    # 键盘 type-ahead 搜索 — Keyboard type-ahead search
    _emit_log_key(log, log_key, "chatgpt.8ac9bee0", country_name=country_name)
    # was: log(f"  尝试键盘 type-ahead: {country_name}") — was: log(f"  Trying keyboard type-ahead: {country_name}")
    page.keyboard.type(country_name, delay=80)
    time.sleep(0.8)

    # 按 Enter 确认选择 — Press Enter to confirm the selection
    page.keyboard.press("Enter")
    time.sleep(0.5)

    # 验证 — Verify
    final_text = page.evaluate(
        """() => {
          const btn = document.querySelector('button[aria-haspopup="listbox"]') ||
                      document.querySelector('.react-aria-Select button');
          return btn ? (btn.innerText || '').trim() : '';
        }""",
    )
    if f"+{dial_code}" in (final_text or ""):
        _emit_log_key(log, log_key, "chatgpt.ed81fa32", final_text=final_text)
        # was: log(f"  ✓ type-ahead 选择成功: {final_text}") — was: log(f"  ✓ type-ahead selection succeeded: {final_text}")
        return True

    _emit_log_key(log, log_key, "chatgpt.0cf274d6", country_name=country_name, dial_code=dial_code)
    # was: log(f"  ⚠️ 下拉框已展开但未找到匹配国家: {country_name} (+{dial_code})") —
    # was: log(f"  ⚠️ Dropdown is open but no matching country was found: {country_name} (+{dial_code})")
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    return False


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


def _find_first_selector(page, selectors: list[str]) -> str | None:
    for sel in selectors:
        try:
            node = page.query_selector(sel)
        except Exception:
            node = None
        if node:
            return sel
    return None


def _wait_for_any_selector(page, selectors: list[str], timeout: int = 30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = _find_first_selector(page, selectors)
        if found:
            return found
        time.sleep(0.5)
    return None


def _click_first(page, selectors: list[str], *, timeout: int = 10) -> str | None:
    found = _wait_for_any_selector(page, selectors, timeout=timeout)
    if not found:
        return None
    try:
        page.click(found)
        return found
    except Exception:
        return None


def _is_login_password_url(url: str) -> bool:
    return bool(re.search(r"(?:auth|accounts)\.openai\.com/.*log-?in/password", str(url or ""), flags=re.I))


def _build_manual_flow_state(page_type: str, current_url: str) -> dict:
    state = _extract_flow_state(None, current_url)
    state["page_type"] = page_type
    state["current_url"] = current_url
    return state


def _get_visible_page_text(page) -> str:
    try:
        return str(page.evaluate("() => document.body?.innerText || ''") or "")
    except Exception:
        return ""


def _has_signup_registration_choice(page) -> bool:
    if not _is_login_password_url(str(page.url or "")):
        return False
    if _find_first_selector(page, SIGNUP_RECOVERY_SELECTORS):
        return True
    text = _get_visible_page_text(page)
    return bool(re.search(r"sign\s*up|register|create\s*account|还没有帐户|还没有账户|請註冊|请注册|去注册|注册", text, flags=re.I))


def _click_passwordless_login_if_available(page, log, log_key: Optional[Callable[[str, dict], None]] = None, *, context: str) -> bool:
    selector = _click_first(page, PASSWORDLESS_LOGIN_SELECTORS, timeout=1)
    if selector:
        _emit_log_key(log, log_key, "chatgpt.1cc33861", context=context, selector=selector)
        # was: log(f"{context} 已选择一次性验证码登录: {selector}") — was: log(f"{context} selected one-time-code login: {selector}")
        time.sleep(1)
        return True
    try:
        clicked = bool(
            page.evaluate(
                """
                () => {
                  const nodes = Array.from(document.querySelectorAll('button, [role="button"], a'));
                  const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                  };
                  const target = nodes.find((el) => {
                    const text = String(el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                    return visible(el) && /使用一次性验证码登录|使用一次性驗證碼登入|one-time code|one time code|passwordless/i.test(text);
                  });
                  if (!target) return false;
                  target.click();
                  return true;
                }
                """
            )
        )
    except Exception:
        clicked = False
    if clicked:
        _emit_log_key(log, log_key, "chatgpt.5708f22e", context=context)
        # was: log(f"{context} 已选择一次性验证码登录") — was: log(f"{context} selected one-time-code login")
        time.sleep(1)
    return clicked


def _get_page_oauth_url(page) -> str:
    try:
        return str(
            page.evaluate(
                """
                () => {
                  const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                  };
                  const anchors = Array.from(document.querySelectorAll('a[href*="/api/oauth/authorize"]'));
                  const anchor = anchors.find((el) => visible(el));
                  return anchor ? String(anchor.href || anchor.getAttribute('href') || '') : '';
                }
                """
            )
            or ""
        ).strip()
    except Exception:
        return ""


def _oauth_url_matches_state(url: str, state: str) -> bool:
    if not url or not state:
        return False
    return f"state={state}" in url or f"state%3D{state}" in url


def _extract_auth_error_text(page) -> str:
    selectors = [
        "text=Failed to create account",
        "text=Sorry, we cannot create your account",
        "text=Please try again",
        "text=Invalid code",
        "text=Enter a valid age to continue",
        "text=doesn't look right",
        "[role='alert']",
        ".error, [class*='error'], [class*='Error']",
    ]
    for selector in selectors:
        try:
            text = str(page.locator(selector).first.text_content(timeout=350) or "").strip()
        except Exception:
            text = ""
        if text and "oai_log" not in text and "SSR_HTML" not in text:
            return text
    return ""


def _fill_input_like_user(page, selector: str, value: str) -> bool:
    try:
        locator = page.locator(selector).first
        locator.wait_for(state="visible", timeout=2000)
        current = str(locator.input_value() or "").strip()
        if current == str(value).strip():
            return True
        locator.click(timeout=1500)
        _browser_pause(page)
        try:
            locator.fill("")
        except Exception:
            pass
        _browser_pause(page, headed=False)
        try:
            locator.type(value, delay=random.randint(35, 85))
        except Exception:
            try:
                page.fill(selector, value)
            except Exception:
                return False
        final_value = str(locator.input_value() or "").strip()
        if final_value == str(value):
            return True
    except Exception:
        pass

    try:
        ok = page.evaluate(
            """
            ({ selector, value }) => {
              const input = document.querySelector(selector);
              if (!input) return false;
              const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
              if (!setter) return false;
              setter.call(input, value);
              input.dispatchEvent(new Event('input', { bubbles: true }));
              input.dispatchEvent(new Event('change', { bubbles: true }));
              return String(input.value || '') === String(value || '');
            }
            """,
            {"selector": selector, "value": value},
        )
        return bool(ok)
    except Exception:
        return False


def _submit_form_with_fallback(page, input_selector: str) -> bool:
    try:
        return bool(
            page.evaluate(
                """
                (selector) => {
                  const input = document.querySelector(selector);
                  if (!input) return false;
                  const form = input.form || input.closest?.('form');
                  if (form?.requestSubmit) {
                    form.requestSubmit();
                    return true;
                  }
                  if (form?.submit) {
                    form.submit();
                    return true;
                  }
                  input.focus?.();
                  for (const type of ['keydown', 'keypress', 'keyup']) {
                    input.dispatchEvent(new KeyboardEvent(type, {
                      key: 'Enter',
                      code: 'Enter',
                      bubbles: true,
                      cancelable: true,
                    }));
                  }
                  return true;
                }
                """,
                input_selector,
            )
        )
    except Exception:
        return False


def _sync_hidden_birthday_input(page, birthdate: str, log, log_key: Optional[Callable[[str, dict], None]] = None) -> bool:
    try:
        synced = bool(
            page.evaluate(
                """
                (value) => {
                  const input = document.querySelector("input[name='birthday']");
                  if (!input) return false;
                  input.value = value;
                  input.dispatchEvent(new Event('input', { bubbles: true }));
                  input.dispatchEvent(new Event('change', { bubbles: true }));
                  return String(input.value || '') === String(value || '');
                }
                """,
                birthdate,
            )
        )
    except Exception:
        synced = False
    if synced:
        _emit_log_key(log, log_key, "chatgpt.b8da85bb", birthdate=birthdate)
        # was: log(f"about_you 已同步隐藏 birthday: {birthdate}") — was: log(f"about_you synced the hidden birthday field: {birthdate}")
    return synced


def _collect_visible_text_inputs(page) -> list[dict]:
    try:
        inputs = page.evaluate(
            """
            () => {
              const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
              const nodes = Array.from(document.querySelectorAll("input:not([type='hidden']):not([disabled]):not([readonly])"));
              const visible = nodes.filter((el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style
                  && style.display !== 'none'
                  && style.visibility !== 'hidden'
                  && rect.width > 0
                  && rect.height > 0;
              });
              return visible.map((el, visibleIndex) => {
                const explicitLabels = Array.from(document.querySelectorAll('label'))
                  .filter((label) => String(label.getAttribute('for') || '') === String(el.id || ''))
                  .map((label) => normalize(label.textContent));
                const wrappedLabel = normalize(el.closest('label')?.textContent || '');
                const ariaLabel = normalize(el.getAttribute('aria-label'));
                const labelledByText = normalize(
                  String(el.getAttribute('aria-labelledby') || '')
                    .split(/\\s+/)
                    .filter(Boolean)
                    .map((id) => normalize(document.getElementById(id)?.textContent || ''))
                    .join(' ')
                );
                const parentText = normalize(el.parentElement?.textContent || '');
                return {
                  visibleIndex,
                  type: normalize(el.getAttribute('type') || el.type || ''),
                  name: normalize(el.getAttribute('name') || ''),
                  id: normalize(el.id || ''),
                  placeholder: normalize(el.getAttribute('placeholder') || ''),
                  ariaLabel,
                  labels: explicitLabels.filter(Boolean),
                  wrappedLabel,
                  labelledByText,
                  parentText,
                };
              });
            }
            """
        ) or []
    except Exception:
        inputs = []
    return [item for item in inputs if isinstance(item, dict)]


def _about_you_input_hints(entry: dict) -> str:
    parts: list[str] = []
    labels = entry.get("labels") or []
    if isinstance(labels, list):
        parts.extend(str(item or "") for item in labels)
    parts.extend(
        [
            str(entry.get("wrappedLabel") or ""),
            str(entry.get("labelledByText") or ""),
            str(entry.get("ariaLabel") or ""),
            str(entry.get("placeholder") or ""),
            str(entry.get("name") or ""),
            str(entry.get("id") or ""),
            str(entry.get("parentText") or ""),
        ]
    )
    return " ".join(part for part in parts if part).strip().lower()


def _pick_best_about_you_input(entries: list[dict], field: str, exclude_visible_indices: set[int] | None = None) -> dict | None:
    exclude = {int(value) for value in (exclude_visible_indices or set())}
    best_entry = None
    best_score = float("-inf")
    for entry in entries:
        try:
            visible_index = int(entry.get("visibleIndex"))
        except Exception:
            continue
        if visible_index in exclude:
            continue
        hints = _about_you_input_hints(entry)
        if not hints:
            continue

        score = 0
        if field == "name":
            if any(token in hints for token in ("full name", "fullname", "全名", "姓名", "nombre completo", "nom complet", "vollständiger name", "nome completo")):
                score += 10
            if any(token in hints for token in (" name ", "name", "autocomplete=name", "nombre", "nom", "nome")):
                score += 3
            if any(token in hints for token in ("age", "年龄", "edad", "âge", "alter", "idade", "birthday", "birth", "date of birth", "出生", "生日")):
                score -= 8
        elif field == "age":
            if any(token in hints for token in ("age", "年龄", "how old", "edad", "âge", "alter", "idade", "나이")):
                score += 10
            if any(token in hints for token in ("full name", "fullname", "全名", "姓名", "nombre completo", "nom complet")):
                score -= 10
            if "name" in hints and "age" not in hints and "年龄" not in hints and "edad" not in hints:
                score -= 6
            if any(token in hints for token in ("birthday", "birth", "date of birth", "出生", "生日", "fecha de nacimiento", "nascimento")):
                score -= 3
        else:
            continue

        if score > best_score:
            best_score = score
            best_entry = entry

    if best_score > 0:
        return best_entry

    if field == "age" and len(entries) == 2:
        ordered = []
        for entry in entries:
            try:
                visible_index = int(entry.get("visibleIndex"))
            except Exception:
                continue
            if visible_index not in exclude:
                ordered.append(entry)
        if len(ordered) == 1:
            return ordered[0]
        if len(ordered) == 2:
            return ordered[1]
    return None


def _derive_registration_state_from_page(page) -> dict:
    current_url = str(page.url or "")
    state = _extract_flow_state(None, current_url)
    if state.get("page_type"):
        return state

    if _find_first_selector(page, PASSWORD_INPUT_SELECTORS):
        page_type = "login_password" if _is_login_password_url(current_url) else "create_account_password"
        return _build_manual_flow_state(page_type, current_url)

    otp_selector = _find_first_selector(page, OTP_INPUT_SELECTORS)
    if otp_selector and "password" not in otp_selector:
        return _build_manual_flow_state("email_otp_verification", current_url)

    try:
        about_visible = bool(
            page.evaluate(
                """
                () => {
                  const inputs = Array.from(document.querySelectorAll("input:not([type='hidden'])"));
                  const text = String(document.body?.innerText || '').toLowerCase();
                  const hasName = inputs.some((el) => {
                    const hint = `${el.name || ''} ${el.id || ''} ${el.placeholder || ''}`.toLowerCase();
                    return hint.includes('name') || hint.includes('姓名') || hint.includes('全名');
                  });
                  const hasAgeOrBirth = inputs.some((el) => {
                    const hint = `${el.name || ''} ${el.id || ''} ${el.placeholder || ''}`.toLowerCase();
                    return hint.includes('age') || hint.includes('birth') || hint.includes('birthday') || hint.includes('年龄') || hint.includes('生日');
                  });
                  return (hasName && hasAgeOrBirth) || text.includes('about you');
                }
                """
            )
        )
    except Exception:
        about_visible = False
    if about_visible:
        return _build_manual_flow_state("about_you", current_url)

    return state


def _recover_signup_password_page(page, log, log_key: Optional[Callable[[str, dict], None]] = None) -> bool:
    if not _is_login_password_url(str(page.url or "")):
        return False
    if not _has_signup_registration_choice(page):
        return False
    selector = _click_first(page, SIGNUP_RECOVERY_SELECTORS, timeout=2)
    if not selector:
        return False
    _emit_log_key(log, log_key, "chatgpt.bc8dd545", selector=selector)
    # was: log(f"密码页落到登录态，尝试点击注册入口恢复: {selector}") —
    # was: log(f"Password page landed on the login state, trying to recover via the signup entry: {selector}")
    time.sleep(1.2)
    return True


def _wait_for_signup_entry_transition(page, log, log_key: Optional[Callable[[str, dict], None]] = None, timeout: int = 20) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _click_passwordless_login_if_available(page, log, log_key, context="邮箱页提交后"):
            time.sleep(0.5)
            continue
        state = _derive_registration_state_from_page(page)
        if state.get("page_type") in {
            "create_account_password",
            "login_password",
            "email_otp_verification",
            "about_you",
            "add_phone",
            "chatgpt_home",
            "oauth_callback",
        }:
            if state.get("page_type") == "login_password" and _recover_signup_password_page(page, log, log_key):
                return _derive_registration_state_from_page(page)
            return state
        error_text = _extract_auth_error_text(page)
        if error_text:
            _raise_keyed(RuntimeError, "chatgpt.544304c8", val=error_text[:300])
            # was: raise RuntimeError(f"邮箱页提交失败: {error_text[:300]}") — was: raise RuntimeError(f"Email page submission failed: {error_text[:300]}")
        time.sleep(0.25)
    _raise_keyed(RuntimeError, "chatgpt.296b6826")
    # was: raise RuntimeError("邮箱页提交后未进入密码/验证码页面") —
    # was: raise RuntimeError("After submitting the email page, did not reach the password/verification-code page")


def _start_browser_signup_via_page(page, email: str, log, log_key: Optional[Callable[[str, dict], None]] = None) -> dict:
    for entry_url in (PLATFORM_LOGIN_ENTRY, f"{OPENAI_AUTH}/log-in"):
        try:
            _emit_log_key(log, log_key, "chatgpt.a6a51644", entry_url=entry_url)
            # was: log(f"打开 OpenAI 注册入口: {entry_url}") — was: log(f"Opening OpenAI signup entry: {entry_url}")
            page.goto(entry_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            _emit_log_key(log, log_key, "chatgpt.a559bb96", entry_url=entry_url, exc=exc)
            # was: log(f"注册入口访问失败: {entry_url} -> {exc}") — was: log(f"Failed to access signup entry: {entry_url} -> {exc}")
            continue

        initial_state = _derive_registration_state_from_page(page)
        if initial_state.get("page_type") in {
            "create_account_password",
            "login_password",
            "email_otp_verification",
            "about_you",
            "add_phone",
        }:
            return initial_state

        email_selector = _wait_for_any_selector(page, EMAIL_INPUT_SELECTORS, timeout=12)
        if not email_selector:
            continue
        if not _fill_input_like_user(page, email_selector, email):
            _raise_keyed(RuntimeError, "chatgpt.5456e703")
            # was: raise RuntimeError("邮箱页填写失败") — was: raise RuntimeError("Failed to fill the email page")
        _emit_log_key(log, log_key, "chatgpt.435ecdb5", email_selector=email_selector)
        # was: log(f"邮箱页输入框: {email_selector}") — was: log(f"Email page input field: {email_selector}")

        inline_state = _derive_registration_state_from_page(page)
        if inline_state.get("page_type") in {"create_account_password", "login_password"}:
            if inline_state.get("page_type") == "login_password" and _recover_signup_password_page(page, log, log_key):
                return _derive_registration_state_from_page(page)
            return inline_state

        submit_selector = _click_first(page, EMAIL_SUBMIT_SELECTORS, timeout=8)
        if submit_selector:
            _emit_log_key(log, log_key, "chatgpt.56d5dc8c", submit_selector=submit_selector)
            # was: log(f"邮箱页已点击继续按钮: {submit_selector}") — was: log(f"Clicked the Continue button on the email page: {submit_selector}")
        elif _submit_form_with_fallback(page, email_selector):
            _emit_log_key(log, log_key, "chatgpt.15fd5f77")
            # was: log("邮箱页未找到可点击 Continue，已使用表单 fallback 提交") —
            # was: log("Email page found no clickable Continue, used form fallback submission")
        else:
            _raise_keyed(RuntimeError, "chatgpt.9ff61a8d")
            # was: raise RuntimeError("邮箱页未找到 Continue 按钮") — was: raise RuntimeError("Email page: Continue button not found")

        return _wait_for_signup_entry_transition(page, log, log_key)

    _raise_keyed(RuntimeError, "chatgpt.290a57a9")
    # was: raise RuntimeError("未找到 OpenAI 注册入口邮箱输入框") — was: raise RuntimeError("OpenAI signup entry email input field not found")


def _start_browser_signup_via_authorize(page, email: str, device_id: str, log, log_key: Optional[Callable[[str, dict], None]] = None) -> dict:
    _emit_log_key(log, log_key, "chatgpt.3f1edf82")
    # was: log("访问 ChatGPT 首页...") — was: log("Visiting the ChatGPT home page...")
    page.goto(f"{CHATGPT_APP}/", wait_until="domcontentloaded", timeout=30000)

    _emit_log_key(log, log_key, "chatgpt.5aeeabd5")
    # was: log("获取 CSRF token...") — was: log("Fetching CSRF token...")
    csrf_token = _get_browser_csrf_token(page)
    if not csrf_token:
        _raise_keyed(RuntimeError, "chatgpt.83b44235")
        # was: raise RuntimeError("获取 CSRF token 失败") — was: raise RuntimeError("Failed to fetch CSRF token")

    _emit_log_key(log, log_key, "chatgpt.32bd72ad", email=email)
    # was: log(f"提交邮箱: {email}") — was: log(f"Submitting email: {email}")
    authorize_url = _start_browser_signin(page, email, device_id, csrf_token)
    if not authorize_url:
        _raise_keyed(RuntimeError, "chatgpt.768e8dd2")
        # was: raise RuntimeError("提交邮箱失败，未获取 authorize URL") — was: raise RuntimeError("Failed to submit email, did not get authorize URL")

    final_url = _browser_authorize(page, authorize_url, log, log_key)
    if not final_url:
        _raise_keyed(RuntimeError, "chatgpt.4863bbde")
        # was: raise RuntimeError("访问 authorize URL 失败") — was: raise RuntimeError("Failed to access authorize URL")
    return _derive_registration_state_from_page(page)


def _dump_debug(page, prefix: str) -> None:
    page.screenshot(path=f"/tmp/{prefix}.png")
    with open(f"/tmp/{prefix}.html", "w") as f:
        f.write(page.content())


def _get_cookies(page) -> dict:
    return {c["name"]: c["value"] for c in page.context.cookies()}


def _random_chrome_ua() -> str:
    patch = random.randint(0, 220)
    return (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/136.0.7103.{patch} Safari/537.36"
    )


def _infer_sec_ch_ua(user_agent: str) -> str:
    match = re.search(r"Chrome/(\d+)", str(user_agent or ""))
    major = str(match.group(1) if match else "136")
    return f'"Chromium";v="{major}", "Google Chrome";v="{major}", "Not.A/Brand";v="99"'


def _build_browser_headers(
    *,
    user_agent: str,
    accept: str,
    referer: str = "",
    origin: str = "",
    content_type: str = "",
    navigation: bool = False,
    extra_headers: dict | None = None,
) -> dict:
    headers = {
        "user-agent": user_agent or _random_chrome_ua(),
        "accept-language": "en-US,en;q=0.9",
        "sec-ch-ua": _infer_sec_ch_ua(user_agent),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "accept": accept,
    }
    if referer:
        headers["referer"] = referer
    if origin:
        headers["origin"] = origin
    if content_type:
        headers["content-type"] = content_type
    if navigation:
        headers["sec-fetch-dest"] = "document"
        headers["sec-fetch-mode"] = "navigate"
        headers["sec-fetch-user"] = "?1"
        headers["upgrade-insecure-requests"] = "1"
    else:
        headers["sec-fetch-dest"] = "empty"
        headers["sec-fetch-mode"] = "cors"
    for key, value in dict(extra_headers or {}).items():
        if value is not None:
            headers[key] = value
    return headers


def _browser_pause(page, *, headed: bool = True):
    delay_ms = random.randint(150, 450) if headed else random.randint(60, 180)
    try:
        page.wait_for_timeout(delay_ms)
    except Exception:
        time.sleep(delay_ms / 1000)


def _generate_datadog_trace_headers() -> dict:
    trace_hex = secrets.token_hex(8).rjust(16, "0")
    parent_hex = secrets.token_hex(8).rjust(16, "0")
    trace_id = str(int(trace_hex, 16))
    parent_id = str(int(parent_hex, 16))
    return {
        "traceparent": f"00-0000000000000000{trace_hex}-{parent_hex}-01",
        "tracestate": "dd=s:1;o:rum",
        "x-datadog-origin": "rum",
        "x-datadog-parent-id": parent_id,
        "x-datadog-sampling-priority": "1",
        "x-datadog-trace-id": trace_id,
    }


def _infer_page_type(data: dict | None, current_url: str = "") -> str:
    raw = data if isinstance(data, dict) else {}
    page_type = str(((raw.get("page") or {}).get("type")) or "").strip().lower().replace("-", "_").replace("/", "_").replace(" ", "_")
    if page_type:
        return page_type
    url = (current_url or "").lower()
    if "code=" in url:
        return "oauth_callback"
    if "create-account/password" in url:
        return "create_account_password"
    if "email-verification" in url or "email-otp" in url:
        return "email_otp_verification"
    if "about-you" in url:
        return "about_you"
    if "log-in/password" in url:
        return "login_password"
    if "sign-in-with-chatgpt" in url and "consent" in url:
        return "consent"
    if "workspace" in url and "select" in url:
        return "workspace_selection"
    if "organization" in url and "select" in url:
        return "organization_selection"
    if "add-phone" in url:
        return "add_phone"
    if "/api/oauth/oauth2/auth" in url:
        return "external_url"
    if "chatgpt.com" in url:
        return "chatgpt_home"
    return ""


def _extract_flow_state(data: dict | None, current_url: str = "") -> dict:
    raw = data if isinstance(data, dict) else {}
    page = raw.get("page") or {}
    payload = page.get("payload") or {}
    continue_url = str(raw.get("continue_url") or payload.get("url") or "").strip()
    if continue_url and continue_url.startswith("/"):
        continue_url = urljoin(OPENAI_AUTH, continue_url)
    effective_url = continue_url or current_url
    return {
        "page_type": _infer_page_type(raw, effective_url),
        "continue_url": continue_url,
        "method": str(raw.get("method") or payload.get("method") or "GET").upper(),
        "current_url": effective_url,
        "payload": payload if isinstance(payload, dict) else {},
        "raw": raw,
    }


def _extract_code_from_url(url: str) -> str:
    if not url or "code=" not in url:
        return ""
    try:
        from urllib.parse import parse_qs, urlparse as _up

        parsed = _up(url)
        values = parse_qs(parsed.query, keep_blank_values=True)
        return str((values.get("code") or [""])[0] or "").strip()
    except Exception:
        return ""


def _normalize_url(target_url: str, base_url: str = OPENAI_AUTH) -> str:
    value = str(target_url or "").strip()
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    try:
        return urljoin(base_url, value)
    except Exception:
        return value


def _decode_jwt_payload(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        pad = "=" * ((4 - (len(payload) % 4)) % 4)
        return json.loads(base64.urlsafe_b64decode((payload + pad).encode("ascii")).decode("utf-8"))
    except Exception:
        return {}


class _SentinelTokenGenerator:
    def __init__(self, device_id: str, user_agent: str):
        self.device_id = device_id or str(uuid.uuid4())
        self.user_agent = user_agent or _random_chrome_ua()
        self.sid = str(uuid.uuid4())

    @staticmethod
    def _fnv1a32(text: str) -> str:
        h = 2166136261
        for ch in text:
            h ^= ord(ch)
            h = (h * 16777619) & 0xFFFFFFFF
        h ^= (h >> 16)
        h = (h * 2246822507) & 0xFFFFFFFF
        h ^= (h >> 13)
        h = (h * 3266489909) & 0xFFFFFFFF
        h ^= (h >> 16)
        return f"{h & 0xFFFFFFFF:08x}"

    @staticmethod
    def _b64(data) -> str:
        return base64.b64encode(json.dumps(data, separators=(",", ":")).encode("utf-8")).decode("ascii")

    def _config(self) -> list:
        perf_now = 1000 + random.random() * 49000
        return [
            "1920x1080",
            time.strftime("%a, %d %b %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)", time.gmtime()),
            4294705152,
            random.random(),
            self.user_agent,
            SENTINEL_SDK_URL,
            None,
            None,
            "en-US",
            "en-US,en",
            random.random(),
            "webkitTemporaryStorage−undefined",
            "location",
            "Object",
            perf_now,
            self.sid,
            "",
            random.choice([4, 8, 12, 16]),
            int(time.time() * 1000 - perf_now),
        ]

    def generate_requirements_token(self) -> str:
        cfg = self._config()
        cfg[3] = 1
        cfg[9] = round(5 + random.random() * 45)
        return "gAAAAAC" + self._b64(cfg)

    def generate_token(self, seed: str, difficulty: str) -> str:
        max_attempts = 500000
        cfg = self._config()
        start_ms = int(time.time() * 1000)
        diff = str(difficulty or "0")
        for nonce in range(max_attempts):
            cfg[3] = nonce
            cfg[9] = round(int(time.time() * 1000) - start_ms)
            encoded = self._b64(cfg)
            digest = self._fnv1a32((seed or "") + encoded)
            if digest[: len(diff)] <= diff:
                return "gAAAAAB" + encoded + "~S"
        return "gAAAAAB" + self._b64(None)


def _browser_fetch(page, url: str, *, method: str = "GET", headers: dict | None = None, body: str | None = None, redirect: str = "manual", timeout_ms: int = 30000) -> dict:
    return page.evaluate(
        """
        async ({ url, method, headers, body, redirect, timeoutMs }) => {
          const controller = new AbortController();
          const timer = setTimeout(() => controller.abort(new Error(`fetch timeout after ${timeoutMs}ms`)), timeoutMs);
          try {
            const resp = await fetch(url, {
              method,
              headers: headers || {},
              body: body === null ? undefined : body,
              redirect,
              signal: controller.signal,
            });
            const respHeaders = {};
            resp.headers.forEach((v, k) => { respHeaders[k] = v; });
            let text = '';
            try { text = await resp.text(); } catch {}
            let data = null;
            try { data = JSON.parse(text); } catch {}
            return { ok: resp.ok, status: resp.status, url: resp.url || url, headers: respHeaders, text, data };
          } catch (e) {
            return { ok: false, status: 0, url, headers: {}, text: String(e && e.message || e), data: null };
          } finally {
            clearTimeout(timer);
          }
        }
        """,
        {
            "url": url,
            "method": method,
            "headers": headers or {},
            "body": body,
            "redirect": redirect,
            "timeoutMs": timeout_ms,
        },
    )


def _build_browser_sentinel_token(page, device_id: str, flow: str, user_agent: str) -> str:
    generator = _SentinelTokenGenerator(device_id, user_agent)
    req_body = json.dumps(
        {"p": generator.generate_requirements_token(), "id": device_id, "flow": flow},
        separators=(",", ":"),
    )
    result = _browser_fetch(
        page,
        SENTINEL_REQ_URL,
        method="POST",
        headers=_build_browser_headers(
            user_agent=user_agent,
            accept="*/*",
            referer=SENTINEL_FRAME_URL,
            origin=SENTINEL_BASE,
            content_type="text/plain;charset=UTF-8",
            extra_headers={
                "sec-fetch-site": "same-origin",
            },
        ),
        body=req_body,
        redirect="follow",
    )
    data = result.get("data") or {}
    challenge_token = str(data.get("token") or "").strip()
    if not challenge_token:
        return ""
    pow_meta = data.get("proofofwork") or {}
    if pow_meta.get("required") and pow_meta.get("seed"):
        p_value = generator.generate_token(str(pow_meta.get("seed") or ""), str(pow_meta.get("difficulty") or "0"))
    else:
        p_value = generator.generate_requirements_token()
    return json.dumps(
        {
            "p": p_value,
            "t": "",
            "c": challenge_token,
            "id": device_id,
            "flow": flow,
        },
        separators=(",", ":"),
    )


def _submit_browser_user_register(page, email: str, password: str, device_id: str, user_agent: str) -> dict:
    headers = _build_browser_headers(
        user_agent=user_agent,
        accept="application/json",
        referer=f"{OPENAI_AUTH}/create-account/password",
        origin=OPENAI_AUTH,
        content_type="application/json",
        extra_headers={
            "sec-fetch-site": "same-origin",
            "oai-device-id": device_id,
            **_generate_datadog_trace_headers(),
        },
    )
    sentinel = _build_browser_sentinel_token(page, device_id, "username_password_create", user_agent)
    if sentinel:
        headers["openai-sentinel-token"] = sentinel
    _browser_pause(page)
    return _browser_fetch(
        page,
        f"{OPENAI_AUTH}/api/accounts/user/register",
        method="POST",
        headers=headers,
        body=json.dumps({"username": email, "password": password}),
        redirect="follow",
    )


def _send_browser_email_otp(page) -> dict:
    _browser_pause(page)
    return _browser_fetch(
        page,
        f"{OPENAI_AUTH}/api/accounts/email-otp/send",
        method="GET",
        headers={
            "accept": "application/json, text/plain, */*",
            "referer": f"{OPENAI_AUTH}/create-account/password",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "accept-language": "en-US,en;q=0.9",
        },
        redirect="follow",
    )


def _decode_oauth_session_cookie(cookies_dict: dict) -> dict:
    raw = str(cookies_dict.get("oai-client-auth-session") or "").strip()
    if not raw:
        return {}
    first = raw.split(".")[0]
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            pad = "=" * ((4 - (len(first) % 4)) % 4)
            decoded = decoder((first + pad).encode("ascii")).decode("utf-8")
            parsed = json.loads(decoded)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return {}


def _extract_workspace_from_consent_html(session, consent_url: str) -> dict:
    try:
        response = session.get(consent_url, allow_redirects=True, timeout=30)
        html = response.text or ""
        if "workspaces" not in html:
            return {}
        ids = re.findall(r'"id"(?:,|:)"([0-9a-f-]{36})"', html, flags=re.I)
        kinds = re.findall(r'"kind"(?:,|:)"([^"]+)"', html, flags=re.I)
        if not ids:
            return {}
        seen: set[str] = set()
        workspaces: list[dict] = []
        for idx, workspace_id in enumerate(ids):
            if workspace_id in seen:
                continue
            seen.add(workspace_id)
            item = {"id": workspace_id}
            if idx < len(kinds):
                item["kind"] = kinds[idx]
            workspaces.append(item)
        return {"workspaces": workspaces} if workspaces else {}
    except Exception:
        return {}


def _seed_session_cookies(session, cookies_dict: dict):
    for name, value in cookies_dict.items():
        for domain in [".openai.com", ".chatgpt.com", ".auth.openai.com", "auth.openai.com", "chatgpt.com"]:
            try:
                session.cookies.set(name, value, domain=domain, path="/")
            except Exception:
                pass


def _follow_redirects_for_code(session, start_url: str, log, *, max_redirects: int = 12) -> str:
    current_url = start_url
    for idx in range(max_redirects):
        response = session.get(current_url, allow_redirects=False, timeout=30)
        log(f"  redirect-follow[{idx+1}] {response.status_code} {str(current_url)[:140]}")
        location = str(response.headers.get("Location") or "").strip()
        if not location:
            break
        next_url = urljoin(current_url, location)
        code = _extract_code_from_url(next_url)
        if code:
            return next_url
        if response.status_code not in (301, 302, 303, 307, 308):
            break
        current_url = next_url
    return ""


def _complete_oauth_with_session(cookies_dict: dict, oauth_start, proxy: str | None, log, log_key: Optional[Callable[[str, dict], None]] = None) -> dict | None:
    from .oauth import submit_callback_url
    from curl_cffi import requests as cffi_requests

    s = cffi_requests.Session(impersonate="chrome131")
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    _seed_session_cookies(s, cookies_dict)

    try:
        session_meta = _decode_oauth_session_cookie(cookies_dict)
        consent_url = "https://auth.openai.com/sign-in-with-chatgpt/codex/consent"
        workspaces = list(session_meta.get("workspaces") or [])
        if not workspaces:
            session_meta = _extract_workspace_from_consent_html(s, consent_url)
            workspaces = list(session_meta.get("workspaces") or [])
        if not workspaces:
            _emit_log_key(log, log_key, "chatgpt.5f0d00f7")
            # was: log("  ⚠️ 缺少 oai-client-auth-session workspaces，OAuth 失败") —
            # was: log("  ⚠️ missing oai-client-auth-session workspaces, OAuth failed")
            return None
        workspace_id = str((workspaces[0] or {}).get("id") or "").strip()
        _emit_log_key(log, log_key, "chatgpt.ae99599f", workspace_id=workspace_id)
        # was: log(f"  选择 workspace: {workspace_id}") — was: log(f"  select workspace: {workspace_id}")
        ws_resp = s.post(
            "https://auth.openai.com/api/accounts/workspace/select",
            headers={
                "accept": "application/json",
                "referer": consent_url,
                "origin": OPENAI_AUTH,
                "content-type": "application/json",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            },
            data=json.dumps({"workspace_id": workspace_id}),
            allow_redirects=False,
            timeout=30,
        )
        log(f"  workspace/select -> {ws_resp.status_code}")

        next_url = str(ws_resp.headers.get("Location") or "").strip()
        next_data = {}
        if not next_url:
            try:
                next_data = ws_resp.json() or {}
            except Exception:
                next_data = {}
            next_url = str(next_data.get("continue_url") or "").strip()
        next_url = _normalize_url(next_url, consent_url)
        direct_code = _extract_code_from_url(next_url)
        if direct_code:
            result_json = submit_callback_url(
                callback_url=next_url,
                expected_state=oauth_start.state,
                code_verifier=oauth_start.code_verifier,
                proxy_url=proxy,
            )
            return json.loads(result_json)

        orgs = list((((next_data.get("data") or {}).get("orgs")) or []))
        if orgs and orgs[0].get("id"):
            org_id = str(orgs[0].get("id") or "").strip()
            org_body = {"org_id": org_id}
            projects = list(orgs[0].get("projects") or [])
            if projects and projects[0].get("id"):
                org_body["project_id"] = str(projects[0].get("id") or "").strip()
            _emit_log_key(log, log_key, "chatgpt.4df63e8a", org_id=org_id)
            # was: log(f"  选择 organization: {org_id}") — was: log(f"  select organization: {org_id}")
            org_resp = s.post(
                "https://auth.openai.com/api/accounts/organization/select",
                headers={
                    "accept": "application/json",
                    "referer": consent_url,
                    "origin": OPENAI_AUTH,
                    "content-type": "application/json",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
                },
                data=json.dumps(org_body),
                allow_redirects=False,
                timeout=30,
            )
            log(f"  organization/select -> {org_resp.status_code}")
            next_url = str(org_resp.headers.get("Location") or "").strip() or next_url
            if not next_url:
                try:
                    org_data = org_resp.json() or {}
                    next_url = str(org_data.get("continue_url") or "").strip()
                    if not next_url:
                        org_state = _extract_flow_state(org_data, str(org_resp.url))
                        next_url = org_state.get("continue_url") or org_state.get("current_url") or ""
                except Exception:
                    next_url = ""
            next_url = _normalize_url(next_url, consent_url)

        if not next_url and next_data:
            state = _extract_flow_state(next_data, str(ws_resp.url))
            next_url = state.get("continue_url") or state.get("current_url") or ""
            next_url = _normalize_url(next_url, consent_url)

        if not next_url:
            next_url = "https://auth.openai.com/api/oauth/oauth2/auth?" + oauth_start.auth_url.split("?", 1)[1]

        callback_url = _follow_redirects_for_code(s, next_url, log)
        if not callback_url:
            _emit_log_key(log, log_key, "chatgpt.2d1a030b")
            # was: log("  ⚠️ 未能跟到 OAuth callback") — was: log("  ⚠️ failed to follow OAuth callback")
            return None
        result_json = submit_callback_url(
            callback_url=callback_url,
            expected_state=oauth_start.state,
            code_verifier=oauth_start.code_verifier,
            proxy_url=proxy,
        )
        return json.loads(result_json)
    except Exception as e:
        _emit_log_key(log, log_key, "chatgpt.87802bb5", e=e)
        # was: log(f"  OAuth 会话补全异常: {e}") — was: log(f"  OAuth session completion exception: {e}")
        return None


def _submit_callback_result(callback_url: str, oauth_start, proxy: str | None) -> dict:
    from .oauth import submit_callback_url

    result_json = submit_callback_url(
        callback_url=callback_url,
        expected_state=oauth_start.state,
        code_verifier=oauth_start.code_verifier,
        redirect_uri=oauth_start.redirect_uri,
        client_id=oauth_start.client_id,
        proxy_url=proxy,
    )
    return json.loads(result_json)


def _extract_callback_url_from_exception(exc: Exception) -> str:
    text = str(exc or "")
    if not text:
        return ""
    match = re.search(r"(https?://localhost[^\s\"')]+)", text, flags=re.I)
    if not match:
        return ""
    callback_url = str(match.group(1) or "").strip().rstrip(".,")
    return callback_url if _extract_code_from_url(callback_url) else ""


def _derive_oauth_state_from_page(page) -> dict:
    state = _derive_registration_state_from_page(page)
    if state.get("page_type"):
        return state
    current_url = str(page.url or "")
    if _find_first_selector(page, EMAIL_INPUT_SELECTORS):
        return _build_manual_flow_state("login_email", current_url)
    return _extract_flow_state(None, current_url)


def _submit_login_email_via_page(page, email: str, log, log_key: Optional[Callable[[str, dict], None]] = None) -> dict:
    input_selector = _wait_for_any_selector(page, EMAIL_INPUT_SELECTORS, timeout=15)
    if not input_selector:
        _raise_keyed(RuntimeError, "chatgpt.517c8c0b")
        # was: raise RuntimeError("OAuth 邮箱页未找到输入框") — was: raise RuntimeError("OAuth email page: input box not found")
    if not _fill_input_like_user(page, input_selector, email):
        _raise_keyed(RuntimeError, "chatgpt.f2649838")
        # was: raise RuntimeError("OAuth 邮箱页填写失败") — was: raise RuntimeError("OAuth email page: fill failed")
    _emit_log_key(log, log_key, "chatgpt.1edb3a16", input_selector=input_selector)
    # was: log(f"OAuth 邮箱页输入框: {input_selector}") — was: log(f"OAuth email page input box: {input_selector}")
    _browser_pause(page)

    start_url = str(page.url or "")
    submit_selector = _click_first(page, EMAIL_SUBMIT_SELECTORS, timeout=8)
    if submit_selector:
        _emit_log_key(log, log_key, "chatgpt.7b922217", submit_selector=submit_selector)
        # was: log(f"OAuth 邮箱页已点击继续按钮: {submit_selector}") —
        # was: log(f"OAuth email page: clicked continue button: {submit_selector}")
    elif _submit_form_with_fallback(page, input_selector):
        _emit_log_key(log, log_key, "chatgpt.beb0490e")
        # was: log("OAuth 邮箱页未找到可点击 Continue，已使用表单 fallback 提交") —
        # was: log("OAuth email page: no clickable Continue found, submitted via form fallback")
    else:
        _raise_keyed(RuntimeError, "chatgpt.fb166a83")
        # was: raise RuntimeError("OAuth 邮箱页未找到 Continue 按钮") —
        # was: raise RuntimeError("OAuth email page: Continue button not found")

    deadline = time.time() + 20
    last_url = start_url
    while time.time() < deadline:
        current_url = str(page.url or "")
        last_url = current_url or last_url
        if _click_passwordless_login_if_available(page, log, log_key, context="OAuth 邮箱页提交后"):
            time.sleep(0.5)
            continue
        state = _derive_oauth_state_from_page(page)
        page_type = str(state.get("page_type") or "")
        if page_type in {
            "login_password",
            "create_account_password",
            "email_otp_verification",
            "about_you",
            "consent",
            "workspace_selection",
            "organization_selection",
            "add_phone",
            "external_url",
            "oauth_callback",
            "chatgpt_home",
        }:
            return {"ok": True, "status": 200, "url": current_url, "data": None, "text": ""}
        if current_url != start_url and page_type != "login_email":
            return {"ok": True, "status": 200, "url": current_url, "data": None, "text": ""}
        error_text = _extract_auth_error_text(page)
        if error_text:
            return {"ok": False, "status": 400, "url": current_url, "data": None, "text": error_text}
        time.sleep(0.5)
    return {"ok": False, "status": 0, "url": last_url, "data": None, "text": "OAuth 邮箱页提交后未跳转"}


def _do_codex_oauth(page, cookies_dict: dict, email: str, password: str, otp_callback, phone_callback, proxy: str | None, log, log_key: Optional[Callable[[str, dict], None]] = None) -> dict | None:
    """在真实浏览器会话内完成 Codex OAuth，返回完整 token 包。 — Complete the Codex OAuth flow inside a real browser session, returning the full token bundle."""
    from .oauth import generate_oauth_url
    from .constants import CODEX_CLIENT_ID, CODEX_REDIRECT_URI, CODEX_SCOPE

    oauth_start = generate_oauth_url(
        redirect_uri=CODEX_REDIRECT_URI,
        scope=CODEX_SCOPE,
        client_id=CODEX_CLIENT_ID,
    )
    try:
        user_agent = str(page.evaluate("() => navigator.userAgent") or "").strip() or _random_chrome_ua()
    except Exception:
        user_agent = _random_chrome_ua()
    device_id = str(cookies_dict.get("oai-did") or uuid.uuid4())
    log(f"  OAuth state={oauth_start.state[:20]}...")

    try:
        try:
            page.goto(oauth_start.auth_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            callback_url = _extract_callback_url_from_exception(exc)
            if callback_url:
                _emit_log_key(log, log_key, "chatgpt.33abf55e", callback_url=callback_url[:100])
                # was: log(f"  OAuth bootstrap 直接捕获 callback: {callback_url[:100]}...") —
                # was: log(f"  OAuth bootstrap directly captured callback: {callback_url[:100]}...")
                return _submit_callback_result(callback_url, oauth_start, proxy)
            raise

        current_url = str(page.url or "")
        log(f"  OAuth bootstrap -> {current_url[:100]}...")

        for step in range(20):
            state = _derive_oauth_state_from_page(page)
            current_url = str(page.url or "")
            next_url = str(state.get("continue_url") or "").strip()
            log(
                f"  OAuth state step[{step+1}/20]: "
                f"page={state.get('page_type') or '-'} next={next_url[:60]}"
                f" url={current_url[:120]}"
            )

            callback_url = ""
            if _extract_code_from_url(current_url):
                callback_url = current_url
            elif _extract_code_from_url(next_url):
                callback_url = next_url
            if callback_url:
                return _submit_callback_result(callback_url, oauth_start, proxy)

            page_oauth_url = _get_page_oauth_url(page)
            if (
                page_oauth_url
                and page_oauth_url != current_url
                and _oauth_url_matches_state(page_oauth_url, oauth_start.state)
            ):
                _emit_log_key(log, log_key, "chatgpt.c32fc9dd")
                # was: log("  OAuth 页面检测到更新的授权链接，跟随页面授权链接...") —
                # was: log("  OAuth page detected an updated authorization link, following it...")
                page.goto(page_oauth_url, wait_until="domcontentloaded", timeout=30000)
                continue

            if state["page_type"] == "login_email":
                _emit_log_key(log, log_key, "chatgpt.379ff815")
                # was: log("  OAuth 页面需要邮箱登录，提交邮箱...") —
                # was: log("  OAuth page requires email login, submitting email...")
                email_resp = _submit_login_email_via_page(page, email, log, log_key)
                _emit_log_key(log, log_key, "chatgpt.c510799e", status=email_resp.get('status', 0))
                # was: log(f"  OAuth 邮箱页提交状态: {email_resp.get('status', 0)}") —
                # was: log(f"  OAuth email page submit status: {email_resp.get('status', 0)}")
                if not email_resp.get("ok"):
                    _raise_keyed(RuntimeError, "chatgpt.6a8063fe", val=(email_resp.get('text') or '')[:300])
                    # was: raise RuntimeError(f"OAuth 邮箱页提交失败: {(email_resp.get('text') or '')[:300]}") —
                    # was: raise RuntimeError(f"OAuth email page submission failed: {(email_resp.get('text') or '')[:300]}")
                continue

            if state["page_type"] in {"login_password", "create_account_password"}:
                _emit_log_key(log, log_key, "chatgpt.2d98d2d9")
                # was: log("  OAuth 页面需要密码登录，提交密码...") —
                # was: log("  OAuth page requires password login, submitting password...")
                # OAuth 流程中直接填密码登录，不尝试恢复到注册态 —
                # In the OAuth flow, fill in the password directly to log in; don't try to fall back to the registration state
                password_resp = _submit_oauth_password_direct(page, password, log, log_key)
                _emit_log_key(log, log_key, "chatgpt.9041ab4d", status=password_resp.get('status', 0))
                # was: log(f"  OAuth 密码页提交状态: {password_resp.get('status', 0)}") —
                # was: log(f"  OAuth password page submit status: {password_resp.get('status', 0)}")
                if not password_resp.get("ok"):
                    _raise_keyed(RuntimeError, "chatgpt.25bc0ae6", val=(password_resp.get('text') or '')[:300])
                    # was: raise RuntimeError(f"OAuth 密码页提交失败: {(password_resp.get('text') or '')[:300]}") —
                    # was: raise RuntimeError(f"OAuth password page submission failed: {(password_resp.get('text') or '')[:300]}")
                continue

            if state["page_type"] == "email_otp_verification":
                if not otp_callback:
                    _emit_log_key(log, log_key, "chatgpt.6a2354c7")
                    # was: log("  ⚠️ OAuth 需要邮箱 OTP 但没有 otp_callback") —
                    # was: log("  ⚠️ OAuth requires email OTP but no otp_callback is configured")
                    return None
                _emit_log_key(log, log_key, "chatgpt.bad3e092")
                # was: log("  OAuth 等待邮箱验证码...") — was: log("  OAuth waiting for email verification code...")
                code = otp_callback()
                if not code:
                    _emit_log_key(log, log_key, "chatgpt.83573a41")
                    # was: log("  ⚠️ OAuth OTP 获取失败") — was: log("  ⚠️ OAuth OTP retrieval failed")
                    return None
                otp_resp = _submit_otp_via_page(page, code, log, log_key)
                _emit_log_key(log, log_key, "chatgpt.d4441004", status=otp_resp.get('status', 0))
                # was: log(f"  OAuth 验证码页提交状态: {otp_resp.get('status', 0)}") —
                # was: log(f"  OAuth verification code page submit status: {otp_resp.get('status', 0)}")
                if not otp_resp.get("ok"):
                    _raise_keyed(RuntimeError, "chatgpt.d4d9dc48", val=(otp_resp.get('text') or '')[:300])
                    # was: raise RuntimeError(f"OAuth 验证码校验失败: {(otp_resp.get('text') or '')[:300]}") —
                    # was: raise RuntimeError(f"OAuth verification code check failed: {(otp_resp.get('text') or '')[:300]}")
                continue

            if state["page_type"] == "about_you":
                _emit_log_key(log, log_key, "chatgpt.7ead5104")
                # was: log("  OAuth 页面出现 about_you，继续页面填写...") —
                # was: log("  OAuth page shows about_you, continuing to fill it in...")
                about_resp = _submit_about_you_via_page(page, log, log_key)
                _emit_log_key(log, log_key, "chatgpt.5c616431", status=about_resp.get('status', 0))
                # was: log(f"  OAuth about_you 提交状态: {about_resp.get('status', 0)}") —
                # was: log(f"  OAuth about_you submit status: {about_resp.get('status', 0)}")
                if not about_resp.get("ok"):
                    _raise_keyed(RuntimeError, "chatgpt.804d9cfc", val=(about_resp.get('text') or '')[:300])
                    # was: raise RuntimeError(f"OAuth about_you 提交失败: {(about_resp.get('text') or '')[:300]}") —
                    # was: raise RuntimeError(f"OAuth about_you submission failed: {(about_resp.get('text') or '')[:300]}")
                continue

            if state["page_type"] in {"consent", "workspace_selection", "organization_selection", "external_url"}:
                browser_result = _complete_oauth_in_browser(page, oauth_start, proxy, log, log_key)
                if browser_result:
                    return browser_result
                cookies_dict = _get_cookies(page)
                session_result = _complete_oauth_with_session(cookies_dict, oauth_start, proxy, log, log_key)
                if session_result:
                    return session_result
                _emit_log_key(log, log_key, "chatgpt.ef15be9e")
                # was: log("  ⚠️ 页面已到 consent/workspace，但会话补全失败") —
                # was: log("  ⚠️ Page reached consent/workspace, but session completion failed")
                return None

            if state["page_type"] == "add_phone":
                if phone_callback:
                    _emit_log_key(log, log_key, "chatgpt.8b1c4c26")
                    # was: log("  OAuth 检测到 add_phone，优先执行短信验证...") —
                    # was: log("  OAuth detected add_phone, prioritizing SMS verification...")
                    try:
                        _handle_add_phone_challenge(
                            page, phone_callback,
                            device_id=device_id, user_agent=user_agent,
                            log=log, log_key=log_key, resume_url=oauth_start.auth_url,
                        )
                        continue
                    except Exception as exc:
                        _emit_log_key(log, log_key, "chatgpt.734c2128", exc=exc)
                        # was: log(f"  短信验证失败，停止 OAuth 流程: {exc}") —
                        # was: log(f"  SMS verification failed, stopping the OAuth flow: {exc}")
                        return None

                # 先尝试跳过 add_phone，直接重新访问 OAuth 授权 URL
                # 用户已登录，重新访问 auth URL 应该能直接跳到 callback
                # First try skipping add_phone by revisiting the OAuth authorization URL directly
                # The user is already logged in, so revisiting the auth URL should jump straight to the callback
                _emit_log_key(log, log_key, "chatgpt.bb02c306")
                # was: log("  检测到 add_phone，尝试跳过...") — was: log("  Detected add_phone, attempting to skip...")
                try:
                    page.goto(oauth_start.auth_url, wait_until="domcontentloaded", timeout=15000)
                    time.sleep(2)
                    current_url = str(page.url or "")

                    # 检查是否直接拿到了 callback — Check whether the callback was obtained directly
                    callback_url = ""
                    if "code=" in current_url:
                        callback_url = current_url
                    else:
                        # 可能需要跟随重定向 — May need to follow a redirect
                        for _ in range(5):
                            time.sleep(1)
                            current_url = str(page.url or "")
                            if "code=" in current_url:
                                callback_url = current_url
                                break

                    if callback_url:
                        _emit_log_key(log, log_key, "chatgpt.1f579d09")
                        # was: log("  ✓ 成功跳过 add_phone，获取到 OAuth callback") —
                        # was: log("  ✓ Successfully skipped add_phone, obtained OAuth callback")
                        return _submit_callback_result(callback_url, oauth_start, proxy)

                    # 检查页面状态 — Check page state
                    skip_state = _derive_registration_state_from_page(page)
                    if skip_state.get("page_type") in {"consent", "workspace_selection", "organization_selection"}:
                        _emit_log_key(log, log_key, "chatgpt.6d54bfbf")
                        # was: log("  ✓ 跳过 add_phone 到达 consent 页面") —
                        # was: log("  ✓ Skipped add_phone and reached the consent page")
                        # 尝试在浏览器里完成 consent 流程 — Try to complete the consent flow in the browser
                        browser_result = _complete_oauth_in_browser(page, oauth_start, proxy, log, log_key)
                        if browser_result:
                            return browser_result
                        # 回退到 curl session 方式 — Fall back to the curl session approach
                        cookies_dict = _get_cookies(page)
                        session_result = _complete_oauth_with_session(cookies_dict, oauth_start, proxy, log, log_key)
                        if session_result:
                            return session_result

                    if skip_state.get("page_type") == "add_phone":
                        _emit_log_key(log, log_key, "chatgpt.ee496676")
                        # was: log("  跳过失败，仍在 add_phone 页面") — was: log("  Skip failed, still on the add_phone page")
                    else:
                        _emit_log_key(log, log_key, "chatgpt.bd5c726c", page_type=skip_state.get('page_type') or '-')
                        # was: log(f"  跳过后页面状态: {skip_state.get('page_type') or '-'}") —
                        # was: log(f"  Page state after skip attempt: {skip_state.get('page_type') or '-'}")
                        # 继续状态机循环 — Continue the state machine loop
                        continue

                except Exception as exc:
                    callback_url = _extract_callback_url_from_exception(exc)
                    if callback_url:
                        return _submit_callback_result(callback_url, oauth_start, proxy)
                    _emit_log_key(log, log_key, "chatgpt.29ea0a37", exc=exc)
                    # was: log(f"  跳过 add_phone 异常: {exc}") — was: log(f"  Exception while skipping add_phone: {exc}")

                _emit_log_key(log, log_key, "chatgpt.5e235c24")
                # was: log("  ⚠️ add_phone 无法跳过且无可用接码服务") —
                # was: log("  ⚠️ add_phone cannot be skipped and no SMS-receiving service is available")
                return None

            # chatgpt_home: 页面可能正在 JS 重定向（如跳转到 add-phone）
            # 等待更长时间让重定向完成
            # chatgpt_home: the page may be doing a JS redirect (e.g. to add-phone)
            # Wait longer to let the redirect finish
            if state["page_type"] == "chatgpt_home":
                # 检查是否是错误页面 — Check whether this is an error page
                if "error" in current_url:
                    error_msg = current_url.split("error=")[-1].split("&")[0] if "error=" in current_url else "unknown"
                    _emit_log_key(log, log_key, "chatgpt.aaad326c", error_msg=error_msg, url=current_url[:150])
                    # was: log(f"  OAuth 错误页面: {error_msg} url={current_url[:150]}") —
                    # was: log(f"  OAuth error page: {error_msg} url={current_url[:150]}")
                    _raise_keyed(RuntimeError, "chatgpt.5eac4930", error_msg=error_msg)
                    # was: raise RuntimeError(f"OpenAI OAuth 错误: {error_msg}") —
                    # was: raise RuntimeError(f"OpenAI OAuth error: {error_msg}")
                time.sleep(2)
                new_url = str(page.url or "")
                if new_url != current_url:
                    continue
                # 检查 cookie 里是否有 session — Check whether the cookies contain a session
                cookies_dict = _get_cookies(page)
                for ck, cv in cookies_dict.items():
                    if "session" in ck.lower() and cv:
                        _emit_log_key(log, log_key, "chatgpt.3d898ed1", ck=ck)
                        # was: log(f"  chatgpt_home 检测到 session cookie: {ck}") —
                        # was: log(f"  chatgpt_home detected a session cookie: {ck}")
                        session_result = _complete_oauth_with_session(cookies_dict, oauth_start, proxy, log, log_key)
                        if session_result:
                            return session_result
                        break
                continue

            target_url = _normalize_url(state.get("continue_url") or "", OPENAI_AUTH)
            if target_url and target_url != current_url:
                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as exc:
                    callback_url = _extract_callback_url_from_exception(exc)
                    if callback_url:
                        return _submit_callback_result(callback_url, oauth_start, proxy)
                    log(f"  OAuth navigation failed: {exc}")
                    break
                continue

            error_text = _extract_auth_error_text(page)
            if error_text:
                _raise_keyed(RuntimeError, "chatgpt.db6abcbc", error_text=error_text[:300])
                # was: raise RuntimeError(f"OAuth 页面错误: {error_text[:300]}") —
                # was: raise RuntimeError(f"OAuth page error: {error_text[:300]}")
            time.sleep(0.5)
    except Exception as e:
        _emit_log_key(log, log_key, "chatgpt.84eb8564", e=e)
        # was: log(f"  OAuth 异常: {e}") — was: log(f"  OAuth exception: {e}")
        return None

    cookies_dict = _get_cookies(page)
    result = _complete_oauth_with_session(cookies_dict, oauth_start, proxy, log, log_key)
    if result:
        return result

    session_token = cookies_dict.get("__Secure-next-auth.session-token", "")
    if not session_token:
        _emit_log_key(log, log_key, "chatgpt.b4753f15")
        # was: log("  ⚠️ 无 session_token，OAuth 失败") — was: log("  ⚠️ No session_token, OAuth failed")
        return None
    _emit_log_key(log, log_key, "chatgpt.baaea19d")
    # was: log("  ⚠️ 完整 OAuth 失败，回退 session access_token") —
    # was: log("  ⚠️ Full OAuth failed, falling back to session access_token")
    return None


def _wait_for_access_token(page, timeout: int = 60) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = page.evaluate("""
            async () => {
                const r = await fetch('/api/auth/session');
                const j = await r.json();
                return j.accessToken || '';
            }
            """)
            if r:
                return r
        except Exception:
            pass
        time.sleep(2)
    return ""


def _is_registration_complete(state: dict) -> bool:
    page_type = str(state.get("page_type") or "")
    url = str(state.get("current_url") or state.get("continue_url") or "").lower()
    return page_type in {"callback", "oauth_callback", "chatgpt_home"} or (
        "chatgpt.com" in url and "redirect_uri" not in url and "about-you" not in url
    )


def _handle_post_signup_onboarding(page, log, log_key: Optional[Callable[[str, dict], None]] = None) -> None:
    current_url = str(page.url or "")
    if "chatgpt.com" not in current_url:
        return
    try:
        # 可能弹出 persistent storage 提示，优先点 Allow，不影响主流程也可点 Block。 —
        # A persistent storage prompt may pop up; prefer clicking Allow, though clicking Block doesn't hurt the main flow either.
        allow_selector = _click_first(
            page,
            [
                'button:has-text("Allow")',
                'button:has-text("allow")',
                'button:has-text("Block")',
                'button:has-text("block")',
            ],
            timeout=1,
        )
        if allow_selector:
            _emit_log_key(log, log_key, "chatgpt.50763b0f", allow_selector=allow_selector)
            # was: log(f"已处理浏览器弹窗: {allow_selector}") — was: log(f"Handled browser popup: {allow_selector}")
    except Exception:
        pass

    # 新账号常见 onboarding 问卷页，优先 Skip。 — New accounts often show an onboarding survey page; prefer clicking Skip.
    try:
        if page.locator("text=What brings you to ChatGPT?").first.count() > 0:
            skip_selector = _click_first(
                page,
                [
                    'button:has-text("Skip")',
                    'button:has-text("skip")',
                    'button:has-text("Next")',
                    'button:has-text("next")',
                ],
                timeout=5,
            )
            if skip_selector:
                _emit_log_key(log, log_key, "chatgpt.cc1c8c46", skip_selector=skip_selector)
                # was: log(f"已处理 onboarding 页面: {skip_selector}") —
                # was: log(f"Handled onboarding page: {skip_selector}")
                _browser_pause(page)
    except Exception:
        pass


def _is_password_registration(state: dict) -> bool:
    return str(state.get("page_type") or "") in {"create_account_password", "password"}


def _is_email_otp(state: dict) -> bool:
    target = f"{state.get('continue_url') or ''} {state.get('current_url') or ''}".lower()
    return str(state.get("page_type") or "") == "email_otp_verification" or "email-verification" in target or "email-otp" in target


def _is_about_you(state: dict) -> bool:
    target = f"{state.get('continue_url') or ''} {state.get('current_url') or ''}".lower()
    return str(state.get("page_type") or "") == "about_you" or "about-you" in target


def _is_add_phone(state: dict) -> bool:
    target = f"{state.get('continue_url') or ''} {state.get('current_url') or ''}".lower()
    return str(state.get("page_type") or "") == "add_phone" or "add-phone" in target


def _mask_phone_number(phone_number: str) -> str:
    text = str(phone_number or "").strip()
    if len(text) <= 4:
        return text
    if len(text) <= 8:
        return f"{text[:2]}****{text[-2:]}"
    return f"{text[:4]}****{text[-2:]}"


def _is_invalid_phone_otp_response(result: dict) -> bool:
    status = int((result or {}).get("status") or 0)
    if status != 400:
        return False
    data = (result or {}).get("data")
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "").lower()
            code = str(error.get("code") or "").lower()
            return code == "invalid_input" and "invalid otp code" in message
    text = str((result or {}).get("text") or "").lower()
    return "invalid otp code" in text


def _handle_add_phone_challenge(
    page,
    phone_callback,
    *,
    device_id: str,
    user_agent: str,
    log,
    log_key: Optional[Callable[[str, dict], None]] = None,
    resume_url: str = "",
    max_phone_attempts: int = 3,
) -> dict:
    """在 add-phone 页面通过 UI 交互完成手机号验证。

    流程: 选择国家 -> 输入本地号码 -> 点击发送 -> 填写 OTP -> 点击验证。
    如果验证码超时未收到，自动换号重试（最多 max_phone_attempts 次）。

    Complete phone verification via UI interaction on the add-phone page.

    Flow: select country -> enter local number -> click send -> fill in the
    OTP -> click verify. If the OTP times out without arriving, automatically
    retry with a new number (up to max_phone_attempts times).
    """
    if not phone_callback:
        _raise_keyed(RuntimeError, "chatgpt.52d3c834")
        # was: raise RuntimeError("ChatGPT 注册遇到手机号验证，但未配置 phone_callback。" "请在 RegisterConfig.extra 中配置接码服务，或手动完成手机验证。") —
        # was: raise RuntimeError("ChatGPT registration hit phone verification, but no phone_callback is configured." " Configure an SMS-receiving service in RegisterConfig.extra, or complete phone verification manually.")

    last_error = None
    for phone_attempt in range(max_phone_attempts):
        if phone_attempt > 0:
            _emit_log_key(log, log_key, "chatgpt.922bf0d7", attempt=phone_attempt + 1, max_phone_attempts=max_phone_attempts)
            # was: log(f"换号重试第 {phone_attempt + 1}/{max_phone_attempts} 次...") —
            # was: log(f"Retrying with a new number, attempt {phone_attempt + 1}/{max_phone_attempts}...")
            # 回到 add-phone 页面 — Go back to the add-phone page
            try:
                page.goto(f"{OPENAI_AUTH}/add-phone", wait_until="domcontentloaded", timeout=15000)
                time.sleep(1)
            except Exception:
                pass

        try:
            result = _do_add_phone_attempt(
                page, phone_callback,
                device_id=device_id, user_agent=user_agent,
                log=log, log_key=log_key, resume_url=resume_url,
            )
            return result
        except RuntimeError as exc:
            last_error = exc
            error_msg = str(exc)
            # 验证码超时或号码已被使用时换号重试，其他错误直接抛出 —
            # Retry with a new number when the code times out or the number is already in use; raise other errors directly
            should_retry = (
                "未获取到短信验证码" in error_msg
                or "phone_number_in_use" in error_msg
                or "already" in error_msg.lower()
                or "in use" in error_msg.lower()
            )
            if not should_retry:
                raise
            _emit_log_key(log, log_key, "chatgpt.888f4570")
            # was: log(f"⚠️ 验证码超时未收到，准备换号重试...") —
            # was: log(f"⚠️ Verification code timed out, preparing to retry with a new number...")
            # 取消当前号码 — Cancel the current number
            if hasattr(phone_callback, "cleanup"):
                phone_callback.cleanup()
            # 重置 phone_callback 状态为 need_number — Reset phone_callback state to need_number
            if hasattr(phone_callback, "phase"):
                phone_callback.phase = "need_number"
                phone_callback.activation = None
                phone_callback.completed = False

    raise last_error or _raise_keyed(RuntimeError, "chatgpt.fb4b66a0")
    # was: raise last_error or RuntimeError("短信验证失败: 多次换号均未收到验证码") —
    # was: raise last_error or RuntimeError("SMS verification failed: no code received after multiple number changes")


def _do_add_phone_attempt(
    page,
    phone_callback,
    *,
    device_id: str,
    user_agent: str,
    log,
    log_key: Optional[Callable[[str, dict], None]] = None,
    resume_url: str = "",
) -> dict:
    """单次手机号验证尝试（内部函数）。 — A single phone-verification attempt (internal function)."""

    # 保留 HTTP resend 回调供 SMS provider 内部使用 — Keep the HTTP resend callback for internal use by the SMS provider
    referer = _normalize_url(str(page.url or ""), OPENAI_AUTH) or f"{OPENAI_AUTH}/add-phone"
    headers = _build_browser_headers(
        user_agent=user_agent,
        accept="application/json",
        referer=referer,
        origin=OPENAI_AUTH,
        content_type="application/json",
        extra_headers={
            "sec-fetch-site": "same-origin",
            "oai-device-id": device_id,
            **_generate_datadog_trace_headers(),
        },
    )

    def _request_openai_resend():
        # 浏览器模式下只通过页面 UI 点击 Resend 按钮 — In browser mode, only click the Resend button via the page UI
        resend_clicked = _click_first(page, [
            'button:has-text("Resend")',
            'button:has-text("resend")',
            'button:has-text("Resend code")',
            'button:has-text("重新发送")',
            'a:has-text("Resend")',
            'a:has-text("resend")',
            'a:has-text("Resend code")',
        ], timeout=3)
        if resend_clicked:
            _emit_log_key(log, log_key, "chatgpt.a825846a", resend_clicked=resend_clicked)
            # was: log(f"  phone-otp/resend -> 已点击页面 Resend 按钮: {resend_clicked}") —
            # was: log(f"  phone-otp/resend -> clicked the page's Resend button: {resend_clicked}")
        else:
            _emit_log_key(log, log_key, "chatgpt.61a78d06")
            # was: log("  phone-otp/resend -> 页面未找到 Resend 按钮，跳过（浏览器模式不走 HTTP）") —
            # was: log("  phone-otp/resend -> Resend button not found on page, skipping (browser mode doesn't use HTTP)")

    if hasattr(phone_callback, "set_resend_callback"):
        phone_callback.set_resend_callback(_request_openai_resend)

    # ---- 第1步: 获取手机号 ---- — ---- Step 1: Get phone number ----
    _emit_log_key(log, log_key, "chatgpt.fb273255")
    # was: log("注册流程已进入 add_phone，开始准备租号并接收短信验证码...") —
    # was: log("Registration flow entered add_phone, preparing to rent a number and receive the SMS code...")
    phone_number = str(phone_callback() or "").strip()
    if not phone_number:
        _raise_keyed(RuntimeError, "chatgpt.0755ba30")
        # was: raise RuntimeError("未获取到手机号") — was: raise RuntimeError("Failed to obtain a phone number")
    _emit_log_key(log, log_key, "chatgpt.a4038235", val=_mask_phone_number(phone_number))
    # was: log(f"检测到 add_phone，提交手机号(UI): {_mask_phone_number(phone_number)}") —
    # was: log(f"Detected add_phone, submitting phone number (UI): {_mask_phone_number(phone_number)}")

    # 解析国家拨号码和本地号码 — Parse the country dial code and local number
    dial_code, local_number, country_name = _parse_phone_country_and_local(phone_number)
    _emit_log_key(log, log_key, "chatgpt.49a9af86", country=country_name or '未知', dial_code=dial_code, local=local_number[:4])
    # was: log(f"  解析号码: 国家={country_name or '未知'} 拨号码=+{dial_code} 本地号={local_number[:4]}...") —
    # was: log(f"  Parsed number: country={country_name or 'unknown'} dial_code=+{dial_code} local={local_number[:4]}...")

    # 确保在 add-phone 页面 — Make sure we're on the add-phone page
    current_url = str(page.url or "")
    if "add-phone" not in current_url:
        page.goto(f"{OPENAI_AUTH}/add-phone", wait_until="domcontentloaded", timeout=30000)
    time.sleep(1)

    # ---- 第2步: 选择国家 ---- — ---- Step 2: Select country ----
    country_selected = _select_phone_country_ui(page, dial_code, country_name, log, log_key)
    _browser_pause(page)

    # ---- 第3步: 填写手机号 ---- — ---- Step 3: Fill in phone number ----
    phone_input_sel = _wait_for_any_selector(page, PHONE_INPUT_SELECTORS, timeout=10)
    if phone_input_sel:
        # 如果成功选了国家，输入本地号码；否则输入完整号码 —
        # If the country was selected successfully, enter the local number; otherwise enter the full number
        fill_value = local_number if country_selected else phone_number
        filled = _fill_input_like_user(page, phone_input_sel, fill_value)
        # _fill_input_like_user 用严格相等验证，但 add-phone 页面可能在 input 中自动加了国家前缀
        # 所以额外检查 input.value 是否包含我们填入的号码
        # _fill_input_like_user checks for strict equality, but the add-phone page may auto-prepend a country prefix in the input
        # so also check whether input.value contains the number we entered
        if not filled:
            try:
                actual_val = str(page.evaluate(
                    "(sel) => { const el = document.querySelector(sel); return el ? el.value : ''; }",
                    phone_input_sel,
                ) or "")
                # 如果 input 值包含我们的号码（可能前面有 +56 之类的前缀），认为成功 —
                # If the input value contains our number (possibly with a prefix like +56), treat it as success
                if fill_value and fill_value in actual_val.replace(" ", "").replace("-", ""):
                    filled = True
                    _emit_log_key(log, log_key, "chatgpt.7a6aa18d", value=actual_val[:12])
                    # was: log(f"  手机号已填写(含前缀): {actual_val[:12]}...") —
                    # was: log(f"  Phone number filled (with prefix): {actual_val[:12]}...")
            except Exception:
                pass
        if not filled:
            # fallback: 尝试先清空再用 keyboard.type 输入 — fallback: try clearing the field first, then type via keyboard.type
            _emit_log_key(log, log_key, "chatgpt.51fa337c")
            # was: log(f"  _fill_input_like_user 失败，尝试 keyboard fallback...") —
            # was: log(f"  _fill_input_like_user failed, trying keyboard fallback...")
            try:
                page.click(phone_input_sel)
                time.sleep(0.3)
                # 三次全选删除确保清空 — Select all and delete three times to make sure the field is cleared
                for _ in range(3):
                    page.keyboard.press("Meta+a")
                    time.sleep(0.1)
                    page.keyboard.press("Backspace")
                    time.sleep(0.1)
                page.keyboard.type(fill_value, delay=random.randint(30, 70))
                time.sleep(0.3)
                # 验证输入值 — Verify the entered value
                actual = page.evaluate(
                    "(sel) => { const el = document.querySelector(sel); return el ? el.value : ''; }",
                    phone_input_sel,
                )
                actual_clean = str(actual or "").replace(" ", "").replace("-", "")
                if fill_value in actual_clean:
                    filled = True
                    _emit_log_key(log, log_key, "chatgpt.88703380", value=str(actual or '')[:12])
                    # was: log(f"  keyboard fallback 成功: {str(actual or '')[:12]}...") —
                    # was: log(f"  keyboard fallback succeeded: {str(actual or '')[:12]}...")
            except Exception as e:
                _emit_log_key(log, log_key, "chatgpt.1cef2160", e=e)
                # was: log(f"  keyboard fallback 失败: {e}") — was: log(f"  keyboard fallback failed: {e}")
        if not filled:
            # 最终 fallback: 直接用 JS 设置值 — final fallback: set the value directly via JS
            try:
                js_ok = page.evaluate(
                    """
                    ({ selector, value }) => {
                      const input = document.querySelector(selector);
                      if (!input) return false;
                      input.focus();
                      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                      if (setter) setter.call(input, value);
                      else input.value = value;
                      input.dispatchEvent(new Event('input', { bubbles: true }));
                      input.dispatchEvent(new Event('change', { bubbles: true }));
                      // 也触发 React 合成事件
                      const nativeEvent = new Event('input', { bubbles: true });
                      Object.defineProperty(nativeEvent, 'target', { writable: false, value: input });
                      input.dispatchEvent(nativeEvent);
                      return input.value.includes(value);
                    }
                    """,
                    {"selector": phone_input_sel, "value": fill_value},
                )
                if js_ok:
                    filled = True
                    _emit_log_key(log, log_key, "chatgpt.8e55cc66")
                    # was: log(f"  JS setValue fallback 成功") — was: log(f"  JS setValue fallback succeeded")
            except Exception as e:
                _emit_log_key(log, log_key, "chatgpt.89324a6f", e=e)
                # was: log(f"  JS setValue fallback 失败: {e}") — was: log(f"  JS setValue fallback failed: {e}")
        if not filled:
            _raise_keyed(RuntimeError, "chatgpt.0d08959b", phone_input_sel=phone_input_sel)
            # was: raise RuntimeError(f"手机号输入框填写失败: {phone_input_sel}") —
            # was: raise RuntimeError(f"Phone number input fill failed: {phone_input_sel}")
        _emit_log_key(log, log_key, "chatgpt.a610607d", phone_input_sel=phone_input_sel, value=fill_value[:4])
        # was: log(f"  手机号输入框已填写: {phone_input_sel} value={fill_value[:4]}...") —
        # was: log(f"  Phone number input filled: {phone_input_sel} value={fill_value[:4]}...")
    else:
        _raise_keyed(RuntimeError, "chatgpt.0383ea57")
        # was: raise RuntimeError("未找到手机号输入框") — was: raise RuntimeError("Phone number input not found")
    _browser_pause(page)

    # ---- 第4步: 点击发送按钮 ---- — ---- Step 4: Click the send button ----
    send_sel = _click_first(page, PHONE_SEND_SELECTORS, timeout=8)
    if send_sel:
        _emit_log_key(log, log_key, "chatgpt.f6aae652", send_sel=send_sel)
        # was: log(f"  已点击发送按钮: {send_sel}") — was: log(f"  Clicked the send button: {send_sel}")
    elif _submit_form_with_fallback(page, phone_input_sel):
        _emit_log_key(log, log_key, "chatgpt.a0ffd85e")
        # was: log("  未找到发送按钮，已使用表单 fallback 提交") — was: log("  Send button not found, submitted via form fallback")
    else:
        _raise_keyed(RuntimeError, "chatgpt.40c0fbdc")
        # was: raise RuntimeError("未找到发送验证码按钮") — was: raise RuntimeError("Send-code button not found")

    # 等待页面响应（可能显示 OTP 输入框或错误） — Wait for the page response (may show an OTP input or an error)
    time.sleep(2)

    # 检查发送是否成功（页面应出现 OTP 输入框或 URL 变化） —
    # Check whether the send succeeded (page should show an OTP input or the URL should change)
    error_text = _extract_auth_error_text(page)
    if error_text:
        if hasattr(phone_callback, "mark_send_failed"):
            phone_callback.mark_send_failed(error_text)
        _raise_keyed(RuntimeError, "chatgpt.0b04c013", val=error_text[:200])
        # was: raise RuntimeError(f"手机号提交失败: {error_text[:200]}") —
        # was: raise RuntimeError(f"Phone number submission failed: {error_text[:200]}")

    if hasattr(phone_callback, "mark_send_succeeded"):
        phone_callback.mark_send_succeeded()
    _emit_log_key(log, log_key, "chatgpt.093b8849")
    # was: log("手机号提交成功(UI)，开始等待短信验证码...") —
    # was: log("Phone number submitted successfully (UI), waiting for the SMS code...")

    # ---- 第5步: 等待 SMS 验证码并在页面 OTP 输入框中填写 ---- —
    # ---- Step 5: Wait for the SMS code and fill it into the page's OTP input ----
    for code_attempt in range(3):
        sms_code = str(phone_callback() or "").strip()
        if not sms_code:
            _raise_keyed(RuntimeError, "chatgpt.ef43f923")
            # was: raise RuntimeError("未获取到短信验证码") — was: raise RuntimeError("Failed to obtain the SMS code")

        # 等待 OTP 输入框出现 — Wait for the OTP input to appear
        otp_sel = _wait_for_any_selector(page, OTP_INPUT_SELECTORS, timeout=10)
        if not otp_sel:
            # 尝试用 phone input selectors 作为 OTP（某些版本页面复用同一 input） —
            # Try using the phone input selectors as OTP (some page versions reuse the same input)
            otp_sel = _find_first_selector(page, PHONE_INPUT_SELECTORS)
        if not otp_sel:
            _raise_keyed(RuntimeError, "chatgpt.8af216a9")
            # was: raise RuntimeError("未找到短信验证码输入框") — was: raise RuntimeError("SMS code input not found")

        # 使用与邮箱 OTP 相同的填写逻辑 — Use the same fill logic as the email OTP
        otp_resp = _submit_otp_via_page(page, sms_code, log, log_key)
        otp_status = int(otp_resp.get("status") or 0)
        _emit_log_key(log, log_key, "chatgpt.04c00651", otp_status=otp_status)
        # was: log(f"  phone-otp 页面提交状态: {otp_status}") — was: log(f"  phone-otp page submit status: {otp_status}")

        if otp_resp.get("ok") or otp_status in (200, 201, 204):
            if hasattr(phone_callback, "report_success"):
                phone_callback.report_success()
            # 等待页面跳转 — Wait for the page to navigate
            time.sleep(1.5)
            state = _extract_flow_state(
                otp_resp.get("data"),
                otp_resp.get("url", page.url),
            )
            if not state.get("page_type"):
                state = _derive_registration_state_from_page(page)
            next_url = _normalize_url(resume_url, OPENAI_AUTH) if resume_url else ""
            if next_url:
                page.goto(next_url, wait_until="domcontentloaded", timeout=30000)
                return _extract_flow_state(None, page.url)
            return state

        # 检查是否是无效验证码 — Check whether the code is invalid
        page_error = _extract_auth_error_text(page)
        if page_error and any(kw in page_error.lower() for kw in ("invalid", "incorrect", "wrong", "expired")):
            _emit_log_key(log, log_key, "chatgpt.b0b9433c", error=page_error[:100])
            # was: log(f"短信验证码被判定无效: {page_error[:100]}，继续等待下一条...") —
            # was: log(f"SMS code judged invalid: {page_error[:100]}, waiting for the next one...")
            if hasattr(phone_callback, "mark_code_failed"):
                phone_callback.mark_code_failed(page_error or "invalid otp code")
            continue

        if hasattr(phone_callback, "mark_code_failed"):
            phone_callback.mark_code_failed(page_error or f"status {otp_status}")
        _raise_keyed(RuntimeError, "chatgpt.b30e850f", detail=page_error[:200] if page_error else f'status {otp_status}')
        # was: raise RuntimeError(f"短信验证码校验失败: {page_error[:200] if page_error else f'status {otp_status}'}") —
        # was: raise RuntimeError(f"SMS code verification failed: {page_error[:200] if page_error else f'status {otp_status}'}")

    _raise_keyed(RuntimeError, "chatgpt.4b2ba617")
    # was: raise RuntimeError("短信验证码校验失败: 多次验证码均无效或未通过") —
    # was: raise RuntimeError("SMS code verification failed: multiple codes were invalid or rejected")


def _requires_registration_navigation(state: dict) -> bool:
    if str(state.get("method") or "GET").upper() != "GET":
        return False
    if str(state.get("page_type") or "") == "external_url" and state.get("continue_url"):
        return True
    continue_url = str(state.get("continue_url") or "")
    current_url = str(state.get("current_url") or "")
    return bool(continue_url and continue_url != current_url)


def _browser_add_cookies(page, cookies: list[dict]) -> None:
    try:
        page.context.add_cookies(cookies)
    except Exception:
        pass


def _seed_browser_device_id(page, device_id: str) -> None:
    _browser_add_cookies(
        page,
        [
            {"name": "oai-did", "value": device_id, "domain": "chatgpt.com", "path": "/"},
            {"name": "oai-did", "value": device_id, "domain": ".chatgpt.com", "path": "/"},
            {"name": "oai-did", "value": device_id, "domain": "openai.com", "path": "/"},
            {"name": "oai-did", "value": device_id, "domain": "auth.openai.com", "path": "/"},
            {"name": "oai-did", "value": device_id, "domain": ".auth.openai.com", "path": "/"},
        ],
    )


def _get_browser_csrf_token(page) -> str:
    result = _browser_fetch(
        page,
        f"{CHATGPT_APP}/api/auth/csrf",
        method="GET",
        headers={
            "accept": "application/json",
            "referer": f"{CHATGPT_APP}/",
            "sec-fetch-site": "same-origin",
        },
        redirect="follow",
    )
    if result.get("ok") and isinstance(result.get("data"), dict):
        return str((result.get("data") or {}).get("csrfToken") or "").strip()
    return ""


def _start_browser_signin(page, email: str, device_id: str, csrf_token: str) -> str:
    from urllib.parse import urlencode

    query = urlencode(
        {
            "prompt": "login",
            "ext-oai-did": device_id,
            "auth_session_logging_id": str(uuid.uuid4()),
            "screen_hint": "login_or_signup",
            "login_hint": email,
        }
    )
    body = urlencode(
        {
            "callbackUrl": f"{CHATGPT_APP}/",
            "csrfToken": csrf_token,
            "json": "true",
        }
    )
    result = _browser_fetch(
        page,
        f"{CHATGPT_APP}/api/auth/signin/openai?{query}",
        method="POST",
        headers={
            "accept": "application/json",
            "referer": f"{CHATGPT_APP}/",
            "origin": CHATGPT_APP,
            "content-type": "application/x-www-form-urlencoded",
            "sec-fetch-site": "same-origin",
        },
        body=body,
        redirect="follow",
    )
    if result.get("ok") and isinstance(result.get("data"), dict):
        return str((result.get("data") or {}).get("url") or "").strip()
    return ""


def _browser_authorize(page, auth_url: str, log, log_key: Optional[Callable[[str, dict], None]] = None) -> str:
    if not auth_url:
        return ""
    try:
        page.goto(auth_url, wait_until="domcontentloaded", timeout=30000)
        final_url = page.url
        log(f"Authorize -> {final_url[:120]}")
        return final_url
    except Exception as exc:
        _emit_log_key(log, log_key, "chatgpt.61d5f6a7", exc=exc)
        # was: log(f"Authorize 失败: {exc}") — was: log(f"Authorize failed: {exc}")
        return ""


def _validate_browser_email_otp(page, code: str, device_id: str, user_agent: str, referer: str) -> dict:
    headers = _build_browser_headers(
        user_agent=user_agent,
        accept="application/json",
        referer=referer or f"{OPENAI_AUTH}/email-verification",
        origin=OPENAI_AUTH,
        content_type="application/json",
        extra_headers={
            "sec-fetch-site": "same-origin",
            "oai-device-id": device_id,
            **_generate_datadog_trace_headers(),
        },
    )
    sentinel = _build_browser_sentinel_token(page, device_id, "email_otp_validate", user_agent)
    if sentinel:
        headers["openai-sentinel-token"] = sentinel
    _browser_pause(page)
    return _browser_fetch(
        page,
        f"{OPENAI_AUTH}/api/accounts/email-otp/validate",
        method="POST",
        headers=headers,
        body=json.dumps({"code": code}),
        redirect="follow",
    )


def _submit_browser_about_you(page, device_id: str, user_agent: str, referer: str) -> dict:
    from .constants import generate_random_user_info

    headers = _build_browser_headers(
        user_agent=user_agent,
        accept="application/json",
        referer=referer or f"{OPENAI_AUTH}/about-you",
        origin=OPENAI_AUTH,
        content_type="application/json",
        extra_headers={
            "sec-fetch-site": "same-origin",
            "oai-device-id": device_id,
            **_generate_datadog_trace_headers(),
        },
    )
    sentinel = _build_browser_sentinel_token(page, device_id, "oauth_create_account", user_agent)
    if sentinel:
        headers["openai-sentinel-token"] = sentinel
    user_info = generate_random_user_info()
    _browser_pause(page)
    return _browser_fetch(
        page,
        f"{OPENAI_AUTH}/api/accounts/create_account",
        method="POST",
        headers=headers,
        body=json.dumps(user_info),
        redirect="follow",
    )


def _complete_oauth_in_browser(page, oauth_start, proxy, log, log_key: Optional[Callable[[str, dict], None]] = None) -> dict | None:
    """在浏览器里完成 OAuth consent 流程，多策略重试点击 Continue。

    参考 Chrome 扩展项目的 step9 实现:
    - consent 页面是一个 <form action="/sign-in-with-chatgpt/.../consent">
    - 首选 form.requestSubmit(button) 而非 button.click()
    - 多轮重试: requestSubmit → click → dispatchEvent → 刷新重试

    Complete the OAuth consent flow in the browser, retrying the Continue
    click with multiple strategies.

    Modeled on the Chrome-extension reference project's step9 implementation:
    - The consent page is a <form action="/sign-in-with-chatgpt/.../consent">
    - Prefer form.requestSubmit(button) over button.click()
    - Multi-round retry: requestSubmit -> click -> dispatchEvent -> refresh and retry
    """
    from .oauth import submit_callback_url

    CONSENT_FORM_SEL = OAUTH_CONSENT_FORM_SELECTOR
    MAX_ROUNDS = 4
    CLICK_EFFECT_TIMEOUT = 30

    def _try_extract_callback(url: str) -> dict | None:
        if not url or "code=" not in url:
            return None
        try:
            return json.loads(submit_callback_url(
                callback_url=url,
                expected_state=oauth_start.state,
                code_verifier=oauth_start.code_verifier,
                redirect_uri=oauth_start.redirect_uri,
                client_id=oauth_start.client_id,
                proxy_url=proxy,
            ))
        except ValueError as ve:
            # state 缺失或不匹配时，如果 URL 确实是我们的 callback，跳过 state 验证直接换 token —
            # If state is missing/mismatched but the URL is genuinely our callback, skip state validation and exchange the code directly
            if "state" in str(ve) and "localhost" in url and "code=" in url:
                try:
                    # 手动提取 code，跳过 state 验证 — Manually extract the code, skipping state validation
                    from urllib.parse import urlparse, parse_qs
                    parsed = urlparse(url)
                    params = parse_qs(parsed.query)
                    code = (params.get("code") or [""])[0]
                    if code:
                        from .oauth import _post_form, _jwt_claims_no_verify, OAUTH_TOKEN_URL
                        import time as _time
                        token_resp = _post_form(
                            OAUTH_TOKEN_URL,
                            {
                                "grant_type": "authorization_code",
                                "client_id": oauth_start.client_id,
                                "code": code,
                                "redirect_uri": oauth_start.redirect_uri,
                                "code_verifier": oauth_start.code_verifier,
                            },
                            proxy_url=proxy,
                        )
                        access_token = (token_resp.get("access_token") or "").strip()
                        refresh_token = (token_resp.get("refresh_token") or "").strip()
                        id_token = (token_resp.get("id_token") or "").strip()
                        if access_token:
                            claims = _jwt_claims_no_verify(id_token)
                            auth_claims = claims.get("https://api.openai.com/auth") or {}
                            now = int(_time.time())
                            expires_in = int(token_resp.get("expires_in") or 0)
                            return {
                                "id_token": id_token,
                                "access_token": access_token,
                                "refresh_token": refresh_token,
                                "account_id": str(auth_claims.get("chatgpt_account_id") or ""),
                                "email": str(claims.get("email") or ""),
                                "expired": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime(now + max(expires_in, 0))),
                                "last_refresh": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime(now)),
                            }
                except Exception:
                    pass
            return None
        except Exception:
            return None

    def _check_current_url() -> dict | None:
        url = str(page.url or "")
        result = _try_extract_callback(url)
        if result:
            return result
        cb = _extract_callback_url_from_exception(Exception(url))
        return _try_extract_callback(cb) if cb else None

    def _wait_for_callback(timeout_sec: int) -> dict | None:
        deadline = time.time() + timeout_sec
        checked_urls = set()
        while time.time() < deadline:
            try:
                url = str(page.url or "")
            except Exception:
                url = ""
            if url and url not in checked_urls:
                checked_urls.add(url)
                if "code=" in url or "localhost" in url:
                    _emit_log_key(log, log_key, "chatgpt.aa8c25ba", url=url[:150])
                    # was: log(f"  [callback_wait] 检测到 URL 变化: {url[:150]}") — [callback_wait] detected a URL change
            result = _check_current_url()
            if result:
                return result
            # 也检查是否有导航到 localhost 的请求（即使页面加载失败） — Also check for a navigation to localhost (even if the page load failed)
            if "localhost" in url and "code=" in url:
                result = _try_extract_callback(url)
                if result:
                    return result
            time.sleep(0.8)
        # 最后再检查一次 — One final check
        try:
            final_url = str(page.url or "")
            if "code=" in final_url:
                _emit_log_key(log, log_key, "chatgpt.7c61dd82", url=final_url[:150])
                # was: log(f"  [callback_wait] 超时后最终 URL: {final_url[:150]}") — [callback_wait] final URL after timeout
                result = _try_extract_callback(final_url)
                if result:
                    return result
        except Exception:
            pass
        return None

    def _find_consent_button():
        """按优先级查找 consent 页面的 Continue 按钮 — Find the consent page's Continue button, by priority."""
        # 策略 1: 在 consent form 内找 submit 按钮 — Strategy 1: find the submit button inside the consent form
        _sel = CONSENT_FORM_SEL
        btn = page.evaluate("""(sel) => {
            const form = document.querySelector(sel);
            if (!form) return null;
            const buttons = form.querySelectorAll('button[type="submit"], input[type="submit"], [role="button"]');
            for (const el of buttons) {
                if (el.offsetParent === null) continue;
                const text = (el.textContent || '').trim().toLowerCase();
                const ddName = el.getAttribute('data-dd-action-name') || '';
                if (ddName === 'Continue' || /continue|继续|continuar|fortfahren|continuer|続ける/i.test(text)) return 'form-continue';
            }
            const first = Array.from(buttons).find(el => el.offsetParent !== null);
            if (first) return 'form-submit';
            return null;
        }""", _sel)
        if btn:
            return btn
        # 策略 2: 全局查找 Continue 按钮 — Strategy 2: search the whole page for a Continue button
        for sel in [
            'button[type="submit"][data-dd-action-name="Continue"]',
            'button:has-text("Continue")',
            'button:has-text("继续")',
            'button:has-text("Continuar")',
            'button:has-text("Fortfahren")',
            'button:has-text("Continuer")',
            'button:has-text("Allow")',
            'button:has-text("Authorize")',
            'button[type="submit"]',
        ]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=500):
                    return sel
            except Exception:
                continue
        return None

    def _click_strategy_request_submit(log_round: int) -> bool:
        """策略 1: form.requestSubmit(button) — 最可靠的表单提交方式 — Strategy 1: form.requestSubmit(button), the most reliable way to submit the form"""
        try:
            result = page.evaluate("""(sel) => {
                const form = document.querySelector(sel);
                if (!form) return 'no-form';
                const buttons = form.querySelectorAll('button[type="submit"], input[type="submit"]');
                let target = null;
                for (const el of buttons) {
                    if (el.offsetParent === null) continue;
                    const text = (el.textContent || '').trim().toLowerCase();
                    const ddName = el.getAttribute('data-dd-action-name') || '';
                    if (ddName === 'Continue' || /continue|继续|continuar|fortfahren|continuer/i.test(text)) { target = el; break; }
                }
                if (!target) target = Array.from(buttons).find(el => el.offsetParent !== null);
                if (!target) return 'no-button';
                if (typeof form.requestSubmit === 'function') {
                    form.requestSubmit(target);
                    return 'requestSubmit';
                }
                target.click();
                return 'click-fallback';
            }""", CONSENT_FORM_SEL)
            _emit_log_key(log, log_key, "chatgpt.163ff0b9", log_round=log_round, result=result)
            # was: log(f"  consent 第{log_round}轮 requestSubmit: {result}") — consent round {log_round} requestSubmit result
            return result not in ("no-form", "no-button")
        except Exception as e:
            _emit_log_key(log, log_key, "chatgpt.b10852d7", e=e)
            # was: log(f"  consent requestSubmit 异常: {e}") — consent requestSubmit exception
            return False

    def _click_strategy_playwright(log_round: int) -> bool:
        """策略 2: Playwright locator.click() — Strategy 2: Playwright locator.click()"""
        for sel in [
            'button:has-text("Continue")',
            'button:has-text("继续")',
            'button:has-text("Continuar")',
            'button:has-text("Fortfahren")',
            'button:has-text("Continuer")',
            'button[type="submit"]',
        ]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=1500):
                    loc.click()
                    _emit_log_key(log, log_key, "chatgpt.028deb05", log_round=log_round, sel=sel)
                    # was: log(f"  consent 第{log_round}轮 playwright click: {sel}") — consent round {log_round} playwright click selector
                    return True
            except Exception:
                continue
        return False

    def _click_strategy_js_dispatch(log_round: int) -> bool:
        """策略 3: JS dispatchEvent 模拟点击 — Strategy 3: simulate a click via JS dispatchEvent"""
        try:
            result = page.evaluate("""() => {
                const buttons = document.querySelectorAll('button, [role="button"]');
                for (const el of buttons) {
                    if (el.offsetParent === null) continue;
                    const text = (el.textContent || '').trim().toLowerCase();
                    const ddName = el.getAttribute('data-dd-action-name') || '';
                    if (ddName === 'Continue' || /continue|继续|continuar|fortfahren|continuer/i.test(text)) {
                        el.focus();
                        el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                        return text || 'dispatched';
                    }
                }
                return null;
            }
            """)
            if result:
                _emit_log_key(log, log_key, "chatgpt.8093899f", log_round=log_round, result=result)
                # was: log(f"  consent 第{log_round}轮 JS dispatch: {result}") — consent round {log_round} JS dispatch result
                return True
            return False
        except Exception:
            return False

    strategies = [
        _click_strategy_request_submit,
        _click_strategy_playwright,
        _click_strategy_js_dispatch,
        _click_strategy_request_submit,
    ]

    try:
        current_url = str(page.url or "")
        _emit_log_key(log, log_key, "chatgpt.b870d449", url=current_url[:100])
        # was: log(f"  浏览器 consent 处理: {current_url[:100]}") — browser consent handling, current URL

        # 先检查当前 URL 是否已经有 code — First check whether the current URL already carries a code
        result = _check_current_url()
        if result:
            _emit_log_key(log, log_key, "chatgpt.a57282ac")
            # was: log("  ✓ 页面已在 callback URL") — page is already at the callback URL
            return result

        # 等待页面加载 — Wait for the page to load
        try:
            page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        time.sleep(1)

        # 检查 "Try again" 按钮 — Check for a "Try again" button
        try:
            try_again = page.query_selector('button:has-text("Try again")')
            if try_again and try_again.is_visible():
                _emit_log_key(log, log_key, "chatgpt.aa65104a")
                # was: log("  consent 页面报错，点击 Try again...") — consent page showed an error, clicking Try again...
                try_again.click()
                time.sleep(3)
        except Exception:
            pass

        # 多轮策略重试 — Retry across multiple rounds of strategies
        for round_idx in range(MAX_ROUNDS):
            result = _check_current_url()
            if result:
                _emit_log_key(log, log_key, "chatgpt.8c003840")
                # was: log("  ✓ 浏览器 OAuth consent 完成") — browser OAuth consent complete
                return result

            strategy_fn = strategies[min(round_idx, len(strategies) - 1)]
            clicked = strategy_fn(round_idx + 1)

            if clicked:
                # consent 提交后会跳转到 localhost:1455/auth/callback —
                # After the consent submits, it redirects to localhost:1455/auth/callback
                # 由于没有本地服务监听，浏览器可能报连接错误，但 URL 已经更新 —
                # Since nothing is listening locally, the browser may report a connection error, but the URL has already updated
                try:
                    page.wait_for_url("**/auth/callback*", timeout=15000)
                except Exception:
                    pass  # 超时或导航错误都忽略，下面会检查 URL — Ignore timeout/navigation errors; the URL is checked below
                time.sleep(1)
                result = _wait_for_callback(CLICK_EFFECT_TIMEOUT)
                if result:
                    _emit_log_key(log, log_key, "chatgpt.8c003840")
                    # was: log("  ✓ 浏览器 OAuth consent 完成") — browser OAuth consent complete
                    return result
                _emit_log_key(log, log_key, "chatgpt.b5db7dca", round=round_idx + 1)
                # was: log(f"  consent 第{round_idx + 1}轮点击后页面未跳转") — consent round {round_idx + 1}: page did not navigate after clicking
            else:
                _emit_log_key(log, log_key, "chatgpt.eecdb39f", round=round_idx + 1)
                # was: log(f"  consent 第{round_idx + 1}轮未找到按钮") — consent round {round_idx + 1}: no button found

            # 最后一轮前刷新页面重试 — Reload the page before the final round and retry
            if round_idx < MAX_ROUNDS - 1:
                _emit_log_key(log, log_key, "chatgpt.66e01add", round=round_idx + 2)
                # was: log(f"  consent 刷新页面准备第{round_idx + 2}轮...") — consent reloading page for round {round_idx + 2}...
                try:
                    page.reload(wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    pass
                time.sleep(2)

        _emit_log_key(log, log_key, "chatgpt.165a3014", MAX_ROUNDS=MAX_ROUNDS, url=str(page.url or '')[:100])
        # was: log(f"  consent {MAX_ROUNDS}轮尝试后仍未完成，当前: {str(page.url or '')[:100]}") — consent still incomplete after {MAX_ROUNDS} rounds, current URL
        return None
    except Exception as exc:
        cb = _extract_callback_url_from_exception(exc)
        if cb:
            result = _try_extract_callback(cb)
            if result:
                _emit_log_key(log, log_key, "chatgpt.bfef325c")
                # was: log("  ✓ 从异常中提取 callback 完成 OAuth") — extracted the callback from the exception and completed OAuth
                return result
        _emit_log_key(log, log_key, "chatgpt.49f69953", exc=exc)
        # was: log(f"  浏览器 OAuth consent 异常: {exc}") — browser OAuth consent exception
        return None


def _submit_oauth_password_direct(page, password: str, log, log_key: Optional[Callable[[str, dict], None]] = None) -> dict:
    """OAuth 流程专用：直接填密码登录，不尝试恢复到注册态。 — OAuth-flow-specific: fill in the password and log in directly, without trying to recover registration state."""
    input_selector = _wait_for_any_selector(page, PASSWORD_INPUT_SELECTORS, timeout=15)
    if not input_selector:
        # 密码输入框没出现，可能页面还在加载或跳转了 — The password input didn't appear; the page may still be loading or navigating
        # 等一下再试 — Wait a bit and try again
        time.sleep(2)
        input_selector = _wait_for_any_selector(page, PASSWORD_INPUT_SELECTORS, timeout=10)
    if not input_selector:
        _raise_keyed(RuntimeError, "chatgpt.f28d73e2")
        # was: raise RuntimeError("OAuth 密码页未找到输入框") — OAuth password page: input not found
    if not _fill_input_like_user(page, input_selector, password):
        _raise_keyed(RuntimeError, "chatgpt.eb4e1dfe")
        # was: raise RuntimeError("OAuth 密码页填写失败") — OAuth password page: fill failed
    _emit_log_key(log, log_key, "chatgpt.1a7a5b10", input_selector=input_selector)
    # was: log(f"  OAuth 密码页输入框: {input_selector}") — OAuth password page input selector
    _browser_pause(page)

    submit_selector = _click_first(page, PASSWORD_SUBMIT_SELECTORS, timeout=8)
    if submit_selector:
        _emit_log_key(log, log_key, "chatgpt.cc6da93d", submit_selector=submit_selector)
        # was: log(f"  OAuth 密码页已点击继续按钮: {submit_selector}") — OAuth password page: clicked the continue button
    elif _submit_form_with_fallback(page, input_selector):
        _emit_log_key(log, log_key, "chatgpt.a6073135")
        # was: log("  OAuth 密码页使用表单 fallback 提交") — OAuth password page: submitted via form fallback
    else:
        _raise_keyed(RuntimeError, "chatgpt.4cfd80e0")
        # was: raise RuntimeError("OAuth 密码页未找到 Continue 按钮") — OAuth password page: Continue button not found

    deadline = time.time() + 20
    while time.time() < deadline:
        current_url = str(page.url or "")
        state = _derive_registration_state_from_page(page)
        page_type = str(state.get("page_type") or "")
        if page_type in {"email_otp_verification", "about_you", "consent", "workspace_selection",
                         "organization_selection", "add_phone", "oauth_callback", "chatgpt_home", "external_url"}:
            return {"ok": True, "status": 200, "url": current_url, "data": None, "text": ""}
        if "code=" in current_url:
            return {"ok": True, "status": 200, "url": current_url, "data": None, "text": ""}
        error_text = _extract_auth_error_text(page)
        if error_text:
            return {"ok": False, "status": 400, "url": current_url, "data": None, "text": error_text}
        time.sleep(0.5)
    return {"ok": False, "status": 0, "url": str(page.url or ""), "data": None, "text": "OAuth 密码提交后未跳转"}


def _submit_password_via_page(page, password: str, log, log_key: Optional[Callable[[str, dict], None]] = None) -> dict:
    if _recover_signup_password_page(page, log, log_key):
        time.sleep(1)

    input_selector = _wait_for_any_selector(page, PASSWORD_INPUT_SELECTORS, timeout=15)
    if not input_selector:
        _raise_keyed(RuntimeError, "chatgpt.0543c072")
        # was: raise RuntimeError("密码页未找到输入框") — password page: input not found
    if not _fill_input_like_user(page, input_selector, password):
        _raise_keyed(RuntimeError, "chatgpt.708b2dd9")
        # was: raise RuntimeError("密码页填写失败") — password page: fill failed
    _emit_log_key(log, log_key, "chatgpt.d03c813e", input_selector=input_selector)
    # was: log(f"密码页输入框: {input_selector}") — password page input selector
    _browser_pause(page)

    start_url = str(page.url or "")
    submit_selector = _click_first(page, PASSWORD_SUBMIT_SELECTORS, timeout=8)
    if submit_selector:
        _emit_log_key(log, log_key, "chatgpt.b66a2726", submit_selector=submit_selector)
        # was: log(f"密码页已点击继续按钮: {submit_selector}") — password page: clicked the continue button
    elif _submit_form_with_fallback(page, input_selector):
        _emit_log_key(log, log_key, "chatgpt.9d760628")
        # was: log("密码页未找到可点击 Continue，已使用表单 fallback 提交") — password page: no clickable Continue found, submitted via form fallback
    else:
        _raise_keyed(RuntimeError, "chatgpt.ec32665c")
        # was: raise RuntimeError("密码页未找到 Continue 按钮") — password page: Continue button not found

    deadline = time.time() + 20
    last_url = str(page.url or "")
    while time.time() < deadline:
        current_url = str(page.url or "")
        last_url = current_url or last_url
        state = _derive_registration_state_from_page(page)
        page_type = str(state.get("page_type") or "")
        if page_type in {"email_otp_verification", "about_you", "add_phone", "oauth_callback", "chatgpt_home"}:
            return {"ok": True, "status": 200, "url": current_url, "data": None, "text": ""}
        if current_url != start_url and page_type and page_type not in {"create_account_password", "login_password"}:
            return {"ok": True, "status": 200, "url": current_url, "data": None, "text": ""}
        if page_type == "login_password" and _recover_signup_password_page(page, log, log_key):
            input_selector = _wait_for_any_selector(page, PASSWORD_INPUT_SELECTORS, timeout=5)
            if not input_selector:
                return {"ok": False, "status": 400, "url": current_url, "data": None, "text": "登录密码页恢复后未找到注册密码输入框"}
            if not _fill_input_like_user(page, input_selector, password):
                return {"ok": False, "status": 400, "url": current_url, "data": None, "text": "登录密码页恢复后密码重新填写失败"}
            submit_selector = _click_first(page, PASSWORD_SUBMIT_SELECTORS, timeout=5)
            if submit_selector:
                _emit_log_key(log, log_key, "chatgpt.ec4ed81b", submit_selector=submit_selector)
                # was: log(f"恢复后重新点击密码提交按钮: {submit_selector}") — after recovery, re-clicked the password submit button
                start_url = str(page.url or start_url)
                time.sleep(0.4)
                continue
            if _submit_form_with_fallback(page, input_selector):
                _emit_log_key(log, log_key, "chatgpt.4135c016")
                # was: log("恢复后未找到密码提交按钮，已使用表单 fallback 提交") — after recovery, no password submit button found; submitted via form fallback
                start_url = str(page.url or start_url)
                time.sleep(0.4)
                continue
            return {"ok": False, "status": 400, "url": current_url, "data": None, "text": "登录密码页恢复后未找到提交方式"}
        error_text = _extract_auth_error_text(page)
        if error_text:
            _dump_debug(page, "chatgpt_password_fail")
            return {"ok": False, "status": 400, "url": current_url, "data": None, "text": error_text}
        time.sleep(0.5)
    _dump_debug(page, "chatgpt_password_fail")
    return {"ok": False, "status": 0, "url": last_url, "data": None, "text": "密码页提交后未跳转"}


def _submit_otp_via_page(page, code: str, log, log_key: Optional[Callable[[str, dict], None]] = None) -> dict:
    otp = str(code or "").strip()
    if not otp:
        return {"ok": False, "status": 400, "url": page.url, "data": None, "text": "验证码为空"}

    # 等待页面加载完成，确保 OTP 输入框已渲染 — Wait for the page to finish loading so the OTP inputs are rendered
    try:
        page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass
    time.sleep(1)

    filled = False

    # 先尝试 6 格 OTP 输入框 — First try the 6-box OTP input layout
    try:
        digit_inputs = page.locator(
            "input[inputmode='numeric'], input[autocomplete='one-time-code'], input[type='tel'], input[type='number']"
        )
        count = digit_inputs.count()
        if count >= len(otp):
            done = 0
            for i in range(min(count, len(otp))):
                box = digit_inputs.nth(i)
                try:
                    box.wait_for(state="visible", timeout=800)
                    box.fill("")
                    box.type(otp[i], delay=random.randint(20, 60))
                    done += 1
                except Exception:
                    break
            if done >= len(otp):
                filled = True
                _emit_log_key(log, log_key, "chatgpt.4aeb6668", done=done)
                # was: log(f"验证码页已填写 {done} 位分格输入框") — OTP page: filled {done} boxes of the split input
    except Exception:
        pass

    # 再尝试单输入框 — Then try a single input box
    if not filled:
        otp_candidates = [
            page.get_by_label(re.compile(r"verification code|code|otp", re.IGNORECASE)),
            page.get_by_role("textbox", name=re.compile(r"verification code|code|otp", re.IGNORECASE)),
            page.locator("input[autocomplete='one-time-code']"),
            page.locator("input[name*='code' i]"),
            page.locator("input[id*='code' i]"),
            page.locator("input[type='text']"),
            page.locator("input"),
        ]
        for candidate in otp_candidates:
            try:
                target = candidate.first
                target.wait_for(state="visible", timeout=1200)
                target.click(timeout=1200)
                target.fill("")
                target.type(otp, delay=random.randint(18, 45))
                final_value = str(target.input_value() or "").strip()
                if final_value:
                    filled = True
                    _emit_log_key(log, log_key, "chatgpt.b497f65e")
                    # was: log("验证码页已填写单输入框") — OTP page: filled the single input box
                    break
            except Exception:
                continue

    if not filled:
        # 再等 3 秒重试一次（页面可能还在渲染） — Wait another 3 seconds and retry once (the page may still be rendering)
        time.sleep(3)
        otp_retry_selectors = [
            "input[inputmode='numeric']",
            "input[autocomplete='one-time-code']",
            "input[name*='code' i]",
            "input[type='text']",
        ]
        for sel in otp_retry_selectors:
            try:
                target = page.locator(sel).first
                if target.is_visible(timeout=2000):
                    target.click(timeout=1500)
                    target.fill("")
                    target.type(otp, delay=random.randint(18, 45))
                    if str(target.input_value() or "").strip():
                        filled = True
                        _emit_log_key(log, log_key, "chatgpt.98936a73")
                        # was: log("验证码页已填写单输入框(重试)") — OTP page: filled the single input box (retry)
                        break
            except Exception:
                continue

    if not filled:
        return {"ok": False, "status": 0, "url": page.url, "data": None, "text": "验证码页未找到可填写输入框"}

    _browser_pause(page)
    submit_selector = _click_first(
        page,
        [
            'button[type="submit"]',
            'button[data-testid="continue-button"]',
            'button:has-text("Continue")',
            'button:has-text("continue")',
            'button:has-text("Verify")',
            'button:has-text("verify")',
            'button:has-text("Next")',
            'button:has-text("next")',
        ],
        timeout=8,
    )
    if not submit_selector:
        return {"ok": False, "status": 0, "url": page.url, "data": None, "text": "验证码页未找到 Continue 按钮"}
    _emit_log_key(log, log_key, "chatgpt.6c6526d1", submit_selector=submit_selector)
    # was: log(f"验证码页已点击继续按钮: {submit_selector}") — OTP page: clicked the continue button

    deadline = time.time() + 20
    last_url = page.url
    while time.time() < deadline:
        current_url = page.url
        last_url = current_url or last_url
        if "about-you" in current_url:
            return {"ok": True, "status": 200, "url": current_url, "data": None, "text": ""}
        if "add-phone" in current_url or "chatgpt.com" in current_url or "code=" in current_url:
            return {"ok": True, "status": 200, "url": current_url, "data": None, "text": ""}
        if "consent" in current_url or "sign-in-with-chatgpt" in current_url or "workspace" in current_url or "organization" in current_url:
            return {"ok": True, "status": 200, "url": current_url, "data": None, "text": ""}
        try:
            error_text = page.locator("text=Invalid code").first.text_content(timeout=400)
        except Exception:
            error_text = ""
        if error_text:
            return {"ok": False, "status": 400, "url": current_url, "data": None, "text": error_text}
        time.sleep(0.5)
    return {"ok": False, "status": 0, "url": last_url, "data": None, "text": "验证码页提交后未跳转"}


def _submit_about_you_via_page(page, log, log_key: Optional[Callable[[str, dict], None]] = None) -> dict:
    from .constants import generate_random_user_info

    user_info = generate_random_user_info()
    name = str(user_info.get("name") or "").strip()
    birthdate = str(user_info.get("birthdate") or "").strip()
    if not name or not birthdate:
        _raise_keyed(RuntimeError, "chatgpt.e269fef6")
        # was: raise RuntimeError("about_you 数据生成失败") — was: raise RuntimeError("about_you data generation failed")
    date_parts = birthdate.split("-")
    if len(date_parts) == 3:
        yyyy, mm, dd = date_parts
        us_birthdate = f"{mm}/{dd}/{yyyy}"
        cn_birthdate = f"{yyyy}/{mm}/{dd}"
    else:
        us_birthdate = birthdate
        cn_birthdate = birthdate.replace("-", "/")
    _emit_log_key(log, log_key, "chatgpt.69ee44f0", name=name, birthdate=birthdate, us_birthdate=us_birthdate, cn_birthdate=cn_birthdate)
    # was: log(f"about_you 表单: name={name}, birthdate={birthdate}, ui_birthdate={us_birthdate}, cn_birthdate={cn_birthdate}") —
    # was: log(f"about_you form: name={name}, birthdate={birthdate}, ui_birthdate={us_birthdate}, cn_birthdate={cn_birthdate}")

    def _fill_locator(locator, value: str) -> bool:
        try:
            target = locator.first
            target.wait_for(state="visible", timeout=1500)
            target.click(timeout=1500)
            _browser_pause(page, headed=False)
            try:
                applied = bool(
                    target.evaluate(
                        """
                        (input, nextValue) => {
                          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                          if (!setter) return false;
                          setter.call(input, nextValue);
                          input.dispatchEvent(new Event('input', { bubbles: true }));
                          input.dispatchEvent(new Event('change', { bubbles: true }));
                          return String(input.value || '') === String(nextValue || '');
                        }
                        """,
                        value,
                    )
                )
            except Exception:
                applied = False
            if not applied:
                target.fill("")
                target.type(value, delay=random.randint(25, 70))
            try:
                target.dispatch_event("blur")
            except Exception:
                pass
            final_val = str(target.input_value() or "").strip()
            return final_val == str(value).strip()
        except Exception:
            return False

    def _locator_from_visible_input_entry(entry: dict):
        try:
            visible_index = int(entry.get("visibleIndex"))
        except Exception:
            return None
        return page.locator("input:visible:not([type='hidden']):not([disabled]):not([readonly])").nth(visible_index)

    def _fill_visible_input_entry(entry: dict | None, value: str) -> bool:
        if not entry:
            return False
        locator = _locator_from_visible_input_entry(entry)
        if locator is None:
            return False
        return _fill_locator(locator, value)

    def _resolve_visible_input_selector(selectors: list[str]) -> str | None:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                locator.wait_for(state="visible", timeout=500)
                return selector
            except Exception:
                continue
        return None

    def _fill_second_visible_input(values: list[str], excluded_visible_indices: set[int] | None = None) -> bool:
        """兜底：about_you 卡片一般是 Full name + Birthday/Age 两个输入框。 — Fallback: the about_you card usually has two inputs, Full name + Birthday/Age."""
        try:
            locator = page.locator(
                "input:visible:not([type='hidden']):not([disabled]):not([readonly])"
            )
            count = locator.count()
            if count < 2:
                return False
            excluded = {int(value) for value in (excluded_visible_indices or set())}
            target_index = None
            for idx in range(count):
                if idx not in excluded:
                    target_index = idx
                    if idx > 0:
                        break
            if target_index is None:
                return False
            target = locator.nth(target_index)
            target.click(timeout=1200)
            _browser_pause(page, headed=False)
            for value in values:
                try:
                    target.fill("")
                except Exception:
                    pass
                try:
                    target.type(str(value), delay=random.randint(18, 45))
                except Exception:
                    continue
                final_val = str(target.input_value() or "").strip()
                if final_val:
                    return True
            return False
        except Exception:
            return False

    def _has_visible(locator) -> bool:
        try:
            locator.first.wait_for(state="visible", timeout=700)
            return True
        except Exception:
            return False

    def _fill_birthday_selects(yyyy: str, mm: str, dd: str) -> bool:
        """处理 Month/Day/Year 下拉样式的生日控件。 — Handle the Month/Day/Year dropdown-style birthday control."""
        try:
            select_locator = page.locator("select:visible")
            count = select_locator.count()
            if count < 2:
                return False

            month_num = int(mm)
            day_num = int(dd)
            year_num = int(yyyy)
            month_short = time.strftime("%b", time.strptime(str(month_num), "%m"))
            month_full = time.strftime("%B", time.strptime(str(month_num), "%m"))

            assigned = {"month": False, "day": False, "year": False}

            for i in range(count):
                sel = select_locator.nth(i)
                try:
                    options = sel.locator("option")
                    option_count = options.count()
                except Exception:
                    option_count = 0
                if option_count <= 0:
                    continue

                texts: list[str] = []
                for idx in range(min(option_count, 80)):
                    try:
                        texts.append(str(options.nth(idx).inner_text(timeout=300) or "").strip())
                    except Exception:
                        continue
                joined = " ".join(texts).lower()

                try:
                    if (not assigned["month"]) and (
                        "january" in joined or "february" in joined or "march" in joined or "april" in joined
                    ):
                        for candidate in (month_full, month_short, str(month_num), f"{month_num:02d}"):
                            try:
                                sel.select_option(label=candidate, timeout=800)
                                assigned["month"] = True
                                break
                            except Exception:
                                try:
                                    sel.select_option(value=candidate, timeout=800)
                                    assigned["month"] = True
                                    break
                                except Exception:
                                    continue
                        continue

                    if (not assigned["year"]) and any(str(y) in joined for y in (year_num, year_num - 1, year_num + 1, 2026, 2025)):
                        for candidate in (str(year_num),):
                            try:
                                sel.select_option(label=candidate, timeout=800)
                                assigned["year"] = True
                                break
                            except Exception:
                                try:
                                    sel.select_option(value=candidate, timeout=800)
                                    assigned["year"] = True
                                    break
                                except Exception:
                                    continue
                        continue

                    if (not assigned["day"]) and any(str(x) in joined for x in (" 1 ", "2", "30", "31")):
                        for candidate in (str(day_num), f"{day_num:02d}"):
                            try:
                                sel.select_option(label=candidate, timeout=800)
                                assigned["day"] = True
                                break
                            except Exception:
                                try:
                                    sel.select_option(value=candidate, timeout=800)
                                    assigned["day"] = True
                                    break
                                except Exception:
                                    continue
                except Exception:
                    continue

            # 下拉顺序兜底：month/day/year — Fallback by dropdown order: month/day/year
            if count >= 3:
                try:
                    if not assigned["month"]:
                        select_locator.nth(0).select_option(label=month_short, timeout=800)
                        assigned["month"] = True
                except Exception:
                    pass
                try:
                    if not assigned["day"]:
                        select_locator.nth(1).select_option(label=str(day_num), timeout=800)
                        assigned["day"] = True
                except Exception:
                    pass
                try:
                    if not assigned["year"]:
                        select_locator.nth(2).select_option(label=str(year_num), timeout=800)
                        assigned["year"] = True
                except Exception:
                    pass

            return assigned["month"] and assigned["day"] and assigned["year"]
        except Exception:
            return False

    visible_inputs = _collect_visible_text_inputs(page)
    if visible_inputs:
        _emit_log_key(log, log_key, "chatgpt.3efc3c40", items=" | ".join(
                f"#{int(item.get('visibleIndex', 0))} {(_about_you_input_hints(item) or '-')[:80]}"
                for item in visible_inputs[:4]
            ))
        # was: log("about_you 可见输入框: " + " | ".join(f"#{int(item.get('visibleIndex', 0))} {(_about_you_input_hints(item) or '-')[:80]}" for item in visible_inputs[:4])) —
        # was: log("about_you visible inputs: " + " | ".join(f"#{int(item.get('visibleIndex', 0))} {(_about_you_input_hints(item) or '-')[:80]}" for item in visible_inputs[:4]))
    ordered_visible_entries = sorted(
        [item for item in visible_inputs if str(item.get("visibleIndex", "")).isdigit()],
        key=lambda item: int(item.get("visibleIndex", 0)),
    )
    name_entry = _pick_best_about_you_input(visible_inputs, "name")
    age_entry = _pick_best_about_you_input(
        visible_inputs,
        "age",
        exclude_visible_indices={int(name_entry.get("visibleIndex"))} if name_entry and str(name_entry.get("visibleIndex", "")).isdigit() else set(),
    )

    name_candidates = [
        page.get_by_label(re.compile(r"full\s*name", re.IGNORECASE)),
        page.get_by_label(re.compile(r"全名|姓名", re.IGNORECASE)),
        page.get_by_role("textbox", name=re.compile(r"full\s*name|name", re.IGNORECASE)),
        page.get_by_role("textbox", name=re.compile(r"全名|姓名", re.IGNORECASE)),
        page.locator("input[autocomplete='name']"),
        page.locator("input[name*='name' i]"),
        page.locator("input[id*='name' i]"),
        page.locator("input[name*='姓名']"),
        page.locator("input[id*='姓名']"),
        page.locator(
            "xpath=//*[contains(translate(normalize-space(string(.)),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'full name')]/following::input[1]"
        ),
        page.locator("xpath=//*[contains(normalize-space(string(.)),'全名') or contains(normalize-space(string(.)),'姓名')]/following::input[1]"),
    ]
    birthday_candidates = [
        page.get_by_label(re.compile(r"birthday|date of birth|birth", re.IGNORECASE)),
        page.get_by_label(re.compile(r"生日|出生", re.IGNORECASE)),
        page.get_by_role("textbox", name=re.compile(r"birthday|date of birth|birth", re.IGNORECASE)),
        page.get_by_role("textbox", name=re.compile(r"生日|出生", re.IGNORECASE)),
        page.get_by_placeholder(re.compile(r"mm.?dd.?yyyy|yyyy.?mm.?dd|birthday|生日", re.IGNORECASE)),
        page.locator("input[name*='birth' i]"),
        page.locator("input[id*='birth' i]"),
        page.locator("input[placeholder*='MM' i]"),
        page.locator("input[placeholder*='DD' i]"),
        page.locator("input[placeholder*='YYYY' i]"),
        page.locator("input[placeholder*='年']"),
        page.locator("input[placeholder*='月']"),
        page.locator("input[placeholder*='日']"),
        page.locator("input[inputmode='numeric']"),
        page.locator(
            "xpath=//*[contains(translate(normalize-space(string(.)),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'birthday')]/following::input[1]"
        ),
        page.locator("xpath=//*[contains(normalize-space(string(.)),'生日') or contains(normalize-space(string(.)),'出生')]/following::input[1]"),
        page.locator("input[type='date']"),
    ]

    age_years = None
    try:
        birth_year = int(str(birthdate).split("-")[0])
        current_year = int(time.strftime("%Y"))
        age_years = max(25, min(40, current_year - birth_year))
    except Exception:
        age_years = random.randint(25, 35)

    age_candidates = [
        page.get_by_label(re.compile(r"age", re.IGNORECASE)),
        page.get_by_label(re.compile(r"年龄", re.IGNORECASE)),
        page.get_by_role("textbox", name=re.compile(r"age", re.IGNORECASE)),
        page.get_by_role("textbox", name=re.compile(r"年龄", re.IGNORECASE)),
        page.locator("input[name*='age' i]"),
        page.locator("input[id*='age' i]"),
        page.locator("input[placeholder*='Age' i]"),
        page.locator("input[placeholder*='年龄']"),
        page.locator(
            "xpath=//*[contains(translate(normalize-space(string(.)),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'age')]/following::input[1]"
        ),
        page.locator("xpath=//*[contains(normalize-space(string(.)),'年龄')]/following::input[1]"),
    ]

    fill_result = {"name": False, "birthdate": False, "age": False, "month": False, "day": False, "year": False}
    if _fill_visible_input_entry(name_entry, name):
        fill_result["name"] = True
    if not fill_result.get("name"):
        for candidate in name_candidates:
            if _fill_locator(candidate, name):
                fill_result["name"] = True
                break
    mode_probe = {}
    try:
        mode_probe = page.evaluate(
            """
            () => {
              const labels = Array.from(document.querySelectorAll('label'))
                .map((n) => String(n.textContent || '').trim().toLowerCase())
                .filter(Boolean);
              const placeholders = Array.from(document.querySelectorAll('input'))
                .map((n) => String(n.placeholder || '').trim().toLowerCase())
                .filter(Boolean);
              const headings = Array.from(document.querySelectorAll('h1,h2,h3'))
                .map((n) => String(n.textContent || '').trim().toLowerCase())
                .filter(Boolean);
              const allText = labels.concat(placeholders).concat(headings);
              const hasAge = allText.some((t) => t === 'age' || t === 'edad' || t === 'âge' || t === 'alter' || t === 'idade' || t.includes('how old') || t.includes('年龄') || t.includes('나이'));
              const hasBirthday = allText.some((t) =>
                t.includes('birthday') || t.includes('date of birth') || t.includes('birth') || t.includes('生日') || t.includes('出生') || t.includes('fecha de nacimiento') || t.includes('nascimento') || t.includes('geburtstag') || t.includes('naissance')
              );
              return { labels, placeholders, headings, hasAge, hasBirthday };
            }
            """
        ) or {}
    except Exception:
        mode_probe = {}

    has_age_label = bool(mode_probe.get("hasAge"))
    has_birthday_label = bool(mode_probe.get("hasBirthday"))
    has_age_field = any(_has_visible(candidate) for candidate in age_candidates[:3])
    has_birthday_field = any(_has_visible(candidate) for candidate in birthday_candidates[:3])
    has_birthday_select = False
    try:
        has_birthday_select = page.locator("select:visible").count() >= 2
    except Exception:
        has_birthday_select = False
    if has_birthday_select:
        about_mode = "birthday_select"
    elif (has_age_label and not has_birthday_label) or (has_age_field and not has_birthday_field):
        about_mode = "age"
    else:
        about_mode = "birthday"
    _emit_log_key(log, log_key, "chatgpt.f2006b5c", about_mode=about_mode, labels=mode_probe.get('labels', [])[:4])
    # was: log(f"about_you 页面模式: {about_mode} labels={mode_probe.get('labels', [])[:4]}") —
    # was: log(f"about_you page mode: {about_mode} labels={mode_probe.get('labels', [])[:4]}")
    direct_name_selector = _resolve_visible_input_selector(
        [
            'input[name="name"]',
            'input[name="full_name"]',
            'input[autocomplete="name"]',
            'input[placeholder*="全名"]',
            'input[placeholder*="name" i]',
            'input[id*="name" i]:not([type="hidden"])',
        ]
    )
    direct_age_selector = _resolve_visible_input_selector(
        [
            'input[name="age"]',
            'input[placeholder="Age"]',
            'input[placeholder="age"]',
            'input[placeholder*="年龄"]',
            'input[id*="age" i]',
        ]
    )
    if about_mode == "age" and len(ordered_visible_entries) >= 2:
        name_entry = ordered_visible_entries[0]
        age_entry = ordered_visible_entries[1]
        _emit_log_key(log, log_key, "chatgpt.5fdfcdf9", name_idx=int(name_entry.get('visibleIndex', 0)), age_idx=int(age_entry.get('visibleIndex', 0)))
        # was: log(f"about_you age 输入框映射: name=#{int(name_entry.get('visibleIndex', 0))}, " f"age=#{int(age_entry.get('visibleIndex', 0))}") —
        # was: log(f"about_you age input mapping: name=#{int(name_entry.get('visibleIndex', 0))}, " f"age=#{int(age_entry.get('visibleIndex', 0))}")
    if about_mode == "age":
        _emit_log_key(log, log_key, "chatgpt.60a70bfd", name=direct_name_selector or '-', age=direct_age_selector or '-')
        # was: log("about_you age 直接定位: " f"name={direct_name_selector or '-'}, age={direct_age_selector or '-'}") —
        # was: log("about_you age direct locate: " f"name={direct_name_selector or '-'}, age={direct_age_selector or '-'}")

    def _fill_segmented_date(mm: str, dd: str, yyyy: str) -> bool:
        """处理 MM / DD / YYYY 分段日期输入框（React DateField 样式）。
        特征：一个 Birthday label 下有多个小 input 或 div[data-type] 段。

        Handle the segmented MM / DD / YYYY date input (React DateField style).
        Characteristic: under a single Birthday label there are multiple small
        input or div[data-type] segments."""
        try:
            # 方式1: div[data-type] 段 (React Aria DateField) — Method 1: div[data-type] segments (React Aria DateField)
            month_seg = page.locator('div[data-type="month"], input[data-type="month"]')
            day_seg = page.locator('div[data-type="day"], input[data-type="day"]')
            year_seg = page.locator('div[data-type="year"], input[data-type="year"]')
            if month_seg.count() > 0 and day_seg.count() > 0 and year_seg.count() > 0:
                month_seg.first.click(force=True)
                page.keyboard.type(mm, delay=50)
                time.sleep(0.3)
                day_seg.first.click(force=True)
                page.keyboard.type(dd, delay=50)
                time.sleep(0.3)
                year_seg.first.click(force=True)
                page.keyboard.type(yyyy, delay=50)
                return True

            # 方式2: 单个 date input 里有 MM/DD/YYYY 占位符 — Method 2: a single date input with an MM/DD/YYYY placeholder
            # 点击输入框，然后按顺序输入 MM DD YYYY（Tab 切换段） —
            # Click the input, then type MM DD YYYY in order (Tab moves to the next segment)
            date_input = page.locator("input[placeholder*='MM'], input[placeholder*='mm'], input[type='date']")
            if date_input.count() > 0:
                date_input.first.click(force=True)
                time.sleep(0.2)
                page.keyboard.type(mm, delay=50)
                page.keyboard.type(dd, delay=50)
                page.keyboard.type(yyyy, delay=50)
                return True

            # 方式3: Birthday label 下的第二个可见 input，直接点击后按数字键输入 —
            # Method 3: the second visible input under the Birthday label; click it and type digits directly
            birthday_input = page.get_by_label(re.compile(r"birthday|birth", re.IGNORECASE))
            if birthday_input.count() > 0:
                birthday_input.first.click(force=True)
                time.sleep(0.2)
                page.keyboard.type(mm, delay=50)
                page.keyboard.type(dd, delay=50)
                page.keyboard.type(yyyy, delay=50)
                return True

            # 方式4: 第二个可见 input（name 是第一个） — Method 4: the second visible input (name is the first)
            inputs = page.locator("input:visible:not([type='hidden']):not([disabled])")
            if inputs.count() >= 2:
                target = inputs.nth(1)
                target.click(force=True)
                time.sleep(0.3)
                # 先清空 — Clear it first
                page.keyboard.press("Control+a")
                page.keyboard.press("Backspace")
                time.sleep(0.1)
                # 输入 MM，Tab 到 DD，Tab 到 YYYY — Type MM, Tab to DD, Tab to YYYY
                page.keyboard.type(mm, delay=80)
                time.sleep(0.3)
                page.keyboard.type(dd, delay=80)
                time.sleep(0.3)
                page.keyboard.type(yyyy, delay=80)
                time.sleep(0.3)
                # 验证是否填入了正确的值 — Verify the correct value was entered
                val = str(target.input_value() or "").strip()
                if val and val != target.get_attribute("placeholder"):
                    return True
                # 如果直接输入不行，试 Tab 切换 — If direct typing does not work, try switching with Tab
                target.click(force=True)
                time.sleep(0.2)
                page.keyboard.press("Control+a")
                page.keyboard.press("Backspace")
                for i, part in enumerate([mm, dd, yyyy]):
                    page.keyboard.type(part, delay=80)
                    if i < 2:
                        page.keyboard.press("Tab")
                        time.sleep(0.2)
                return True
        except Exception:
            pass
        return False

    if about_mode == "birthday_select":
        if len(date_parts) == 3 and _fill_birthday_selects(yyyy, mm, dd):
            fill_result["month"] = True
            fill_result["day"] = True
            fill_result["year"] = True
            fill_result["birthdate"] = True
    elif about_mode == "age":
        if direct_name_selector and _fill_input_like_user(page, direct_name_selector, name):
            fill_result["name"] = True
        elif _fill_visible_input_entry(name_entry, name):
            fill_result["name"] = True
        if age_years is not None:
            if direct_age_selector and _fill_input_like_user(page, direct_age_selector, str(age_years)):
                fill_result["age"] = True
            elif _fill_visible_input_entry(age_entry, str(age_years)):
                fill_result["age"] = True
            if not fill_result.get("age") and len(ordered_visible_entries) < 2:
                for candidate in age_candidates:
                    if _fill_locator(candidate, str(age_years)):
                        fill_result["age"] = True
                        break
        # fallback: 直接找 placeholder="Age" 的输入框 — fallback: find the input with placeholder="Age" directly
        if not fill_result.get("age") and age_years is not None and len(ordered_visible_entries) < 2:
            try:
                age_input = page.locator("input[placeholder='Age'], input[placeholder='age']")
                if age_input.count() > 0:
                    age_input.first.click(force=True)
                    time.sleep(0.2)
                    age_input.first.fill("")
                    age_input.first.type(str(age_years), delay=random.randint(30, 60))
                    fill_result["age"] = True
            except Exception:
                pass
        if not fill_result.get("age") and age_years is not None:
            excluded_indices = set()
            if name_entry and str(name_entry.get("visibleIndex", "")).isdigit():
                excluded_indices.add(int(name_entry.get("visibleIndex")))
            if _fill_second_visible_input([str(age_years)], excluded_visible_indices=excluded_indices):
                fill_result["age"] = True
        if len(date_parts) == 3 and _sync_hidden_birthday_input(page, f"{yyyy}-{mm}-{dd}", log, log_key):
            fill_result["birthdate"] = True
    elif about_mode == "birthday" or about_mode == "birthday_text":
        # 先尝试分段日期输入（MM / DD / YYYY 格式的 DateField） — Try the segmented date input first (MM / DD / YYYY style DateField)
        if len(date_parts) == 3 and _fill_segmented_date(mm, dd, yyyy):
            fill_result["birthdate"] = True
            _emit_log_key(log, log_key, "chatgpt.8a0ccc56")
            # was: log("about_you 使用分段日期输入成功") — was: log("about_you segmented date input succeeded")
        # 再尝试普通文本输入 — Then fall back to a plain text input
        if not fill_result.get("birthdate"):
            for candidate in birthday_candidates:
                if _fill_locator(candidate, cn_birthdate):
                    fill_result["birthdate"] = True
                    break
                if _fill_locator(candidate, us_birthdate):
                    fill_result["birthdate"] = True
                    break
                if _fill_locator(candidate, birthdate):
                    fill_result["birthdate"] = True
                    break
                if _fill_locator(candidate, cn_birthdate.replace("/", "")):
                    fill_result["birthdate"] = True
                    break
                if _fill_locator(candidate, us_birthdate.replace("/", "")):
                    fill_result["birthdate"] = True
                    break
        if not fill_result.get("birthdate"):
            fallback_values = [cn_birthdate, cn_birthdate.replace("/", " / "), cn_birthdate.replace("/", ""), us_birthdate, us_birthdate.replace("/", " / "), us_birthdate.replace("/", ""), birthdate]
            if _fill_second_visible_input(fallback_values):
                fill_result["birthdate"] = True

    _emit_log_key(log, log_key, "chatgpt.5bad6f16", fill_result=fill_result)
    # was: log(f"about_you 填写结果: {fill_result}") — was: log(f"about_you fill result: {fill_result}")
    if not fill_result.get("name"):
        _raise_keyed(RuntimeError, "chatgpt.eec1673e")
        # was: raise RuntimeError("about_you 未成功填写 Full name") —
        # was: raise RuntimeError("about_you failed to fill Full name")
    if not (
        fill_result.get("birthdate")
        or fill_result.get("age")
        or (fill_result.get("month") and fill_result.get("day") and fill_result.get("year"))
    ):
        _raise_keyed(RuntimeError, "chatgpt.4939b14b")
        # was: raise RuntimeError("about_you 未成功填写 Birthday/Age") —
        # was: raise RuntimeError("about_you failed to fill Birthday/Age")
    _browser_pause(page)

    submit_selector = _click_first(
        page,
        [
            'button:has-text("Finish creating account")',
            'button:has-text("finish creating account")',
            'button[type="submit"]',
            'button[data-testid="continue-button"]',
            'button:has-text("Continue")',
            'button:has-text("continue")',
            'button:has-text("Next")',
            'button:has-text("next")',
        ],
        timeout=8,
    )
    if not submit_selector:
        _raise_keyed(RuntimeError, "chatgpt.09eb6ff9")
        # was: raise RuntimeError("about_you 未找到提交按钮") — was: raise RuntimeError("about_you submit button not found")
    _emit_log_key(log, log_key, "chatgpt.156fb08c", submit_selector=submit_selector)
    # was: log(f"about_you 已点击继续按钮: {submit_selector}") —
    # was: log(f"about_you clicked continue button: {submit_selector}")

    deadline = time.time() + 20
    retried_generic_validation = False
    last_url = page.url
    while time.time() < deadline:
        current_url = page.url
        last_url = current_url or last_url
        if "code=" in current_url or "chatgpt.com" in current_url or "sign-in-with-chatgpt" in current_url:
            return {"ok": True, "status": 200, "url": current_url, "data": None, "text": ""}
        if "add-phone" in current_url:
            return {"ok": True, "status": 200, "url": current_url, "data": None, "text": ""}
        try:
            error_text = page.locator("text=Sorry, we cannot create your account").first.text_content(timeout=500)
        except Exception:
            error_text = ""
        if not error_text:
            try:
                error_text = page.locator("text=Enter a valid age to continue").first.text_content(timeout=300)
            except Exception:
                error_text = ""
        if not error_text:
            try:
                error_text = page.locator("text=doesn't look right").first.text_content(timeout=300)
            except Exception:
                error_text = ""
        if not error_text:
            try:
                error_text = page.locator("[role='alert']").first.text_content(timeout=300)
            except Exception:
                error_text = ""
        if not error_text:
            try:
                error_text = page.locator(".error, [class*='error'], [class*='Error']").first.text_content(timeout=300)
            except Exception:
                error_text = ""
        if error_text and "oai_log" not in error_text and "SSR_HTML" not in error_text:
            normalized_error = str(error_text).strip().lower()
            if (
                about_mode == "age"
                and not retried_generic_validation
                and ("doesn't look right" in normalized_error or "try again" in normalized_error)
            ):
                retried_generic_validation = True
                _emit_log_key(log, log_key, "chatgpt.0b25bc0c")
                # was: log("about_you age 模式提交被拒，重新同步 Full name/Age/hidden birthday 后重试一次...") —
                # was: log("about_you age mode submit rejected, resyncing Full name/Age/hidden birthday then retrying once...")
                if direct_name_selector and _fill_input_like_user(page, direct_name_selector, name):
                    fill_result["name"] = True
                elif _fill_visible_input_entry(name_entry, name):
                    fill_result["name"] = True
                elif len(ordered_visible_entries) < 2:
                    for candidate in name_candidates:
                        if _fill_locator(candidate, name):
                            fill_result["name"] = True
                            break
                if age_years is not None:
                    if direct_age_selector and _fill_input_like_user(page, direct_age_selector, str(age_years)):
                        fill_result["age"] = True
                    elif _fill_visible_input_entry(age_entry, str(age_years)):
                        fill_result["age"] = True
                    elif len(ordered_visible_entries) < 2:
                        for candidate in age_candidates:
                            if _fill_locator(candidate, str(age_years)):
                                fill_result["age"] = True
                                break
                if len(date_parts) == 3 and _sync_hidden_birthday_input(page, f"{yyyy}-{mm}-{dd}", log, log_key):
                    fill_result["birthdate"] = True
                _browser_pause(page)
                retry_submit_selector = _click_first(
                    page,
                    [
                        'button:has-text("Finish creating account")',
                        'button:has-text("finish creating account")',
                        'button[type="submit"]',
                        'button[data-testid="continue-button"]',
                        'button:has-text("Continue")',
                        'button:has-text("continue")',
                        'button:has-text("Next")',
                        'button:has-text("next")',
                    ],
                    timeout=5,
                )
                if retry_submit_selector:
                    _emit_log_key(log, log_key, "chatgpt.f7a9b1fe", retry_submit_selector=retry_submit_selector)
                    # was: log(f"about_you 重试提交按钮: {retry_submit_selector}") —
                    # was: log(f"about_you retry submit button: {retry_submit_selector}")
                    time.sleep(0.5)
                    continue
            return {"ok": False, "status": 400, "url": current_url, "data": None, "text": error_text}
        time.sleep(0.5)
    _dump_debug(page, "chatgpt_about_you_fail")
    return {"ok": False, "status": 0, "url": last_url, "data": None, "text": "about_you 提交后未跳转"}


def _browser_registration_flow(page, email: str, password: str, otp_callback, phone_callback, log, log_key: Optional[Callable[[str, dict], None]] = None) -> dict:
    device_id = str(uuid.uuid4())
    try:
        user_agent = str(page.evaluate("() => navigator.userAgent") or "").strip() or _random_chrome_ua()
    except Exception:
        user_agent = _random_chrome_ua()

    _seed_browser_device_id(page, device_id)
    try:
        state = _start_browser_signup_via_page(page, email, log, log_key)
    except Exception as exc:
        _emit_log_key(log, log_key, "chatgpt.92d09e9b", exc=exc)
        # was: log(f"页面驱动注册入口失败，回退 ChatGPT authorize 入口: {exc}") —
        # was: log(f"page-driven signup entry failed, falling back to ChatGPT authorize entry: {exc}")
        state = _start_browser_signup_via_authorize(page, email, device_id, log, log_key)
    auth_cookies = _get_cookies(page)
    _emit_log_key(log, log_key, "chatgpt.1ad05205", login_session='yes' if auth_cookies.get('login_session') else 'no', oai_did='yes' if auth_cookies.get('oai-did') else 'no')
    # was: log("授权态 cookies: " f"login_session={'yes' if auth_cookies.get('login_session') else 'no'}, " f"oai-did={'yes' if auth_cookies.get('oai-did') else 'no'}") —
    # was: log("auth-state cookies: " f"login_session={'yes' if auth_cookies.get('login_session') else 'no'}, " f"oai-did={'yes' if auth_cookies.get('oai-did') else 'no'}")
    _emit_log_key(log, log_key, "chatgpt.c2f61b93", page=state.get('page_type') or '-', url=(state.get('current_url') or '')[:100])
    # was: log(f"注册状态起点: page={state.get('page_type') or '-'} url={(state.get('current_url') or '')[:100]}") —
    # was: log(f"registration state start: page={state.get('page_type') or '-'} url={(state.get('current_url') or '')[:100]}")
    register_submitted = False
    seen_states: dict[str, int] = {}

    for step in range(12):
        signature = "|".join(
            [
                str(state.get("page_type") or ""),
                str(state.get("method") or ""),
                str(state.get("continue_url") or ""),
                str(state.get("current_url") or ""),
            ]
        )
        seen_states[signature] = seen_states.get(signature, 0) + 1
        _emit_log_key(log, log_key, "chatgpt.7c9f06dc", step=step+1, page=state.get('page_type') or '-', next_url=str(state.get('continue_url') or '')[:60], seen=seen_states[signature])
        # was: log(f"注册状态推进: step={step+1} page={state.get('page_type') or '-'} " f"next={str(state.get('continue_url') or '')[:60]} seen={seen_states[signature]}") —
        # was: log(f"registration state advance: step={step+1} page={state.get('page_type') or '-'} " f"next={str(state.get('continue_url') or '')[:60]} seen={seen_states[signature]}")
        if seen_states[signature] > 2:
            _raise_keyed(RuntimeError, "chatgpt.407c1444", page=state.get('page_type') or '-')
            # was: raise RuntimeError(f"注册状态卡住: page={state.get('page_type') or '-'}") —
            # was: raise RuntimeError(f"registration state stuck: page={state.get('page_type') or '-'}")

        if _is_registration_complete(state):
            _handle_post_signup_onboarding(page, log, log_key)
            return _extract_flow_state(None, page.url)

        if _is_password_registration(state):
            if register_submitted:
                _raise_keyed(RuntimeError, "chatgpt.583d3109")
                # was: raise RuntimeError("重复进入密码注册阶段") —
                # was: raise RuntimeError("re-entered password registration stage")
            _emit_log_key(log, log_key, "chatgpt.cba3a93f")
            # was: log("提交注册密码...") — was: log("submitting registration password...")
            pre_cookies = _get_cookies(page)
            _emit_log_key(log, log_key, "chatgpt.eafa0a69", login_session='yes' if pre_cookies.get('login_session') else 'no', oai_client_auth_session='yes' if pre_cookies.get('oai-client-auth-session') else 'no')
            # was: log("密码阶段 cookies: " f"login_session={'yes' if pre_cookies.get('login_session') else 'no'}, " f"oai-client-auth-session={'yes' if pre_cookies.get('oai-client-auth-session') else 'no'}") —
            # was: log("password-stage cookies: " f"login_session={'yes' if pre_cookies.get('login_session') else 'no'}, " f"oai-client-auth-session={'yes' if pre_cookies.get('oai-client-auth-session') else 'no'}")
            reg_resp = _submit_password_via_page(page, password, log, log_key)
            _emit_log_key(log, log_key, "chatgpt.c7315fc5", val=reg_resp.get('status', 0))
            # was: log(f"密码页提交状态: {reg_resp.get('status', 0)}") —
            # was: log(f"password page submit status: {reg_resp.get('status', 0)}")
            if not reg_resp.get("ok"):
                _raise_keyed(RuntimeError, "chatgpt.8ea76eac", text=(reg_resp.get('text') or '')[:300])
                # was: raise RuntimeError(f"密码页提交失败: {(reg_resp.get('text') or '')[:300]}") —
                # was: raise RuntimeError(f"password page submit failed: {(reg_resp.get('text') or '')[:300]}")
            register_submitted = True
            state = _extract_flow_state(reg_resp.get("data"), reg_resp.get("url", page.url))
            if not state.get("page_type") or _is_password_registration(state):
                state = _derive_registration_state_from_page(page)
            continue

        if str(state.get("page_type") or "") == "login_password":
            if _recover_signup_password_page(page, log, log_key):
                state = _derive_registration_state_from_page(page)
                continue
            _emit_log_key(log, log_key, "chatgpt.aec7b097")
            # was: log("注册流程落到已有账号登录密码页，按登录流程继续认证...") —
            # was: log("registration flow landed on an existing-account login password page, continuing via login flow...")
            login_resp = _submit_oauth_password_direct(page, password, log, log_key)
            _emit_log_key(log, log_key, "chatgpt.04c047a0", val=login_resp.get('status', 0))
            # was: log(f"登录密码页提交状态: {login_resp.get('status', 0)}") —
            # was: log(f"login password page submit status: {login_resp.get('status', 0)}")
            if not login_resp.get("ok"):
                _raise_keyed(RuntimeError, "chatgpt.83cdc327", text=(login_resp.get('text') or '')[:300])
                # was: raise RuntimeError(f"登录密码页提交失败: {(login_resp.get('text') or '')[:300]}") —
                # was: raise RuntimeError(f"login password page submit failed: {(login_resp.get('text') or '')[:300]}")
            state = _extract_flow_state(login_resp.get("data"), login_resp.get("url", page.url))
            if not state.get("page_type"):
                state = _derive_registration_state_from_page(page)
            continue

        if _is_email_otp(state):
            if not otp_callback:
                _raise_keyed(RuntimeError, "chatgpt.af30d923")
                # was: raise RuntimeError("ChatGPT 注册需要邮箱验证码但未提供 otp_callback") —
                # was: raise RuntimeError("ChatGPT registration needs an email OTP but no otp_callback was provided")
            _emit_log_key(log, log_key, "chatgpt.abe606fe")
            # was: log("等待 ChatGPT 验证码") — was: log("waiting for ChatGPT verification code")
            code = otp_callback()
            if not code:
                _raise_keyed(RuntimeError, "chatgpt.13939cce")
                # was: raise RuntimeError("未获取到验证码") — was: raise RuntimeError("failed to obtain verification code")
            otp_resp = _submit_otp_via_page(page, code, log, log_key)
            _emit_log_key(log, log_key, "chatgpt.6c016e07", val=otp_resp.get('status', 0))
            # was: log(f"验证码页提交状态: {otp_resp.get('status', 0)}") —
            # was: log(f"verification code page submit status: {otp_resp.get('status', 0)}")
            if not otp_resp.get("ok"):
                _raise_keyed(RuntimeError, "chatgpt.133769b7", text=(otp_resp.get('text') or '')[:300])
                # was: raise RuntimeError(f"验证码校验失败: {(otp_resp.get('text') or '')[:300]}") —
                # was: raise RuntimeError(f"verification code check failed: {(otp_resp.get('text') or '')[:300]}")
            state = _extract_flow_state(otp_resp.get("data"), otp_resp.get("url", page.url))
            if not state.get("page_type"):
                state = _derive_registration_state_from_page(page)
            continue

        if _is_about_you(state):
            _emit_log_key(log, log_key, "chatgpt.18cf15f8")
            # was: log("提交 about_you 信息...") — was: log("submitting about_you info...")
            target_url = _normalize_url(
                str(state.get("current_url") or state.get("continue_url") or f"{OPENAI_AUTH}/about-you"),
                OPENAI_AUTH,
            )
            if "about-you" not in str(page.url):
                _emit_log_key(log, log_key, "chatgpt.843208b3", url=target_url[:120])
                # was: log(f"跳转到 about_you 页面: {target_url[:120]}") —
                # was: log(f"navigating to about_you page: {target_url[:120]}")
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            about_resp = _submit_about_you_via_page(page, log, log_key)
            _emit_log_key(log, log_key, "chatgpt.6f11c10d", status=about_resp.get('status', 0))
            # was: log(f"about_you 提交状态: {about_resp.get('status', 0)}") —
            # was: log(f"about_you submit status: {about_resp.get('status', 0)}")
            if not about_resp.get("ok"):
                _raise_keyed(RuntimeError, "chatgpt.b23dc737", text=(about_resp.get('text') or '')[:300])
                # was: raise RuntimeError(f"about_you 提交失败: {(about_resp.get('text') or '')[:300]}") —
                # was: raise RuntimeError(f"about_you submit failed: {(about_resp.get('text') or '')[:300]}")
            state = _extract_flow_state(about_resp.get("data"), about_resp.get("url", page.url))
            if not state.get("page_type"):
                state = _derive_registration_state_from_page(page)
            if _is_add_phone(state):
                if not phone_callback:
                    return state
                _emit_log_key(log, log_key, "chatgpt.09a608d9")
                # was: log("about_you 后进入 add_phone，尝试短信验证...") —
                # was: log("after about_you, entered add_phone, trying SMS verification...")
                state = _handle_add_phone_challenge(
                    page,
                    phone_callback,
                    device_id=device_id,
                    user_agent=user_agent,
                    log=log,
                    log_key=log_key,
                    resume_url=f"{CHATGPT_APP}/",
                )
            continue

        if _is_add_phone(state):
            if not phone_callback:
                return state
            _emit_log_key(log, log_key, "chatgpt.5149264c")
            # was: log("注册流程进入 add_phone，尝试短信验证...") —
            # was: log("registration flow entered add_phone, trying SMS verification...")
            state = _handle_add_phone_challenge(
                page,
                phone_callback,
                device_id=device_id,
                user_agent=user_agent,
                log=log,
                log_key=log_key,
                resume_url=f"{CHATGPT_APP}/",
            )
            continue

        if _requires_registration_navigation(state):
            target_url = _normalize_url(str(state.get("continue_url") or state.get("current_url") or ""), OPENAI_AUTH)
            if not target_url:
                _raise_keyed(RuntimeError, "chatgpt.2fb11597")
                # was: raise RuntimeError("缺少可跟随的 continue_url") —
                # was: raise RuntimeError("missing a continue_url to follow")
            page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            state = _extract_flow_state(None, page.url)
            continue

        _raise_keyed(RuntimeError, "chatgpt.456d8144", page=state.get('page_type') or '-')
        # was: raise RuntimeError(f"未支持的注册状态: page={state.get('page_type') or '-'}") —
        # was: raise RuntimeError(f"unsupported registration state: page={state.get('page_type') or '-'}")

    _raise_keyed(RuntimeError, "chatgpt.73ff27e1")
    # was: raise RuntimeError("注册状态机超出最大步数") — was: raise RuntimeError("registration state machine exceeded max steps")


class ChatGPTBrowserRegister:
    def __init__(
        self,
        *,
        headless: bool,
        proxy: Optional[str] = None,
        otp_callback: Optional[Callable[[], str]] = None,
        phone_callback: Optional[Callable[[], str]] = None,
        log_fn: Callable[[str], None] = print,
        log_key_fn: Optional[Callable[[str, dict], None]] = None,
    ):
        self.headless = headless
        self.proxy = proxy
        self.otp_callback = otp_callback
        self.phone_callback = phone_callback
        self.log = log_fn
        self._log_key_fn = log_key_fn

    def log_key(self, key: str, **params) -> None:
        if self._log_key_fn is not None:
            self._log_key_fn(key, params)  # positional (key, dict) -- not **params
        else:
            self.log(t(key, "zh", **params))

    def run(self, email: str, password: str) -> dict:
        proxy = _build_proxy_config(self.proxy)
        launch_opts = {"headless": self.headless}
        if proxy:
            launch_opts["proxy"] = proxy
            launch_opts["geoip"] = True

        with Camoufox(**launch_opts) as browser:
            page = browser.new_page()
            self.log_key("chatgpt.1d89a161")
            # was: self.log("启动浏览器上下文注册状态机") — was: self.log("starting browser-context registration state machine")
            final_state = _browser_registration_flow(
                page,
                email,
                password,
                self.otp_callback,
                self.phone_callback,
                self.log,
                self.log_key,
            )
            self.log_key("chatgpt.3052c843", page=final_state.get('page_type') or '-')
            # was: self.log(f"注册流程完成: page={final_state.get('page_type') or '-'}") —
            # was: self.log(f"registration flow complete: page={final_state.get('page_type') or '-'}")

            # 获取 session token 和 cookies — Get the session token and cookies
            cookies_dict = _get_cookies(page)

            # ═══ 通过 Codex CLI OAuth 获取正确的 token ═══
            # 注册完成后的浏览器上下文 session 状态不稳定（NS_BINDING_ABORTED），
            # 直接用全新浏览器做 OAuth 更可靠
            # === Get the correct token via Codex CLI OAuth ===
            # After registration, the browser-context session state is unstable (NS_BINDING_ABORTED),
            # so doing OAuth in a brand-new browser is more reliable.
            self.log_key("chatgpt.263d7f6a")
            # was: self.log("执行 Codex CLI OAuth 流程获取 token...") —
            # was: self.log("running Codex CLI OAuth flow to get token...")

        # 直接用全新浏览器做 OAuth（注册后的浏览器上下文不可靠） —
        # Do OAuth in a brand-new browser directly (the post-registration browser context is unreliable)
        codex_result = self._retry_oauth_fresh_browser(email, password)
        if codex_result:
            self.log_key("chatgpt.4b768d99", account_id=codex_result.get('account_id',''))
            # was: self.log(f"全新浏览器 OAuth 成功: account_id={codex_result.get('account_id','')}") —
            # was: self.log(f"fresh-browser OAuth succeeded: account_id={codex_result.get('account_id','')}")
            return {
                "email": email, "password": password,
                "account_id": codex_result.get("account_id", ""),
                "access_token": codex_result.get("access_token", ""),
                "refresh_token": codex_result.get("refresh_token", ""),
                "id_token": codex_result.get("id_token", ""),
                "session_token": "", "workspace_id": "",
                "cookies": "", "profile": {},
            }

        _raise_keyed(RuntimeError, "chatgpt.c05cf589")
        # was: raise RuntimeError("ChatGPT 注册未完成完整 OAuth callback，已拒绝回退到 session/access_token 半成品结果") —
        # was: raise RuntimeError("ChatGPT registration did not complete a full OAuth callback; refusing to fall back to a partial session/access_token result")

    def _retry_oauth_fresh_browser(self, email, password):
        """在全新浏览器 context 里做 Codex OAuth（绕过 add_phone session）。 — Perform Codex OAuth in a fresh browser context (bypassing the add_phone session)."""
        proxy = _build_proxy_config(self.proxy)
        launch_opts = {"headless": self.headless}
        if proxy:
            launch_opts["proxy"] = proxy
        try:
            with Camoufox(**launch_opts) as browser:
                page = browser.new_page()
                self.log_key("chatgpt.14955e08")
                # was: self.log("  全新浏览器 OAuth 开始...") — was: self.log("  fresh-browser OAuth starting...")
                result = _do_codex_oauth(
                    page, {}, email, password,
                    self.otp_callback, self.phone_callback, self.proxy, self.log,
                    self.log_key,
                )
                return result
        except Exception as e:
            self.log_key("chatgpt.3f70c63e", e=e)
            # was: self.log(f"  全新浏览器 OAuth 异常: {e}") — was: self.log(f"  fresh-browser OAuth exception: {e}")
            return None
