"""HTTP-level i18n tests for PortalService's HTTPException details.

Exercises `customer_portal_api.app.services.portal.PortalService`'s
`HTTPException` detail rendering through `self.lang`, wired end-to-end via
`get_portal_locale` -> router `Depends()` -> `PortalService(session, lang)`.
Uses `starlette.testclient.TestClient` against the real
`customer_portal_api.main.app`, matching the style of
`tests/test_customer_portal_locale.py` and
`tests/test_customer_portal_startup_guard.py`.
"""
from __future__ import annotations

import pytest
from sqlmodel import create_engine
from starlette.testclient import TestClient

import i18n


@pytest.fixture(autouse=True)
def _isolated_catalog_cache(monkeypatch):
    """Every test gets its own i18n catalog cache slot so tests never leak
    state (mirrors tests/test_customer_portal_startup_guard.py)."""
    monkeypatch.setattr(i18n, "_catalogs", None)
    yield


@pytest.fixture()
def portal_client(monkeypatch, tmp_path):
    """A TestClient wired to a throwaway, isolated sqlite DB, so the seeded
    admin user and fixtures never collide with other test runs or files.

    `customer_portal_api.app.db`, `.deps`, and `.bootstrap` each bind their
    own `engine` name at import time (`from customer_portal_api.app.db
    import engine`), so all three must be monkeypatched -- reassigning
    `db.engine` alone would not be visible to `deps.get_db_session` or
    `bootstrap.initialize_runtime`, which each hold their own reference.
    """
    import customer_portal_api.app.bootstrap as bootstrap_module
    import customer_portal_api.app.db as db_module
    import customer_portal_api.app.deps as deps_module
    import customer_portal_api.main as main_module

    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'portal_i18n_test.db'}",
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(deps_module, "engine", test_engine)
    monkeypatch.setattr(bootstrap_module, "engine", test_engine)

    with TestClient(main_module.app) as client:
        yield client


