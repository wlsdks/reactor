from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from reactor.observability.alerts import AlertInstance, AlertRule, AlertSeverity, AlertStatus
from reactor.persistence.alert_store import (
    build_alert_active_list,
    build_alert_resolve,
    build_alert_rule_delete,
    build_alert_rule_list,
    build_alert_rule_upsert,
    build_alert_save,
)
from reactor.persistence.models import Base

NOW = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)


def test_alert_models_are_registered_in_metadata() -> None:
    assert "alert_rules" in Base.metadata.tables
    assert "alert_instances" in Base.metadata.tables
    rule_indexes = Base.metadata.tables["alert_rules"].indexes
    alert_indexes = Base.metadata.tables["alert_instances"].indexes

    assert "ix_alert_rules_tenant_enabled" in {index.name for index in rule_indexes}
    assert "ix_alert_instances_status" in {index.name for index in alert_indexes}


def test_alert_store_queries_are_postgres_compatible_and_scope_active_alerts() -> None:
    rule = AlertRule(
        id="rule_1",
        tenant_id="tenant_1",
        name="High error rate",
        metric="error_rate",
        threshold=0.05,
        severity=AlertSeverity.CRITICAL,
        created_at=NOW,
    )
    alert = AlertInstance(
        id="alert_1",
        rule_id="rule_1",
        tenant_id="tenant_1",
        severity=AlertSeverity.CRITICAL,
        message="High error rate",
        metric_value=0.12,
        threshold=0.05,
        fired_at=NOW,
    )

    upsert = str(build_alert_rule_upsert(rule).compile(dialect=postgresql.dialect()))
    listed = build_alert_rule_list().compile(dialect=postgresql.dialect())
    delete = build_alert_rule_delete("rule_1", tenant_id="tenant_1").compile(
        dialect=postgresql.dialect()
    )
    save_alert = str(build_alert_save(alert).compile(dialect=postgresql.dialect()))
    active = build_alert_active_list(tenant_id="tenant_1").compile(dialect=postgresql.dialect())
    resolved = build_alert_resolve(
        "alert_1",
        tenant_id="tenant_1",
        actor="admin_1",
        at=NOW,
    ).compile(dialect=postgresql.dialect())

    assert "alert_rules" in upsert
    assert "ON CONFLICT" in upsert
    assert "ORDER BY alert_rules.created_at" in str(listed)
    assert delete.params["id_1"] == "rule_1"
    assert delete.params["tenant_id_1"] == "tenant_1"
    assert "alert_rules.tenant_id" in str(delete)
    assert "alert_instances" in save_alert
    assert active.params["status_1"] == AlertStatus.ACTIVE.value
    assert active.params["tenant_id_1"] == "tenant_1"
    assert "alert_instances.tenant_id" in str(active)
    assert resolved.params["tenant_id_1"] == "tenant_1"
    assert "alert_instances.tenant_id" in str(resolved)
    assert resolved.params["status"] == AlertStatus.RESOLVED.value
    assert resolved.params["acknowledged_by"] == "admin_1"
