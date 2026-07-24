from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Protocol, cast

from reactor.evals.models import is_citation_safe_id
from reactor.rag.ingestion_candidate_actions import RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE
from reactor.rag.ingestion_candidate_ids import (
    command_slug,
    is_command_slug,
    rag_candidate_case_id,
    rag_candidate_workflow_tag,
)

CITATION_MARKER_RE = re.compile(r"\[[^\[\]\n]{1,120}\]")
EXPECTED_CITATION_TAG_PREFIX = "expected-citation:"
CITATION_MARKER_PLACEHOLDERS = frozenset({"[replace-with-source-id]"})
MEMORY_PLAIN_LANGUAGE_RE = re.compile(
    r"\b(?:remember|remembered|forget|forgot|delete|deleted|remove|removed)\b"
    r".{0,80}\b(?:my|me|about me|preference|preferences|answer style)\b"
    r"|\b(?:i|we|my|me)\b.{0,40}\b(?:prefer|prefers|preferred)\b"
)
MEMORY_KOREAN_LANGUAGE_RE = re.compile(
    r"(?:기억|잊|삭제|지워).{0,80}(?:선호|취향|말투|응답)"
    r"|(?:선호|취향|말투|응답).{0,80}(?:기억|잊|삭제|지워)"
)


class FeedbackWorkflowRecord(Protocol):
    @property
    def query(self) -> str: ...

    @property
    def response(self) -> str: ...

    @property
    def comment(self) -> str | None: ...

    @property
    def tools_used(self) -> list[str] | None: ...

    @property
    def tags(self) -> list[str] | None: ...

    @property
    def review_tags(self) -> list[str]: ...

    @property
    def review_note(self) -> str | None: ...

    @property
    def run_id(self) -> str | None: ...


def feedback_with_workflow_tags[FeedbackT: FeedbackWorkflowRecord](
    feedback: FeedbackT,
) -> FeedbackT:
    workflow_tags = feedback_workflow_tags(feedback)
    if not workflow_tags:
        return feedback
    tags = list(dict.fromkeys([*(feedback.tags or []), *workflow_tags]))
    return cast(FeedbackT, replace(feedback, tags=tags))  # pyright: ignore[reportArgumentType]


def feedback_workflow_tags(feedback: FeedbackWorkflowRecord) -> list[str]:
    tags: list[str] = []
    if feedback_indicates_rag_citation_failure(feedback):
        tags.extend(["rag", "grounding", "citation-failure"])
        if feedback_requires_citation_marker_eval(feedback):
            tags.append("documents-ask")
    elif feedback_indicates_rag_tool_workflow(feedback):
        tags.extend(["rag", "grounding"])
    if feedback_indicates_rag_candidate_collection(feedback):
        tags.append("collection:rag-ingestion-candidate")
        candidate_id = feedback_rag_candidate_id(feedback)
        if candidate_id is not None:
            tags.append(rag_candidate_workflow_tag(candidate_id))
    if feedback_indicates_memory_workflow(feedback):
        tags.append("memory")
    return list(dict.fromkeys(tags))


def feedback_eval_expected_answers(feedback: FeedbackWorkflowRecord) -> list[str]:
    if not feedback_requires_citation_marker_eval(feedback):
        return []
    values = feedback_signal_values(feedback)
    markers: list[str] = []
    for value in values:
        for match in CITATION_MARKER_RE.findall(value):
            if placeholder_citation_marker(match) or not safe_citation_marker(match):
                continue
            if match not in markers:
                markers.append(match)
    for marker in feedback_expected_citation_tag_markers(feedback):
        if marker not in markers:
            markers.append(marker)
    return markers


def placeholder_citation_marker(value: str) -> bool:
    return value.strip().lower() in CITATION_MARKER_PLACEHOLDERS


def safe_citation_marker(value: str) -> bool:
    stripped = value.strip()
    if not stripped.startswith("[") or not stripped.endswith("]"):
        return False
    return is_citation_safe_id(stripped[1:-1].strip())


def feedback_indicates_rag_citation_failure(feedback: FeedbackWorkflowRecord) -> bool:
    values = feedback_signal_values(feedback)
    normalized = " ".join(values).lower()
    has_rag_signal = "rag" in normalized or "retriev" in normalized or "documents-ask" in normalized
    has_citation_signal = any(
        marker in normalized
        for marker in (
            "citation",
            "source",
            "출처",
            "근거",
            "missing_sources",
        )
    ) or any(feedback_grounding_failure_signal(value) for value in values)
    return has_rag_signal and has_citation_signal


def feedback_grounding_failure_signal(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"rag", "grounding", "documents-ask"}:
        return False
    return "ground" in normalized


def feedback_indicates_rag_tool_workflow(feedback: FeedbackWorkflowRecord) -> bool:
    return any(rag_tool_signal(value) for value in feedback.tools_used or [])


