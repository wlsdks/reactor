from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.kernel.ids import new_id
from reactor.memory.policy import MemoryNamespaceKey
from reactor.memory.service import (
    MemoryItemRecord,
    MemoryPromotionResult,
    MemoryProposalRecord,
    MemoryTombstoneResult,
    UserMemoryRecord,
)
from reactor.persistence.models import (
    MemoryEmbedding,
    MemoryItem,
    MemoryNamespace,
    MemoryProposal,
)


@dataclass(frozen=True)
class MemoryNamespaceMigrationRecord:
    id: str
    tenant_id: str
    subject_type: str
    subject_id: str
    memory_type: str
    visibility: str
    created_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("subject_type", self.subject_type),
            ("subject_id", self.subject_id),
            ("memory_type", self.memory_type),
            ("visibility", self.visibility),
        )


@dataclass(frozen=True)
class MemoryItemMigrationRecord:
    id: str
    namespace_id: str
    tenant_id: str
    status: str
    content: str
    source_id: str | None
    confidence: float
    valid_from: datetime | None
    valid_until: datetime | None
    metadata: dict[str, Any]
    created_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("id", self.id),
            ("namespace_id", self.namespace_id),
            ("tenant_id", self.tenant_id),
            ("status", self.status),
        )


@dataclass(frozen=True)
class MemoryEmbeddingRecord:
    memory_id: str
    tenant_id: str
    embedding: list[float]
    embedding_model: str
    created_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("memory_id", self.memory_id),
            ("tenant_id", self.tenant_id),
            ("embedding_model", self.embedding_model),
        )


@dataclass(frozen=True)
class MemoryProposalMigrationRecord:
    id: str
    tenant_id: str
    namespace_id: str
    status: str
    proposed_content: str
    extraction_model: str
    extraction_prompt_version: str
    confidence: float
    source_payload: dict[str, Any]
    decision_reason: str | None
    created_at: datetime

    def validate(self) -> None:
        require_non_blank(
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("namespace_id", self.namespace_id),
            ("status", self.status),
            ("extraction_model", self.extraction_model),
            ("extraction_prompt_version", self.extraction_prompt_version),
        )


class SqlAlchemyMemoryStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_proposal(self, proposal: MemoryProposalRecord) -> str:
        namespace_id = new_id("memory_namespace")
        async with self._session_factory() as session:
            async with session.begin():
                persisted_namespace_id = await self._get_or_create_namespace(
                    session,
                    proposal.namespace,
                    namespace_id=namespace_id,
                )
                await session.execute(
                    build_memory_proposal_insert(
                        proposal,
                        namespace_id=persisted_namespace_id,
                    )
                )
        return proposal.id

    async def save_promotion(self, result: MemoryPromotionResult) -> str:
        namespace_id = new_id("memory_namespace")
        async with self._session_factory() as session:
            async with session.begin():
                persisted_namespace_id = await self._get_or_create_namespace(
                    session,
                    result.item.namespace,
                    namespace_id=namespace_id,
                )
                await session.execute(build_memory_proposal_status_update(result.proposal))
                for superseded_item in result.superseded_items:
                    supersede_result = await session.execute(
                        build_memory_supersede_update(superseded_item)
                    )
                    require_memory_rows_changed(
                        supersede_result,
                        action="supersede active memory",
                    )
                await session.execute(
                    build_memory_item_insert(result.item, namespace_id=persisted_namespace_id)
                )
        return result.item.id

    async def save_rejection(self, proposal: MemoryProposalRecord) -> str:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(build_memory_proposal_status_update(proposal))
                require_memory_rows_changed(result, action="reject memory proposal")
        return proposal.id

    async def save_tombstone(self, result: MemoryTombstoneResult) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_memory_tombstone_update(result.item))
                if result.delete_embedding:
                    await session.execute(
                        build_memory_embedding_delete(
                            memory_id=result.item.id,
                            tenant_id=result.item.tenant_id,
                        )
                    )

    async def list_active_items(
        self,
        namespace: MemoryNamespaceKey,
        *,
        limit: int = 20,
    ) -> list[MemoryItemRecord]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        async with self._session_factory() as session:
            namespace_id = await session.scalar(build_memory_namespace_lookup(namespace))
            if namespace_id is None:
                return []
            rows = await session.scalars(
                build_active_memory_items_query(
                    namespace_id=namespace_id,
                    tenant_id=namespace.tenant_id,
                    limit=limit,
                )
            )
            return [memory_item_record_from_model(row, namespace=namespace) for row in rows]

    async def list_proposals(
        self,
        *,
        tenant_id: str,
        status: str = "proposed",
        limit: int = 50,
        subject_id: str | None = None,
    ) -> list[MemoryProposalRecord]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        async with self._session_factory() as session:
            rows = await session.execute(
                build_memory_proposals_query(
                    tenant_id=tenant_id,
                    status=status,
                    limit=limit,
                    subject_id=subject_id,
                )
            )
            return [
                memory_proposal_record_from_models(
                    cast(MemoryProposal, proposal),
                    namespace=memory_namespace_key_from_model(cast(MemoryNamespace, namespace)),
                )
                for proposal, namespace in rows
            ]

    async def get_proposal(
        self,
        *,
        tenant_id: str,
        proposal_id: str,
    ) -> MemoryProposalRecord | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    build_memory_proposal_lookup(tenant_id=tenant_id, proposal_id=proposal_id)
                )
            ).one_or_none()
            if row is None:
                return None
            proposal, namespace = row
            return memory_proposal_record_from_models(
                cast(MemoryProposal, proposal),
                namespace=memory_namespace_key_from_model(cast(MemoryNamespace, namespace)),
            )

    async def get_memory_item(
        self,
        *,
        tenant_id: str,
        item_id: str,
    ) -> MemoryItemRecord | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    build_memory_item_lookup(tenant_id=tenant_id, item_id=item_id)
                )
            ).one_or_none()
            if row is None:
                return None
            item, namespace = row
            return memory_item_record_from_model(
                cast(MemoryItem, item),
                namespace=memory_namespace_key_from_model(cast(MemoryNamespace, namespace)),
            )

    async def get_user_memory(self, *, tenant_id: str, user_id: str) -> UserMemoryRecord | None:
        key = user_memory_namespace_key(tenant_id=tenant_id, user_id=user_id)
        async with self._session_factory() as session:
            namespace_id = await session.scalar(build_memory_namespace_lookup(key))
            if namespace_id is None:
                return None
            rows = await session.scalars(build_user_memory_items_query(namespace_id=namespace_id))
            facts: dict[str, str] = {}
            preferences: dict[str, str] = {}
            recent_topics: list[str] = []
            updated_at: datetime | None = None
            for item in rows:
                metadata = cast(dict[str, Any], item.item_metadata)
                category = str(metadata.get("category") or "")
                item_key = str(metadata.get("key") or "")
                if not item_key:
                    continue
                if category == "fact":
                    facts[item_key] = item.content
                elif category == "preference":
                    preferences[item_key] = item.content
                elif category == "recent_topic":
                    recent_topics.append(item.content)
                updated_at = max(updated_at or item.created_at, item.created_at)
            if not facts and not preferences and not recent_topics:
                return None
            return UserMemoryRecord(
                user_id=user_id,
                facts=facts,
                preferences=preferences,
                recent_topics=recent_topics,
                updated_at=updated_at or datetime.now(UTC),
            )

    async def upsert_user_memory_value(
        self,
        *,
        tenant_id: str,
        user_id: str,
        category: str,
        key: str,
        value: str,
    ) -> None:
        namespace_key = user_memory_namespace_key(tenant_id=tenant_id, user_id=user_id)
        namespace_id = new_id("memory_namespace")
        async with self._session_factory() as session:
            async with session.begin():
                persisted_namespace_id = await self._get_or_create_namespace(
                    session,
                    namespace_key,
                    namespace_id=namespace_id,
                )
                await session.execute(
                    build_user_memory_supersede_update(
                        namespace_id=persisted_namespace_id,
                        category=category,
                        key=key,
                    )
                )
                await session.execute(
                    build_user_memory_item_insert(
                        tenant_id=tenant_id,
                        namespace_id=persisted_namespace_id,
                        category=category,
                        key=key,
                        value=value,
                    )
                )

    async def delete_user_memory(self, *, tenant_id: str, user_id: str) -> None:
        key = user_memory_namespace_key(tenant_id=tenant_id, user_id=user_id)
        async with self._session_factory() as session:
            async with session.begin():
                namespace_id = await session.scalar(build_memory_namespace_lookup(key))
                if namespace_id is None:
                    return
                await session.execute(
                    update(MemoryItem)
                    .where(MemoryItem.namespace_id == namespace_id, MemoryItem.status == "active")
                    .values(status="tombstoned")
                )

    async def save_namespace(self, record: MemoryNamespaceMigrationRecord) -> str:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_memory_namespace_migration_upsert(record))
        return record.id

    async def save_item(self, record: MemoryItemMigrationRecord) -> str:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_memory_item_migration_upsert(record))
        return record.id

    async def save_embedding(self, record: MemoryEmbeddingRecord) -> str:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_memory_embedding_migration_upsert(record))
        return record.memory_id

    async def save_proposal_record(self, record: MemoryProposalMigrationRecord) -> str:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_memory_proposal_migration_upsert(record))
        return record.id

    async def _get_or_create_namespace(
        self,
        session: AsyncSession,
        key: MemoryNamespaceKey,
        *,
        namespace_id: str,
    ) -> str:
        inserted_id = await session.scalar(build_memory_namespace_insert(key, namespace_id))
        if inserted_id is not None:
            return inserted_id
        existing_id = await session.scalar(build_memory_namespace_lookup(key))
        if existing_id is None:
            raise RuntimeError("memory namespace upsert did not return a row")
        return existing_id


