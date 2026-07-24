from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.persistence.models import ToolInvocation

TOOL_INVOCATION_STATUSES = frozenset(
    {
        "started",
        "succeeded",
        "failed",
        "requires_reconciliation",
        "cancelled",
    }
)


@dataclass(frozen=True)
class ToolInvocationRecord:
    id: str
    tenant_id: str
    run_id: str
    tool_id: str
    approval_id: str | None
    status: str
    idempotency_key: str
    request_checksum: str
    result_checksum: str | None
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None
    error_payload: dict[str, Any] | None
    started_at: datetime
    completed_at: datetime | None

    def validate(self) -> None:
        for field_name, value in (
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("run_id", self.run_id),
            ("tool_id", self.tool_id),
            ("status", self.status),
            ("idempotency_key", self.idempotency_key),
            ("request_checksum", self.request_checksum),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")
        if self.status not in TOOL_INVOCATION_STATUSES:
            allowed = ", ".join(sorted(TOOL_INVOCATION_STATUSES))
            raise ValueError(f"status must be one of: {allowed}")
        if self.status == "succeeded" and self.output_payload is None:
            raise ValueError("output_payload is required for succeeded tool invocations")
        if self.status == "failed" and self.error_payload is None:
            raise ValueError("error_payload is required for failed tool invocations")


@dataclass(frozen=True)
class ToolInvocationClaim:
    claimed: bool
    record: ToolInvocationRecord


class SqlAlchemyToolInvocationStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def claim(self, record: ToolInvocationRecord) -> ToolInvocationClaim:
        record.validate()
        if record.status != "started":
            raise ValueError("tool invocation claim status must be started")
        async with self._session_factory() as session:
            async with session.begin():
                claimed_id = await session.scalar(build_tool_invocation_claim_insert(record))
                if claimed_id is not None:
                    return ToolInvocationClaim(claimed=True, record=record)
                if record.approval_id is not None:
                    rebound_row = await session.scalar(
                        build_approved_pending_tool_invocation_claim_update(record)
                    )
                    if rebound_row is not None:
                        return ToolInvocationClaim(
                            claimed=True,
                            record=tool_invocation_from_row(rebound_row),
                        )
                row = await session.scalar(
                    build_tool_invocation_idempotency_query(
                        tenant_id=record.tenant_id,
                        idempotency_key=record.idempotency_key,
                    )
                )
        if row is None:
            raise RuntimeError("tool invocation claim conflict record is unavailable")
        return ToolInvocationClaim(claimed=False, record=tool_invocation_from_row(row))

    async def save(self, record: ToolInvocationRecord) -> ToolInvocationRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_tool_invocation_record_upsert(record))
        return record

    async def list_between(
        self,
        *,
        tenant_id: str,
        from_time: datetime,
        to_time: datetime,
        limit: int = 500,
        status: str | None = None,
    ) -> list[ToolInvocationRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                build_tool_invocation_list_query(
                    tenant_id=tenant_id,
                    from_time=from_time,
                    to_time=to_time,
                    limit=limit,
                    status=status,
                )
            )
        return [tool_invocation_from_row(row) for row in rows]

    async def mark_stale_started_for_reconciliation(
        self,
        *,
        tenant_id: str,
        older_than: datetime,
        limit: int = 100,
    ) -> list[str]:
        async with self._session_factory() as session:
            async with session.begin():
                invocation_ids = await session.scalars(
                    build_stale_tool_invocation_reconciliation_update(
                        tenant_id=tenant_id,
                        older_than=older_than,
                        limit=limit,
                    )
                )
                return list(invocation_ids)

    async def list_for_run(
        self,
        *,
        tenant_id: str,
        run_id: str,
        limit: int = 100,
        status: str | None = None,
    ) -> list[ToolInvocationRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                build_tool_invocation_run_query(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    limit=limit,
                    status=status,
                )
            )
        return [tool_invocation_from_row(row) for row in rows]


def build_tool_invocation_run_query(
    *,
    tenant_id: str,
    run_id: str,
    limit: int = 100,
    status: str | None = None,
) -> Select[tuple[ToolInvocation]]:
    conditions = [
        ToolInvocation.tenant_id == tenant_id,
        ToolInvocation.run_id == run_id,
    ]
    if status is not None and status.strip():
        normalized_status = status.strip()
        validate_tool_invocation_status(normalized_status)
        conditions.append(ToolInvocation.status == normalized_status)
    return (
        select(ToolInvocation)
        .where(*conditions)
        .order_by(ToolInvocation.started_at.asc(), ToolInvocation.id.asc())
        .limit(max(1, min(limit, 1000)))
    )


