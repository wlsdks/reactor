from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from reactor.api.routers.feedback import (
    bulk_update_feedback_review,
    export_feedback,
    feedback_next_actions,
    feedback_review_version_conflict_detail,
    list_feedback,
)
from reactor.api.schemas.feedback import BulkFeedbackReviewUpdateRequest
from reactor.auth.rbac import AuthPrincipal, UserRole
from reactor.rag.ingestion_candidate_actions import RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE
from reactor.release.readiness_actions import release_readiness_command_for_reports
from reactor.slack.feedback import Feedback, FeedbackRating


class RecordingFeedbackStore:
    def __init__(self) -> None:
        self.list_calls: list[dict[str, object]] = []

    async def list(self, **kwargs: object) -> list[Feedback]:
        self.list_calls.append(dict(kwargs))
        return [
            Feedback(
                feedback_id="fb_1",
                tenant_id="tenant_1",
                query="documents-ask RAG answer missed citation evidence",
                response="Use [runbook.md].",
                rating=FeedbackRating.THUMBS_DOWN,
                session_id="session_1",
                run_id="run_rag_candidate_c1",
                user_id="U1",
                source="admin_cli",
                tags=["collection:rag-ingestion-candidate", "rag-candidate:c1"],
            )
        ]


class RecordingContainer:
    def __init__(self, store: RecordingFeedbackStore) -> None:
        self._store = store

    def feedback_store(self) -> RecordingFeedbackStore:
        return self._store


class BulkUpdateFeedbackStore:
    def __init__(self, feedback: Feedback) -> None:
        self.feedback = feedback
        self.bulk_update_calls: list[dict[str, object]] = []

    async def get(self, *, tenant_id: str, feedback_id: str) -> Feedback | None:
        if tenant_id == self.feedback.tenant_id and feedback_id == self.feedback.feedback_id:
            return self.feedback
        return None

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
        self.bulk_update_calls.append(
            {
                "tenant_id": tenant_id,
                "ids": ids,
                "status": status,
                "tags": tags,
                "note": note,
                "actor": actor,
            }
        )
        return {"updated": ids, "failed": []}


def fake_request(store: RecordingFeedbackStore) -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(reactor=RecordingContainer(store)))
    )


def admin_principal() -> AuthPrincipal:
    return AuthPrincipal(user_id="operator_1", tenant_id="tenant_1", role=UserRole.ADMIN)


async def test_list_feedback_filters_by_eval_case_id() -> None:
    store = RecordingFeedbackStore()

    response = await list_feedback(
        fake_request(store),  # pyright: ignore[reportArgumentType]
        admin_principal(),
        reviewStatus="inbox",
        caseId=" case_rag_candidate_c1 ",
        limit=10,
    )

    assert store.list_calls == [
        {
            "tenant_id": "tenant_1",
            "rating": None,
            "source": None,
            "review_status": "inbox",
            "tags": None,
            "case_id": "case_rag_candidate_c1",
            "limit": 10,
        }
    ]
    assert response.approximateTotal == 1
    assert response.items[0].feedbackId == "fb_1"


async def test_export_feedback_filters_by_eval_case_id() -> None:
    store = RecordingFeedbackStore()

    response = await export_feedback(
        fake_request(store),  # pyright: ignore[reportArgumentType]
        admin_principal(),
        reviewStatus="inbox",
        caseId=" case_rag_candidate_c1 ",
        limit=10,
    )

    assert store.list_calls == [
        {
            "tenant_id": "tenant_1",
            "rating": None,
            "source": None,
            "review_status": "inbox",
            "tags": None,
            "case_id": "case_rag_candidate_c1",
            "limit": 10,
        }
    ]
    assert response.items[0].feedbackId == "fb_1"


async def test_bulk_update_feedback_review_preserves_release_readiness_command() -> None:
    feedback = Feedback(
        feedback_id="fb_1",
        tenant_id="tenant_1",
        query="documents-ask RAG candidate answer missed citation evidence",
        response="Use [runbook.md].",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_1",
        user_id="user_1",
        source="admin_cli",
        tags=["collection:rag-ingestion-candidate", "rag-candidate:c1", "documents-ask"],
    )
    store = BulkUpdateFeedbackStore(feedback)

    response = await bulk_update_feedback_review(
        fake_request(store),  # pyright: ignore[reportArgumentType]
        BulkFeedbackReviewUpdateRequest(
            ids=["fb_1"],
            status="done",
            tags=[
                "promoted",
                "langsmith",
                "collection:rag-ingestion-candidate",
                "rag-candidate:c1",
            ],
            note=RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
        ),
        admin_principal(),
    )

    assert store.bulk_update_calls == [
        {
            "tenant_id": "tenant_1",
            "ids": ["fb_1"],
            "status": "done",
            "tags": [
                "promoted",
                "langsmith",
                "collection:rag-ingestion-candidate",
                "rag-candidate:c1",
            ],
            "note": RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
            "actor": "operator_1",
        }
    ]
    assert response.updated == ["fb_1"]
    assert response.failed == []
    assert response.updatedDetails is not None
    detail = response.updatedDetails[0].model_dump()
    assert detail["feedbackId"] == "fb_1"
    assert detail["nextAction"] == detail["releaseReadinessCommand"]
    assert "uv run reactor-release-smoke-run" in detail["releaseReadinessCommand"]
    assert "--required-readiness-report hardening_suite" in detail["releaseReadinessCommand"]
    assert "--required-readiness-report langsmith_eval_sync" in detail["releaseReadinessCommand"]
    assert detail["readinessReportArg"] == (
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json"
    )


