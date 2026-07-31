from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_ui_language
from application.platforms import PlatformsService

router = APIRouter(prefix="/platforms", tags=["platforms"])
service = PlatformsService()


@router.get("")
def list_platforms(lang: str = Depends(get_ui_language)):
    return service.list_platforms(lang)


@router.get("/{platform}/desktop-state")
def get_desktop_state(platform: str, lang: str = Depends(get_ui_language)):
    return service.get_desktop_state(platform, lang)
