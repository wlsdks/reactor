from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.persistence.models import AdminAudit


class SqlAlchemyAdminAuditStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(
        self,
        *,
        tenant_id: str,
        limit: int = 100,
        category: str | None = None,
        action: str | None = None,
    ) -> list[AdminAuditLog]:
        conditions = [AdminAudit.tenant_id == tenant_id]
        category_filter = category.strip().lower() if category and category.strip() else None
        action_filter = action.strip().upper() if action and action.strip() else None
        if category_filter is not None:
            conditions.append(func.lower(AdminAudit.category) == category_filter)
        if action_filter is not None:
            conditions.append(func.upper(AdminAudit.action) == action_filter)
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(AdminAudit)
                .where(*conditions)
                .order_by(AdminAudit.created_at.desc())
                .limit(max(1, min(limit, 1000)))
            )
            return [admin_audit_from_model(row) for row in rows]

    async def save(self, log: AdminAuditLog, *, tenant_id: str) -> AdminAuditLog:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    insert(AdminAudit)
                    .values(admin_audit_values(log, tenant_id=tenant_id))
                    .returning(AdminAudit)
                )
                if row is None:
                    raise RuntimeError("admin audit insert did not return a row")
                return admin_audit_from_model(row)

    async def find_by_id(self, *, tenant_id: str, audit_id: str) -> AdminAuditLog | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(AdminAudit).where(
                    AdminAudit.tenant_id == tenant_id,
                    AdminAudit.id == audit_id,
                )
            )
            return admin_audit_from_model(row) if row is not None else None


def admin_audit_values(log: AdminAuditLog, *, tenant_id: str) -> dict[str, object]:
    return {
        "id": log.id,
        "tenant_id": tenant_id,
        "category": log.category,
        "action": log.action.value,
        "actor": log.actor,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "detail": log.detail,
        "created_at": log.created_at,
    }


def admin_audit_from_model(row: AdminAudit) -> AdminAuditLog:
    return AdminAuditLog(
        id=row.id,
        category=row.category,
        action=AdminAuditAction(row.action),
        actor=row.actor,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        detail=row.detail,
        created_at=row.created_at,
    )
