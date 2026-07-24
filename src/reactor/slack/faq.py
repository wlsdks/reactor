from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from time import time


class AutoReplyMode(StrEnum):
    MENTION = "mention"
    ALWAYS = "always"
    OFF = "off"


class IngestStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    OK = "ok"
    FAILED = "failed"


class FaqOutcome(StrEnum):
    HIT = "hit"
    SKIP_NOT_REGISTERED = "skip_not_registered"
    SKIP_DISABLED = "skip_disabled"
    SKIP_MODE = "skip_mode"
    SKIP_COOLDOWN = "skip_cooldown"
    SKIP_CONFIDENCE = "skip_confidence"
    SKIP_EMPTY = "skip_empty"
    SKIP_VECTORSTORE_UNAVAILABLE = "skip_vectorstore_unavailable"
    ERROR = "error"


@dataclass(frozen=True)
class FaqEvent:
    timestamp: int
    outcome: str
    score: float | None = None
    query: str | None = None
    matched_document_id: str | None = None


@dataclass(frozen=True)
class FaqDocFeedback:
    doc_id: str
    thumbs_up: int
    thumbs_down: int

    @property
    def total(self) -> int:
        return self.thumbs_up + self.thumbs_down

    @property
    def negative_ratio(self) -> float:
        if self.total == 0:
            return 0.0
        return self.thumbs_down / self.total


@dataclass(frozen=True)
class ChannelFaqStats:
    hits: int = 0
    skips_by_reason: dict[str, int] = field(default_factory=lambda: {})
    errors: int = 0
    last_hit_at: int | None = None
    avg_hit_score: float | None = None

    @property
    def total(self) -> int:
        return self.hits + self.errors + sum(self.skips_by_reason.values())

    @property
    def hit_ratio(self) -> float:
        if self.total == 0:
            return 0.0
        return self.hits / self.total


@dataclass
class _ChannelFaqCounter:
    hits: int = 0
    skips_by_reason: dict[str, int] = field(default_factory=lambda: {})
    errors: int = 0
    last_hit_at: int | None = None
    hit_score_sum: float = 0.0

    def record(self, outcome: FaqOutcome, *, score: float | None, timestamp: int) -> None:
        if outcome == FaqOutcome.HIT:
            self.hits += 1
            self.last_hit_at = timestamp
            self.hit_score_sum += score if score is not None else 0.0
            return
        if outcome == FaqOutcome.ERROR:
            self.errors += 1
            return
        self.skips_by_reason[outcome.value] = self.skips_by_reason.get(outcome.value, 0) + 1

    def to_stats(self) -> ChannelFaqStats:
        return ChannelFaqStats(
            hits=self.hits,
            skips_by_reason=dict(sorted(self.skips_by_reason.items())),
            errors=self.errors,
            last_hit_at=self.last_hit_at,
            avg_hit_score=(self.hit_score_sum / self.hits) if self.hits else None,
        )


