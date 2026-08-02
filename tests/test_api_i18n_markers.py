"""story 3.6 -- end-to-end coverage for the worker-thread marker convention and
the four request-scoped `t(key, lang)` sites.

Two shapes are exercised:
  - Worker-thread plugin/switch sites write a `json.dumps({"i18n_key", ...})`
    marker; a read boundary with `lang` renders it via render_marker/render_result
    before the response is built (api/actions.py, api/tasks.py,
    api/task_commands.py -> application/task_commands.py).
  - The four request-scoped sites (api/provider_settings.py, api/auth.py,
    application/proxies.py via api/proxies.py, infrastructure/system_runtime.py
    via api/system.py) render directly via t(key, lang) at return time.
"""
from __future__ import annotations

import asyncio
import json

from core.base_platform import Account, RegisterConfig
from platforms.kiro.plugin import KiroPlatform


def _create_account(client, platform: str, **overrides) -> int:
    payload = {"platform": platform, "email": "test@example.com", "password": "", **overrides}
    resp = client.post("/api/accounts", json=payload)
    assert resp.status_code == 200
    return resp.json()["id"]


def _set_lang(client, lang: str) -> None:
    if lang != "zh":
        resp = client.put("/api/config", json={"data": {"ui_language": lang}})
        assert resp.status_code == 200


# --- sync action (api/actions.py::execute_action) --------------------------
#
# windsurf's "switch_desktop" capability defaults to sync=True (no
# capability_overrides entry sets sync=False for it) and its
# _handle_switch_desktop fails deterministically -- no network call -- when
# the account carries no session_token/token, returning the
# `windsurf.ba57068f` marker this story minted.


