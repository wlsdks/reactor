from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from reactor.agents import checkpoints
from reactor.agents.checkpoints import postgres_checkpointer


def test_alembic_checkpoint_versions_match_installed_langgraph() -> None:
    with open("migrations/versions/202606260001_initial_agent_runs.py") as file:
        migration = file.read()

    assert len(checkpoints.AsyncPostgresSaver.MIGRATIONS) == 10
    assert "for version in range(10)" in migration


async def test_postgres_checkpointer_connects_without_runtime_schema_mutation(
    monkeypatch: Any,
) -> None:
    calls: list[str] = []

    class FakeSaver:
        async def setup(self) -> None:
            raise AssertionError("checkpoint schema setup belongs to Alembic")

    @asynccontextmanager
    async def fake_from_conn_string(database_url: str):
        calls.append(f"open:{database_url}")
        yield FakeSaver()
        calls.append("close")

    monkeypatch.setattr(
        checkpoints.AsyncPostgresSaver,
        "from_conn_string",
        fake_from_conn_string,
    )

    async with postgres_checkpointer("postgresql://reactor/db") as saver:
        assert isinstance(saver, FakeSaver)
        assert calls == ["open:postgresql://reactor/db"]

    assert calls == ["open:postgresql://reactor/db", "close"]
