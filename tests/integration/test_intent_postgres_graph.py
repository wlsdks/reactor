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
from reactor.agents.profiles import GraphProfile, GraphProfileRegistry
from reactor.agents.state import ReactorState
from reactor.core.settings import get_settings
from reactor.guards.intents import IntentDefinition
from reactor.persistence.intent_store import SqlAlchemyIntentRegistry

pytestmark = pytest.mark.skipif(
    os.environ.get("REACTOR_TEST_POSTGRES") != "1",
    reason="set REACTOR_TEST_POSTGRES=1 to run Docker-backed intent graph tests",
)


async def test_intent_registry_selects_graph_profile_through_langgraph_against_postgres() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for intent graph test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        intent_registry = SqlAlchemyIntentRegistry(session_factory)
        graph_profile_registry = GraphProfileRegistry(
            [
                GraphProfile(
                    profile_id="standard",
                    prompt_version="standard-v1",
                    model_provider="openai",
                    model="gpt-5-mini",
                    tool_allowlist=[],
                    max_tool_calls=1,
                ),
                GraphProfile(
                    profile_id="rag",
                    prompt_version="rag-v3",
                    model_provider="anthropic",
                    model="claude-sonnet-4-5",
                    tool_allowlist=["Rag:hybrid_search"],
                    max_tool_calls=5,
                    temperature=0.1,
                ),
            ]
        )
        graph = build_reactor_graph(
            graph_profile=graph_profile_registry.get("standard"),
            graph_profile_registry=graph_profile_registry,
            intent_registry=intent_registry,
        )

        try:
            await intent_registry.save(
                IntentDefinition(
                    name="disabled_knowledge_search",
                    description="Disabled retrieval intent must not route",
                    keywords=("source",),
                    profile="rag",
                    enabled=False,
                )
            )

            unmatched = await graph.ainvoke(graph_state("Find the source policy for MFA reset"))

            assert unmatched["graph_profile"] == "standard"
            assert unmatched["response_metadata"]["intent_resolution_status"] == "unmatched"

            await intent_registry.save(
                IntentDefinition(
                    name="knowledge_search",
                    description="Grounded knowledge retrieval",
                    keywords=("policy", "source"),
                    profile="rag",
                )
            )

            matched = await graph.ainvoke(graph_state("Find the source policy for MFA reset"))

            assert matched["graph_profile"] == "rag"
            assert matched["prompt_version"] == "rag-v3"
            assert matched["selected_model"] == "claude-sonnet-4-5"
            assert matched["active_tools"] == ["Rag:hybrid_search"]
            assert matched["max_tool_calls"] == 5
            assert matched["response_metadata"]["intent_name"] == "knowledge_search"
            assert matched["response_metadata"]["intent_confidence"] == 1.0
            assert matched["response_metadata"]["intent_classified_by"] == "rule"
        finally:
            await engine.dispose()


def graph_state(message: str) -> ReactorState:
    return ReactorState(
        run_id="run_test",
        tenant_id="tenant_1",
        user_id="user_1",
        messages=[HumanMessage(content=message)],
        tool_call_count=0,
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
