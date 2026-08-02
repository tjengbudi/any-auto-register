from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_ui_language, render_detail
from application.config import ConfigService

router = APIRouter(prefix="/config", tags=["config"])
service = ConfigService()


class ConfigUpdateRequest(BaseModel):
    data: dict[str, str] = Field(default_factory=dict)


@router.get("")
def get_config():
    return service.get_config()


@router.get("/options")
def get_config_options(lang: str = Depends(get_ui_language)):
    return service.get_options(lang)


@router.put("")
def update_config(body: ConfigUpdateRequest, lang: str = Depends(get_ui_language)):
    try:
        return service.update_config(body.data)
    except ValueError as exc:
        raise HTTPException(400, render_detail(exc, lang)) from exc
