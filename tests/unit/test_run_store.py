from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from sqlalchemy.dialects import postgresql

from reactor.persistence.run_store import (
    RunCompletionEvent,
    SqlAlchemyRunStore,
    build_cancel_active_run_query,
    build_cancel_pending_approval_tool_invocations_query,
    build_cancel_pending_run_approvals_query,
    build_cancel_running_run_query,
    build_claim_interrupted_run_resume_query,
    build_complete_running_run_query,
    build_has_slack_thread_run_query,
    build_list_run_events_query,
    build_next_run_event_sequence_query,
    resume_claim_event_payload,
    run_result_event_type,
)


def test_cancel_active_run_query_allows_running_and_interrupted_only() -> None:
    statement = build_cancel_active_run_query(
        run_id="run_123",
        tenant_id="tenant_1",
        response_text="Run cancelled.",
        metadata={"cancel_reason": "user_requested_cancellation"},
    )

    compiled = statement.compile()
    sql = str(compiled)

    assert "agent_runs.id =" in sql
    assert "agent_runs.tenant_id =" in sql
    assert "agent_runs.status IN" in sql
    assert compiled.params["id_1"] == "run_123"
    assert compiled.params["tenant_id_1"] == "tenant_1"
    assert set(compiled.params["status_1"]) == {"running", "interrupted"}
    assert compiled.params["status"] == "cancelled"


def test_cancel_pending_approval_tool_invocations_query_excludes_executing_claims() -> None:
    statement = build_cancel_pending_approval_tool_invocations_query(
        run_id="run_123",
        tenant_id="tenant_1",
        reason="external_stream_cancellation",
    )

    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "tool_invocations.run_id =" in sql
    assert "tool_invocations.tenant_id =" in sql
    assert "tool_invocations.status =" in sql
    assert "tool_invocations.approval_id IS NULL" in sql
    assert "tool_invocations.error_payload" in sql
    assert compiled.params["run_id_1"] == "run_123"
    assert compiled.params["tenant_id_1"] == "tenant_1"
    assert compiled.params["status_1"] == "started"
    assert "approval_required" in compiled.params.values()
    assert compiled.params["status"] == "cancelled"


def test_cancel_pending_run_approvals_query_is_tenant_and_run_scoped() -> None:
    statement = build_cancel_pending_run_approvals_query(
        run_id="run_123",
        tenant_id="tenant_1",
        cancelled_by="user_1",
        reason="external_stream_cancellation",
    )

    compiled = statement.compile()
    sql = str(compiled)

    assert "pending_approvals.run_id =" in sql
    assert "pending_approvals.tenant_id =" in sql
    assert "pending_approvals.status =" in sql
    assert compiled.params["run_id_1"] == "run_123"
    assert compiled.params["tenant_id_1"] == "tenant_1"
    assert compiled.params["status_1"] == "pending"
    assert compiled.params["status"] == "cancelled"
    assert compiled.params["decided_by"] == "user_1"
    assert compiled.params["decision_reason"] == "external_stream_cancellation"


def test_cancel_running_run_query_is_tenant_scoped_and_atomic() -> None:
    statement = build_cancel_running_run_query(
        run_id="run_123",
        tenant_id="tenant_1",
        response_text="Agent stream cancelled.",
        metadata={"cancel_reason": "external_stream_cancellation"},
    )

    compiled = statement.compile()
    sql = str(compiled)

    assert "agent_runs.id =" in sql
    assert "agent_runs.tenant_id =" in sql
    assert "agent_runs.status =" in sql
    assert "RETURNING agent_runs.id" in sql
    assert compiled.params["id_1"] == "run_123"
    assert compiled.params["tenant_id_1"] == "tenant_1"
    assert compiled.params["status_1"] == "running"
    assert compiled.params["status"] == "cancelled"
    assert compiled.params["response_text"] == "Agent stream cancelled."


def test_claim_interrupted_run_resume_query_is_tenant_scoped_and_atomic() -> None:
    statement = build_claim_interrupted_run_resume_query(
        run_id="run_123",
        tenant_id="tenant_1",
    )

    compiled = statement.compile()
    sql = str(compiled)

    assert "agent_runs.id =" in sql
    assert "agent_runs.tenant_id =" in sql
    assert "agent_runs.status =" in sql
    assert "status=:status" in sql.replace(" ", "")
    assert compiled.params["id_1"] == "run_123"
    assert compiled.params["tenant_id_1"] == "tenant_1"
    assert compiled.params["status_1"] == "interrupted"
    assert compiled.params["status"] == "running"