class InMemorySlackFaqMetrics:
    def __init__(
        self,
        *,
        clock_millis: Callable[[], int] | None = None,
        recent_limit: int = 50,
    ) -> None:
        self._clock_millis = clock_millis or (lambda: int(time() * 1000))
        self._recent_limit = recent_limit
        self._per_channel: dict[str, _ChannelFaqCounter] = {}
        self._overall = _ChannelFaqCounter()
        self._recent_events: dict[str, list[FaqEvent]] = {}
        self._feedback: dict[str, dict[str, FaqDocFeedback]] = {}
        self._reply_docs: OrderedDict[tuple[str, str], list[str]] = OrderedDict()
        self._feedback_events: OrderedDict[str, None] = OrderedDict()

    def record_feedback(
        self,
        channel_id: str,
        doc_ids: list[str],
        rating: bool,
        *,
        event_id: str | None = None,
    ) -> None:
        if event_id is not None:
            if event_id in self._feedback_events:
                self._feedback_events.move_to_end(event_id)
                return
            self._feedback_events[event_id] = None
            while len(self._feedback_events) > self._recent_limit:
                self._feedback_events.popitem(last=False)
        channel_feedback = self._feedback.setdefault(channel_id, {})
        for doc_id in doc_ids:
            current = channel_feedback.get(doc_id) or FaqDocFeedback(
                doc_id=doc_id,
                thumbs_up=0,
                thumbs_down=0,
            )
            channel_feedback[doc_id] = FaqDocFeedback(
                doc_id=doc_id,
                thumbs_up=current.thumbs_up + (1 if rating else 0),
                thumbs_down=current.thumbs_down + (0 if rating else 1),
            )

    def feedback_snapshot(self, channel_id: str) -> dict[str, FaqDocFeedback]:
        return dict(sorted(self._feedback.get(channel_id, {}).items()))

    def track_reply(self, channel_id: str, message_ts: str, doc_ids: list[str]) -> None:
        if doc_ids:
            key = (channel_id, message_ts)
            self._reply_docs[key] = list(doc_ids)
            self._reply_docs.move_to_end(key)
            while len(self._reply_docs) > self._recent_limit:
                self._reply_docs.popitem(last=False)

    def doc_ids_for_reply(self, channel_id: str, message_ts: str) -> list[str]:
        return list(self._reply_docs.get((channel_id, message_ts), []))

    def record_outcome(
        self,
        channel_id: str,
        outcome: FaqOutcome,
        *,
        score: float | None = None,
        query: str | None = None,
        matched_document_id: str | None = None,
    ) -> None:
        timestamp = self._clock_millis()
        counter = self._per_channel.setdefault(channel_id, _ChannelFaqCounter())
        counter.record(outcome, score=score, timestamp=timestamp)
        self._overall.record(outcome, score=score, timestamp=timestamp)
        event = FaqEvent(
            timestamp=timestamp,
            outcome=outcome.value,
            score=score,
            query=query[:200] if query is not None else None,
            matched_document_id=matched_document_id,
        )
        events = self._recent_events.setdefault(channel_id, [])
        events.insert(0, event)
        del events[self._recent_limit :]

    def snapshot(self, channel_id: str) -> ChannelFaqStats:
        return self._per_channel.get(channel_id, _ChannelFaqCounter()).to_stats()

    def overall_snapshot(self) -> ChannelFaqStats:
        return self._overall.to_stats()

    def recent_events(self, channel_id: str, *, limit: int = 50) -> list[FaqEvent]:
        clamped = max(1, min(limit, self._recent_limit))
        return list(self._recent_events.get(channel_id, [])[:clamped])

    def reset(self) -> None:
        self._per_channel.clear()
        self._overall = _ChannelFaqCounter()
        self._recent_events.clear()
        self._feedback.clear()
        self._reply_docs.clear()
        self._feedback_events.clear()


@dataclass(frozen=True)
class ChannelFaqRegistration:
    tenant_id: str
    channel_id: str
    channel_name: str | None = None
    enabled: bool = True
    auto_reply_mode: AutoReplyMode = AutoReplyMode.MENTION
    confidence_threshold: float = 0.75
    days_back: int = 30
    re_ingest_interval_hours: int = 24
    last_ingested_at: datetime | None = None
    last_message_count: int | None = None
    last_chunk_count: int | None = None
    last_status: str = IngestStatus.PENDING.value
    last_error: str | None = None
    registered_by: str | None = None
    registered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not self.channel_id.strip():
            raise ValueError("channel_id is required")
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0.0 and 1.0")
        if not 1 <= self.re_ingest_interval_hours <= 720:
            raise ValueError("re_ingest_interval_hours must be between 1 and 720")
        if not 1 <= self.days_back <= 365:
            raise ValueError("days_back must be between 1 and 365")


@dataclass(frozen=True)
class RegistrationOptions:
    channel_name: str | None = None
    enabled: bool = True
    auto_reply_mode: AutoReplyMode = AutoReplyMode.MENTION
    confidence_threshold: float = 0.75
    days_back: int = 30
    re_ingest_interval_hours: int = 24


