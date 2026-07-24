from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.kernel.ids import new_id
from reactor.persistence.models import RuntimeSetting
from reactor.runtime_settings.service import (
    GLOBAL_TENANT_ID,
    RuntimeSettingRecord,
    RuntimeSettingType,
    RuntimeSettingUpdate,
)


class SqlAlchemyRuntimeSettingsStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def set(self, update: RuntimeSettingUpdate) -> RuntimeSettingRecord:
        update.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(build_runtime_setting_upsert(update))
                if row is None:
                    raise RuntimeError("runtime setting upsert did not return a row")
        return runtime_setting_record(row)

    async def find(
        self,
        key: str,
        *,
        tenant_id: str = GLOBAL_TENANT_ID,
    ) -> RuntimeSettingRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(build_runtime_setting_find(key, tenant_id=tenant_id))
        return runtime_setting_record(row) if row is not None else None

    async def list(self, *, tenant_id: str | None = None) -> Sequence[RuntimeSettingRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_runtime_setting_list(tenant_id=tenant_id))
            settings = list(rows)
        return [runtime_setting_record(row) for row in settings]

    async def delete(self, key: str, *, tenant_id: str = GLOBAL_TENANT_ID) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_runtime_setting_delete(key, tenant_id=tenant_id))


def build_runtime_setting_upsert(update: RuntimeSettingUpdate) -> Any:
    update.validate()
    return (
        insert(RuntimeSetting)
        .values(
            id=new_id("setting"),
            tenant_id=update.tenant_id,
            key=update.key,
            value=update.value,
            value_type=update.value_type,
            category=update.category,
            description=update.description,
            updated_by=update.updated_by,
            setting_metadata=dict(update.metadata),
        )
        .on_conflict_do_update(
            constraint="uq_runtime_settings_key",
            set_={
                "value": update.value,
                "type": update.value_type,
                "category": update.category,
                "description": update.description,
                "updated_by": update.updated_by,
                "metadata": dict(update.metadata),
                "updated_at": func.now(),
            },
        )
        .returning(RuntimeSetting)
    )


def build_runtime_setting_find(key: str, *, tenant_id: str = GLOBAL_TENANT_ID) -> Any:
    RuntimeSettingUpdate(key=key, value="", tenant_id=tenant_id).validate()
    return select(RuntimeSetting).where(
        RuntimeSetting.tenant_id == tenant_id,
        RuntimeSetting.key == key,
    )


def build_runtime_setting_list(*, tenant_id: str | None = None) -> Any:
    statement = select(RuntimeSetting)
    if tenant_id is not None:
        RuntimeSettingUpdate(key="placeholder", value="", tenant_id=tenant_id).validate()
        statement = statement.where(RuntimeSetting.tenant_id == tenant_id)
    return statement.order_by(
        RuntimeSetting.tenant_id.asc(), RuntimeSetting.category.asc(), RuntimeSetting.key.asc()
    )


def build_runtime_setting_delete(key: str, *, tenant_id: str = GLOBAL_TENANT_ID) -> Any:
    RuntimeSettingUpdate(key=key, value="", tenant_id=tenant_id).validate()
    return delete(RuntimeSetting).where(
        RuntimeSetting.tenant_id == tenant_id,
        RuntimeSetting.key == key,
    )


def runtime_setting_record(row: RuntimeSetting) -> RuntimeSettingRecord:
    return RuntimeSettingRecord(
        key=row.key,
        value=row.value,
        value_type=cast(RuntimeSettingType, row.value_type),
        category=row.category,
        tenant_id=row.tenant_id,
        description=row.description,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
        metadata=dict(row.setting_metadata),
    )