def test_complete_running_run_query_is_tenant_scoped_and_atomic() -> None:
    statement = build_complete_running_run_query(
        run_id="run_123",
        tenant_id="tenant_1",
        status="completed",
        response_text="done",
        metadata={"runtime": "langgraph"},
    )

    compiled = statement.compile()
    sql = str(compiled)

    assert "agent_runs.id =" in sql
    assert "agent_runs.tenant_id =" in sql
    assert "agent_runs.status =" in sql
    assert "RETURNING agent_runs.id" in sql
    assert compiled.params["id_1"] == "run_123"
    assert compiled.params["tenant_id_1"] == "tenant_1"
    assert compiled.params["status_1"] == "running"
    assert compiled.params["status"] == "completed"
    assert compiled.params["response_text"] == "done"


def test_resume_claim_event_payload_exposes_only_audit_identity() -> None:
    payload = resume_claim_event_payload(
        approval_id="approval_1",
        claimed_by="admin_1",
        runtime="langgraph",
    )

    assert payload == {
        "approval_id": "approval_1",
        "claimed_by": "admin_1",
        "runtime": "langgraph",
    }
    assert "tool_input" not in payload


async def test_claim_interrupted_resume_records_audit_event_in_claim_transaction() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.scalar_results: list[object] = ["run_123", 7]
            self.added: list[object] = []

        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def begin(self) -> FakeSession:
            return self

        async def scalar(self, _statement: object) -> object:
            return self.scalar_results.pop(0)

        def add(self, record: object) -> None:
            self.added.append(record)

    session = FakeSession()
    store = SqlAlchemyRunStore(cast(Any, lambda: session))

    claimed = await store.claim_interrupted_resume(
        run_id="run_123",
        tenant_id="tenant_1",
        approval_id="approval_1",
        claimed_by="admin_1",
        runtime="langgraph",
    )

    assert claimed is True
    assert len(session.added) == 1
    event = cast(Any, session.added[0])
    assert event.run_id == "run_123"
    assert event.tenant_id == "tenant_1"
    assert event.sequence == 7
    assert event.event_type == "run.resume_claimed"
    assert event.payload == {
        "approval_id": "approval_1",
        "claimed_by": "admin_1",
        "runtime": "langgraph",
    }


async def test_record_completed_commits_resume_event_in_terminal_transaction() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.added: list[object] = []
            self.executed: list[object] = []
            self.scalar_results: list[object] = ["run_123", 7]

        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def begin(self) -> FakeSession:
            return self

        async def execute(self, statement: object) -> None:
            self.executed.append(statement)

        async def scalar(self, _statement: object) -> object:
            return self.scalar_results.pop(0)

        def add_all(self, records: list[object]) -> None:
            self.added.extend(records)

    session = FakeSession()
    store = SqlAlchemyRunStore(cast(Any, lambda: session))
    result = SimpleNamespace(
        run_id="run_123",
        tenant_id="tenant_1",
        status="completed",
        response="resumed",
    )

    transitioned = await store.record_completed(
        result=cast(Any, result),
        metadata={"runtime": "langgraph"},
        completion_events=(
            RunCompletionEvent(
                event_type="run.resumed",
                payload={"approval_id": "approval_1", "runtime": "langgraph"},
            ),
        ),
    )

    assert transitioned is True
    assert len(session.added) == 2
    completed_event = cast(Any, session.added[0])
    resumed_event = cast(Any, session.added[1])
    assert (completed_event.sequence, completed_event.event_type, completed_event.payload) == (
        7,
        "run.completed",
        {"status": "completed"},
    )
    assert (resumed_event.sequence, resumed_event.event_type, resumed_event.payload) == (
        8,
        "run.resumed",
        {"approval_id": "approval_1", "runtime": "langgraph"},
    )
    assert len(session.executed) == 1
    assert all("pending_approvals" not in str(statement) for statement in session.executed)


async def test_record_completed_preserves_existing_terminal_state() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.executed: list[object] = []
            self.added: list[object] = []

        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def begin(self) -> FakeSession:
            return self

        async def scalar(self, _statement: object) -> None:
            return None

        async def execute(self, statement: object) -> None:
            self.executed.append(statement)

        def add_all(self, records: list[object]) -> None:
            self.added.extend(records)

    session = FakeSession()
    store = SqlAlchemyRunStore(cast(Any, lambda: session))
    result = SimpleNamespace(
        run_id="run_123",
        tenant_id="tenant_1",
        status="completed",
        response="late completion",
    )

    transitioned = await store.record_completed(
        result=cast(Any, result),
        metadata={"runtime": "langgraph"},
    )

    assert transitioned is False
    assert session.executed == []
    assert session.added == []


