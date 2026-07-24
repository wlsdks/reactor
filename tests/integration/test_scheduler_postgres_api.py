from __future__ import annotations

import os
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from docker.errors import DockerException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from reactor.api.app import create_app
from reactor.core.settings import Settings, get_settings
from reactor.persistence.scheduler_store import (
    SqlAlchemyScheduledJobExecutionStore,
    SqlAlchemySchedulerStore,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("REACTOR_TEST_POSTGRES") != "1",
    reason="set REACTOR_TEST_POSTGRES=1 to run Docker-backed scheduler API tests",
)

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}


async def test_scheduler_prompt_lab_auto_optimize_job_persists_against_postgres() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for scheduler API test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()
        app.state.reactor = SchedulerApiContainer(session_factory)
        transport = ASGITransport(app=app)

        try:
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                created = await client.post(
                    "/api/scheduler/jobs",
                    headers=ADMIN_HEADERS,
                    json={
                        "name": "PromptLab auto optimize",
                        "cronExpression": "0 0 9 * * *",
                        "jobType": "PROMPT_LAB_AUTO_OPTIMIZE",
                        "toolArguments": {"templateId": "tmpl-1", "candidateCount": 2},
                    },
                )
                job_id = created.json()["id"]
                fetched = await client.get(f"/api/scheduler/jobs/{job_id}", headers=ADMIN_HEADERS)

            assert created.status_code == 201
            assert created.json()["jobType"] == "PROMPT_LAB_AUTO_OPTIMIZE"
            assert fetched.status_code == 200
            assert fetched.json()["toolArguments"] == {
                "templateId": "tmpl-1",
                "candidateCount": 2,
            }
        finally:
            await engine.dispose()


class SchedulerApiContainer:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.settings = Settings()
        self._scheduler_store = SqlAlchemySchedulerStore(session_factory)
        self._execution_store = SqlAlchemyScheduledJobExecutionStore(session_factory)

    def scheduler_store(self) -> SqlAlchemySchedulerStore:
        return self._scheduler_store

    def scheduled_job_execution_store(self) -> SqlAlchemyScheduledJobExecutionStore:
        return self._execution_store


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
