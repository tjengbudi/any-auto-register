from __future__ import annotations

from i18n import t
from infrastructure.provider_definitions_repository import ProviderDefinitionsRepository


def _render_auth_modes(auth_modes: list[dict], lang: str) -> list[dict]:
    return [
        {**mode, "label": t(mode.get("label", ""), lang)}
        for mode in auth_modes
    ]


def _render_fields(fields: list[dict], lang: str) -> list[dict]:
    rendered = []
    for field in fields:
        item = dict(field)
        if item.get("label"):
            item["label"] = t(item["label"], lang)
        if item.get("placeholder"):
            item["placeholder"] = t(item["placeholder"], lang)
        if item.get("hint"):
            item["hint"] = t(item["hint"], lang)
        rendered.append(item)
    return rendered


class ProviderDefinitionsService:
    def __init__(self, repository: ProviderDefinitionsRepository | None = None):
        self.repository = repository or ProviderDefinitionsRepository()

    def list_definitions(self, provider_type: str, lang: str, *, enabled_only: bool = False) -> list[dict]:
        return [self._serialize(item, lang) for item in self.repository.list_by_type(provider_type, enabled_only=enabled_only)]

    def list_driver_templates(self, provider_type: str, lang: str) -> list[dict]:
        templates = self.repository.list_driver_templates(provider_type)
        rendered = []
        for template in templates:
            item = dict(template)
            item["label"] = t(item.get("label", ""), lang)
            item["description"] = t(item.get("description", ""), lang)
            item["auth_modes"] = _render_auth_modes(item.get("auth_modes") or [], lang)
            item["fields"] = _render_fields(item.get("fields") or [], lang)
            rendered.append(item)
        return rendered

    def save_definition(self, payload: dict, lang: str) -> dict:
        item = self.repository.save(
            definition_id=payload.get("id"),
            provider_type=str(payload.get("provider_type") or ""),
            provider_key=str(payload.get("provider_key") or ""),
            label=str(payload.get("label") or ""),
            description=str(payload.get("description") or ""),
            driver_type=str(payload.get("driver_type") or ""),
            enabled=bool(payload.get("enabled", True)),
            default_auth_mode=str(payload.get("default_auth_mode") or ""),
            metadata=dict(payload.get("metadata") or {}),
        )
        return {"ok": True, "item": self._serialize(item, lang)}

    def delete_definition(self, definition_id: int) -> dict:
        return {"ok": self.repository.delete(definition_id)}

    def get_definition(self, provider_type: str, provider_key: str, lang: str = "zh") -> dict | None:
        item = self.repository.get_by_key(provider_type, provider_key)
        return self._serialize(item, lang) if item else None

    def _serialize(self, item, lang: str) -> dict:
        return {
            "id": int(item.id or 0),
            "provider_type": item.provider_type,
            "provider_key": item.provider_key,
            "value": item.provider_key,
            "label": t(item.label, lang),
            "description": t(item.description, lang),
            "driver_type": item.driver_type,
            "default_auth_mode": item.default_auth_mode,
            "auth_modes": _render_auth_modes(item.get_auth_modes(), lang),
            "fields": _render_fields(item.get_fields(), lang),
            "enabled": bool(item.enabled),
            "is_builtin": bool(getattr(item, "is_builtin", False)),
            "category": str(getattr(item, "category", "") or ""),
            "metadata": item.get_metadata(),
        }