def test_sync_action_marker_renders_english(client):
    _set_lang(client, "en")
    account_id = _create_account(client, "windsurf")
    resp = client.post(f"/api/actions/windsurf/{account_id}/switch_desktop", json={"params": {}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["sync"] is True
    assert body["ok"] is False
    assert body["error"] == "The account is missing a session_token"
    # Never a raw key or unparsed JSON.
    assert "i18n_key" not in body["error"]


def test_sync_action_marker_renders_chinese_default(client):
    account_id = _create_account(client, "windsurf")
    resp = client.post(f"/api/actions/windsurf/{account_id}/switch_desktop", json={"params": {}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] == "账号缺少 session_token"


# --- chatgpt switch_desktop guard-clause and fallback markers (DW-41) -------


def test_chatgpt_switch_desktop_missing_session_token_renders_english():
    from i18n import render_marker
    from platforms.chatgpt.plugin import ChatGPTPlatform

    platform = ChatGPTPlatform(RegisterConfig())
    account = Account(platform="chatgpt", email="user@example.com", password="", token="")
    result = platform.execute_action("switch_desktop", account, {})
    assert result["ok"] is False
    assert render_marker(result["error"], "en") == "Switch to Codex desktop requires session_token"
    assert "i18n_key" not in render_marker(result["error"], "en")


def test_chatgpt_switch_desktop_missing_session_token_renders_chinese_default():
    from i18n import render_marker
    from platforms.chatgpt.plugin import ChatGPTPlatform

    platform = ChatGPTPlatform(RegisterConfig())
    account = Account(platform="chatgpt", email="user@example.com", password="", token="")
    result = platform.execute_action("switch_desktop", account, {})
    assert render_marker(result["error"], "zh") == "切换到 Codex 桌面版需要 session_token"


def test_chatgpt_switch_desktop_upstream_failure_without_error_key_renders_english(monkeypatch):
    import platforms.chatgpt.switch as chatgpt_switch
    from i18n import render_marker
    from platforms.chatgpt.plugin import ChatGPTPlatform

    monkeypatch.setattr(chatgpt_switch, "close_codex_app", lambda: (True, "closed"))
    monkeypatch.setattr(chatgpt_switch, "switch_codex_account", lambda session_token="", cookies="": (False, {}))

    platform = ChatGPTPlatform(RegisterConfig())
    account = Account(
        platform="chatgpt", email="user@example.com", password="", token="", extra={"session_token": "tok"}
    )
    result = platform.execute_action("switch_desktop", account, {})
    assert result["ok"] is False
    assert render_marker(result["error"], "en") == "Switch failed"


def test_chatgpt_switch_desktop_upstream_failure_without_error_key_renders_chinese_default(monkeypatch):
    import platforms.chatgpt.switch as chatgpt_switch
    from i18n import render_marker
    from platforms.chatgpt.plugin import ChatGPTPlatform

    monkeypatch.setattr(chatgpt_switch, "close_codex_app", lambda: (True, "closed"))
    monkeypatch.setattr(chatgpt_switch, "switch_codex_account", lambda session_token="", cookies="": (False, {}))

    platform = ChatGPTPlatform(RegisterConfig())
    account = Account(
        platform="chatgpt", email="user@example.com", password="", token="", extra={"session_token": "tok"}
    )
    result = platform.execute_action("switch_desktop", account, {})
    assert render_marker(result["error"], "zh") == "切换失败"


def test_chatgpt_switch_desktop_upstream_error_key_passes_through_untouched(monkeypatch):
    """When switch_data carries its own "error" key (a marker or plain text),
    the DW-41 fallback default must never override it."""
    import platforms.chatgpt.switch as chatgpt_switch
    from i18n import render_marker
    from platforms.chatgpt.plugin import ChatGPTPlatform

    # Deliberately a different key than the DW-41 fallback (chatgpt.d08fd422),
    # so this test cannot pass by accident if the fallback ever overwrites it.
    upstream_marker = json.dumps({"i18n_key": "windsurf.ba57068f", "i18n_params": {}}, ensure_ascii=False)
    monkeypatch.setattr(chatgpt_switch, "close_codex_app", lambda: (True, "closed"))
    monkeypatch.setattr(
        chatgpt_switch,
        "switch_codex_account",
        lambda session_token="", cookies="": (False, {"error": upstream_marker}),
    )

    platform = ChatGPTPlatform(RegisterConfig())
    account = Account(
        platform="chatgpt", email="user@example.com", password="", token="", extra={"session_token": "tok"}
    )
    result = platform.execute_action("switch_desktop", account, {})
    assert render_marker(result["error"], "en") == "The account is missing a session_token"
    assert render_marker(result["error"], "en") != "Switch failed"


def test_chatgpt_switch_desktop_routes_through_execute_action_not_generic_not_implemented():
    """DW-43: ChatGPTPlatform now overrides _handle_switch_desktop, so the
    standard capability dispatch (BasePlatform._handle_capability) reaches it
    directly via execute_action, instead of falling through to the base
    class's untranslated "not implemented" string."""
    from i18n import render_marker
    from platforms.chatgpt.plugin import ChatGPTPlatform

    platform = ChatGPTPlatform(RegisterConfig())
    account = Account(platform="chatgpt", email="user@example.com", password="", token="")
    result = platform.execute_action("switch_desktop", account, {})
    assert result["ok"] is False
    rendered = render_marker(result["error"], "en")
    assert rendered == "Switch to Codex desktop requires session_token"
    assert rendered != "Capability switch_desktop not implemented for ChatGPT"
    assert result["error"] != "Capability switch_desktop not implemented for ChatGPT"


# --- compound cursor success: switch + restart compose into one coherent
#     sentence, never two concatenated still-encoded markers -----------------


def test_cursor_switch_restart_composition_renders_one_coherent_english_sentence(monkeypatch):
    import platforms.cursor.switch as cursor_switch
    from i18n import render_result
    from platforms.cursor.plugin import CursorPlatform

    switch_marker = json.dumps({"i18n_key": "cursor.e29d05fa", "i18n_params": {}}, ensure_ascii=False)
    restart_marker = json.dumps({"i18n_key": "cursor.2b2a1772", "i18n_params": {}}, ensure_ascii=False)

    monkeypatch.setattr(cursor_switch, "switch_cursor_account", lambda token: (True, switch_marker))
    monkeypatch.setattr(cursor_switch, "restart_cursor_ide", lambda: (True, restart_marker))
    monkeypatch.setattr(cursor_switch, "get_cursor_user_info", lambda token: {})
    monkeypatch.setattr(cursor_switch, "get_cursor_billing_info", lambda token: {})
    monkeypatch.setattr(cursor_switch, "has_cursor_valid_payment_method", lambda token: None)
    monkeypatch.setattr(cursor_switch, "get_cursor_usage", lambda token, sub: {})
    monkeypatch.setattr(cursor_switch, "summarize_cursor_usage", lambda usage: None)
    monkeypatch.setattr(cursor_switch, "read_current_cursor_account", lambda: {})
    monkeypatch.setattr(cursor_switch, "get_cursor_desktop_state", lambda *a, **k: {"available": False})

    platform = CursorPlatform(RegisterConfig())
    account = Account(platform="cursor", email="user@example.com", password="", token="tok")
    result = platform.execute_action("switch_account", account, {})
    assert result["ok"] is True

    rendered = render_result(result, "en")
    assert rendered["data"]["message"] == (
        "Switch succeeded; restart Cursor IDE for the new account to take effect. Cursor IDE restarted"
    )
    # Not two still-encoded markers concatenated together.
    assert "i18n_key" not in rendered["data"]["message"]
    # data.restart.message renders correctly on its own too.
    assert rendered["data"]["restart"]["message"] == "Cursor IDE restarted"


# --- async action read back via GET /api/tasks/{id} -------------------------


def _finish_task_with_marker_error(marker_key: str) -> str:
    from application.tasks import TASK_STATUS_FAILED, TaskLogger, create_platform_action_task

    task = create_platform_action_task({"platform": "blink", "account_id": 1, "action_id": "get_account_state"})
    task_id = task["id"]
    marker = json.dumps({"i18n_key": marker_key, "i18n_params": {}}, ensure_ascii=False)
    TaskLogger(task_id).finish(TASK_STATUS_FAILED, error=marker)
    return task_id


def test_async_task_error_marker_renders_english(client):
    _set_lang(client, "en")
    task_id = _finish_task_with_marker_error("blink.41497ce5")
    resp = client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] == "Could not obtain workspace_id; unable to generate the Blink payment link"
    assert "i18n_key" not in body["error"]


def test_async_task_error_marker_renders_chinese_default(client):
    task_id = _finish_task_with_marker_error("blink.41497ce5")
    resp = client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["error"] == "未获取到 workspace_id，无法生成 Blink 支付链接"


def test_async_task_result_data_message_and_error_render_english(client):
    # I/O matrix row "Async action, read after completion": result.data's
    # message/error fields must render, not just the top-level task error.
    from application.tasks import TASK_STATUS_SUCCEEDED, TaskLogger, create_platform_action_task

    task = create_platform_action_task({"platform": "blink", "account_id": 1, "action_id": "generate_checkout_link"})
    task_id = task["id"]
    logger = TaskLogger(task_id)
    logger.set_result_data(
        {
            "message": json.dumps({"i18n_key": "blink.efe9de30", "i18n_params": {}}, ensure_ascii=False),
            "nested": {"error": json.dumps({"i18n_key": "blink.8932cb51", "i18n_params": {}}, ensure_ascii=False)},
        }
    )
    logger.finish(TASK_STATUS_SUCCEEDED)

    _set_lang(client, "en")
    resp = client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["data"]["message"] == "Blink Pro payment link generated"
    assert result["data"]["nested"]["error"] == "Blink did not return a payment link"


# --- Task History list (api/tasks.py::list_tasks) ---------------------------


def test_list_tasks_marker_renders_english(client):
    _set_lang(client, "en")
    task_id = _finish_task_with_marker_error("blink.41497ce5")
    resp = client.get("/api/tasks")
    assert resp.status_code == 200
    items = {item["task_id"]: item for item in resp.json()["items"]}
    assert items[task_id]["error"] == "Could not obtain workspace_id; unable to generate the Blink payment link"


# --- poll-fallback events (api/tasks.py::list_task_events) ------------------


def test_list_task_events_marker_renders_english(client):
    from application.tasks import append_task_event, create_platform_action_task

    task = create_platform_action_task({"platform": "blink", "account_id": 1, "action_id": "get_account_state"})
    task_id = task["id"]
    marker = json.dumps({"i18n_key": "blink.8932cb51", "i18n_params": {}}, ensure_ascii=False)
    append_task_event(task_id, "task failed", event_type="state", level="error", detail={"status": "failed", "error": marker})

    _set_lang(client, "en")
    resp = client.get(f"/api/tasks/{task_id}/events")
    assert resp.status_code == 200
    events = resp.json()["items"]
    # events[0] is the "task created" event append_task_event auto-writes;
    # the marker-bearing one is the one this test appended.
    marker_event = next(e for e in events if "error" in e.get("detail", {}))
    assert marker_event["detail"]["error"] == "Blink did not return a payment link"


# --- SSE live stream (api/task_commands.py::stream_logs ->
#     application/task_commands.py::TaskCommandsService.stream_task_events) --


def test_sse_stream_marker_renders_english(client):
    from application.task_commands import TaskCommandsService
    from application.tasks import TASK_STATUS_FAILED, TaskLogger, append_task_event, create_platform_action_task

    task = create_platform_action_task({"platform": "blink", "account_id": 1, "action_id": "get_account_state"})
    task_id = task["id"]
    marker = json.dumps({"i18n_key": "blink.8932cb51", "i18n_params": {}}, ensure_ascii=False)
    append_task_event(task_id, "task failed", event_type="state", level="error", detail={"status": "failed", "error": marker})
    TaskLogger(task_id).finish(TASK_STATUS_FAILED, error=marker)

    async def _collect() -> list[dict]:
        frames = []
        service = TaskCommandsService()
        async for chunk in service.stream_task_events(task_id, since=0, lang="en"):
            if chunk.startswith("data: "):
                frames.append(json.loads(chunk[len("data: "):].strip()))
            if len(frames) >= 10:
                break
        return frames

    frames = asyncio.run(_collect())
    # The first event frame is the "task created" event append_task_event
    # auto-writes; the marker-bearing one is the one this test appended.
    event_frames = [f for f in frames if "error" in f.get("detail", {})]
    assert event_frames, frames
    assert event_frames[0]["detail"]["error"] == "Blink did not return a payment link"
    done_frames = [f for f in frames if f.get("done")]
    assert done_frames, frames
    assert done_frames[0]["line"] == "Blink did not return a payment link"


# --- Windsurf post-registration failure log line (source-language, no
#     request/lang context) ---------------------------------------------------


def test_windsurf_auto_upgrade_log_line_renders_source_language(monkeypatch):
    from application.tasks import TaskLogger, _auto_followup_windsurf_payment

    logged: list[tuple[str, str]] = []

    class _RecordingLogger(TaskLogger):
        def __init__(self):
            self.task_id = "task_test"

        def log(self, message, *, level="info", event_type="log", detail=None):
            logged.append((message, level))

        def record_error(self, error):
            logged.append((error, "recorded_error"))

    class _Platform:
        def execute_action(self, action_id, account, params):
            marker = json.dumps({"i18n_key": "windsurf.0abfa13e", "i18n_params": {}}, ensure_ascii=False)
            return {"ok": False, "error": marker}

    account = Account(platform="windsurf", email="user@example.com", password="secret", token="tok")
    _auto_followup_windsurf_payment(
        platform_name="windsurf",
        payload={"executor_type": "protocol", "extra": {}},
        platform=_Platform(),
        account=account,
        logger=_RecordingLogger(),
    )

    messages = [m for m, _ in logged]
    assert any("Windsurf 注册后自动升级失败: 账号缺少 Windsurf 密码，无法执行浏览器自动化" == m for m in messages)
    # Never leaks the raw marker JSON into the log line.
    assert not any("i18n_key" in m for m in messages)


# --- kiro default-with-upstream: an upstream (non-marker) error string
#     passes through render_result untouched --------------------------------


def test_kiro_refresh_upstream_error_passes_through_untouched(monkeypatch):
    import platforms.kiro.switch as kiro_switch

    monkeypatch.setattr(
        kiro_switch,
        "refresh_kiro_token",
        lambda *a, **k: (False, {"error": "自定义已存在的错误"}),
    )
    # KiroPlatform.execute_action imports refresh_kiro_token lazily inside the
    # method body, so patching platforms.kiro.switch is enough -- no separate
    # patch needed on the plugin module.
    platform = KiroPlatform(RegisterConfig())
    account = Account(
        platform="kiro",
        email="user@example.com",
        password="",
        token="",
        extra={"refreshToken": "rt", "clientId": "cid", "clientSecret": "secret"},
    )
    result = platform.execute_action("refresh_token", account, {})
    assert result["ok"] is False
    assert result["error"] == "自定义已存在的错误"


# --- four request-scoped sites: api/provider_settings.py, api/auth.py,
#     application/proxies.py, infrastructure/system_runtime.py -------------


def test_provider_settings_test_endpoint_renders_english(client):
    _set_lang(client, "en")
    resp = client.post(
        "/api/provider-settings/test",
        json={"provider_type": "captcha", "provider_key": "yescaptcha_api", "config": {}, "auth": {}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["message"] == "Captcha service testing is not supported online yet; please verify it in a registration task"


def test_provider_settings_test_endpoint_renders_chinese_default(client):
    resp = client.post(
        "/api/provider-settings/test",
        json={"provider_type": "captcha", "provider_key": "yescaptcha_api", "config": {}, "auth": {}},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "验证码服务暂不支持在线测试，请在注册任务中验证"


def test_auth_login_failure_renders_english(client, monkeypatch):
    # ui_language 要先在 APP_PASSWORD 生效前设置，否则 PUT /api/config 本身
    # 也会被鉴权中间件拦下 —
    # Set ui_language before APP_PASSWORD takes effect, or PUT /api/config
    # itself gets blocked by the auth middleware too.
    _set_lang(client, "en")
    monkeypatch.setenv("APP_PASSWORD", "correct-horse")
    resp = client.post("/api/auth/login", json={"password": "wrong"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"] == "Incorrect password"


def test_auth_login_failure_renders_chinese_default(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "correct-horse")
    resp = client.post("/api/auth/login", json={"password": "wrong"})
    assert resp.status_code == 200
    assert resp.json()["error"] == "密码错误"


def test_proxies_check_trigger_renders_english(client, monkeypatch):
    import application.proxies as proxies_module

    monkeypatch.setattr(proxies_module.proxy_pool, "check_all", lambda: None)
    _set_lang(client, "en")
    resp = client.post("/api/proxies/check")
    assert resp.status_code == 200
    assert resp.json()["message"] == "The check task has started"


def test_solver_restart_renders_english(client, monkeypatch):
    import infrastructure.system_runtime as system_runtime_module

    monkeypatch.setattr(system_runtime_module, "restart", lambda: None)
    _set_lang(client, "en")
    resp = client.post("/api/solver/restart")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Restarting"


def test_solver_restart_renders_chinese_default(client, monkeypatch):
    import infrastructure.system_runtime as system_runtime_module

    monkeypatch.setattr(system_runtime_module, "restart", lambda: None)
    resp = client.post("/api/solver/restart")
    assert resp.status_code == 200
    assert resp.json()["message"] == "重启中"


# --- DW-36: kiro/trae switch.py + plugin.py returned-payload migration -----
#
# switch_kiro_account/restart_kiro_ide/switch_trae_account/restart_trae_ide
# used to return raw Chinese (ok, msg) tuples; they now return
# json.dumps({"i18n_key", "i18n_params"}) markers mirroring cursor/switch.py.
# Tests assert the decoded marker's i18n_key/i18n_params, never rendered
# text, per DW-36's decision.


def test_switch_kiro_account_success_marker(tmp_path, monkeypatch):
    import platforms.kiro.switch as kiro_switch

    monkeypatch.setattr(kiro_switch, "_get_cache_dir", lambda: str(tmp_path))

    ok, marker = kiro_switch.switch_kiro_account(
        access_token="at", refresh_token="rt", client_id="cid", client_secret="secret"
    )
    assert ok is True
    assert json.loads(marker) == {"i18n_key": "kiro.f0af92d4", "i18n_params": {}}


def test_switch_kiro_account_exception_marker(tmp_path, monkeypatch):
    import platforms.kiro.switch as kiro_switch

    monkeypatch.setattr(kiro_switch, "_get_cache_dir", lambda: str(tmp_path))

    def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(kiro_switch, "_atomic_write", _boom)

    ok, marker = kiro_switch.switch_kiro_account(access_token="at", refresh_token="rt")
    assert ok is False
    assert json.loads(marker) == {"i18n_key": "kiro.fe53dc8a", "i18n_params": {"reason": "boom"}}


def test_switch_trae_account_success_marker(tmp_path, monkeypatch):
    import platforms.trae.switch as trae_switch

    storage_path = str(tmp_path / "storage.json")
    monkeypatch.setattr(trae_switch, "_get_trae_storage_path", lambda: storage_path)

    ok, marker = trae_switch.switch_trae_account("tok")
    assert ok is True
    assert json.loads(marker) == {"i18n_key": "trae.40099cb0", "i18n_params": {}}


def test_switch_trae_account_exception_marker(tmp_path, monkeypatch):
    import platforms.trae.switch as trae_switch

    storage_path = str(tmp_path / "storage.json")
    monkeypatch.setattr(trae_switch, "_get_trae_storage_path", lambda: storage_path)

    def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(trae_switch, "_atomic_write", _boom)

    ok, marker = trae_switch.switch_trae_account("tok")
    assert ok is False
    assert json.loads(marker) == {"i18n_key": "trae.fe53dc8a", "i18n_params": {"reason": "boom"}}


# --- restart_kiro_ide / restart_trae_ide: restart / closed-fallback /
#     exception paths, all forced onto the Linux OS branch for determinism --


def test_restart_kiro_ide_restarts_successfully(monkeypatch):
    import os
    import platform
    import subprocess
    import time

    import platforms.kiro.switch as kiro_switch

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: None)
    monkeypatch.setattr(os.path, "exists", lambda path: path == "/usr/bin/kiro")
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)

    ok, marker = kiro_switch.restart_kiro_ide()
    assert ok is True
    assert json.loads(marker) == {"i18n_key": "kiro.414ec63b", "i18n_params": {}}


def test_restart_kiro_ide_falls_back_to_closed_marker(monkeypatch):
    import os
    import platform
    import subprocess
    import time

    import platforms.kiro.switch as kiro_switch

    def _popen(args, *a, **k):
        raise FileNotFoundError("no kiro binary")

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(subprocess, "Popen", _popen)
    monkeypatch.setattr(os.path, "exists", lambda path: False)
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)

    ok, marker = kiro_switch.restart_kiro_ide()
    assert ok is True
    assert json.loads(marker) == {"i18n_key": "kiro.aa840b4a", "i18n_params": {}}


def test_restart_kiro_ide_exception_marker(monkeypatch):
    import platform
    import subprocess

    import platforms.kiro.switch as kiro_switch

    def _run(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(subprocess, "run", _run)

    ok, marker = kiro_switch.restart_kiro_ide()
    assert ok is False
    assert json.loads(marker) == {"i18n_key": "kiro.c744b509", "i18n_params": {"reason": "boom"}}


def test_restart_trae_ide_restarts_successfully(monkeypatch):
    import os
    import platform
    import subprocess
    import time

    import platforms.trae.switch as trae_switch

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: None)
    monkeypatch.setattr(os.path, "exists", lambda path: path == "/usr/bin/trae")
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)

    ok, marker = trae_switch.restart_trae_ide()
    assert ok is True
    assert json.loads(marker) == {"i18n_key": "trae.28619c8c", "i18n_params": {}}


def test_restart_trae_ide_falls_back_to_closed_marker(monkeypatch):
    import os
    import platform
    import subprocess
    import time

    import platforms.trae.switch as trae_switch

    def _popen(args, *a, **k):
        raise FileNotFoundError("no trae binary")

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(subprocess, "Popen", _popen)
    monkeypatch.setattr(os.path, "exists", lambda path: False)
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)

    ok, marker = trae_switch.restart_trae_ide()
    assert ok is True
    assert json.loads(marker) == {"i18n_key": "trae.05d8c318", "i18n_params": {}}


def test_restart_trae_ide_exception_marker(monkeypatch):
    import platform
    import subprocess

    import platforms.trae.switch as trae_switch

    def _run(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(subprocess, "run", _run)

    ok, marker = trae_switch.restart_trae_ide()
    assert ok is False
    assert json.loads(marker) == {"i18n_key": "trae.c744b509", "i18n_params": {"reason": "boom"}}


# --- compound kiro/trae success: switch + restart compose into one marker,
#     structure asserted (not rendered text), per DW-36's decision ----------


def test_kiro_switch_restart_composition_marker_structure(monkeypatch):
    import platforms.kiro.switch as kiro_switch
    from i18n import render_marker
    from platforms.kiro.plugin import KiroPlatform

    switch_marker = json.dumps({"i18n_key": "kiro.f0af92d4", "i18n_params": {}}, ensure_ascii=False)
    restart_marker = json.dumps({"i18n_key": "kiro.414ec63b", "i18n_params": {}}, ensure_ascii=False)

    monkeypatch.setattr(kiro_switch, "switch_kiro_account", lambda **kwargs: (True, switch_marker))
    monkeypatch.setattr(kiro_switch, "restart_kiro_ide", lambda: (True, restart_marker))
    monkeypatch.setattr(kiro_switch, "read_current_kiro_account", lambda: {})
    monkeypatch.setattr(kiro_switch, "get_kiro_portal_state", lambda *a, **k: {})
    monkeypatch.setattr(kiro_switch, "summarize_kiro_usage", lambda *a, **k: None)
    monkeypatch.setattr(kiro_switch, "get_kiro_desktop_state", lambda *a, **k: {"available": False})

    platform_ = KiroPlatform(RegisterConfig())
    account = Account(
        platform="kiro", email="user@example.com", password="", token="tok", extra={"accessToken": "tok"}
    )
    result = platform_.execute_action("switch_account", account, {})
    assert result["ok"] is True

    message = result["data"]["message"]
    decoded = json.loads(message)
    assert decoded["i18n_key"] == "kiro.9311bf9d"
    assert decoded["i18n_params"] == {"switch_msg": switch_marker, "restart_msg": restart_marker}

    # Light resolution check confirming the composed key resolves to
    # non-key, non-marker text in both languages -- the primary assertion
    # above is structural.
    rendered_en = render_marker(message, "en")
    assert rendered_en != message
    assert "i18n_key" not in rendered_en
    rendered_zh = render_marker(message, "zh")
    assert rendered_zh != message
    assert "i18n_key" not in rendered_zh


def test_kiro_switch_restart_composition_uses_switch_message_when_restart_fails(monkeypatch):
    """When restart_ok is False, data.message is the bare switch marker --
    matching cursor/plugin.py's precedent composition ternary exactly (the
    restart failure marker is not surfaced here; DW-36 replicates the
    existing shape, it does not change it)."""
    import platforms.kiro.switch as kiro_switch
    from platforms.kiro.plugin import KiroPlatform

    switch_marker = json.dumps({"i18n_key": "kiro.f0af92d4", "i18n_params": {}}, ensure_ascii=False)
    restart_failure_marker = json.dumps(
        {"i18n_key": "kiro.c744b509", "i18n_params": {"reason": "boom"}}, ensure_ascii=False
    )

    monkeypatch.setattr(kiro_switch, "switch_kiro_account", lambda **kwargs: (True, switch_marker))
    monkeypatch.setattr(kiro_switch, "restart_kiro_ide", lambda: (False, restart_failure_marker))
    monkeypatch.setattr(kiro_switch, "read_current_kiro_account", lambda: {})
    monkeypatch.setattr(kiro_switch, "get_kiro_portal_state", lambda *a, **k: {})
    monkeypatch.setattr(kiro_switch, "summarize_kiro_usage", lambda *a, **k: None)
    monkeypatch.setattr(kiro_switch, "get_kiro_desktop_state", lambda *a, **k: {"available": False})

    platform_ = KiroPlatform(RegisterConfig())
    account = Account(
        platform="kiro", email="user@example.com", password="", token="tok", extra={"accessToken": "tok"}
    )
    result = platform_.execute_action("switch_account", account, {})
    assert result["ok"] is True
    assert result["data"]["message"] == switch_marker
    # restart's own failure marker still travels separately in "restart".
    assert result["data"]["restart"] == {"ok": False, "message": restart_failure_marker}


def test_trae_switch_restart_composition_marker_structure(monkeypatch):
    import platforms.trae.switch as trae_switch
    from i18n import render_marker
    from platforms.trae.plugin import TraePlatform

    switch_marker = json.dumps({"i18n_key": "trae.40099cb0", "i18n_params": {}}, ensure_ascii=False)
    restart_marker = json.dumps({"i18n_key": "trae.28619c8c", "i18n_params": {}}, ensure_ascii=False)

    monkeypatch.setattr(trae_switch, "switch_trae_account", lambda *a, **k: (True, switch_marker))
    monkeypatch.setattr(trae_switch, "restart_trae_ide", lambda: (True, restart_marker))

    platform_ = TraePlatform(RegisterConfig())
    account = Account(platform="trae", email="user@example.com", password="", token="tok")
    result = platform_.execute_action("switch_account", account, {})
    assert result["ok"] is True

    message = result["data"]["message"]
    decoded = json.loads(message)
    assert decoded["i18n_key"] == "trae.9311bf9d"
    assert decoded["i18n_params"] == {"switch_msg": switch_marker, "restart_msg": restart_marker}

    rendered_en = render_marker(message, "en")
    assert rendered_en != message
    assert "i18n_key" not in rendered_en
    rendered_zh = render_marker(message, "zh")
    assert rendered_zh != message
    assert "i18n_key" not in rendered_zh


def test_trae_switch_restart_composition_uses_switch_message_when_restart_fails(monkeypatch):
    """Same precedent-matching behavior as kiro's equivalent test above --
    when restart_ok is False, data.message is the bare switch marker."""
    import platforms.trae.switch as trae_switch
    from platforms.trae.plugin import TraePlatform

    switch_marker = json.dumps({"i18n_key": "trae.40099cb0", "i18n_params": {}}, ensure_ascii=False)
    restart_failure_marker = json.dumps(
        {"i18n_key": "trae.c744b509", "i18n_params": {"reason": "boom"}}, ensure_ascii=False
    )

    monkeypatch.setattr(trae_switch, "switch_trae_account", lambda *a, **k: (True, switch_marker))
    monkeypatch.setattr(trae_switch, "restart_trae_ide", lambda: (False, restart_failure_marker))

    platform_ = TraePlatform(RegisterConfig())
    account = Account(platform="trae", email="user@example.com", password="", token="tok")
    result = platform_.execute_action("switch_account", account, {})
    assert result["ok"] is True
    assert result["data"]["message"] == switch_marker


# --- resolution smoke test: every DW-36 key resolves for both en and zh,
#     never falling back to the raw key -------------------------------------


def test_dw36_new_and_reused_keys_resolve_for_en_and_zh():
    from i18n import t

    # Keys with no {param} placeholder resolve with no kwargs; keys that
    # interpolate need matching params or t()'s formatter degrades to the
    # raw key (see i18n/__init__.py's _StrictFormatter), which would make
    # this smoke test indistinguishable from a genuinely missing key.
    keys_and_params = [
        # Reused, previously-orphaned kiro.* keys (now live via this bundle).
        ("kiro.f0af92d4", {}),
        ("kiro.414ec63b", {}),
        ("kiro.aa840b4a", {}),
        # Hand-added dynamic/compose keys.
        ("kiro.fe53dc8a", {"reason": "boom"}),
        ("kiro.c744b509", {"reason": "boom"}),
        ("kiro.9311bf9d", {"switch_msg": "s", "restart_msg": "r"}),
        ("trae.40099cb0", {}),
        ("trae.28619c8c", {}),
        ("trae.05d8c318", {}),
        ("trae.fe53dc8a", {"reason": "boom"}),
        ("trae.c744b509", {"reason": "boom"}),
        ("trae.9311bf9d", {"switch_msg": "s", "restart_msg": "r"}),
    ]
    for key, params in keys_and_params:
        assert t(key, "en", **params) != key, key
        assert t(key, "zh", **params) != key, key
