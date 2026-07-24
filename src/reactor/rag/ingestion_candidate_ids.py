from __future__ import annotations

RAG_CANDIDATE_CASE_PREFIX = "case_rag_candidate_"
RAG_CANDIDATE_WORKFLOW_TAG_PREFIX = "rag-candidate:"


def command_slug(value: str, *, fallback: str = "item") -> str:
    slug = "".join(char if char.isalnum() else "_" for char in value.strip()).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or fallback


def is_command_slug(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped) and command_slug(stripped) == stripped


def rag_candidate_case_id(candidate_id: str) -> str:
    return f"{RAG_CANDIDATE_CASE_PREFIX}{command_slug(candidate_id)}"


def rag_candidate_workflow_tag(candidate_id: str) -> str:
    return f"{RAG_CANDIDATE_WORKFLOW_TAG_PREFIX}{command_slug(candidate_id)}"


def rag_candidate_slug_from_case_id(case_id: str) -> str | None:
    stripped = case_id.strip()
    if not stripped.startswith(RAG_CANDIDATE_CASE_PREFIX):
        return None
    candidate_slug = stripped.removeprefix(RAG_CANDIDATE_CASE_PREFIX).strip()
    return candidate_slug if is_command_slug(candidate_slug) else None
