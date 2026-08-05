from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from customer_portal_api.app.db import engine
from customer_portal_api.app.models import PortalUser
from customer_portal_api.app.security import decode_access_token
from i18n import LOCALES


bearer_scheme = HTTPBearer(auto_error=False)


def get_db_session():
    with Session(engine) as session:
        yield session


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_db_session),
) -> PortalUser:
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 access token")
    payload = decode_access_token(credentials.credentials)
    user = session.get(PortalUser, int(payload.get("sub", 0) or 0))
    if not user or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被禁用")
    return user


def require_admin(user: PortalUser = Depends(get_current_user)) -> PortalUser:
    if user.role_code != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def parse_accept_language(header: str | None) -> str:
    """解析 Accept-Language 头，解析失败一律回退到 zh，从不抛出 —
    Parse an Accept-Language header; any parse failure falls back to `zh`,
    never raises.

    与 `api/deps.py`'s `get_ui_language()`（FR22 已存储的 `ui_language` 校验）
    是两条独立的路径，只共享 `i18n.LOCALES` 这一个常量 —— `en-US` 这类带地区
    标签的值在这里是合法输入，在那边则会被拒绝 —
    A separate path from `api/deps.py`'s `get_ui_language()` (FR22's stored
    `ui_language` validation); the two share only the `i18n.LOCALES` constant.
    A region-tagged value like `en-US` is valid input here, but FR22 rejects
    it as a stored value.
    """
    if not header:
        return "zh"

    candidates: list[tuple[float, int, str]] = []
    for index, raw in enumerate(header.split(",")):
        parts = [p.strip() for p in raw.split(";")]
        tag = parts[0]
        if not tag:
            continue
        quality = 1.0
        for param in parts[1:]:
            key, _, value = param.partition("=")
            if key.strip().lower() != "q":
                continue
            try:
                parsed = float(value.strip())
            except ValueError:
                break
            # `parsed == parsed` rejects NaN; RFC 7231 quality values are 0-1 —
            # anything else is treated as if no q= param were given (weight 1.0).
            if parsed == parsed and 0.0 <= parsed <= 1.0:
                quality = parsed
            break
        candidates.append((-quality, index, tag))

    for _, _, tag in sorted(candidates, key=lambda c: (c[0], c[1])):
        if tag == "*":
            return "zh"
        primary = tag.replace("_", "-").split("-")[0].lower()
        if primary in LOCALES:
            return primary

    return "zh"


def get_portal_locale(request: Request) -> str:
    """从当前请求解析界面语言；每个请求解析一次，供未来 `t()` 调用点复用 —
    Resolve the current request's UI language once per request, for future
    `t()` call sites to reuse (AD-4).
    """
    return parse_accept_language(request.headers.get("accept-language"))
