from __future__ import annotations

from reactor.rag.ingestion_candidate_actions import RAG_CANDIDATE_REVIEW_ACTION
from reactor.rag.ingestion_candidates import RagIngestionCandidate, RagIngestionCandidateStatus
from reactor.release.readiness_actions import release_readiness_command_for_reports


def test_rag_candidate_handoff_actions_are_shared_across_workflow_surfaces() -> None:
    from reactor.api.routers.rag_ingestion_candidates import (
        approved_candidate_next_action,
        approved_candidate_next_actions,
    )
    from reactor.evals.langsmith_dataset import (
        RAG_CANDIDATE_REVIEW_ACTION as langsmith_candidate_action,
    )
    from reactor.release.readiness_contracts import feedback_review_queue_candidate_review_action

    candidate = RagIngestionCandidate(
        id="candidate-1",
        run_id="run-1",
        user_id="user-1",
        query="How should RAG candidate answers cite sources?",
        response="Use the candidate source. [candidate-runbook.md]",
        status=RagIngestionCandidateStatus.INGESTED,
        ingested_document_id="rag_doc_1",
    )

    next_action = approved_candidate_next_action(candidate)

    assert next_action is not None
    assert "--tag collection:rag-ingestion-candidate" in next_action
    assert "--tag rag-candidate:candidate_1" in next_action
    assert RAG_CANDIDATE_REVIEW_ACTION == langsmith_candidate_action
    assert RAG_CANDIDATE_REVIEW_ACTION == feedback_review_queue_candidate_review_action(
        {"collection:rag-ingestion-candidate": 1}
    )

    actions = {action.id: action for action in approved_candidate_next_actions(candidate)}
    submit_feedback = actions["submit-feedback"].model_dump()
    assert "expected-citation:candidate-runbook.md" in submit_feedback["feedbackTags"]
    assert "--tag expected-citation:candidate-runbook.md" in submit_feedback["command"]
    ask_and_apply = actions["ask-and-apply-eval"].model_dump()
    assert "expected-citation:candidate-runbook.md" in ask_and_apply["workflowTags"]
    assert "expected-citation:candidate-runbook.md" in ask_and_apply["feedbackTags"]
    assert "--feedback-tag expected-citation:candidate-runbook.md" in ask_and_apply["command"]
    promote_eval = actions["promote-eval"].model_dump()
    assert "expected-citation:candidate-runbook.md" in promote_eval["workflowTags"]
    assert "expected-citation:candidate-runbook.md" in promote_eval["feedbackTags"]
    assert "--tag expected-citation:candidate-runbook.md" in promote_eval["command"]
    assert "inspect-candidate-feedback" in actions
    assert "review-feedback" not in actions
    bulk_review = actions["bulk-review-candidate-feedback"].model_dump()
    assert bulk_review["candidateTag"] == "rag-candidate:candidate_1"
    assert "expected-citation:candidate-runbook.md" in bulk_review["feedbackTags"]
    assert "--tag expected-citation:candidate-runbook.md" in bulk_review["command"]
    assert bulk_review["command"] == (
        "reactor-admin feedback-bulk-review --candidate-tag rag-candidate:candidate_1 "
        "--source admin_cli --status done --tag promoted --tag langsmith "
        "--tag expected-citation:candidate-runbook.md "
        "--tag collection:rag-ingestion-candidate --tag rag-candidate:candidate_1 "
        "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. "
        "Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
        "--output table"
    )
    assert bulk_review["reportFile"] == (
        "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_candidate_1.json"
    )
    assert bulk_review["readinessReportArg"] == (
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report "
        "langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_candidate_1.json"
    )
    assert bulk_review["requiredReadinessReports"] == [
        "hardening_suite",
        "langsmith_eval_sync",
    ]
    assert bulk_review["readinessReports"] == {
        "hardening_suite": "reports/hardening-suite.json",
        "langsmith_eval_sync": (
            "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_candidate_1.json"
        ),
    }
    hardening = actions["generate-hardening-suite"].model_dump()
    assert hardening["command"] == (
        "uv run reactor-hardening-suite --report-file reports/hardening-suite.json"
    )
    assert hardening["readinessReportArg"] == (
        "--readiness-report hardening_suite=reports/hardening-suite.json"
    )
    refresh = actions["refresh-readiness"].model_dump()
    assert refresh["remediationCommand"] == refresh["command"]
    preflight = actions["preflight-langsmith"].model_dump()
    assert preflight["remediationCommand"] == preflight["command"]
    assert preflight["preflightFile"] == "reports/release/release-smoke-preflight.local.json"
    assert preflight["preflightEnvTemplate"] == "reports/release/release-smoke-preflight.local.env"
    assert preflight["envFileCommand"] == (
        f"{preflight['command']} --env-file reports/release/release-smoke-preflight.local.env"
    )
    assert preflight["releaseReadinessFile"] == "reports/release-readiness.json"
    assert "--required-readiness-report hardening_suite" in preflight["command"]
    assert "--required-readiness-report langsmith_eval_sync" in preflight["command"]
    assert "langsmith_eval_sync=artifacts/langsmith/" in preflight["command"]
    sync = actions["sync-langsmith"].model_dump()
    assert sync["remediationCommand"] == sync["command"]
    assert sync["envFileCommand"] == (
        f"{sync['command']} --env-file reports/release/release-smoke-preflight.local.env"
    )
    assert "--required-readiness-report hardening_suite" in sync["command"]
    assert "--required-readiness-report langsmith_eval_sync" in sync["command"]
    assert "langsmith_eval_sync=artifacts/langsmith/" in sync["command"]
    assert sync["releaseReadinessCommand"] == release_readiness_command_for_reports(
        required_reports=["hardening_suite", "langsmith_eval_sync"],
        report_files={
            "hardening_suite": "reports/hardening-suite.json",
            "langsmith_eval_sync": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_candidate_1.json"
            ),
        },
    )
    assert refresh["recommendedVersionBump"] is None
    assert refresh["recommendedTagPattern"] is None
    assert refresh["minorBoundaryReports"] == ["hardening_suite", "langsmith_eval_sync"]
    assert refresh["recommendedTagSource"] == "release_readiness.tagRecommendation.recommendedTag"
    assert refresh["readinessReportArg"] == (
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report "
        "langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_candidate_1.json"
    )


