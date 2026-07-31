"""GET /api/actions/{platform} i18n tests.

Covers both minted-label sources -- a `get_platform_actions()` override
(`chatgpt`) and a `capability_overrides` platform (`windsurf`) -- plus the
passthrough case for a platform with no overrides of its own
(`openblocklabs`), and the single-config-store-read regression mirroring
tests/test_api_platforms.py::test_platforms_reads_ui_language_exactly_once.
"""
from __future__ import annotations


def test_actions_chatgpt_english(client):
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    resp = client.get("/api/actions/chatgpt")
    assert resp.status_code == 200
    data = resp.json()
    labels = {a["id"]: a["label"] for a in data["actions"]}
    assert labels["switch_account"] == "Switch to Codex desktop"
    assert labels["get_account_state"] == "Check account status/subscription"
    assert labels["refresh_token"] == "Refresh token"
    assert labels["payment_link"] == "Generate payment link"

    payment_link = next(a for a in data["actions"] if a["id"] == "payment_link")
    param_labels = {p["key"]: p["label"] for p in payment_link["params"]}
    assert param_labels["country"] == "Region"
    assert param_labels["plan"] == "Plan"


def test_actions_chatgpt_chinese_default(client):
    resp = client.get("/api/actions/chatgpt")
    assert resp.status_code == 200
    data = resp.json()
    labels = {a["id"]: a["label"] for a in data["actions"]}
    assert labels["switch_account"] == "切换到 Codex 桌面端"
    assert labels["get_account_state"] == "查询账号状态/订阅"
    assert labels["refresh_token"] == "刷新 Token"
    assert labels["payment_link"] == "生成支付链接"

    payment_link = next(a for a in data["actions"] if a["id"] == "payment_link")
    param_labels = {p["key"]: p["label"] for p in payment_link["params"]}
    assert param_labels["country"] == "地区"
    assert param_labels["plan"] == "套餐"


def test_actions_windsurf_english(client):
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    resp = client.get("/api/actions/windsurf")
    assert resp.status_code == 200
    data = resp.json()
    labels = {a["id"]: a["label"] for a in data["actions"]}
    assert labels["generate_link"] == "Generate Pro Trial link (auto captcha)"
    assert labels["generate_link_browser"] == "Generate Pro Trial link (browser)"
    assert labels["switch_desktop"] == "Switch desktop app (protocol only)"

    generate_link = next(a for a in data["actions"] if a["id"] == "generate_link")
    assert generate_link["params"][0]["label"] == "Turnstile Token (optional, auto captcha)"

    browser = next(a for a in data["actions"] if a["id"] == "generate_link_browser")
    browser_param_labels = {p["key"]: p["label"] for p in browser["params"]}
    assert browser_param_labels["turnstile_token"] == "Turnstile Token (optional, auto captcha)"
    assert browser_param_labels["timeout"] == "Wait seconds (default 180)"
    assert browser_param_labels["headless"] == "Headless mode"

    # query_state/check_trial are not overridden by windsurf -- their labels
    # come straight from core/capability_registry.py, minted by story 3.3,
    # so they render in English here too.
    assert labels["query_state"] == "Check account status/quota"
    assert labels["check_trial"] == "Check trial eligibility"


def test_actions_windsurf_chinese_default(client):
    resp = client.get("/api/actions/windsurf")
    assert resp.status_code == 200
    data = resp.json()
    labels = {a["id"]: a["label"] for a in data["actions"]}
    assert labels["generate_link"] == "生成 Pro Trial 链接（自动打码）"
    assert labels["generate_link_browser"] == "生成 Pro Trial 链接（浏览器）"
    assert labels["switch_desktop"] == "切换桌面应用（纯协议）"
    assert labels["query_state"] == "查询账号状态/额度"
    assert labels["check_trial"] == "检查试用资格"


def test_actions_openblocklabs_passthrough_english(client):
    """openblocklabs defines neither get_platform_actions() nor
    capability_overrides, and (like tavily/grok) declares no
    `capabilities` of its own either -- so its action list is empty
    regardless of locale. The point of this test is that the read
    boundary still answers 200 under ui_language=en without erroring,
    not that it has content to translate yet (story 3.3's territory).
    """
    client.put("/api/config", json={"data": {"ui_language": "en"}})
    resp = client.get("/api/actions/openblocklabs")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"actions": []}


def test_actions_reads_ui_language_exactly_once(client, monkeypatch):
    from core.config_store import config_store

    calls = []
    original_get = config_store.get

    def counting_get(key, default=""):
        if key == "ui_language":
            calls.append(key)
        return original_get(key, default)

    monkeypatch.setattr(config_store, "get", counting_get)

    resp = client.get("/api/actions/chatgpt")
    assert resp.status_code == 200
    assert len(calls) == 1
