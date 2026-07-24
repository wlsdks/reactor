from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from reactor.agents import stores
from reactor.agents.stores import postgres_graph_store


def test_alembic_graph_store_versions_match_installed_langgraph() -> None:
    with open("migrations/versions/202607230002_langgraph_store_tables.py") as file:
        migration = file.read()

    assert len(stores.AsyncPostgresStore.MIGRATIONS) == 4
    assert "VALUES (0), (1), (2), (3)" in migration


async def test_postgres_graph_store_connects_without_runtime_schema_mutation(
    monkeypatch: Any,
) -> None:
    calls: list[str] = []

    class FakeStore:
        async def setup(self) -> None:
            raise AssertionError("graph store schema setup belongs to Alembic")

    @asynccontextmanager
    async def fake_from_conn_string(database_url: str):
        calls.append(f"open:{database_url}")
        yield FakeStore()
        calls.append("close")

    monkeypatch.setattr(
        stores.AsyncPostgresStore,
        "from_conn_string",
        fake_from_conn_string,
    )

    async with postgres_graph_store("postgresql://reactor/db") as store:
        assert isinstance(store, FakeStore)
        assert calls == ["open:postgresql://reactor/db"]

    assert calls == ["open:postgresql://reactor/db", "close"]
