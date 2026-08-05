"""Tavily OAuth 浏览器流程。"""
from __future__ import annotations

import time
from typing import Callable, Optional

from core.oauth_browser import OAUTH_PROVIDER_LABELS, OAuthBrowser, finalize_oauth_email
from platforms.tavily._i18n_helpers import _emit_log_key, _raise_keyed
from platforms.tavily.browser_register import (
    click_oauth_provider,
    close_marketing_dialog,
    extract_signup_url,
    verify_api_key,
    wait_for_api_key,
    wait_for_manual_oauth_completion,
)


def _finalize_api_key(page, *, timeout: int) -> str:
    close_marketing_dialog(page)
    api_key = wait_for_api_key(page, timeout=timeout)
    if not api_key:
        try:
            page.goto("https://app.tavily.com", wait_until="networkidle", timeout=30000)
            time.sleep(3)
        except Exception:
            pass
        api_key = wait_for_api_key(page, timeout=timeout)
    if not api_key:
        _raise_keyed(RuntimeError, "tavily.465ac145")
        # was: raise RuntimeError("未找到 Tavily API Key") — was: raise RuntimeError("Tavily API Key not found")
    if not verify_api_key(api_key):
        _raise_keyed(RuntimeError, "tavily.005c0ad6")
        # was: raise RuntimeError("Tavily API Key 校验失败") — was: raise RuntimeError("Tavily API Key verification failed")
    return api_key


def register_with_browser_oauth(
    *,
    proxy: str | None = None,
    oauth_provider: str = "",
    email_hint: str = "",
    timeout: int = 300,
    log_fn=print,
    log_key: Optional[Callable[[str, dict], None]] = None,
    chrome_user_data_dir: str = "",
    chrome_cdp_url: str = "",
) -> dict:
    provider = (oauth_provider or "").strip().lower()
    if not chrome_user_data_dir and not chrome_cdp_url:
        _raise_keyed(RuntimeError, "tavily.a33b2ec1")
        # was: raise RuntimeError("Tavily OAuth 需要复用本机浏览器会话，请配置 chrome_user_data_dir 或 chrome_cdp_url")
        # was: raise RuntimeError("Tavily OAuth requires reusing the local browser session; configure chrome_user_data_dir or chrome_cdp_url")

    with OAuthBrowser(
        proxy=proxy,
        headless=False,
        chrome_user_data_dir=chrome_user_data_dir,
        chrome_cdp_url=chrome_cdp_url,
        log_fn=log_fn,
        log_key_fn=log_key,
    ) as browser:
        browser.goto("https://app.tavily.com/sign-in", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        page = browser.active_page()
        signup_url = extract_signup_url(page.content())
        if not signup_url:
            _raise_keyed(RuntimeError, "tavily.7d00428e")
            # was: raise RuntimeError("未找到 Tavily 注册入口") — was: raise RuntimeError("Tavily registration entry not found")
        _emit_log_key(log_fn, log_key, "tavily.9bb51ac8")
        # was: log_fn("进入 Tavily 注册页") — was: log_fn("Entering the Tavily registration page")
        browser.goto(signup_url, wait_until="networkidle", timeout=30000)
        time.sleep(2)
        page = browser.active_page()

        provider_label = OAUTH_PROVIDER_LABELS.get(provider, provider.title()) if provider else ""
        if provider:
            _emit_log_key(log_fn, log_key, "tavily.1bc7b623", provider_label=provider_label)
            # was: log_fn(f"切换到 {provider_label} 登录入口") — was: log_fn(f"Switching to the {provider_label} login entry")
            if not click_oauth_provider(page, provider):
                page.goto("https://app.tavily.com/sign-in", wait_until="networkidle", timeout=30000)
                time.sleep(2)
                if not click_oauth_provider(page, provider):
                    _raise_keyed(RuntimeError, "tavily.2aaefef0", provider_label=provider_label)
                    # was: raise RuntimeError(f"未找到 {provider_label} 登录入口") — was: raise RuntimeError(f"{provider_label} login entry not found")

        if provider_label:
            _emit_log_key(log_fn, log_key, "tavily.2f5ee887", method_text=provider_label, timeout=timeout)
            # was: log_fn(f"请在浏览器中完成登录/授权，可使用 {method_text}，最长等待 {timeout} 秒")
            # was: log_fn(f"Please complete login/authorization in the browser using {method_text}; waiting up to {timeout} seconds")
        else:
            _emit_log_key(log_fn, log_key, "tavily.c9721284", timeout=timeout)
            # was: log_fn(f"请在浏览器中完成登录/授权，可使用 邮箱、Google、GitHub、LinkedIn、Microsoft 等任一可用方式，最长等待 {timeout} 秒")
            # was: log_fn(f"Please complete login/authorization in the browser using email, Google, GitHub, LinkedIn, Microsoft, or any other available method; waiting up to {timeout} seconds")
        if email_hint:
            _emit_log_key(log_fn, log_key, "tavily.18555deb", email_hint=email_hint)
            # was: log_fn(f"请确认最终登录账号邮箱为: {email_hint}")
            # was: log_fn(f"Please confirm the final login account email is: {email_hint}")
        if not wait_for_manual_oauth_completion(page, timeout=timeout):
            _raise_keyed(RuntimeError, "tavily.7a0b6a9f", timeout=timeout)
            # was: raise RuntimeError(f"Tavily 浏览器登录未在 {timeout} 秒内完成")
            # was: raise RuntimeError(f"Tavily browser login did not complete within {timeout} seconds")

        time.sleep(3)
        api_key = _finalize_api_key(page, timeout=20)
        return {
            "email": finalize_oauth_email(email_hint, email_hint, "Tavily"),
            "password": "",
            "api_key": api_key,
        }


register_with_manual_oauth = register_with_browser_oauth
