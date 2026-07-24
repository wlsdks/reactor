from __future__ import annotations

from pathlib import Path

from sqlalchemy.dialects import postgresql

from reactor.api.routers.rag_ingestion_candidates import (
    approved_candidate_next_action,
    approved_candidate_next_actions,
)
from reactor.evals.suite import AgentEvalRegressionSuite
from reactor.persistence.models import Base
from reactor.persistence.rag_ingestion_candidate_store import (
    candidate_find_by_run_id,
    candidate_insert,
    candidate_list,
    candidate_update_review,
)
from reactor.rag.ingestion_candidate_actions import RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE
from reactor.rag.ingestion_candidates import (
    RagIngestionCandidate,
    RagIngestionCandidateStatus,
    build_rag_candidate_content,
)


def test_rag_ingestion_candidate_model_is_registered() -> None:
    assert "rag_ingestion_candidates" in Base.metadata.tables
    table = Base.metadata.tables["rag_ingestion_candidates"]
    assert "ck_rag_ingestion_candidates_status" in {
        constraint.name for constraint in table.constraints
    }
    assert "uq_rag_ingestion_candidates_run" in {
        constraint.name for constraint in table.constraints
    }
    assert "idx_rag_ingestion_candidates_status_captured_at" in {
        index.name for index in table.indexes
    }


def test_rag_ingestion_candidate_table_is_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"rag_ingestion_candidates"' in content
    assert "ck_rag_ingestion_candidates_status" in content
    assert "uq_rag_ingestion_candidates_run" in content
    assert "idx_rag_ingestion_candidates_status_captured_at" in content


def test_rag_ingestion_candidate_sql_builders_match_legacy_store_contract() -> None:
    candidate = RagIngestionCandidate(
        id="c1",
        run_id="run-1",
        user_id="user-1",
        channel="Slack",
        query="q",
        response="a",
    )

    insert_sql = candidate_insert(candidate).compile(dialect=postgresql.dialect())
    list_sql = candidate_list(
        limit=5,
        status=RagIngestionCandidateStatus.PENDING,
        channel="slack",
    ).compile(dialect=postgresql.dialect())
    find_sql = candidate_find_by_run_id("run-1").compile(dialect=postgresql.dialect())
    update_sql = candidate_update_review(
        candidate_id="c1",
        status=RagIngestionCandidateStatus.INGESTED,
        reviewed_by="admin",
        review_comment="good",
        ingested_document_id="doc-1",
    ).compile(dialect=postgresql.dialect())

    assert "INSERT INTO rag_ingestion_candidates" in str(insert_sql)
    assert "ON CONFLICT ON CONSTRAINT uq_rag_ingestion_candidates_run DO NOTHING" in str(insert_sql)
    assert insert_sql.params["run_id"] == "run-1"
    assert "rag_ingestion_candidates.status = " in str(list_sql)
    assert "lower(rag_ingestion_candidates.channel)" in str(list_sql)
    assert "ORDER BY rag_ingestion_candidates.captured_at DESC" in str(list_sql)
    assert "rag_ingestion_candidates.run_id = " in str(find_sql)
    assert "UPDATE rag_ingestion_candidates SET status=" in str(update_sql)
    assert "rag_ingestion_candidates.status = " in str(update_sql)


def test_rag_ingestion_candidate_list_collection_tag_does_not_hide_candidates() -> None:
    collection_sql = candidate_list(
        limit=5,
        status=RagIngestionCandidateStatus.INGESTED,
        tags=["collection:rag-ingestion-candidate"],
    ).compile(dialect=postgresql.dialect())
    candidate_sql = candidate_list(
        limit=5,
        status=RagIngestionCandidateStatus.INGESTED,
        tags=["collection:rag-ingestion-candidate", "rag-candidate:c1"],
    ).compile(dialect=postgresql.dialect())
    unknown_sql = candidate_list(
        limit=5,
        status=RagIngestionCandidateStatus.INGESTED,
        tags=["documents-ask"],
    ).compile(dialect=postgresql.dialect())

    assert "false" not in str(collection_sql).lower()
    assert "rag_ingestion_candidates.id IN " not in str(collection_sql)
    assert "rag_ingestion_candidates.id IN " in str(candidate_sql)
    assert "false" in str(unknown_sql).lower()


