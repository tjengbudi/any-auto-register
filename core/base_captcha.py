"""验证码解决器基类 — 具体实现已迁移到 providers/captcha/
Captcha solver base class; concrete implementations have moved to providers/captcha/"""
from abc import ABC, abstractmethod

from i18n import t


def _raise_keyed(exc_cls, key: str, **params):
    # AD-17: 异常携带 i18n_key/i18n_params，供 application/tasks.py 的 _exc_key 转发 —
    # AD-17: carries i18n_key/i18n_params for application/tasks.py's _exc_key.
    exc = exc_cls(t(key, "zh", **params))
    exc.i18n_key = key
    exc.i18n_params = params
    raise exc


class BaseCaptcha(ABC):
    @abstractmethod
    def solve_turnstile(self, page_url: str, site_key: str) -> str:
        """返回 Turnstile token — return the Turnstile token"""
        ...

    @abstractmethod
    def solve_image(self, image_b64: str) -> str:
        """返回图片验证码文字 — return the image captcha text"""
        ...


# ---------------------------------------------------------------------------
# Lazy re-exports for backward compatibility
# (concrete classes now live under providers/captcha/)
# ---------------------------------------------------------------------------
_LAZY_IMPORTS = {
    "YesCaptcha": "providers.captcha.yescaptcha",
    "TwoCaptcha": "providers.captcha.twocaptcha",
    "ManualCaptcha": "providers.captcha.manual",
    "LocalSolverCaptcha": "providers.captcha.local_solver",
}


def __getattr__(name: str):
    module_path = _LAZY_IMPORTS.get(name)
    if module_path is not None:
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _definition_auth_fields(definition) -> list[str]:
    if not definition:
        return []
    return [
        str(field.get("key") or "")
        for field in definition.get_fields()
        if str(field.get("category") or "") == "auth" and str(field.get("key") or "")
    ]


def has_captcha_configured(provider_key: str, extra: dict | None = None) -> bool:
    from infrastructure.provider_definitions_repository import ProviderDefinitionsRepository
    from infrastructure.provider_settings_repository import ProviderSettingsRepository

    key = str(provider_key or "").strip()
    if key == "manual":
        return True

    definition = ProviderDefinitionsRepository().get_by_key("captcha", key)
    if not definition or not definition.enabled:
        return False

    merged = ProviderSettingsRepository().resolve_runtime_settings("captcha", key, extra or {})
    auth_fields = _definition_auth_fields(definition)
    if not auth_fields:
        return True
    return any(str(merged.get(field_key, "")).strip() for field_key in auth_fields)


def create_captcha_solver(provider_key: str, extra: dict | None = None) -> BaseCaptcha:
    from infrastructure.provider_definitions_repository import ProviderDefinitionsRepository
    from infrastructure.provider_settings_repository import ProviderSettingsRepository
    from providers.captcha.local_solver import LocalSolverCaptcha
    from providers.captcha.manual import ManualCaptcha
    from providers.captcha.twocaptcha import TwoCaptcha
    from providers.captcha.yescaptcha import YesCaptcha

    key = str(provider_key or "").strip().lower()
    if key == "manual":
        return ManualCaptcha()

    definition = ProviderDefinitionsRepository().get_by_key("captcha", key)
    if not definition or not definition.enabled:
        _raise_keyed(RuntimeError, "core.293461f5", provider=key)
    merged = ProviderSettingsRepository().resolve_runtime_settings("captcha", key, extra or {})
    driver_type = (definition.driver_type if definition else key).lower()

    if driver_type == "local_solver":
        return LocalSolverCaptcha(str(merged.get("solver_url", "") or ""))
    if driver_type == "yescaptcha_api":
        client_key = str(merged.get("yescaptcha_key", "") or "")
        if not client_key:
            _raise_keyed(RuntimeError, "core.963e5ef1")
        return YesCaptcha(client_key)
    if driver_type == "twocaptcha_api":
        api_key = str(merged.get("twocaptcha_key", "") or "")
        if not api_key:
            _raise_keyed(RuntimeError, "core.3e6b0a75")
        return TwoCaptcha(api_key)
    _raise_keyed(ValueError, "core.f34d1c98", provider=provider_key)
