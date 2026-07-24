from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from reactor.persistence.durable_store import OutboxLease


class OutboxStore(Protocol):
    async def claim_outbox(
        self,
        *,
        tenant_id: str,
        lease_owner: str,
        limit: int,
    ) -> list[OutboxLease]: ...

    async def mark_outbox_dispatched(self, *, event_id: str, lease_owner: str) -> None: ...

    async def mark_outbox_failed(
        self,
        *,
        event_id: str,
        lease_owner: str,
        status: str,
        error: str,
        retry_after_seconds: int | None = None,
    ) -> None: ...


class OutboxPayloadWorker(Protocol):
    async def handle_outbox_payload(
        self,
        payload: Mapping[str, object],
        *,
        tenant_id: str,
    ) -> object: ...


@dataclass(frozen=True)
class OutboxWorkerRegistry:
    slack_event_worker: OutboxPayloadWorker | None = None
    slack_command_worker: OutboxPayloadWorker | None = None
    slack_faq_ingest_worker: OutboxPayloadWorker | None = None
    slack_interaction_worker: OutboxPayloadWorker | None = None

    def resolve(self, lease: OutboxLease) -> OutboxPayloadWorker | None:
        route = (lease.destination, lease.event_type)
        if route == ("slack.events", "slack.event_callback"):
            return self.slack_event_worker
        if route == ("slack.commands", "slack.slash_command"):
            return self.slack_command_worker
        if route == ("slack.faq_ingest", "slack.channel_faq_ingest"):
            return self.slack_faq_ingest_worker
        if route == ("slack.interactions", "slack.block_action"):
            return self.slack_interaction_worker
        return None


@dataclass(frozen=True)
class OutboxDispatchResult:
    claimed: int
    dispatched: int
    failed: int


class OutboxDispatcher:
    def __init__(self, *, store: OutboxStore, registry: OutboxWorkerRegistry) -> None:
        self._store = store
        self._registry = registry

    async def dispatch_once(
        self,
        *,
        tenant_id: str,
        lease_owner: str,
        limit: int = 10,
    ) -> OutboxDispatchResult:
        leases = await self._store.claim_outbox(
            tenant_id=tenant_id,
            lease_owner=lease_owner,
            limit=limit,
        )
        dispatched = 0
        failed = 0
        for lease in leases:
            worker = self._registry.resolve(lease)
            if worker is None:
                failed += 1
                await self._store.mark_outbox_failed(
                    event_id=lease.event_id,
                    lease_owner=lease_owner,
                    status="dead_lettered",
                    error=unsupported_route_error(lease),
                )
                continue
            try:
                await worker.handle_outbox_payload(lease.payload, tenant_id=lease.tenant_id)
            except Exception as error:
                failed += 1
                retry_after = retry_after_seconds(error)
                await self._store.mark_outbox_failed(
                    event_id=lease.event_id,
                    lease_owner=lease_owner,
                    status=failure_status(lease),
                    error="rate_limited" if retry_after is not None else "worker_dispatch_failed",
                    retry_after_seconds=retry_after,
                )
                continue
            dispatched += 1
            await self._store.mark_outbox_dispatched(
                event_id=lease.event_id,
                lease_owner=lease_owner,
            )
        return OutboxDispatchResult(
            claimed=len(leases),
            dispatched=dispatched,
            failed=failed,
        )


def failure_status(lease: OutboxLease) -> str:
    return "dead_lettered" if lease.attempt >= lease.max_attempts else "retryable_failed"


def unsupported_route_error(lease: OutboxLease) -> str:
    return f"Unsupported outbox route: {lease.destination}/{lease.event_type}"


def retry_after_seconds(error: Exception) -> int | None:
    value = getattr(error, "retry_after_seconds", None)
    return value if isinstance(value, int) and value >= 0 else None
