from __future__ import annotations

import os
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from docker.errors import DockerException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from reactor.core.container import AppContainer
from reactor.core.settings import Settings, get_settings
from reactor.persistence.runtime_settings_store import SqlAlchemyRuntimeSettingsStore
from reactor.runtime_settings.service import GLOBAL_TENANT_ID, RuntimeSettingUpdate

pytestmark = pytest.mark.skipif(
    os.environ.get("REACTOR_TEST_POSTGRES") != "1",
    reason="set REACTOR_TEST_POSTGRES=1 to run Docker-backed runtime settings tests",
)


async def test_app_container_effective_settings_applies_postgres_runtime_overrides() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for runtime settings test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        store = SqlAlchemyRuntimeSettingsStore(session_factory)
        app_container = AppContainer(
            settings=Settings(max_tool_calls=4, response_cache_enabled=False),
            engine=engine,
            session_factory=session_factory,
            graph=object(),
            checkpointer=None,
        )

        try:
            await store.set(
                RuntimeSettingUpdate(
                    tenant_id=GLOBAL_TENANT_ID,
                    key="settings.max_tool_calls",
                    value="6",
                    value_type="INT",
                    category="settings",
                    updated_by="admin_1",
                )
            )
            await store.set(
                RuntimeSettingUpdate(
                    tenant_id="tenant_1",
                    key="settings.max_tool_calls",
                    value="9",
                    value_type="INT",
                    category="settings",
                    updated_by="admin_1",
                )
            )
            await store.set(
                RuntimeSettingUpdate(
                    tenant_id="tenant_1",
                    key="settings.response_cache_enabled",
                    value="true",
                    value_type="BOOLEAN",
                    category="settings",
                    updated_by="admin_1",
                )
            )
            await store.set(
                RuntimeSettingUpdate(
                    tenant_id="tenant_1",
                    key="settings.cors_allowed_origins",
                    value='["https://sample.example"]',
                    value_type="JSON",
                    category="settings",
                    updated_by="admin_1",
                )
            )

            result = await app_container.effective_settings(tenant_id="tenant_1")
            other_tenant_result = await app_container.effective_settings(tenant_id="tenant_2")

            assert result.settings.max_tool_calls == 9
            assert result.settings.response_cache_enabled is True
            assert result.settings.cors_allowed_origins == ["https://sample.example"]
            assert result.applied_keys == (
                "settings.response_cache_enabled",
                "settings.max_tool_calls",
                "settings.cors_allowed_origins",
            )
            assert result.ignored_keys == ()
            assert result.errors == {}
            assert other_tenant_result.settings.max_tool_calls == 6
            assert other_tenant_result.settings.response_cache_enabled is False
        finally:
            await engine.dispose()


async def test_app_container_effective_settings_reports_invalid_postgres_overrides() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for runtime settings test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        store = SqlAlchemyRuntimeSettingsStore(session_factory)
        app_container = AppContainer(
            settings=Settings(max_tool_calls=4, response_cache_enabled=False),
            engine=engine,
            session_factory=session_factory,
            graph=object(),
            checkpointer=None,
        )

        try:
            await store.set(
                RuntimeSettingUpdate(
                    tenant_id=GLOBAL_TENANT_ID,
                    key="settings.max_tool_calls",
                    value="200",
                    value_type="INT",
                    category="settings",
                    updated_by="admin_1",
                )
            )
            await store.set(
                RuntimeSettingUpdate(
                    tenant_id=GLOBAL_TENANT_ID,
                    key="settings.response_cache_enabled",
                    value="maybe",
                    value_type="BOOLEAN",
                    category="settings",
                    updated_by="admin_1",
                )
            )

            result = await app_container.effective_settings()

            assert result.settings.max_tool_calls == 4
            assert result.settings.response_cache_enabled is False
            assert result.applied_keys == ()
            assert result.ignored_keys == (
                "settings.max_tool_calls",
                "settings.response_cache_enabled",
            )
            assert "less than or equal to 100" in result.errors["__settings__"]
            assert result.errors["settings.response_cache_enabled"] == (
                "invalid BOOLEAN value for settings.response_cache_enabled"
            )
        finally:
            await engine.dispose()


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
