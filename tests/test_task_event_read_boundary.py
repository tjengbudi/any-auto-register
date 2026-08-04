"""story 4.2 -- the read boundary renders once per batch.

Covers the I/O & Edge-Case Matrix in
`_bmad-output/implementation-artifacts/spec-4-2-the-read-boundary-renders-once-per-batch.md`:
a `log_key`-written row must re-render in whatever `ui_language` the caller
resolved (not the `zh` it was written under), a pre-4.1/unkeyed row must
always render from its stored `message` regardless of `ui_language`, a
single batch renders every row through one shared `ui_language` (no
per-row drift), and an `i18n_params` name that collides with `t()`'s own
`key`/`lang` parameters degrades to the stored message instead of raising
(AD-10 -- the read boundary never raises).

Exercised end-to-end through both real callers: the polling route
(`GET /api/tasks/{task_id}/events`) and the SSE stream
(`TaskCommandsService.stream_task_events`).
"""
from __future__ import annotations

import asyncio

from application.task_commands import TaskCommandsService
from application.tasks import TASK_STATUS_SUCCEEDED, TaskLogger, append_task_event, create_platform_action_task, list_task_events
from i18n import t

# Real catalog key with a param, used to prove actual re-rendering (not just
# that some string comes back): zh "不支持测试的 provider 类型: {provider_type}"
# / en "Testing is not supported for provider type: {provider_type}".
_KEY = "api.373ed38b"
_PARAMS = {"provider_type": "acme"}


def _set_lang(client, lang: str) -> None:
    if lang != "zh":
        resp = client.put("/api/config", json={"data": {"ui_language": lang}})
        assert resp.status_code == 200


def _new_task() -> str:
    task = create_platform_action_task({"platform": "blink", "account_id": 1, "action_id": "get_account_state"})
    return task["id"]


# --- serialize_event / list_task_events (direct, unit-level) ----------------


def test_keyed_event_language_switch_renders_english():
    task_id = _new_task()
    TaskLogger(task_id).log_key(_KEY, params=_PARAMS)

    events = list_task_events(task_id, ui_language="en")
    keyed = next(e for e in events if e["detail"].get("i18n_key") == _KEY)

    expected = t(_KEY, "en", **_PARAMS)
    assert keyed["message"] == expected
    assert keyed["line"].endswith(f"] {expected}")


def test_same_row_renders_differently_for_zh_vs_en():
    task_id = _new_task()
    TaskLogger(task_id).log_key(_KEY, params=_PARAMS)

    zh_events = list_task_events(task_id, ui_language="zh")
    en_events = list_task_events(task_id, ui_language="en")
    zh_keyed = next(e for e in zh_events if e["detail"].get("i18n_key") == _KEY)
    en_keyed = next(e for e in en_events if e["detail"].get("i18n_key") == _KEY)

    assert zh_keyed["message"] == t(_KEY, "zh", **_PARAMS)
    assert en_keyed["message"] == t(_KEY, "en", **_PARAMS)
    assert zh_keyed["message"] != en_keyed["message"]


def test_unkeyed_row_always_renders_stored_message_regardless_of_language():
    task_id = _new_task()
    TaskLogger(task_id).log("这是一条普通消息", event_type="log")

    zh_events = list_task_events(task_id, ui_language="zh")
    en_events = list_task_events(task_id, ui_language="en")
    zh_plain = next(e for e in zh_events if e["message"] == "这是一条普通消息")
    en_plain = next(e for e in en_events if e["message"] == "这是一条普通消息")

    assert zh_plain["message"] == "这是一条普通消息"
    assert en_plain["message"] == "这是一条普通消息"


def test_mixed_batch_all_render_through_single_ui_language():
    task_id = _new_task()
    logger = TaskLogger(task_id)
    # 3 keyed + 2 unkeyed rows (plus the auto "task created" unkeyed row).
    logger.log_key(_KEY, params={"provider_type": "one"})
    logger.log("plain-1")
    logger.log_key(_KEY, params={"provider_type": "two"})
    logger.log("plain-2")
    logger.log_key(_KEY, params={"provider_type": "three"})

    events = list_task_events(task_id, ui_language="en")
    keyed = [e for e in events if e["detail"].get("i18n_key") == _KEY]
    plain = [e for e in events if e["message"] in ("plain-1", "plain-2")]

    assert len(keyed) == 3
    assert {e["message"] for e in keyed} == {
        t(_KEY, "en", provider_type="one"),
        t(_KEY, "en", provider_type="two"),
        t(_KEY, "en", provider_type="three"),
    }
    assert len(plain) == 2
    assert {e["message"] for e in plain} == {"plain-1", "plain-2"}


def test_i18n_params_collision_falls_back_to_stored_message():
    task_id = _new_task()
    # Written directly via append_task_event (not TaskLogger.log_key, whose
    # own zh render would raise eagerly on this collision) -- simulates a
    # row already persisted with a colliding param name.
    stored_message = "存的中文消息"
    append_task_event(
        task_id,
        stored_message,
        detail={"i18n_key": _KEY, "i18n_params": {"lang": "x"}},
    )

    events = list_task_events(task_id, ui_language="en")
    collided = next(e for e in events if e["message"] == stored_message)

    assert collided["message"] == stored_message
    assert collided["line"].endswith(f"] {stored_message}")


