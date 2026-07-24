from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from reactor.kernel.ids import new_id

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")


class TenantPlan(StrEnum):
    FREE = "FREE"
    STARTER = "STARTER"
    BUSINESS = "BUSINESS"
    ENTERPRISE = "ENTERPRISE"


class TenantStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DEACTIVATED = "DEACTIVATED"


@dataclass(frozen=True)
class TenantQuota:
    max_requests_per_month: int = 1_000
    max_tokens_per_month: int = 1_000_000
    max_users: int = 5
    max_agents: int = 3
    max_mcp_servers: int = 5


def empty_metadata() -> dict[str, object]:
    return {}


@dataclass(frozen=True)
class TenantRecord:
    name: str
    slug: str
    id: str = field(default_factory=lambda: new_id("tenant"))
    plan: TenantPlan = TenantPlan.FREE
    status: TenantStatus = TenantStatus.ACTIVE
    quota: TenantQuota = field(default_factory=TenantQuota)
    billing_cycle_start: int = 1
    billing_email: str | None = None
    slo_availability: float = 0.995
    slo_latency_p99_ms: int = 10_000
    metadata: dict[str, object] = field(default_factory=empty_metadata)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class TenantStore(Protocol):
    async def find_by_id(self, tenant_id: str) -> TenantRecord | None: ...

    async def find_by_slug(self, slug: str) -> TenantRecord | None: ...

    async def find_all(self, status: TenantStatus | None = None) -> list[TenantRecord]: ...

    async def save(self, tenant: TenantRecord) -> TenantRecord: ...

    async def delete(self, tenant_id: str) -> bool: ...


def default_quota_for(plan: TenantPlan) -> TenantQuota:
    match plan:
        case TenantPlan.FREE:
            return TenantQuota()
        case TenantPlan.STARTER:
            return TenantQuota(
                max_requests_per_month=10_000,
                max_tokens_per_month=10_000_000,
                max_users=20,
                max_agents=10,
                max_mcp_servers=10,
            )
        case TenantPlan.BUSINESS:
            return TenantQuota(
                max_requests_per_month=100_000,
                max_tokens_per_month=100_000_000,
                max_users=100,
                max_agents=50,
                max_mcp_servers=30,
            )
        case TenantPlan.ENTERPRISE:
            return TenantQuota(
                max_requests_per_month=9_223_372_036_854_775_807,
                max_tokens_per_month=9_223_372_036_854_775_807,
                max_users=2_147_483_647,
                max_agents=2_147_483_647,
                max_mcp_servers=2_147_483_647,
            )


def parse_tenant_plan(raw_plan: str) -> TenantPlan | None:
    normalized = raw_plan.strip().upper()
    try:
        return TenantPlan(normalized)
    except ValueError:
        return None


async def create_tenant(
    store: TenantStore,
    *,
    name: str,
    slug: str,
    plan: TenantPlan,
    billing_email: str | None = None,
) -> TenantRecord:
    normalized_name = name.strip()
    normalized_slug = slug.strip()
    if not normalized_name:
        raise ValueError("tenant name is required")
    if not SLUG_PATTERN.fullmatch(normalized_slug):
        raise ValueError("invalid tenant slug")
    if await store.find_by_slug(normalized_slug) is not None:
        raise ValueError(f"tenant slug already exists: {normalized_slug}")
    tenant = TenantRecord(
        name=normalized_name,
        slug=normalized_slug,
        plan=plan,
        quota=default_quota_for(plan),
        billing_email=billing_email.strip() if billing_email else None,
    )
    return await store.save(tenant)


async def suspend_tenant(store: TenantStore, tenant_id: str) -> TenantRecord:
    return await update_tenant_status(store, tenant_id, TenantStatus.SUSPENDED)


async def activate_tenant(store: TenantStore, tenant_id: str) -> TenantRecord:
    return await update_tenant_status(store, tenant_id, TenantStatus.ACTIVE)


async def update_tenant_status(
    store: TenantStore,
    tenant_id: str,
    status: TenantStatus,
) -> TenantRecord:
    tenant = await store.find_by_id(tenant_id)
    if tenant is None:
        raise LookupError(f"Tenant not found: {tenant_id}")
    return await store.save(replace(tenant, status=status, updated_at=datetime.now(UTC)))
