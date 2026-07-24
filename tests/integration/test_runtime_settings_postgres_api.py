from __future__ import annotations

import os
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from docker.errors import DockerException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from reactor.api.app import create_app
from reactor.core.settings import Settings, get_settings
from reactor.persistence.runtime_settings_store import SqlAlchemyRuntimeSettingsStore

pytestmark = pytest.mark.skipif(
    os.environ.get("REACTOR_TEST_POSTGRES") != "1",
    reason="set REACTOR_TEST_POSTGRES=1 to run Docker-backed runtime settings API tests",
)

ADMIN_HEADERS = {
    "X-Reactor-Admin": "true",
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
}


async def test_runtime_settings_admin_api_persists_crud_against_postgres() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for runtime settings API test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        store = SqlAlchemyRuntimeSettingsStore(session_factory)
        app = create_app()
        app.state.reactor = RuntimeSettingsApiContainer(store)
        transport = ASGITransport(app=app)

        try:
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                missing = await client.get(
                    "/v1/admin/settings/settings.max_tool_calls",
                    params={"tenant_id": "tenant_1"},
                    headers=ADMIN_HEADERS,
                )
                saved = await client.put(
                    "/v1/admin/settings/settings.max_tool_calls",
                    params={"tenant_id": "tenant_1"},
                    headers=ADMIN_HEADERS,
                    json={
                        "value": "8",
                        "type": "INT",
                        "category": "settings",
                        "description": "Tenant max tool calls",
                        "metadata": {"source": "postgres-api-test"},
                    },
                )
                fetched = await client.get(
                    "/v1/admin/settings/settings.max_tool_calls",
                    params={"tenant_id": "tenant_1"},
                    headers=ADMIN_HEADERS,
                )
                listed = await client.get(
                    "/v1/admin/settings",
                    params={"tenant_id": "tenant_1"},
                    headers=ADMIN_HEADERS,
                )
                deleted = await client.delete(
                    "/v1/admin/settings/settings.max_tool_calls",
                    params={"tenant_id": "tenant_1"},
                    headers=ADMIN_HEADERS,
                )
                after_delete = await client.get(
                    "/v1/admin/settings/settings.max_tool_calls",
                    params={"tenant_id": "tenant_1"},
                    headers=ADMIN_HEADERS,
                )

            assert missing.status_code == 404
            assert missing.json()["detail"] == "runtime setting not found"
            assert saved.status_code == 200
            assert saved.json() == {
                "tenantId": "tenant_1",
                "key": "settings.max_tool_calls",
                "value": "8",
                "status": "updated",
            }
            assert fetched.status_code == 200
            assert fetched.json()["updatedBy"] == "admin_1"
            assert fetched.json()["metadata"] == {"source": "postgres-api-test"}
            assert listed.status_code == 200
            assert [item["key"] for item in listed.json()] == ["settings.max_tool_calls"]
            assert deleted.status_code == 204
            assert after_delete.status_code == 404
        finally:
            await engine.dispose()


class RuntimeSettingsApiContainer:
    def __init__(self, store: SqlAlchemyRuntimeSettingsStore) -> None:
        self.settings = Settings()
        self._store = store

    def runtime_settings_store(self) -> SqlAlchemyRuntimeSettingsStore:
        return self._store


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
