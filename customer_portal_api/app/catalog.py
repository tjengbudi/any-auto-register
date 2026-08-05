from __future__ import annotations

from i18n import t


EXECUTOR_LABELS = {
    "protocol": "customerPortalApi.ec83bb04",
    "headless": "customerPortalApi.c161fc9b",
    "headed": "customerPortalApi.38258a58",
}

IDENTITY_MODE_LABELS = {
    "mailbox": "customerPortalApi.415fd6aa",
    "oauth_browser": "customerPortalApi.94b52a85",
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

PLATFORM_SEEDS: list[dict] = [
    {
        "platform_code": "chatgpt",
        "display_name": "ChatGPT",
        "version": "1.0.0",
        "supported_executors": ["protocol", "headless", "headed"],
        "supported_identity_modes": ["mailbox", "oauth_browser"],
        "supported_oauth_providers": ["google", "github", "microsoft"],
    },
    {
        "platform_code": "cursor",
        "display_name": "Cursor",
        "version": "1.0.0",
        "supported_executors": ["headless", "headed"],
        "supported_identity_modes": ["oauth_browser"],
        "supported_oauth_providers": ["google", "github"],
    },
    {
        "platform_code": "kiro",
        "display_name": "Kiro",
        "version": "1.0.0",
        "supported_executors": ["headless", "headed"],
        "supported_identity_modes": ["oauth_browser"],
        "supported_oauth_providers": ["google", "github", "builderid"],
    },
    {
        "platform_code": "blink",
        "display_name": "Blink",
        "version": "1.0.0",
        "supported_executors": ["protocol", "headless", "headed"],
        "supported_identity_modes": ["mailbox"],
        "supported_oauth_providers": [],
    },
    {
        "platform_code": "trae",
        "display_name": "Trae",
        "version": "1.0.0",
        "supported_executors": ["headless", "headed"],
        "supported_identity_modes": ["oauth_browser"],
        "supported_oauth_providers": ["google", "github"],
    },
    {
        "platform_code": "tavily",
        "display_name": "Tavily",
        "version": "1.0.0",
        "supported_executors": ["protocol"],
        "supported_identity_modes": ["mailbox"],
        "supported_oauth_providers": [],
    },
    {
        "platform_code": "openblocklabs",
        "display_name": "OpenBlockLabs",
        "version": "1.0.0",
        "supported_executors": ["protocol"],
        "supported_identity_modes": ["mailbox"],
        "supported_oauth_providers": [],
    },
    {
        "platform_code": "grok",
        "display_name": "Grok",
        "version": "1.0.0",
        "supported_executors": ["headless", "headed"],
        "supported_identity_modes": ["oauth_browser"],
        "supported_oauth_providers": ["google", "x"],
    },
]

PERMISSION_SEEDS: list[dict] = [
    {"permission_code": "admin:*", "permission_name": "customerPortalApi.85fe0023"},
    {"permission_code": "admin:user:read", "permission_name": "customerPortalApi.61e865c7"},
    {"permission_code": "admin:user:write", "permission_name": "customerPortalApi.fff6a05a"},
    {"permission_code": "admin:platform:read", "permission_name": "customerPortalApi.868312f0"},
    {"permission_code": "admin:config:read", "permission_name": "customerPortalApi.3b8ae0dc"},
    {"permission_code": "admin:config:write", "permission_name": "customerPortalApi.da1e8010"},
    {"permission_code": "admin:task:read", "permission_name": "customerPortalApi.36550b9c"},
    {"permission_code": "admin:account:read", "permission_name": "customerPortalApi.844264f7"},
    {"permission_code": "admin:account:write", "permission_name": "customerPortalApi.43568cc7"},
    {"permission_code": "admin:proxy:read", "permission_name": "customerPortalApi.1f4f69f7"},
    {"permission_code": "admin:proxy:write", "permission_name": "customerPortalApi.218e353f"},
    {"permission_code": "admin:order:read", "permission_name": "customerPortalApi.7546a59d"},
    {"permission_code": "admin:subscription:read", "permission_name": "customerPortalApi.98655b0f"},
    {"permission_code": "app:platform:view", "permission_name": "customerPortalApi.c734b096"},
    {"permission_code": "app:task:create", "permission_name": "customerPortalApi.9fee7688"},
    {"permission_code": "app:task:view_self", "permission_name": "customerPortalApi.c05bd245"},
    {"permission_code": "app:order:view_self", "permission_name": "customerPortalApi.fe63fd48"},
    {"permission_code": "app:order:create", "permission_name": "customerPortalApi.50504d10"},
    {"permission_code": "app:payment:submit", "permission_name": "customerPortalApi.e5f00c25"},
    {"permission_code": "app:subscription:view_self", "permission_name": "customerPortalApi.334b105b"},
    {"permission_code": "app:profile:view_self", "permission_name": "customerPortalApi.f802a135"},
    {"permission_code": "app:profile:update_self", "permission_name": "customerPortalApi.d1033f24"},
    {"permission_code": "payment:callback", "permission_name": "customerPortalApi.ff4c7790"},
]

ROLE_SEEDS: list[dict] = [
    {
        "role_code": "admin",
        "role_name": "customerPortalApi.e1979671",
        "permissions": [
            "admin:*",
            "admin:user:read",
            "admin:user:write",
            "admin:platform:read",
            "admin:config:read",
            "admin:config:write",
            "admin:task:read",
            "admin:account:read",
            "admin:account:write",
            "admin:proxy:read",
            "admin:proxy:write",
            "admin:order:read",
            "admin:subscription:read",
            "payment:callback",
            "app:platform:view",
            "app:task:view_self",
            "app:order:view_self",
            "app:subscription:view_self",
            "app:profile:view_self",
            "app:profile:update_self",
        ],
    },
    {
        "role_code": "user",
        "role_name": "customerPortalApi.f6a2faaa",
        "permissions": [
            "app:platform:view",
            "app:task:create",
            "app:task:view_self",
            "app:order:view_self",
            "app:order:create",
            "app:payment:submit",
            "app:subscription:view_self",
            "app:profile:view_self",
            "app:profile:update_self",
        ],
    },
]

PERMISSION_NAME_KEYS: dict[str, str] = {seed["permission_code"]: seed["permission_name"] for seed in PERMISSION_SEEDS}

ROLE_NAME_KEYS: dict[str, str] = {seed["role_code"]: seed["role_name"] for seed in ROLE_SEEDS}

CONFIG_DEFAULTS: dict[str, str] = {
    "default_executor": "protocol",
    "default_identity_provider": "mailbox",
    "default_oauth_provider": "",
    "oauth_email_hint": "",
    "chrome_user_data_dir": "",
    "chrome_cdp_url": "",
}


def choice_options(values: list[str], labels: dict[str, str], lang: str, *, translated: bool = True) -> list[dict]:
    result = []
    for value in values:
        if not str(value or "").strip():
            continue
        label = labels.get(value, value)
        if translated:
            label = t(label, lang)
        result.append({"value": value, "label": label})
    return result


def platform_payload(item: dict, lang: str) -> dict:
    supported_executors = list(item.get("supported_executors", []) or [])
    supported_identity_modes = list(item.get("supported_identity_modes", []) or [])
    supported_oauth_providers = list(item.get("supported_oauth_providers", []) or [])
    return {
        "name": item["platform_code"],
        "display_name": item["display_name"],
        "version": item.get("version", "1.0.0"),
        "supported_executors": supported_executors,
        "supported_identity_modes": supported_identity_modes,
        "supported_oauth_providers": supported_oauth_providers,
        "supported_executor_options": choice_options(supported_executors, EXECUTOR_LABELS, lang),
        "supported_identity_mode_options": choice_options(supported_identity_modes, IDENTITY_MODE_LABELS, lang),
        "supported_oauth_provider_options": choice_options(
            supported_oauth_providers, OAUTH_PROVIDER_LABELS, lang, translated=False
        ),
    }


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
        "executor_options": choice_options(executor_values, EXECUTOR_LABELS, lang),
        "identity_mode_options": choice_options(identity_values, IDENTITY_MODE_LABELS, lang),
        "oauth_provider_options": choice_options(oauth_values, OAUTH_PROVIDER_LABELS, lang, translated=False),
    }
