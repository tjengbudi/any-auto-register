from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.deps import get_ui_language
from application.task_commands import TaskCommandsService
from application.tasks_query import TasksQueryService
from i18n import t

router = APIRouter(prefix="/tasks", tags=["task-commands"])
command_service = TaskCommandsService()
query_service = TasksQueryService()


class RegisterTaskRequest(BaseModel):
    platform: str
    email: Optional[str] = None
    password: Optional[str] = None
    count: int = 1
    concurrency: int = 1
    proxy: Optional[str] = None
    executor_type: str = "protocol"
    captcha_solver: str = "auto"
    extra: dict = Field(default_factory=dict)


@router.post("/register")
def create_register_task(body: RegisterTaskRequest):
    return command_service.create_register_task(body.model_dump())


@router.post("/{task_id}/cancel")
def cancel_task(task_id: str, lang: str = Depends(get_ui_language)):
    task = command_service.cancel_task(task_id)
    if not task:
        raise HTTPException(404, t("api.d1817495", lang))
    return task


@router.get("/{task_id}/logs/stream")
async def stream_logs(task_id: str, since: int = 0, lang: str = Depends(get_ui_language)):
    if not query_service.get_task(task_id):
        raise HTTPException(404, t("api.d1817495", lang))
    return StreamingResponse(
        command_service.stream_task_events(task_id, since=since),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
