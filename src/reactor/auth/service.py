from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from reactor.auth.jwt import JwtTokenService
from reactor.auth.models import UserRecord
from reactor.auth.passwords import hash_password, verify_password
from reactor.auth.rbac import UserRole


class UserStoreProtocol(Protocol):
    async def find_by_email(self, email: str) -> UserRecord | None: ...

    async def find_by_id(self, user_id: str) -> UserRecord | None: ...

    async def save(self, user: UserRecord) -> UserRecord: ...

    async def update(self, user: UserRecord) -> UserRecord: ...

    async def exists_by_email(self, email: str) -> bool: ...

    async def count(self) -> int: ...


@dataclass(frozen=True)
class AuthResult:
    token: str
    user: UserRecord


class AuthService:
    def __init__(
        self,
        *,
        user_store: UserStoreProtocol,
        jwt_tokens: JwtTokenService,
        self_registration_enabled: bool,
    ) -> None:
        self._user_store = user_store
        self._jwt_tokens = jwt_tokens
        self._self_registration_enabled = self_registration_enabled

    async def register(self, *, email: str, password: str, name: str) -> AuthResult:
        if not self._self_registration_enabled:
            raise PermissionError("Self-registration is disabled. Contact an administrator.")
        if await self._user_store.exists_by_email(email):
            raise FileExistsError("Email already registered")
        user = UserRecord(
            id=uuid4().hex,
            email=email,
            name=name,
            password_hash=hash_password(password),
            role=UserRole.ADMIN if await self._user_store.count() == 0 else UserRole.USER,
        )
        saved = await self._user_store.save(user)
        return AuthResult(token=self._jwt_tokens.create_token(saved), user=saved)

    async def login(self, *, email: str, password: str) -> AuthResult | None:
        user = await self._user_store.find_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            return None
        return AuthResult(token=self._jwt_tokens.create_token(user), user=user)

    async def get_user(self, user_id: str) -> UserRecord | None:
        return await self._user_store.find_by_id(user_id)

    async def change_password(
        self,
        *,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> bool:
        user = await self._user_store.find_by_id(user_id)
        if user is None or not verify_password(current_password, user.password_hash):
            return False
        updated = UserRecord(
            id=user.id,
            email=user.email,
            name=user.name,
            password_hash=hash_password(new_password),
            role=user.role,
            tenant_id=user.tenant_id,
            groups=user.groups,
            created_at=user.created_at,
        )
        await self._user_store.update(updated)
        return True

    async def demo_login(self) -> AuthResult:
        email = "demo@reactor.local"
        existing = await self._user_store.find_by_email(email)
        if existing is None:
            user = UserRecord(
                id=uuid4().hex,
                email=email,
                name="Demo Admin",
                password_hash=hash_password("demo-password-disabled"),  # noqa: S106
                role=UserRole.ADMIN,
            )
            saved = await self._user_store.save(user)
        elif existing.role != UserRole.ADMIN:
            saved = await self._user_store.update(
                UserRecord(
                    id=existing.id,
                    email=existing.email,
                    name=existing.name,
                    password_hash=existing.password_hash,
                    role=UserRole.ADMIN,
                    tenant_id=existing.tenant_id,
                    groups=existing.groups,
                    created_at=existing.created_at,
                )
            )
        else:
            saved = existing
        return AuthResult(token=self._jwt_tokens.create_token(saved), user=saved)
