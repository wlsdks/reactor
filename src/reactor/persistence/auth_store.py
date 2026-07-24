from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.auth.models import (
    TokenRevocationRecord,
    UserIdentityRecord,
    UserRecord,
    normalize_groups,
)
from reactor.auth.rbac import UserRole
from reactor.persistence.models import AuthTokenRevocation, AuthUser, UserIdentity


class SqlAlchemyUserStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find_by_email(self, email: str) -> UserRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(build_user_find_by_email(email))
        return user_record(row) if row is not None else None

    async def find_by_id(self, user_id: str) -> UserRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(build_user_find_by_id(user_id))
        return user_record(row) if row is not None else None

    async def save(self, user: UserRecord) -> UserRecord:
        user.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(build_user_insert(user))
                if row is None:
                    raise RuntimeError("user insert did not return a row")
        return user_record(row)

    async def update(self, user: UserRecord) -> UserRecord:
        user.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(build_user_update(user))
                if row is None:
                    raise RuntimeError("user update did not return a row")
        return user_record(row)

    async def exists_by_email(self, email: str) -> bool:
        async with self._session_factory() as session:
            exists = await session.scalar(
                select(AuthUser.id).where(AuthUser.email == email).limit(1)
            )
        return exists is not None

    async def count(self) -> int:
        async with self._session_factory() as session:
            count = await session.scalar(select(func.count()).select_from(AuthUser))
        return int(count or 0)


class SqlAlchemyUserIdentityStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def upsert(
        self,
        *,
        tenant_id: str,
        provider: str,
        external_subject: str,
        user_id: str,
        metadata: dict[str, Any] | None = None,
        identity_id: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> UserIdentityRecord:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    build_user_identity_upsert(
                        tenant_id=tenant_id,
                        provider=provider,
                        external_subject=external_subject,
                        user_id=user_id,
                        metadata=metadata or {},
                        identity_id=identity_id,
                        created_at=created_at,
                        updated_at=updated_at,
                    )
                )
                if row is None:
                    raise RuntimeError("user identity upsert did not return a row")
        return user_identity_record(row)

    async def find_by_external_subject(
        self,
        *,
        tenant_id: str,
        provider: str,
        external_subject: str,
    ) -> UserIdentityRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                build_user_identity_find_by_external_subject(
                    tenant_id=tenant_id,
                    provider=provider,
                    external_subject=external_subject,
                )
            )
        return user_identity_record(row) if row is not None else None

    async def list_for_user(self, *, tenant_id: str, user_id: str) -> list[UserIdentityRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                build_user_identity_list_for_user(tenant_id=tenant_id, user_id=user_id)
            )
        return [user_identity_record(row) for row in rows]

    async def list_all(self, *, tenant_id: str) -> list[UserIdentityRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_user_identity_list_all(tenant_id=tenant_id))
        return [user_identity_record(row) for row in rows]

    async def delete_by_external_subject(
        self,
        *,
        tenant_id: str,
        provider: str,
        external_subject: str,
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                deleted_id = await session.scalar(
                    build_user_identity_delete_by_external_subject(
                        tenant_id=tenant_id,
                        provider=provider,
                        external_subject=external_subject,
                    )
                )
        return deleted_id is not None


class SqlAlchemyTokenRevocationStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def revoke(self, token_id: str, expires_at: datetime) -> None:
        if expires_at <= datetime.now(UTC):
            return
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_token_revoke_upsert(token_id, expires_at))

    async def save(self, revocation: TokenRevocationRecord) -> TokenRevocationRecord:
        revocation.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_token_revocation_insert(revocation))
        return revocation

    async def is_revoked(self, token_id: str) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                expires_at = await session.scalar(build_token_revocation_find(token_id))
                if expires_at is None:
                    return False
                if expires_at <= datetime.now(UTC):
                    await session.execute(build_token_revocation_delete(token_id))
                    return False
        return True


def build_user_insert(user: UserRecord) -> Any:
    user.validate()
    return (
        insert(AuthUser)
        .values(
            id=user.id,
            email=user.email,
            name=user.name,
            password_hash=user.password_hash,
            role=user.role.value,
            tenant_id=user.tenant_id,
            groups=list(user.groups),
            created_at=user.created_at,
        )
        .returning(AuthUser)
    )


def build_user_update(user: UserRecord) -> Any:
    user.validate()
    return (
        update(AuthUser)
        .where(AuthUser.id == user.id)
        .values(
            name=user.name,
            password_hash=user.password_hash,
            role=user.role.value,
            tenant_id=user.tenant_id,
            groups=list(user.groups),
            updated_at=func.now(),
        )
        .returning(AuthUser)
    )


def build_user_find_by_email(email: str) -> Any:
    validate_lookup_value("email", email)
    return select(AuthUser).where(AuthUser.email == email)


def build_user_find_by_id(user_id: str) -> Any:
    validate_lookup_value("user_id", user_id)
    return select(AuthUser).where(AuthUser.id == user_id)


