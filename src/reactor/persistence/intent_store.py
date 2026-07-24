from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.guards.intents import IntentDefinition
from reactor.persistence.models import IntentDefinitionModel


class SqlAlchemyIntentRegistry:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(self) -> list[IntentDefinition]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(IntentDefinitionModel).order_by(IntentDefinitionModel.name.asc())
            )
            return [intent_from_model(row) for row in rows]

    async def get(self, intent_name: str) -> IntentDefinition | None:
        async with self._session_factory() as session:
            row = await session.get(IntentDefinitionModel, intent_name)
            return intent_from_model(row) if row is not None else None

    async def save(self, intent: IntentDefinition) -> IntentDefinition:
        intent.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(build_intent_upsert(intent))
                if row is None:
                    raise RuntimeError("intent upsert returned no row")
                return intent_from_model(row)

    async def update(
        self,
        *,
        intent_name: str,
        intent: IntentDefinition,
    ) -> IntentDefinition | None:
        intent.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    update(IntentDefinitionModel)
                    .where(IntentDefinitionModel.name == intent_name)
                    .values(intent_values(intent, include_created_at=False))
                    .returning(IntentDefinitionModel)
                )
                return intent_from_model(row) if row is not None else None

    async def delete(self, intent_name: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    delete(IntentDefinitionModel).where(IntentDefinitionModel.name == intent_name)
                )


def build_intent_upsert(intent: IntentDefinition):
    return (
        insert(IntentDefinitionModel)
        .values(intent_values(intent))
        .on_conflict_do_update(
            index_elements=[IntentDefinitionModel.name],
            set_=intent_values(intent, include_created_at=False),
        )
        .returning(IntentDefinitionModel)
    )


def intent_values(
    intent: IntentDefinition,
    *,
    include_created_at: bool = True,
) -> dict[str, object]:
    values: dict[str, object] = {
        "name": intent.name,
        "description": intent.description,
        "examples": list(intent.examples),
        "keywords": list(intent.keywords),
        "profile": intent.profile,
        "enabled": intent.enabled,
        "updated_at": intent.updated_at,
    }
    if include_created_at:
        values["created_at"] = intent.created_at
    return values


def intent_from_model(row: IntentDefinitionModel) -> IntentDefinition:
    return IntentDefinition(
        name=row.name,
        description=row.description,
        examples=tuple(str(item) for item in row.examples),
        keywords=tuple(str(item) for item in row.keywords),
        profile=row.profile,
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
