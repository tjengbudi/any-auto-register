"""story 4.3 -- failures travel the log path, and the panel's own frame is
translated.

Covers the I/O & Edge-Case Matrix from this story's spec:
  - an except-handler catching an unkeyed exception emits a fallback key with
    str(exc) embedded as a scalar param, in both the log event and
    task.error, never a bare str(exc) interpolation;
  - an except-handler catching a keyed exception (carrying i18n_key/
    i18n_params) forwards them directly, in both places, never stringified;
  - the 23 frame/lifecycle lines (task created/started/finished, ...)
    re-render per ui_language on read, with no task re-run;
  - a task-level failure (_execute_register_task's platform-lookup/
    mailbox-init except) reports in English then Chinese from the very same
    underlying marker via GET /api/tasks/{id}.
"""
from __future__ import annotations

import json

import application.tasks as tasks_module
from application.tasks import (
    TASK_STATUS_FAILED,
    TASK_STATUS_SUCCEEDED,
    TaskLogger,
    _exc_key,
    _execute_account_check_task,
    _execute_register_task,
    create_account_check_task,
    create_register_task,
    create_task,
    get_task,
    list_task_events,
)
from i18n import t

# Real catalog key with a {param} placeholder, borrowed as a stand-in "inner"
# key an upstream (future) keyed raise might carry -- mirrors
# tests/test_task_event_read_boundary.py's own choice of this same key.
_KEYED_EXC_KEY = "api.373ed38b"
_KEYED_EXC_PARAMS = {"provider_type": "acme"}


def _set_lang(client, lang: str) -> None:
    # Unlike most existing i18n tests (which only ever set "en" once per
    # test, so skipping "zh" as a no-op default is safe), the REST round
    # trip tests below switch language back and forth within one test --
    # "zh" must be an explicit PUT here too, or it would silently keep
    # whatever language a prior call in the same test already set.
    resp = client.put("/api/config", json={"data": {"ui_language": lang}})
    assert resp.status_code == 200


class _KeyedError(Exception):
    """A caught exception carrying i18n_key/i18n_params (AD-8/AD-17)."""


def _make_keyed_error(message: str = "boom-keyed") -> _KeyedError:
    exc = _KeyedError(message)
    exc.i18n_key = _KEYED_EXC_KEY
    exc.i18n_params = dict(_KEYED_EXC_PARAMS)
    return exc


# --- _exc_key unit coverage ---------------------------------------------


def test_exc_key_unkeyed_exception_falls_back():
    exc = RuntimeError("plain failure")
    key, params = _exc_key(exc, "application.b404b7e1", detail=str(exc))
    assert key == "application.b404b7e1"
    assert params == {"detail": "plain failure"}


def test_exc_key_keyed_exception_forwards_untouched():
    exc = _make_keyed_error()
    key, params = _exc_key(exc, "application.b404b7e1", detail=str(exc))
    assert key == _KEYED_EXC_KEY
    assert params == _KEYED_EXC_PARAMS


def test_exc_key_keyed_exception_with_non_dict_params_falls_back_to_empty():
    exc = RuntimeError("boom")
    exc.i18n_key = "core.something"
    exc.i18n_params = "not-a-dict"
    key, params = _exc_key(exc, "application.b404b7e1", detail=str(exc))
    assert key == "core.something"
    assert params == {}


def test_exc_key_keyed_exception_with_reserved_param_name_falls_back_to_fallback():
    # "key"/"lang" collide with t()'s and _marker()'s own positional
    # parameter names when forwarded via **params -- must fall back to the
    # caller's fallback entirely rather than crash the caller with a
    # "multiple values for argument" TypeError.
    exc = RuntimeError("boom")
    exc.i18n_key = "core.something"
    exc.i18n_params = {"key": "clobbered", "detail": "x"}
    key, params = _exc_key(exc, "application.b404b7e1", detail=str(exc))
    assert key == "application.b404b7e1"
    assert params == {"detail": "boom"}


def test_exc_key_keyed_exception_with_non_scalar_param_falls_back_to_fallback():
    # A non-scalar value would make log_key() raise ValueError uncaught
    # inside an already-exceptional block -- fall back instead.
    exc = RuntimeError("boom")
    exc.i18n_key = "core.something"
    exc.i18n_params = {"detail": ["not", "a", "scalar"]}
    key, params = _exc_key(exc, "application.b404b7e1", detail=str(exc))
    assert key == "application.b404b7e1"
    assert params == {"detail": "boom"}


# --- except-handler, unkeyed exception (I/O matrix row 1) ---------------


def test_account_check_unkeyed_exception_uses_fallback_key_and_marker(monkeypatch):
    task = create_account_check_task(1)
    task_id = task["id"]

    def _boom(account_id, logger=None):
        raise RuntimeError("boom-plain")

    monkeypatch.setattr(tasks_module, "_run_single_account_check", _boom)
    _execute_account_check_task({"account_id": 1}, TaskLogger(task_id))

    events = list_task_events(task_id, ui_language="en")
    keyed = next(e for e in events if e["detail"].get("i18n_key") == "application.b404b7e1")
    assert keyed["detail"]["i18n_params"] == {"detail": "boom-plain"}
    assert keyed["level"] == "error"
    assert keyed["message"] == t("application.b404b7e1", "en", detail="boom-plain")

    task = get_task(task_id)
    assert task["status"] == TASK_STATUS_FAILED
    marker = json.loads(task["error"])
    assert marker == {"i18n_key": "application.b404b7e1", "i18n_params": {"detail": "boom-plain"}}


# --- except-handler, keyed exception (I/O matrix row 2) ------------------


