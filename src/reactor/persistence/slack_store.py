from __future__ import annotations

from typing import Any

from sqlalchemy import Update, delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.kernel.ids import new_id
from reactor.persistence.models import (
    ChannelFaqRegistration,
    SlackBotInstance,
    SlackProactiveChannel,
)
from reactor.slack.faq import (
    AutoReplyMode,
    IngestStatus,
)
from reactor.slack.faq import (
    ChannelFaqRegistration as ChannelFaqRegistrationRecord,
)
from reactor.slack.models import ProactiveChannelRecord, SlackBotInstanceRecord


class SqlAlchemySlackBotStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(self, *, tenant_id: str) -> list[SlackBotInstanceRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(SlackBotInstance)
                .where(SlackBotInstance.tenant_id == tenant_id)
                .order_by(SlackBotInstance.created_at.asc())
            )
            return [slack_bot_from_model(row) for row in rows]

    async def list_enabled(self, *, tenant_id: str) -> list[SlackBotInstanceRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(SlackBotInstance)
                .where(
                    SlackBotInstance.tenant_id == tenant_id,
                    SlackBotInstance.enabled.is_(True),
                )
                .order_by(SlackBotInstance.created_at.asc())
            )
            return [slack_bot_from_model(row) for row in rows]

    async def get(self, *, tenant_id: str, bot_id: str) -> SlackBotInstanceRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(SlackBotInstance).where(
                    SlackBotInstance.tenant_id == tenant_id,
                    SlackBotInstance.id == bot_id,
                )
            )
            return slack_bot_from_model(row) if row is not None else None

    async def find_by_name(self, *, tenant_id: str, name: str) -> SlackBotInstanceRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(SlackBotInstance).where(
                    SlackBotInstance.tenant_id == tenant_id,
                    SlackBotInstance.name == name,
                )
            )
            return slack_bot_from_model(row) if row is not None else None

    async def save(self, record: SlackBotInstanceRecord) -> SlackBotInstanceRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    insert(SlackBotInstance)
                    .values(slack_bot_values(record))
                    .on_conflict_do_update(
                        index_elements=[SlackBotInstance.id],
                        set_=slack_bot_values(record, include_id=False, include_created_at=False),
                    )
                    .returning(SlackBotInstance)
                )
                if row is None:
                    raise RuntimeError("slack bot upsert did not return a row")
                return slack_bot_from_model(row)

    async def delete(self, *, tenant_id: str, bot_id: str) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                existing = await session.scalar(
                    select(SlackBotInstance.id).where(
                        SlackBotInstance.tenant_id == tenant_id,
                        SlackBotInstance.id == bot_id,
                    )
                )
                if existing is None:
                    return False
                await session.execute(
                    delete(SlackBotInstance).where(
                        SlackBotInstance.tenant_id == tenant_id,
                        SlackBotInstance.id == bot_id,
                    )
                )
                return True


class SqlAlchemyProactiveChannelStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(self, *, tenant_id: str) -> list[ProactiveChannelRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(SlackProactiveChannel)
                .where(SlackProactiveChannel.tenant_id == tenant_id)
                .order_by(SlackProactiveChannel.added_at.asc())
            )
            return [proactive_channel_from_model(row) for row in rows]

    async def is_enabled(self, *, tenant_id: str, channel_id: str) -> bool:
        async with self._session_factory() as session:
            existing = await session.scalar(
                select(SlackProactiveChannel.id).where(
                    SlackProactiveChannel.tenant_id == tenant_id,
                    SlackProactiveChannel.channel_id == channel_id,
                )
            )
            return existing is not None

    async def add(
        self, *, tenant_id: str, channel_id: str, channel_name: str | None
    ) -> ProactiveChannelRecord:
        record = ProactiveChannelRecord(
            tenant_id=tenant_id,
            channel_id=channel_id,
            channel_name=channel_name,
        )
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    insert(SlackProactiveChannel)
                    .values(proactive_channel_values(record))
                    .on_conflict_do_update(
                        constraint="uq_slack_proactive_channels_id",
                        set_={"channel_name": record.channel_name},
                    )
                    .returning(SlackProactiveChannel)
                )
                if row is None:
                    raise RuntimeError("proactive channel upsert did not return a row")
                return proactive_channel_from_model(row)

    async def save(self, record: ProactiveChannelRecord) -> ProactiveChannelRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    insert(SlackProactiveChannel)
                    .values(proactive_channel_values(record))
                    .on_conflict_do_update(
                        constraint="uq_slack_proactive_channels_id",
                        set_={
                            "channel_name": record.channel_name,
                            "added_at": record.added_at,
                        },
                    )
                    .returning(SlackProactiveChannel)
                )
                if row is None:
                    raise RuntimeError("proactive channel upsert did not return a row")
                return proactive_channel_from_model(row)

    async def remove(self, *, tenant_id: str, channel_id: str) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.scalar(
                    delete(SlackProactiveChannel)
                    .where(
                        SlackProactiveChannel.tenant_id == tenant_id,
                        SlackProactiveChannel.channel_id == channel_id,
                    )
                    .returning(SlackProactiveChannel.id)
                )
                return result is not None


class SqlAlchemyChannelFaqRegistrationStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(
        self,
        registration: ChannelFaqRegistrationRecord,
    ) -> ChannelFaqRegistrationRecord:
        registration.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(build_faq_registration_upsert(registration))
                if row is None:
                    raise RuntimeError("FAQ registration upsert did not return a row")
                return faq_registration_from_model(row)

    async def get(
        self,
        *,
        tenant_id: str,
        channel_id: str,
    ) -> ChannelFaqRegistrationRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(ChannelFaqRegistration).where(
                    ChannelFaqRegistration.tenant_id == tenant_id,
                    ChannelFaqRegistration.channel_id == channel_id,
                )
            )
            return faq_registration_from_model(row) if row is not None else None

    async def list(
        self,
        *,
        tenant_id: str,
        enabled_only: bool = False,
    ) -> list[ChannelFaqRegistrationRecord]:
        statement = select(ChannelFaqRegistration).where(
            ChannelFaqRegistration.tenant_id == tenant_id
        )
        if enabled_only:
            statement = statement.where(ChannelFaqRegistration.enabled.is_(True))
        statement = statement.order_by(
            ChannelFaqRegistration.last_ingested_at.asc().nulls_first(),
            ChannelFaqRegistration.channel_id.asc(),
        )
        async with self._session_factory() as session:
            rows = await session.scalars(statement)
            return [faq_registration_from_model(row) for row in rows]

    async def delete(self, *, tenant_id: str, channel_id: str) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.scalar(
                    delete(ChannelFaqRegistration)
                    .where(
                        ChannelFaqRegistration.tenant_id == tenant_id,
                        ChannelFaqRegistration.channel_id == channel_id,
                    )
                    .returning(ChannelFaqRegistration.id)
                )
                return result is not None

    async def update_ingest_result(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        status: IngestStatus,
        message_count: int | None,
        chunk_count: int | None,
        error: str | None,
    ) -> ChannelFaqRegistrationRecord | None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    build_faq_update_ingest_result(
                        tenant_id=tenant_id,
                        channel_id=channel_id,
                        status=status,
                        message_count=message_count,
                        chunk_count=chunk_count,
                        error=error,
                    )
                )
                return faq_registration_from_model(row) if row is not None else None


def slack_bot_values(
    record: SlackBotInstanceRecord,
    *,
    include_id: bool = True,
    include_created_at: bool = True,
) -> dict[str, object]:
    values: dict[str, object] = {
        "tenant_id": record.tenant_id,
        "name": record.name,
        "bot_token": record.bot_token,
        "app_token": record.app_token,
        "persona_id": record.persona_id,
        "default_channel": record.default_channel,
        "enabled": record.enabled,
        "updated_at": record.updated_at,
    }
    if include_id:
        values["id"] = record.id
    if include_created_at:
        values["created_at"] = record.created_at
    return values


