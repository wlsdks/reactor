from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
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
from reactor.observability.usage_ledger import UsageLedgerRecord
from reactor.persistence.usage_ledger_store import SqlAlchemyUsageLedger

pytestmark = pytest.mark.skipif(
    os.environ.get("REACTOR_TEST_POSTGRES") != "1",
    reason="set REACTOR_TEST_POSTGRES=1 to run Docker-backed admin usage API tests",
)

MANAGER_HEADERS = {
    "X-Reactor-User-Id": "manager_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN_MANAGER",
}
USER_HEADERS = {
    "X-Reactor-User-Id": "user_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "USER",
}


async def test_admin_token_cost_api_queries_postgres_usage_ledger() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for admin usage API test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        ledger = SqlAlchemyUsageLedger(session_factory)
        app = create_app()
        app.state.reactor = AdminUsageApiContainer(ledger)
        transport = ASGITransport(app=app)

        now = datetime.now(UTC)
        day = now - timedelta(days=1)
        try:
            await ledger.record(
                UsageLedgerRecord(
                    id="usage_1",
                    tenant_id="tenant_1",
                    run_id="session-a-turn-1",
                    provider="openai",
                    model="gpt-5-mini",
                    step_type="model",
                    prompt_tokens=1000,
                    completion_tokens=200,
                    total_tokens=1200,
                    estimated_cost_usd=Decimal("0.00027000"),
                    occurred_at=day,
                )
            )
            await ledger.record(
                UsageLedgerRecord(
                    id="usage_2",
                    tenant_id="tenant_1",
                    run_id="session-b-turn-1",
                    provider="anthropic",
                    model="claude-sonnet-4",
                    step_type="model",
                    prompt_tokens=5000,
                    completion_tokens=1000,
                    total_tokens=6000,
                    estimated_cost_usd=Decimal("0.02000000"),
                    occurred_at=day + timedelta(minutes=5),
                )
            )
            await ledger.record(
                UsageLedgerRecord(
                    id="usage_3",
                    tenant_id="tenant_2",
                    run_id="session-a-turn-tenant-2",
                    provider="openai",
                    model="gpt-5-mini",
                    step_type="model",
                    prompt_tokens=9000,
                    completion_tokens=9000,
                    total_tokens=18000,
                    estimated_cost_usd=Decimal("9.00000000"),
                    occurred_at=day + timedelta(minutes=10),
                )
            )

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                forbidden = await client.get(
                    "/api/admin/token-cost/by-session",
                    params={"sessionId": "session-a"},
                    headers=USER_HEADERS,
                )
                by_session = await client.get(
                    "/api/admin/token-cost/by-session",
                    params={"sessionId": "session-a"},
                    headers=MANAGER_HEADERS,
                )
                daily = await client.get(
                    "/v1/admin/token-cost/daily",
                    params={"days": 90},
                    headers=MANAGER_HEADERS,
                )
                top = await client.get(
                    "/api/admin/token-cost/top-expensive",
                    params={"days": 90, "limit": 1},
                    headers=MANAGER_HEADERS,
                )

            assert forbidden.status_code == 403
            assert forbidden.json()["detail"] == "admin access required"
            assert by_session.status_code == 200
            assert by_session.json() == [
                {
                    "runId": "session-a-turn-1",
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "stepType": "model",
                    "promptTokens": 1000,
                    "completionTokens": 200,
                    "totalTokens": 1200,
                    "estimatedCostUsd": "0.00027000",
                    "occurredAt": int(day.timestamp() * 1000),
                }
            ]
            assert daily.status_code == 200
            assert {
                (row["day"], row["model"], row["totalTokens"], row["totalCostUsd"])
                for row in daily.json()
            } == {
                (day.date().isoformat(), "gpt-5-mini", 1200, "0.00027000"),
                (day.date().isoformat(), "claude-sonnet-4", 6000, "0.02000000"),
            }
            assert top.status_code == 200
            assert top.json()[0]["runId"] == "session-b-turn-1"
            assert top.json()[0]["totalTokens"] == 6000
            assert top.json()[0]["totalCostUsd"] == "0.02000000"
        finally:
            await engine.dispose()


class AdminUsageApiContainer:
    def __init__(self, ledger: SqlAlchemyUsageLedger) -> None:
        self.settings = Settings()
        self._usage_ledger = ledger

    def usage_ledger(self) -> SqlAlchemyUsageLedger:
        return self._usage_ledger


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
