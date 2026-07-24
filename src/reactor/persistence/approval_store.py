from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import func

from reactor.kernel.ids import new_id
from reactor.persistence.models import PendingApproval
from reactor.tools.approval import (
    PENDING_APPROVAL_STATUS,
    ApprovalDecision,
    ApprovalRequest,
)


@dataclass(frozen=True)
class ApprovalRecord:
    id: str
    tenant_id: str
    run_id: str
    tool_id: str
    status: str
    requested_by: str
    decided_by: str | None
    request_payload: dict[str, object]
    decision_reason: str | None
    created_at: datetime | None = None
    decided_at: datetime | None = None


@dataclass(frozen=True)
class PendingApprovalRecord:
    id: str
    tenant_id: str
    run_id: str
    tool_id: str
    status: str
    requested_by: str
    decided_by: str | None
    request_payload: dict[str, Any]
    decision_reason: str | None
    created_at: datetime
    decided_at: datetime | None

    def validate(self) -> None:
        for field_name, value in (
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("run_id", self.run_id),
            ("tool_id", self.tool_id),
            ("status", self.status),
            ("requested_by", self.requested_by),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")


class SqlAlchemyApprovalStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def request_approval(self, request: ApprovalRequest) -> str:
        request.validate()
        approval_id = new_id("approval")
        async with self._session_factory() as session:
            async with session.begin():
                session.add(
                    PendingApproval(
                        id=approval_id,
                        tenant_id=request.tenant_id,
                        run_id=request.run_id,
                        tool_id=request.tool_id,
                        status=PENDING_APPROVAL_STATUS,
                        requested_by=request.requested_by,
                        request_payload=dict(request.request_payload),
                    )
                )
        return approval_id

    async def decide_approval(self, decision: ApprovalDecision) -> bool:
        decision.validate()
        statement = (
            update(PendingApproval)
            .where(
                PendingApproval.id == decision.approval_id,
                PendingApproval.tenant_id == decision.tenant_id,
                PendingApproval.status == PENDING_APPROVAL_STATUS,
            )
            .values(
                status=decision.status,
                decided_by=decision.decided_by,
                decision_reason=decision.reason,
                decided_at=func.now(),
            )
            .returning(PendingApproval.id)
        )
        async with self._session_factory() as session:
            async with session.begin():
                approval_id = await session.scalar(statement)
        return approval_id is not None

    async def save(self, record: PendingApprovalRecord) -> PendingApprovalRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_pending_approval_record_upsert(record))
        return record

    async def find_approval(
        self,
        *,
        tenant_id: str,
        approval_id: str,
    ) -> ApprovalRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(PendingApproval).where(
                    PendingApproval.tenant_id == tenant_id,
                    PendingApproval.id == approval_id,
                )
            )
        if row is None:
            return None
        return approval_record(row)

    async def list_pending(self, tenant_id: str, limit: int = 50) -> Sequence[ApprovalRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(PendingApproval)
                .where(
                    PendingApproval.tenant_id == tenant_id,
                    PendingApproval.status == PENDING_APPROVAL_STATUS,
                )
                .order_by(PendingApproval.created_at.asc())
                .limit(limit)
            )
            return [approval_record(row) for row in rows]

    async def list_approvals(
        self,
        tenant_id: str,
        limit: int = 50,
        status: str | None = None,
    ) -> Sequence[ApprovalRecord]:
        query = select(PendingApproval).where(PendingApproval.tenant_id == tenant_id)
        if status is not None:
            query = query.where(PendingApproval.status == status)
        async with self._session_factory() as session:
            rows = await session.scalars(
                query.order_by(PendingApproval.created_at.desc()).limit(limit)
            )
            return [approval_record(row) for row in rows]


def approval_record(row: PendingApproval) -> ApprovalRecord:
    return ApprovalRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        tool_id=row.tool_id,
        status=row.status,
        requested_by=row.requested_by,
        decided_by=row.decided_by,
        request_payload=dict(row.request_payload),
        decision_reason=row.decision_reason,
        created_at=row.created_at,
        decided_at=row.decided_at,
    )


def build_pending_approval_record_upsert(record: PendingApprovalRecord):
    values = {
        "id": record.id,
        "tenant_id": record.tenant_id,
        "run_id": record.run_id,
        "tool_id": record.tool_id,
        "status": record.status,
        "requested_by": record.requested_by,
        "decided_by": record.decided_by,
        "request_payload": record.request_payload,
        "decision_reason": record.decision_reason,
        "created_at": record.created_at,
        "decided_at": record.decided_at,
    }
    return (
        insert(PendingApproval)
        .values(values)
        .on_conflict_do_update(
            index_elements=[PendingApproval.id],
            set_={
                "status": record.status,
                "decided_by": record.decided_by,
                "request_payload": record.request_payload,
                "decision_reason": record.decision_reason,
                "decided_at": record.decided_at,
            },
        )
    )