@dataclass(frozen=True)
class RegistrationPatch:
    channel_name: str | None = None
    enabled: bool | None = None
    auto_reply_mode: AutoReplyMode | None = None
    confidence_threshold: float | None = None
    days_back: int | None = None
    re_ingest_interval_hours: int | None = None


class InMemoryChannelFaqRegistrationStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], ChannelFaqRegistration] = {}

    def save(self, registration: ChannelFaqRegistration) -> ChannelFaqRegistration:
        registration.validate()
        saved = replace(registration, updated_at=datetime.now(UTC))
        self._records[(saved.tenant_id, saved.channel_id)] = saved
        return saved

    def get(self, *, tenant_id: str, channel_id: str) -> ChannelFaqRegistration | None:
        return self._records.get((tenant_id, channel_id))

    def list(self, *, tenant_id: str, enabled_only: bool = False) -> list[ChannelFaqRegistration]:
        records = [record for key, record in self._records.items() if key[0] == tenant_id]
        if enabled_only:
            records = [record for record in records if record.enabled]
        return sorted(
            records,
            key=lambda record: (record.last_ingested_at is not None, record.channel_id),
        )

    def delete(self, *, tenant_id: str, channel_id: str) -> bool:
        return self._records.pop((tenant_id, channel_id), None) is not None

    def update_ingest_result(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        status: str,
        message_count: int | None,
        chunk_count: int | None,
        error: str | None,
    ) -> ChannelFaqRegistration | None:
        existing = self.get(tenant_id=tenant_id, channel_id=channel_id)
        if existing is None:
            return None
        updated = replace(
            existing,
            last_ingested_at=datetime.now(UTC),
            last_message_count=message_count,
            last_chunk_count=chunk_count,
            last_status=status,
            last_error=error,
            updated_at=datetime.now(UTC),
        )
        self._records[(tenant_id, channel_id)] = updated
        return updated


class ChannelFaqRegistrationService:
    def __init__(self, store: InMemoryChannelFaqRegistrationStore) -> None:
        self._store = store

    def register(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        options: RegistrationOptions | None = None,
        actor: str | None = None,
    ) -> ChannelFaqRegistration:
        actual_options = options or RegistrationOptions()
        record = ChannelFaqRegistration(
            tenant_id=tenant_id,
            channel_id=channel_id,
            channel_name=actual_options.channel_name,
            enabled=actual_options.enabled,
            auto_reply_mode=actual_options.auto_reply_mode,
            confidence_threshold=actual_options.confidence_threshold,
            days_back=actual_options.days_back,
            re_ingest_interval_hours=actual_options.re_ingest_interval_hours,
            registered_by=actor,
        )
        return self._store.save(record)

    def get(self, *, tenant_id: str, channel_id: str) -> ChannelFaqRegistration | None:
        return self._store.get(tenant_id=tenant_id, channel_id=channel_id)

    def list(self, *, tenant_id: str, enabled_only: bool = False) -> list[ChannelFaqRegistration]:
        return self._store.list(tenant_id=tenant_id, enabled_only=enabled_only)

    def update(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        patch: RegistrationPatch,
    ) -> ChannelFaqRegistration | None:
        existing = self._store.get(tenant_id=tenant_id, channel_id=channel_id)
        if existing is None:
            return None
        return self._store.save(
            replace(
                existing,
                channel_name=patch.channel_name
                if patch.channel_name is not None
                else existing.channel_name,
                enabled=patch.enabled if patch.enabled is not None else existing.enabled,
                auto_reply_mode=patch.auto_reply_mode or existing.auto_reply_mode,
                confidence_threshold=patch.confidence_threshold
                if patch.confidence_threshold is not None
                else existing.confidence_threshold,
                days_back=patch.days_back if patch.days_back is not None else existing.days_back,
                re_ingest_interval_hours=patch.re_ingest_interval_hours
                if patch.re_ingest_interval_hours is not None
                else existing.re_ingest_interval_hours,
            )
        )

    def delete(self, *, tenant_id: str, channel_id: str) -> bool:
        return self._store.delete(tenant_id=tenant_id, channel_id=channel_id)