async def test_record_cancelled_if_running_commits_event_in_transition_transaction() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.scalar_results: list[object] = ["run_123", 7]
            self.executed: list[object] = []
            self.added: list[object] = []

        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def begin(self) -> FakeSession:
            return self

        async def scalar(self, _statement: object) -> object:
            return self.scalar_results.pop(0)

        async def execute(self, statement: object) -> None:
            self.executed.append(statement)

        def add(self, record: object) -> None:
            self.added.append(record)

    session = FakeSession()
    store = SqlAlchemyRunStore(cast(Any, lambda: session))
    result = SimpleNamespace(
        run_id="run_123",
        tenant_id="tenant_1",
        user_id="user_1",
        status="cancelled",
        response="Agent stream cancelled.",
    )

    transitioned = await store.record_cancelled_if_running(
        result=cast(Any, result),
        metadata={
            "cancelled_by": "user_1",
            "cancel_reason": "external_stream_cancellation",
        },
    )

    assert transitioned is True
    assert len(session.executed) == 3
    assert len(session.added) == 1
    event = cast(Any, session.added[0])
    assert event.run_id == "run_123"
    assert event.tenant_id == "tenant_1"
    assert event.sequence == 7
    assert event.event_type == "run.cancelled"
    assert event.payload == {
        "status": "cancelled",
        "cancelled_by": "user_1",
        "reason": "external_stream_cancellation",
    }


async def test_record_cancelled_if_running_preserves_existing_terminal_state() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.executed: list[object] = []
            self.added: list[object] = []

        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def begin(self) -> FakeSession:
            return self

        async def scalar(self, _statement: object) -> None:
            return None

        async def execute(self, statement: object) -> None:
            self.executed.append(statement)

        def add(self, record: object) -> None:
            self.added.append(record)

    session = FakeSession()
    store = SqlAlchemyRunStore(cast(Any, lambda: session))
    result = SimpleNamespace(
        run_id="run_123",
        tenant_id="tenant_1",
        status="cancelled",
        response="Agent stream cancelled.",
    )

    transitioned = await store.record_cancelled_if_running(
        result=cast(Any, result),
        metadata={"cancel_reason": "external_stream_cancellation"},
    )

    assert transitioned is False
    assert session.executed == []
    assert session.added == []


def test_interrupted_run_records_a_non_terminal_event() -> None:
    assert run_result_event_type("interrupted") == "run.interrupted"
    assert run_result_event_type("completed") == "run.completed"


def test_next_run_event_sequence_query_advances_persisted_history() -> None:
    statement = build_next_run_event_sequence_query(run_id="run_123")

    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "max(agent_run_events.sequence)" in sql
    assert "coalesce" in sql.lower()
    assert compiled.params["run_id_1"] == "run_123"


def test_list_run_events_query_scopes_by_tenant_when_provided() -> None:
    statement = build_list_run_events_query(
        run_id="run_123",
        tenant_id="tenant_1",
        after_sequence=7,
    )

    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "agent_run_events.run_id" in sql
    assert "agent_run_events.tenant_id" in sql
    assert "agent_run_events.sequence >" in sql
    assert compiled.params == {
        "run_id_1": "run_123",
        "tenant_id_1": "tenant_1",
        "sequence_1": 7,
    }


def test_list_run_events_query_allows_unscoped_internal_calls() -> None:
    statement = build_list_run_events_query(
        run_id="run_123",
        tenant_id=None,
        after_sequence=0,
    )

    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "agent_run_events.run_id" in sql
    assert "AND agent_run_events.tenant_id" not in sql
    assert compiled.params == {"run_id_1": "run_123", "sequence_1": 0}


def test_has_slack_thread_run_query_scopes_by_tenant_and_thread_id() -> None:
    statement = build_has_slack_thread_run_query(
        tenant_id="tenant_1",
        thread_id="slack-C1-1710000000.000100",
    )

    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "agent_runs.tenant_id" in sql
    assert "agent_runs.thread_id" in sql
    assert "agent_runs.metadata" in sql
    assert "LIMIT" in sql
    assert compiled.params == {
        "tenant_id_1": "tenant_1",
        "thread_id_1": "slack-C1-1710000000.000100",
        "metadata_1": "source",
        "param_1": "slack",
        "param_2": 1,
    }
