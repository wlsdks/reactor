from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import jwt

from reactor.auth.models import UserRecord
from reactor.auth.rbac import UserRole, parse_groups, parse_role

JWT_ALGORITHM = "HS256"


@dataclass(frozen=True)
class JwtClaims:
    user_id: str
    token_id: str
    email: str
    role: UserRole
    tenant_id: str
    issued_at: datetime
    expires_at: datetime
    groups: tuple[str, ...] = ()


class JwtTokenService:
    def __init__(
        self,
        *,
        secret: str,
        expiration_ms: int,
        default_tenant_id: str,
    ) -> None:
        secret_bytes = secret.encode("utf-8")
        if len(secret_bytes) < 32:
            raise ValueError("JWT secret must be at least 32 bytes for HS256")
        if expiration_ms <= 0:
            raise ValueError("expiration_ms must be positive")
        if not default_tenant_id.strip():
            raise ValueError("default_tenant_id is required")
        self._secret = secret
        self._expiration = timedelta(milliseconds=expiration_ms)
        self._default_tenant_id = default_tenant_id

    def create_token(self, user: UserRecord) -> str:
        user.validate()
        now = datetime.now(UTC)
        expires_at = now + self._expiration
        payload: dict[str, object] = {
            "jti": uuid4().hex,
            "sub": user.id,
            "email": user.email,
            "role": user.role.value,
            "tenantId": user.tenant_id or self._default_tenant_id,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        if user.groups:
            payload["groups"] = list(user.groups)
        return jwt.encode(payload, self._secret, algorithm=JWT_ALGORITHM)

    def validate_token(self, token: str) -> str | None:
        claims = self.parse_claims(token)
        return claims.user_id if claims is not None else None

    def parse_claims(self, token: str) -> JwtClaims | None:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[JWT_ALGORITHM])
        except jwt.PyJWTError:
            return None
        return claims_from_payload(payload)

    def extract_token_id(self, token: str) -> str | None:
        claims = self.parse_claims(token)
        return claims.token_id if claims is not None else None

    def extract_expiration(self, token: str) -> datetime | None:
        claims = self.parse_claims(token)
        return claims.expires_at if claims is not None else None


def claims_from_payload(payload: dict[str, Any]) -> JwtClaims | None:
    subject = str(payload.get("sub") or "").strip()
    token_id = str(payload.get("jti") or "").strip()
    email = str(payload.get("email") or "").strip()
    tenant_id = str(payload.get("tenantId") or "").strip()
    if not subject or not token_id or not email or not tenant_id:
        return None
    expires_at = timestamp_to_datetime(payload.get("exp"))
    issued_at = timestamp_to_datetime(payload.get("iat"))
    if expires_at is None or issued_at is None:
        return None
    return JwtClaims(
        user_id=subject,
        token_id=token_id,
        email=email,
        role=parse_role(cast(str | None, payload.get("role"))),
        tenant_id=tenant_id,
        issued_at=issued_at,
        expires_at=expires_at,
        groups=groups_from_payload(payload.get("groups")),
    )


def groups_from_payload(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return parse_groups(value)
    if not isinstance(value, list):
        return ()
    groups: list[str] = []
    seen: set[str] = set()
    for raw_group in cast(list[object], value):
        group = str(raw_group).strip()
        if not group or group in seen:
            continue
        groups.append(group)
        seen.add(group)
    return tuple(groups)


def timestamp_to_datetime(value: object) -> datetime | None:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC)
    return None
