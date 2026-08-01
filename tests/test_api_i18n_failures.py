"""Locale-rendering tests for the api/ failure-message read boundary (story 3.5).

One representative endpoint per migrated file (9 total), a same-key
cross-file assertion for tasks.py/task_commands.py's shared "任务不存在"
key, and a plain unit test of api.deps.render_detail covering both the
keyed and unkeyed branches.
"""
from __future__ import annotations

from api.deps import render_detail


# ---------------------------------------------------------------------------
# api/sms.py -- direct raise, HeroSMS API Key not configured
# ---------------------------------------------------------------------------


def test_sms_herosms_balance_missing_key_english(client):
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    resp = client.post("/api/sms/herosms/balance", json={})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "HeroSMS API Key is not configured"


def test_sms_herosms_balance_missing_key_chinese_default(client):
    resp = client.post("/api/sms/herosms/balance", json={})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "HeroSMS API Key 未配置"


# ---------------------------------------------------------------------------
# api/proxies.py -- direct raise, duplicate proxy
# ---------------------------------------------------------------------------


def test_proxies_duplicate_english(client):
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    client.post("/api/proxies", json={"url": "http://127.0.0.1:7890"})
    resp = client.post("/api/proxies", json={"url": "http://127.0.0.1:7890"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Proxy already exists"


def test_proxies_duplicate_chinese_default(client):
    client.post("/api/proxies", json={"url": "http://127.0.0.1:7890"})
    resp = client.post("/api/proxies", json={"url": "http://127.0.0.1:7890"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "代理已存在"


# ---------------------------------------------------------------------------
# api/accounts.py -- direct raise, account not found
# ---------------------------------------------------------------------------


def test_accounts_get_not_found_english(client):
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    resp = client.get("/api/accounts/99999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Account not found"


def test_accounts_get_not_found_chinese_default(client):
    resp = client.get("/api/accounts/99999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "账号不存在"


# ---------------------------------------------------------------------------
# api/task_commands.py -- direct raise, task not found (cancel)
# ---------------------------------------------------------------------------


def test_task_commands_cancel_not_found_english(client):
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    resp = client.post("/api/tasks/bogus-task-id/cancel")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Task not found"


def test_task_commands_cancel_not_found_chinese_default(client):
    resp = client.post("/api/tasks/bogus-task-id/cancel")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "任务不存在"


# ---------------------------------------------------------------------------
# api/tasks.py -- direct raise, task not found (get) -- shares its key with
# api/task_commands.py above; asserted together below.
# ---------------------------------------------------------------------------


def test_tasks_get_not_found_english(client):
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    resp = client.get("/api/tasks/bogus-task-id")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Task not found"


def test_tasks_get_not_found_chinese_default(client):
    resp = client.get("/api/tasks/bogus-task-id")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "任务不存在"


def test_shared_task_not_found_key_renders_identically_across_files(client):
    """tasks.py::get_task and task_commands.py::cancel_task raise from the
    same minted key -- both must render byte-identical text in both
    locales, proving the mint run's cross-file dedup actually collapsed
    them to one shared key rather than two lookalike ones."""
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    en_tasks = client.get("/api/tasks/bogus-task-id").json()["detail"]
    en_commands = client.post("/api/tasks/bogus-task-id/cancel").json()["detail"]
    assert en_tasks == en_commands == "Task not found"

    client.put("/api/config", json={"data": {"ui_language": "zh"}})
    zh_tasks = client.get("/api/tasks/bogus-task-id").json()["detail"]
    zh_commands = client.post("/api/tasks/bogus-task-id/cancel").json()["detail"]
    assert zh_tasks == zh_commands == "任务不存在"


# ---------------------------------------------------------------------------
# api/account_checks.py -- direct raise, account not found -- shares its key
# with api/accounts.py above.
# ---------------------------------------------------------------------------


def test_account_checks_not_found_english(client):
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    resp = client.post("/api/accounts/99999/check")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Account not found"


def test_account_checks_not_found_chinese_default(client):
    resp = client.post("/api/accounts/99999/check")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "账号不存在"


# ---------------------------------------------------------------------------
# api/provider_definitions.py -- direct raise, definition not found
# ---------------------------------------------------------------------------


def test_provider_definitions_delete_not_found_english(client):
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    resp = client.delete("/api/provider-definitions/99999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Provider definition not found"


def test_provider_definitions_delete_not_found_chinese_default(client):
    resp = client.delete("/api/provider-definitions/99999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "provider definition 不存在"


# ---------------------------------------------------------------------------
# api/provider_settings.py -- direct raise, setting not found
# ---------------------------------------------------------------------------


def test_provider_settings_delete_not_found_english(client):
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    resp = client.delete("/api/provider-settings/99999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Provider setting not found"


def test_provider_settings_delete_not_found_chinese_default(client):
    resp = client.delete("/api/provider-settings/99999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "provider setting 不存在"


# ---------------------------------------------------------------------------
# api/actions.py -- direct raise, task creation failed
# ---------------------------------------------------------------------------


def test_actions_execute_action_failure_english(client, monkeypatch):
    import api.actions as actions_module

    monkeypatch.setattr(actions_module.service, "execute_action", lambda command: None)
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    resp = client.post("/api/actions/chatgpt/1/payment_link", json={"params": {}})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Failed to create task"


def test_actions_execute_action_failure_chinese_default(client, monkeypatch):
    import api.actions as actions_module

    monkeypatch.setattr(actions_module.service, "execute_action", lambda command: None)
    resp = client.post("/api/actions/chatgpt/1/payment_link", json={"params": {}})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "任务创建失败"


# ---------------------------------------------------------------------------
# api/deps.py::render_detail -- unit tests, no HTTP involved
# ---------------------------------------------------------------------------


class _KeyedError(Exception):
    """A stand-in for a future providers/infrastructure exception carrying
    i18n_key/i18n_params (AD-17); no base class is required to opt in."""


def test_render_detail_renders_the_carried_key_when_present():
    exc = _KeyedError("this text must never reach the response")
    exc.i18n_key = "api.d1817495"
    exc.i18n_params = {}
    assert render_detail(exc, "en") == "Task not found"
    assert render_detail(exc, "zh") == "任务不存在"


def test_render_detail_threads_i18n_params_through_t():
    exc = _KeyedError("discarded")
    exc.i18n_key = "core.5912705f"  # "{reset_label} 重置" / "Resets {reset_label}"
    exc.i18n_params = {"reset_label": "Monday"}
    assert render_detail(exc, "en") == "Resets Monday"
    assert render_detail(exc, "zh") == "Monday 重置"


def test_render_detail_treats_missing_i18n_params_as_empty():
    exc = _KeyedError("discarded")
    exc.i18n_key = "api.d1817495"
    # i18n_params intentionally left unset.
    assert render_detail(exc, "en") == "Task not found"


def test_render_detail_falls_back_to_str_when_no_i18n_key():
    """The default shape of every providers/infrastructure exception today,
    until story 4.13 adds i18n_key there -- render_detail must not error or
    change behavior for these."""
    exc = ValueError("upstream boom")
    assert render_detail(exc, "en") == "upstream boom"
    assert render_detail(exc, "zh") == "upstream boom"


def test_render_detail_falls_back_to_str_when_i18n_key_is_not_a_string():
    exc = _KeyedError("discarded")
    exc.i18n_key = 12345
    assert render_detail(exc, "en") == "discarded"


def test_render_detail_falls_back_to_str_when_i18n_params_is_not_a_mapping():
    exc = _KeyedError("discarded")
    exc.i18n_key = "api.d1817495"
    exc.i18n_params = ["not", "a", "dict"]
    assert render_detail(exc, "en") == "discarded"


def test_render_detail_falls_back_to_str_when_i18n_params_shadows_a_t_parameter():
    """A param named "lang" or "key" collides with t()'s own positional
    parameters at the `**params` call boundary -- this raises before t()'s
    own never-raises guarantee can apply, so render_detail must catch it."""
    exc = _KeyedError("discarded")
    exc.i18n_key = "api.d1817495"
    exc.i18n_params = {"lang": "fr"}
    assert render_detail(exc, "en") == "discarded"
