from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.agents.specs import AgentSpecMode, AgentSpecRecord
from reactor.persistence.models import AgentSpecRow


class SqlAlchemyAgentSpecStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(self) -> list[AgentSpecRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_agent_spec_list())
            return [agent_spec_from_model(row) for row in rows]

    async def list_enabled(self) -> list[AgentSpecRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_agent_spec_list(enabled=True))
            return [agent_spec_from_model(row) for row in rows]

    async def get(self, spec_id: str) -> AgentSpecRecord | None:
        async with self._session_factory() as session:
            row = await session.get(AgentSpecRow, spec_id)
            return agent_spec_from_model(row) if row is not None else None

    async def save(self, record: AgentSpecRecord) -> AgentSpecRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(build_agent_spec_upsert(record))
                if row is None:
                    raise RuntimeError("agent spec upsert returned no row")
                return agent_spec_from_model(row)

    async def delete(self, spec_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(delete(AgentSpecRow).where(AgentSpecRow.id == spec_id))


def build_agent_spec_list(*, enabled: bool | None = None):
    statement = select(AgentSpecRow)
    if enabled is not None:
        statement = statement.where(AgentSpecRow.enabled.is_(enabled))
    return statement.order_by(AgentSpecRow.created_at.asc(), AgentSpecRow.name.asc())


def build_agent_spec_upsert(record: AgentSpecRecord):
    return (
        insert(AgentSpecRow)
        .values(agent_spec_values(record))
        .on_conflict_do_update(
            index_elements=[AgentSpecRow.id],
            set_=agent_spec_values(record, include_created_at=False),
        )
        .returning(AgentSpecRow)
    )


def agent_spec_values(
    record: AgentSpecRecord,
    *,
    include_created_at: bool = True,
) -> dict[str, object]:
    values: dict[str, object] = {
        "id": record.id,
        "name": record.name,
        "description": record.description,
        "tool_names": list(record.tool_names),
        "keywords": list(record.keywords),
        "system_prompt": record.system_prompt,
        "mode": record.mode.value,
        "independent_execution": record.independent_execution,
        "enabled": record.enabled,
        "updated_at": record.updated_at,
    }
    if include_created_at:
        values["created_at"] = record.created_at
    return values


def agent_spec_from_model(row: AgentSpecRow) -> AgentSpecRecord:
    return AgentSpecRecord(
        id=row.id,
        name=row.name,
        description=row.description,
        tool_names=tuple(str(item) for item in row.tool_names),
        keywords=tuple(str(item) for item in row.keywords),
        system_prompt=row.system_prompt,
        mode=AgentSpecMode(row.mode),
        independent_execution=row.independent_execution,
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
