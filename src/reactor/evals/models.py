from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from reactor.kernel.citations import is_citation_safe_id
from reactor.kernel.ids import new_id

DOCUMENTS_ASK_TAG = "documents-ask"
GROUNDING_TAG = "grounding"
RAG_TAG = "rag"
FEEDBACK_RATING_TAG_PREFIX = "feedback-rating:"
FEEDBACK_SOURCE_TAG_PREFIX = "feedback-source:"
EXPECTED_CITATION_TAG_PREFIX = "expected-citation:"
ALLOWED_FEEDBACK_RATINGS = frozenset({"thumbs_up", "thumbs_down"})
CITATION_MARKER_PLACEHOLDERS = frozenset({"[replace-with-source-id]"})
COMMAND_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class AgentEvalCaseRecord:
    id: str = field(default_factory=lambda: new_id("eval_case"))
    tenant_id: str = "global"
    name: str = ""
    user_input: str = ""
    expected_answer_contains: tuple[str, ...] = ()
    forbidden_answer_contains: tuple[str, ...] = ()
    expected_tool_names: tuple[str, ...] = ()
    forbidden_tool_names: tuple[str, ...] = ()
    expected_exposed_tool_names: tuple[str, ...] = ()
    forbidden_exposed_tool_names: tuple[str, ...] = ()
    max_tool_exposure_count: int | None = None
    agent_type: str | None = None
    model: str | None = None
    enabled: bool = True
    tags: tuple[str, ...] = ()
    min_score: float = 1.0
    source_run_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        object.__setattr__(self, "tags", normalized_tags(self.tags))

    @property
    def assertion_count(self) -> int:
        return (
            len(self.expected_answer_contains)
            + len(self.forbidden_answer_contains)
            + len(self.expected_tool_names)
            + len(self.forbidden_tool_names)
            + len(self.expected_exposed_tool_names)
            + len(self.forbidden_exposed_tool_names)
            + (1 if self.max_tool_exposure_count is not None else 0)
            + (1 if self.agent_type is not None else 0)
            + (1 if self.model is not None else 0)
        )

    def validate(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not self.id.strip():
            raise ValueError("id is required")
        if not is_command_safe_id(self.id):
            raise ValueError("id must be command-safe")
        if not self.name.strip():
            raise ValueError("name is required")
        if len(self.name) > 255:
            raise ValueError("name must not exceed 255 characters")
        if not self.user_input.strip():
            raise ValueError("userInput is required")
        if not 0 <= self.min_score <= 1:
            raise ValueError("minScore must be between 0 and 1")
        if self.max_tool_exposure_count is not None and self.max_tool_exposure_count < 0:
            raise ValueError("maxToolExposureCount must be >= 0")
        if self.has_blank_feedback_provenance_tag:
            raise ValueError("feedback eval cases require non-empty feedback id")
        if self.has_command_unsafe_feedback_provenance_tag:
            raise ValueError("feedback eval cases require command-safe feedback id")
        if self.has_blank_feedback_rating_tag:
            raise ValueError("feedback eval cases require non-empty feedback rating")
        if self.has_unknown_feedback_rating_tag:
            raise ValueError("feedback eval cases require known feedback rating")
        if self.has_blank_feedback_source_tag:
            raise ValueError("feedback eval cases require non-empty feedback source")
        if self.has_command_unsafe_feedback_source_tag:
            raise ValueError("feedback eval cases require command-safe feedback source")
        if self.has_feedback_provenance_tag and (
            self.source_run_id is None or not self.source_run_id.strip()
        ):
            raise ValueError("feedback eval cases require sourceRunId")
        if self.source_run_id is not None and self.source_run_id.strip():
            if not is_command_safe_id(self.source_run_id):
                raise ValueError("sourceRunId must be command-safe")
        if self.has_feedback_provenance_tag and not self.has_feedback_rating_tag:
            raise ValueError("feedback eval cases require feedback-rating tag")
        if self.has_feedback_provenance_tag and not self.has_feedback_source_tag:
            raise ValueError("feedback eval cases require feedback-source tag")
        if self.requires_documents_ask_citation_marker and any(
            is_placeholder_citation_marker(item) for item in self.expected_answer_contains
        ):
            raise ValueError("documents-ask eval cases cannot use placeholder citation marker")
        if self.requires_documents_ask_citation_marker and not any(
            is_bracketed_citation_marker(item) for item in self.expected_answer_contains
        ):
            raise ValueError("documents-ask eval cases require bracketed citations")
        if self.has_unsafe_expected_citation_marker:
            raise ValueError("documents-ask eval cases require safe citation markers")
        if self.has_blank_expected_citation_tag:
            raise ValueError("documents-ask eval cases require non-empty citation ids")
        if self.has_command_unsafe_expected_citation_tag:
            raise ValueError("documents-ask eval cases require command-safe citation ids")
        if self.has_unmatched_expected_citation_tag:
            raise ValueError(
                "documents-ask eval cases require expected-citation tags to match citation markers"
            )

    @property
    def requires_documents_ask_citation_marker(self) -> bool:
        return DOCUMENTS_ASK_TAG in set(self.tags)

    @property
    def has_feedback_provenance_tag(self) -> bool:
        return any(
            tag.startswith("feedback:") and tag.removeprefix("feedback:").strip()
            for tag in self.tags
        )

    @property
    def has_blank_feedback_provenance_tag(self) -> bool:
        return any(
            tag.startswith("feedback:") and not tag.removeprefix("feedback:").strip()
            for tag in self.tags
        )

    @property
    def has_command_unsafe_feedback_provenance_tag(self) -> bool:
        return any(
            not is_command_safe_id(feedback_id)
            for tag in self.tags
            if tag.startswith("feedback:")
            and (feedback_id := tag.removeprefix("feedback:").strip())
        )

    @property
    def has_blank_feedback_rating_tag(self) -> bool:
        return any(
            tag.startswith(FEEDBACK_RATING_TAG_PREFIX)
            and not tag.removeprefix(FEEDBACK_RATING_TAG_PREFIX).strip()
            for tag in self.tags
        )

    @property
    def has_feedback_rating_tag(self) -> bool:
        return any(
            tag.startswith(FEEDBACK_RATING_TAG_PREFIX)
            and tag.removeprefix(FEEDBACK_RATING_TAG_PREFIX).strip()
            for tag in self.tags
        )

    @property
    def has_unknown_feedback_rating_tag(self) -> bool:
        return any(
            rating not in ALLOWED_FEEDBACK_RATINGS
            for tag in self.tags
            if tag.startswith(FEEDBACK_RATING_TAG_PREFIX)
            and (rating := tag.removeprefix(FEEDBACK_RATING_TAG_PREFIX).strip())
        )

    @property
    def has_blank_feedback_source_tag(self) -> bool:
        return any(
            tag.startswith(FEEDBACK_SOURCE_TAG_PREFIX)
            and not tag.removeprefix(FEEDBACK_SOURCE_TAG_PREFIX).strip()
            for tag in self.tags
        )

    @property
    def has_feedback_source_tag(self) -> bool:
        return any(
            tag.startswith(FEEDBACK_SOURCE_TAG_PREFIX)
            and tag.removeprefix(FEEDBACK_SOURCE_TAG_PREFIX).strip()
            for tag in self.tags
        )

    @property
    def has_command_unsafe_feedback_source_tag(self) -> bool:
        return any(
            not is_command_safe_id(source)
            for tag in self.tags
            if tag.startswith(FEEDBACK_SOURCE_TAG_PREFIX)
            and (source := tag.removeprefix(FEEDBACK_SOURCE_TAG_PREFIX).strip())
        )

    @property
    def has_command_unsafe_expected_citation_tag(self) -> bool:
        return any(
            not is_citation_safe_id(citation_id)
            for tag in self.tags
            if tag.startswith(EXPECTED_CITATION_TAG_PREFIX)
            and (citation_id := tag.removeprefix(EXPECTED_CITATION_TAG_PREFIX).strip())
        )

    @property
    def has_blank_expected_citation_tag(self) -> bool:
        return any(
            tag.startswith(EXPECTED_CITATION_TAG_PREFIX)
            and not tag.removeprefix(EXPECTED_CITATION_TAG_PREFIX).strip()
            for tag in self.tags
        )

    @property
    def has_unmatched_expected_citation_tag(self) -> bool:
        markers = {
            item.strip()
            for item in self.expected_answer_contains
            if is_bracketed_citation_marker(item)
        }
        return any(
            f"[{citation_id}]" not in markers
            for tag in self.tags
            if tag.startswith(EXPECTED_CITATION_TAG_PREFIX)
            and (citation_id := tag.removeprefix(EXPECTED_CITATION_TAG_PREFIX).strip())
            and is_citation_safe_id(citation_id)
        )

    @property
    def has_unsafe_expected_citation_marker(self) -> bool:
        return any(
            not is_citation_safe_id(citation_id)
            for item in self.expected_answer_contains
            if is_bracketed_citation_marker(item) and (citation_id := item.strip()[1:-1].strip())
        )


def is_placeholder_citation_marker(value: str) -> bool:
    normalized = value.strip().lower()
    return any(placeholder in normalized for placeholder in CITATION_MARKER_PLACEHOLDERS)


def normalized_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    normalized = list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
    if (
        RAG_TAG in normalized
        and DOCUMENTS_ASK_TAG in normalized
        and GROUNDING_TAG not in normalized
    ):
        normalized.append(GROUNDING_TAG)
    return tuple(normalized)


def is_command_safe_id(value: str) -> bool:
    stripped = value.strip()
    return (
        bool(stripped) and stripped == value and COMMAND_SAFE_ID_RE.fullmatch(stripped) is not None
    )


def is_bracketed_citation_marker(value: str) -> bool:
    stripped = value.strip()
    return (
        len(stripped) > 2
        and stripped.startswith("[")
        and stripped.endswith("]")
        and stripped.lower() not in CITATION_MARKER_PLACEHOLDERS
    )


@dataclass(frozen=True)
class AgentEvalRunRecord:
    run_id: str
    final_answer: str
    tool_names: tuple[str, ...] = ()
    exposed_tool_names: tuple[str, ...] = ()
    agent_type: str | None = None
    model: str | None = None

    def with_agent_identity(
        self,
        *,
        agent_type: str | None = None,
        model: str | None = None,
    ) -> AgentEvalRunRecord:
        return AgentEvalRunRecord(
            run_id=self.run_id,
            final_answer=self.final_answer,
            tool_names=self.tool_names,
            exposed_tool_names=self.exposed_tool_names,
            agent_type=agent_type,
            model=model,
        )


@dataclass(frozen=True)
class AgentEvalCaseResultRecord:
    case_id: str
    run_id: str
    passed: bool
    score: float
    reasons: tuple[str, ...]
    missing_expected_answer_contains: tuple[str, ...] = ()
    missing_expected_tools: tuple[str, ...] = ()
    forbidden_tools_used: tuple[str, ...] = ()
    missing_expected_exposed_tools: tuple[str, ...] = ()
    forbidden_tools_exposed: tuple[str, ...] = ()
    tool_exposure_count_exceeded: bool = False
    agent_type_mismatch: bool = False
    model_mismatch: bool = False
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_stored_result(
        self, *, tenant_id: str, tier: str = "deterministic"
    ) -> AgentEvalStoredResultRecord:
        return AgentEvalStoredResultRecord(
            tenant_id=tenant_id,
            case_id=self.case_id,
            run_id=self.run_id,
            tier=tier,
            passed=self.passed,
            score=self.score,
            reasons=self.reasons,
            evaluated_at=self.evaluated_at,
        )


@dataclass(frozen=True)
class AgentEvalStoredResultRecord:
    id: str = field(default_factory=lambda: new_id("eval_result"))
    tenant_id: str = "global"
    case_id: str = ""
    run_id: str | None = None
    tier: str = "deterministic"
    passed: bool = False
    score: float = 0.0
    reasons: tuple[str, ...] = ()
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not self.case_id.strip():
            raise ValueError("case_id is required")
        if not self.tier.strip():
            raise ValueError("tier is required")
        if not 0 <= self.score <= 1:
            raise ValueError("score must be between 0 and 1")
