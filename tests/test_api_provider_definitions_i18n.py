"""Locale-rendering tests for the provider-definitions read boundary (story 3.1)."""
from __future__ import annotations


def test_provider_definitions_english(client):
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    resp = client.get("/api/provider-definitions", params={"provider_type": "mailbox"})
    assert resp.status_code == 200
    data = resp.json()
    cfworker = next(item for item in data if item["provider_key"] == "cfworker_admin_api")
    assert cfworker["label"] == "CF Worker (custom domain)"
    assert cfworker["description"] == (
        "Custom-domain mailbox based on Cloudflare Worker; requires self-deploying the Worker backend"
    )
    assert cfworker["auth_modes"] == [{"value": "token", "label": "Token auth"}]
    field = next(f for f in cfworker["fields"] if f["key"] == "cfworker_api_url")
    assert field["label"] == "API URL"


def test_provider_definitions_chinese_default(client):
    resp = client.get("/api/provider-definitions", params={"provider_type": "mailbox"})
    assert resp.status_code == 200
    data = resp.json()
    cfworker = next(item for item in data if item["provider_key"] == "cfworker_admin_api")
    assert cfworker["label"] == "CF Worker（自建域名）"
    assert cfworker["description"] == "基于 Cloudflare Worker 的自定义域名邮箱，需自行部署 Worker 后端"
    assert cfworker["auth_modes"] == [{"value": "token", "label": "Token 认证"}]


def test_provider_definitions_chinese_explicit(client):
    client.put("/api/config", json={"data": {"ui_language": "zh"}})
    resp = client.get("/api/provider-definitions", params={"provider_type": "mailbox"})
    assert resp.status_code == 200
    data = resp.json()
    cfworker = next(item for item in data if item["provider_key"] == "cfworker_admin_api")
    assert cfworker["label"] == "CF Worker（自建域名）"


def test_provider_driver_templates_english(client):
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    resp = client.get("/api/provider-definitions/drivers", params={"provider_type": "captcha"})
    assert resp.status_code == 200
    data = resp.json()
    yescaptcha = next(item for item in data if item["driver_type"] == "yescaptcha_api")
    assert yescaptcha["label"] == "YesCaptcha"
    assert yescaptcha["description"] == (
        "YesCaptcha cloud captcha-solving service; supports Turnstile and other types"
    )


def test_provider_driver_templates_chinese(client):
    resp = client.get("/api/provider-definitions/drivers", params={"provider_type": "captcha"})
    assert resp.status_code == 200
    data = resp.json()
    yescaptcha = next(item for item in data if item["driver_type"] == "yescaptcha_api")
    assert yescaptcha["description"] == "YesCaptcha 云端验证码识别服务，支持 Turnstile 等类型"


def test_custom_definition_label_passes_through_unmodified_in_english(client):
    # A user-authored label was never minted into the catalog, so t() must
    # return it unchanged even when the request asks for English.
    custom_label = "我的自定义中文标签"
    resp = client.post(
        "/api/provider-definitions",
        json={
            "provider_type": "mailbox",
            "provider_key": "my_custom_provider",
            "label": custom_label,
            "description": "一个自定义描述",
            "driver_type": "generic_http_mailbox",
            "enabled": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["item"]["label"] == custom_label

    client.put("/api/config", json={"data": {"ui_language": "en"}})
    resp = client.get("/api/provider-definitions", params={"provider_type": "mailbox"})
    assert resp.status_code == 200
    data = resp.json()
    custom = next(item for item in data if item["provider_key"] == "my_custom_provider")
    assert custom["label"] == custom_label
    assert custom["description"] == "一个自定义描述"


def test_provider_definitions_reads_ui_language_exactly_once(client, monkeypatch):
    from core.config_store import config_store

    calls = []
    original_get = config_store.get

    def counting_get(key, default=""):
        if key == "ui_language":
            calls.append(key)
        return original_get(key, default)

    monkeypatch.setattr(config_store, "get", counting_get)

    resp = client.get("/api/provider-definitions", params={"provider_type": "mailbox"})
    assert resp.status_code == 200
    assert len(calls) == 1
