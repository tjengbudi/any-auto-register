"""HTTP-level i18n tests for the 9 `deps.py`/`security.py`/`services/auth.py`
raise sites story 5.3 migrated.

Uses `starlette.testclient.TestClient` against the real
`customer_portal_api.main.app`, matching the style and fixtures of
`tests/test_customer_portal_service_i18n.py`.

Covered raise sites (file:line dispositions are recorded in the spec's
Verification section):
    - deps.py `get_current_user`: missing token, user not found/disabled
    - deps.py `require_admin`: admin required
    - security.py `decode_access_token`: malformed/invalid-signature/expired
    - services/auth.py `AuthService.login`: bad credentials
    - services/auth.py `AuthService.refresh`: invalid/expired refresh token,
      user not found/disabled
"""
from __future__ import annotations

import pytest
from sqlmodel import Session as SQLSession, create_engine, select
from starlette.testclient import TestClient

import i18n
from customer_portal_api.app.models import PortalUser


@pytest.fixture(autouse=True)
def _isolated_catalog_cache(monkeypatch):
    """Every test gets its own i18n catalog cache slot so tests never leak
    state (mirrors tests/test_customer_portal_startup_guard.py)."""
    monkeypatch.setattr(i18n, "_catalogs", None)
    yield


@pytest.fixture()
def portal_client(monkeypatch, tmp_path):
    """A TestClient wired to a throwaway, isolated sqlite DB -- see
    tests/test_customer_portal_service_i18n.py's identical fixture for why
    db/deps/bootstrap's `engine` names must each be monkeypatched."""
    import customer_portal_api.app.bootstrap as bootstrap_module
    import customer_portal_api.app.db as db_module
    import customer_portal_api.app.deps as deps_module
    import customer_portal_api.main as main_module

    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'portal_auth_i18n_test.db'}",
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(deps_module, "engine", test_engine)
    monkeypatch.setattr(bootstrap_module, "engine", test_engine)

    with TestClient(main_module.app) as client:
        yield client


