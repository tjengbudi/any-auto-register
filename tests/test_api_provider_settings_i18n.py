"""Locale-rendering tests for the provider-settings read boundary (story 3.1)."""
from __future__ import annotations


def _create_setting(client, provider_key="cfworker_admin_api"):
    resp = client.post(
        "/api/provider-settings",
        json={
            "provider_type": "mailbox",
            "provider_key": provider_key,
            "display_name": "My Mailbox",
            "auth_mode": "token",
            "enabled": True,
            "config": {},
            "auth": {},
        },
    )
    assert resp.status_code == 200
    return resp.json()["item"]


def test_provider_settings_english(client):
    _create_setting(client)
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    resp = client.get("/api/provider-settings", params={"provider_type": "mailbox"})
    assert resp.status_code == 200
    data = resp.json()
    setting = next(item for item in data if item["provider_key"] == "cfworker_admin_api")
    assert setting["catalog_label"] == "CF Worker (custom domain)"
    assert setting["description"] == (
        "Custom-domain mailbox based on Cloudflare Worker; requires self-deploying the Worker backend"
    )
    assert setting["auth_modes"] == [{"value": "token", "label": "Token auth"}]
    field = next(f for f in setting["fields"] if f["key"] == "cfworker_api_url")
    assert field["label"] == "API URL"


def test_provider_settings_chinese_default(client):
    _create_setting(client)
    resp = client.get("/api/provider-settings", params={"provider_type": "mailbox"})
    assert resp.status_code == 200
    data = resp.json()
    setting = next(item for item in data if item["provider_key"] == "cfworker_admin_api")
    assert setting["catalog_label"] == "CF Worker（自建域名）"
    assert setting["description"] == "基于 Cloudflare Worker 的自定义域名邮箱，需自行部署 Worker 后端"
    assert setting["auth_modes"] == [{"value": "token", "label": "Token 认证"}]


def test_provider_settings_reads_ui_language_exactly_once(client, monkeypatch):
    from core.config_store import config_store

    _create_setting(client)

    calls = []
    original_get = config_store.get

    def counting_get(key, default=""):
        if key == "ui_language":
            calls.append(key)
        return original_get(key, default)

    monkeypatch.setattr(config_store, "get", counting_get)

    resp = client.get("/api/provider-settings", params={"provider_type": "mailbox"})
    assert resp.status_code == 200
    assert len(calls) == 1