def test_malformed_detail_json_does_not_raise():
    """A non-dict detail_json (e.g. a legacy/corrupt row) must not crash the
    read boundary -- serialize_event guards with isinstance(detail, dict)."""
    from sqlmodel import Session

    from core.db import TaskEventModel, engine

    task_id = _new_task()
    with Session(engine) as session:
        session.add(TaskEventModel(task_id=task_id, message="raw row", detail_json="null"))
        session.commit()

    events = list_task_events(task_id, ui_language="en")
    raw = next(e for e in events if e["message"] == "raw row")
    assert raw["detail"] is None


# --- polling route: GET /api/tasks/{task_id}/events --------------------------


def test_polling_route_renders_keyed_event_in_requested_language(client):
    task_id = _new_task()
    TaskLogger(task_id).log_key(_KEY, params=_PARAMS)

    _set_lang(client, "en")
    resp = client.get(f"/api/tasks/{task_id}/events")
    assert resp.status_code == 200
    items = resp.json()["items"]
    keyed = next(i for i in items if i["detail"].get("i18n_key") == _KEY)
    assert keyed["message"] == t(_KEY, "en", **_PARAMS)


def test_polling_route_default_language_renders_chinese(client):
    task_id = _new_task()
    TaskLogger(task_id).log_key(_KEY, params=_PARAMS)

    resp = client.get(f"/api/tasks/{task_id}/events")
    assert resp.status_code == 200
    items = resp.json()["items"]
    keyed = next(i for i in items if i["detail"].get("i18n_key") == _KEY)
    assert keyed["message"] == t(_KEY, "zh", **_PARAMS)


def test_polling_route_mixed_batch_single_language(client):
    task_id = _new_task()
    logger = TaskLogger(task_id)
    logger.log_key(_KEY, params={"provider_type": "one"})
    logger.log("plain-row")
    logger.log_key(_KEY, params={"provider_type": "two"})

    _set_lang(client, "en")
    resp = client.get(f"/api/tasks/{task_id}/events")
    assert resp.status_code == 200
    items = resp.json()["items"]
    keyed = [i for i in items if i["detail"].get("i18n_key") == _KEY]
    plain = next(i for i in items if i["message"] == "plain-row")

    assert {i["message"] for i in keyed} == {
        t(_KEY, "en", provider_type="one"),
        t(_KEY, "en", provider_type="two"),
    }
    assert plain["message"] == "plain-row"


def test_polling_route_i18n_params_collision_falls_back(client):
    task_id = _new_task()
    stored_message = "存的中文消息-路由"
    append_task_event(task_id, stored_message, detail={"i18n_key": _KEY, "i18n_params": {"lang": "x"}})

    _set_lang(client, "en")
    resp = client.get(f"/api/tasks/{task_id}/events")
    assert resp.status_code == 200
    items = resp.json()["items"]
    collided = next(i for i in items if i["message"] == stored_message)
    assert collided["message"] == stored_message


# --- SSE stream: TaskCommandsService.stream_task_events -----------------------


def _collect_sse_events(task_id: str, lang: str, *, max_frames: int = 20) -> list[dict]:
    async def _run() -> list[dict]:
        import json as _json

        frames = []
        service = TaskCommandsService()
        async for chunk in service.stream_task_events(task_id, since=0, lang=lang):
            if chunk.startswith("data: "):
                frames.append(_json.loads(chunk[len("data: "):].strip()))
            if len(frames) >= max_frames:
                break
        return frames

    return asyncio.run(_run())


def test_sse_stream_renders_keyed_event_in_requested_language():
    task_id = _new_task()
    TaskLogger(task_id).log_key(_KEY, params=_PARAMS)
    TaskLogger(task_id).finish(TASK_STATUS_SUCCEEDED)

    frames = _collect_sse_events(task_id, "en")
    keyed = next(f for f in frames if f.get("detail", {}).get("i18n_key") == _KEY)
    assert keyed["message"] == t(_KEY, "en", **_PARAMS)


def test_sse_stream_mixed_batch_single_language():
    task_id = _new_task()
    logger = TaskLogger(task_id)
    logger.log_key(_KEY, params={"provider_type": "one"})
    logger.log("plain-row-sse")
    logger.log_key(_KEY, params={"provider_type": "two"})
    logger.finish(TASK_STATUS_SUCCEEDED)

    frames = _collect_sse_events(task_id, "en")
    keyed = [f for f in frames if f.get("detail", {}).get("i18n_key") == _KEY]
    plain = next(f for f in frames if f.get("message") == "plain-row-sse")

    assert {f["message"] for f in keyed} == {
        t(_KEY, "en", provider_type="one"),
        t(_KEY, "en", provider_type="two"),
    }
    assert plain["message"] == "plain-row-sse"


def test_sse_stream_i18n_params_collision_falls_back():
    task_id = _new_task()
    stored_message = "存的中文消息-sse"
    append_task_event(task_id, stored_message, detail={"i18n_key": _KEY, "i18n_params": {"lang": "x"}})
    TaskLogger(task_id).finish(TASK_STATUS_SUCCEEDED)

    frames = _collect_sse_events(task_id, "en")
    collided = next(f for f in frames if f.get("message") == stored_message)
    assert collided["message"] == stored_message
