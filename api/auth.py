from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_ui_language
from i18n import t

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str = ""


@router.get("/check")
def auth_check():
    """Return whether the app requires a password."""
    password = os.environ.get("APP_PASSWORD", "").strip()
    return {"required": bool(password)}


@router.post("/login")
def auth_login(body: LoginRequest, lang: str = Depends(get_ui_language)):
    password = os.environ.get("APP_PASSWORD", "").strip()
    if not password:
        return {"ok": True}
    if body.password == password:
        return {"ok": True, "token": password}
    return {"ok": False, "error": t("api.4585c822", lang)}