def test_feedback_next_actions_promote_eval_uses_feedback_source_option() -> None:
    feedback = Feedback(
        feedback_id="fb_1",
        tenant_id="tenant_1",
        query="documents-ask RAG answer missed citation evidence for rollback",
        response="Use [runbook.md].",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_1",
        user_id="user_1",
        source="slack_button",
        tags=["rag", "documents-ask"],
    )

    actions = {action.id: action.model_dump() for action in feedback_next_actions(feedback)}

    promote_action = actions["promote-eval"]
    promote_command = promote_action["command"]
    assert "--feedback-source slack_button" in promote_command
    assert "--tag feedback-source:slack_button" not in promote_command
    assert "--tag feedback:fb_1" in promote_command
    assert "--tag feedback-rating:thumbs_down" in promote_command
    assert "--tag rag" in promote_command
    assert "--tag grounding" in promote_command
    assert "--tag citation-failure" in promote_command
    assert "--tag documents-ask" in promote_command
    assert promote_action["feedbackTags"] == [
        "feedback:fb_1",
        "feedback-rating:thumbs_down",
        "rag",
        "grounding",
        "citation-failure",
        "documents-ask",
        "slack",
        "expected-citation:runbook.md",
    ]
    assert promote_action["expectedAnswers"] == ["[runbook.md]"]


def test_feedback_next_actions_promote_eval_tags_expected_answer_citation() -> None:
    feedback = Feedback(
        feedback_id="fb_1",
        tenant_id="tenant_1",
        query="documents-ask RAG answer missed citation evidence",
        response="Use [runbook.md].",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_1",
        user_id="user_1",
        source="admin_cli",
        tags=["rag", "documents-ask"],
    )

    actions = {action.id: action.model_dump() for action in feedback_next_actions(feedback)}

    promote_action = actions["promote-eval"]
    assert "expected-citation:runbook.md" in promote_action["feedbackTags"]
    assert "--tag expected-citation:runbook.md" in promote_action["command"]


def test_feedback_next_actions_preserve_readiness_handoff_fields() -> None:
    feedback = Feedback(
        feedback_id="fb_1",
        tenant_id="tenant_1",
        query="documents-ask RAG candidate answer missed citation evidence",
        response="Use [runbook.md].",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_1",
        user_id="user_1",
        source="admin_cli",
        tags=["collection:rag-ingestion-candidate", "rag-candidate:c1", "documents-ask"],
    )

    actions = {action.id: action.model_dump() for action in feedback_next_actions(feedback)}
    refresh = actions["refresh-readiness"]
    promote = actions["promote-eval"]
    persist = actions["persist-eval-suite"]
    summarize = actions["summarize-langsmith"]

    assert refresh["remediationCommand"] == refresh["command"]
    assert refresh["readinessReportArg"] == (
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json"
    )
    for action in (promote, persist, summarize):
        assert action["releaseReadinessFile"] == "reports/release-readiness.json"
        assert action["feedbackTags"] == [
            "feedback:fb_1",
            "feedback-rating:thumbs_down",
            "rag",
            "grounding",
            "citation-failure",
            "documents-ask",
            "collection:rag-ingestion-candidate",
            "rag-candidate:c1",
            "expected-citation:runbook.md",
        ]
        assert action["expectedAnswers"] == ["[runbook.md]"]
    assert actions["review-done"]["feedbackTags"] == [
        "feedback:fb_1",
        "feedback-rating:thumbs_down",
        "rag",
        "grounding",
        "citation-failure",
        "documents-ask",
        "collection:rag-ingestion-candidate",
        "rag-candidate:c1",
        "expected-citation:runbook.md",
    ]
    assert refresh["minorBoundaryReports"] == ["hardening_suite", "langsmith_eval_sync"]


