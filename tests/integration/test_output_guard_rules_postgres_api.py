from __future__ import annotations

import os
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from docker.errors import DockerException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from reactor.api.app import create_app
from reactor.core.settings import Settings, get_settings
from reactor.persistence.models import OutputGuardRule, OutputGuardRuleAudit
from reactor.persistence.output_guard_rule_store import (
    SqlAlchemyOutputGuardRuleAuditStore,
    SqlAlchemyOutputGuardRuleStore,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("REACTOR_TEST_POSTGRES") != "1",
    reason="set REACTOR_TEST_POSTGRES=1 to run Docker-backed output guard API tests",
)

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}


async def test_output_guard_rule_api_persists_crud_simulation_and_audits_in_postgres() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for output guard API test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()
        app.state.reactor = OutputGuardApiContainer(session_factory)
        transport = ASGITransport(app=app)

        try:
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                mask = await client.post(
                    "/api/output-guard/rules",
                    headers=ADMIN_HEADERS,
                    json={
                        "name": "Mask token",
                        "pattern": "token-[0-9]+",
                        "action": "MASK",
                        "replacement": "[TOKEN]",
                        "priority": 10,
                    },
                )
                reject = await client.post(
                    "/v1/output-guard/rules",
                    headers=ADMIN_HEADERS,
                    json={
                        "name": "Reject canary",
                        "pattern": "never-send",
                        "action": "REJECT",
                        "priority": 20,
                        "enabled": False,
                    },
                )
                reject_id = reject.json()["id"]
                updated = await client.put(
                    f"/api/output-guard/rules/{reject_id}",
                    headers=ADMIN_HEADERS,
                    json={"enabled": True, "priority": 20},
                )
                listed = await client.get("/v1/output-guard/rules", headers=ADMIN_HEADERS)
                simulated = await client.post(
                    "/api/output-guard/rules/simulate",
                    headers=ADMIN_HEADERS,
                    json={"content": "token-123 never-send"},
                )
                audits = await client.get(
                    "/api/output-guard/rules/audits?limit=10",
                    headers=ADMIN_HEADERS,
                )
                deleted = await client.delete(
                    f"/v1/output-guard/rules/{mask.json()['id']}",
                    headers=ADMIN_HEADERS,
                )

            async with session_factory() as session:
                db_rules = list(await session.scalars(select(OutputGuardRule)))
                db_audits = list(await session.scalars(select(OutputGuardRuleAudit)))

            assert mask.status_code == 201
            assert reject.status_code == 201
            assert updated.status_code == 200
            assert listed.status_code == 200
            assert [rule["id"] for rule in listed.json()] == [mask.json()["id"], reject_id]
            assert simulated.status_code == 200
            assert simulated.json()["blocked"] is True
            assert simulated.json()["resultContent"] == "[TOKEN] never-send"
            assert simulated.json()["blockedByRuleId"] == reject_id
            assert audits.status_code == 200
            assert [audit["action"] for audit in audits.json()[:4]] == [
                "SIMULATE",
                "UPDATE",
                "CREATE",
                "CREATE",
            ]
            assert deleted.status_code == 204
            assert [(rule.id, rule.enabled, rule.priority) for rule in db_rules] == [
                (reject_id, True, 20)
            ]
            assert [audit.action for audit in db_audits] == [
                "CREATE",
                "CREATE",
                "UPDATE",
                "SIMULATE",
                "DELETE",
            ]
        finally:
            await engine.dispose()


class OutputGuardApiContainer:
    def __init__(self, session_factory: async_sessionmaker[Any]) -> None:
        self.settings = Settings()
        self._rule_store = SqlAlchemyOutputGuardRuleStore(session_factory)
        self._audit_store = SqlAlchemyOutputGuardRuleAuditStore(session_factory)

    def output_guard_rule_store(self) -> SqlAlchemyOutputGuardRuleStore:
        return self._rule_store

    def output_guard_rule_audit_store(self) -> SqlAlchemyOutputGuardRuleAuditStore:
        return self._audit_store


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
