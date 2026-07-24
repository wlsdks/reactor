from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres import AsyncPostgresStore

GraphStore = BaseStore


def in_memory_graph_store() -> GraphStore:
    return InMemoryStore()


@asynccontextmanager
async def postgres_graph_store(database_url: str) -> AsyncGenerator[GraphStore]:
    async with AsyncPostgresStore.from_conn_string(database_url) as store:
        yield store