def test_account_check_keyed_exception_forwards_key_and_params_never_stringified(monkeypatch):
    task = create_account_check_task(1)
    task_id = task["id"]

    def _boom(account_id, logger=None):
        raise _make_keyed_error("boom-keyed")

    monkeypatch.setattr(tasks_module, "_run_single_account_check", _boom)
    _execute_account_check_task({"account_id": 1}, TaskLogger(task_id))

    events = list_task_events(task_id, ui_language="en")
    keyed = next(e for e in events if e["detail"].get("i18n_key") == _KEYED_EXC_KEY)
    assert keyed["detail"]["i18n_params"] == _KEYED_EXC_PARAMS
    assert keyed["message"] == t(_KEYED_EXC_KEY, "en", **_KEYED_EXC_PARAMS)
    # The fallback key never appears -- the inner exception's own key wins.
    assert not any(e["detail"].get("i18n_key") == "application.b404b7e1" for e in events)
    # Never stringified: "boom-keyed" itself never leaks into the rendered message.
    assert "boom-keyed" not in keyed["message"]

    task = get_task(task_id)
    marker = json.loads(task["error"])
    assert marker == {"i18n_key": _KEYED_EXC_KEY, "i18n_params": _KEYED_EXC_PARAMS}


# --- frame line, language switch (I/O matrix row 3) ----------------------


def test_frame_lines_rerender_on_language_switch_without_rerun():
    task = create_task(task_type="register", platform="windsurf", payload={})
    task_id = task["id"]
    logger = TaskLogger(task_id)
    logger.mark_running()
    logger.finish(TASK_STATUS_SUCCEEDED)

    zh_events = list_task_events(task_id, ui_language="zh")
    en_events = list_task_events(task_id, ui_language="en")

    def _by_key(events, key):
        return next(e for e in events if e["detail"].get("i18n_key") == key)

    created_zh = _by_key(zh_events, "application.540aefd8")
    created_en = _by_key(en_events, "application.540aefd8")
    assert created_zh["message"] == "任务已创建: register"
    assert created_en["message"] == "Task created: register"

    started_zh = _by_key(zh_events, "application.7f935d40")
    started_en = _by_key(en_events, "application.7f935d40")
    assert started_zh["message"] == "任务已开始执行"
    assert started_en["message"] == "Task execution started"

    finished_zh = _by_key(zh_events, "application.260e6363")
    finished_en = _by_key(en_events, "application.260e6363")
    assert finished_zh["message"] == "任务结束: succeeded"
    assert finished_en["message"] == "Task finished: succeeded"

    # Same underlying rows -- ids line up 1:1 between the two language reads.
    assert [e["id"] for e in zh_events] == [e["id"] for e in en_events]


# --- task-level failure via REST, mailbox-init/platform-lookup except
#     (I/O matrix row 4) ---------------------------------------------------


def test_register_task_platform_lookup_failure_renders_via_rest_en_then_zh(client, monkeypatch):
    # Force the platform-lookup except at application.tasks.py's
    # `get(platform_name)` call, deterministically and without touching any
    # real platform registry state.
    def _boom(name):
        raise RuntimeError("platform lookup boom")

    monkeypatch.setattr(tasks_module, "get", _boom)

    task = create_register_task({"platform": "windsurf", "count": 1, "extra": {}})
    task_id = task["id"]
    _execute_register_task({"platform": "windsurf", "count": 1, "extra": {}}, TaskLogger(task_id))

    _set_lang(client, "en")
    resp_en = client.get(f"/api/tasks/{task_id}")
    assert resp_en.status_code == 200
    body_en = resp_en.json()
    assert body_en["status"] == TASK_STATUS_FAILED
    assert body_en["error"] == "Fatal error: platform lookup boom"
    assert "i18n_key" not in body_en["error"]

    _set_lang(client, "zh")
    resp_zh = client.get(f"/api/tasks/{task_id}")
    assert resp_zh.status_code == 200
    assert resp_zh.json()["error"] == "致命错误: platform lookup boom"


def test_register_task_mailbox_init_failure_renders_via_rest_en_then_zh(client, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("mailbox init boom")

    monkeypatch.setattr(tasks_module, "get", lambda name: object)
    import core.base_mailbox as base_mailbox_module

    monkeypatch.setattr(base_mailbox_module, "create_mailbox", _boom)

    payload = {"platform": "windsurf", "count": 1, "extra": {"mail_provider": "anything"}}
    task = create_register_task(payload)
    task_id = task["id"]
    _execute_register_task(payload, TaskLogger(task_id))

    _set_lang(client, "en")
    resp_en = client.get(f"/api/tasks/{task_id}")
    assert resp_en.status_code == 200
    body_en = resp_en.json()
    assert body_en["status"] == TASK_STATUS_FAILED
    assert body_en["error"] == "Mailbox initialization failed: mailbox init boom"

    _set_lang(client, "zh")
    resp_zh = client.get(f"/api/tasks/{task_id}")
    assert resp_zh.status_code == 200
    assert resp_zh.json()["error"] == "邮箱初始化失败: mailbox init boom"


# --- record_error/task.result["errors"] stay unchanged -------------------


def test_record_error_still_receives_plain_rendered_string(monkeypatch):
    """AC: task.result["errors"] and record_error's call sites are unchanged
    -- still rendered strings for counting only, never a key or marker."""
    task = create_account_check_task(1)
    task_id = task["id"]

    def _boom(account_id, logger=None):
        raise RuntimeError("boom-for-errors-list")

    monkeypatch.setattr(tasks_module, "_run_single_account_check", _boom)
    _execute_account_check_task({"account_id": 1}, TaskLogger(task_id))

    task = get_task(task_id)
    assert task["errors"] == ["boom-for-errors-list"]
