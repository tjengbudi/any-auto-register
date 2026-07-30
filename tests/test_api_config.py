"""Config endpoint tests for ui_language persistence and validation."""
from __future__ import annotations


def test_ui_language_round_trip(client):
    resp = client.put("/api/config", json={"data": {"ui_language": "en"}})
    assert resp.status_code == 200
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
