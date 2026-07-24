from __future__ import annotations

import os
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from docker.errors import DockerException
from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from reactor.agents.graph import build_reactor_graph
from reactor.agents.state import ReactorState
from reactor.core.settings import get_settings
from reactor.guards.output import OutputGuard, OutputGuardBlocked
from reactor.guards.output_rules import OutputGuardRuleAction, OutputGuardRuleRecord
from reactor.persistence.output_guard_rule_store import SqlAlchemyOutputGuardRuleStore

pytestmark = pytest.mark.skipif(
    os.environ.get("REACTOR_TEST_POSTGRES") != "1",
    reason="set REACTOR_TEST_POSTGRES=1 to run Docker-backed output guard graph tests",
)


async def test_output_guard_dynamic_rules_execute_through_langgraph_against_postgres() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for output guard graph test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        store = SqlAlchemyOutputGuardRuleStore(session_factory)
        graph = build_reactor_graph(output_guard=OutputGuard(dynamic_rule_store=store))

        try:
            await store.save(
                OutputGuardRuleRecord(
                    id="rule_mask_runtime",
                    tenant_id="tenant_1",
                    name="Mask fallback marker",
                    pattern="Agent runtime",
                    action=OutputGuardRuleAction.MASK,
                    replacement="Runtime",
                    priority=10,
                )
            )
            await store.save(
                OutputGuardRuleRecord(
                    id="rule_disabled_reject",
                    tenant_id="tenant_1",
                    name="Disabled reject ready",
                    pattern="ready",
                    action=OutputGuardRuleAction.REJECT,
                    priority=20,
                    enabled=False,
                )
            )
            await store.save(
                OutputGuardRuleRecord(
                    id="rule_other_tenant_reject",
                    tenant_id="tenant_other",
                    name="Other tenant reject ready",
                    pattern="ready",
                    action=OutputGuardRuleAction.REJECT,
                    priority=20,
                )
            )

            result = await graph.ainvoke(graph_state(tenant_id="tenant_1"))

            assert "Agent runtime" not in result["response_text"]
            assert "Runtime is ready" in result["response_text"]
            assert result["output_guard_status"] == "modified"
            assert result["response_metadata"]["output_guard_status"] == "modified"

            await store.save(
                OutputGuardRuleRecord(
                    id="rule_enabled_reject",
                    tenant_id="tenant_1",
                    name="Reject ready marker",
                    pattern="ready",
                    action=OutputGuardRuleAction.REJECT,
                    priority=5,
                )
            )

            with pytest.raises(OutputGuardBlocked, match="dynamic_rule:Reject ready marker"):
                await graph.ainvoke(graph_state(tenant_id="tenant_1"))
        finally:
            await engine.dispose()


def graph_state(*, tenant_id: str) -> ReactorState:
    return ReactorState(
        run_id="run_test",
        tenant_id=tenant_id,
        user_id="user_1",
        messages=[HumanMessage(content="hello")],
        tool_call_count=0,
        max_tool_calls=10,
    )


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