def _login(client: TestClient, account: str, password: str, *, accept_language: str | None = None) -> dict:
    headers = {"Accept-Language": accept_language} if accept_language is not None else {}
    resp = client.post("/api/auth/login", json={"account": account, "password": password}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _admin_headers(client: TestClient, *, accept_language: str | None = None) -> dict[str, str]:
    body = _login(client, "admin", "admin123456")
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    if accept_language is not None:
        headers["Accept-Language"] = accept_language
    return headers


def _set_user_status(status_value: str, *, username: str = "admin") -> None:
    """Flip a user's status directly against the currently-patched engine."""
    import customer_portal_api.app.db as db_module

    with SQLSession(db_module.engine) as session:
        user = session.exec(select(PortalUser).where(PortalUser.username == username)).first()
        assert user is not None
        user.status = status_value
        session.add(user)
        session.commit()


# (a) deps.py's `get_current_user`: missing token.
@pytest.mark.parametrize(
    ("lang", "expected_text"),
    [("en", "Missing access token"), ("zh", "缺少 access token")],
)
def test_missing_token_renders_per_language(portal_client, lang, expected_text):
    resp = portal_client.get("/api/auth/me", headers={"Accept-Language": lang})
    assert resp.status_code == 401
    assert resp.json()["detail"] == expected_text


# (b) security.py's `decode_access_token`: malformed token (no dots).
@pytest.mark.parametrize(
    ("lang", "expected_text"),
    [("en", "Invalid access token"), ("zh", "无效的 access token")],
)
def test_malformed_token_renders_per_language(portal_client, lang, expected_text):
    headers = {"Authorization": "Bearer not-a-jwt", "Accept-Language": lang}
    resp = portal_client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 401
    assert resp.json()["detail"] == expected_text


# (c) security.py's `decode_access_token`: tampered/invalid signature.
@pytest.mark.parametrize(
    ("lang", "expected_text"),
    [("en", "Invalid access token signature"), ("zh", "access token 签名无效")],
)
def test_invalid_signature_renders_per_language(portal_client, lang, expected_text):
    valid_token = _login(portal_client, "admin", "admin123456")["access_token"]
    header, payload, _signature = valid_token.split(".", 2)
    tampered = f"{header}.{payload}.not-the-real-signature"

    headers = {"Authorization": f"Bearer {tampered}", "Accept-Language": lang}
    resp = portal_client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 401
    assert resp.json()["detail"] == expected_text


# (d) security.py's `decode_access_token`: expired token.
@pytest.mark.parametrize(
    ("lang", "expected_text"),
    [("en", "Access token has expired"), ("zh", "access token 已过期")],
)
def test_expired_token_renders_per_language(portal_client, monkeypatch, lang, expected_text):
    from customer_portal_api.app.config import settings

    monkeypatch.setattr(settings, "access_token_ttl_seconds", -1)
    expired_token = _login(portal_client, "admin", "admin123456")["access_token"]

    headers = {"Authorization": f"Bearer {expired_token}", "Accept-Language": lang}
    resp = portal_client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 401
    assert resp.json()["detail"] == expected_text


# (e) deps.py's `get_current_user`: user not found or disabled.
@pytest.mark.parametrize(
    ("lang", "expected_text"),
    [("en", "User not found or disabled"), ("zh", "用户不存在或已被禁用")],
)
def test_disabled_user_rejected_by_get_current_user(portal_client, lang, expected_text):
    token = _login(portal_client, "admin", "admin123456")["access_token"]
    _set_user_status("disabled")

    headers = {"Authorization": f"Bearer {token}", "Accept-Language": lang}
    resp = portal_client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 401
    assert resp.json()["detail"] == expected_text


# (f) deps.py's `require_admin`: admin permission required.
@pytest.mark.parametrize(
    ("lang", "expected_text"),
    [("en", "Admin permission required"), ("zh", "需要管理员权限")],
)
def test_require_admin_rejects_non_admin_per_language(portal_client, lang, expected_text):
    admin_headers = _admin_headers(portal_client)
    create_resp = portal_client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={"username": f"plain-user-{lang}", "password": "whatever123", "role_code": "user"},
    )
    assert create_resp.status_code == 200, create_resp.text

    user_body = _login(portal_client, f"plain-user-{lang}", "whatever123")
    headers = {"Authorization": f"Bearer {user_body['access_token']}", "Accept-Language": lang}
    resp = portal_client.get("/api/admin/users", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == expected_text


# (g) services/auth.py's `AuthService.login`: bad credentials.
@pytest.mark.parametrize(
    ("lang", "expected_text"),
    [("en", "Incorrect account or password"), ("zh", "账号或密码错误")],
)
def test_login_bad_credentials_renders_per_language(portal_client, lang, expected_text):
    resp = portal_client.post(
        "/api/auth/login",
        json={"account": "admin", "password": "definitely-wrong"},
        headers={"Accept-Language": lang},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == expected_text


# (h) services/auth.py's `AuthService.refresh`: invalid/expired refresh token.
@pytest.mark.parametrize(
    ("lang", "expected_text"),
    [("en", "Refresh token is invalid or has expired"), ("zh", "refresh token 无效或已过期")],
)
def test_refresh_invalid_token_renders_per_language(portal_client, lang, expected_text):
    resp = portal_client.post(
        "/api/auth/refresh",
        json={"refresh_token": "not-a-real-refresh-token"},
        headers={"Accept-Language": lang},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == expected_text


# (i) services/auth.py's `AuthService.refresh`: user not found or disabled --
# shares the 25fa2ac3 key with (e) but through a different raise site.
@pytest.mark.parametrize(
    ("lang", "expected_text"),
    [("en", "User not found or disabled"), ("zh", "用户不存在或已被禁用")],
)
def test_refresh_disabled_user_renders_per_language(portal_client, lang, expected_text):
    body = _login(portal_client, "admin", "admin123456")
    _set_user_status("disabled")

    resp = portal_client.post(
        "/api/auth/refresh",
        json={"refresh_token": body["refresh_token"]},
        headers={"Accept-Language": lang},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == expected_text
