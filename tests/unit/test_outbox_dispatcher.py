from __future__ import annotations

from collections.abc import Mapping

from reactor.jobs.durable import OutboxLease
from reactor.workers.outbox_dispatcher import OutboxDispatcher, OutboxWorkerRegistry


async def test_outbox_dispatcher_routes_slack_event_command_and_faq_ingest() -> None:
    store = RecordingOutboxStore(
        leases=[
            outbox_lease("outbox_1", "slack.events", "slack.event_callback"),
            outbox_lease("outbox_2", "slack.commands", "slack.slash_command"),
            outbox_lease("outbox_3", "slack.faq_ingest", "slack.channel_faq_ingest"),
            outbox_lease("outbox_4", "slack.interactions", "slack.block_action"),
        ]
    )
    event_worker = RecordingPayloadWorker()
    command_worker = RecordingPayloadWorker()
    faq_worker = RecordingPayloadWorker()
    interaction_worker = RecordingPayloadWorker()
    dispatcher = OutboxDispatcher(
        store=store,
        registry=OutboxWorkerRegistry(
            slack_event_worker=event_worker,
            slack_command_worker=command_worker,
            slack_faq_ingest_worker=faq_worker,
            slack_interaction_worker=interaction_worker,
        ),
    )

    result = await dispatcher.dispatch_once(
        tenant_id="tenant_1",
        lease_owner="worker_1",
        limit=10,
    )

    assert result.claimed == 4
    assert result.dispatched == 4
    assert result.failed == 0
    assert event_worker.payloads == [("tenant_1", {"entrypoint": "events_api"})]
    assert command_worker.payloads == [("tenant_1", {"entrypoint": "events_api"})]
    assert faq_worker.payloads == [("tenant_1", {"entrypoint": "events_api"})]
    assert interaction_worker.payloads == [("tenant_1", {"entrypoint": "events_api"})]
    assert store.marked_dispatched == [
        ("outbox_1", "worker_1"),
        ("outbox_2", "worker_1"),
        ("outbox_3", "worker_1"),
        ("outbox_4", "worker_1"),
    ]
    assert store.marked_failed == []


async def test_outbox_dispatcher_marks_retryable_then_dead_letter() -> None:
    store = RecordingOutboxStore(
        leases=[
            outbox_lease(
                "outbox_1",
                "slack.events",
                "slack.event_callback",
                attempt=1,
                max_attempts=2,
            ),
            outbox_lease(
                "outbox_2",
                "slack.events",
                "slack.event_callback",
                attempt=2,
                max_attempts=2,
            ),
        ]
    )
    dispatcher = OutboxDispatcher(
        store=store,
        registry=OutboxWorkerRegistry(slack_event_worker=RaisingPayloadWorker()),
    )

    result = await dispatcher.dispatch_once(
        tenant_id="tenant_1",
        lease_owner="worker_1",
        limit=10,
    )

    assert result.claimed == 2
    assert result.dispatched == 0
    assert result.failed == 2
    assert store.marked_failed == [
        (
            "outbox_1",
            "worker_1",
            "retryable_failed",
            "worker_dispatch_failed",
            None,
        ),
        (
            "outbox_2",
            "worker_1",
            "dead_lettered",
            "worker_dispatch_failed",
            None,
        ),
    ]


async def test_outbox_dispatcher_preserves_worker_retry_after_seconds() -> None:
    store = RecordingOutboxStore(
        leases=[
            outbox_lease(
                "outbox_1",
                "slack.events",
                "slack.event_callback",
                attempt=1,
                max_attempts=2,
            )
        ]
    )
    dispatcher = OutboxDispatcher(
        store=store,
        registry=OutboxWorkerRegistry(slack_event_worker=RateLimitedPayloadWorker()),
    )

    result = await dispatcher.dispatch_once(
        tenant_id="tenant_1",
        lease_owner="worker_1",
        limit=10,
    )

    assert result.failed == 1
    assert store.marked_failed == [
        ("outbox_1", "worker_1", "retryable_failed", "rate_limited", 7),
    ]


async def test_outbox_dispatcher_marks_unsupported_destination_dead_letter() -> None:
    store = RecordingOutboxStore(leases=[outbox_lease("outbox_1", "unknown", "unknown.event")])
    dispatcher = OutboxDispatcher(store=store, registry=OutboxWorkerRegistry())

    result = await dispatcher.dispatch_once(
        tenant_id="tenant_1",
        lease_owner="worker_1",
        limit=10,
    )

    assert result.failed == 1
    assert store.marked_failed == [
        (
            "outbox_1",
            "worker_1",
            "dead_lettered",
            "Unsupported outbox route: unknown/unknown.event",
            None,
        )
    ]


class RecordingOutboxStore:
    def __init__(self, *, leases: list[OutboxLease]) -> None:
        self._leases = leases
        self.claims: list[tuple[str, str, int]] = []
        self.marked_dispatched: list[tuple[str, str]] = []
        self.marked_failed: list[tuple[str, str, str, str, int | None]] = []

    async def claim_outbox(
        self,
        *,
        tenant_id: str,
        lease_owner: str,
        limit: int,
    ) -> list[OutboxLease]:
        self.claims.append((tenant_id, lease_owner, limit))
        return self._leases

    async def mark_outbox_dispatched(self, *, event_id: str, lease_owner: str) -> None:
        self.marked_dispatched.append((event_id, lease_owner))

    async def mark_outbox_failed(
        self,
        *,
        event_id: str,
        lease_owner: str,
        status: str,
        error: str,
        retry_after_seconds: int | None = None,
    ) -> None:
        self.marked_failed.append((event_id, lease_owner, status, error, retry_after_seconds))


class RecordingPayloadWorker:
    def __init__(self) -> None:
        self.payloads: list[tuple[str, Mapping[str, object]]] = []

    async def handle_outbox_payload(
        self,
        payload: Mapping[str, object],
        *,
        tenant_id: str,
    ) -> None:
        self.payloads.append((tenant_id, payload))


class RaisingPayloadWorker:
    async def handle_outbox_payload(
        self,
        payload: Mapping[str, object],
        *,
        tenant_id: str,
    ) -> None:
        del payload, tenant_id
        raise RuntimeError("worker failed: private-storage-detail")


class RateLimitedPayloadWorker:
    async def handle_outbox_payload(
        self,
        payload: Mapping[str, object],
        *,
        tenant_id: str,
    ) -> None:
        del payload, tenant_id
        raise RateLimitedError("rate_limited", retry_after_seconds=7)


class RateLimitedError(RuntimeError):
    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def outbox_lease(
    event_id: str,
    destination: str,
    event_type: str,
    *,
    attempt: int = 1,
    max_attempts: int = 5,
) -> OutboxLease:
    return OutboxLease(
        event_id=event_id,
        tenant_id="tenant_1",
        destination=destination,
        event_type=event_type,
        attempt=attempt,
        max_attempts=max_attempts,
        payload={"entrypoint": "events_api"},
    )