def proactive_channel_values(record: ProactiveChannelRecord) -> dict[str, object]:
    return {
        "id": new_id("slack_channel"),
        "tenant_id": record.tenant_id,
        "channel_id": record.channel_id,
        "channel_name": record.channel_name,
        "added_at": record.added_at,
    }


def faq_registration_values(record: ChannelFaqRegistrationRecord) -> dict[str, object]:
    return {
        "id": new_id("faq_reg"),
        "tenant_id": record.tenant_id,
        "channel_id": record.channel_id,
        "channel_name": record.channel_name,
        "enabled": record.enabled,
        "auto_reply_mode": record.auto_reply_mode.value,
        "confidence_threshold": record.confidence_threshold,
        "days_back": record.days_back,
        "re_ingest_interval_hours": record.re_ingest_interval_hours,
        "last_ingested_at": record.last_ingested_at,
        "last_message_count": record.last_message_count,
        "last_chunk_count": record.last_chunk_count,
        "last_status": record.last_status,
        "last_error": record.last_error,
        "registered_by": record.registered_by,
        "registered_at": record.registered_at,
        "updated_at": record.updated_at,
    }


def build_faq_registration_upsert(
    record: ChannelFaqRegistrationRecord,
) -> Any:
    values = faq_registration_values(record)
    return (
        insert(ChannelFaqRegistration)
        .values(values)
        .on_conflict_do_update(
            constraint="uq_channel_faq_registrations_tenant_channel",
            set_={
                "channel_name": record.channel_name,
                "enabled": record.enabled,
                "auto_reply_mode": record.auto_reply_mode.value,
                "confidence_threshold": record.confidence_threshold,
                "days_back": record.days_back,
                "re_ingest_interval_hours": record.re_ingest_interval_hours,
                "updated_at": record.updated_at,
            },
        )
        .returning(ChannelFaqRegistration)
    )


def build_faq_update_ingest_result(
    *,
    tenant_id: str,
    channel_id: str,
    status: IngestStatus,
    message_count: int | None,
    chunk_count: int | None,
    error: str | None,
) -> Update:
    return (
        update(ChannelFaqRegistration)
        .where(
            ChannelFaqRegistration.tenant_id == tenant_id,
            ChannelFaqRegistration.channel_id == channel_id,
        )
        .values(
            last_ingested_at=select_now(),
            last_status=status.value,
            last_message_count=message_count,
            last_chunk_count=chunk_count,
            last_error=error[:4000] if error is not None else None,
        )
        .returning(ChannelFaqRegistration)
    )


def select_now():
    from sqlalchemy.sql import func

    return func.now()


def slack_bot_from_model(row: SlackBotInstance) -> SlackBotInstanceRecord:
    return SlackBotInstanceRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        bot_token=row.bot_token,
        app_token=row.app_token,
        persona_id=row.persona_id,
        default_channel=row.default_channel,
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def proactive_channel_from_model(row: SlackProactiveChannel) -> ProactiveChannelRecord:
    return ProactiveChannelRecord(
        tenant_id=row.tenant_id,
        channel_id=row.channel_id,
        channel_name=row.channel_name,
        added_at=row.added_at,
    )


def faq_registration_from_model(row: ChannelFaqRegistration) -> ChannelFaqRegistrationRecord:
    return ChannelFaqRegistrationRecord(
        tenant_id=row.tenant_id,
        channel_id=row.channel_id,
        channel_name=row.channel_name,
        enabled=row.enabled,
        auto_reply_mode=AutoReplyMode(row.auto_reply_mode),
        confidence_threshold=row.confidence_threshold,
        days_back=row.days_back,
        re_ingest_interval_hours=row.re_ingest_interval_hours,
        last_ingested_at=row.last_ingested_at,
        last_message_count=row.last_message_count,
        last_chunk_count=row.last_chunk_count,
        last_status=row.last_status,
        last_error=row.last_error,
        registered_by=row.registered_by,
        registered_at=row.registered_at,
        updated_at=row.updated_at,
    )
