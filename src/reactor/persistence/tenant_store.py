from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.admin.tenants import TenantPlan, TenantQuota, TenantRecord, TenantStatus
from reactor.persistence.models import Tenant as TenantRow


class SqlAlchemyTenantStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find_by_id(self, tenant_id: str) -> TenantRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(select(TenantRow).where(TenantRow.id == tenant_id))
        return tenant_from_row(row) if row is not None else None

    async def find_by_slug(self, slug: str) -> TenantRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(select(TenantRow).where(TenantRow.slug == slug))
        return tenant_from_row(row) if row is not None else None

    async def find_all(self, status: TenantStatus | None = None) -> list[TenantRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_tenant_list(status))
        return [tenant_from_row(row) for row in rows]

    async def save(self, tenant: TenantRecord) -> TenantRecord:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(build_tenant_upsert(tenant))
                if row is None:
                    raise RuntimeError("tenant upsert did not return a row")
        return tenant_from_row(row)

    async def delete(self, tenant_id: str) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                deleted_id = await session.scalar(
                    delete(TenantRow).where(TenantRow.id == tenant_id).returning(TenantRow.id)
                )
        return deleted_id is not None


def build_tenant_list(status: TenantStatus | None = None) -> Any:
    query = select(TenantRow)
    if status is not None:
        query = query.where(TenantRow.status == status.value)
    return query.order_by(TenantRow.created_at.desc())


def build_tenant_upsert(tenant: TenantRecord) -> Any:
    values = tenant_values(tenant)
    return (
        insert(TenantRow)
        .values(values)
        .on_conflict_do_update(index_elements=[TenantRow.id], set_=values)
        .returning(TenantRow)
    )


def tenant_values(tenant: TenantRecord) -> dict[object, object]:
    return {
        TenantRow.id: tenant.id,
        TenantRow.name: tenant.name,
        TenantRow.slug: tenant.slug,
        TenantRow.plan: tenant.plan.value,
        TenantRow.status: tenant.status.value,
        TenantRow.max_requests_per_month: tenant.quota.max_requests_per_month,
        TenantRow.max_tokens_per_month: tenant.quota.max_tokens_per_month,
        TenantRow.max_users: tenant.quota.max_users,
        TenantRow.max_agents: tenant.quota.max_agents,
        TenantRow.max_mcp_servers: tenant.quota.max_mcp_servers,
        TenantRow.billing_cycle_start: tenant.billing_cycle_start,
        TenantRow.billing_email: tenant.billing_email,
        TenantRow.slo_availability: tenant.slo_availability,
        TenantRow.slo_latency_p99_ms: tenant.slo_latency_p99_ms,
        TenantRow.tenant_metadata: tenant.metadata,
        TenantRow.created_at: tenant.created_at,
        TenantRow.updated_at: tenant.updated_at,
    }


def tenant_from_row(row: TenantRow) -> TenantRecord:
    return TenantRecord(
        id=row.id,
        name=row.name,
        slug=row.slug,
        plan=TenantPlan(row.plan),
        status=TenantStatus(row.status),
        quota=TenantQuota(
            max_requests_per_month=row.max_requests_per_month,
            max_tokens_per_month=row.max_tokens_per_month,
            max_users=row.max_users,
            max_agents=row.max_agents,
            max_mcp_servers=row.max_mcp_servers,
        ),
        billing_cycle_start=row.billing_cycle_start,
        billing_email=row.billing_email,
        slo_availability=row.slo_availability,
        slo_latency_p99_ms=row.slo_latency_p99_ms,
        metadata=dict(row.tenant_metadata),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