def rag_tool_signal(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("rag:") or "rag." in normalized or "retriev" in normalized


def feedback_indicates_documents_ask(feedback: FeedbackWorkflowRecord) -> bool:
    values = feedback_signal_values(feedback)
    normalized = " ".join(values).lower()
    return "documents-ask" in normalized


def feedback_indicates_memory_workflow(feedback: FeedbackWorkflowRecord) -> bool:
    normalized = " ".join(feedback_signal_values(feedback)).lower()
    has_explicit_memory_signal = any(
        marker in normalized
        for marker in (
            "memory",
            "langmem",
            "preference",
            "supersession",
            "superseded",
            "tombstone",
            "tombstoned",
        )
    )
    return (
        has_explicit_memory_signal
        or MEMORY_PLAIN_LANGUAGE_RE.search(normalized) is not None
        or MEMORY_KOREAN_LANGUAGE_RE.search(normalized) is not None
    )


def feedback_requires_citation_marker_eval(feedback: FeedbackWorkflowRecord) -> bool:
    if feedback_indicates_documents_ask(feedback):
        return True
    if not feedback_indicates_rag_citation_failure(feedback):
        return False
    return any(
        CITATION_MARKER_RE.search(value) for value in feedback_signal_values(feedback)
    ) or bool(feedback_expected_citation_tag_markers(feedback))


def feedback_expected_citation_tag_markers(feedback: FeedbackWorkflowRecord) -> list[str]:
    markers: list[str] = []
    for tag in feedback.tags or []:
        normalized = tag.strip()
        if not normalized.startswith(EXPECTED_CITATION_TAG_PREFIX):
            continue
        citation_id = normalized.removeprefix(EXPECTED_CITATION_TAG_PREFIX).strip()
        if not is_citation_safe_id(citation_id):
            continue
        marker = f"[{citation_id}]"
        if marker not in markers:
            markers.append(marker)
    return markers


def feedback_expected_citation_tags(feedback: FeedbackWorkflowRecord) -> list[str]:
    tags: list[str] = []
    for tag in feedback.tags or []:
        normalized = tag.strip()
        if not normalized.startswith(EXPECTED_CITATION_TAG_PREFIX):
            continue
        citation_id = normalized.removeprefix(EXPECTED_CITATION_TAG_PREFIX).strip()
        if not is_citation_safe_id(citation_id):
            continue
        tags.append(f"{EXPECTED_CITATION_TAG_PREFIX}{citation_id}")
    return list(dict.fromkeys(tags))


def feedback_indicates_rag_candidate_collection(feedback: FeedbackWorkflowRecord) -> bool:
    values = feedback_signal_values(feedback)
    normalized_values = {value.strip().lower() for value in values}
    return (
        "collection:rag-ingestion-candidate" in normalized_values
        or feedback_rag_candidate_id(feedback) is not None
    )


def feedback_rag_candidate_id(feedback: FeedbackWorkflowRecord) -> str | None:
    for value in feedback.tags or []:
        normalized = value.strip()
        if normalized.startswith("rag-candidate:"):
            candidate_id = normalized.removeprefix("rag-candidate:").strip()
            if is_command_slug(candidate_id):
                return candidate_id
    return None


def feedback_rag_candidate_id_from_run_id(run_id: str) -> str:
    run_slug = command_slug(run_id)
    for prefix in ("run_rag_candidate_", "rag_candidate_"):
        candidate_id = run_slug.removeprefix(prefix)
        if candidate_id != run_slug and candidate_id:
            return candidate_id
    return run_slug


def feedback_eval_case_id(
    feedback: FeedbackWorkflowRecord,
    *,
    run_id: str | None = None,
) -> str | None:
    resolved_run_id = (run_id or feedback.run_id or "").strip()
    if not resolved_run_id:
        return None
    candidate_id = feedback_rag_candidate_id(feedback)
    if candidate_id is not None:
        return rag_candidate_case_id(candidate_id)
    if feedback_indicates_rag_candidate_collection(feedback):
        return rag_candidate_case_id(feedback_rag_candidate_id_from_run_id(resolved_run_id))
    return f"case_{safe_command_id(resolved_run_id)}"


def feedback_matches_eval_case_id(feedback: FeedbackWorkflowRecord, case_id: str | None) -> bool:
    expected_case_id = (case_id or "").strip()
    if not expected_case_id:
        return True
    return feedback_eval_case_id(feedback) == expected_case_id


def feedback_review_closed(mapping: Mapping[str, object]) -> bool:
    review_status = mapping.get("reviewStatus")
    if not isinstance(review_status, str) or review_status.strip().lower() != "done":
        return False
    review_tags_value = mapping.get("reviewTags")
    if not non_empty_string_sequence(review_tags_value):
        return False
    review_tags = cast(Sequence[str], review_tags_value)
    normalized_tags = {tag.strip().lower() for tag in review_tags if tag.strip()}
    review_note = mapping.get("reviewNote")
    return (
        {"promoted", "langsmith"}.issubset(normalized_tags)
        and isinstance(review_note, str)
        and review_note.strip() == RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE
    )


def non_empty_string_sequence(value: object) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return False
    items = cast(Sequence[object], value)
    return all(isinstance(item, str) and item.strip() for item in items) and len(items) > 0


def feedback_signal_values(feedback: FeedbackWorkflowRecord) -> list[str]:
    values: list[str] = []
    values.extend(feedback.tools_used or [])
    values.extend(feedback.tags or [])
    values.extend(feedback.review_tags)
    values.extend(
        value
        for value in [feedback.review_note, feedback.comment, feedback.query, feedback.response]
        if value is not None
    )
    return values


def safe_command_id(value: str) -> str:
    return command_slug(value, fallback="run")


def optional_safe_command_id(value: str) -> str:
    stripped = value.strip()
    return command_slug(stripped) if stripped else ""
