from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from reactor.evals.langsmith_dataset import LangSmithEvalDatasetSecretError
from reactor.evals.models import AgentEvalCaseRecord
from reactor.evals.regression_suite_apply import (
    apply_promoted_eval_case,
    format_apply_report_table,
    langsmith_dry_run_summary,
    langsmith_dry_run_table_rows,
    main,
    promoted_eval_suite_snapshot,
    validate_promoted_case_citation_markers,
)
from reactor.evals.suite import AgentEvalRegressionSuite
from reactor.memory.lifecycle_actions import MEMORY_LIFECYCLE_GATE_ACTION
from reactor.rag.ingestion_candidate_actions import (
    RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
    rag_candidate_feedback_bulk_review_action,
)
from reactor.release.readiness_actions import release_readiness_command_for_reports


def test_langsmith_dry_run_summary_preserves_feedback_promotion_provenance() -> None:
    report = {
        "status": "skipped",
        "datasetName": "reactor-regression",
        "examples": 2,
        "caseIds": ["case-feedback-1", "case-baseline"],
        "metadataCaseIds": ["case-feedback-1", "case-baseline"],
        "sourceRunIds": ["run_feedback_1", "run_baseline"],
        "caseSourceRunIds": {
            "case-feedback-1": "run_feedback_1",
            "case-baseline": "run_baseline",
        },
        "source": {
            "suiteFile": "tests/fixtures/agent-eval/regression-suite.json",
            "enabledCases": 2,
        },
        "feedbackPromotion": {
            "caseIds": ["case-feedback-1"],
            "feedbackIds": ["fb_1"],
            "feedbackRatingCounts": {"thumbs_down": 1},
            "feedbackSourceCounts": {"slack_button": 1},
            "workflowTagCounts": {"rag": 1},
            "expectedCitationCounts": {"runbook.md": 1},
        },
        "evidence": {
            "traceGrading": {
                "gradedRuns": 2,
                "grades": [
                    {
                        "caseId": "case-feedback-1",
                        "dimensions": [
                            {
                                "name": "grounding",
                                "score": 1.0,
                                "evidence": {
                                    "retrieved": 2,
                                    "cited": 1,
                                    "uncited": 1,
                                    "citedDocuments": ["tenant-vectorstore-release"],
                                },
                            }
                        ],
                    }
                ],
            }
        },
    }

    assert langsmith_dry_run_summary(
        report,
        report_file=Path("reports/langsmith-eval-sync-dry-run.json"),
    ) == {
        "status": "skipped",
        "datasetName": "reactor-regression",
        "examples": 2,
        "caseIds": ["case-feedback-1", "case-baseline"],
        "metadataCaseIds": ["case-feedback-1", "case-baseline"],
        "sourceRunIds": ["run_feedback_1", "run_baseline"],
        "caseSourceRunIds": {
            "case-feedback-1": "run_feedback_1",
            "case-baseline": "run_baseline",
        },
        "sourceSuite": "tests/fixtures/agent-eval/regression-suite.json",
        "feedbackCases": 1,
        "feedbackIds": 1,
        "feedbackIdList": ["fb_1"],
        "feedbackReviewIds": ["fb_1"],
        "feedbackRatings": {"thumbs_down": 1},
        "feedbackSources": {"slack_button": 1},
        "feedbackWorkflows": {"rag": 1},
        "feedbackExpectedCitations": {"runbook.md": 1},
        "feedbackReviewAction": ("reactor-admin feedback --feedback-id fb_1 --output table"),
        "bulkReviewAction": (
            "reactor-admin feedback-bulk-review fb_1 --status done "
            "--tag promoted --tag langsmith --tag expected-citation:runbook.md --tag rag "
            "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
            "--output table"
        ),
        "gradedRuns": 2,
        "missingRunCases": 0,
        "groundingCitationCases": 1,
        "groundingCitedChunks": 1,
        "groundingUncitedChunks": 1,
        "groundingCitationDocuments": ["tenant-vectorstore-release"],
        "reportFile": "reports/langsmith-eval-sync-dry-run.json",
        "preflightFile": "reports/release/release-smoke-preflight.local.json",
        "preflightEnvTemplate": "reports/release/release-smoke-preflight.local.env",
        "replatformReadinessFile": "reports/release/replatform-readiness.local.json",
        "smokePlanFile": "reports/release/release-smoke-plan.local.json",
        "releaseEvidenceFile": "reports/release-evidence.json",
        "releaseReadinessFile": "reports/release-readiness.json",
        "readinessCommand": (
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
            "--required-readiness-report langsmith_eval_sync "
            "--readiness-report "
            "langsmith_eval_sync=reports/langsmith-eval-sync-dry-run.json"
        ),
    }


