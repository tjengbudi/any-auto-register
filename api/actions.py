from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_ui_language
from application.actions import ActionsService
from domain.actions import ActionExecutionCommand
from i18n import render_marker, render_result, t

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
    if task.get("sync"):
        # sync 动作的 data/error 里可能携带 worker 线程写入的标记字符串，
        # lang 已经在这个请求边界解析过，直接渲染再返回 (AD-3/AD-8) —
        # A sync action's data/error may carry marker strings written by a
        # worker thread; `lang` is already resolved at this request
        # boundary, so render before the response is built (AD-3/AD-8).
        task["data"] = render_result(task.get("data"), lang)
        task["error"] = render_marker(task.get("error", ""), lang)
    return task
