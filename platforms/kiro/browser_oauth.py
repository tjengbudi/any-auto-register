"""Kiro OAuth 浏览器流程。 — Kiro OAuth browser flow."""
from urllib.parse import parse_qs, urlparse

import cbor2

from core.oauth_browser import (
    OAuthBrowser,
    browser_login_method_text,
    finalize_oauth_email,
    oauth_provider_label,
)
from platforms.kiro._i18n_helpers import _raise_keyed
from platforms.kiro.core import KIRO, KiroRegister, UA, _uuid


def _exchange_callback_tokens(reg: KiroRegister, callback_url: str):
    parsed = urlparse(callback_url)
    query = parse_qs(parsed.query)
    auth_code = (query.get("code") or [""])[0]
    redirect_state = (query.get("state") or [""])[0]
    if not auth_code:
        _raise_keyed(RuntimeError, "kiro.6f57fe44")
        # was: raise RuntimeError("Kiro OAuth 回调里缺少 code") — was: raise RuntimeError("Kiro OAuth callback is missing code")
    if redirect_state and redirect_state != reg.state:
        _raise_keyed(RuntimeError, "kiro.63fd1109")
        # was: raise RuntimeError("Kiro OAuth state 不匹配") — was: raise RuntimeError("Kiro OAuth state mismatch")

    exchange_body = cbor2.dumps({
        "code": auth_code,
        "codeVerifier": reg.cv,
        "idp": "BuilderId",
        "redirectUri": f"{KIRO}/signin/oauth",
        "state": redirect_state or reg.state,
    })
    exchange_headers = {
        **UA,
        "accept": "application/cbor",
        "content-type": "application/cbor",
        "smithy-protocol": "rpc-v2-cbor",
        "origin": KIRO,
        "referer": f"{KIRO}/signin",
        "x-kiro-visitorid": reg.vid,
        "amz-sdk-invocation-id": _uuid(),
        "amz-sdk-request": "attempt=1; max=1",
        "x-amz-user-agent": "aws-sdk-js/1.0.0 ua/2.1 os/macOS lang/js md/browser#Chromium_131 m/N,M,E",
    }
    response = reg.s.post(
        f"{KIRO}/service/KiroWebPortalService/operation/ExchangeToken",
        headers=exchange_headers,
        data=exchange_body,
        cookies={"kiro-visitor-id": reg.vid},
    )
    if response.status_code != 200:
        _raise_keyed(RuntimeError, "kiro.77e70637", status_code=response.status_code)
        # was: raise RuntimeError(f"Kiro ExchangeToken 失败: HTTP {response.status_code}") —
        # was: raise RuntimeError(f"Kiro ExchangeToken failed: HTTP {response.status_code}")
    data = cbor2.loads(response.content)
    access_token = data.get("accessToken", "")
    if not access_token:
        _raise_keyed(RuntimeError, "kiro.f8e6f158")
        # was: raise RuntimeError("Kiro ExchangeToken 响应里缺少 accessToken") —
        # was: raise RuntimeError("Kiro ExchangeToken response is missing accessToken")
    return {
        "accessToken": access_token,
        "csrfToken": data.get("csrfToken", ""),
        "expiresIn": data.get("expiresIn", 0),
    }


def register_with_browser_oauth(
    *,
    proxy: str | None = None,
    oauth_provider: str = "",
    email_hint: str = "",
    timeout: int = 300,
    log_fn=print,
    log_key_fn=None,
    headless: bool = False,
    chrome_user_data_dir: str = "",
    chrome_cdp_url: str = "",
) -> dict:
    method_text = browser_login_method_text(oauth_provider)
    reg = KiroRegister(proxy=proxy, tag="KIRO-OAUTH")
    reg.log = log_fn
    reg._log_key_fn = log_key_fn
    redirect_url = reg.step1_kiro_init()
    if not redirect_url:
        _raise_keyed(RuntimeError, "kiro.276321ca")
        # was: raise RuntimeError("Kiro InitiateLogin 失败") — was: raise RuntimeError("Kiro InitiateLogin failed")

    with OAuthBrowser(
        proxy=proxy,
        headless=headless,
        chrome_user_data_dir=chrome_user_data_dir,
        chrome_cdp_url=chrome_cdp_url,
        log_fn=log_fn,
    ) as browser:
        browser.goto(redirect_url)
        if oauth_provider:
            browser.try_click_provider(oauth_provider)

        if chrome_user_data_dir or chrome_cdp_url:
            browser.auto_select_google_account()
        else:
            log_fn(f"请在浏览器中完成登录，可使用 {method_text}，最长等待 {timeout} 秒")
            if email_hint:
                log_fn(f"请确认最终登录账号邮箱为: {email_hint}")

        callback_url = browser.wait_for_url(
            lambda url: url.startswith(f"{KIRO}/signin/oauth") and "code=" in url,
            timeout=timeout,
        )
        if not callback_url:
            _raise_keyed(RuntimeError, "kiro.2da6b380", timeout=timeout)
            # was: raise RuntimeError(f"Kiro 浏览器登录未在 {timeout} 秒内完成") —
            # was: raise RuntimeError(f"Kiro browser login did not finish within {timeout} seconds")

        token_info = _exchange_callback_tokens(reg, callback_url)
        resolved_email = finalize_oauth_email("", email_hint, "Kiro")
        return {
            "email": resolved_email,
            "accessToken": token_info.get("accessToken", ""),
            "sessionToken": browser.cookie_value("__Secure-authjs.session-token", domain_substrings=("kiro.dev",)),
            "csrfToken": token_info.get("csrfToken", ""),
            "expiresIn": token_info.get("expiresIn", 0),
        }


# Backward-compat alias
register_with_manual_oauth = register_with_browser_oauth