def _admin_headers(client: TestClient, *, accept_language: str | None = None) -> dict[str, str]:
    """Log in as the seeded admin (bootstrap._seed_admin) and return auth
    headers, optionally carrying Accept-Language."""
    resp = client.post("/api/auth/login", json={"account": "admin", "password": "admin123456"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    if accept_language is not None:
        headers["Accept-Language"] = accept_language
    return headers


# (a) One representative endpoint per shared-key group named in the spec's
# Tasks item: identical status code, differing EN/ZH detail text.
@pytest.mark.parametrize(
    ("method", "path", "zh_text", "en_text", "body"),
    [
        ("get", "/api/tasks/does-not-exist", "任务不存在", "Task not found", None),
        ("get", "/api/accounts/999999", "账号不存在", "Account not found", None),
        ("get", "/api/app/orders/does-not-exist", "订单不存在", "Order not found", None),
        ("delete", "/api/proxies/999999", "代理不存在", "Proxy not found", None),
        ("patch", "/api/admin/users/999999", "用户不存在", "User not found", {}),
        ("get", "/api/admin/users/999999/platform-access", "用户不存在", "User not found", None),
    ],
    ids=[
        "task-not-found",
        "account-not-found",
        "order-not-found",
        "proxy-not-found",
        "user-not-found-update",
        "user-not-found-platform-access",
    ],
)
def test_shared_key_endpoints_render_per_language(portal_client, method, path, zh_text, en_text, body):
    en_headers = _admin_headers(portal_client, accept_language="en")
    zh_headers = _admin_headers(portal_client, accept_language="zh")

    kwargs = {"json": body} if body is not None else {}
    en_resp = getattr(portal_client, method)(path, headers=en_headers, **kwargs)
    zh_resp = getattr(portal_client, method)(path, headers=zh_headers, **kwargs)

    assert en_resp.status_code == zh_resp.status_code == 404
    assert en_resp.json()["detail"] == en_text
    assert zh_resp.json()["detail"] == zh_text


# (a2) Validation-error (422/400/501) call sites the shared-key table above
# doesn't reach: duplicate/missing-field checks and the two "not implemented"
# stubs, each hit with a single request that needs no prior setup.
@pytest.mark.parametrize(
    ("method", "path", "body", "expected_status", "zh_text", "en_text"),
    [
        (
            "post",
            "/api/admin/users",
            {"username": "admin", "password": "whatever123"},
            400,
            "用户名已存在",
            "Username already exists",
        ),
        (
            "post",
            "/api/admin/users",
            {"username": "", "password": ""},
            422,
            "username 和 password 必填",
            "username and password are required",
        ),
        (
            "post",
            "/api/accounts",
            {"platform": "", "email": "", "password": ""},
            422,
            "platform、email、password 必填",
            "platform, email, and password are required",
        ),
        (
            "post",
            "/api/tasks/register",
            {"platform": "chatgpt"},
            501,
            "独立版暂未实现注册任务",
            "Registration tasks are not implemented in the standalone edition",
        ),
    ],
    ids=[
        "duplicate-username",
        "missing-username-password",
        "missing-account-fields",
        "admin-register-task-not-implemented",
    ],
)
def test_validation_and_not_implemented_endpoints_render_per_language(
    portal_client, method, path, body, expected_status, zh_text, en_text
):
    en_headers = _admin_headers(portal_client, accept_language="en")
    zh_headers = _admin_headers(portal_client, accept_language="zh")

    en_resp = getattr(portal_client, method)(path, headers=en_headers, json=body)
    zh_resp = getattr(portal_client, method)(path, headers=zh_headers, json=body)

    assert en_resp.status_code == zh_resp.status_code == expected_status
    assert en_resp.json()["detail"] == en_text
    assert zh_resp.json()["detail"] == zh_text


# (a3) Duplicate-field checks that require a pre-existing record: create one
# user/proxy per language, then trigger the same-language conflict. Each
# language iteration uses its own conflicting value -- the "en" pass's
# holder user must not collide with the "zh" pass's, since both run against
# the same portal_client/database within one test.
@pytest.mark.parametrize(
    ("field", "value_template", "zh_text", "en_text"),
    [
        ("email", "dup-{suffix}@example.com", "邮箱已被占用", "Email already in use"),
        ("mobile", "000000000{suffix_digit}", "手机号已被占用", "Mobile number already in use"),
    ],
    ids=["duplicate-email", "duplicate-mobile"],
)
def test_duplicate_user_field_renders_per_language(portal_client, field, value_template, zh_text, en_text):
    for lang, expected_text, suffix, suffix_digit in (("en", en_text, "en", "1"), ("zh", zh_text, "zh", "2")):
        conflicting_value = value_template.format(suffix=suffix, suffix_digit=suffix_digit)
        headers = _admin_headers(portal_client, accept_language=lang)
        first_body = {"username": f"{field}-holder-{suffix}", "password": "whatever123", field: conflicting_value}
        create_resp = portal_client.post("/api/admin/users", headers=headers, json=first_body)
        assert create_resp.status_code == 200, create_resp.text

        second_body = {"username": f"{field}-dup-{suffix}", "password": "whatever123", field: conflicting_value}
        dup_resp = portal_client.post("/api/admin/users", headers=headers, json=second_body)
        assert dup_resp.status_code == 400
        assert dup_resp.json()["detail"] == expected_text


def test_duplicate_proxy_renders_per_language(portal_client):
    for lang, expected_text in (("en", "Proxy already exists"), ("zh", "代理已存在")):
        headers = _admin_headers(portal_client, accept_language=lang)
        url = f"http://dup-proxy-{lang}.example.com"
        first_resp = portal_client.post("/api/proxies", headers=headers, json={"url": url})
        assert first_resp.status_code == 200, first_resp.text

        dup_resp = portal_client.post("/api/proxies", headers=headers, json={"url": url})
        assert dup_resp.status_code == 400
        assert dup_resp.json()["detail"] == expected_text


# (b) Accept-Language absent falls back to the Chinese detail.
def test_absent_accept_language_falls_back_to_zh(portal_client):
    headers = _admin_headers(portal_client)  # no Accept-Language sent
    resp = portal_client.get("/api/tasks/does-not-exist", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "任务不存在"


# (c) A minted key with no `en` entry (yet) degrades to the zh value under
# lang="en" -- never a 500, status code unchanged.
def test_untranslated_key_falls_back_to_zh_without_500(portal_client):
    headers = _admin_headers(portal_client, accept_language="en")

    catalogs = i18n.load()
    removed = catalogs["en"]["customerPortalApi"].pop("d1817495", None)
    assert removed is not None  # sanity: the key had an English value before removal

    try:
        resp = portal_client.get("/api/tasks/does-not-exist", headers=headers)
    finally:
        catalogs["en"]["customerPortalApi"]["d1817495"] = removed

    assert resp.status_code == 404
    assert resp.json()["detail"] == "任务不存在"
