from __future__ import annotations


class RegistrationError(RuntimeError):
    """注册流程基础异常。
    Base exception for the registration flow."""


class IdentityResolutionError(RegistrationError):
    """身份解析失败。 — Identity resolution failed."""


class CaptchaConfigurationError(RegistrationError):
    """验证码配置不可用。
    Captcha configuration is unavailable."""


class OtpTimeoutError(RegistrationError):
    """验证码等待超时。
    Timed out waiting for the verification code."""


class BrowserReuseRequiredError(RegistrationError):
    """无头 OAuth 缺少可复用浏览器会话。
    Headless OAuth is missing a reusable browser session."""


class RegistrationUnsupportedError(RegistrationError):
    """当前平台或执行器不支持该注册路径。
    The current platform or executor doesn't support this registration path."""

