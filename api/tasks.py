from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_ui_language
from application.tasks_query import TasksQueryService
from i18n import render_marker, render_result, t

router = APIRouter(prefix="/tasks", tags=["tasks"])
service = TasksQueryService()


@router.get("")
def list_tasks(platform: str = "", status: str = "", page: int = 1, page_size: int = 50, lang: str = Depends(get_ui_language)):
    page_result = service.list_tasks(platform=platform, status=status, page=page, page_size=page_size)
    # Task History 列表：每个 item 的 error/result（含嵌套 data）字段都可能携带
    # worker 线程写入的标记字符串，在这里统一渲染，不能让原始 JSON 漏到界面上 —
    # Task History list: every item's error/result (including nested data)
    # fields may carry marker strings written by a worker thread; render
    # them here uniformly so raw JSON never leaks to the UI.
    page_result["items"] = [_render_task_item(item, lang) for item in page_result.get("items", [])]
    return page_result


@router.get("/{task_id}")
def get_task(task_id: str, lang: str = Depends(get_ui_language)):
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(404, t("api.d1817495", lang))
    return _render_task_item(task, lang)


@router.get("/{task_id}/events")
def list_task_events(task_id: str, since: int = 0, limit: int = 200, lang: str = Depends(get_ui_language)):
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(404, t("api.d1817495", lang))
    events = service.list_events(task_id, since=since, limit=limit)
    events["items"] = [render_result(item, lang) for item in events.get("items", [])]
    return events


def _render_task_item(task: dict, lang: str) -> dict:
    """渲染一个任务序列化结果里所有携带标记字符串的字段 —
    Render every marker-bearing field of one serialized task result.

    这个响应形状（TasksQueryService._serialize）没有顶层 data 字段——
    result.data 已经嵌套在 result 里，跟 errors 一起靠 render_result 递归覆盖 —
    This response shape (TasksQueryService._serialize) has no top-level
    `data` field -- `result.data` already nests inside `result`, covered
    recursively by render_result alongside `errors`.
    """
    task["error"] = render_marker(task.get("error", ""), lang)
    task["result"] = render_result(task.get("result"), lang)
    task["errors"] = render_result(task.get("errors"), lang)
    return task
