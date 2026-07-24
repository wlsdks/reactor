from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.dialects import postgresql

from reactor.persistence.models import ToolInvocation
from reactor.persistence.tool_invocation_store import (
    ToolInvocationRecord,
    build_approved_pending_tool_invocation_claim_update,
    build_stale_tool_invocation_reconciliation_update,
    build_tool_invocation_claim_insert,
    build_tool_invocation_idempotency_query,
    build_tool_invocation_record_upsert,
)

NOW = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)


def test_tool_invocation_claim_insert_is_conflict_safe() -> None:
    statement = build_tool_invocation_claim_insert(
        ToolInvocationRecord(
            id="tool_invocation_1",
            tenant_id="tenant_1",
            run_id="run_1",
            tool_id="builtin:search",
            approval_id=None,
            status="started",
            idempotency_key="tool:tenant_1:run_1:builtin:search:digest",
            request_checksum="sha256:request",
            result_checksum=None,
            input_payload={"executed": False},
            output_payload=None,
            error_payload=None,
            started_at=NOW,
            completed_at=None,
        )
    )

    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "ON CONFLICT ON CONSTRAINT uq_tool_invocations_idempotency DO NOTHING" in sql
    assert "RETURNING tool_invocations.id" in sql


def test_tool_invocation_idempotency_query_is_tenant_scoped() -> None:
    statement = build_tool_invocation_idempotency_query(
        tenant_id="tenant_1",
        idempotency_key="tool:tenant_1:run_1:builtin:search:digest",
    )

    compiled = statement.compile()
    sql = str(compiled)

    assert "tool_invocations.tenant_id =" in sql
    assert "tool_invocations.idempotency_key =" in sql
    assert compiled.params["tenant_id_1"] == "tenant_1"
    assert compiled.params["idempotency_key_1"].endswith(":digest")


def test_approved_pending_tool_invocation_claim_is_atomic_and_provenance_bound() -> None:
    statement = build_approved_pending_tool_invocation_claim_update(
        ToolInvocationRecord(
            id="tool_invocation_new_claim",
            tenant_id="tenant_1",
            run_id="run_1",
            tool_id="builtin:send_webhook",
            approval_id="approval_1",
            status="started",
            idempotency_key="tool:tenant_1:run_1:builtin:send_webhook:digest",
            request_checksum="sha256:request",
            result_checksum=None,
            input_payload={"approvalRequired": True, "executed": False},
            output_payload=None,
            error_payload=None,
            started_at=NOW,
            completed_at=None,
        )
    )

    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "UPDATE tool_invocations SET" in sql
    assert "tool_invocations.tenant_id =" in sql
    assert "tool_invocations.idempotency_key =" in sql
    assert "tool_invocations.status =" in sql
    assert "tool_invocations.approval_id IS NULL" in sql
    assert "tool_invocations.request_checksum =" in sql
    assert "approval_required" in compiled.params.values()
    assert "RETURNING tool_invocations.id" in sql
    assert compiled.params["approval_id"] == "approval_1"


def test_approved_pending_tool_invocation_claim_requires_approval_id() -> None:
    with pytest.raises(ValueError, match="approval_id is required"):
        build_approved_pending_tool_invocation_claim_update(
            ToolInvocationRecord(
                id="tool_invocation_1",
                tenant_id="tenant_1",
                run_id="run_1",
                tool_id="builtin:send_webhook",
                approval_id=None,
                status="started",
                idempotency_key="tool:tenant_1:run_1:builtin:send_webhook:digest",
                request_checksum="sha256:request",
                result_checksum=None,
                input_payload={"approvalRequired": True, "executed": False},
                output_payload=None,
                error_payload=None,
                started_at=NOW,
                completed_at=None,
            )
        )


def test_stale_started_reconciliation_update_is_tenant_scoped_and_bounded() -> None:
    statement = build_stale_tool_invocation_reconciliation_update(
        tenant_id="tenant_1",
        older_than=NOW,
        limit=25,
    )

    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "tool_invocations.tenant_id =" in sql
    assert "tool_invocations.status =" in sql
    assert "tool_invocations.started_at <" in sql
    assert "ORDER BY tool_invocations.started_at ASC, tool_invocations.id ASC" in sql
    assert "LIMIT" in sql
    assert "requires_reconciliation" in compiled.params.values()
    assert "RETURNING tool_invocations.id" in sql


def test_tool_invocation_dashboard_query_is_tenant_and_time_scoped() -> None:
    from reactor.persistence.tool_invocation_store import SqlAlchemyToolInvocationStore

    statement = (
        ToolInvocation.__table__.select()
        .where(
            ToolInvocation.tenant_id == "tenant_1",
            ToolInvocation.started_at >= NOW - timedelta(days=1),
            ToolInvocation.started_at < NOW,
        )
        .order_by(ToolInvocation.started_at.asc(), ToolInvocation.id.asc())
        .limit(500)
    )

    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert SqlAlchemyToolInvocationStore is not None
    assert "FROM tool_invocations" in sql
    assert "tool_invocations.tenant_id" in sql
    assert "ORDER BY tool_invocations.started_at ASC, tool_invocations.id ASC" in sql
    assert compiled.params["tenant_id_1"] == "tenant_1"


def test_tool_invocation_dashboard_query_filters_by_status() -> None:
    from reactor.persistence.tool_invocation_store import build_tool_invocation_list_query

    statement = build_tool_invocation_list_query(
        tenant_id="tenant_1",
        from_time=NOW - timedelta(days=1),
        to_time=NOW,
        limit=500,
        status="requires_reconciliation",
    )

    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "tool_invocations.status" in sql
    assert compiled.params["status_1"] == "requires_reconciliation"


