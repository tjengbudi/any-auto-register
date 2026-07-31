"""Platform listing endpoint tests."""
from __future__ import annotations


def test_list_platforms(client):
    resp = client.get("/api/platforms")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    names = [p["name"] for p in data]
    # At least the core platforms should be loaded
    assert "chatgpt" in names
    assert "cursor" in names


def test_platform_has_required_fields(client):
    resp = client.get("/api/platforms")
    data = resp.json()
    for platform in data:
        assert "name" in platform
        assert "display_name" in platform
        assert "version" in platform
        assert "supported_executors" in platform
        assert isinstance(platform["supported_executors"], list)


def test_platform_choice_options_english(client):
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    resp = client.get("/api/platforms")
    assert resp.status_code == 200
    data = resp.json()
    protocol_platform = next(p for p in data if "protocol" in p["supported_executors"])
    labels = {o["value"]: o["label"] for o in protocol_platform["supported_executor_options"]}
    assert labels.get("protocol") == "Protocol mode"


def test_platform_choice_options_chinese_default(client):
    resp = client.get("/api/platforms")
    assert resp.status_code == 200
    data = resp.json()
    protocol_platform = next(p for p in data if "protocol" in p["supported_executors"])
    labels = {o["value"]: o["label"] for o in protocol_platform["supported_executor_options"]}
    assert labels.get("protocol") == "协议模式"


def test_platforms_reads_ui_language_exactly_once(client, monkeypatch):
    from core.config_store import config_store

    calls = []
    original_get = config_store.get

    def counting_get(key, default=""):
        if key == "ui_language":
            calls.append(key)
        return original_get(key, default)

    monkeypatch.setattr(config_store, "get", counting_get)

    resp = client.get("/api/platforms")
    assert resp.status_code == 200
    assert len(calls) == 1
