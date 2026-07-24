from __future__ import annotations

from dataclasses import dataclass

import psycopg


@dataclass(frozen=True)
class DatabaseHealth:
    configured: bool
    ok: bool
    detail: str


async def check_database(database_url: str | None, required: bool) -> DatabaseHealth:
    if not database_url:
        return DatabaseHealth(configured=False, ok=not required, detail="database not configured")

    try:
        async with await psycopg.AsyncConnection.connect(database_url, connect_timeout=2) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("select 1")
                await cursor.fetchone()
    except Exception as exc:  # pragma: no cover - integration behavior
        return DatabaseHealth(configured=True, ok=False, detail=exc.__class__.__name__)

    return DatabaseHealth(configured=True, ok=True, detail="ok")
