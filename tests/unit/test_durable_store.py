from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from reactor.jobs.durable import (
    OutboxLease,
    OutboxRequest,
    RunQueueLease,
    build_claim_outbox_query,
    build_claim_queue_query,
    build_dead_letter_expired_run_queue_statement,
    build_durable_queue_diagnostics_query,
    build_retry_expired_run_queue_statement,
    dead_letter_job_from_expired_run_queue,
)
from reactor.persistence.models import RunQueue


def test_outbox_request_defaults_are_retryable_and_not_bound_to_run() -> None:
    request = OutboxRequest(
        tenant_id="tenant_1",
        destination="webhook",
        event_type="example.sent",
        idempotency_key="tenant_1:webhook:1",
        payload={"ok": True},
    )

    assert request.run_id is None
    assert request.max_attempts == 5
    assert request.payload == {"ok": True}


def test_claim_queue_query_uses_skip_locked() -> None:
    query = build_claim_queue_query("tenant_1", limit=3)

    compiled = str(query.compile(dialect=postgresql.dialect()))

    assert "FOR UPDATE SKIP LOCKED" in compiled
    assert "run_queue.status IN" in compiled
    assert "ORDER BY run_queue.priority ASC" in compiled
    assert "LIMIT" in compiled


def test_durable_queue_diagnostics_query_counts_queue_and_dead_letters() -> None:
    query = build_durable_queue_diagnostics_query("tenant_1")

    compiled = str(query.compile(dialect=postgresql.dialect()))

    assert "FROM run_queue" in compiled
    assert "dead_letter_jobs" in compiled
    assert "tenant_1" not in compiled
    assert "queue_status" in compiled
    assert "dead_letter_count" in compiled


def test_claim_outbox_query_uses_retryable_statuses_and_skip_locked() -> None:
    query = build_claim_outbox_query("tenant_1", limit=10)

    compiled = str(query.compile(dialect=postgresql.dialect()))

    assert "FOR UPDATE SKIP LOCKED" in compiled
    assert "outbox_events.status IN" in compiled
    assert "outbox_events.available_at <=" in compiled
    assert "outbox_events.status = " in compiled
    assert "outbox_events.lease_expires_at <=" in compiled
    assert "ORDER BY outbox_events.available_at ASC" in compiled
    assert "LIMIT" in compiled


def test_expired_run_queue_release_dead_letters_exhausted_attempts() -> None:
    retry_statement = build_retry_expired_run_queue_statement("tenant_1")
    dead_letter_statement = build_dead_letter_expired_run_queue_statement("tenant_1")

    retry_sql = str(retry_statement.compile(dialect=postgresql.dialect()))
    dead_letter_sql = str(dead_letter_statement.compile(dialect=postgresql.dialect()))

    assert "run_queue.attempt < run_queue.max_attempts" in retry_sql
    assert retry_statement.compile(dialect=postgresql.dialect()).params["status"] == (
        "retryable_failed"
    )
    assert "run_queue.attempt >= run_queue.max_attempts" in dead_letter_sql
    assert dead_letter_statement.compile(dialect=postgresql.dialect()).params["status"] == (
        "dead_lettered"
    )


def test_dead_letter_job_from_expired_run_queue_preserves_investigation_context() -> None:
    lease_expires_at = datetime(2026, 7, 1, 12, 30, tzinfo=UTC)
    queue = RunQueue(
        id="queue_1",
        run_id="run_1",
        tenant_id="tenant_1",
        status="leased",
        attempt=3,
        max_attempts=3,
        lease_owner="worker_1",
        lease_expires_at=lease_expires_at,
        fencing_token=7,
        payload={"kind": "agent_run", "checkpointId": "checkpoint_1", "traceId": "trace_1"},
    )

    dead_letter = dead_letter_job_from_expired_run_queue(queue)

    assert dead_letter.queue_id == "queue_1"
    assert dead_letter.run_id == "run_1"
    assert dead_letter.tenant_id == "tenant_1"
    assert dead_letter.reason == "run_queue_lease_attempts_exhausted"
    assert dead_letter.last_checkpoint_id == "checkpoint_1"
    assert dead_letter.trace_id == "trace_1"
    assert dead_letter.payload == {
        "attempt": 3,
        "maxAttempts": 3,
        "leaseOwner": "worker_1",
        "leaseExpiresAt": "2026-07-01T12:30:00+00:00",
        "fencingToken": 7,
        "queuePayload": {
            "kind": "agent_run",
            "checkpointId": "checkpoint_1",
            "traceId": "trace_1",
        },
    }


def test_outbox_lease_carries_event_routing_contract() -> None:
    lease = OutboxLease(
        event_id="outbox_1",
        tenant_id="tenant_1",
        destination="slack.events",
        event_type="slack.event_callback",
        attempt=1,
        max_attempts=5,
        payload={"entrypoint": "events_api"},
    )

    assert lease.destination == "slack.events"
    assert lease.event_type == "slack.event_callback"
    assert lease.payload["entrypoint"] == "events_api"


def test_run_queue_lease_carries_fencing_token_and_payload() -> None:
    expires_at = datetime.now().astimezone()
    lease = RunQueueLease(
        queue_id="queue_1",
        run_id="run_1",
        tenant_id="tenant_1",
        lease_owner="worker_1",
        fencing_token=3,
        lease_expires_at=expires_at,
        payload={"kind": "agent_run"},
    )

    assert lease.fencing_token == 3
    assert lease.lease_expires_at == expires_at
    assert lease.payload["kind"] == "agent_run"