def build_tool_invocation_list_query(
    *,
    tenant_id: str,
    from_time: datetime,
    to_time: datetime,
    limit: int = 500,
    status: str | None = None,
) -> Select[tuple[ToolInvocation]]:
    conditions = [
        ToolInvocation.tenant_id == tenant_id,
        ToolInvocation.started_at >= from_time,
        ToolInvocation.started_at < to_time,
    ]
    if status is not None and status.strip():
        normalized_status = status.strip()
        validate_tool_invocation_status(normalized_status)
        conditions.append(ToolInvocation.status == normalized_status)
    return (
        select(ToolInvocation)
        .where(*conditions)
        .order_by(ToolInvocation.started_at.asc(), ToolInvocation.id.asc())
        .limit(max(0, min(limit, 5000)))
    )


def validate_tool_invocation_status(status: str) -> str:
    normalized_status = status.strip()
    if normalized_status not in TOOL_INVOCATION_STATUSES:
        allowed = ", ".join(sorted(TOOL_INVOCATION_STATUSES))
        raise ValueError(f"status must be one of: {allowed}")
    return normalized_status


def build_tool_invocation_record_upsert(record: ToolInvocationRecord):
    values = tool_invocation_record_values(record)
    return (
        insert(ToolInvocation)
        .values(values)
        .on_conflict_do_update(
            constraint="uq_tool_invocations_idempotency",
            set_={
                "approval_id": record.approval_id,
                "status": record.status,
                "result_checksum": record.result_checksum,
                "input_payload": record.input_payload,
                "output_payload": record.output_payload,
                "error_payload": record.error_payload,
                "completed_at": record.completed_at,
            },
        )
    )


def build_tool_invocation_claim_insert(record: ToolInvocationRecord):
    values = tool_invocation_record_values(record)
    return (
        insert(ToolInvocation)
        .values(values)
        .on_conflict_do_nothing(constraint="uq_tool_invocations_idempotency")
        .returning(ToolInvocation.id)
    )


def build_approved_pending_tool_invocation_claim_update(record: ToolInvocationRecord):
    if record.approval_id is None:
        raise ValueError("approval_id is required to claim a pending approval invocation")
    return (
        update(ToolInvocation)
        .where(
            ToolInvocation.tenant_id == record.tenant_id,
            ToolInvocation.idempotency_key == record.idempotency_key,
            ToolInvocation.status == "started",
            ToolInvocation.approval_id.is_(None),
            ToolInvocation.request_checksum == record.request_checksum,
            ToolInvocation.error_payload["error"]["code"].as_string() == "approval_required",
        )
        .values(
            approval_id=record.approval_id,
            input_payload=record.input_payload,
            error_payload=None,
        )
        .returning(ToolInvocation)
    )


def build_tool_invocation_idempotency_query(
    *,
    tenant_id: str,
    idempotency_key: str,
) -> Select[tuple[ToolInvocation]]:
    return select(ToolInvocation).where(
        ToolInvocation.tenant_id == tenant_id,
        ToolInvocation.idempotency_key == idempotency_key,
    )


def build_stale_tool_invocation_reconciliation_update(
    *,
    tenant_id: str,
    older_than: datetime,
    limit: int = 100,
):
    candidates = (
        select(ToolInvocation.id)
        .where(
            ToolInvocation.tenant_id == tenant_id,
            ToolInvocation.status == "started",
            ToolInvocation.started_at < older_than,
        )
        .order_by(ToolInvocation.started_at.asc(), ToolInvocation.id.asc())
        .limit(max(1, min(limit, 500)))
    )
    return (
        update(ToolInvocation)
        .where(
            ToolInvocation.id.in_(candidates),
            ToolInvocation.tenant_id == tenant_id,
            ToolInvocation.status == "started",
            ToolInvocation.started_at < older_than,
        )
        .values(
            status="requires_reconciliation",
            error_payload={
                "error": {
                    "code": "stale_started_claim",
                    "message": "tool invocation outcome requires operator reconciliation",
                }
            },
            completed_at=func.now(),
        )
        .returning(ToolInvocation.id)
    )


def tool_invocation_record_values(record: ToolInvocationRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "tenant_id": record.tenant_id,
        "run_id": record.run_id,
        "tool_id": record.tool_id,
        "approval_id": record.approval_id,
        "status": record.status,
        "idempotency_key": record.idempotency_key,
        "request_checksum": record.request_checksum,
        "result_checksum": record.result_checksum,
        "input_payload": record.input_payload,
        "output_payload": record.output_payload,
        "error_payload": record.error_payload,
        "started_at": record.started_at,
        "completed_at": record.completed_at,
    }


def tool_invocation_from_row(row: ToolInvocation) -> ToolInvocationRecord:
    return ToolInvocationRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        tool_id=row.tool_id,
        approval_id=row.approval_id,
        status=row.status,
        idempotency_key=row.idempotency_key,
        request_checksum=row.request_checksum,
        result_checksum=row.result_checksum,
        input_payload=row.input_payload,
        output_payload=row.output_payload,
        error_payload=row.error_payload,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )
