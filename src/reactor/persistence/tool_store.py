from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.kernel.ids import new_id
from reactor.persistence.models import ToolCatalog
from reactor.tools.catalog import ToolSpec


@dataclass(frozen=True)
class ToolRecord:
    id: str
    qualified_name: str
    description: str
    risk_level: str
    enabled: bool
    requires_approval: bool
    timeout_ms: int


@dataclass(frozen=True)
class ToolCatalogRecord:
    id: str
    tenant_id: str
    namespace: str
    name: str
    description: str
    risk_level: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    enabled: bool
    requires_approval: bool
    timeout_ms: int
    created_at: datetime
    updated_at: datetime

    def validate(self) -> None:
        ToolSpec(
            tenant_id=self.tenant_id,
            namespace=self.namespace,
            name=self.name,
            description=self.description,
            risk_level=self.risk_level,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
            enabled=self.enabled,
            requires_approval=self.requires_approval,
            timeout_ms=self.timeout_ms,
        ).validate()
        if not self.id.strip():
            raise ValueError("id is required")


class SqlAlchemyToolStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def upsert_tool(self, spec: ToolSpec) -> str:
        spec.validate()
        tool_id = new_id("tool")
        statement = (
            insert(ToolCatalog)
            .values(
                id=tool_id,
                tenant_id=spec.tenant_id,
                namespace=spec.namespace,
                name=spec.name,
                description=spec.description,
                risk_level=spec.risk_level,
                input_schema=dict(spec.input_schema),
                output_schema=dict(spec.output_schema),
                enabled=spec.enabled,
                requires_approval=spec.approval_required,
                timeout_ms=spec.timeout_ms,
            )
            .on_conflict_do_update(
                constraint="uq_tool_catalog_name",
                set_={
                    "description": spec.description,
                    "risk_level": spec.risk_level,
                    "input_schema": dict(spec.input_schema),
                    "output_schema": dict(spec.output_schema),
                    "enabled": spec.enabled,
                    "requires_approval": spec.approval_required,
                    "timeout_ms": spec.timeout_ms,
                },
            )
            .returning(ToolCatalog.id)
        )
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.scalar(statement)
        return result or tool_id

    async def save(self, record: ToolCatalogRecord) -> ToolCatalogRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_tool_catalog_record_upsert(record))
        return record

    async def list_catalog(self, *, tenant_id: str) -> Sequence[ToolCatalogRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(ToolCatalog)
                .where(ToolCatalog.tenant_id == tenant_id)
                .order_by(ToolCatalog.namespace.asc(), ToolCatalog.name.asc())
            )
            return [tool_catalog_record(row) for row in rows]

    async def find_catalog(
        self,
        *,
        tenant_id: str,
        namespace: str,
        name: str,
    ) -> ToolCatalogRecord | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ToolCatalog).where(
                    ToolCatalog.tenant_id == tenant_id,
                    ToolCatalog.namespace == namespace,
                    ToolCatalog.name == name,
                )
            )
            row = result.scalar_one_or_none()
        return tool_catalog_record(row) if row is not None else None

    async def list_enabled_tools(self, tenant_id: str) -> Sequence[ToolRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(ToolCatalog)
                .where(ToolCatalog.tenant_id == tenant_id, ToolCatalog.enabled.is_(True))
                .order_by(ToolCatalog.namespace.asc(), ToolCatalog.name.asc())
            )
            return [
                ToolRecord(
                    id=row.id,
                    qualified_name=f"{row.namespace}:{row.name}",
                    description=row.description,
                    risk_level=row.risk_level,
                    enabled=row.enabled,
                    requires_approval=row.requires_approval,
                    timeout_ms=row.timeout_ms,
                )
                for row in rows
            ]

    async def list_enabled_tool_specs(self, tenant_id: str) -> Sequence[ToolSpec]:
        records = await self.list_catalog(tenant_id=tenant_id)
        return [
            ToolSpec(
                tenant_id=record.tenant_id,
                namespace=record.namespace,
                name=record.name,
                description=record.description,
                risk_level=record.risk_level,
                input_schema=record.input_schema,
                output_schema=record.output_schema,
                enabled=record.enabled,
                requires_approval=record.requires_approval,
                timeout_ms=record.timeout_ms,
                catalog_id=record.id,
            )
            for record in records
            if record.enabled
        ]


def tool_catalog_record(row: ToolCatalog) -> ToolCatalogRecord:
    return ToolCatalogRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        namespace=row.namespace,
        name=row.name,
        description=row.description,
        risk_level=row.risk_level,
        input_schema=dict(row.input_schema),
        output_schema=dict(row.output_schema),
        enabled=row.enabled,
        requires_approval=row.requires_approval,
        timeout_ms=row.timeout_ms,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def build_tool_catalog_record_upsert(record: ToolCatalogRecord):
    return (
        insert(ToolCatalog)
        .values(
            id=record.id,
            tenant_id=record.tenant_id,
            namespace=record.namespace,
            name=record.name,
            description=record.description,
            risk_level=record.risk_level,
            input_schema=record.input_schema,
            output_schema=record.output_schema,
            enabled=record.enabled,
            requires_approval=record.requires_approval,
            timeout_ms=record.timeout_ms,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        .on_conflict_do_update(
            constraint="uq_tool_catalog_name",
            set_={
                "description": record.description,
                "risk_level": record.risk_level,
                "input_schema": record.input_schema,
                "output_schema": record.output_schema,
                "enabled": record.enabled,
                "requires_approval": record.requires_approval,
                "timeout_ms": record.timeout_ms,
                "updated_at": record.updated_at,
            },
        )
    )
