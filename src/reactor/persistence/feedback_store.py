from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.feedback.workflow import feedback_matches_eval_case_id
from reactor.persistence.models import FeedbackRecord
from reactor.slack.feedback import (
    Feedback,
    FeedbackRating,
    feedback_analytics_payload,
    feedback_review_matches,
    feedback_stats_payload,
)


class SqlAlchemyFeedbackStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, feedback: Feedback) -> Feedback:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    insert(FeedbackRecord)
                    .values(feedback_values(feedback))
                    .on_conflict_do_update(
                        index_elements=[FeedbackRecord.id],
                        set_=feedback_upsert_update_values(feedback),
                    )
                    .returning(FeedbackRecord)
                )
                if row is None:
                    raise RuntimeError("feedback upsert did not return a row")
                return feedback_from_model(row)

    async def get(self, *, tenant_id: str, feedback_id: str) -> Feedback | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(FeedbackRecord).where(
                    FeedbackRecord.tenant_id == tenant_id,
                    FeedbackRecord.id == feedback_id,
                )
            )
            return feedback_from_model(row) if row is not None else None

    async def list(
        self,
        *,
        tenant_id: str,
        rating: FeedbackRating | None = None,
        template_id: str | None = None,
        source: str | None = None,
        review_status: str | None = None,
        tags: list[str] | None = None,
        case_id: str | None = None,
        limit: int = 50,
    ) -> list[Feedback]:
        statement = select(FeedbackRecord).where(FeedbackRecord.tenant_id == tenant_id)
        if rating is not None:
            statement = statement.where(FeedbackRecord.rating == rating.value)
        if template_id is not None:
            statement = statement.where(FeedbackRecord.template_id == template_id)
        if source is not None:
            statement = statement.where(FeedbackRecord.source == source)
        if review_status is not None:
            statement = statement.where(FeedbackRecord.review_status == review_status)
        capped_limit = max(1, min(limit, 100))
        statement = statement.order_by(FeedbackRecord.created_at.desc())
        if not tags:
            statement = statement.limit(capped_limit)
        async with self._session_factory() as session:
            rows = await session.scalars(statement)
            records = [feedback_from_model(row) for row in rows]
        if tags:
            wanted = set(tags)
            records = [
                record
                for record in records
                if wanted.issubset(set(record.tags or []) | set(record.review_tags))
            ]
        if case_id:
            records = [
                record for record in records if feedback_matches_eval_case_id(record, case_id)
            ]
        return records[:capped_limit]

    async def count(self, *, tenant_id: str) -> int:
        async with self._session_factory() as session:
            value = await session.scalar(
                select(func.count())
                .select_from(FeedbackRecord)
                .where(FeedbackRecord.tenant_id == tenant_id)
            )
            return int(value or 0)

    async def update_review(
        self,
        *,
        tenant_id: str,
        feedback_id: str,
        expected_version: int,
        status: str | None,
        tags: list[str] | None,
        note: str | None,
        actor: str,
    ) -> Feedback:
        async with self._session_factory() as session:
            async with session.begin():
                current = await session.scalar(
                    select(FeedbackRecord).where(
                        FeedbackRecord.tenant_id == tenant_id,
                        FeedbackRecord.id == feedback_id,
                    )
                )
                if current is None:
                    raise KeyError(feedback_id)
                if current.version != expected_version:
                    raise ValueError("version_conflict")
                current_feedback = feedback_from_model(current)
                if feedback_review_matches(
                    current_feedback,
                    status=status,
                    tags=tags,
                    note=note,
                ):
                    return current_feedback
                now = datetime.now(UTC)
                values: dict[str, object] = {
                    "reviewed_by": actor,
                    "reviewed_at": now,
                    "version": current.version + 1,
                    "updated_at": now,
                }
                if status is not None:
                    values["review_status"] = status
                if tags is not None:
                    values["review_tags"] = tags
                if note is not None:
                    values["review_note"] = note
                row = await session.scalar(
                    update(FeedbackRecord)
                    .where(
                        FeedbackRecord.tenant_id == tenant_id,
                        FeedbackRecord.id == feedback_id,
                    )
                    .values(values)
                    .returning(FeedbackRecord)
                )
                if row is None:
                    raise RuntimeError("feedback review update did not return a row")
                return feedback_from_model(row)

    async def unreviewed_count(self, *, tenant_id: str) -> int:
        async with self._session_factory() as session:
            value = await session.scalar(
                select(func.count())
                .select_from(FeedbackRecord)
                .where(
                    FeedbackRecord.tenant_id == tenant_id,
                    FeedbackRecord.rating == FeedbackRating.THUMBS_DOWN.value,
                    FeedbackRecord.review_status == "inbox",
                )
            )
            return int(value or 0)

    async def delete(self, *, tenant_id: str, feedback_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    delete(FeedbackRecord).where(
                        FeedbackRecord.tenant_id == tenant_id,
                        FeedbackRecord.id == feedback_id,
                    )
                )

    async def stats(self, *, tenant_id: str) -> dict[str, object]:
        records = await self.list(tenant_id=tenant_id, limit=100)
        positive = sum(1 for record in records if record.rating == FeedbackRating.THUMBS_UP)
        negative = sum(1 for record in records if record.rating == FeedbackRating.THUMBS_DOWN)
        inbox = sum(1 for record in records if record.review_status == "inbox")
        done = sum(1 for record in records if record.review_status == "done")
        with_comment = sum(1 for record in records if record.comment is not None)
        return feedback_stats_payload(
            total=len(records),
            positive=positive,
            negative=negative,
            with_comment=with_comment,
            inbox=inbox,
            done=done,
        )

    async def analytics(
        self,
        *,
        tenant_id: str,
        group_by: str,
        limit: int = 20,
    ) -> dict[str, object]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(FeedbackRecord)
                .where(FeedbackRecord.tenant_id == tenant_id)
                .order_by(FeedbackRecord.created_at.desc())
            )
            records = [feedback_from_model(row) for row in rows]
        return feedback_analytics_payload(records, group_by=group_by, limit=limit)

    async def bulk_update_review(
        self,
        *,
        tenant_id: str,
        ids: list[str],
        status: str | None,
        tags: list[str] | None,
        note: str | None,
        actor: str,
    ) -> dict[str, object]:
        updated: list[str] = []
        already_done: list[str] = []
        failed: list[dict[str, str]] = []
        for feedback_id in ids:
            current = await self.get(tenant_id=tenant_id, feedback_id=feedback_id)
            if current is None:
                failed.append({"id": feedback_id, "reason": "not_found"})
                continue
            if feedback_review_matches(current, status=status, tags=tags, note=note):
                already_done.append(feedback_id)
                continue
            await self.update_review(
                tenant_id=tenant_id,
                feedback_id=feedback_id,
                expected_version=current.version,
                status=status,
                tags=tags,
                note=note,
                actor=actor,
            )
            updated.append(feedback_id)
        result: dict[str, object] = {"updated": updated, "failed": failed}
        if already_done:
            result["alreadyDone"] = already_done
        return result