def build_memory_namespace_insert(key: MemoryNamespaceKey, namespace_id: str) -> Any:
    key.validate()
    return (
        insert(MemoryNamespace)
        .values(
            id=namespace_id,
            tenant_id=key.tenant_id,
            subject_type=key.subject_type,
            subject_id=key.subject_id,
            memory_type=key.memory_type,
            visibility=key.visibility,
        )
        .on_conflict_do_nothing(constraint="uq_memory_namespaces_identity")
        .returning(MemoryNamespace.id)
    )


def build_memory_namespace_migration_upsert(record: MemoryNamespaceMigrationRecord) -> Any:
    values = {
        "id": record.id,
        "tenant_id": record.tenant_id,
        "subject_type": record.subject_type,
        "subject_id": record.subject_id,
        "memory_type": record.memory_type,
        "visibility": record.visibility,
        "created_at": record.created_at,
    }
    return (
        insert(MemoryNamespace)
        .values(values)
        .on_conflict_do_update(
            constraint="uq_memory_namespaces_identity",
            set_={"created_at": values["created_at"]},
        )
    )


def build_memory_item_migration_upsert(record: MemoryItemMigrationRecord) -> Any:
    return (
        insert(MemoryItem)
        .values(
            id=record.id,
            namespace_id=record.namespace_id,
            tenant_id=record.tenant_id,
            status=record.status,
            content=record.content,
            source_id=record.source_id,
            confidence=record.confidence,
            valid_from=record.valid_from,
            valid_until=record.valid_until,
            item_metadata=dict(record.metadata),
            created_at=record.created_at,
        )
        .on_conflict_do_update(
            index_elements=[MemoryItem.id],
            set_={
                "status": record.status,
                "content": record.content,
                "source_id": record.source_id,
                "confidence": record.confidence,
                "valid_from": record.valid_from,
                "valid_until": record.valid_until,
                "metadata": dict(record.metadata),
            },
        )
    )


def build_memory_embedding_migration_upsert(record: MemoryEmbeddingRecord) -> Any:
    return (
        insert(MemoryEmbedding)
        .values(
            memory_id=record.memory_id,
            tenant_id=record.tenant_id,
            embedding=record.embedding,
            embedding_model=record.embedding_model,
            created_at=record.created_at,
        )
        .on_conflict_do_update(
            index_elements=[MemoryEmbedding.memory_id],
            set_={
                "tenant_id": record.tenant_id,
                "embedding": record.embedding,
                "embedding_model": record.embedding_model,
            },
        )
    )


