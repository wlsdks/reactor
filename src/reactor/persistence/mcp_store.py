from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.kernel.ids import new_id
from reactor.mcp.registry import McpServerRegistration
from reactor.persistence.models import McpAccessPolicy, McpServer, McpServerStatus, McpToolSnapshot


@dataclass(frozen=True)
class McpServerRecord:
    id: str
    tenant_id: str
    name: str
    transport: str
    status: str
    command: str | None
    args: list[str]
    url: str | None
    auth_type: str
    timeout_ms: int
    reconnect_policy: dict[str, Any]
    protocol_version: str | None = None
    last_connection_error: str | None = None
    tool_snapshot_hash: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class McpServerMigrationRecord:
    id: str
    tenant_id: str
    name: str
    transport: str
    status: str
    command: str | None
    args: list[str]
    url: str | None
    auth_type: str
    timeout_ms: int
    protocol_version: str | None
    last_connection_error: str | None
    reconnect_policy: dict[str, Any]
    tool_snapshot_hash: str | None
    created_at: datetime
    updated_at: datetime

    def validate(self) -> None:
        for field_name, value in (
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("name", self.name),
            ("transport", self.transport),
            ("status", self.status),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")


@dataclass(frozen=True)
class McpServerStatusRecord:
    server_id: str
    tenant_id: str
    status: str
    negotiated_protocol_version: str | None
    last_error: str | None
    reconnect_attempt: int
    backoff_until: datetime | None
    checked_at: datetime

    def validate(self) -> None:
        for field_name, value in (
            ("server_id", self.server_id),
            ("tenant_id", self.tenant_id),
            ("status", self.status),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")


@dataclass(frozen=True)
class McpToolSnapshotRecord:
    id: str
    tenant_id: str
    server_id: str
    qualified_name: str
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_level: str
    enabled: bool
    snapshot_hash: str
    created_at: datetime

    def validate(self) -> None:
        for field_name, value in (
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("server_id", self.server_id),
            ("qualified_name", self.qualified_name),
            ("tool_name", self.tool_name),
            ("description", self.description),
            ("risk_level", self.risk_level),
            ("snapshot_hash", self.snapshot_hash),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")


@dataclass(frozen=True)
class McpAccessPolicyRecord:
    id: str
    tenant_id: str
    server_id: str
    graph_profile: str
    allow_write: bool
    allowed_tools: list[str]
    created_at: datetime

    def validate(self) -> None:
        for field_name, value in (
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("server_id", self.server_id),
            ("graph_profile", self.graph_profile),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")


def build_mcp_status_upsert_statement(
    *,
    server_id: str,
    tenant_id: str,
    status: str,
    negotiated_protocol_version: str | None,
    last_error: str | None,
):
    return (
        insert(McpServerStatus)
        .values(
            server_id=server_id,
            tenant_id=tenant_id,
            status=status,
            negotiated_protocol_version=negotiated_protocol_version,
            last_error=last_error,
        )
        .on_conflict_do_update(
            index_elements=[McpServerStatus.server_id],
            set_={
                "status": status,
                "negotiated_protocol_version": negotiated_protocol_version,
                "last_error": last_error,
                "reconnect_attempt": 0,
            },
        )
    )


def build_mcp_server_record_upsert(record: McpServerMigrationRecord):
    return (
        insert(McpServer)
        .values(
            id=record.id,
            tenant_id=record.tenant_id,
            name=record.name,
            transport=record.transport,
            status=record.status,
            command=record.command,
            args=record.args,
            url=record.url,
            auth_type=record.auth_type,
            timeout_ms=record.timeout_ms,
            protocol_version=record.protocol_version,
            last_connection_error=record.last_connection_error,
            reconnect_policy=record.reconnect_policy,
            tool_snapshot_hash=record.tool_snapshot_hash,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        .on_conflict_do_update(
            constraint="uq_mcp_servers_name",
            set_={
                "transport": record.transport,
                "status": record.status,
                "command": record.command,
                "args": record.args,
                "url": record.url,
                "auth_type": record.auth_type,
                "timeout_ms": record.timeout_ms,
                "protocol_version": record.protocol_version,
                "last_connection_error": record.last_connection_error,
                "reconnect_policy": record.reconnect_policy,
                "tool_snapshot_hash": record.tool_snapshot_hash,
                "updated_at": record.updated_at,
            },
        )
    )


def build_mcp_server_status_record_upsert(record: McpServerStatusRecord):
    return (
        insert(McpServerStatus)
        .values(
            server_id=record.server_id,
            tenant_id=record.tenant_id,
            status=record.status,
            negotiated_protocol_version=record.negotiated_protocol_version,
            last_error=record.last_error,
            reconnect_attempt=record.reconnect_attempt,
            backoff_until=record.backoff_until,
            checked_at=record.checked_at,
        )
        .on_conflict_do_update(
            index_elements=[McpServerStatus.server_id],
            set_={
                "tenant_id": record.tenant_id,
                "status": record.status,
                "negotiated_protocol_version": record.negotiated_protocol_version,
                "last_error": record.last_error,
                "reconnect_attempt": record.reconnect_attempt,
                "backoff_until": record.backoff_until,
                "checked_at": record.checked_at,
            },
        )
    )


def build_mcp_tool_snapshot_record_upsert(record: McpToolSnapshotRecord):
    return (
        insert(McpToolSnapshot)
        .values(
            id=record.id,
            tenant_id=record.tenant_id,
            server_id=record.server_id,
            qualified_name=record.qualified_name,
            tool_name=record.tool_name,
            description=record.description,
            input_schema=record.input_schema,
            output_schema=record.output_schema,
            risk_level=record.risk_level,
            enabled=record.enabled,
            snapshot_hash=record.snapshot_hash,
            created_at=record.created_at,
        )
        .on_conflict_do_update(
            constraint="uq_mcp_tool_snapshots_tool",
            set_={
                "qualified_name": record.qualified_name,
                "description": record.description,
                "input_schema": record.input_schema,
                "output_schema": record.output_schema,
                "risk_level": record.risk_level,
                "enabled": record.enabled,
                "snapshot_hash": record.snapshot_hash,
            },
        )
    )


def build_mcp_access_policy_record_upsert(record: McpAccessPolicyRecord):
    return (
        insert(McpAccessPolicy)
        .values(
            id=record.id,
            tenant_id=record.tenant_id,
            server_id=record.server_id,
            graph_profile=record.graph_profile,
            allow_write=record.allow_write,
            allowed_tools=record.allowed_tools,
            created_at=record.created_at,
        )
        .on_conflict_do_update(
            constraint="uq_mcp_access_policy",
            set_={
                "allow_write": record.allow_write,
                "allowed_tools": record.allowed_tools,
            },
        )
    )


class SqlAlchemyMcpRegistryStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def register_server(self, registration: McpServerRegistration) -> str:
        registration.validate()
        server_id = new_id("mcp")
        statement = (
            insert(McpServer)
            .values(
                id=server_id,
                tenant_id=registration.tenant_id,
                name=registration.name,
                transport=registration.transport,
                status="registered",
                command=registration.command,
                args=list(registration.args),
                url=registration.url,
                auth_type=registration.auth_type,
                timeout_ms=registration.timeout_ms,
                reconnect_policy=dict(registration.reconnect_policy),
            )
            .on_conflict_do_update(
                constraint="uq_mcp_servers_name",
                set_={
                    "transport": registration.transport,
                    "status": "registered",
                    "command": registration.command,
                    "args": list(registration.args),
                    "url": registration.url,
                    "auth_type": registration.auth_type,
                    "timeout_ms": registration.timeout_ms,
                    "reconnect_policy": dict(registration.reconnect_policy),
                    "last_connection_error": None,
                },
            )
            .returning(McpServer.id)
        )
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.scalar(statement)
        return result or server_id

    async def save_server(self, record: McpServerMigrationRecord) -> McpServerMigrationRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_mcp_server_record_upsert(record))
        return record

    async def save_server_status(self, record: McpServerStatusRecord) -> McpServerStatusRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_mcp_server_status_record_upsert(record))
        return record

    async def save_tool_snapshot(self, record: McpToolSnapshotRecord) -> McpToolSnapshotRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_mcp_tool_snapshot_record_upsert(record))
        return record

    async def save_access_policy(self, record: McpAccessPolicyRecord) -> McpAccessPolicyRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_mcp_access_policy_record_upsert(record))
        return record

    async def list_access_policies(
        self,
        *,
        tenant_id: str,
        server_id: str,
    ) -> Sequence[McpAccessPolicyRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(McpAccessPolicy)
                .where(
                    McpAccessPolicy.tenant_id == tenant_id, McpAccessPolicy.server_id == server_id
                )
                .order_by(McpAccessPolicy.graph_profile.asc())
            )
            return [
                McpAccessPolicyRecord(
                    id=row.id,
                    tenant_id=row.tenant_id,
                    server_id=row.server_id,
                    graph_profile=row.graph_profile,
                    allow_write=row.allow_write,
                    allowed_tools=list(row.allowed_tools),
                    created_at=row.created_at,
                )
                for row in rows
            ]

    async def delete_access_policies(self, *, tenant_id: str, server_id: str) -> int:
        statement = (
            delete(McpAccessPolicy)
            .where(McpAccessPolicy.tenant_id == tenant_id, McpAccessPolicy.server_id == server_id)
            .returning(McpAccessPolicy.id)
        )
        async with self._session_factory() as session:
            async with session.begin():
                deleted_ids = list(await session.scalars(statement))
        return len(deleted_ids)

    async def update_server(
        self,
        *,
        tenant_id: str,
        name: str,
        registration: McpServerRegistration,
    ) -> McpServerRecord | None:
        registration.validate()
        statement = (
            update(McpServer)
            .where(McpServer.tenant_id == tenant_id, McpServer.name == name)
            .values(
                transport=registration.transport,
                status="registered",
                command=registration.command,
                args=list(registration.args),
                url=registration.url,
                auth_type=registration.auth_type,
                timeout_ms=registration.timeout_ms,
                reconnect_policy=dict(registration.reconnect_policy),
                last_connection_error=None,
            )
            .returning(McpServer.id)
        )
        async with self._session_factory() as session:
            async with session.begin():
                updated_id = await session.scalar(statement)
        if updated_id is None:
            return None
        return await self.find_server_by_name(tenant_id=tenant_id, name=name)

    async def set_server_status(
        self,
        *,
        tenant_id: str,
        name: str,
        status: str,
    ) -> McpServerRecord | None:
        clear_error = status in {"healthy", "disabled"}
        values: dict[str, Any] = {"status": status}
        if clear_error:
            values["last_connection_error"] = None
        statement = (
            update(McpServer)
            .where(McpServer.tenant_id == tenant_id, McpServer.name == name)
            .values(**values)
            .returning(McpServer.id)
        )
        async with self._session_factory() as session:
            async with session.begin():
                updated_id = await session.scalar(statement)
        if updated_id is None:
            return None
        return await self.find_server_by_name(tenant_id=tenant_id, name=name)

    async def delete_server(self, *, tenant_id: str, name: str) -> bool:
        statement = (
            delete(McpServer)
            .where(McpServer.tenant_id == tenant_id, McpServer.name == name)
            .returning(McpServer.id)
        )
        async with self._session_factory() as session:
            async with session.begin():
                deleted_id = await session.scalar(statement)
        return deleted_id is not None

    async def list_servers(self, tenant_id: str) -> Sequence[McpServerRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(McpServer)
                .where(McpServer.tenant_id == tenant_id)
                .order_by(McpServer.name.asc())
            )
            return [
                McpServerRecord(
                    id=row.id,
                    tenant_id=row.tenant_id,
                    name=row.name,
                    transport=row.transport,
                    status=row.status,
                    command=row.command,
                    args=list(row.args),
                    url=row.url,
                    auth_type=row.auth_type,
                    timeout_ms=row.timeout_ms,
                    reconnect_policy=dict(row.reconnect_policy),
                    protocol_version=row.protocol_version,
                    last_connection_error=row.last_connection_error,
                    tool_snapshot_hash=row.tool_snapshot_hash,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]

    async def find_server_by_name(self, *, tenant_id: str, name: str) -> McpServerRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(McpServer).where(McpServer.tenant_id == tenant_id, McpServer.name == name)
            )
        if row is None:
            return None
        return McpServerRecord(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            transport=row.transport,
            status=row.status,
            command=row.command,
            args=list(row.args),
            url=row.url,
            auth_type=row.auth_type,
            timeout_ms=row.timeout_ms,
            reconnect_policy=dict(row.reconnect_policy),
            protocol_version=row.protocol_version,
            last_connection_error=row.last_connection_error,
            tool_snapshot_hash=row.tool_snapshot_hash,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def record_preflight(
        self,
        *,
        server_id: str,
        tenant_id: str,
        status: str,
        negotiated_protocol_version: str | None,
        last_error: str | None,
    ) -> None:
        statement = build_mcp_status_upsert_statement(
            server_id=server_id,
            tenant_id=tenant_id,
            status=status,
            negotiated_protocol_version=negotiated_protocol_version,
            last_error=last_error,
        )
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(statement)
                await session.execute(
                    update(McpServer)
                    .where(McpServer.id == server_id, McpServer.tenant_id == tenant_id)
                    .values(
                        status=status,
                        protocol_version=negotiated_protocol_version,
                        last_connection_error=last_error,
                    )
                )

    async def update_tool_snapshot_hash(
        self,
        *,
        server_id: str,
        tenant_id: str,
        snapshot_hash: str,
    ) -> bool:
        statement = (
            update(McpServer)
            .where(McpServer.id == server_id, McpServer.tenant_id == tenant_id)
            .values(tool_snapshot_hash=snapshot_hash)
            .returning(McpServer.id)
        )
        async with self._session_factory() as session:
            async with session.begin():
                updated_id = await session.scalar(statement)
        return updated_id is not None