def test_feedback_next_actions_candidate_bulk_review_preserves_expected_citation_tag() -> None:
    feedback = Feedback(
        feedback_id="fb_1",
        tenant_id="tenant_1",
        query="documents-ask RAG candidate answer missed citation evidence",
        response="Use [runbook.md].",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_1",
        user_id="user_1",
        source="admin_cli",
        tags=["collection:rag-ingestion-candidate", "rag-candidate:c1", "documents-ask"],
    )

    actions = {action.id: action.model_dump() for action in feedback_next_actions(feedback)}

    bulk_review = actions["bulk-review-candidate-feedback"]
    assert "expected-citation:runbook.md" in bulk_review["feedbackTags"]
    assert "--tag expected-citation:runbook.md" in bulk_review["command"]


def test_feedback_review_version_conflict_preserves_readiness_handoff_fields() -> None:
    feedback = Feedback(
        feedback_id="fb_1",
        tenant_id="tenant_1",
        query="documents-ask RAG candidate answer missed citation evidence",
        response="Use [runbook.md].",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_1",
        user_id="user_1",
        source="admin_cli",
        tags=["collection:rag-ingestion-candidate", "rag-candidate:c1", "documents-ask"],
    )

    detail = feedback_review_version_conflict_detail(feedback, expected_version=1)

    assert detail["feedbackId"] == "fb_1"
    assert detail["expectedVersion"] == 1
    assert detail["currentVersion"] == feedback.version
    assert detail["readinessReportArg"] == (
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json"
    )
    assert detail["requiredReadinessReports"] == [
        "hardening_suite",
        "langsmith_eval_sync",
    ]
    assert detail["readinessReports"] == {
        "hardening_suite": "reports/hardening-suite.json",
        "langsmith_eval_sync": (
            "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
        ),
    }


def test_feedback_review_version_conflict_preserves_recovery_next_actions() -> None:
    feedback = Feedback(
        feedback_id="fb_1",
        tenant_id="tenant_1",
        query="documents-ask RAG candidate answer missed citation evidence",
        response="Use [runbook.md].",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_1",
        user_id="user_1",
        source="admin_cli",
        tags=["collection:rag-ingestion-candidate", "rag-candidate:c1", "documents-ask"],
    )

    detail = feedback_review_version_conflict_detail(feedback, expected_version=1)

    ready_action_ids = cast(list[str], detail["readyNextActionIds"])
    blocked_action_ids = cast(list[str], detail["blockedNextActionIds"])
    assert "promote-eval" in ready_action_ids
    assert "review-done" not in ready_action_ids
    assert "refresh-readiness" in blocked_action_ids
    assert "review-done" in blocked_action_ids
    next_actions = cast(list[dict[str, object]], detail["nextActions"])
    actions = {str(action["id"]): action for action in next_actions}
    assert actions["preflight-langsmith"]["feedbackId"] == "fb_1"
    assert actions["preflight-langsmith"]["readinessReportArg"] == (
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json"
    )
    assert actions["refresh-readiness"]["minorBoundaryReports"] == [
        "hardening_suite",
        "langsmith_eval_sync",
    ]
    review_done_command = actions["review-done"]["command"]
    assert isinstance(review_done_command, str)
    assert "reactor-admin feedback-review fb_1" in review_done_command