def test_tool_invocation_dashboard_query_rejects_invalid_status_filter() -> None:
    from reactor.persistence.tool_invocation_store import build_tool_invocation_list_query

    with pytest.raises(ValueError, match="status must be one of"):
        build_tool_invocation_list_query(
            tenant_id="tenant_1",
            from_time=NOW - timedelta(days=1),
            to_time=NOW,
            limit=500,
            status="pending",
        )


def test_tool_invocation_run_query_is_tenant_and_run_scoped() -> None:
    from reactor.persistence.tool_invocation_store import SqlAlchemyToolInvocationStore

    statement = (
        ToolInvocation.__table__.select()
        .where(
            ToolInvocation.tenant_id == "tenant_1",
            ToolInvocation.run_id == "run_1",
        )
        .order_by(ToolInvocation.started_at.asc(), ToolInvocation.id.asc())
        .limit(100)
    )

    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert SqlAlchemyToolInvocationStore is not None
    assert "FROM tool_invocations" in sql
    assert "tool_invocations.tenant_id" in sql
    assert "tool_invocations.run_id" in sql
    assert "ORDER BY tool_invocations.started_at ASC, tool_invocations.id ASC" in sql
    assert compiled.params["tenant_id_1"] == "tenant_1"
    assert compiled.params["run_id_1"] == "run_1"


def test_tool_invocation_run_query_filters_by_status() -> None:
    from reactor.persistence.tool_invocation_store import build_tool_invocation_run_query

    statement = build_tool_invocation_run_query(
        tenant_id="tenant_1",
        run_id="run_1",
        limit=100,
        status="failed",
    )

    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "tool_invocations.run_id" in sql
    assert "tool_invocations.status" in sql
    assert compiled.params["tenant_id_1"] == "tenant_1"
    assert compiled.params["run_id_1"] == "run_1"
    assert compiled.params["status_1"] == "failed"


def test_tool_invocation_upsert_advances_lifecycle_by_idempotency_key() -> None:
    statement = build_tool_invocation_record_upsert(
        ToolInvocationRecord(
            id="tool_invocation_approved",
            tenant_id="tenant_1",
            run_id="run_1",
            tool_id="builtin:send_webhook",
            approval_id="approval_1",
            status="succeeded",
            idempotency_key="tool:tenant_1:run_1:builtin:send_webhook:digest",
            request_checksum="sha256:request",
            result_checksum="sha256:result",
            input_payload={"executed": True},
            output_payload={"ok": True},
            error_payload=None,
            started_at=NOW + timedelta(minutes=5),
            completed_at=NOW + timedelta(minutes=6),
        )
    )

    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "ON CONFLICT ON CONSTRAINT uq_tool_invocations_idempotency DO UPDATE" in sql
    assert "approval_id = %(param_1)s" in sql
    assert "status = %(param_2)s" in sql
    assert "result_checksum = %(param_3)s" in sql
    assert "input_payload = %(param_4)s" in sql
    assert "output_payload = %(param_5)s" in sql
    assert "error_payload = %(param_6)s" in sql
    assert "completed_at = %(param_7)s" in sql
    update_clause = sql.split("DO UPDATE SET", 1)[1]
    assert "started_at =" not in update_clause
    assert "request_checksum =" not in update_clause
    assert " id =" not in update_clause
    assert update_clause.lstrip().startswith("approval_id =")
    assert compiled.params["approval_id"] == "approval_1"
    assert compiled.params["status"] == "succeeded"
    assert compiled.params["idempotency_key"] == "tool:tenant_1:run_1:builtin:send_webhook:digest"


def test_tool_invocation_record_rejects_status_outside_database_contract() -> None:
    record = ToolInvocationRecord(
        id="tool_invocation_1",
        tenant_id="tenant_1",
        run_id="run_1",
        tool_id="builtin:send_webhook",
        approval_id=None,
        status="pending_approval",
        idempotency_key="tool:tenant_1:run_1:builtin:send_webhook:digest",
        request_checksum="sha256:request",
        result_checksum=None,
        input_payload={},
        output_payload=None,
        error_payload=None,
        started_at=NOW,
        completed_at=None,
    )

    with pytest.raises(ValueError, match="status must be one of"):
        record.validate()


def test_tool_invocation_record_rejects_succeeded_without_output_payload() -> None:
    record = ToolInvocationRecord(
        id="tool_invocation_1",
        tenant_id="tenant_1",
        run_id="run_1",
        tool_id="builtin:send_webhook",
        approval_id=None,
        status="succeeded",
        idempotency_key="tool:tenant_1:run_1:builtin:send_webhook:digest",
        request_checksum="sha256:request",
        result_checksum="sha256:result",
        input_payload={},
        output_payload=None,
        error_payload=None,
        started_at=NOW,
        completed_at=NOW,
    )

    with pytest.raises(ValueError, match="output_payload is required for succeeded"):
        record.validate()


def test_tool_invocation_record_rejects_failed_without_error_payload() -> None:
    record = ToolInvocationRecord(
        id="tool_invocation_1",
        tenant_id="tenant_1",
        run_id="run_1",
        tool_id="builtin:send_webhook",
        approval_id=None,
        status="failed",
        idempotency_key="tool:tenant_1:run_1:builtin:send_webhook:digest",
        request_checksum="sha256:request",
        result_checksum="sha256:result",
        input_payload={},
        output_payload=None,
        error_payload=None,
        started_at=NOW,
        completed_at=NOW,
    )

    with pytest.raises(ValueError, match="error_payload is required for failed"):
        record.validate()
