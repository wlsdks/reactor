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
from reactor.guards.input import InputGuard, InputGuardBlocked
from reactor.guards.rules import InputGuardRuleRecord, PatternType, RuleAction
from reactor.persistence.input_guard_rule_store import SqlAlchemyInputGuardRuleStore

pytestmark = pytest.mark.skipif(
    os.environ.get("REACTOR_TEST_POSTGRES") != "1",
    reason="set REACTOR_TEST_POSTGRES=1 to run Docker-backed input guard graph tests",
)


async def test_input_guard_custom_rules_execute_through_langgraph_against_postgres() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for input guard graph test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        store = SqlAlchemyInputGuardRuleStore(session_factory)
        graph = build_reactor_graph(input_guard=InputGuard(dynamic_rule_store=store))

        try:
            await store.save(
                InputGuardRuleRecord(
                    id="rule_disabled_block",
                    tenant_id="tenant_1",
                    name="Disabled export block",
                    pattern="export payroll",
                    pattern_type=PatternType.KEYWORD,
                    action=RuleAction.BLOCK,
                    priority=900,
                    enabled=False,
                )
            )
            await store.save(
                InputGuardRuleRecord(
                    id="rule_warn_only",
                    tenant_id="tenant_1",
                    name="Warn unusual",
                    pattern="unusual",
                    pattern_type=PatternType.KEYWORD,
                    action=RuleAction.WARN,
                    priority=800,
                )
            )
            await store.save(
                InputGuardRuleRecord(
                    id="rule_other_tenant_block",
                    tenant_id="tenant_other",
                    name="Other tenant export block",
                    pattern="export payroll",
                    pattern_type=PatternType.KEYWORD,
                    action=RuleAction.BLOCK,
                    priority=900,
                )
            )

            allowed = await graph.ainvoke(graph_state("export payroll unusual"))

            assert "Agent runtime is ready" in allowed["response_text"]
            assert "Reactor Python/LangGraph" not in allowed["response_text"]
            assert allowed["guard_status"] == "allowed"

            await store.save(
                InputGuardRuleRecord(
                    id="rule_enabled_block",
                    tenant_id="tenant_1",
                    name="Block export",
                    pattern="export payroll",
                    pattern_type=PatternType.KEYWORD,
                    action=RuleAction.BLOCK,
                    priority=1000,
                )
            )
            await store.save(
                InputGuardRuleRecord(
                    id="rule_regex_block",
                    tenant_id="tenant_1",
                    name="Block account dump",
                    pattern=r"account\s+dump",
                    pattern_type=PatternType.REGEX,
                    action=RuleAction.BLOCK,
                    priority=950,
                )
            )

            with pytest.raises(InputGuardBlocked, match="custom_rule:Block export"):
                await graph.ainvoke(graph_state("please export payroll"))
            with pytest.raises(InputGuardBlocked, match="custom_rule:Block account dump"):
                await graph.ainvoke(graph_state("please run account dump"))
        finally:
            await engine.dispose()


def graph_state(message: str) -> ReactorState:
    return ReactorState(
        run_id="run_test",
        tenant_id="tenant_1",
        user_id="user_1",
        messages=[HumanMessage(content=message)],
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
