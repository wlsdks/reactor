from __future__ import annotations

from shlex import quote

from reactor.rag.ingestion_candidate_ids import command_slug, rag_candidate_slug_from_case_id

RAG_CANDIDATE_FEEDBACK_REVIEW_ACTION = (
    "reactor-admin feedback --rating thumbs_down "
    "--review-status inbox --tag collection:rag-ingestion-candidate "
    "--limit 10 --output table"
)
RAG_CANDIDATE_REVIEW_ACTION = (
    "reactor-admin rag-candidates --status INGESTED --limit 10 --output table"
)
RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE = (
    "Promoted to regression eval and reviewed in hardening/LangSmith. "
    "Required readiness reports: hardening_suite, langsmith_eval_sync."
)


def rag_candidate_review_action(candidate_tag: str | None = None) -> str:
    if candidate_tag is None or not candidate_tag.strip():
        return RAG_CANDIDATE_REVIEW_ACTION
    return (
        "reactor-admin rag-candidates --status INGESTED "
        "--tag collection:rag-ingestion-candidate "
        f"--tag {quote(candidate_tag.strip())} --limit 10 --output table"
    )


def rag_candidate_feedback_bulk_review_action(
    candidate_tag: str,
    *,
    source: str = "",
    extra_review_tags: list[str] | None = None,
) -> str:
    stripped_candidate_tag = candidate_tag.strip()
    source_arg = f"--source {quote(source.strip())} " if source.strip() else ""
    review_tags = [
        "promoted",
        "langsmith",
        *(extra_review_tags or []),
        "collection:rag-ingestion-candidate",
        stripped_candidate_tag,
    ]
    tag_args = " ".join(f"--tag {quote(tag)}" for tag in dict.fromkeys(review_tags))
    return (
        f"reactor-admin feedback-bulk-review --candidate-tag {quote(stripped_candidate_tag)} "
        f"{source_arg}"
        f"--status done {tag_args} "
        f"--note {quote(RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE)} "
        "--output table"
    )


def rag_candidate_eval_apply_action_command(
    *,
    source_run_id: str,
    case_id: str,
    source_suite: str,
    dataset_name: str,
    feedback_source: str = "",
    extra_tags: list[str] | None = None,
    feedback_review_status: str = "",
    feedback_review_tags: list[str] | None = None,
    feedback_review_note: str = "",
) -> str:
    stripped_source_run_id = source_run_id.strip()
    stripped_case_id = case_id.strip()
    candidate_slug = rag_candidate_slug_from_case_id(stripped_case_id)
    if not stripped_source_run_id or candidate_slug is None:
        return ""
    feedback_source_arg = (
        f"--feedback-source {quote(feedback_source.strip())} " if feedback_source.strip() else ""
    )
    feedback_review_args = ""
    if feedback_review_status.strip():
        feedback_review_args = (
            f"{feedback_review_args}--feedback-review-status "
            f"{quote(feedback_review_status.strip())} "
        )
    for tag in feedback_review_tags or ():
        if tag.strip():
            feedback_review_args = (
                f"{feedback_review_args}--feedback-review-tag {quote(tag.strip())} "
            )
    if feedback_review_note.strip():
        feedback_review_args = (
            f"{feedback_review_args}--feedback-review-note {quote(feedback_review_note.strip())} "
        )
    workflow_tags = [
        "collection:rag-ingestion-candidate",
        f"rag-candidate:{candidate_slug}",
        *(extra_tags or []),
        "documents-ask",
        "rag",
        "grounding",
    ]
    tag_args = " ".join(f"--tag {quote(tag)}" for tag in dict.fromkeys(workflow_tags))
    return (
        f"reactor-runs promote-eval {quote(stripped_source_run_id)} "
        f"--case-id {quote(stripped_case_id)} "
        f"--case-file evals/cases/{quote(stripped_case_id)}.json "
        f"--run-file evals/runs/{quote(command_slug(stripped_source_run_id))}.json "
        f"{tag_args} "
        f"{feedback_source_arg}"
        f"--apply-suite-file {quote(source_suite.strip())} "
        f"--apply-dataset-name {quote(dataset_name.strip())} "
        "--apply-require-source-run-id "
        "--apply-require-run-file --apply-require-context-diagnostics "
        "--apply-suite-summary "
        "--langsmith-dry-run-report-file "
        f"artifacts/langsmith/rag-ingestion-candidate-{quote(stripped_case_id)}.json "
        f"{feedback_review_args}"
        "--output table"
    )