def test_feedback_next_actions_preserve_feedback_id_on_rag_candidate_handoff() -> None:
    feedback = Feedback(
        feedback_id="fb_1",
        tenant_id="tenant_1",
        query="documents-ask RAG candidate answer missed citation evidence",
        response="Use [runbook.md].",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_1",
        user_id="user_1",
        source="admin_cli",
        tags=["collection:rag-ingestion-candidate", "rag-candidate:c1", "documents-ask"],
    )

    actions = {action.id: action.model_dump() for action in feedback_next_actions(feedback)}

    for action_id in [
        "promote-eval",
        "persist-eval-suite",
        "summarize-langsmith",
        "preflight-langsmith",
        "sync-langsmith",
        "generate-hardening-suite",
        "inspect-candidate-feedback",
        "export-candidate-feedback",
        "bulk-review-candidate-feedback",
        "refresh-readiness",
        "review-done",
    ]:
        assert actions[action_id]["feedbackId"] == "fb_1"
        assert actions[action_id]["evalCaseId"] == "case_rag_candidate_c1"
        assert actions[action_id]["sourceRunId"] == "run_1"
    assert actions["bulk-review-candidate-feedback"]["candidateTag"] == "rag-candidate:c1"
    assert actions["bulk-review-candidate-feedback"]["command"] == (
        "reactor-admin feedback-bulk-review --candidate-tag rag-candidate:c1 "
        "--source admin_cli --status done --tag promoted --tag langsmith "
        "--tag expected-citation:runbook.md "
        "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 "
        "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. "
        "Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
        "--output table"
    )
    assert actions["bulk-review-candidate-feedback"]["reportFile"] == (
        "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
    )
    assert actions["bulk-review-candidate-feedback"]["releaseReadinessFile"] == (
        "reports/release-readiness.json"
    )
    assert actions["bulk-review-candidate-feedback"]["readinessReportArg"] == (
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json"
    )
    assert actions["bulk-review-candidate-feedback"]["requiredReadinessReports"] == [
        "hardening_suite",
        "langsmith_eval_sync",
    ]
    assert actions["bulk-review-candidate-feedback"]["readinessReports"] == {
        "hardening_suite": "reports/hardening-suite.json",
        "langsmith_eval_sync": (
            "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
        ),
    }
    assert actions["preflight-langsmith"]["requiredEnvAnyOf"] == [
        ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
    ]
    assert actions["preflight-langsmith"]["recommendedEnv"] == ["LANGSMITH_ENDPOINT"]
    assert (
        actions["preflight-langsmith"]["preflightFile"]
        == "reports/release/release-smoke-preflight.local.json"
    )
    assert (
        actions["preflight-langsmith"]["preflightEnvTemplate"]
        == "reports/release/release-smoke-preflight.local.env"
    )
    assert actions["preflight-langsmith"]["releaseReadinessFile"] == (
        "reports/release-readiness.json"
    )
    assert actions["preflight-langsmith"]["command"] == (
        "uv run reactor-langsmith-eval-sync "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate "
        "--report-file artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json "
        "--preflight-only --output table"
    )
    assert actions["preflight-langsmith"]["envFileCommand"] == (
        "uv run reactor-langsmith-eval-sync "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate "
        "--report-file artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json "
        "--preflight-only --output table "
        "--env-file reports/release/release-smoke-preflight.local.env"
    )
    assert (
        actions["preflight-langsmith"]["remediationCommand"]
        == (actions["preflight-langsmith"]["command"])
    )
    assert actions["sync-langsmith"]["requiredEnvAnyOf"] == [
        ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
    ]
    assert actions["sync-langsmith"]["recommendedEnv"] == ["LANGSMITH_ENDPOINT"]
    assert actions["sync-langsmith"]["remediationCommand"] == (actions["sync-langsmith"]["command"])
    assert actions["sync-langsmith"]["command"] == (
        "uv run reactor-langsmith-eval-sync "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate "
        "--report-file artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json "
        "--output table"
    )
    assert actions["sync-langsmith"]["envFileCommand"] == (
        "uv run reactor-langsmith-eval-sync "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate "
        "--report-file artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json "
        "--output table "
        "--env-file reports/release/release-smoke-preflight.local.env"
    )
    assert actions["sync-langsmith"][
        "releaseReadinessCommand"
    ] == release_readiness_command_for_reports(
        required_reports=["hardening_suite", "langsmith_eval_sync"],
        report_files={
            "hardening_suite": "reports/hardening-suite.json",
            "langsmith_eval_sync": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
            ),
        },
    )
    assert actions["review-done"]["releaseReadinessFile"] == "reports/release-readiness.json"
    assert (
        "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. "
        "Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
        in actions["review-done"]["command"]
    )


def test_feedback_next_actions_keep_memory_review_when_citation_marker_is_required() -> None:
    feedback = Feedback(
        feedback_id="fb_1",
        tenant_id="tenant_1",
        query="documents-ask memory RAG answer missed citation evidence",
        response="This answer has no bracketed source marker.",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_1",
        user_id="user_1",
        source="admin_cli",
        tags=["documents-ask", "memory"],
    )

    actions = {action.id: action.command for action in feedback_next_actions(feedback)}

    assert "add-citation-marker" in actions
    assert "promote-eval" not in actions
    assert actions["review-memory"].startswith(
        "reactor-memory get --target-user-id user_1 --output table"
    )
    assert "verify-memory-lifecycle" in actions


def test_feedback_next_actions_reject_unsafe_bracketed_citation_marker() -> None:
    feedback = Feedback(
        feedback_id="fb_1",
        tenant_id="tenant_1",
        query="documents-ask RAG answer missed citation evidence",
        response="Use the runbook. [docs/reactor runbooks/rag.md]",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_1",
        user_id="user_1",
        source="admin_cli",
        tags=["documents-ask", "rag", "grounding"],
    )

    actions = {action.id: action.model_dump() for action in feedback_next_actions(feedback)}

    assert "add-citation-marker" in actions
    assert "promote-eval" not in actions
    assert actions["add-citation-marker"]["command"] == (
        "reactor-admin feedback-review fb_1 --if-match 1 --status inbox "
        "--tag citation-marker-required "
        "--note 'Expected citation marker: [replace-with-source-id]' --output table"
    )
