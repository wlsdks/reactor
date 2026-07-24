from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

Checkpointer = BaseCheckpointSaver[Any]


@asynccontextmanager
async def postgres_checkpointer(database_url: str) -> AsyncGenerator[Checkpointer]:
    async with AsyncPostgresSaver.from_conn_string(database_url) as checkpointer:
        yield checkpointer