def test_langsmith_dry_run_summary_exposes_release_next_actions() -> None:
    report = {
        "status": "skipped",
        "datasetName": "reactor-regression",
        "examples": 1,
        "caseIds": ["case-feedback-1"],
        "metadataCaseIds": ["case-feedback-1"],
        "sourceRunIds": ["run_feedback_1"],
        "caseSourceRunIds": {"case-feedback-1": "run_feedback_1"},
        "source": {
            "suiteFile": "tests/fixtures/agent-eval/regression-suite.json",
            "enabledCases": 1,
        },
        "feedbackPromotion": {
            "caseIds": ["case-feedback-1"],
            "feedbackIds": ["fb_1"],
            "feedbackRatingCounts": {"thumbs_down": 1},
            "feedbackSourceCounts": {"admin_cli": 1},
            "workflowTagCounts": {"rag": 1},
        },
        "releaseGate": {
            "status": "blocked",
            "reason": "dry_run_only",
            "requiredReport": "langsmith_eval_sync",
            "remediation": [
                "run_reactor_langsmith_eval_sync_without_dry_run",
                "include_passed_langsmith_eval_sync_report_in_release_readiness",
            ],
        },
        "evidence": {
            "command": (
                "uv run reactor-langsmith-eval-sync "
                "--suite-file tests/fixtures/agent-eval/regression-suite.json "
                "--dataset-name reactor-regression --dry-run "
                "--report-file reports/langsmith dry run.json"
            ),
            "liveSyncCommand": (
                "uv run reactor-langsmith-eval-sync "
                "--suite-file tests/fixtures/agent-eval/regression-suite.json "
                "--dataset-name reactor-regression "
                "--report-file reports/langsmith dry run.json"
            ),
        },
    }

    summary = langsmith_dry_run_summary(
        report,
        report_file=Path("reports/langsmith dry run.json"),
    )
    expected_readiness_command = release_readiness_command_for_reports(
        required_reports=["langsmith_eval_sync"],
        report_files={"langsmith_eval_sync": "reports/langsmith dry run.json"},
    )

    assert summary["nextActions"] == [
        {
            "id": "review-feedback-fb_1",
            "label": "Review feedback promoted into the LangSmith eval report",
            "command": "reactor-admin feedback --feedback-id fb_1 --output table",
            "feedbackId": "fb_1",
        },
        {
            "id": "bulk-review-feedback",
            "label": "Close promoted feedback after LangSmith eval handoff is reviewed",
            "command": (
                "reactor-admin feedback-bulk-review fb_1 --status done "
                "--tag promoted --tag langsmith --tag rag "
                "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
                "--output table"
            ),
        },
        {
            "id": "preflight-langsmith",
            "label": "Preflight the LangSmith eval sync credentials",
            "command": (
                "uv run reactor-langsmith-eval-sync "
                "--suite-file tests/fixtures/agent-eval/regression-suite.json "
                "--dataset-name reactor-regression "
                "--report-file reports/langsmith dry run.json --preflight-only --output table"
            ),
            "requiredEnvAnyOf": [["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]],
            "recommendedEnv": ["LANGSMITH_ENDPOINT"],
            "preflightFile": "reports/release/release-smoke-preflight.local.json",
            "preflightEnvTemplate": "reports/release/release-smoke-preflight.local.env",
            "releaseReadinessFile": "reports/release-readiness.json",
            "releaseReadinessCommand": expected_readiness_command,
            "readinessReportArg": (
                "--readiness-report langsmith_eval_sync='reports/langsmith dry run.json'"
            ),
            "requiredReadinessReports": ["langsmith_eval_sync"],
            "readinessReports": {
                "langsmith_eval_sync": "reports/langsmith dry run.json",
            },
            "remediationCommand": (
                "uv run reactor-langsmith-eval-sync "
                "--suite-file tests/fixtures/agent-eval/regression-suite.json "
                "--dataset-name reactor-regression "
                "--report-file reports/langsmith dry run.json --preflight-only --output table"
            ),
        },
        {
            "id": "sync-langsmith",
            "label": "Run the LangSmith eval sync without dry-run",
            "command": (
                "uv run reactor-langsmith-eval-sync "
                "--suite-file tests/fixtures/agent-eval/regression-suite.json "
                "--dataset-name reactor-regression "
                "--report-file reports/langsmith dry run.json"
            ),
            "requiredEnvAnyOf": [["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]],
            "recommendedEnv": ["LANGSMITH_ENDPOINT"],
            "preflightFile": "reports/release/release-smoke-preflight.local.json",
            "preflightEnvTemplate": "reports/release/release-smoke-preflight.local.env",
            "releaseReadinessFile": "reports/release-readiness.json",
            "releaseReadinessCommand": expected_readiness_command,
            "readinessReportArg": (
                "--readiness-report langsmith_eval_sync='reports/langsmith dry run.json'"
            ),
            "requiredReadinessReports": ["langsmith_eval_sync"],
            "readinessReports": {
                "langsmith_eval_sync": "reports/langsmith dry run.json",
            },
            "remediationCommand": (
                "uv run reactor-langsmith-eval-sync "
                "--suite-file tests/fixtures/agent-eval/regression-suite.json "
                "--dataset-name reactor-regression "
                "--report-file reports/langsmith dry run.json"
            ),
        },
        {
            "id": "refresh-release-readiness",
            "label": "Refresh release readiness with the LangSmith eval sync report",
            "latestTagCommand": "git describe --tags --abbrev=0",
            "recommendedTagSource": "release_readiness.tagRecommendation.recommendedTag",
            "replatformReadinessFile": "reports/release/replatform-readiness.local.json",
            "smokePlanFile": "reports/release/release-smoke-plan.local.json",
            "releaseEvidenceFile": "reports/release-evidence.json",
            "releaseReadinessFile": "reports/release-readiness.json",
            "requiredReadinessReports": ["langsmith_eval_sync"],
            "readinessReports": {
                "langsmith_eval_sync": "reports/langsmith dry run.json",
            },
            "command": (
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
                "--required-readiness-report langsmith_eval_sync "
                "--readiness-report langsmith_eval_sync='reports/langsmith dry run.json'"
            ),
            "envFileCommand": (
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
                "--required-readiness-report langsmith_eval_sync "
                "--readiness-report langsmith_eval_sync='reports/langsmith dry run.json'"
            ),
            "remediationCommand": (
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
                "--required-readiness-report langsmith_eval_sync "
                "--readiness-report langsmith_eval_sync='reports/langsmith dry run.json'"
            ),
            "readinessReportArg": (
                "--readiness-report langsmith_eval_sync='reports/langsmith dry run.json'"
            ),
        },
    ]


def test_apply_report_table_shows_langsmith_release_next_actions() -> None:
    table = format_apply_report_table(
        {
            "langsmithDryRun": {
                "status": "skipped",
                "datasetName": "reactor-regression",
                "nextActions": [
                    {
                        "id": "preflight-langsmith",
                        "label": "Preflight the LangSmith eval sync credentials",
                        "command": (
                            "uv run reactor-langsmith-eval-sync "
                            "--suite-file evals/regression/rag.json "
                            "--dataset-name reactor-regression "
                            "--report-file reports/langsmith.json --preflight-only --output table"
                        ),
                        "requiredEnvAnyOf": [
                            ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                        ],
                        "recommendedEnv": ["LANGSMITH_ENDPOINT"],
                        "preflightFile": "reports/release/release-smoke-preflight.local.json",
                        "preflightEnvTemplate": "reports/release/release-smoke-preflight.local.env",
                        "releaseReadinessFile": "reports/release-readiness.json",
                        "requiredReadinessReports": ["langsmith_eval_sync"],
                        "readinessReports": {
                            "langsmith_eval_sync": "reports/langsmith.json",
                        },
                    },
                    {
                        "id": "sync-langsmith",
                        "label": "Run the LangSmith eval sync without dry-run",
                        "command": (
                            "uv run reactor-langsmith-eval-sync "
                            "--suite-file evals/regression/rag.json "
                            "--dataset-name reactor-regression "
                            "--report-file reports/langsmith.json"
                        ),
                    },
                    {
                        "id": "refresh-release-readiness",
                        "label": "Refresh release readiness with the LangSmith eval sync report",
                        "candidateTag": "rag-candidate:c1",
                        "evalCaseId": "case_rag_candidate_c1",
                        "sourceRunId": "run_rag_candidate_c1",
                        "requiredReviewNote": "Reviewed RAG candidate feedback before release.",
                        "latestTagCommand": "git describe --tags --abbrev=0",
                        "recommendedTagSource": (
                            "release_readiness.tagRecommendation.recommendedTag"
                        ),
                        "recommendedVersionBump": "minor",
                        "recommendedTagPattern": "v1.2.0",
                        "minorBoundaryReports": ["langsmith_eval_sync"],
                        "requiredReadinessReports": ["langsmith_eval_sync"],
                        "readinessReports": {
                            "langsmith_eval_sync": "reports/langsmith.json",
                        },
                        "command": (
                            "uv run reactor-release-smoke-run "
                            "--readiness-report langsmith_eval_sync=reports/langsmith.json"
                        ),
                        "envFileCommand": (
                            "uv run reactor-release-smoke-run "
                            "--readiness-report langsmith_eval_sync=reports/langsmith.json "
                            "--env-file reports/release/release-smoke-preflight.local.env"
                        ),
                        "remediationCommand": (
                            "uv run reactor-release-smoke-run "
                            "--readiness-report langsmith_eval_sync=reports/langsmith.json"
                        ),
                        "readinessReportArg": (
                            "--readiness-report langsmith_eval_sync=reports/langsmith.json"
                        ),
                    },
                ],
            }
        }
    )

    rows = dict(line.split(maxsplit=1) for line in table.splitlines()[1:])
    assert rows["langsmithNextActionIds"] == (
        "preflight-langsmith,sync-langsmith,refresh-release-readiness"
    )
    assert rows["langsmithNextAction.preflight-langsmith"] == (
        "uv run reactor-langsmith-eval-sync "
        "--suite-file evals/regression/rag.json "
        "--dataset-name reactor-regression "
        "--report-file reports/langsmith.json --preflight-only --output table"
    )
    assert rows["langsmithNextAction.preflight-langsmith.requiredEnvAnyOf.0"] == (
        "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    )
    assert rows["langsmithNextAction.preflight-langsmith.recommendedEnv"] == ("LANGSMITH_ENDPOINT")
    assert (
        rows["langsmithNextAction.preflight-langsmith.preflightFile"]
        == "reports/release/release-smoke-preflight.local.json"
    )
    assert (
        rows["langsmithNextAction.preflight-langsmith.preflightEnvTemplate"]
        == "reports/release/release-smoke-preflight.local.env"
    )
    assert (
        rows["langsmithNextAction.preflight-langsmith.releaseReadinessFile"]
        == "reports/release-readiness.json"
    )
    assert rows["langsmithNextAction.sync-langsmith"] == (
        "uv run reactor-langsmith-eval-sync "
        "--suite-file evals/regression/rag.json "
        "--dataset-name reactor-regression "
        "--report-file reports/langsmith.json"
    )
    assert rows["langsmithNextAction.refresh-release-readiness"] == (
        "uv run reactor-release-smoke-run "
        "--readiness-report langsmith_eval_sync=reports/langsmith.json"
    )
    assert rows["langsmithNextAction.refresh-release-readiness.envFileCommand"] == (
        "uv run reactor-release-smoke-run "
        "--readiness-report langsmith_eval_sync=reports/langsmith.json "
        "--env-file reports/release/release-smoke-preflight.local.env"
    )
    assert (
        rows["langsmithNextAction.refresh-release-readiness.requiredReadinessReports"]
        == "langsmith_eval_sync"
    )
    assert (
        rows["langsmithNextAction.refresh-release-readiness.readinessReports.langsmith_eval_sync"]
        == "reports/langsmith.json"
    )
    assert rows["langsmithNextAction.refresh-release-readiness.remediationCommand"] == (
        "uv run reactor-release-smoke-run "
        "--readiness-report langsmith_eval_sync=reports/langsmith.json"
    )
    assert rows["langsmithNextAction.refresh-release-readiness.readinessReportArg"] == (
        "--readiness-report langsmith_eval_sync=reports/langsmith.json"
    )
    assert rows["langsmithNextAction.refresh-release-readiness.requiredReviewNote"] == (
        "Reviewed RAG candidate feedback before release."
    )
    assert rows["langsmithNextAction.refresh-release-readiness.candidateTag"] == "rag-candidate:c1"
    assert (
        rows["langsmithNextAction.refresh-release-readiness.evalCaseId"] == "case_rag_candidate_c1"
    )
    assert (
        rows["langsmithNextAction.refresh-release-readiness.sourceRunId"] == "run_rag_candidate_c1"
    )
    assert rows["langsmithNextAction.refresh-release-readiness.latestTagCommand"] == (
        "git describe --tags --abbrev=0"
    )
    assert rows["langsmithNextAction.refresh-release-readiness.recommendedTagSource"] == (
        "release_readiness.tagRecommendation.recommendedTag"
    )
    assert rows["langsmithNextAction.refresh-release-readiness.recommendedVersionBump"] == "minor"
    assert rows["langsmithNextAction.refresh-release-readiness.recommendedTagPattern"] == "v1.2.0"
    assert (
        rows["langsmithNextAction.refresh-release-readiness.minorBoundaryReports"]
        == "langsmith_eval_sync"
    )


def test_langsmith_dry_run_summary_uses_workflow_review_queue_for_multiple_feedback() -> None:
    report = {
        "status": "skipped",
        "datasetName": "reactor-regression",
        "examples": 2,
        "caseIds": ["case-feedback-1", "case-feedback-2"],
        "metadataCaseIds": ["case-feedback-1", "case-feedback-2"],
        "feedbackPromotion": {
            "caseIds": ["case-feedback-1", "case-feedback-2"],
            "feedbackIds": ["fb_1", "fb_2"],
            "feedbackRatingCounts": {"thumbs_down": 2},
            "workflowTagCounts": {"documents-ask": 1, "rag": 2},
        },
    }

    summary = langsmith_dry_run_summary(
        report,
        report_file=Path("reports/langsmith-eval-sync-dry-run.json"),
    )

    assert summary["feedbackReviewAction"] == (
        "reactor-admin feedback --rating thumbs_down --review-status inbox "
        "--tag rag --limit 10 --output table"
    )


def test_langsmith_dry_run_summary_preserves_multiple_feedback_id_review_actions() -> None:
    report = {
        "status": "skipped",
        "datasetName": "reactor-regression",
        "examples": 2,
        "caseIds": ["case-feedback-1", "case-feedback-2"],
        "metadataCaseIds": ["case-feedback-1", "case-feedback-2"],
        "feedbackPromotion": {
            "caseIds": ["case-feedback-1", "case-feedback-2"],
            "feedbackIds": ["fb_1", "fb_2"],
        },
    }

    summary = langsmith_dry_run_summary(
        report,
        report_file=Path("reports/langsmith-eval-sync-dry-run.json"),
    )

    assert summary["feedbackReviewActions"] == [
        "reactor-admin feedback --feedback-id fb_1 --output table",
        "reactor-admin feedback --feedback-id fb_2 --output table",
    ]
    table = format_apply_report_table({"langsmithDryRun": summary})
    rows = dict(line.split(maxsplit=1) for line in table.splitlines()[1:])
    assert rows["langsmithFeedbackReviewActions"] == (
        "reactor-admin feedback --feedback-id fb_1 --output table;"
        "reactor-admin feedback --feedback-id fb_2 --output table"
    )
    assert "langsmithFeedbackReviewAction" not in rows


def test_langsmith_dry_run_summary_exposes_multiple_feedback_review_next_actions() -> None:
    report = {
        "status": "skipped",
        "datasetName": "reactor-regression",
        "examples": 2,
        "caseIds": ["case-feedback-1", "case-feedback-2"],
        "metadataCaseIds": ["case-feedback-1", "case-feedback-2"],
        "feedbackPromotion": {
            "caseIds": ["case-feedback-1", "case-feedback-2"],
            "feedbackIds": ["fb_1", "fb_2"],
        },
        "releaseGate": {
            "status": "blocked",
            "reason": "dry_run_only",
            "requiredReport": "langsmith_eval_sync",
            "remediation": ["run_reactor_langsmith_eval_sync_without_dry_run"],
        },
        "evidence": {
            "liveSyncCommand": (
                "uv run reactor-langsmith-eval-sync "
                "--suite-file tests/fixtures/agent-eval/regression-suite.json "
                "--dataset-name reactor-regression "
                "--report-file reports/langsmith-dry-run.json"
            ),
        },
    }

    summary = langsmith_dry_run_summary(
        report,
        report_file=Path("reports/langsmith-dry-run.json"),
    )

    next_actions = cast(list[dict[str, object]], summary["nextActions"])
    review_actions = [
        action for action in next_actions if str(action["id"]).startswith("review-feedback")
    ]

    assert review_actions == [
        {
            "id": "review-feedback-fb_1",
            "label": "Review feedback promoted into the LangSmith eval report",
            "command": "reactor-admin feedback --feedback-id fb_1 --output table",
            "feedbackId": "fb_1",
        },
        {
            "id": "review-feedback-fb_2",
            "label": "Review feedback promoted into the LangSmith eval report",
            "command": "reactor-admin feedback --feedback-id fb_2 --output table",
            "feedbackId": "fb_2",
        },
    ]


def test_langsmith_dry_run_summary_uses_unique_multiple_feedback_review_action_ids() -> None:
    report = {
        "status": "skipped",
        "datasetName": "reactor-regression",
        "examples": 2,
        "caseIds": ["case-feedback-1", "case-feedback-2"],
        "metadataCaseIds": ["case-feedback-1", "case-feedback-2"],
        "feedbackPromotion": {
            "caseIds": ["case-feedback-1", "case-feedback-2"],
            "feedbackIds": ["fb_1", "fb_2"],
        },
        "releaseGate": {
            "status": "blocked",
            "reason": "dry_run_only",
            "requiredReport": "langsmith_eval_sync",
            "remediation": ["run_reactor_langsmith_eval_sync_without_dry_run"],
        },
    }

    summary = langsmith_dry_run_summary(
        report,
        report_file=Path("reports/langsmith-dry-run.json"),
    )

    next_actions = cast(list[dict[str, object]], summary["nextActions"])
    review_action_ids = [
        action["id"] for action in next_actions if str(action["id"]).startswith("review-feedback")
    ]

    assert review_action_ids == ["review-feedback-fb_1", "review-feedback-fb_2"]


def test_apply_report_table_shows_langsmith_product_boundary_readiness_command() -> None:
    table = format_apply_report_table(
        {
            "langsmithDryRun": {
                "status": "skipped",
                "datasetName": "reactor-rag-ingestion-candidate",
                "productBoundaryReadinessCommand": (
                    "uv run reactor-release-smoke-run "
                    "--required-readiness-report hardening_suite "
                    "--required-readiness-report langsmith_eval_sync"
                ),
            },
        }
    )

    assert (
        "langsmithProductBoundaryReadinessCommand  uv run reactor-release-smoke-run "
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync\n"
    ) in table


def test_langsmith_dry_run_summary_preserves_product_boundary_next_action_reports() -> None:
    report = {
        "status": "skipped",
        "datasetName": "reactor-rag-ingestion-candidate",
        "examples": 1,
        "caseIds": ["case_rag_candidate_grounded_citation"],
        "metadataCaseIds": ["case_rag_candidate_grounded_citation"],
        "sourceRunIds": ["run_rag_candidate_grounded_citation"],
        "caseSourceRunIds": {
            "case_rag_candidate_grounded_citation": "run_rag_candidate_grounded_citation"
        },
        "liveSyncCommand": (
            "uv run reactor-langsmith-eval-sync "
            "--suite-file evals/regression/rag-ingestion-candidate.json "
            "--dataset-name reactor-rag-ingestion-candidate "
            "--report-file reports/langsmith-rag-candidate.json"
        ),
        "readinessCommand": (
            "uv run reactor-release-smoke-run "
            "--required-readiness-report hardening_suite "
            "--required-readiness-report langsmith_eval_sync "
            "--readiness-report hardening_suite=reports/hardening-suite.json "
            "--readiness-report langsmith_eval_sync=reports/langsmith-rag-candidate.json"
        ),
        "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
        "readinessReports": {
            "hardening_suite": "reports/hardening-suite.json",
            "langsmith_eval_sync": "reports/langsmith-rag-candidate.json",
        },
        "productCapabilityBoundary": {
            "minorEligible": False,
            "capability": "rag_ingest_to_feedback_eval_langsmith_readiness",
            "evidence": [
                "rag_ingestion_candidate_feedback_queue",
                "langsmith_trace_grading",
                "release_readiness_command",
            ],
            "missingEvidence": ["rag_ingestion_lifecycle"],
        },
        "productBoundaryReadinessCommand": (
            "uv run reactor-release-smoke-run "
            "--required-readiness-report hardening_suite "
            "--required-readiness-report langsmith_eval_sync "
            "--readiness-report hardening_suite=reports/hardening-suite.json "
            "--readiness-report langsmith_eval_sync=reports/langsmith-rag-candidate.json"
        ),
        "releaseGate": {
            "status": "blocked",
            "blocksReleaseReadiness": True,
            "reason": "dry_run_only",
            "requiredReport": "langsmith_eval_sync",
            "remediation": ["run_reactor_langsmith_eval_sync_without_dry_run"],
        },
    }

    summary = langsmith_dry_run_summary(
        report,
        report_file=Path("reports/langsmith-rag-candidate.json"),
    )

    assert summary["readinessCommand"] == report["productBoundaryReadinessCommand"]
    assert summary["requiredReadinessReports"] == ["hardening_suite", "langsmith_eval_sync"]
    assert summary["readinessReports"] == {
        "hardening_suite": "reports/hardening-suite.json",
        "langsmith_eval_sync": "reports/langsmith-rag-candidate.json",
    }
    assert summary["productCapabilityBoundary"] == report["productCapabilityBoundary"]
    assert summary["productBoundaryReadinessCommand"] == report["productBoundaryReadinessCommand"]
    next_actions = cast(list[dict[str, object]], summary["nextActions"])
    sync_action = next(action for action in next_actions if action["id"] == "sync-langsmith")
    assert sync_action["preflightFile"] == "reports/release/release-smoke-preflight.local.json"
    assert sync_action["preflightEnvTemplate"] == (
        "reports/release/release-smoke-preflight.local.env"
    )
    assert sync_action["releaseReadinessFile"] == "reports/release-readiness.json"
    hardening_action = next(
        action for action in next_actions if action["id"] == "generate-hardening-suite"
    )
    assert hardening_action == {
        "id": "generate-hardening-suite",
        "label": "Generate the hardening suite report required for minor boundary review",
        "command": "uv run reactor-hardening-suite --report-file reports/hardening-suite.json",
        "readinessReportArg": "--readiness-report hardening_suite=reports/hardening-suite.json",
        "releaseReadinessCommand": report["productBoundaryReadinessCommand"],
        "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
        "readinessReports": {
            "hardening_suite": "reports/hardening-suite.json",
            "langsmith_eval_sync": "reports/langsmith-rag-candidate.json",
        },
    }
    refresh_action = next(
        action for action in next_actions if action["id"] == "refresh-release-readiness"
    )
    assert refresh_action["command"] == report["productBoundaryReadinessCommand"]
    assert refresh_action["remediationCommand"] == report["productBoundaryReadinessCommand"]
    assert refresh_action["readinessReportArg"] == (
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=reports/langsmith-rag-candidate.json"
    )
    assert refresh_action["requiredReadinessReports"] == [
        "hardening_suite",
        "langsmith_eval_sync",
    ]
    assert refresh_action["readinessReports"] == {
        "hardening_suite": "reports/hardening-suite.json",
        "langsmith_eval_sync": "reports/langsmith-rag-candidate.json",
    }
    assert "recommendedVersionBump" not in refresh_action
    assert "recommendedTagPattern" not in refresh_action
    assert refresh_action["minorBoundaryReports"] == ["hardening_suite", "langsmith_eval_sync"]
    assert (
        refresh_action["recommendedTagSource"]
        == "release_readiness.tagRecommendation.recommendedTag"
    )


def test_langsmith_dry_run_summary_scopes_workflow_review_action_by_source() -> None:
    report = {
        "status": "skipped",
        "datasetName": "reactor-regression",
        "examples": 2,
        "caseIds": ["case-feedback-1", "case-feedback-2"],
        "metadataCaseIds": ["case-feedback-1", "case-feedback-2"],
        "feedbackPromotion": {
            "caseIds": ["case-feedback-1", "case-feedback-2"],
            "feedbackIds": ["fb_1", "fb_2"],
            "feedbackRatingCounts": {"thumbs_down": 2},
            "feedbackSourceCounts": {"slack_button": 2},
            "workflowTagCounts": {"documents-ask": 2, "rag": 2},
        },
    }

    summary = langsmith_dry_run_summary(
        report,
        report_file=Path("reports/langsmith-eval-sync-dry-run.json"),
    )

    assert summary["feedbackReviewAction"] == (
        "reactor-admin feedback --rating thumbs_down --source slack_button "
        "--review-status inbox --tag rag --limit 10 --output table"
    )
    assert "feedbackReviewActions" not in summary


def test_langsmith_dry_run_summary_bulk_review_omits_case_local_workflow_tags() -> None:
    report = {
        "status": "skipped",
        "datasetName": "reactor-regression",
        "examples": 2,
        "caseIds": ["case-feedback-1", "case-feedback-2"],
        "metadataCaseIds": ["case-feedback-1", "case-feedback-2"],
        "feedbackPromotion": {
            "caseIds": ["case-feedback-1", "case-feedback-2"],
            "feedbackIds": ["fb_1"],
            "feedbackReviewIds": ["fb_1"],
            "feedbackRatingCounts": {"thumbs_down": 2},
            "workflowTagCounts": {"documents-ask": 1, "rag": 1},
        },
    }

    summary = langsmith_dry_run_summary(
        report,
        report_file=Path("reports/langsmith-eval-sync-dry-run.json"),
    )

    assert summary["bulkReviewAction"] == (
        "reactor-admin feedback-bulk-review fb_1 --status done "
        "--tag promoted --tag langsmith "
        "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
        "--output table"
    )


def test_langsmith_dry_run_summary_prefers_candidate_review_queue_for_candidate_feedback() -> None:
    report = {
        "status": "skipped",
        "datasetName": "reactor-rag-ingestion-candidate",
        "examples": 2,
        "caseIds": ["case_rag_candidate_c1", "case_rag_candidate_c1_retry"],
        "metadataCaseIds": ["case_rag_candidate_c1", "case_rag_candidate_c1_retry"],
        "feedbackPromotion": {
            "caseIds": ["case_rag_candidate_c1", "case_rag_candidate_c1_retry"],
            "feedbackIds": ["fb_1", "fb_2"],
            "feedbackRatingCounts": {"thumbs_down": 2},
            "workflowTagCounts": {
                "collection:rag-ingestion-candidate": 2,
                "rag-candidate:c1": 2,
                "rag": 2,
            },
        },
    }

    summary = langsmith_dry_run_summary(
        report,
        report_file=Path("artifacts/langsmith/rag-ingestion-candidate-c1.json"),
    )

    assert summary["feedbackReviewAction"] == (
        "reactor-admin feedback --rating thumbs_down "
        "--review-status inbox "
        "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 "
        "--limit 10 --output table"
    )
    assert summary["bulkReviewAction"] == rag_candidate_feedback_bulk_review_action(
        "rag-candidate:c1"
    )


def test_langsmith_dry_run_summary_recovers_candidate_review_action_from_candidate_tag() -> None:
    report = {
        "status": "skipped",
        "datasetName": "reactor-rag-ingestion-candidate",
        "examples": 1,
        "caseIds": ["case_rag_candidate_c1"],
        "metadataCaseIds": ["case_rag_candidate_c1"],
        "caseSourceRunIds": {"case_rag_candidate_c1": "run_rag_candidate_c1"},
        "feedbackReviewQueue": {
            "caseIds": ["case_rag_candidate_c1"],
            "feedbackRatingCounts": {"thumbs_down": 1},
            "feedbackSourceCounts": {"slack_button": 1},
            "workflowTagCounts": {
                "rag-candidate:c1": 1,
                "rag": 1,
            },
        },
    }

    summary = langsmith_dry_run_summary(
        report,
        report_file=Path("artifacts/langsmith/rag-ingestion-candidate-c1.json"),
    )

    assert summary["feedbackReviewQueue"] == {
        "caseIds": ["case_rag_candidate_c1"],
        "candidateTag": "rag-candidate:c1",
        "feedbackRatingCounts": {"thumbs_down": 1},
        "feedbackSourceCounts": {"slack_button": 1},
        "workflowTagCounts": {
            "rag-candidate:c1": 1,
            "rag": 1,
        },
        "reviewAction": (
            "reactor-admin feedback --rating thumbs_down "
            "--source slack_button "
            "--review-status inbox "
            "--case-id case_rag_candidate_c1 "
            "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 "
            "--limit 10 --output table"
        ),
        "exportAction": (
            "reactor-admin feedback-export --rating thumbs_down "
            "--source slack_button "
            "--review-status inbox "
            "--case-id case_rag_candidate_c1 "
            "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 "
            "--limit 10 --output json"
        ),
        "candidateReviewAction": (
            "reactor-admin rag-candidates --status INGESTED "
            "--tag collection:rag-ingestion-candidate "
            "--tag rag-candidate:c1 --limit 10 --output table"
        ),
        "bulkReviewAction": (
            "reactor-admin feedback-bulk-review --candidate-tag rag-candidate:c1 "
            "--source slack_button --status done --tag promoted --tag langsmith "
            "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 "
            "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
            "--output table"
        ),
    }
    assert summary["nextActions"] == [
        {
            "id": "review-feedback-queue",
            "label": "Review feedback waiting for LangSmith eval source metadata",
            "command": (
                "reactor-admin feedback --rating thumbs_down "
                "--source slack_button "
                "--review-status inbox "
                "--case-id case_rag_candidate_c1 "
                "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 "
                "--limit 10 --output table"
            ),
            "evalCaseId": "case_rag_candidate_c1",
            "sourceRunId": "run_rag_candidate_c1",
        },
        {
            "id": "review-rag-candidate-c1",
            "label": "Review the RAG ingestion candidate behind the LangSmith report",
            "command": (
                "reactor-admin rag-candidates --status INGESTED "
                "--tag collection:rag-ingestion-candidate "
                "--tag rag-candidate:c1 --limit 10 --output table"
            ),
            "candidateTag": "rag-candidate:c1",
            "evalCaseId": "case_rag_candidate_c1",
            "sourceRunId": "run_rag_candidate_c1",
        },
        {
            "id": "bulk-review-feedback-queue",
            "label": "Close queued feedback after the LangSmith eval handoff is reviewed",
            "command": (
                "reactor-admin feedback-bulk-review --candidate-tag rag-candidate:c1 "
                "--source slack_button --status done --tag promoted --tag langsmith "
                "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 "
                "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
                "--output table"
            ),
            "candidateTag": "rag-candidate:c1",
            "evalCaseId": "case_rag_candidate_c1",
            "sourceRunId": "run_rag_candidate_c1",
        },
    ]


def test_langsmith_dry_run_summary_preserves_release_gate_remediation_command() -> None:
    summary = langsmith_dry_run_summary(
        {
            "status": "skipped",
            "datasetName": "reactor-rag-ingestion-candidate",
            "releaseGate": {
                "status": "blocked",
                "reason": "feedback_review_queue_source_missing",
                "requiredReport": "langsmith_eval_sync",
                "remediation": ["resubmit_feedback_with_source_metadata"],
                "remediationCommand": (
                    "reactor-admin feedback --rating thumbs_down "
                    "--tag collection:rag-ingestion-candidate --output table"
                ),
            },
        },
        report_file=Path("reports/langsmith-eval-sync-dry-run.json"),
    )

    release_gate = summary["releaseGate"]
    assert isinstance(release_gate, dict)
    assert release_gate["remediationCommand"] == (
        "reactor-admin feedback --rating thumbs_down "
        "--tag collection:rag-ingestion-candidate --output table"
    )


def test_langsmith_dry_run_summary_recovers_memory_queue_lifecycle_action() -> None:
    report = {
        "status": "skipped",
        "datasetName": "reactor-regression",
        "examples": 1,
        "caseIds": ["memory-supersession-review"],
        "metadataCaseIds": ["memory-supersession-review"],
        "feedbackReviewQueue": {
            "caseIds": ["memory-supersession-review"],
            "feedbackRatingCounts": {"thumbs_down": 1},
            "workflowTagCounts": {"memory": 1},
            "reviewAction": (
                "reactor-admin feedback --rating thumbs_down --review-status inbox "
                "--tag memory --limit 10 --output table"
            ),
        },
    }

    summary = langsmith_dry_run_summary(
        report,
        report_file=Path("reports/langsmith-eval-sync-dry-run.json"),
    )

    assert summary["feedbackReviewQueue"] == {
        "caseIds": ["memory-supersession-review"],
        "feedbackRatingCounts": {"thumbs_down": 1},
        "workflowTagCounts": {"memory": 1},
        "reviewAction": (
            "reactor-admin feedback --rating thumbs_down --review-status inbox "
            "--tag memory --limit 10 --output table"
        ),
        "exportAction": (
            "reactor-admin feedback-export --rating thumbs_down "
            "--review-status inbox "
            "--case-id memory-supersession-review "
            "--tag memory --limit 10 --output json"
        ),
        "memoryLifecycleAction": MEMORY_LIFECYCLE_GATE_ACTION,
    }
    assert summary["nextActions"] == [
        {
            "id": "review-feedback-queue",
            "label": "Review feedback waiting for LangSmith eval source metadata",
            "command": (
                "reactor-admin feedback --rating thumbs_down --review-status inbox "
                "--tag memory --limit 10 --output table"
            ),
            "evalCaseId": "memory-supersession-review",
        },
        {
            "id": "verify-memory-lifecycle",
            "label": "Verify memory lifecycle gates before closing feedback",
            "command": MEMORY_LIFECYCLE_GATE_ACTION,
            "preflightFile": "reports/release/release-smoke-preflight.local.json",
            "preflightEnvTemplate": "reports/release/release-smoke-preflight.local.env",
            "replatformReadinessFile": "reports/release/replatform-readiness.local.json",
            "smokePlanFile": "reports/release/release-smoke-plan.local.json",
            "releaseEvidenceFile": "reports/release-evidence.json",
            "releaseReadinessFile": "reports/release-readiness.json",
            "readinessReportArg": "--readiness-report hardening_suite=reports/hardening-suite.json",
            "requiredReadinessReports": ["hardening_suite"],
            "readinessReports": {"hardening_suite": "reports/hardening-suite.json"},
        },
    ]


def test_apply_report_table_shows_langsmith_feedback_review_queue_action() -> None:
    table = format_apply_report_table(
        {
            "status": "applied",
            "langsmithDryRun": {
                "status": "skipped",
                "datasetName": "reactor-rag-ingestion-candidate",
                "caseIds": ["case_rag_candidate_grounded_citation"],
                "feedbackReviewQueue": {
                    "caseIds": ["case_rag_candidate_grounded_citation"],
                    "feedbackRatingCounts": {"thumbs_down": 1},
                    "feedbackSourceCounts": {"slack_button": 1},
                    "workflowTagCounts": {
                        "collection:rag-ingestion-candidate": 1,
                        "documents-ask": 1,
                        "rag": 1,
                    },
                    "reviewAction": (
                        "reactor-admin feedback --rating thumbs_down "
                        "--review-status inbox "
                        "--tag collection:rag-ingestion-candidate --limit 10 --output table"
                    ),
                },
                "reportFile": "reports/rag-ingestion-candidate-dry-run.json",
            },
        }
    )

    rows = dict(line.split(maxsplit=1) for line in table.splitlines()[1:])
    assert rows["langsmithFeedbackQueueCases"] == "1"
    assert rows["langsmithFeedbackQueueRatings"] == "thumbs_down=1"
    assert rows["langsmithFeedbackQueueSources"] == "slack_button=1"
    assert (
        rows["langsmithFeedbackQueueWorkflows"]
        == "collection:rag-ingestion-candidate=1,documents-ask=1,rag=1"
    )
    assert rows["langsmithFeedbackQueueAction"] == (
        "reactor-admin feedback --rating thumbs_down "
        "--review-status inbox "
        "--tag collection:rag-ingestion-candidate --limit 10 --output table"
    )
    assert rows["langsmithFeedbackQueueExportAction"] == (
        "reactor-admin feedback-export --rating thumbs_down "
        "--source slack_button "
        "--review-status inbox "
        "--case-id case_rag_candidate_grounded_citation "
        "--tag collection:rag-ingestion-candidate --tag rag-candidate:grounded_citation "
        "--limit 10 --output json"
    )
    assert rows["langsmithFeedbackQueueCandidateAction"] == (
        "reactor-admin rag-candidates --status INGESTED --limit 10 --output table"
    )
    assert rows["langsmithFeedbackQueueBulkReviewAction"] == (
        "reactor-admin feedback-bulk-review --candidate-tag rag-candidate:grounded_citation "
        "--source slack_button --status done --tag promoted --tag langsmith "
        "--tag collection:rag-ingestion-candidate --tag rag-candidate:grounded_citation "
        "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
        "--output table"
    )


def test_apply_report_table_shows_langsmith_memory_queue_lifecycle_action() -> None:
    table = format_apply_report_table(
        {
            "status": "applied",
            "langsmithDryRun": {
                "status": "skipped",
                "datasetName": "reactor-regression",
                "caseIds": ["memory-supersession-review"],
                "feedbackReviewQueue": {
                    "caseIds": ["memory-supersession-review"],
                    "feedbackRatingCounts": {"thumbs_down": 1},
                    "workflowTagCounts": {"memory": 1},
                    "reviewAction": (
                        "reactor-admin feedback --rating thumbs_down "
                        "--review-status inbox "
                        "--tag memory --limit 10 --output table"
                    ),
                    "memoryLifecycleAction": MEMORY_LIFECYCLE_GATE_ACTION,
                },
                "reportFile": "reports/langsmith-eval-sync-dry-run.json",
            },
        }
    )

    rows = dict(line.split(maxsplit=1) for line in table.splitlines()[1:])
    assert rows["langsmithFeedbackQueueMemoryAction"] == MEMORY_LIFECYCLE_GATE_ACTION


def test_apply_report_table_shows_memory_queue_next_action_release_files() -> None:
    summary = langsmith_dry_run_summary(
        {
            "status": "skipped",
            "datasetName": "reactor-regression",
            "examples": 1,
            "caseIds": ["memory-supersession-review"],
            "metadataCaseIds": ["memory-supersession-review"],
            "feedbackReviewQueue": {
                "caseIds": ["memory-supersession-review"],
                "feedbackRatingCounts": {"thumbs_down": 1},
                "workflowTagCounts": {"memory": 1},
                "reviewAction": (
                    "reactor-admin feedback --rating thumbs_down --review-status inbox "
                    "--tag memory --limit 10 --output table"
                ),
            },
        },
        report_file=Path("reports/langsmith-eval-sync-dry-run.json"),
    )

    table = format_apply_report_table({"langsmithDryRun": summary})

    rows = dict(line.split(maxsplit=1) for line in table.splitlines()[1:])
    assert rows["langsmithNextAction.verify-memory-lifecycle.replatformReadinessFile"] == (
        "reports/release/replatform-readiness.local.json"
    )
    assert rows["langsmithNextAction.verify-memory-lifecycle.smokePlanFile"] == (
        "reports/release/release-smoke-plan.local.json"
    )
    assert rows["langsmithNextAction.verify-memory-lifecycle.releaseEvidenceFile"] == (
        "reports/release-evidence.json"
    )


def test_apply_report_table_shows_langsmith_grounding_citation_summary() -> None:
    table = format_apply_report_table(
        {
            "status": "applied",
            "langsmithDryRun": {
                "status": "skipped",
                "datasetName": "reactor-regression",
                "caseIds": ["rag-grounded-answer-cites-source"],
                "feedbackIdList": [],
                "feedbackReviewIds": ["fb_1"],
                "groundingCitationCases": 1,
                "groundingCitedChunks": 1,
                "groundingUncitedChunks": 1,
                "groundingCitationDocuments": ["tenant-vectorstore-release"],
                "reportFile": "reports/langsmith-eval-sync-dry-run.json",
            },
        }
    )

    rows = dict(line.split(maxsplit=1) for line in table.splitlines()[1:])
    assert rows["langsmithGroundingCases"] == "1"
    assert rows["langsmithFeedbackReviewIds"] == "fb_1"
    assert rows["langsmithGroundingCited"] == "1"
    assert rows["langsmithGroundingUncited"] == "1"
    assert rows["langsmithGroundingDocuments"] == "tenant-vectorstore-release"
    assert "langsmithFeedbackQueueCases" not in rows


def test_langsmith_dry_run_summary_preserves_memory_status_diagnostics() -> None:
    report = {
        "status": "skipped",
        "datasetName": "reactor-regression",
        "examples": 1,
        "caseIds": ["memory-supersession-review"],
        "metadataCaseIds": ["memory-supersession-review"],
        "evidence": {
            "contextManifestDiagnostics": {
                "memoryStatusCounts": {"active": 2},
                "skippedMemoryStatusCounts": {"superseded": 1, "tombstoned": 1},
            }
        },
    }

    summary = langsmith_dry_run_summary(
        report,
        report_file=Path("reports/langsmith-eval-sync-dry-run.json"),
    )

    assert summary["memoryStatusCounts"] == {"active": 2}
    assert summary["skippedMemoryStatusCounts"] == {"superseded": 1, "tombstoned": 1}
    assert summary["memoryLifecycleAction"] == MEMORY_LIFECYCLE_GATE_ACTION

    table = format_apply_report_table({"langsmithDryRun": summary})
    rows = dict(line.split(maxsplit=1) for line in table.splitlines()[1:])
    assert rows["langsmithMemoryLifecycleAction"] == MEMORY_LIFECYCLE_GATE_ACTION


def test_langsmith_dry_run_summary_preserves_context_diagnostics_status() -> None:
    report = {
        "status": "skipped",
        "datasetName": "reactor-regression",
        "examples": 1,
        "caseIds": ["rag-grounded-answer-cites-source"],
        "metadataCaseIds": ["rag-grounded-answer-cites-source"],
        "evidence": {
            "contextManifestDiagnostics": {
                "ok": False,
                "status": "failed",
                "memoryStatusCounts": {"active": 2},
                "skippedMemoryStatusCounts": {"superseded": 1},
            }
        },
    }

    summary = langsmith_dry_run_summary(
        report,
        report_file=Path("reports/langsmith-eval-sync-dry-run.json"),
    )

    assert summary["contextManifestDiagnosticsOk"] is False
    assert summary["contextManifestDiagnosticsStatus"] == "failed"
    assert summary["memoryStatusCounts"] == {"active": 2}


def test_langsmith_dry_run_summary_preserves_context_diagnostics_findings() -> None:
    report = {
        "status": "skipped",
        "datasetName": "reactor-regression",
        "examples": 1,
        "caseIds": ["memory-supersession-review"],
        "metadataCaseIds": ["memory-supersession-review"],
        "evidence": {
            "contextManifestDiagnostics": {
                "ok": False,
                "status": "failed",
                "findings": [
                    {
                        "code": "unknown_memory_status_count",
                        "severity": "error",
                        "field": "memoryStatusCounts",
                    },
                    {
                        "code": "memory_status_count_mismatch",
                        "severity": "error",
                        "field": "skippedMemoryStatusCounts",
                    },
                ],
                "memoryStatusCounts": {"active": 1, "deleted": 1},
                "skippedMemoryStatusCounts": {"superseded": 1},
            }
        },
    }

    summary = langsmith_dry_run_summary(
        report,
        report_file=Path("reports/langsmith-eval-sync-dry-run.json"),
    )

    assert summary["contextManifestDiagnosticsFindings"] == [
        "unknown_memory_status_count",
        "memory_status_count_mismatch",
    ]

    table = format_apply_report_table({"langsmithDryRun": summary})
    rows = dict(line.split(maxsplit=1) for line in table.splitlines()[1:])
    assert (
        rows["langsmithContextDiagnosticsFindings"]
        == "unknown_memory_status_count,memory_status_count_mismatch"
    )


def test_apply_report_table_shows_langsmith_memory_status_diagnostics() -> None:
    table = format_apply_report_table(
        {
            "status": "applied",
            "langsmithDryRun": {
                "status": "skipped",
                "datasetName": "reactor-regression",
                "caseIds": ["memory-supersession-review"],
                "memoryStatusCounts": {"active": 2},
                "skippedMemoryStatusCounts": {"superseded": 1, "tombstoned": 1},
                "reportFile": "reports/langsmith-eval-sync-dry-run.json",
            },
        }
    )

    rows = dict(line.split(maxsplit=1) for line in table.splitlines()[1:])
    assert rows["langsmithMemoryStatusCounts"] == "active=2"
    assert rows["langsmithSkippedMemoryStatusCounts"] == "superseded=1,tombstoned=1"


def test_apply_report_table_shows_langsmith_context_diagnostics_status() -> None:
    table = format_apply_report_table(
        {
            "status": "applied",
            "langsmithDryRun": {
                "status": "skipped",
                "datasetName": "reactor-regression",
                "caseIds": ["rag-grounded-answer-cites-source"],
                "contextManifestDiagnosticsOk": False,
                "contextManifestDiagnosticsStatus": "failed",
                "memoryStatusCounts": {"active": 2},
                "reportFile": "reports/langsmith-eval-sync-dry-run.json",
            },
        }
    )

    rows = dict(line.split(maxsplit=1) for line in table.splitlines()[1:])
    assert rows["langsmithContextDiagnostics"] == "failed"
    assert rows["langsmithContextDiagnosticsOk"] == "false"
    assert rows["langsmithMemoryStatusCounts"] == "active=2"


def test_apply_report_table_shows_citation_marker_coverage() -> None:
    table = format_apply_report_table(
        {
            "status": "would_add",
            "caseId": "case_documents_ask_citations",
            "promotionCoverage": {
                "sourceRunIdPresent": True,
                "runFixturePresent": True,
                "runFixtureMatchedCase": True,
                "requiredSourceRunId": True,
                "requiredRunFile": True,
                "citationMarkersRequired": True,
                "citationMarkersPresent": True,
                "runCitationMarkersPresent": True,
                "runContextDiagnosticsPresent": True,
                "requiredContextDiagnostics": True,
                "contextCitationEvalCaseIdMatched": True,
                "contextCitationWorkflowTagMatched": True,
            },
        }
    )

    rows = dict(line.split(maxsplit=1) for line in table.splitlines()[1:])
    assert rows["coverageCitationMarkers"] == "true"
    assert rows["coverageRunCitationMarkers"] == "true"
    assert rows["coverageRunContextDiagnostics"] == "true"
    assert rows["coverageRequiredContextDiagnostics"] == "true"
    assert rows["coverageContextCitationEvalCaseId"] == "true"
    assert rows["coverageContextCitationWorkflowTag"] == "true"


def test_apply_promoted_eval_case_adds_case_to_source_controlled_suite(tmp_path: Path) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "cases": [],
                "runs": [{"runId": "existing-run", "evalCaseId": "existing-case"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_failed_provider_timeout",
                "name": "Provider timeout should recover",
                "userInput": "Investigate the provider timeout and answer from safe evidence",
                "expectedAnswerContains": ["provider timeout"],
                "forbiddenAnswerContains": ["redacted credential marker"],
                "expectedToolNames": ["Provider:chat"],
                "forbiddenToolNames": ["Shell:exec"],
                "expectedExposedToolNames": ["Provider:chat"],
                "forbiddenExposedToolNames": ["Shell:exec"],
                "maxToolExposureCount": 3,
                "agentType": "standard",
                "model": "test-model",
                "enabled": True,
                "tags": ["regression", "promoted-from-failed-run"],
                "minScore": 1.0,
                "sourceRunId": "run_failed_provider_timeout",
                "assertionCount": 6,
                "createdAt": "2026-07-01T00:00:00Z",
                "updatedAt": "2026-07-01T00:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = apply_promoted_eval_case(
        suite_file=suite_file,
        case_file=case_file,
        dataset_name="reactor-regression",
    )

    assert report == {
        "status": "added",
        "caseId": "case_failed_provider_timeout",
        "sourceRunId": "run_failed_provider_timeout",
        "suiteFile": str(suite_file),
        "caseCount": 1,
        "replaced": False,
        "dryRun": False,
        "promotionCoverage": {
            "sourceRunIdPresent": True,
            "runFixturePresent": False,
            "runFixtureMatchedCase": False,
            "runContextDiagnosticsPresent": False,
            "requiredSourceRunId": False,
            "requiredRunFile": False,
            "requiredContextDiagnostics": False,
        },
    }
    suite = json.loads(suite_file.read_text(encoding="utf-8"))
    assert suite["runs"] == [{"runId": "existing-run", "evalCaseId": "existing-case"}]
    assert suite["cases"] == [
        {
            "id": "case_failed_provider_timeout",
            "name": "Provider timeout should recover",
            "userInput": "Investigate the provider timeout and answer from safe evidence",
            "expectedAnswerContains": ["provider timeout"],
            "forbiddenAnswerContains": ["redacted credential marker"],
            "expectedToolNames": ["Provider:chat"],
            "forbiddenToolNames": ["Shell:exec"],
            "expectedExposedToolNames": ["Provider:chat"],
            "forbiddenExposedToolNames": ["Shell:exec"],
            "maxToolExposureCount": 3,
            "agentType": "standard",
            "model": "test-model",
            "enabled": True,
            "tags": ["regression", "promoted-from-failed-run"],
            "minScore": 1.0,
            "sourceRunId": "run_failed_provider_timeout",
        }
    ]


def test_apply_promoted_eval_case_requires_context_diagnostics_when_requested(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_rag_candidate_c1",
                "name": "RAG answer should stay grounded",
                "userInput": "How should RAG answers cite sources?",
                "expectedAnswerContains": ["[runbook.md]"],
                "enabled": True,
                "tags": ["collection:rag-ingestion-candidate", "rag"],
                "sourceRunId": "run_rag_candidate_c1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_file = tmp_path / "promoted-run.json"
    run_file.write_text(
        json.dumps(
            {
                "runId": "run_rag_candidate_c1",
                "evalCaseId": "case_rag_candidate_c1",
                "userInput": "How should RAG answers cite sources?",
                "agentType": "documents-ask",
                "model": "test-model",
                "finalAnswer": "Use [runbook.md].",
                "toolCalls": [],
                "toolExposure": {"count": 0, "names": []},
                "retrievedChunks": [],
                "errors": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="context diagnostics are required"):
        apply_promoted_eval_case(
            suite_file=suite_file,
            case_file=case_file,
            run_file=run_file,
            dataset_name="reactor-rag-ingestion-candidate",
            require_run_file=True,
            require_context_diagnostics=True,
        )


def test_apply_promoted_rag_candidate_requires_context_citation_workflow_metadata(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "rag-ingestion-candidate.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_rag_candidate_c1",
                "name": "RAG candidate answer should stay grounded",
                "userInput": "How should RAG answers cite candidate sources?",
                "expectedAnswerContains": ["[runbook.md]"],
                "enabled": True,
                "tags": ["collection:rag-ingestion-candidate", "rag", "documents-ask"],
                "sourceRunId": "run_rag_candidate_c1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_file = tmp_path / "promoted-run.json"
    run_file.write_text(
        json.dumps(
            {
                "runId": "run_rag_candidate_c1",
                "evalCaseId": "case_rag_candidate_c1",
                "userInput": "How should RAG answers cite candidate sources?",
                "agentType": "documents-ask",
                "model": "test-model",
                "finalAnswer": "Use [runbook.md].",
                "toolCalls": [],
                "toolExposure": {"count": 0, "names": []},
                "retrievedChunks": [],
                "contextManifestDiagnostics": {
                    "ok": True,
                    "status": "passed",
                    "citations": [
                        {
                            "citation_id": "rag:doc_1:0",
                            "source_uri": "runbook.md",
                            "evalCaseId": "case_other_candidate",
                            "workflowTags": ["rag-candidate:other"],
                        }
                    ],
                },
                "errors": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="RAG ingestion candidate context citations must include evalCaseId",
    ):
        apply_promoted_eval_case(
            suite_file=suite_file,
            case_file=case_file,
            run_file=run_file,
            dataset_name="reactor-rag-ingestion-candidate",
            require_run_file=True,
            require_context_diagnostics=True,
        )


def test_apply_promoted_documents_ask_case_requires_citation_marker(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(json.dumps({"cases": [], "runs": []}) + "\n", encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_rag_candidate_c1",
                "name": "Documents ask should cite source",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["runbook.md"],
                "forbiddenAnswerContains": [],
                "expectedToolNames": [],
                "forbiddenToolNames": [],
                "expectedExposedToolNames": [],
                "forbiddenExposedToolNames": [],
                "enabled": True,
                "tags": [
                    "rag",
                    "documents-ask",
                    "feedback:fb_1",
                    "feedback-rating:thumbs_down",
                    "feedback-source:slack_button",
                ],
                "minScore": 1.0,
                "sourceRunId": "run_1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="documents-ask eval cases require bracketed citations"):
        apply_promoted_eval_case(
            suite_file=suite_file,
            case_file=case_file,
            dataset_name="reactor-regression",
        )


def test_apply_promoted_documents_ask_case_rejects_placeholder_citation_marker(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(json.dumps({"cases": [], "runs": []}) + "\n", encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_rag_candidate_c1",
                "name": "Documents ask should cite source",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["[replace-with-source-id]"],
                "forbiddenAnswerContains": [],
                "expectedToolNames": [],
                "forbiddenToolNames": [],
                "expectedExposedToolNames": [],
                "forbiddenExposedToolNames": [],
                "enabled": True,
                "tags": [
                    "rag",
                    "documents-ask",
                    "feedback:fb_1",
                    "feedback-rating:thumbs_down",
                    "feedback-source:slack_button",
                ],
                "minScore": 1.0,
                "sourceRunId": "run_1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="placeholder citation marker"):
        apply_promoted_eval_case(
            suite_file=suite_file,
            case_file=case_file,
            dataset_name="reactor-regression",
        )


def test_apply_promoted_documents_ask_case_rejects_embedded_placeholder_citation_marker(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(json.dumps({"cases": [], "runs": []}) + "\n", encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_rag_candidate_c1",
                "name": "Documents ask should cite source",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["Expected citation marker: [replace-with-source-id]"],
                "forbiddenAnswerContains": [],
                "expectedToolNames": [],
                "forbiddenToolNames": [],
                "expectedExposedToolNames": [],
                "forbiddenExposedToolNames": [],
                "enabled": True,
                "tags": [
                    "rag",
                    "documents-ask",
                    "feedback:fb_1",
                    "feedback-rating:thumbs_down",
                    "feedback-source:slack_button",
                ],
                "minScore": 1.0,
                "sourceRunId": "run_1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="placeholder citation marker"):
        apply_promoted_eval_case(
            suite_file=suite_file,
            case_file=case_file,
            dataset_name="reactor-regression",
        )


def test_promoted_case_validator_rejects_embedded_placeholder_citation_marker() -> None:
    case = AgentEvalCaseRecord(
        id="case_rag_candidate_c1",
        name="Documents ask should cite source",
        user_input="How should rollback work?",
        expected_answer_contains=("Expected citation marker: [replace-with-source-id]",),
        tags=("rag", "documents-ask", "feedback:fb_1", "feedback-rating:thumbs_down"),
        source_run_id="run_1",
    )

    with pytest.raises(ValueError, match="placeholder citation marker"):
        validate_promoted_case_citation_markers(case)


def test_apply_promoted_rag_candidate_suite_rejects_non_candidate_case_id(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "rag-ingestion-candidate.json"
    suite_file.write_text(json.dumps({"cases": [], "runs": []}) + "\n", encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_failed_provider",
                "name": "RAG candidate should cite source",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["[runbook.md]"],
                "forbiddenAnswerContains": [],
                "expectedToolNames": [],
                "forbiddenToolNames": [],
                "expectedExposedToolNames": [],
                "forbiddenExposedToolNames": [],
                "enabled": True,
                "tags": ["rag", "documents-ask", "collection:rag-ingestion-candidate"],
                "minScore": 1.0,
                "sourceRunId": "run_1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="RAG ingestion candidate eval apply requires case id case_rag_candidate_\\*",
    ):
        apply_promoted_eval_case(
            suite_file=suite_file,
            case_file=case_file,
            dataset_name="reactor-rag-ingestion-candidate",
        )


def test_apply_promoted_rag_candidate_suite_rejects_unslugged_case_id(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "rag-ingestion-candidate.json"
    suite_file.write_text(json.dumps({"cases": [], "runs": []}) + "\n", encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_rag_candidate_bad.path",
                "name": "RAG candidate should cite source",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["[runbook.md]"],
                "forbiddenAnswerContains": [],
                "expectedToolNames": [],
                "forbiddenToolNames": [],
                "expectedExposedToolNames": [],
                "forbiddenExposedToolNames": [],
                "enabled": True,
                "tags": ["rag", "documents-ask", "collection:rag-ingestion-candidate"],
                "minScore": 1.0,
                "sourceRunId": "run_1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="RAG ingestion candidate eval apply requires slugged case id",
    ):
        apply_promoted_eval_case(
            suite_file=suite_file,
            case_file=case_file,
            dataset_name="reactor-rag-ingestion-candidate",
        )


def test_apply_promoted_documents_ask_run_requires_expected_citation_marker(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(json.dumps({"cases": [], "runs": []}) + "\n", encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_rag_candidate_c1",
                "name": "Documents ask should cite source",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["[runbook.md]"],
                "forbiddenAnswerContains": [],
                "expectedToolNames": [],
                "forbiddenToolNames": [],
                "expectedExposedToolNames": [],
                "forbiddenExposedToolNames": [],
                "enabled": True,
                "tags": [
                    "rag",
                    "documents-ask",
                    "feedback:fb_1",
                    "feedback-rating:thumbs_down",
                    "feedback-source:slack_button",
                ],
                "minScore": 1.0,
                "sourceRunId": "run_1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_file = tmp_path / "promoted-run.json"
    run_file.write_text(
        json.dumps(
            {
                "runId": "run_1",
                "evalCaseId": "case_rag_candidate_c1",
                "userInput": "How should rollback work?",
                "agentType": "documents-ask",
                "model": "test-model",
                "finalAnswer": "Use runbook.md for rollback.",
                "toolCalls": [],
                "toolExposure": {"count": 0, "names": []},
                "retrievedChunks": [
                    {
                        "documentId": "doc_1",
                        "source": "runbook.md",
                        "title": "Runbook",
                        "score": 1.0,
                        "cited": True,
                    }
                ],
                "errors": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="run fixture finalAnswer must include expected citation"):
        apply_promoted_eval_case(
            suite_file=suite_file,
            case_file=case_file,
            run_file=run_file,
            dataset_name="reactor-regression",
        )


def test_apply_promoted_documents_ask_citation_failure_can_capture_failing_run(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(json.dumps({"cases": [], "runs": []}) + "\n", encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_rag_candidate_c1",
                "name": "Documents ask should cite source",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["[runbook.md]"],
                "forbiddenAnswerContains": [],
                "expectedToolNames": [],
                "forbiddenToolNames": [],
                "expectedExposedToolNames": [],
                "forbiddenExposedToolNames": [],
                "enabled": True,
                "tags": [
                    "rag",
                    "documents-ask",
                    "citation-failure",
                    "feedback:fb_1",
                    "feedback-rating:thumbs_down",
                    "feedback-source:slack_button",
                ],
                "minScore": 1.0,
                "sourceRunId": "run_1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_file = tmp_path / "promoted-run.json"
    run_file.write_text(
        json.dumps(
            {
                "runId": "run_1",
                "evalCaseId": "case_rag_candidate_c1",
                "userInput": "How should rollback work?",
                "agentType": "documents-ask",
                "model": "test-model",
                "finalAnswer": "Use runbook.md for rollback.",
                "toolCalls": [],
                "toolExposure": {"count": 0, "names": []},
                "retrievedChunks": [
                    {
                        "documentId": "doc_1",
                        "source": "runbook.md",
                        "title": "Runbook",
                        "score": 1.0,
                        "cited": False,
                    }
                ],
                "errors": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = apply_promoted_eval_case(
        suite_file=suite_file,
        case_file=case_file,
        run_file=run_file,
        dataset_name="reactor-regression",
    )

    assert report["runStatus"] == "added"
    coverage = cast(dict[str, object], report["promotionCoverage"])
    assert coverage["citationMarkersPresent"] is True
    assert coverage["runCitationMarkersPresent"] is False
    assert coverage["citationFailureAllowsMissingRunCitation"] is True
    table = format_apply_report_table(report)
    table_rows = dict(line.split(maxsplit=1) for line in table.splitlines()[1:])
    assert table_rows["coverageCitationFailureAllowsMissing"] == "true"
    [result] = AgentEvalRegressionSuite.load(suite_file).evaluate()
    assert result.passed is False
    assert result.missing_expected_answer_contains == ("[runbook.md]",)


def test_apply_promoted_eval_case_is_idempotent_without_replace(tmp_path: Path) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case_existing",
                        "name": "Existing case",
                        "userInput": "Existing question",
                        "enabled": True,
                        "minScore": 1.0,
                    }
                ],
                "runs": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_existing",
                "name": "Replacement case",
                "userInput": "Replacement question",
                "enabled": True,
                "minScore": 1.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = apply_promoted_eval_case(
        suite_file=suite_file,
        case_file=case_file,
        dataset_name="reactor-regression",
    )

    assert report["status"] == "unchanged"
    assert report["caseId"] == "case_existing"
    suite = json.loads(suite_file.read_text(encoding="utf-8"))
    assert suite["cases"][0]["name"] == "Existing case"


def test_apply_promoted_eval_case_rejects_secret_shaped_values(tmp_path: Path) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_secret",
                "name": "Secret leak",
                "userInput": "Investigate api_key=sk-live-1234567890abcdef safely",
                "enabled": True,
                "minScore": 1.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(LangSmithEvalDatasetSecretError, match="case_secret"):
        apply_promoted_eval_case(
            suite_file=suite_file,
            case_file=case_file,
            dataset_name="reactor-regression",
        )

    assert json.loads(suite_file.read_text(encoding="utf-8")) == {"cases": [], "runs": []}


def test_apply_promoted_eval_case_can_merge_matching_run_fixture(tmp_path: Path) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_rag_answer",
                "name": "RAG answer should cite docs",
                "userInput": "How should Reactor cite RAG answers?",
                "expectedAnswerContains": ["[runbook.md]"],
                "expectedToolNames": ["Rag:hybrid_search"],
                "expectedExposedToolNames": ["Rag:hybrid_search"],
                "enabled": True,
                "minScore": 1.0,
                "sourceRunId": "run_rag_answer",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_file = tmp_path / "promoted-run.json"
    run_file.write_text(
        json.dumps(
            {
                "runId": "run_rag_answer",
                "evalCaseId": "case_rag_answer",
                "userInput": "How should Reactor cite RAG answers?",
                "agentType": "standard",
                "model": "test-model",
                "finalAnswer": "Use grounded citations from [runbook.md].",
                "toolCalls": [
                    {
                        "step": 1,
                        "toolName": "Rag:hybrid_search",
                        "arguments": {"query": "citations"},
                        "success": True,
                    }
                ],
                "toolExposure": {"count": 1, "names": ["Rag:hybrid_search"]},
                "retrievedChunks": [
                    {
                        "documentId": "doc_rag",
                        "source": "runbook.md",
                        "title": "RAG Runbook",
                        "score": 0.91,
                    }
                ],
                "contextManifestDiagnostics": {
                    "ok": True,
                    "status": "passed",
                    "memoryStatusCounts": {"active": 1},
                    "skippedMemoryStatusCounts": {},
                },
                "errors": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = apply_promoted_eval_case(
        suite_file=suite_file,
        case_file=case_file,
        run_file=run_file,
        dataset_name="reactor-regression",
    )

    assert report == {
        "status": "added",
        "caseId": "case_rag_answer",
        "sourceRunId": "run_rag_answer",
        "suiteFile": str(suite_file),
        "caseCount": 1,
        "replaced": False,
        "dryRun": False,
        "runStatus": "added",
        "runId": "run_rag_answer",
        "runCount": 1,
        "contextManifestDiagnosticsPresent": True,
        "promotionCoverage": {
            "sourceRunIdPresent": True,
            "runFixturePresent": True,
            "runFixtureMatchedCase": True,
            "runContextDiagnosticsPresent": True,
            "requiredSourceRunId": False,
            "requiredRunFile": False,
            "requiredContextDiagnostics": False,
        },
    }
    suite = json.loads(suite_file.read_text(encoding="utf-8"))
    assert [run["runId"] for run in suite["runs"]] == ["run_rag_answer"]
    assert suite["runs"][0]["contextManifestDiagnostics"] == {
        "ok": True,
        "status": "passed",
        "memoryStatusCounts": {"active": 1},
        "skippedMemoryStatusCounts": {},
    }
    [result] = AgentEvalRegressionSuite.load(suite_file).evaluate()
    assert result.passed is True


def test_apply_promoted_eval_case_rejects_run_fixture_source_run_mismatch(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_rag_answer",
                "name": "RAG answer should cite docs",
                "userInput": "How should Reactor cite RAG answers?",
                "expectedAnswerContains": ["[runbook.md]"],
                "enabled": True,
                "minScore": 1.0,
                "sourceRunId": "run_expected",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_file = tmp_path / "promoted-run.json"
    run_file.write_text(
        json.dumps(
            {
                "runId": "run_actual",
                "evalCaseId": "case_rag_answer",
                "userInput": "How should Reactor cite RAG answers?",
                "agentType": "standard",
                "model": "test-model",
                "finalAnswer": "Use grounded citations from [runbook.md].",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="run fixture runId must match sourceRunId: run_expected",
    ):
        apply_promoted_eval_case(
            suite_file=suite_file,
            case_file=case_file,
            run_file=run_file,
            dataset_name="reactor-regression",
        )

    assert json.loads(suite_file.read_text(encoding="utf-8")) == {"cases": [], "runs": []}


def test_apply_promoted_eval_case_can_add_run_fixture_for_existing_case(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case_existing",
                        "name": "Existing case",
                        "userInput": "Existing question",
                        "expectedAnswerContains": ["answer"],
                        "enabled": True,
                        "minScore": 1.0,
                    }
                ],
                "runs": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_existing",
                "name": "Existing case",
                "userInput": "Existing question",
                "expectedAnswerContains": ["answer"],
                "enabled": True,
                "minScore": 1.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_file = tmp_path / "promoted-run.json"
    run_file.write_text(
        json.dumps(
            {
                "runId": "run_existing",
                "evalCaseId": "case_existing",
                "userInput": "Existing question",
                "agentType": "standard",
                "model": "test-model",
                "finalAnswer": "answer",
                "toolCalls": [],
                "toolExposure": {"count": 0, "names": []},
                "retrievedChunks": [],
                "errors": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = apply_promoted_eval_case(
        suite_file=suite_file,
        case_file=case_file,
        run_file=run_file,
        dataset_name="reactor-regression",
    )

    assert report["status"] == "unchanged"
    assert report["runStatus"] == "added"
    suite = json.loads(suite_file.read_text(encoding="utf-8"))
    assert [run["runId"] for run in suite["runs"]] == ["run_existing"]


def test_apply_promoted_eval_case_dry_run_reports_existing_case_and_pending_run(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    original_suite = {
        "cases": [
            {
                "id": "case_existing",
                "name": "Existing case",
                "userInput": "Existing question",
                "expectedAnswerContains": ["answer"],
                "enabled": True,
                "minScore": 1.0,
            }
        ],
        "runs": [],
    }
    suite_file.write_text(json.dumps(original_suite) + "\n", encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_existing",
                "name": "Existing case",
                "userInput": "Existing question",
                "expectedAnswerContains": ["answer"],
                "enabled": True,
                "minScore": 1.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_file = tmp_path / "promoted-run.json"
    run_file.write_text(
        json.dumps(
            {
                "runId": "run_pending",
                "evalCaseId": "case_existing",
                "userInput": "Existing question",
                "agentType": "standard",
                "model": "test-model",
                "finalAnswer": "answer",
                "toolCalls": [],
                "toolExposure": {"count": 0, "names": []},
                "retrievedChunks": [],
                "errors": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = apply_promoted_eval_case(
        suite_file=suite_file,
        case_file=case_file,
        run_file=run_file,
        dataset_name="reactor-regression",
        dry_run=True,
    )

    assert report["status"] == "unchanged"
    assert report["runStatus"] == "would_add"
    assert report["dryRun"] is True
    assert json.loads(suite_file.read_text(encoding="utf-8")) == original_suite


def test_promoted_eval_suite_snapshot_rejects_existing_duplicate_case_ids(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case_existing",
                        "name": "Existing case",
                        "userInput": "Existing question",
                    },
                    {
                        "id": "case_existing",
                        "name": "Duplicate case",
                        "userInput": "Different question",
                    },
                ],
                "runs": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_new",
                "name": "New case",
                "userInput": "New question",
                "expectedAnswerContains": ["answer"],
                "enabled": True,
                "minScore": 1.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate eval suite case id: case_existing"):
        promoted_eval_suite_snapshot(
            suite_file=suite_file,
            case_file=case_file,
            run_file=None,
            replace=False,
        )


def test_apply_promoted_eval_case_cli_can_render_operator_table_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_failed_rag",
                "name": "Failed RAG run should cite source",
                "userInput": "How should Reactor cite RAG answers?",
                "expectedAnswerContains": ["[runbook.md]"],
                "enabled": True,
                "minScore": 1.0,
                "sourceRunId": "run_failed_rag",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_file = tmp_path / "promoted-run.json"
    run_file.write_text(
        json.dumps(
            {
                "runId": "run_failed_rag",
                "evalCaseId": "case_failed_rag",
                "userInput": "How should Reactor cite RAG answers?",
                "agentType": "standard",
                "model": "test-model",
                "finalAnswer": "Use grounded citations from runbook.md.",
                "toolCalls": [],
                "toolExposure": {"count": 0, "names": []},
                "retrievedChunks": [],
                "errors": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    exit_code = main(
        [
            "--suite-file",
            str(suite_file),
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--dry-run",
            "--output",
            "table",
        ]
    )

    assert exit_code == 0
    rows = dict(line.split(maxsplit=1) for line in capsys.readouterr().out.splitlines()[1:])
    assert rows == {
        "status": "would_add",
        "caseId": "case_failed_rag",
        "sourceRunId": "run_failed_rag",
        "runStatus": "would_add",
        "runId": "run_failed_rag",
        "dryRun": "true",
        "caseCount": "1",
        "runCount": "1",
        "coverageSourceRunId": "true",
        "coverageRunFixture": "true",
        "coverageRunMatchedCase": "true",
        "coverageRunContextDiagnostics": "false",
        "coverageRequiredSource": "false",
        "coverageRequiredRunFile": "false",
        "coverageRequiredContextDiagnostics": "false",
        "suitePersistCommand": (
            f"reactor-agent-eval-apply --case-file {case_file} "
            f"--run-file {run_file} --suite-file {suite_file} "
            "--dataset-name reactor-regression --output table"
        ),
    }


def test_apply_promoted_eval_case_cli_can_write_langsmith_dry_run_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_failed_rag",
                "name": "Failed RAG run should cite source",
                "userInput": "How should Reactor cite RAG answers?",
                "expectedAnswerContains": ["[runbook.md]"],
                "enabled": True,
                "minScore": 1.0,
                "sourceRunId": "run_failed_rag",
                "tags": [
                    "rag",
                    "documents-ask",
                    "feedback:fb_1",
                    "feedback-rating:thumbs_down",
                    "feedback-source:slack_button",
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    langsmith_report_file = tmp_path / "langsmith-dry-run.json"
    exit_code = main(
        [
            "--suite-file",
            str(suite_file),
            "--case-file",
            str(case_file),
            "--dataset-name",
            "reactor-regression",
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
        ]
    )

    assert exit_code == 0
    apply_report = json.loads(capsys.readouterr().out)
    expected_readiness_command = release_readiness_command_for_reports(
        required_reports=["hardening_suite", "langsmith_eval_sync"],
        report_files={
            "hardening_suite": "reports/hardening-suite.json",
            "langsmith_eval_sync": str(langsmith_report_file),
        },
    )
    assert apply_report["langsmithDryRun"] == {
        "status": "skipped",
        "datasetName": "reactor-regression",
        "examples": 1,
        "caseIds": ["case_failed_rag"],
        "metadataCaseIds": ["case_failed_rag"],
        "sourceRunIds": ["run_failed_rag"],
        "caseSourceRunIds": {"case_failed_rag": "run_failed_rag"},
        "splitCounts": {"regression": 1},
        "sourceSuite": str(suite_file),
        "feedbackCases": 1,
        "feedbackIds": 1,
        "feedbackIdList": ["fb_1"],
        "feedbackReviewIds": ["fb_1"],
        "feedbackRatings": {"thumbs_down": 1},
        "feedbackSources": {"slack_button": 1},
        "feedbackWorkflows": {"documents-ask": 1, "grounding": 1, "rag": 1},
        "feedbackExpectedCitations": {"runbook.md": 1},
        "feedbackReviewAction": ("reactor-admin feedback --feedback-id fb_1 --output table"),
        "bulkReviewAction": (
            "reactor-admin feedback-bulk-review fb_1 --status done "
            "--tag promoted --tag langsmith --tag expected-citation:runbook.md "
            "--tag documents-ask "
            "--tag grounding --tag rag "
            "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
            "--output table"
        ),
        "gradedRuns": 0,
        "missingRunCases": 1,
        "releaseGate": {
            "reason": "dry_run_only",
            "requiredReport": "langsmith_eval_sync",
            "remediation": [
                "run_reactor_langsmith_eval_sync_without_dry_run",
                "include_passed_langsmith_eval_sync_report_in_release_readiness",
            ],
            "status": "blocked",
        },
        "syncCommand": (
            f"uv run reactor-langsmith-eval-sync --suite-file {suite_file} "
            f"--dataset-name reactor-regression --dry-run --report-file {langsmith_report_file}"
        ),
        "liveSyncCommand": (
            f"uv run reactor-langsmith-eval-sync --suite-file {suite_file} "
            f"--dataset-name reactor-regression --report-file {langsmith_report_file} "
            "--required-readiness-report hardening_suite "
            "--required-readiness-report langsmith_eval_sync "
            "--readiness-report hardening_suite=reports/hardening-suite.json "
            f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
        ),
        "preflightFile": "reports/release/release-smoke-preflight.local.json",
        "preflightEnvTemplate": "reports/release/release-smoke-preflight.local.env",
        "replatformReadinessFile": "reports/release/replatform-readiness.local.json",
        "smokePlanFile": "reports/release/release-smoke-plan.local.json",
        "releaseEvidenceFile": "reports/release-evidence.json",
        "releaseReadinessFile": "reports/release-readiness.json",
        "readinessCommand": (
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
            f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
        ),
        "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
        "readinessReports": {
            "hardening_suite": "reports/hardening-suite.json",
            "langsmith_eval_sync": str(langsmith_report_file),
        },
        "nextActions": [
            {
                "id": "review-feedback-fb_1",
                "label": "Review feedback promoted into the LangSmith eval report",
                "command": "reactor-admin feedback --feedback-id fb_1 --output table",
                "feedbackId": "fb_1",
            },
            {
                "id": "bulk-review-feedback",
                "label": "Close promoted feedback after LangSmith eval handoff is reviewed",
                "command": (
                    "reactor-admin feedback-bulk-review fb_1 --status done "
                    "--tag promoted --tag langsmith --tag expected-citation:runbook.md "
                    "--tag documents-ask "
                    "--tag grounding --tag rag "
                    "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
                    "--output table"
                ),
            },
            {
                "id": "preflight-langsmith",
                "label": "Preflight the LangSmith eval sync credentials",
                "command": (
                    f"uv run reactor-langsmith-eval-sync --suite-file {suite_file} "
                    f"--dataset-name reactor-regression --report-file {langsmith_report_file} "
                    "--required-readiness-report hardening_suite "
                    "--required-readiness-report langsmith_eval_sync "
                    "--readiness-report hardening_suite=reports/hardening-suite.json "
                    f"--readiness-report langsmith_eval_sync={langsmith_report_file} "
                    "--preflight-only --output table"
                ),
                "requiredEnvAnyOf": [
                    ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                ],
                "recommendedEnv": ["LANGSMITH_ENDPOINT"],
                "preflightFile": "reports/release/release-smoke-preflight.local.json",
                "preflightEnvTemplate": "reports/release/release-smoke-preflight.local.env",
                "releaseReadinessFile": "reports/release-readiness.json",
                "releaseReadinessCommand": expected_readiness_command,
                "readinessReportArg": (
                    "--readiness-report hardening_suite=reports/hardening-suite.json "
                    f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
                ),
                "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                "readinessReports": {
                    "hardening_suite": "reports/hardening-suite.json",
                    "langsmith_eval_sync": str(langsmith_report_file),
                },
                "remediationCommand": (
                    f"uv run reactor-langsmith-eval-sync --suite-file {suite_file} "
                    f"--dataset-name reactor-regression --report-file {langsmith_report_file} "
                    "--required-readiness-report hardening_suite "
                    "--required-readiness-report langsmith_eval_sync "
                    "--readiness-report hardening_suite=reports/hardening-suite.json "
                    f"--readiness-report langsmith_eval_sync={langsmith_report_file} "
                    "--preflight-only --output table"
                ),
            },
            {
                "id": "sync-langsmith",
                "label": "Run the LangSmith eval sync without dry-run",
                "command": (
                    f"uv run reactor-langsmith-eval-sync --suite-file {suite_file} "
                    f"--dataset-name reactor-regression --report-file {langsmith_report_file} "
                    "--required-readiness-report hardening_suite "
                    "--required-readiness-report langsmith_eval_sync "
                    "--readiness-report hardening_suite=reports/hardening-suite.json "
                    f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
                ),
                "requiredEnvAnyOf": [
                    ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                ],
                "recommendedEnv": ["LANGSMITH_ENDPOINT"],
                "preflightFile": "reports/release/release-smoke-preflight.local.json",
                "preflightEnvTemplate": "reports/release/release-smoke-preflight.local.env",
                "releaseReadinessFile": "reports/release-readiness.json",
                "releaseReadinessCommand": expected_readiness_command,
                "readinessReportArg": (
                    "--readiness-report hardening_suite=reports/hardening-suite.json "
                    f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
                ),
                "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                "readinessReports": {
                    "hardening_suite": "reports/hardening-suite.json",
                    "langsmith_eval_sync": str(langsmith_report_file),
                },
                "remediationCommand": (
                    f"uv run reactor-langsmith-eval-sync --suite-file {suite_file} "
                    f"--dataset-name reactor-regression --report-file {langsmith_report_file} "
                    "--required-readiness-report hardening_suite "
                    "--required-readiness-report langsmith_eval_sync "
                    "--readiness-report hardening_suite=reports/hardening-suite.json "
                    f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
                ),
            },
            {
                "id": "generate-hardening-suite",
                "label": "Generate the hardening suite report required for minor boundary review",
                "command": (
                    "uv run reactor-hardening-suite --report-file reports/hardening-suite.json"
                ),
                "readinessReportArg": (
                    "--readiness-report hardening_suite=reports/hardening-suite.json"
                ),
                "releaseReadinessCommand": expected_readiness_command,
                "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                "readinessReports": {
                    "hardening_suite": "reports/hardening-suite.json",
                    "langsmith_eval_sync": str(langsmith_report_file),
                },
            },
            {
                "id": "refresh-release-readiness",
                "label": "Refresh release readiness with promoted LangSmith and hardening reports",
                "latestTagCommand": "git describe --tags --abbrev=0",
                "recommendedTagSource": "release_readiness.tagRecommendation.recommendedTag",
                "replatformReadinessFile": "reports/release/replatform-readiness.local.json",
                "smokePlanFile": "reports/release/release-smoke-plan.local.json",
                "releaseEvidenceFile": "reports/release-evidence.json",
                "releaseReadinessFile": "reports/release-readiness.json",
                "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                "readinessReports": {
                    "hardening_suite": "reports/hardening-suite.json",
                    "langsmith_eval_sync": str(langsmith_report_file),
                },
                "command": (
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
                    f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
                ),
                "envFileCommand": (
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
                    f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
                ),
                "remediationCommand": (
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
                    f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
                ),
                "readinessReportArg": (
                    "--readiness-report hardening_suite=reports/hardening-suite.json "
                    f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
                ),
            },
        ],
        "reportFile": str(langsmith_report_file),
    }
    langsmith_report = json.loads(langsmith_report_file.read_text(encoding="utf-8"))
    assert langsmith_report["status"] == "skipped"
    assert langsmith_report["datasetName"] == "reactor-regression"
    assert langsmith_report["caseIds"] == ["case_failed_rag"]


def test_apply_promoted_eval_case_cli_quotes_langsmith_handoff_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_dir = tmp_path / "eval artifacts"
    artifact_dir.mkdir()
    suite_file = artifact_dir / "regression suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = artifact_dir / "promoted case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_failed_rag",
                "name": "Failed RAG run should cite source",
                "userInput": "How should Reactor cite RAG answers?",
                "expectedAnswerContains": ["[runbook.md]"],
                "enabled": True,
                "minScore": 1.0,
                "sourceRunId": "run_failed_rag",
                "tags": ["rag", "documents-ask"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    langsmith_report_file = artifact_dir / "langsmith dry run.json"

    exit_code = main(
        [
            "--suite-file",
            str(suite_file),
            "--case-file",
            str(case_file),
            "--dataset-name",
            "reactor regression",
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
        ]
    )

    assert exit_code == 0
    apply_report = json.loads(capsys.readouterr().out)
    assert apply_report["langsmithDryRun"]["syncCommand"] == (
        "uv run reactor-langsmith-eval-sync "
        f"--suite-file '{suite_file}' "
        "--dataset-name 'reactor regression' "
        f"--dry-run --report-file '{langsmith_report_file}'"
    )
    assert apply_report["langsmithDryRun"]["liveSyncCommand"] == (
        "uv run reactor-langsmith-eval-sync "
        f"--suite-file '{suite_file}' "
        "--dataset-name 'reactor regression' "
        f"--report-file '{langsmith_report_file}' "
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync "
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        f"--readiness-report langsmith_eval_sync='{langsmith_report_file}'"
    )
    assert apply_report["langsmithDryRun"]["readinessCommand"].endswith(
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync "
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        f"--readiness-report langsmith_eval_sync='{langsmith_report_file}'"
    )
    assert (
        "--preflight-file reports/release/release-smoke-preflight.local.json"
        in (apply_report["langsmithDryRun"]["readinessCommand"])
    )
    assert (
        "--env-file reports/release/release-smoke-preflight.local.env"
        in (apply_report["langsmithDryRun"]["readinessCommand"])
    )


def test_apply_promoted_eval_case_cli_dry_run_langsmith_report_includes_pending_case(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    original_suite: dict[str, object] = {"cases": [], "runs": []}
    suite_file.write_text(json.dumps(original_suite) + "\n", encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_failed_rag",
                "name": "Failed RAG run should cite source",
                "userInput": "How should Reactor cite RAG answers?",
                "expectedAnswerContains": ["[runbook.md]"],
                "enabled": True,
                "minScore": 1.0,
                "sourceRunId": "run_failed_rag",
                "tags": ["rag", "documents-ask"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    langsmith_report_file = tmp_path / "langsmith-dry-run.json"
    exit_code = main(
        [
            "--suite-file",
            str(suite_file),
            "--case-file",
            str(case_file),
            "--dataset-name",
            "reactor-regression",
            "--dry-run",
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
        ]
    )

    assert exit_code == 0
    apply_report = json.loads(capsys.readouterr().out)
    assert apply_report["status"] == "would_add"
    assert apply_report["persistCommand"] == (
        f"reactor-agent-eval-apply --case-file {case_file} "
        f"--suite-file {suite_file} --dataset-name reactor-regression "
        f"--langsmith-dry-run-report-file {langsmith_report_file} --output table"
    )
    assert apply_report["langsmithDryRun"]["caseIds"] == ["case_failed_rag"]
    langsmith_report = json.loads(langsmith_report_file.read_text(encoding="utf-8"))
    assert langsmith_report["caseIds"] == ["case_failed_rag"]
    assert json.loads(suite_file.read_text(encoding="utf-8")) == original_suite


def test_apply_promoted_eval_case_table_shows_langsmith_dry_run_next_actions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_failed_rag",
                "name": "Failed RAG run should cite source",
                "userInput": "How should Reactor cite RAG answers?",
                "expectedAnswerContains": ["[runbook.md]"],
                "enabled": True,
                "minScore": 1.0,
                "sourceRunId": "run_failed_rag",
                "tags": [
                    "rag",
                    "documents-ask",
                    "feedback:fb_1",
                    "feedback-rating:thumbs_down",
                    "feedback-source:slack_button",
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    langsmith_report_file = tmp_path / "langsmith-dry-run.json"
    exit_code = main(
        [
            "--suite-file",
            str(suite_file),
            "--case-file",
            str(case_file),
            "--dataset-name",
            "reactor-regression",
            "--dry-run",
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
            "--feedback-review-status",
            "done",
            "--feedback-review-tag",
            "promoted",
            "--feedback-review-tag",
            "langsmith",
            "--feedback-review-tag",
            "rag-candidate:grounded_citation",
            "--feedback-review-note",
            RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
            "--output",
            "table",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    rows = dict(line.split(maxsplit=1) for line in output.splitlines()[1:])
    assert rows["langsmithDryRunStatus"] == "skipped"
    assert rows["langsmithDryRunDataset"] == "reactor-regression"
    assert rows["langsmithDryRunCases"] == "1"
    assert rows["langsmithSourceRunIds"] == "1"
    assert rows["langsmithCaseSourceRunMappings"] == "1"
    assert rows["langsmithDryRunFeedbackIds"] == "fb_1"
    assert rows["langsmithDryRunFeedbackSources"] == "slack_button=1"
    assert rows["langsmithDryRunFeedbackWorkflows"] == "documents-ask=1,grounding=1,rag=1"
    assert rows["langsmithDryRunExpectedCitations"] == "runbook.md=1"
    assert rows["langsmithFeedbackReviewAction"] == (
        "reactor-admin feedback --feedback-id fb_1 --output table"
    )
    assert rows["langsmithDryRunReport"] == str(langsmith_report_file)
    feedback_review_args = (
        "--feedback-review-status done "
        "--feedback-review-tag promoted "
        "--feedback-review-tag langsmith "
        "--feedback-review-tag rag-candidate:grounded_citation "
        f"--feedback-review-note {RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE!r}"
    )
    assert rows["langsmithSyncCommand"] == (
        f"uv run reactor-langsmith-eval-sync --suite-file {suite_file} "
        f"--dataset-name reactor-regression --dry-run --report-file {langsmith_report_file} "
        f"{feedback_review_args}"
    )
    assert rows["langsmithLiveSyncCommand"] == (
        f"uv run reactor-langsmith-eval-sync --suite-file {suite_file} "
        f"--dataset-name reactor-regression --report-file {langsmith_report_file} "
        f"{feedback_review_args} "
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync "
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
    )
    assert rows["langsmithPersistCommand"] == (
        f"reactor-agent-eval-apply --case-file {case_file} "
        f"--suite-file {suite_file} --dataset-name reactor-regression "
        f"--langsmith-dry-run-report-file {langsmith_report_file} --output table"
    )
    assert rows["langsmithReplatformReadinessFile"] == (
        "reports/release/replatform-readiness.local.json"
    )
    assert rows["langsmithSmokePlanFile"] == "reports/release/release-smoke-plan.local.json"
    assert rows["langsmithReleaseEvidenceFile"] == "reports/release-evidence.json"
    assert rows["langsmithReleaseReadinessFile"] == "reports/release-readiness.json"
    assert rows["suitePersistCommand"] == (
        f"reactor-agent-eval-apply --case-file {case_file} "
        f"--suite-file {suite_file} --dataset-name reactor-regression "
        f"--langsmith-dry-run-report-file {langsmith_report_file} --output table"
    )
    assert rows["langsmithReadinessCommand"] == (
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
        "--required-readiness-report langsmith_eval_sync "
        f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
    )
    assert rows["langsmithReleaseGate"] == "blocked"
    assert rows["langsmithReleaseGateNext"] == "run_reactor_langsmith_eval_sync_without_dry_run"


def test_apply_promoted_eval_case_table_shows_langsmith_release_gate_reason(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_missing_source",
                "name": "Missing source provenance should block sync",
                "userInput": "How should Reactor cite RAG answers?",
                "expectedAnswerContains": ["runbook.md"],
                "enabled": True,
                "minScore": 1.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    langsmith_report_file = tmp_path / "langsmith-dry-run.json"

    exit_code = main(
        [
            "--suite-file",
            str(suite_file),
            "--case-file",
            str(case_file),
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
            "--feedback-review-status",
            "done",
            "--feedback-review-tag",
            "promoted",
            "--feedback-review-tag",
            "langsmith",
            "--feedback-review-tag",
            "rag-candidate:grounded_citation",
            "--feedback-review-note",
            RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
            "--output",
            "table",
        ]
    )

    assert exit_code == 0
    rows = dict(line.split(maxsplit=1) for line in capsys.readouterr().out.splitlines()[1:])
    assert rows["langsmithSourceRunIds"] == "0"
    assert rows["langsmithCaseSourceRunMappings"] == "0"
    assert rows["langsmithReleaseGate"] == "blocked"
    assert rows["langsmithReleaseGateReason"] == "missing_source_run_provenance"
    assert rows["langsmithReleaseGateNext"] == "regenerate_langsmith_eval_sync_with_source_run_ids"


def test_langsmith_dry_run_table_rows_show_release_gate_remediation_command() -> None:
    rows = dict(
        langsmith_dry_run_table_rows(
            {
                "status": "failed",
                "datasetName": "reactor-rag-ingestion-candidate",
                "caseIds": ["case_rag_candidate_c1"],
                "releaseGate": {
                    "status": "blocked",
                    "reason": "feedback_review_queue_source_missing",
                    "remediationCommand": (
                        "reactor-admin feedback --rating thumbs_down "
                        "--tag collection:rag-ingestion-candidate --output table"
                    ),
                    "remediation": ["resubmit_feedback_with_source_metadata"],
                },
            }
        )
    )

    assert rows["langsmithReleaseGate"] == "blocked"
    assert rows["langsmithReleaseGateReason"] == "feedback_review_queue_source_missing"
    assert rows["langsmithReleaseGateNext"] == "resubmit_feedback_with_source_metadata"
    assert rows["langsmithReleaseGateRemediationCommand"] == (
        "reactor-admin feedback --rating thumbs_down "
        "--tag collection:rag-ingestion-candidate --output table"
    )


def test_apply_promoted_eval_case_cli_can_summarize_source_controlled_suite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case_active",
                        "name": "Active case",
                        "userInput": "Question",
                        "enabled": True,
                        "tags": ["rag"],
                        "minScore": 1.0,
                    },
                    {
                        "id": "case_disabled",
                        "name": "Disabled case",
                        "userInput": "Question",
                        "enabled": False,
                        "tags": ["tool"],
                        "minScore": 1.0,
                    },
                ],
                "runs": [
                    {
                        "runId": "run_active",
                        "evalCaseId": "case_active",
                        "userInput": "Question",
                        "agentType": "standard",
                        "model": "test-model",
                        "finalAnswer": "Answer",
                        "toolCalls": [],
                        "toolExposure": {"count": 0, "names": []},
                        "retrievedChunks": [],
                        "errors": [],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    exit_code = main(
        [
            "--suite-file",
            str(suite_file),
            "--summary",
            "--output",
            "table",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert output == (
        "FIELD          VALUE\n"
        "suiteFile      "
        f"{suite_file}\n"
        "caseCount      2\n"
        "enabledCases   1\n"
        "disabledCases  1\n"
        "runCount       1\n"
        "coveredCases   1\n"
        "missingRuns    0\n"
        "missingRunIds  \n"
        "caseIds        case_active,case_disabled\n"
    )


def test_apply_promoted_eval_case_cli_summary_writes_langsmith_dry_run_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    suite_file = tmp_path / "rag-ingestion-candidate.json"
    suite_file.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case_rag_candidate_grounded_citation",
                        "name": "RAG candidate answer cites grounded source",
                        "userInput": "What does the candidate document say?",
                        "expectedAnswerContains": ["[doc_1]"],
                        "enabled": True,
                        "tags": [
                            "collection:rag-ingestion-candidate",
                            "feedback-rating:thumbs_down",
                            "feedback-source:slack_button",
                            "rag",
                            "documents-ask",
                        ],
                        "minScore": 1.0,
                        "sourceRunId": "run_rag_candidate_grounded_citation",
                    }
                ],
                "runs": [
                    {
                        "runId": "run_rag_candidate_grounded_citation",
                        "evalCaseId": "case_rag_candidate_grounded_citation",
                        "userInput": "What does the candidate document say?",
                        "agentType": "documents-ask",
                        "model": "test-model",
                        "finalAnswer": "The candidate document says to cite doc_1. [doc_1]",
                        "toolCalls": [],
                        "toolExposure": {"count": 0, "names": []},
                        "retrievedChunks": [
                            {
                                "documentId": "doc_1",
                                "source": "docs://reactor/rag-candidate.md",
                                "title": "Candidate document",
                                "score": 1.0,
                                "cited": True,
                            }
                        ],
                        "contextManifestDiagnostics": {
                            "ok": True,
                            "status": "passed",
                            "ragGroundingPolicy": {
                                "citationTracking": "required",
                                "uncitedChunksTracked": True,
                                "aclEvidence": "acl_hash_only",
                                "rawAclMetadataVisible": False,
                            },
                            "citationCount": 1,
                            "chunkCount": 1,
                            "citedChunkCount": 1,
                            "uncitedChunkCount": 0,
                            "memoryStatusCounts": {"active": 1},
                            "skippedMemoryStatusCounts": {},
                            "citations": [
                                {
                                    "citationId": "doc_1",
                                    "evalCaseId": "case_rag_candidate_grounded_citation",
                                    "workflowTags": ["rag-candidate:grounded_citation"],
                                }
                            ],
                        },
                        "errors": [],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    langsmith_report_file = tmp_path / "langsmith-dry-run.json"

    exit_code = main(
        [
            "--suite-file",
            str(suite_file),
            "--dataset-name",
            "reactor-rag-ingestion-candidate",
            "--summary",
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
            "--feedback-review-status",
            "done",
            "--feedback-review-tag",
            "promoted",
            "--feedback-review-tag",
            "langsmith",
            "--feedback-review-tag",
            "rag-candidate:grounded_citation",
            "--feedback-review-note",
            RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
            "--output",
            "table",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "langsmithDryRunStatus" in output
    rows = {
        field: value.strip()
        for line in output.splitlines()[1:]
        if line.strip()
        for field, _, value in [line.partition("  ")]
    }
    assert rows["langsmithSummaryCommand"] == (
        f"reactor-agent-eval-apply --suite-file {suite_file} "
        "--dataset-name reactor-rag-ingestion-candidate --summary "
        f"--langsmith-dry-run-report-file {langsmith_report_file} "
        "--feedback-review-status done "
        "--feedback-review-tag promoted "
        "--feedback-review-tag langsmith "
        "--feedback-review-tag rag-candidate:grounded_citation "
        f"--feedback-review-note {RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE!r} "
        "--output table"
    )
    assert "langsmithReadinessCommand" in output
    assert str(langsmith_report_file) in output
    langsmith_report = json.loads(langsmith_report_file.read_text(encoding="utf-8"))
    assert langsmith_report["caseIds"] == ["case_rag_candidate_grounded_citation"]
    assert langsmith_report["sourceRunIds"] == ["run_rag_candidate_grounded_citation"]
    assert langsmith_report["feedbackReviewQueue"]["reviewStatus"] == "done"
    assert langsmith_report["feedbackReviewQueue"]["reviewTags"] == [
        "promoted",
        "langsmith",
        "rag-candidate:grounded_citation",
    ]
    assert (
        langsmith_report["feedbackReviewQueue"]["reviewNote"]
        == RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE
    )
    assert langsmith_report["evidence"]["traceGrading"]["gradedRuns"] == 1
    assert langsmith_report["evidence"]["contextManifestDiagnostics"][
        "citationWorkflowEvalCaseIds"
    ] == ["case_rag_candidate_grounded_citation"]
    assert langsmith_report["evidence"]["contextManifestDiagnostics"]["citationWorkflowTags"] == [
        "rag-candidate:grounded_citation"
    ]
    assert langsmith_report["evidence"]["productCapabilityBoundary"] == {
        "capability": "rag_ingest_to_feedback_eval_langsmith_readiness",
        "evidence": [
            "rag_ingestion_candidate_feedback_queue",
            "feedback_promotion.reviewed_feedback",
            "langsmith_trace_grading",
            "release_readiness_command",
        ],
        "minorEligible": False,
        "missingEvidence": ["rag_ingestion_lifecycle"],
    }


def test_apply_promoted_eval_case_cli_dry_run_summary_includes_pending_case_and_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    original_suite: dict[str, object] = {"cases": [], "runs": []}
    suite_file.write_text(json.dumps(original_suite) + "\n", encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_documents_ask_citations",
                "name": "Documents ask should cite sources",
                "userInput": "How should RAG answers cite sources?",
                "expectedAnswerContains": ["doc_1"],
                "enabled": True,
                "minScore": 1.0,
                "sourceRunId": "run_documents_ask",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_file = tmp_path / "promoted-run.json"
    run_file.write_text(
        json.dumps(
            {
                "runId": "run_documents_ask",
                "evalCaseId": "case_documents_ask_citations",
                "userInput": "How should RAG answers cite sources?",
                "agentType": "documents-ask",
                "model": "test-model",
                "finalAnswer": "Use citations for Reactor RAG answers. [doc_1]",
                "toolCalls": [],
                "toolExposure": {"count": 0, "names": []},
                "retrievedChunks": [
                    {
                        "documentId": "doc_1",
                        "source": "docs://reactor/runbooks/rag.md",
                        "title": "RAG runbook",
                        "score": 1.0,
                        "cited": True,
                    }
                ],
                "errors": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    langsmith_report_file = tmp_path / "langsmith-dry-run.json"

    exit_code = main(
        [
            "--suite-file",
            str(suite_file),
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--dry-run",
            "--summary",
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
            "--output",
            "table",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    rows = {
        field: value.strip()
        for line in output.splitlines()[1:]
        if line.strip()
        for field, _, value in [line.partition("  ")]
    }
    assert rows["suiteFile"] == str(suite_file)
    assert rows["caseCount"] == "1"
    assert rows["enabledCases"] == "1"
    assert rows["disabledCases"] == "0"
    assert rows["runCount"] == "1"
    assert rows["coveredCases"] == "1"
    assert rows["missingRuns"] == "0"
    assert rows["caseIds"] == "case_documents_ask_citations"
    assert "langsmithDryRunStatus" in output
    assert "langsmithDryRunCases" in output
    assert "langsmithGroundingCases" in output
    assert "langsmithReadinessCommand" in output
    assert str(langsmith_report_file) in output
    langsmith_report = json.loads(langsmith_report_file.read_text(encoding="utf-8"))
    assert langsmith_report["caseIds"] == ["case_documents_ask_citations"]
    assert langsmith_report["evidence"]["traceGrading"]["gradedRuns"] == 1
    assert json.loads(suite_file.read_text(encoding="utf-8")) == original_suite


def test_apply_promoted_eval_case_summary_reports_enabled_cases_missing_runs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case_with_run",
                        "name": "Covered case",
                        "userInput": "Question",
                        "enabled": True,
                        "minScore": 1.0,
                    },
                    {
                        "id": "case_missing_run",
                        "name": "Missing run fixture",
                        "userInput": "Question",
                        "enabled": True,
                        "minScore": 1.0,
                    },
                    {
                        "id": "case_disabled_missing_run",
                        "name": "Disabled missing run fixture",
                        "userInput": "Question",
                        "enabled": False,
                        "minScore": 1.0,
                    },
                ],
                "runs": [
                    {
                        "runId": "run_with_fixture",
                        "evalCaseId": "case_with_run",
                        "userInput": "Question",
                        "agentType": "standard",
                        "model": "test-model",
                        "finalAnswer": "Answer",
                        "toolCalls": [],
                        "toolExposure": {"count": 0, "names": []},
                        "retrievedChunks": [],
                        "errors": [],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--suite-file",
            str(suite_file),
            "--summary",
            "--output",
            "table",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "coveredCases   1\n" in output
    assert "missingRuns    1\n" in output
    assert "missingRunIds  case_missing_run\n" in output
