from __future__ import annotations

import os
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from docker.errors import DockerException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from reactor.api.app import create_app
from reactor.auth.models import UserRecord
from reactor.auth.rbac import UserRole
from reactor.core.settings import Settings, get_settings
from reactor.persistence.auth_store import (
    SqlAlchemyTokenRevocationStore,
    SqlAlchemyUserIdentityStore,
    SqlAlchemyUserStore,
)
from reactor.persistence.models import AuthTokenRevocation, AuthUser, UserIdentity

pytestmark = pytest.mark.skipif(
    os.environ.get("REACTOR_TEST_POSTGRES") != "1",
    reason="set REACTOR_TEST_POSTGRES=1 to run Docker-backed auth API tests",
)

SECRET = "x" * 32


async def test_auth_register_login_me_change_password_logout_against_postgres() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for auth API test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()
        app.state.reactor = AuthApiContainer(session_factory)
        transport = ASGITransport(app=app)

        try:
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                registered = await client.post(
                    "/api/auth/register",
                    json={
                        "email": "user@example.com",
                        "password": "password-1",
                        "name": "Generic User",
                    },
                )
                duplicate = await client.post(
                    "/v1/auth/register",
                    json={
                        "email": "user@example.com",
                        "password": "password-1",
                        "name": "Generic User",
                    },
                )
                logged_in = await client.post(
                    "/v1/auth/login",
                    json={"email": "user@example.com", "password": "password-1"},
                )
                token = logged_in.json()["token"]
                me = await client.get(
                    "/api/auth/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
                bad_change = await client.post(
                    "/api/auth/change-password",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"currentPassword": "wrong-password", "newPassword": "password-2"},
                )
                good_change = await client.post(
                    "/v1/auth/change-password",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"currentPassword": "password-1", "newPassword": "password-2"},
                )
                old_login = await client.post(
                    "/api/auth/login",
                    json={"email": "user@example.com", "password": "password-1"},
                )
                new_login = await client.post(
                    "/api/auth/login",
                    json={"email": "user@example.com", "password": "password-2"},
                )
                logout = await client.post(
                    "/v1/auth/logout",
                    headers={"Authorization": f"Bearer {token}"},
                )
                revoked_me = await client.get(
                    "/api/auth/me",
                    headers={"Authorization": f"Bearer {token}"},
                )

            async with session_factory() as session:
                user_count = await session.scalar(select(func.count(AuthUser.id)))
                revocation_count = await session.scalar(
                    select(func.count(AuthTokenRevocation.token_id))
                )
                user_row = await session.scalar(
                    select(AuthUser).where(AuthUser.email == "user@example.com")
                )

            assert registered.status_code == 201
            assert registered.json()["user"]["role"] == "ADMIN"
            assert registered.json()["user"]["tenantId"] == "default"
            assert duplicate.status_code == 409
            assert duplicate.json()["detail"] == "Email already registered"
            assert logged_in.status_code == 200
            assert me.status_code == 200
            assert me.json()["email"] == "user@example.com"
            assert bad_change.status_code == 400
            assert good_change.status_code == 200
            assert old_login.status_code == 401
            assert new_login.status_code == 200
            assert logout.status_code == 200
            assert logout.json() == {"message": "Logged out"}
            assert revoked_me.status_code == 401
            assert revoked_me.json()["detail"] == "token is revoked"
            assert user_count == 1
            assert revocation_count == 1
            assert user_row is not None
            assert user_row.password_hash.startswith("pbkdf2_sha256$")
        finally:
            await engine.dispose()


async def test_user_identity_admin_api_persists_external_subjects_against_postgres() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for user identity API test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()
        app.state.reactor = AuthApiContainer(session_factory)
        transport = ASGITransport(app=app)
        headers = {
            "X-Reactor-Role": "ADMIN",
            "X-Reactor-User-Id": "admin_1",
            "X-Reactor-Tenant-Id": "tenant_1",
        }

        try:
            await SqlAlchemyUserStore(session_factory).save(
                UserRecord(
                    id="user_1",
                    email="user_1@example.com",
                    name="User One",
                    password_hash="pbkdf2_sha256$fixture",  # noqa: S106
                    role=UserRole.USER,
                    tenant_id="tenant_1",
                )
            )
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                upserted = await client.put(
                    "/v1/admin/user-identities",
                    headers=headers,
                    json={
                        "userId": "user_1",
                        "provider": "jira",
                        "externalSubject": "acct-123",
                        "metadata": {"workspace": "ENG"},
                    },
                )
                found = await client.get(
                    "/api/admin/user-identities/by-external-subject",
                    headers=headers,
                    params={"provider": "jira", "externalSubject": "acct-123"},
                )
                listed = await client.get("/v1/admin/user-identities", headers=headers)
                deleted = await client.delete(
                    "/api/admin/user-identities/by-external-subject",
                    headers=headers,
                    params={"provider": "jira", "externalSubject": "acct-123"},
                )
                missing = await client.get(
                    "/v1/admin/user-identities/by-external-subject",
                    headers=headers,
                    params={"provider": "jira", "externalSubject": "acct-123"},
                )

            async with session_factory() as session:
                identity_count = await session.scalar(select(func.count(UserIdentity.id)))

            assert upserted.status_code == 200
            assert upserted.json()["tenantId"] == "tenant_1"
            assert upserted.json()["provider"] == "jira"
            assert upserted.json()["externalSubject"] == "acct-123"
            assert found.status_code == 200
            assert found.json()["metadata"] == {"workspace": "ENG"}
            assert listed.status_code == 200
            assert [item["externalSubject"] for item in listed.json()["items"]] == ["acct-123"]
            assert deleted.status_code == 204
            assert missing.status_code == 404
            assert identity_count == 0
        finally:
            await engine.dispose()


class AuthApiContainer:
    def __init__(self, session_factory: async_sessionmaker[Any]) -> None:
        self.settings = Settings(
            auth_jwt_secret=SECRET,
            auth_self_registration_enabled=True,
            auth_default_tenant_id="default",
        )
        self._user_store = SqlAlchemyUserStore(session_factory)
        self._user_identity_store = SqlAlchemyUserIdentityStore(session_factory)
        self._token_revocation_store = SqlAlchemyTokenRevocationStore(session_factory)

    def user_store(self) -> SqlAlchemyUserStore:
        return self._user_store

    def token_revocation_store(self) -> SqlAlchemyTokenRevocationStore:
        return self._token_revocation_store

    def user_identity_store(self) -> SqlAlchemyUserIdentityStore:
        return self._user_identity_store

    def iam_token_exchange_service(self) -> None:
        return None


def postgres_container() -> PostgresContainer:
    return PostgresContainer(
        image="pgvector/pgvector:0.8.3-pg18-trixie",
        username="reactor",
        password="reactor",  # noqa: S106 - ephemeral Docker test credential
        dbname="reactor",
    )


def migrate_postgres(sync_url: str) -> None:
    previous_url = os.environ.get("REACTOR_DATABASE_URL")
    os.environ["REACTOR_DATABASE_URL"] = sync_url
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        if previous_url is None:
            os.environ.pop("REACTOR_DATABASE_URL", None)
        else:
            os.environ["REACTOR_DATABASE_URL"] = previous_url
        get_settings.cache_clear()
