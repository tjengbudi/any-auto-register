"""Config endpoint tests for ui_language persistence and validation."""
from __future__ import annotations


def test_ui_language_round_trip(client):
    resp = client.put("/api/config", json={"data": {"ui_language": "en"}})
    assert resp.status_code == 200
    assert resp.json()["ignored"] == []
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["ui_language"] == "en"


def test_ui_language_defaults_to_zh_when_never_written(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["ui_language"] == "zh"


def test_ui_language_rejects_wrong_case(client):
    resp = client.put("/api/config", json={"data": {"ui_language": "EN"}})
    assert resp.status_code == 400
    resp = client.get("/api/config")
    assert resp.json()["ui_language"] == "zh"


def test_ui_language_rejects_malformed_locale(client):
    resp = client.put("/api/config", json={"data": {"ui_language": "en-US"}})
    assert resp.status_code == 400
    resp = client.get("/api/config")
    assert resp.json()["ui_language"] == "zh"


def test_ui_language_rejects_empty_string(client):
    resp = client.put("/api/config", json={"data": {"ui_language": ""}})
    assert resp.status_code == 400
    resp = client.get("/api/config")
    assert resp.json()["ui_language"] == "zh"


def test_ui_language_rejected_value_leaves_prior_value_unchanged(client):
    resp = client.put("/api/config", json={"data": {"ui_language": "en"}})
    assert resp.status_code == 200
    resp = client.put("/api/config", json={"data": {"ui_language": "EN"}})
    assert resp.status_code == 400
    resp = client.get("/api/config")
    assert resp.json()["ui_language"] == "en"


def test_partial_update_does_not_clobber_ui_language(client):
    resp = client.put("/api/config", json={"data": {"ui_language": "en"}})
    assert resp.status_code == 200
    resp = client.put("/api/config", json={"data": {"default_executor": "x"}})
    assert resp.status_code == 200
    resp = client.get("/api/config")
    assert resp.json()["ui_language"] == "en"


def test_ui_language_accepts_unexposed_vi_value(client):
    resp = client.put("/api/config", json={"data": {"ui_language": "vi"}})
    assert resp.status_code == 200
    resp = client.get("/api/config")
    assert resp.json()["ui_language"] == "vi"


def test_ui_language_falls_back_to_zh_for_stale_invalid_stored_value(client):
    from core.config_store import config_store

    config_store.set("ui_language", "fr")
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["ui_language"] == "zh"


def test_update_config_reports_unknown_key_as_ignored(client):
    resp = client.put(
        "/api/config",
        json={"data": {"default_executor": "x", "ui_lanugage": "en"}},
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == ["default_executor"]
    assert resp.json()["ignored"] == ["ui_lanugage"]
    resp = client.get("/api/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["default_executor"] == "x"
    assert "ui_lanugage" not in body


def test_config_options_english(client):
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    resp = client.get("/api/config/options")
    assert resp.status_code == 200
    data = resp.json()

    cfworker = next(item for item in data["mailbox_providers"] if item["provider_key"] == "cfworker_admin_api")
    assert cfworker["label"] == "CF Worker (custom domain)"

    executor_labels = {item["value"]: item["label"] for item in data["executor_options"]}
    assert executor_labels.get("protocol") == "Protocol mode"
    assert executor_labels.get("headless") == "Headless browser (auto)"
    assert executor_labels.get("headed") == "Visible browser (auto)"

    identity_labels = {item["value"]: item["label"] for item in data["identity_mode_options"]}
    assert identity_labels.get("mailbox") == "System mailbox"
    assert identity_labels.get("oauth_browser") == "Third-party account"


def test_config_options_chinese_default(client):
    resp = client.get("/api/config/options")
    assert resp.status_code == 200
    data = resp.json()

    cfworker = next(item for item in data["mailbox_providers"] if item["provider_key"] == "cfworker_admin_api")
    assert cfworker["label"] == "CF Worker（自建域名）"

    executor_labels = {item["value"]: item["label"] for item in data["executor_options"]}
    assert executor_labels.get("protocol") == "协议模式"
    assert executor_labels.get("headless") == "后台浏览器自动"
    assert executor_labels.get("headed") == "可视浏览器自动"

    identity_labels = {item["value"]: item["label"] for item in data["identity_mode_options"]}
    assert identity_labels.get("mailbox") == "系统邮箱"
    assert identity_labels.get("oauth_browser") == "第三方账号"


def test_config_options_reads_ui_language_exactly_once(client, monkeypatch):
    from core.config_store import config_store

    calls = []
    original_get = config_store.get

    def counting_get(key, default=""):
        if key == "ui_language":
            calls.append(key)
        return original_get(key, default)

    monkeypatch.setattr(config_store, "get", counting_get)

    resp = client.get("/api/config/options")
    assert resp.status_code == 200
    assert len(calls) == 1