def build_user_identity_upsert(
    *,
    tenant_id: str,
    provider: str,
    external_subject: str,
    user_id: str,
    metadata: dict[str, Any] | None = None,
    identity_id: str | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> Any:
    validate_lookup_value("tenant_id", tenant_id)
    validate_lookup_value("provider", provider)
    validate_lookup_value("external_subject", external_subject)
    validate_lookup_value("user_id", user_id)
    values: dict[Any, Any] = {
        UserIdentity.id: identity_id or f"user_identity_{uuid4().hex}",
        UserIdentity.tenant_id: tenant_id,
        UserIdentity.provider: provider,
        UserIdentity.external_subject: external_subject,
        UserIdentity.user_id: user_id,
        UserIdentity.identity_metadata: metadata or {},
    }
    if created_at is not None:
        values[UserIdentity.created_at] = created_at
    if updated_at is not None:
        values[UserIdentity.updated_at] = updated_at

    return (
        insert(UserIdentity)
        .values(values)
        .on_conflict_do_update(
            constraint="uq_user_identities_external_subject",
            set_={
                UserIdentity.user_id: user_id,
                UserIdentity.identity_metadata: metadata or {},
                UserIdentity.updated_at: updated_at or func.now(),
            },
        )
        .returning(UserIdentity)
    )


def build_user_identity_find_by_external_subject(
    *,
    tenant_id: str,
    provider: str,
    external_subject: str,
) -> Any:
    validate_lookup_value("tenant_id", tenant_id)
    validate_lookup_value("provider", provider)
    validate_lookup_value("external_subject", external_subject)
    return select(UserIdentity).where(
        UserIdentity.tenant_id == tenant_id,
        UserIdentity.provider == provider,
        UserIdentity.external_subject == external_subject,
    )


def build_user_identity_list_for_user(*, tenant_id: str, user_id: str) -> Any:
    validate_lookup_value("tenant_id", tenant_id)
    validate_lookup_value("user_id", user_id)
    return (
        select(UserIdentity)
        .where(UserIdentity.tenant_id == tenant_id, UserIdentity.user_id == user_id)
        .order_by(UserIdentity.provider.asc(), UserIdentity.external_subject.asc())
    )


def build_user_identity_list_all(*, tenant_id: str) -> Any:
    validate_lookup_value("tenant_id", tenant_id)
    return (
        select(UserIdentity)
        .where(UserIdentity.tenant_id == tenant_id)
        .order_by(UserIdentity.updated_at.desc(), UserIdentity.provider.asc())
    )


def build_user_identity_delete_by_external_subject(
    *,
    tenant_id: str,
    provider: str,
    external_subject: str,
) -> Any:
    validate_lookup_value("tenant_id", tenant_id)
    validate_lookup_value("provider", provider)
    validate_lookup_value("external_subject", external_subject)
    return (
        delete(UserIdentity)
        .where(
            UserIdentity.tenant_id == tenant_id,
            UserIdentity.provider == provider,
            UserIdentity.external_subject == external_subject,
        )
        .returning(UserIdentity.id)
    )


def build_token_revoke_upsert(token_id: str, expires_at: datetime) -> Any:
    validate_lookup_value("token_id", token_id)
    return (
        insert(AuthTokenRevocation)
        .values(token_id=token_id, expires_at=expires_at, revoked_at=datetime.now(UTC))
        .on_conflict_do_update(
            index_elements=[AuthTokenRevocation.token_id],
            set_={"expires_at": expires_at, "revoked_at": datetime.now(UTC)},
        )
    )


def build_token_revocation_insert(revocation: TokenRevocationRecord) -> Any:
    revocation.validate()
    return (
        insert(AuthTokenRevocation)
        .values(
            token_id=revocation.token_id,
            expires_at=revocation.expires_at,
            revoked_at=revocation.revoked_at,
        )
        .on_conflict_do_update(
            index_elements=[AuthTokenRevocation.token_id],
            set_={
                "expires_at": revocation.expires_at,
                "revoked_at": revocation.revoked_at,
            },
        )
    )


def build_token_revocation_find(token_id: str) -> Any:
    validate_lookup_value("token_id", token_id)
    return select(AuthTokenRevocation.expires_at).where(AuthTokenRevocation.token_id == token_id)


def build_token_revocation_delete(token_id: str) -> Any:
    validate_lookup_value("token_id", token_id)
    return delete(AuthTokenRevocation).where(AuthTokenRevocation.token_id == token_id)


def user_record(row: AuthUser) -> UserRecord:
    return UserRecord(
        id=row.id,
        email=row.email,
        name=row.name,
        password_hash=row.password_hash,
        role=UserRole(row.role),
        tenant_id=row.tenant_id,
        groups=normalize_groups(row.groups),
        created_at=row.created_at,
    )


def token_revocation_record(row: AuthTokenRevocation) -> TokenRevocationRecord:
    return TokenRevocationRecord(
        token_id=row.token_id,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
    )


def user_identity_record(row: UserIdentity) -> UserIdentityRecord:
    return UserIdentityRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        provider=row.provider,
        external_subject=row.external_subject,
        metadata=dict(row.identity_metadata),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def validate_lookup_value(field_name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} is required")
