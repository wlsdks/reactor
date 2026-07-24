from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import uuid4

import jwt

from reactor.auth.jwt import JwtTokenService
from reactor.auth.models import UserRecord
from reactor.auth.rbac import UserRole, parse_role
from reactor.auth.service import AuthResult, UserStoreProtocol
from reactor.core.settings import Settings

IAM_ALGORITHM = "RS256"


class IamExchangeProtocol(Protocol):
    async def exchange(self, iam_token: str) -> AuthResult | None: ...


@dataclass(frozen=True)
class IamExchangeConfig:
    base_url: str
    issuer: str = "reactor-iam"
    auto_create_user: bool = True
    default_role: UserRole = UserRole.USER
    public_key_timeout_ms: int = 5000

    @classmethod
    def from_settings(cls, settings: Settings) -> IamExchangeConfig:
        return cls(
            base_url=settings.auth_iam_base_url.rstrip("/"),
            issuer=settings.auth_iam_issuer,
            auto_create_user=settings.auth_iam_auto_create_user,
            default_role=parse_role(settings.auth_iam_default_role),
            public_key_timeout_ms=settings.auth_iam_public_key_timeout_ms,
        )


class IamTokenExchangeService:
    def __init__(
        self,
        *,
        config: IamExchangeConfig,
        user_store: UserStoreProtocol,
        jwt_tokens: JwtTokenService,
    ) -> None:
        if not config.base_url.strip():
            raise ValueError("IAM base URL is required")
        self._config = config
        self._user_store = user_store
        self._jwt_tokens = jwt_tokens
        self._public_key: str | None = None
        self._public_key_lock = asyncio.Lock()

    async def exchange(self, iam_token: str) -> AuthResult | None:
        public_key = await self.public_key()
        if public_key is None:
            return None
        payload = verify_iam_token(iam_token, public_key=public_key, issuer=self._config.issuer)
        if payload is None:
            return None

        iam_user_id = str(payload.get("sub") or "").strip()
        if not iam_user_id:
            return None
        email = str(payload.get("email") or "").strip() or f"{iam_user_id}@iam.local"
        roles = [
            role for role in cast(list[object], payload.get("roles") or []) if isinstance(role, str)
        ]

        user = await self._user_store.find_by_email(email)
        if user is None:
            if not self._config.auto_create_user:
                return None
            user = await self._user_store.save(
                UserRecord(
                    id=uuid4().hex,
                    email=email,
                    name=email.split("@", 1)[0] if "@" in email else iam_user_id,
                    password_hash="iam-external",  # noqa: S106
                    role=role_from_iam_roles(roles, default_role=self._config.default_role),
                )
            )
        return AuthResult(token=self._jwt_tokens.create_token(user), user=user)

    async def public_key(self) -> str | None:
        if self._public_key is not None:
            return self._public_key
        async with self._public_key_lock:
            if self._public_key is not None:
                return self._public_key
            fetched = await asyncio.to_thread(
                fetch_public_key,
                self._config.base_url,
                self._config.public_key_timeout_ms,
            )
            self._public_key = fetched
            return fetched

    def invalidate_public_key(self) -> None:
        self._public_key = None


def verify_iam_token(iam_token: str, *, public_key: str, issuer: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(
            iam_token,
            public_key,
            algorithms=[IAM_ALGORITHM],
            issuer=issuer,
            options={"require": ["sub", "iss", "exp"]},
        )
    except jwt.PyJWTError:
        return None


def role_from_iam_roles(iam_roles: list[str], *, default_role: UserRole) -> UserRole:
    normalized = {role.upper() for role in iam_roles}
    if "ROLE_ADMIN" in normalized:
        return UserRole.ADMIN
    if "ROLE_MANAGER" in normalized:
        return UserRole.ADMIN_MANAGER
    if "ROLE_DEVELOPER" in normalized:
        return UserRole.ADMIN_DEVELOPER
    return default_role


def fetch_public_key(base_url: str, timeout_ms: int) -> str | None:
    public_key_url = f"{base_url.rstrip('/')}/api/auth/public-key"
    if urlsplit(public_key_url).scheme not in {"http", "https"}:
        return None
    try:
        with urlopen(  # noqa: S310
            public_key_url,
            timeout=timeout_ms / 1000,
        ) as response:
            if response.status != 200:
                return None
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, URLError, json.JSONDecodeError):
        return None
    public_key = payload.get("publicKey")
    return public_key if isinstance(public_key, str) and public_key.strip() else None
