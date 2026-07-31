from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_ui_language, render_detail
from application.provider_definitions import ProviderDefinitionsService
from i18n import t

router = APIRouter(prefix="/provider-definitions", tags=["provider-definitions"])
service = ProviderDefinitionsService()


class ProviderDefinitionUpsertRequest(BaseModel):
    id: int | None = None
    provider_type: str
    provider_key: str
    label: str
    description: str = ""
    driver_type: str
    enabled: bool = True
    default_auth_mode: str = ""
    metadata: dict = Field(default_factory=dict)


@router.get("")
def list_provider_definitions(provider_type: str, enabled_only: bool = False, lang: str = Depends(get_ui_language)):
    return service.list_definitions(provider_type, lang, enabled_only=enabled_only)


@router.get("/drivers")
def list_provider_drivers(provider_type: str, lang: str = Depends(get_ui_language)):
    return service.list_driver_templates(provider_type, lang)


@router.put("")
def save_provider_definition(body: ProviderDefinitionUpsertRequest, lang: str = Depends(get_ui_language)):
    return service.save_definition(body.model_dump(), lang)


@router.post("")
def create_provider_definition(body: ProviderDefinitionUpsertRequest, lang: str = Depends(get_ui_language)):
    return service.save_definition(body.model_dump(), lang)


@router.delete("/{definition_id}")
def delete_provider_definition(definition_id: int, lang: str = Depends(get_ui_language)):
    try:
        result = service.delete_definition(definition_id)
    except ValueError as exc:
        raise HTTPException(400, render_detail(exc, lang))
    if not result["ok"]:
        raise HTTPException(404, t("api.f4a7f40a", lang))
    return result
