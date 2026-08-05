from __future__ import annotations

from datetime import timezone

from fastapi import HTTPException, status
from sqlmodel import Session, or_, select

from customer_portal_api.app.config import settings
from customer_portal_api.app.db import utcnow
from customer_portal_api.app.models import (
    PortalPermission,
    PortalPlatform,
    PortalRole,
    PortalRolePermission,
    PortalUser,
    RefreshToken,
    UserPlatformAccess,
)
from customer_portal_api.app.security import (
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password,
)
from i18n import t


class AuthService:
    def __init__(self, session: Session, lang: str = "zh"):
        self.session = session
        self.lang = lang

    def login(self, account: str, password: str) -> dict:
        user = self.session.exec(
            select(PortalUser).where(
                or_(
                    PortalUser.username == account,
                    PortalUser.email == account,
                    PortalUser.mobile == account,
                )
            )
        ).first()
        if not user or user.status != "active" or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=t("customerPortalApi.80eb55c9", self.lang))
        user.last_login_at = utcnow()
        user.updated_at = utcnow()
        self.session.add(user)
        self.session.commit()
        return self._issue_tokens(user)

    def refresh(self, refresh_token: str) -> dict:
        token_row = self.session.exec(
            select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(refresh_token))
        ).first()
        expires_at = token_row.expires_at if token_row else None
        if expires_at is not None and expires_at.tzinfo is None:
            # sqlite drops tzinfo on the round trip through storage; `utcnow()`
            # is always timezone-aware, so a naive value read back needs it
            # restored before comparison, or `<=` below raises TypeError.
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if not token_row or token_row.revoked_at is not None or expires_at <= utcnow():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=t("customerPortalApi.e0760a78", self.lang))
        user = self.session.get(PortalUser, token_row.user_id)
        if not user or user.status != "active":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=t("customerPortalApi.25fa2ac3", self.lang))
        token_row.revoked_at = utcnow()
        self.session.add(token_row)
        self.session.commit()
        return self._issue_tokens(user)

    def logout(self, refresh_token: str) -> dict:
        token_row = self.session.exec(
            select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(refresh_token))
        ).first()
        if token_row and token_row.revoked_at is None:
            token_row.revoked_at = utcnow()
            self.session.add(token_row)
            self.session.commit()
        return {"ok": True}

    def get_me(self, user: PortalUser) -> dict:
        platform_map = {
            item.platform_code: item.display_name
            for item in self.session.exec(select(PortalPlatform).where(PortalPlatform.status == "active")).all()
        }
        platform_rows = []
        if user.role_code != "admin":
            platform_rows = self.session.exec(
                select(UserPlatformAccess).where(
                    UserPlatformAccess.user_id == int(user.id or 0),
                    UserPlatformAccess.is_active == True,
                )
            ).all()
        return {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name or user.username,
            "email": user.email,
            "mobile": user.mobile,
            "avatar_url": user.avatar_url,
            "role_code": user.role_code,
            "status": user.status,
            "permissions": self._permissions_for_role(user.role_code),
            "platforms": [
                {
                    "platform_code": item.platform_code,
                    "platform_name": platform_map.get(item.platform_code, item.platform_code),
                }
                for item in platform_rows
            ],
        }

    def _issue_tokens(self, user: PortalUser) -> dict:
        access_token = create_access_token(
            str(user.id),
            {
                "role_code": user.role_code,
                "username": user.username,
            },
        )
        refresh_token = create_refresh_token()
        self.session.add(
            RefreshToken(
                user_id=int(user.id or 0),
                token_hash=hash_refresh_token(refresh_token),
                expires_at=refresh_token_expiry(),
                created_at=utcnow(),
            )
        )
        self.session.commit()
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": settings.access_token_ttl_seconds,
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name or user.username,
                "role_code": user.role_code,
            },
        }

    def _permissions_for_role(self, role_code: str) -> list[str]:
        role = self.session.exec(select(PortalRole).where(PortalRole.role_code == role_code)).first()
        if not role:
            return []
        permission_rows = self.session.exec(
            select(PortalPermission.permission_code)
            .join(PortalRolePermission, PortalRolePermission.permission_id == PortalPermission.id)
            .where(PortalRolePermission.role_id == int(role.id or 0))
        ).all()
        return [str(item) for item in permission_rows]
