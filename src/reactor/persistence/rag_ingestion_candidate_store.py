from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import false, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.persistence.models import RagIngestionCandidateRow
from reactor.rag.ingestion_candidate_ids import command_slug
from reactor.rag.ingestion_candidates import (
    RagIngestionCandidate,
    RagIngestionCandidateStatus,
)


class SqlAlchemyRagIngestionCandidateStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, candidate: RagIngestionCandidate) -> RagIngestionCandidate:
        candidate.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(candidate_insert(candidate))
                if row is None:
                    existing = await session.scalar(candidate_find_by_run_id(candidate.run_id))
                    if existing is not None:
                        return candidate_from_model(existing)
                    raise RuntimeError("rag ingestion candidate insert returned no row")
                return candidate_from_model(row)

    async def find_by_id(self, candidate_id: str) -> RagIngestionCandidate | None:
        async with self._session_factory() as session:
            row = await session.get(RagIngestionCandidateRow, candidate_id)
            return candidate_from_model(row) if row is not None else None

    async def find_by_run_id(self, run_id: str) -> RagIngestionCandidate | None:
        async with self._session_factory() as session:
            row = await session.scalar(candidate_find_by_run_id(run_id))
            return candidate_from_model(row) if row is not None else None

    async def list(
        self,
        *,
        limit: int = 100,
        status: RagIngestionCandidateStatus | None = None,
        channel: str | None = None,
        tags: Sequence[str] | None = None,
    ) -> list[RagIngestionCandidate]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                candidate_list(limit=limit, status=status, channel=channel, tags=tags)
            )
            return [candidate_from_model(row) for row in rows]

    async def update_review(
        self,
        *,
        candidate_id: str,
        status: RagIngestionCandidateStatus,
        reviewed_by: str,
        review_comment: str | None,
        ingested_document_id: str | None = None,
    ) -> RagIngestionCandidate | None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    candidate_update_review(
                        candidate_id=candidate_id,
                        status=status,
                        reviewed_by=reviewed_by,
                        review_comment=review_comment,
                        ingested_document_id=ingested_document_id,
                    )
                )
                return candidate_from_model(row) if row is not None else None


def candidate_insert(candidate: RagIngestionCandidate):
    return (
        insert(RagIngestionCandidateRow)
        .values(candidate_values(candidate))
        .on_conflict_do_nothing(constraint="uq_rag_ingestion_candidates_run")
        .returning(RagIngestionCandidateRow)
    )


def candidate_find_by_run_id(run_id: str):
    return select(RagIngestionCandidateRow).where(RagIngestionCandidateRow.run_id == run_id)


def candidate_list(
    *,
    limit: int = 100,
    status: RagIngestionCandidateStatus | None = None,
    channel: str | None = None,
    tags: Sequence[str] | None = None,
):
    capped_limit = max(1, min(limit, 500))
    statement = select(RagIngestionCandidateRow)
    if status is not None:
        statement = statement.where(RagIngestionCandidateRow.status == status.value)
    normalized_channel = channel.strip().lower() if channel is not None else ""
    if normalized_channel:
        statement = statement.where(
            func.lower(RagIngestionCandidateRow.channel) == normalized_channel
        )
    candidate_ids = candidate_ids_from_tags(tags or ())
    if candidate_ids is not None:
        if not candidate_ids:
            statement = statement.where(false())
        else:
            statement = statement.where(RagIngestionCandidateRow.id.in_(candidate_ids))
    return statement.order_by(RagIngestionCandidateRow.captured_at.desc()).limit(capped_limit)


def candidate_ids_from_tags(tags: Sequence[str]) -> list[str] | None:
    if not tags:
        return None
    candidate_ids: list[str] = []
    saw_candidate_filter = False
    for tag in tags:
        stripped = tag.strip()
        if not stripped or stripped == "collection:rag-ingestion-candidate":
            continue
        candidate_id = stripped.removeprefix("rag-candidate:")
        if candidate_id == stripped:
            return []
        saw_candidate_filter = True
        candidate_id = candidate_id.strip()
        if not candidate_id or command_slug(candidate_id) != candidate_id:
            return []
        candidate_ids.append(candidate_id)
    if not saw_candidate_filter:
        return None
    return candidate_ids


def candidate_update_review(
    *,
    candidate_id: str,
    status: RagIngestionCandidateStatus,
    reviewed_by: str,
    review_comment: str | None,
    ingested_document_id: str | None,
):
    return (
        update(RagIngestionCandidateRow)
        .where(
            RagIngestionCandidateRow.id == candidate_id,
            RagIngestionCandidateRow.status == RagIngestionCandidateStatus.PENDING.value,
        )
        .values(
            status=status.value,
            reviewed_at=func.now(),
            reviewed_by=reviewed_by,
            review_comment=review_comment,
            ingested_document_id=ingested_document_id,
        )
        .returning(RagIngestionCandidateRow)
    )


def candidate_values(candidate: RagIngestionCandidate) -> dict[str, object | None]:
    return {
        "id": candidate.id,
        "run_id": candidate.run_id,
        "user_id": candidate.user_id,
        "session_id": candidate.session_id,
        "channel": candidate.channel,
        "query": candidate.query,
        "response": candidate.response,
        "status": candidate.status.value,
        "captured_at": candidate.captured_at,
        "reviewed_at": candidate.reviewed_at,
        "reviewed_by": candidate.reviewed_by,
        "review_comment": candidate.review_comment,
        "ingested_document_id": candidate.ingested_document_id,
    }


def candidate_from_model(row: RagIngestionCandidateRow) -> RagIngestionCandidate:
    return RagIngestionCandidate(
        id=row.id,
        run_id=row.run_id,
        user_id=row.user_id,
        session_id=row.session_id,
        channel=row.channel,
        query=row.query,
        response=row.response,
        status=RagIngestionCandidateStatus(row.status),
        captured_at=row.captured_at,
        reviewed_at=row.reviewed_at,
        reviewed_by=row.reviewed_by,
        review_comment=row.review_comment,
        ingested_document_id=row.ingested_document_id,
    )
