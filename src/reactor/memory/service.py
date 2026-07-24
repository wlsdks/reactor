from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import uuid4

from reactor.memory.policy import MemoryNamespaceKey

SENSITIVE_MARKERS = ("api_key", "password", "secret", "token", "credential")
SENSITIVE_MARKER_ALIASES = {
    "api_key": ("api_key", "api key", "api-key", "apikey"),
    "password": ("password",),
    "secret": ("secret",),
    "token": ("token",),
    "credential": ("credential",),
}


@dataclass(frozen=True)
class MemoryProposalDraft:
    namespace: MemoryNamespaceKey
    content: str
    source_payload: Mapping[str, Any]
    extraction_model: str
    extraction_prompt_version: str
    confidence: float

    def validate(self) -> None:
        self.namespace.validate()
        for field_name, value in (
            ("content", self.content),
            ("extraction_model", self.extraction_model),
            ("extraction_prompt_version", self.extraction_prompt_version),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")


@dataclass(frozen=True)
class MemoryProposalRecord:
    id: str
    tenant_id: str
    namespace: MemoryNamespaceKey
    status: str
    proposed_content: str
    extraction_model: str
    extraction_prompt_version: str
    confidence: float
    source_payload: Mapping[str, Any]
    decision_reason: str | None
    created_at: datetime


@dataclass(frozen=True)
class MemoryItemRecord:
    id: str
    tenant_id: str
    namespace: MemoryNamespaceKey
    status: str
    content: str
    source_id: str | None
    confidence: float
    metadata: Mapping[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class MemoryPromotionResult:
    proposal: MemoryProposalRecord
    item: MemoryItemRecord
    superseded_items: tuple[MemoryItemRecord, ...] = ()


@dataclass(frozen=True)
class MemoryTombstoneResult:
    item: MemoryItemRecord
    delete_embedding: bool


@dataclass(frozen=True)
class UserMemoryRecord:
    user_id: str
    facts: Mapping[str, str]
    preferences: Mapping[str, str]
    recent_topics: list[str]
    updated_at: datetime


class UserMemoryStoreProtocol(Protocol):
    async def get_user_memory(self, *, tenant_id: str, user_id: str) -> UserMemoryRecord | None: ...

    async def upsert_user_memory_value(
        self,
        *,
        tenant_id: str,
        user_id: str,
        category: str,
        key: str,
        value: str,
    ) -> None: ...

    async def delete_user_memory(self, *, tenant_id: str, user_id: str) -> None: ...


class UserMemoryService:
    def __init__(self, store: UserMemoryStoreProtocol) -> None:
        self._store = store

    async def get(self, *, tenant_id: str, user_id: str) -> UserMemoryRecord | None:
        return await self._store.get_user_memory(tenant_id=tenant_id, user_id=user_id)

    async def update_fact(
        self,
        *,
        tenant_id: str,
        user_id: str,
        key: str,
        value: str,
    ) -> None:
        validate_user_memory_key_value(key, value)
        key = key.strip()
        value = value.strip()
        await self._store.upsert_user_memory_value(
            tenant_id=tenant_id,
            user_id=user_id,
            category="fact",
            key=key,
            value=value,
        )

    async def update_preference(
        self,
        *,
        tenant_id: str,
        user_id: str,
        key: str,
        value: str,
    ) -> None:
        validate_user_memory_key_value(key, value)
        key = key.strip()
        value = value.strip()
        await self._store.upsert_user_memory_value(
            tenant_id=tenant_id,
            user_id=user_id,
            category="preference",
            key=key,
            value=value,
        )

    async def delete(self, *, tenant_id: str, user_id: str) -> None:
        await self._store.delete_user_memory(tenant_id=tenant_id, user_id=user_id)


class MemoryProposalService:
    def __init__(
        self,
        *,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._id_factory = id_factory or (lambda: uuid4().hex)
        self._clock = clock or (lambda: datetime.now(UTC))

    def propose(self, draft: MemoryProposalDraft) -> MemoryProposalRecord:
        draft.validate()
        source_payload = memory_proposal_source_payload(
            draft.source_payload,
            content=draft.content,
        )
        return MemoryProposalRecord(
            id=self._id_factory(),
            tenant_id=draft.namespace.tenant_id,
            namespace=draft.namespace,
            status="proposed",
            proposed_content=draft.content,
            extraction_model=draft.extraction_model,
            extraction_prompt_version=draft.extraction_prompt_version,
            confidence=draft.confidence,
            source_payload=source_payload,
            decision_reason=None,
            created_at=self._clock(),
        )

    def promote(
        self,
        proposal: MemoryProposalRecord,
        *,
        reviewer_id: str,
        reason: str,
        supersedes: MemoryItemRecord | None = None,
    ) -> MemoryPromotionResult:
        if proposal.status != "proposed":
            raise ValueError("only proposed memory can be promoted")
        reviewer_id = reviewer_id.strip()
        reason = reason.strip()
        if not reviewer_id:
            raise ValueError("reviewer_id is required")
        if not reason:
            raise ValueError("reason is required")
        if memory_proposal_requires_redaction(proposal):
            raise ValueError("sensitive memory proposals require rejection or redaction")
        superseded_items: tuple[MemoryItemRecord, ...] = ()
        if supersedes is not None:
            if supersedes.status != "active":
                raise ValueError("only active memory can be superseded")
            if (
                supersedes.tenant_id != proposal.tenant_id
                or supersedes.namespace != proposal.namespace
            ):
                raise ValueError("superseded memory must match proposal namespace")
            if (
                supersedes.source_id == proposal.id
                or supersedes.metadata.get("proposal_id") == proposal.id
            ):
                raise ValueError("cannot supersede memory from the same proposal")
            superseded_metadata = dict(supersedes.metadata)
            superseded_metadata.update(
                {
                    "superseded_by_proposal_id": proposal.id,
                    "superseded_reason": reason,
                    "superseded_at": self._clock().isoformat(),
                }
            )
            superseded_items = (
                replace(supersedes, status="superseded", metadata=superseded_metadata),
            )

        approved = replace(proposal, status="approved", decision_reason=reason)
        item_metadata = {
            "reviewer_id": reviewer_id,
            "proposal_id": proposal.id,
            "extraction_model": proposal.extraction_model,
            "extraction_prompt_version": proposal.extraction_prompt_version,
        }
        if supersedes is not None:
            item_metadata["supersedes_memory_id"] = supersedes.id
        item = MemoryItemRecord(
            id=self._id_factory(),
            tenant_id=proposal.tenant_id,
            namespace=proposal.namespace,
            status="active",
            content=proposal.proposed_content,
            source_id=proposal.id,
            confidence=proposal.confidence,
            metadata=item_metadata,
            created_at=self._clock(),
        )
        return MemoryPromotionResult(
            proposal=approved, item=item, superseded_items=superseded_items
        )

    def reject(
        self,
        proposal: MemoryProposalRecord,
        *,
        reviewer_id: str,
        reason: str,
    ) -> MemoryProposalRecord:
        if proposal.status != "proposed":
            raise ValueError("only proposed memory can be rejected")
        reviewer_id = reviewer_id.strip()
        reason = reason.strip()
        if not reviewer_id:
            raise ValueError("reviewer_id is required")
        if not reason:
            raise ValueError("reason is required")
        return replace(
            proposal,
            status="rejected",
            decision_reason=f"{reason} reviewer={reviewer_id}",
        )

    def tombstone(
        self,
        item: MemoryItemRecord,
        *,
        actor_id: str,
        reason: str,
    ) -> MemoryTombstoneResult:
        if item.status != "active":
            raise ValueError("only active memory can be tombstoned")
        actor_id = actor_id.strip()
        reason = reason.strip()
        if not actor_id:
            raise ValueError("actor_id is required")
        if not reason:
            raise ValueError("reason is required")
        metadata = dict(item.metadata)
        metadata.update(
            {
                "tombstone_actor_id": actor_id,
                "tombstone_reason": reason,
                "tombstoned_at": self._clock().isoformat(),
            }
        )
        return MemoryTombstoneResult(
            item=replace(item, status="tombstoned", metadata=metadata),
            delete_embedding=True,
        )


def contains_sensitive_marker(content: str) -> bool:
    normalized = content.lower()
    return any(marker in normalized for marker in SENSITIVE_MARKERS)


def memory_proposal_requires_redaction(proposal: MemoryProposalRecord) -> bool:
    if contains_sensitive_marker(proposal.proposed_content):
        return True
    sensitivity = proposal.source_payload.get("sensitivity")
    if not isinstance(sensitivity, Mapping):
        return False
    sensitivity_payload = cast(Mapping[str, object], sensitivity)
    return sensitivity_payload.get("status") == "flagged"


def sensitive_markers(content: str) -> list[str]:
    normalized = content.lower()
    compact = "".join(character for character in normalized if character.isalnum())
    return [
        marker
        for marker in SENSITIVE_MARKERS
        if any(
            alias in normalized or alias.replace(" ", "") in compact
            for alias in marker_aliases(marker)
        )
    ]


def marker_aliases(marker: str) -> tuple[str, ...]:
    return SENSITIVE_MARKER_ALIASES.get(marker, (marker,))


def sensitive_markers_in_value(value: Any) -> list[str]:
    haystack: list[str] = []
    if isinstance(value, Mapping):
        for key, nested_value in cast(Mapping[object, object], value).items():
            haystack.append(str(key))
            haystack.extend(sensitive_markers_in_value(nested_value))
    elif isinstance(value, list | tuple | set):
        for nested_value in cast(Iterable[object], value):
            haystack.extend(sensitive_markers_in_value(nested_value))
    else:
        haystack.append(str(value))
    return sensitive_markers("\n".join(haystack))


def memory_proposal_source_payload(
    source_payload: Mapping[str, Any],
    *,
    content: str,
) -> dict[str, Any]:
    payload = dict(source_payload)
    content_markers = sensitive_markers(content)
    source_markers = sensitive_markers_in_value(source_payload)
    marker_set = {*content_markers, *source_markers}
    markers = [marker for marker in SENSITIVE_MARKERS if marker in marker_set]
    if markers:
        sensitivity: dict[str, Any] = {
            "status": "flagged",
            "policy": "reject_or_redact_before_promotion",
            "markers": markers,
        }
        if source_markers:
            sensitivity["source"] = "content_or_source_payload"
        payload["sensitivity"] = sensitivity
    return payload


def validate_user_memory_key_value(key: str, value: str) -> None:
    if not key.strip():
        raise ValueError("key must not be blank")
    if not value.strip():
        raise ValueError("value must not be blank")
    if ":" in key:
        raise ValueError("key must not contain ':'")