def build_memory_proposal_migration_upsert(record: MemoryProposalMigrationRecord) -> Any:
    return (
        insert(MemoryProposal)
        .values(
            id=record.id,
            tenant_id=record.tenant_id,
            namespace_id=record.namespace_id,
            status=record.status,
            proposed_content=record.proposed_content,
            extraction_model=record.extraction_model,
            extraction_prompt_version=record.extraction_prompt_version,
            confidence=record.confidence,
            source_payload=dict(record.source_payload),
            decision_reason=record.decision_reason,
            created_at=record.created_at,
        )
        .on_conflict_do_update(
            index_elements=[MemoryProposal.id],
            set_={
                "status": record.status,
                "proposed_content": record.proposed_content,
                "confidence": record.confidence,
                "source_payload": dict(record.source_payload),
                "decision_reason": record.decision_reason,
            },
        )
    )


def build_memory_namespace_lookup(key: MemoryNamespaceKey) -> Any:
    key.validate()
    return select(MemoryNamespace.id).where(
        MemoryNamespace.tenant_id == key.tenant_id,
        MemoryNamespace.subject_type == key.subject_type,
        MemoryNamespace.subject_id == key.subject_id,
        MemoryNamespace.memory_type == key.memory_type,
        MemoryNamespace.visibility == key.visibility,
    )


def build_memory_proposal_insert(
    proposal: MemoryProposalRecord,
    *,
    namespace_id: str,
) -> Any:
    return insert(MemoryProposal).values(
        id=proposal.id,
        tenant_id=proposal.tenant_id,
        namespace_id=namespace_id,
        status=proposal.status,
        proposed_content=proposal.proposed_content,
        extraction_model=proposal.extraction_model,
        extraction_prompt_version=proposal.extraction_prompt_version,
        confidence=proposal.confidence,
        source_payload=dict(proposal.source_payload),
        decision_reason=proposal.decision_reason,
    )


def build_memory_proposal_status_update(proposal: MemoryProposalRecord) -> Any:
    return (
        update(MemoryProposal)
        .where(
            MemoryProposal.id == proposal.id,
            MemoryProposal.tenant_id == proposal.tenant_id,
            MemoryProposal.status == "proposed",
        )
        .values(status=proposal.status, decision_reason=proposal.decision_reason)
    )


def build_memory_item_insert(item: MemoryItemRecord, *, namespace_id: str) -> Any:
    return insert(MemoryItem).values(
        id=item.id,
        namespace_id=namespace_id,
        tenant_id=item.tenant_id,
        status=item.status,
        content=item.content,
        source_id=item.source_id,
        confidence=item.confidence,
        item_metadata=dict(item.metadata),
    )


def build_memory_supersede_update(item: MemoryItemRecord) -> Any:
    return (
        update(MemoryItem)
        .where(
            MemoryItem.id == item.id,
            MemoryItem.tenant_id == item.tenant_id,
            MemoryItem.status == "active",
        )
        .values(status="superseded", item_metadata=dict(item.metadata))
    )


def build_memory_tombstone_update(item: MemoryItemRecord) -> Any:
    return (
        update(MemoryItem)
        .where(
            MemoryItem.id == item.id,
            MemoryItem.tenant_id == item.tenant_id,
            MemoryItem.status == "active",
        )
        .values(status="tombstoned", item_metadata=dict(item.metadata))
    )


def build_memory_embedding_delete(*, memory_id: str, tenant_id: str) -> Any:
    return delete(MemoryEmbedding).where(
        MemoryEmbedding.memory_id == memory_id,
        MemoryEmbedding.tenant_id == tenant_id,
    )


def require_memory_rows_changed(result: Any, *, action: str) -> None:
    rowcount = getattr(result, "rowcount", None)
    if isinstance(rowcount, int) and rowcount > 0:
        return
    raise RuntimeError(f"{action} did not update any memory rows")


def build_active_memory_items_query(*, namespace_id: str, tenant_id: str, limit: int) -> Any:
    return (
        select(MemoryItem)
        .where(
            MemoryItem.namespace_id == namespace_id,
            MemoryItem.tenant_id == tenant_id,
            MemoryItem.status == "active",
        )
        .order_by(MemoryItem.created_at.desc(), MemoryItem.id.asc())
        .limit(limit)
    )