def test_rag_candidate_handoff_does_not_promote_unknown_citation_marker() -> None:
    from reactor.api.routers.rag_ingestion_candidates import approved_candidate_next_actions

    candidate = RagIngestionCandidate(
        id="candidate-unknown",
        run_id="run-unknown",
        user_id="user-1",
        query="How should RAG candidate answers cite sources?",
        response="Use the candidate source. [unknown]",
        status=RagIngestionCandidateStatus.INGESTED,
        ingested_document_id="rag_doc_1",
    )

    actions = {action.id: action for action in approved_candidate_next_actions(candidate)}

    submit_feedback = actions["submit-feedback"].model_dump()
    ask_and_apply = actions["ask-and-apply-eval"].model_dump()
    assert "expected-citation:unknown" not in submit_feedback["feedbackTags"]
    assert "--tag expected-citation:unknown" not in submit_feedback["command"]
    assert "expected-citation:unknown" not in ask_and_apply["workflowTags"]
    assert "expected-citation:unknown" not in ask_and_apply["feedbackTags"]
    assert "--feedback-tag expected-citation:unknown" not in ask_and_apply["command"]


def test_rag_candidate_review_action_filters_known_candidate_id() -> None:
    from reactor.evals.langsmith_dataset import (
        feedback_review_queue_candidate_review_action as langsmith_candidate_action,
    )
    from reactor.release.readiness_contracts import feedback_review_queue_candidate_review_action

    expected = (
        "reactor-admin rag-candidates --status INGESTED "
        "--tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:grounded_citation --limit 10 --output table"
    )

    assert (
        langsmith_candidate_action(
            {
                "caseIds": ["case_rag_candidate_grounded_citation"],
                "workflowTagCounts": {
                    "collection:rag-ingestion-candidate": 1,
                    "rag-candidate:grounded_citation": 1,
                },
            }
        )
        == expected
    )
    assert (
        feedback_review_queue_candidate_review_action(
            {
                "collection:rag-ingestion-candidate": 1,
                "rag-candidate:grounded_citation": 1,
            },
            case_ids=["case_rag_candidate_grounded_citation"],
        )
        == expected
    )
