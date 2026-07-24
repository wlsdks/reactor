from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects import postgresql

from reactor.guards.input import InputGuardMetricRecord
from reactor.persistence.input_guard_stats_store import (
    InputGuardMetricMigrationRecord,
    build_input_guard_metric_insert,
    build_input_guard_metric_migration_insert,
    build_input_guard_stage_counts,
    build_input_guard_top_reasons,
    build_input_guard_totals,
)
from reactor.persistence.models import Base

NOW = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)


def test_input_guard_metric_model_and_queries_match_legacy_contract() -> None:
    assert "metric_guard_events" in Base.metadata.tables
    indexes = Base.metadata.tables["metric_guard_events"].indexes
    assert "ix_metric_guard_events_input_time" in {index.name for index in indexes}
    assert "ix_metric_guard_events_tenant_time" in {index.name for index in indexes}

    since = NOW - timedelta(hours=24)
    totals = build_input_guard_totals(since, tenant_id="tenant_1").compile(
        dialect=postgresql.dialect()
    )
    stages = build_input_guard_stage_counts(since, tenant_id="tenant_1").compile(
        dialect=postgresql.dialect()
    )
    reasons = build_input_guard_top_reasons(
        since,
        stage="InjectionDetection",
        tenant_id="tenant_1",
        limit=5,
    ).compile(dialect=postgresql.dialect())

    assert "metric_guard_events" in str(totals)
    assert "is_output_guard IS false" in str(totals)
    assert "GROUP BY metric_guard_events.action" in str(totals)
    assert totals.params["tenant_id_1"] == "tenant_1"
    assert stages.params["tenant_id_1"] == "tenant_1"
    assert "GROUP BY metric_guard_events.stage, metric_guard_events.action" in str(stages)
    assert reasons.params["stage_1"] == "InjectionDetection"
    assert reasons.params["tenant_id_1"] == "tenant_1"
    assert reasons.params["param_1"] == 5
    assert "coalesce(metric_guard_events.reason_class, metric_guard_events.reason_detail)" in str(
        reasons
    )


def test_input_guard_metric_insert_preserves_legacy_guard_event_fields() -> None:
    statement = build_input_guard_metric_insert(
        InputGuardMetricRecord(
            tenant_id="tenant_1",
            user_id="user_1",
            channel="slack",
            stage="InjectionDetection",
            category="prompt_injection",
            reason_class="prompt_injection",
            reason_detail="x" * 600,
            action="rejected",
        )
    ).compile(dialect=postgresql.dialect())

    sql = str(statement)

    assert "INSERT INTO metric_guard_events" in sql
    assert statement.params["tenant_id"] == "tenant_1"
    assert statement.params["user_id"] == "user_1"
    assert statement.params["channel"] == "slack"
    assert statement.params["stage"] == "InjectionDetection"
    assert statement.params["category"] == "prompt_injection"
    assert statement.params["reason_class"] == "prompt_injection"
    assert statement.params["reason_detail"] == "x" * 500
    assert statement.params["is_output_guard"] is False
    assert statement.params["action"] == "rejected"


def test_input_guard_metric_migration_insert_preserves_legacy_time_and_output_flag() -> None:
    statement = build_input_guard_metric_migration_insert(
        InputGuardMetricMigrationRecord(
            time=datetime(2026, 6, 1, 14, 0, tzinfo=UTC),
            tenant_id="tenant_1",
            user_id="user_1",
            channel="slack",
            stage="OutputValidation",
            category="pii",
            reason_class="pii",
            reason_detail="x" * 600,
            is_output_guard=True,
            action="rejected",
        )
    ).compile(dialect=postgresql.dialect())

    assert statement.params["time"] == datetime(2026, 6, 1, 14, 0, tzinfo=UTC)
    assert statement.params["tenant_id"] == "tenant_1"
    assert statement.params["stage"] == "OutputValidation"
    assert statement.params["reason_detail"] == "x" * 500
    assert statement.params["is_output_guard"] is True
