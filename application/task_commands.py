from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from application.tasks import (
    TASK_STATUS_CANCELLED,
    TASK_STATUS_FAILED,
    TASK_STATUS_INTERRUPTED,
    TERMINAL_TASK_STATUSES,
    create_register_task,
    get_task,
    list_task_events,
    request_cancel,
)
from i18n import render_result, t
from services.task_runtime import task_runtime


class TaskCommandsService:
    def create_register_task(self, payload: dict) -> dict:
        task = create_register_task(payload)
        task_runtime.wake_up()
        return task

    def cancel_task(self, task_id: str) -> dict | None:
        task = request_cancel(task_id)
        if task:
            task_runtime.wake_up()
        return task

    async def stream_task_events(self, task_id: str, *, since: int = 0, lang: str = "zh") -> AsyncIterator[str]:
        cursor = since
        terminal_sent = False
        heartbeat_interval = 10.0
        loop = asyncio.get_running_loop()
        last_stream_activity = loop.time()

        yield "retry: 5000\n"
        yield ": connected\n\n"

        while True:
            emitted = False
            items = list_task_events(task_id, since=cursor, limit=200)
            for item in items:
                cursor = max(cursor, int(item["id"] or 0))
                # 这是文档记录的日志/轮询兜底路径之一（project-context.md），
                # 每个 task/event payload 在编码进 SSE data: 帧之前都要渲染，
                # 不能比 list_task_events 那条轮询边界更容易漏出原始标记 JSON —
                # This is one of the documented log/polling-fallback paths
                # (project-context.md); every task/event payload is rendered
                # before it is JSON-encoded into an SSE data: frame, so this
                # path is no more likely than the list_task_events polling
                # boundary to leak raw marker JSON.
                yield f"data: {json.dumps(render_result(item, lang), ensure_ascii=False)}\n\n"
                emitted = True

            current = get_task(task_id)
            if not current:
                yield f"data: {json.dumps({'done': True, 'status': TASK_STATUS_FAILED, 'line': t('api.d1817495', lang)}, ensure_ascii=False)}\n\n"
                break
            current = render_result(current, lang)
            if current["status"] in TERMINAL_TASK_STATUSES:
                if items:
                    await asyncio.sleep(0)
                    continue
                if not terminal_sent:
                    terminal_sent = True
                    if current["status"] == TASK_STATUS_INTERRUPTED:
                        line = t("application.9145106d", lang)
                    elif current["status"] == TASK_STATUS_CANCELLED:
                        line = t("application.6f96c2ad", lang)
                    elif current["status"] == TASK_STATUS_FAILED:
                        line = current.get("error") or t("application.558518b1", lang)
                    else:
                        line = t("application.e9a880e5", lang)
                    yield f"data: {json.dumps({'done': True, 'status': current['status'], 'line': line}, ensure_ascii=False)}\n\n"
                break
            if emitted:
                last_stream_activity = loop.time()
            elif loop.time() - last_stream_activity >= heartbeat_interval:
                yield ": ping\n\n"
                last_stream_activity = loop.time()
            await asyncio.sleep(0.5)