def build_memory_proposals_query(
    *,
    tenant_id: str,
    status: str,
    limit: int,
    subject_id: str | None = None,
) -> Any:
    query = (
        select(MemoryProposal, MemoryNamespace)
        .join(MemoryNamespace, MemoryProposal.namespace_id == MemoryNamespace.id)
        .where(MemoryProposal.tenant_id == tenant_id, MemoryProposal.status == status)
        .order_by(MemoryProposal.created_at.asc(), MemoryProposal.id.asc())
    )
    if subject_id:
        query = query.where(MemoryNamespace.subject_id == subject_id)
    return query.limit(limit)


def build_memory_proposal_lookup(*, tenant_id: str, proposal_id: str) -> Any:
    return (
        select(MemoryProposal, MemoryNamespace)
        .join(MemoryNamespace, MemoryProposal.namespace_id == MemoryNamespace.id)
        .where(MemoryProposal.tenant_id == tenant_id, MemoryProposal.id == proposal_id)
    )


def build_memory_item_lookup(*, tenant_id: str, item_id: str) -> Any:
    return (
        select(MemoryItem, MemoryNamespace)
        .join(MemoryNamespace, MemoryItem.namespace_id == MemoryNamespace.id)
        .where(MemoryItem.tenant_id == tenant_id, MemoryItem.id == item_id)
    )


def memory_namespace_key_from_model(row: MemoryNamespace) -> MemoryNamespaceKey:
    return MemoryNamespaceKey(
        tenant_id=row.tenant_id,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        memory_type=row.memory_type,
        visibility=row.visibility,
    )


def memory_proposal_record_from_models(
    row: MemoryProposal,
    *,
    namespace: MemoryNamespaceKey,
) -> MemoryProposalRecord:
    return MemoryProposalRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        namespace=namespace,
        status=row.status,
        proposed_content=row.proposed_content,
        extraction_model=row.extraction_model,
        extraction_prompt_version=row.extraction_prompt_version,
        confidence=float(row.confidence),
        source_payload=row.source_payload,
        decision_reason=row.decision_reason,
        created_at=row.created_at,
    )


def memory_item_record_from_model(
    row: MemoryItem,
    *,
    namespace: MemoryNamespaceKey,
) -> MemoryItemRecord:
    return MemoryItemRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        namespace=namespace,
        status=row.status,
        content=row.content,
        source_id=row.source_id,
        confidence=float(row.confidence),
        metadata=row.item_metadata,
        created_at=row.created_at,
    )


def user_memory_namespace_key(*, tenant_id: str, user_id: str) -> MemoryNamespaceKey:
    return MemoryNamespaceKey(
        tenant_id=tenant_id,
        subject_type="user",
        subject_id=user_id,
        memory_type="semantic",
        visibility="user",
    )


def build_user_memory_items_query(*, namespace_id: str) -> Any:
    return (
        select(MemoryItem)
        .where(MemoryItem.namespace_id == namespace_id, MemoryItem.status == "active")
        .order_by(MemoryItem.created_at.asc())
    )


def build_user_memory_supersede_update(*, namespace_id: str, category: str, key: str) -> Any:
    return (
        update(MemoryItem)
        .where(
            MemoryItem.namespace_id == namespace_id,
            MemoryItem.status == "active",
            MemoryItem.item_metadata["category"].as_string() == category,
            MemoryItem.item_metadata["key"].as_string() == key,
        )
        .values(status="superseded")
    )


def build_user_memory_item_insert(
    *,
    tenant_id: str,
    namespace_id: str,
    category: str,
    key: str,
    value: str,
) -> Any:
    return insert(MemoryItem).values(
        id=new_id("memory_item"),
        namespace_id=namespace_id,
        tenant_id=tenant_id,
        status="active",
        content=value,
        source_id=None,
        confidence=1.0,
        item_metadata={"category": category, "key": key, "source": "user-memory-api"},
    )


def require_non_blank(*fields: tuple[str, str]) -> None:
    for field_name, value in fields:
        if not value.strip():
            raise ValueError(f"{field_name} is required")
