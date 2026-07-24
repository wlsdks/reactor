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
from reactor.persistence.intent_store import SqlAlchemyIntentRegistry
from reactor.persistence.models import IntentDefinitionModel

pytestmark = pytest.mark.skipif(
    os.environ.get("REACTOR_TEST_POSTGRES") != "1",
    reason="set REACTOR_TEST_POSTGRES=1 to run Docker-backed intent API tests",
)

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}


async def test_intent_api_persists_crud_contract_against_postgres() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for intent API test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()
        app.state.reactor = IntentApiContainer(session_factory)
        transport = ASGITransport(app=app)

        try:
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                created = await client.post(
                    "/api/intents",
                    headers=ADMIN_HEADERS,
                    json={
                        "name": "knowledge_search",
                        "description": "Grounded knowledge retrieval",
                        "examples": ["find the source"],
                        "keywords": ["source", "policy"],
                        "profile": "rag",
                        "enabled": True,
                    },
                )
                duplicate = await client.post(
                    "/v1/intents",
                    headers=ADMIN_HEADERS,
                    json={
                        "name": "knowledge_search",
                        "description": "Duplicate",
                    },
                )
                listed = await client.get("/v1/intents", headers=ADMIN_HEADERS)
                fetched = await client.get("/api/intents/knowledge_search", headers=ADMIN_HEADERS)
                updated = await client.put(
                    "/v1/intents/knowledge_search",
                    headers=ADMIN_HEADERS,
                    json={
                        "description": "Updated retrieval classifier",
                        "keywords": ["kb"],
                        "enabled": False,
                    },
                )
                missing = await client.get("/api/intents/missing", headers=ADMIN_HEADERS)

                async with session_factory() as session:
                    row_before_delete = await session.get(
                        IntentDefinitionModel,
                        "knowledge_search",
                    )

                deleted = await client.delete(
                    "/api/intents/knowledge_search",
                    headers=ADMIN_HEADERS,
                )

                async with session_factory() as session:
                    rows_after_delete = list(await session.scalars(select(IntentDefinitionModel)))

            assert created.status_code == 201
            assert created.json() == {
                "name": "knowledge_search",
                "description": "Grounded knowledge retrieval",
                "examples": ["find the source"],
                "keywords": ["source", "policy"],
                "profile": "rag",
                "enabled": True,
            }
            assert duplicate.status_code == 409
            assert duplicate.json()["detail"] == "Intent 'knowledge_search' already exists"
            assert listed.status_code == 200
            assert [intent["name"] for intent in listed.json()] == ["knowledge_search"]
            assert fetched.status_code == 200
            assert fetched.json()["profile"] == "rag"
            assert updated.status_code == 200
            assert updated.json()["description"] == "Updated retrieval classifier"
            assert updated.json()["examples"] == ["find the source"]
            assert updated.json()["keywords"] == ["kb"]
            assert updated.json()["enabled"] is False
            assert missing.status_code == 404
            assert missing.json()["detail"] == "Intent not found: missing"
            assert row_before_delete is not None
            assert row_before_delete.description == "Updated retrieval classifier"
            assert row_before_delete.keywords == ["kb"]
            assert row_before_delete.enabled is False
            assert deleted.status_code == 204
            assert rows_after_delete == []
        finally:
            await engine.dispose()


class IntentApiContainer:
    def __init__(self, session_factory: async_sessionmaker[Any]) -> None:
        self.settings = Settings()
        self._registry = SqlAlchemyIntentRegistry(session_factory)

    def intent_registry(self) -> SqlAlchemyIntentRegistry:
        return self._registry


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
