from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.persistence.models import PersonaRow
from reactor.prompts.personas import PersonaRecord


class SqlAlchemyPersonaStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(self) -> list[PersonaRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_persona_list())
            return [persona_from_model(row) for row in rows]

    async def list_active(self) -> list[PersonaRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_persona_list(active=True))
            return [persona_from_model(row) for row in rows]

    async def get(self, persona_id: str) -> PersonaRecord | None:
        async with self._session_factory() as session:
            row = await session.get(PersonaRow, persona_id)
            return persona_from_model(row) if row is not None else None

    async def get_default(self) -> PersonaRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(PersonaRow)
                .where(PersonaRow.is_default.is_(True))
                .order_by(PersonaRow.created_at.asc())
                .limit(1)
            )
            return persona_from_model(row) if row is not None else None

    async def save(self, record: PersonaRecord) -> PersonaRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                if record.is_default:
                    await session.execute(clear_default_personas())
                row = await session.scalar(build_persona_upsert(record))
                if row is None:
                    raise RuntimeError("persona upsert returned no row")
                return persona_from_model(row)

    async def update(
        self,
        persona_id: str,
        *,
        name: str | None = None,
        system_prompt: str | None = None,
        is_default: bool | None = None,
        description: str | None = None,
        response_guideline: str | None = None,
        welcome_message: str | None = None,
        icon: str | None = None,
        prompt_template_id: str | None = None,
        is_active: bool | None = None,
    ) -> PersonaRecord | None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    select(PersonaRow).where(PersonaRow.id == persona_id).with_for_update()
                )
                if row is None:
                    return None
                updated = persona_from_model(row).with_updates(
                    name=name,
                    system_prompt=system_prompt,
                    is_default=is_default,
                    description=description,
                    response_guideline=response_guideline,
                    welcome_message=welcome_message,
                    icon=icon,
                    prompt_template_id=prompt_template_id,
                    is_active=is_active,
                )
                if is_default is True:
                    await session.execute(clear_default_personas())
                saved = await session.scalar(build_persona_upsert(updated))
                if saved is None:
                    raise RuntimeError("persona update returned no row")
                return persona_from_model(saved)

    async def delete(self, persona_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(delete(PersonaRow).where(PersonaRow.id == persona_id))


def build_persona_list(*, active: bool | None = None):
    statement = select(PersonaRow)
    if active is not None:
        statement = statement.where(PersonaRow.is_active.is_(active))
    return statement.order_by(PersonaRow.created_at.asc(), PersonaRow.name.asc())


def build_persona_upsert(record: PersonaRecord):
    return (
        insert(PersonaRow)
        .values(persona_values(record))
        .on_conflict_do_update(
            index_elements=[PersonaRow.id],
            set_=persona_values(record, include_created_at=False),
        )
        .returning(PersonaRow)
    )


def clear_default_personas():
    return update(PersonaRow).where(PersonaRow.is_default.is_(True)).values(is_default=False)


def persona_values(
    record: PersonaRecord,
    *,
    include_created_at: bool = True,
) -> dict[str, object]:
    values: dict[str, object] = {
        "id": record.id,
        "name": record.name,
        "system_prompt": record.system_prompt,
        "is_default": record.is_default,
        "description": record.description,
        "response_guideline": record.response_guideline,
        "welcome_message": record.welcome_message,
        "icon": record.icon,
        "is_active": record.is_active,
        "prompt_template_id": record.prompt_template_id,
        "updated_at": record.updated_at,
    }
    if include_created_at:
        values["created_at"] = record.created_at
    return values


def persona_from_model(row: PersonaRow) -> PersonaRecord:
    return PersonaRecord(
        id=row.id,
        name=row.name,
        system_prompt=row.system_prompt,
        is_default=row.is_default,
        description=row.description,
        response_guideline=row.response_guideline,
        welcome_message=row.welcome_message,
        icon=row.icon,
        is_active=row.is_active,
        prompt_template_id=row.prompt_template_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
