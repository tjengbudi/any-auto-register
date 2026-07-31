from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_ui_language
from application.actions import ActionsService
from domain.actions import ActionExecutionCommand
from i18n import t

router = APIRouter(prefix="/actions", tags=["actions"])
service = ActionsService()


class ActionRequest(BaseModel):
    params: dict = Field(default_factory=dict)


@router.get("/{platform}")
def list_actions(platform: str, lang: str = Depends(get_ui_language)):
    return service.list_actions(platform, lang)


@router.get("/{platform}/capabilities")
def list_capabilities(platform: str):
    return service.list_capabilities(platform)


@router.post("/{platform}/{account_id}/{action_id}")
def execute_action(
    platform: str,
    account_id: int,
    action_id: str,
    body: ActionRequest,
    lang: str = Depends(get_ui_language),
):
    task = service.execute_action(
        ActionExecutionCommand(
            platform=platform,
            account_id=account_id,
            action_id=action_id,
            params=body.params,
        )
    )
    if not task:
        raise HTTPException(400, t("api.2197e510", lang))
    return task
