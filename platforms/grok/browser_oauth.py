"""Grok OAuth 浏览器流程。"""
import time
from typing import Callable, Optional

from core.oauth_browser import (
    OAuthBrowser,
    browser_login_method_text,
    finalize_oauth_email,
    oauth_provider_label,
)
from platforms.grok._i18n_helpers import _emit_log_key, _raise_keyed


def register_with_browser_oauth(
    *,
    proxy: str | None = None,
    oauth_provider: str = "",
    email_hint: str = "",
    timeout: int = 300,
    log_fn=print,
    log_key: Optional[Callable[[str, dict], None]] = None,
    headless: bool = False,
    chrome_user_data_dir: str = "",
    chrome_cdp_url: str = "",
) -> dict:
    method_text = browser_login_method_text(oauth_provider)

    with OAuthBrowser(
        proxy=proxy,
        headless=headless,
        chrome_user_data_dir=chrome_user_data_dir,
        chrome_cdp_url=chrome_cdp_url,
        log_fn=log_fn,
        log_key_fn=log_key,
    ) as browser:
        browser.goto("https://accounts.x.ai/sign-up")
        time.sleep(2)
        if oauth_provider and not browser.try_click_provider(oauth_provider):
            browser.goto("https://accounts.x.ai/sign-in")
            time.sleep(2)
            browser.try_click_provider(oauth_provider)

        if chrome_user_data_dir or chrome_cdp_url:
            browser.auto_select_google_account()
        else:
            _emit_log_key(log_fn, log_key, "grok.a45d8569", method_text=method_text, timeout=timeout)
            # was: log_fn(f"请在浏览器中完成登录，可使用 {method_text}，最长等待 {timeout} 秒")
            # was: log_fn(f"Please complete login in the browser using {method_text}; waiting up to {timeout} seconds")
            if email_hint:
                _emit_log_key(log_fn, log_key, "grok.18555deb", email_hint=email_hint)
                # was: log_fn(f"请确认最终登录账号邮箱为: {email_hint}")
                # was: log_fn(f"Please confirm the final login account email is: {email_hint}")

        sso = browser.wait_for_cookie_value(
            ["sso"],
            timeout=timeout,
            domain_substrings=("x.ai",),
        )
        if not sso:
            _raise_keyed(RuntimeError, "grok.64764871", timeout=timeout)
            # was: raise RuntimeError(f"Grok 浏览器登录未在 {timeout} 秒内拿到 SSO Cookie")
            # was: raise RuntimeError(f"Grok browser login did not obtain the SSO cookie within {timeout} seconds")

        resolved_email = finalize_oauth_email("", email_hint, "Grok")
        return {
            "email": resolved_email,
            "sso": sso,
            "sso_rw": browser.cookie_value("sso-rw", domain_substrings=("x.ai",)),
        }


# Backward-compat alias
register_with_manual_oauth = register_with_browser_oauth