def feedback_values(
    feedback: Feedback,
    *,
    include_id: bool = True,
    include_created_at: bool = True,
) -> dict[str, object]:
    values: dict[str, object] = {
        "tenant_id": feedback.tenant_id,
        "query": feedback.query,
        "response": feedback.response,
        "rating": feedback.rating.value,
        "source": feedback.source,
        "comment": feedback.comment,
        "session_id": feedback.session_id,
        "run_id": feedback.run_id,
        "user_id": feedback.user_id,
        "intent": feedback.intent,
        "domain": feedback.domain,
        "model": feedback.model,
        "prompt_version": feedback.prompt_version,
        "tools_used": feedback.tools_used,
        "duration_ms": feedback.duration_ms,
        "tags": feedback.tags,
        "template_id": feedback.template_id,
        "review_status": feedback.review_status,
        "review_tags": feedback.review_tags,
        "reviewed_by": feedback.reviewed_by,
        "reviewed_at": feedback.reviewed_at,
        "review_note": feedback.review_note,
        "version": feedback.version,
        "updated_at": feedback.updated_at,
    }
    if include_id:
        values["id"] = feedback.feedback_id
    if include_created_at:
        values["created_at"] = feedback.created_at
    return values


def feedback_upsert_update_values(feedback: Feedback) -> dict[str, object]:
    values = feedback_values(feedback, include_id=False, include_created_at=False)
    for review_field in (
        "review_status",
        "review_tags",
        "reviewed_by",
        "reviewed_at",
        "review_note",
        "version",
    ):
        values.pop(review_field, None)
    return values


def feedback_from_model(row: FeedbackRecord) -> Feedback:
    return Feedback(
        feedback_id=row.id,
        tenant_id=row.tenant_id,
        query=row.query,
        response=row.response,
        rating=FeedbackRating(row.rating),
        source=row.source,
        comment=row.comment,
        session_id=row.session_id or "",
        run_id=row.run_id,
        user_id=row.user_id or "",
        intent=row.intent,
        domain=row.domain,
        model=row.model,
        prompt_version=row.prompt_version,
        tools_used=list(row.tools_used) if row.tools_used is not None else None,
        duration_ms=row.duration_ms,
        tags=list(row.tags) if row.tags is not None else None,
        template_id=row.template_id,
        review_status=row.review_status,
        review_tags=list(row.review_tags),
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        review_note=row.review_note,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
