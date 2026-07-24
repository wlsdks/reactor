from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum

from reactor.kernel.ids import new_id


class RagIngestionCandidateStatus(StrEnum):
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    INGESTED = "INGESTED"


@dataclass(frozen=True)
class RagIngestionCandidate:
    run_id: str
    user_id: str
    query: str
    response: str
    id: str = field(default_factory=lambda: new_id("rag_candidate"))
    session_id: str | None = None
    channel: str | None = None
    status: RagIngestionCandidateStatus = RagIngestionCandidateStatus.PENDING
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    review_comment: str | None = None
    ingested_document_id: str | None = None

    def validate(self) -> None:
        for field_name, value in (
            ("id", self.id),
            ("run_id", self.run_id),
            ("user_id", self.user_id),
            ("query", self.query),
            ("response", self.response),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")

    def with_review(
        self,
        *,
        status: RagIngestionCandidateStatus,
        reviewed_by: str,
        review_comment: str | None,
        ingested_document_id: str | None = None,
    ) -> RagIngestionCandidate:
        return replace(
            self,
            status=status,
            reviewed_at=datetime.now(UTC),
            reviewed_by=reviewed_by,
            review_comment=review_comment,
            ingested_document_id=ingested_document_id,
        )


def parse_candidate_status(value: str | None) -> RagIngestionCandidateStatus | None:
    if value is None or not value.strip():
        return None
    try:
        return RagIngestionCandidateStatus(value.strip().upper())
    except ValueError:
        return None


def build_rag_candidate_content(candidate: RagIngestionCandidate) -> str:
    return f"Q: {candidate.query.strip()}\n\nA: {candidate.response.strip()}"


def epoch_millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)
