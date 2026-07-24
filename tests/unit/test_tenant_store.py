from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from reactor.admin.tenants import TenantPlan, TenantRecord, TenantStatus, default_quota_for
from reactor.persistence.models import Base
from reactor.persistence.tenant_store import build_tenant_list, build_tenant_upsert

NOW = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)


def test_tenant_model_is_registered_in_metadata() -> None:
    assert "tenants" in Base.metadata.tables
    table = Base.metadata.tables["tenants"]
    indexes = {index.name for index in table.indexes}

    assert "ix_tenants_slug" in indexes
    assert "ix_tenants_status" in indexes
    assert "uq_tenants_slug" in {constraint.name for constraint in table.constraints}


def test_tenant_store_queries_are_postgres_compatible() -> None:
    tenant = TenantRecord(
        id="tenant_1",
        name="Acme",
        slug="acme",
        plan=TenantPlan.BUSINESS,
        quota=default_quota_for(TenantPlan.BUSINESS),
        created_at=NOW,
        updated_at=NOW,
    )

    upsert = str(build_tenant_upsert(tenant).compile(dialect=postgresql.dialect()))
    active_list = build_tenant_list(TenantStatus.ACTIVE).compile(dialect=postgresql.dialect())
    all_list = str(build_tenant_list().compile(dialect=postgresql.dialect()))

    assert "tenants" in upsert
    assert "ON CONFLICT" in upsert
    assert active_list.params["status_1"] == "ACTIVE"
    assert "WHERE tenants.status" in str(active_list)
    assert "WHERE tenants.status" not in all_list