def test_rag_candidate_content_preserves_qa_shape() -> None:
    candidate = RagIngestionCandidate(
        run_id="run-1",
        user_id="user-1",
        query="  deployment? ",
        response=" use the runbook ",
    )

    assert build_rag_candidate_content(candidate) == "Q: deployment?\n\nA: use the runbook"


def test_approved_rag_candidate_next_action_previews_first_structured_action() -> None:
    candidate = RagIngestionCandidate(
        id="candidate/needs quoting",
        run_id="run needs quoting",
        user_id="user-1",
        query="How should Reactor cite RAG answers?",
        response="Use citations.",
        status=RagIngestionCandidateStatus.INGESTED,
        ingested_document_id="rag_doc_1",
    )

    action = approved_candidate_next_action(candidate)
    actions = approved_candidate_next_actions(candidate)

    assert action is not None
    assert action == (
        "reactor-admin feedback-submit --rating thumbs_down "
        "--run-id 'run needs quoting' "
        "--query 'How should Reactor cite RAG answers?' "
        "--response 'Use citations.' "
        "--comment 'Approved RAG candidate answer needs regression review' "
        "--source admin_cli "
        "--tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:candidate_needs_quoting --tag documents-ask --tag rag "
        "--tag grounding "
        "--output table"
    )
    assert "&&" not in action
    assert [next_action.id for next_action in actions] == [
        "submit-feedback",
        "inspect-submitted-feedback",
        "export-feedback",
        "bulk-review-candidate-feedback",
        "ask-and-apply-eval",
        "promote-eval",
        "persist-eval-suite",
        "summarize-langsmith",
        "preflight-langsmith",
        "sync-langsmith",
        "generate-hardening-suite",
        "inspect-candidate-feedback",
        "refresh-readiness",
    ]
    actions_by_id = {next_action.id: next_action for next_action in actions}
    assert actions_by_id["inspect-submitted-feedback"].dependsOnActionIds == ["submit-feedback"]
    assert actions_by_id["promote-eval"].dependsOnActionIds == ["ask-and-apply-eval"]
    assert actions_by_id["sync-langsmith"].dependsOnActionIds == ["preflight-langsmith"]
    assert actions_by_id["refresh-readiness"].dependsOnActionIds == [
        "generate-hardening-suite",
        "sync-langsmith",
    ]
    assert actions_by_id["bulk-review-candidate-feedback"].dependsOnActionIds == [
        "refresh-readiness"
    ]
    assert (
        "reactor-documents ask --collection rag-ingestion-candidate "
        "--query 'How should Reactor cite RAG answers?' --require-citation "
        "--eval-case-id case_rag_candidate_candidate_needs_quoting "
        "--eval-case-file evals/cases/case_rag_candidate_candidate_needs_quoting.json "
        "--eval-run-file evals/runs/run_needs_quoting.json "
        "--feedback-rating thumbs_down "
        "--feedback-source admin_cli "
        "--feedback-tag collection:rag-ingestion-candidate "
        "--feedback-tag rag-candidate:candidate_needs_quoting "
        "--feedback-tag documents-ask "
        "--feedback-tag rag "
        "--feedback-tag grounding "
        "--apply-suite-file evals/regression/rag-ingestion-candidate.json "
        "--apply-dataset-name reactor-rag-ingestion-candidate "
        "--apply-require-source-run-id --apply-require-run-file "
        "--apply-require-context-diagnostics "
        "--apply-suite-summary "
        "--langsmith-dry-run-report-file "
        "artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_candidate_needs_quoting.json "
        "--output summary"
    ) in actions_by_id["ask-and-apply-eval"].command
    assert "--feedback-id fb_rag_candidate_candidate_needs_quoting" not in action
    assert (
        "reactor-admin feedback --rating thumbs_down --source admin_cli "
        "--review-status inbox "
        "--tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:candidate_needs_quoting --limit 10 --output table"
    ) == actions[1].command
    assert (
        "reactor-admin feedback-export --rating thumbs_down --source admin_cli "
        "--review-status inbox "
        "--tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:candidate_needs_quoting --limit 10 --output json"
    ) == actions[2].command
    assert (
        "reactor-admin feedback-bulk-review --candidate-tag "
        "rag-candidate:candidate_needs_quoting --source admin_cli --status done --tag promoted "
        "--tag langsmith --tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:candidate_needs_quoting "
        "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
        "--output table"
    ) == actions[3].command
    assert (
        "uv run reactor-replatform-readiness --output "
        "reports/release/replatform-readiness.local.json "
        "--allow-deferred-release-gates "
        "&& uv run reactor-release-smoke-plan "
        "--readiness reports/release/replatform-readiness.local.json "
        "--output reports/release/release-smoke-plan.local.json "
        "&& uv run reactor-release-smoke-run "
        "--plan reports/release/release-smoke-plan.local.json "
        "--preflight-file reports/release/release-smoke-preflight.local.json "
        "--env-file reports/release/release-smoke-preflight.local.env "
        "--report-file reports/release-smoke-run.json "
        "--evidence-output reports/release-evidence.json "
        "--verified-at $(date -u +%Y-%m-%dT%H:%M:%SZ) "
        "--latest-tag $(git describe --tags --abbrev=0) "
        "--readiness-output reports/release-readiness.json "
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync "
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report "
        "langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_candidate_needs_quoting.json"
    ) == actions_by_id["refresh-readiness"].command
    assert "VERIFY_TIMESTAMP" not in actions_by_id["refresh-readiness"].command
    assert actions_by_id["refresh-readiness"].recommendedVersionBump is None
    assert actions_by_id["refresh-readiness"].recommendedTagPattern is None
    assert actions_by_id["refresh-readiness"].minorBoundaryReports == [
        "hardening_suite",
        "langsmith_eval_sync",
    ]
    assert (
        actions_by_id["refresh-readiness"].recommendedTagSource
        == "release_readiness.tagRecommendation.recommendedTag"
    )
    feedback_review_args = (
        "--feedback-review-status done "
        "--feedback-review-tag promoted "
        "--feedback-review-tag langsmith "
        "--feedback-review-tag collection:rag-ingestion-candidate "
        "--feedback-review-tag rag-candidate:candidate_needs_quoting "
        f"--feedback-review-note {RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE!r} "
    )
    assert (
        "uv run reactor-langsmith-eval-sync "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate "
        "--report-file artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_candidate_needs_quoting.json "
        f"{feedback_review_args}"
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync "
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_candidate_needs_quoting.json "
        "--preflight-only --output table"
    ) == actions_by_id["preflight-langsmith"].command
    assert actions_by_id["preflight-langsmith"].requiredEnvAnyOf == [
        ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
    ]
    assert actions_by_id["preflight-langsmith"].recommendedEnv == ["LANGSMITH_ENDPOINT"]
    for action_id in ("summarize-langsmith", "preflight-langsmith", "sync-langsmith"):
        command = actions_by_id[action_id].command
        assert "--feedback-review-status done" in command
        assert "--feedback-review-tag promoted" in command
        assert "--feedback-review-tag langsmith" in command
        assert "--feedback-review-tag collection:rag-ingestion-candidate" in command
        assert "--feedback-review-tag rag-candidate:candidate_needs_quoting" in command
        assert f"--feedback-review-note {RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE!r}" in command
    assert (
        "uv run reactor-langsmith-eval-sync "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate "
        "--report-file artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_candidate_needs_quoting.json "
        f"{feedback_review_args}"
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync "
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_candidate_needs_quoting.json "
        "--output table"
    ) == actions_by_id["sync-langsmith"].command
    assert (
        actions_by_id["sync-langsmith"].preflightFile
        == "reports/release/release-smoke-preflight.local.json"
    )
    assert (
        actions_by_id["sync-langsmith"].preflightEnvTemplate
        == "reports/release/release-smoke-preflight.local.env"
    )
    assert actions_by_id["sync-langsmith"].releaseReadinessFile == "reports/release-readiness.json"
    assert actions_by_id["sync-langsmith"].requiredEnvAnyOf == [
        ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
    ]
    assert actions_by_id["sync-langsmith"].recommendedEnv == ["LANGSMITH_ENDPOINT"]


def test_rag_candidate_next_action_references_loadable_regression_suite() -> None:
    suite_file = Path("evals/regression/rag-ingestion-candidate.json")

    assert suite_file.exists()
    suite = AgentEvalRegressionSuite.load(suite_file)
    assert [case.id for case in suite.cases] == ["case_rag_candidate_grounded_citation"]
    assert [run.run_id for run in suite.runs] == ["run_rag_candidate_grounded_citation"]
    [result] = suite.evaluate()
    assert result.passed is True
    assert result.score == 1.0
    assert result.reasons == ()
