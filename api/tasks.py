from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_ui_language
from application.tasks_query import TasksQueryService
from i18n import t

router = APIRouter(prefix="/tasks", tags=["tasks"])
service = TasksQueryService()


@router.get("")
def list_tasks(platform: str = "", status: str = "", page: int = 1, page_size: int = 50):
    return service.list_tasks(platform=platform, status=status, page=page, page_size=page_size)


@router.get("/{task_id}")
def get_task(task_id: str, lang: str = Depends(get_ui_language)):
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(404, t("api.d1817495", lang))
    return task


@router.get("/{task_id}/events")
def list_task_events(task_id: str, since: int = 0, limit: int = 200, lang: str = Depends(get_ui_language)):
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(404, t("api.d1817495", lang))
    return service.list_events(task_id, since=since, limit=limit)
