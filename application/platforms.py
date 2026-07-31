from __future__ import annotations

from i18n import t
from infrastructure.platform_runtime import PlatformRuntime


EXECUTOR_LABELS = {
    "protocol": "application.ec83bb04",
    "headless": "application.c161fc9b",
    "headed": "application.38258a58",
}

IDENTITY_MODE_LABELS = {
    "mailbox": "application.415fd6aa",
    "oauth_browser": "application.94b52a85",
}

OAUTH_PROVIDER_LABELS = {
    "google": "Google",
    "github": "GitHub",
    "microsoft": "Microsoft",
    "linkedin": "LinkedIn",
    "apple": "Apple",
    "x": "X",
    "builderid": "Builder ID",
}


def _choice_options(values: list[str], labels: dict[str, str], lang: str) -> list[dict]:
    return [
        {"value": value, "label": t(labels.get(value, value), lang)}
        for value in values
        if str(value or "").strip()
    ]


def collect_platform_choice_options(platforms: list[dict], lang: str) -> dict[str, list[dict]]:
    executor_values: list[str] = []
    identity_values: list[str] = []
    oauth_values: list[str] = []
    for item in platforms:
        for value in item.get("supported_executors", []) or []:
            if value not in executor_values:
                executor_values.append(value)
        for value in item.get("supported_identity_modes", []) or []:
            if value not in identity_values:
                identity_values.append(value)
        for value in item.get("supported_oauth_providers", []) or []:
            if value not in oauth_values:
                oauth_values.append(value)
    return {
        "executor_options": _choice_options(executor_values, EXECUTOR_LABELS, lang),
        "identity_mode_options": _choice_options(identity_values, IDENTITY_MODE_LABELS, lang),
        "oauth_provider_options": _choice_options(oauth_values, OAUTH_PROVIDER_LABELS, lang),
    }


class PlatformsService:
    def __init__(self, runtime: PlatformRuntime | None = None):
        self.runtime = runtime or PlatformRuntime()

    def list_platforms(self, lang: str) -> list[dict]:
        result = []
        for item in self.runtime.list_platforms():
            result.append(
                {
                    "name": item.name,
                    "display_name": item.display_name,
                    "version": item.version,
                    "supported_executors": item.capabilities.supported_executors,
                    "supported_identity_modes": item.capabilities.supported_identity_modes,
                    "supported_oauth_providers": item.capabilities.supported_oauth_providers,
                    "supported_executor_options": _choice_options(item.capabilities.supported_executors, EXECUTOR_LABELS, lang),
                    "supported_identity_mode_options": _choice_options(item.capabilities.supported_identity_modes, IDENTITY_MODE_LABELS, lang),
                    "supported_oauth_provider_options": _choice_options(item.capabilities.supported_oauth_providers, OAUTH_PROVIDER_LABELS, lang),
                }
            )
        return result

    def get_desktop_state(self, platform: str) -> dict:
        return self.runtime.get_desktop_state(platform)
