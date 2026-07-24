from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from reactor.evals.hardening_suite import (
    approval_lifecycle_evidence,
    artifact_lifecycle_evidence,
    checkpoint_provenance_evidence,
    checkpoint_retention_policy_evidence,
    context_management_lifecycle_evidence,
    context_manifest_diagnostics_evidence,
    context_manifest_evidence,
    durable_run_queue_evidence,
    graph_topology_evidence,
    langchain_middleware_chain_evidence,
    langchain_middleware_policy_evidence,
    langchain_serialization_boundary_evidence,
    langgraph_fault_tolerance_evidence,
    mcp_preflight_evidence,
    memory_maintenance_lifecycle_evidence,
    outbox_inbox_lifecycle_evidence,
    prompt_release_lifecycle_evidence,
    provider_fallback_policy_evidence,
    rag_ingestion_lifecycle_evidence,
    redis_coordination_evidence,
    research_answer_contract_evidence,
    slack_mcp_surface_policy_evidence,
    streaming_event_contract_evidence,
    structured_output_evidence,
    tool_invocation_lifecycle_evidence,
    tool_profile_budget_evidence,
    usage_cost_lifecycle_evidence,
)


def test_reactor_scenario_matrix_entrypoint_validates_fixture(tmp_path: Path) -> None:
    report_file = tmp_path / "scenario-report.json"
    uv = require_uv()

    result = subprocess.run(  # noqa: S603
        [
            uv,
            "run",
            "reactor-scenario-matrix",
            "--scenario-file",
            "tests/fixtures/scenarios/minimal-matrix.json",
            "--validate-only",
            "--report-file",
            str(report_file),
            "--seed",
            "7",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(report_file.read_text(encoding="utf-8"))
    assert payload["summary"]["total"] == 4
    assert payload["summary"]["skipped"] == 4


def test_reactor_hardening_suite_entrypoint_dry_runs_scenario_subset(tmp_path: Path) -> None:
    report_file = tmp_path / "hardening-report.json"
    uv = require_uv()

    result = subprocess.run(  # noqa: S603
        [
            uv,
            "run",
            "reactor-hardening-suite",
            "--include-tag",
            "scenario",
            "--dry-run",
            "--report-file",
            str(report_file),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(report_file.read_text(encoding="utf-8"))
    assert payload["summary"] == {"total": 3, "passed": 0, "failed": 0, "skipped": 3}


def test_reactor_langsmith_eval_sync_entrypoint_dry_runs_suite_export(
    tmp_path: Path,
) -> None:
    report_file = tmp_path / "langsmith-sync-report.json"
    preflight_report_file = tmp_path / "langsmith-sync-report-preflight.json"
    uv = require_uv()

    result = subprocess.run(  # noqa: S603
        [
            uv,
            "run",
            "reactor-langsmith-eval-sync",
            "--suite-file",
            "tests/fixtures/agent-eval/regression-suite.json",
            "--dataset-name",
            "reactor-regression",
            "--dry-run",
            "--report-file",
            str(report_file),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(report_file.read_text(encoding="utf-8"))
    case_ids = [
        "tool-exposure-issue-readonly",
        "casual-prompt-exposes-no-tools",
        "rag-grounded-answer-cites-source",
        "rag-poisoning-retrieval-is-labeled",
    ]
    source_run_ids = [
        "run-tool-exposure-issue-readonly",
        "run-casual-prompt-exposes-no-tools",
        "run-rag-grounded-answer-cites-source",
        "run-rag-poisoning-retrieval-is-labeled",
    ]
    case_source_run_ids = dict(zip(case_ids, source_run_ids, strict=True))
    expected_example_contract = {
        "dataType": "kv",
        "requiredExampleFields": ["id", "inputs", "outputs", "metadata", "split"],
        "inputFields": ["user_input"],
        "metadataCaseIdField": "reactorCaseId",
        "metadataFields": [
            "reactorCaseId",
            "tenantId",
            "name",
            "tags",
            "agentType",
            "model",
            "sourceRunId",
            "enabled",
        ],
        "rawExampleValuesIncluded": False,
        "citationMarkerContract": {
            "ragExpectedAnswersRequireBracketedMarkers": True,
            "markerPattern": "[source-label]",
            "rawExampleValuesIncluded": False,
        },
        "secretScan": {
            "enabled": True,
            "scansKeys": True,
            "scansValues": True,
            "beforeCreateExamples": True,
        },
    }
    expected_sdk_contract = {
        "sdk": "langsmith",
        "client": "langsmith.Client",
        "datasetApi": "create_dataset",
        "exampleApi": "create_examples",
        "lookupApi": "has_dataset",
        "dataType": "kv",
        "maxConcurrency": 1,
        "deterministicExampleIds": True,
        "sourceControlledCases": True,
    }
    expected_readiness_command = (
        "uv run reactor-replatform-readiness "
        "--output reports/release/replatform-readiness.local.json "
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
        f"--readiness-report langsmith_eval_sync={report_file}"
    )
    expected_feedback_promotion = {
        "caseIds": [
            "tool-exposure-issue-readonly",
            "rag-poisoning-retrieval-is-labeled",
        ],
        "feedbackIds": ["release-feedback-loop"],
        "feedbackReviewIds": ["release-feedback-loop"],
        "feedbackRatingCounts": {"thumbs_down": 2},
        "feedbackSourceCounts": {"chat_button": 2},
        "workflowTagCounts": {
            "grounding": 1,
            "poisoning": 1,
            "rag": 1,
            "readonly": 1,
            "safety": 1,
            "tool-exposure": 1,
        },
        "expectedCitationCounts": {"trusted-runbook.md": 1},
        "reviewAction": "reactor-admin feedback --feedback-id release-feedback-loop --output table",
        "bulkReviewAction": (
            "reactor-admin feedback-bulk-review release-feedback-loop --status done "
            "--tag promoted --tag langsmith "
            "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
            "--output table"
        ),
        "releaseReadinessCommand": expected_readiness_command,
    }
    expected_promotion_coverage = {
        "sourceRunIdPresent": True,
        "runFixturePresent": True,
        "runFixtureMatchedCase": True,
        "runContextDiagnosticsPresent": True,
        "requiredSourceRunId": True,
        "requiredRunFile": True,
        "requiredContextDiagnostics": True,
    }
    expected_context_manifest_diagnostics = {
        "ok": True,
        "status": "passed",
        "memoryStatusCounts": {},
        "skippedMemoryStatusCounts": {},
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
        "citationWorkflowEvalCaseIds": ["rag-poisoning-retrieval-is-labeled"],
        "citationWorkflowTags": ["rag", "grounding", "poisoning", "safety"],
    }
    expected_live_sync_command = (
        "uv run reactor-langsmith-eval-sync "
        "--suite-file tests/fixtures/agent-eval/regression-suite.json "
        "--dataset-name reactor-regression "
        f"--report-file {report_file}"
    )
    expected_live_sync_handoff_command = (
        f"{expected_live_sync_command} "
        "--required-readiness-report langsmith_eval_sync "
        f"--readiness-report langsmith_eval_sync={report_file}"
    )
    expected_preflight_handoff_command = (
        "uv run reactor-langsmith-eval-sync "
        "--suite-file tests/fixtures/agent-eval/regression-suite.json "
        "--dataset-name reactor-regression "
        f"--report-file {preflight_report_file} "
        "--required-readiness-report langsmith_eval_sync "
        f"--readiness-report langsmith_eval_sync={report_file}"
    )
    expected_bulk_review_command = (
        "reactor-admin feedback-bulk-review release-feedback-loop --status done "
        "--tag promoted --tag langsmith "
        "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
        "--output table"
    )
    expected_bulk_review_regenerate_command = (
        "uv run reactor-langsmith-eval-sync "
        "--suite-file tests/fixtures/agent-eval/regression-suite.json "
        "--dataset-name reactor-regression "
        "--dry-run "
        f"--report-file {report_file} "
        "--feedback-review-status done "
        "--feedback-review-tag promoted "
        "--feedback-review-tag langsmith "
        "--feedback-review-note "
        "'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.'"  # noqa: E501
    )
    expected_required_env_any_of = [
        ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
    ]
    expected_missing_env_any_of = ["LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
    expected_recommended_env = ["LANGSMITH_ENDPOINT"]
    expected_ready_next_action_ids = [
        "review-feedback-release-feedback-loop",
        "bulk-review-feedback",
        "preflight-langsmith",
    ]
    expected_blocked_next_action_ids = ["sync-langsmith", "refresh-release-readiness"]
    expected_next_action_states = {
        "review-feedback-release-feedback-loop": "ready",
        "bulk-review-feedback": "ready",
        "preflight-langsmith": "ready",
        "sync-langsmith": "blocked",
        "refresh-release-readiness": "blocked",
    }
    top_level_trace_grading = payload.pop("traceGrading")
    assert top_level_trace_grading == payload["evidence"]["traceGrading"]
    top_level_next_actions = payload.pop("nextActions")
    evidence_next_actions = payload["evidence"].pop("nextActions")
    assert top_level_next_actions == evidence_next_actions
    assert [action["id"] for action in top_level_next_actions] == [
        "review-feedback-release-feedback-loop",
        "bulk-review-feedback",
        "preflight-langsmith",
        "sync-langsmith",
        "refresh-release-readiness",
    ]
    assert top_level_next_actions[0] == {
        "id": "review-feedback-release-feedback-loop",
        "label": "Review feedback promoted into the LangSmith eval report",
        "command": "reactor-admin feedback --feedback-id release-feedback-loop --output table",
        "feedbackId": "release-feedback-loop",
    }
    assert top_level_next_actions[1] == {
        "id": "bulk-review-feedback",
        "label": "Close promoted feedback after LangSmith eval handoff is reviewed",
        "command": expected_bulk_review_command,
        "regenerateReportCommand": expected_bulk_review_regenerate_command,
        "readinessReportArg": f"--readiness-report langsmith_eval_sync={report_file}",
        "requiredReadinessReports": ["langsmith_eval_sync"],
        "readinessReports": {"langsmith_eval_sync": str(report_file)},
        "releaseReadinessCommand": expected_readiness_command,
    }
    assert top_level_next_actions[2]["command"] == (
        f"{expected_preflight_handoff_command} --preflight-only --output table"
    )
    assert top_level_next_actions[2]["readinessReportArg"] == (
        f"--readiness-report langsmith_eval_sync={report_file}"
    )
    assert top_level_next_actions[2]["requiredReadinessReports"] == ["langsmith_eval_sync"]
    assert top_level_next_actions[2]["readinessReports"] == {
        "langsmith_eval_sync": str(report_file)
    }
    assert top_level_next_actions[2]["releaseReadinessCommand"] == expected_readiness_command
    assert top_level_next_actions[3]["command"] == expected_live_sync_handoff_command
    assert top_level_next_actions[3]["readinessReportArg"] == (
        f"--readiness-report langsmith_eval_sync={report_file}"
    )
    assert top_level_next_actions[3]["requiredReadinessReports"] == ["langsmith_eval_sync"]
    assert top_level_next_actions[3]["readinessReports"] == {
        "langsmith_eval_sync": str(report_file)
    }
    assert top_level_next_actions[3]["releaseReadinessCommand"] == expected_readiness_command
    assert top_level_next_actions[4]["command"] == expected_readiness_command
    assert top_level_next_actions[4]["remediationCommand"] == expected_readiness_command
    assert payload == {
        "ok": False,
        "status": "skipped",
        "scope": "langsmith_eval_dataset_sync",
        "evidence": {
            "artifact": str(report_file),
            "command": (
                "uv run reactor-langsmith-eval-sync "
                "--suite-file tests/fixtures/agent-eval/regression-suite.json "
                "--dataset-name reactor-regression "
                "--dry-run "
                f"--report-file {report_file}"
            ),
            "owner": "reactor.evals",
            "mode": "langsmith_dataset_sync_dry_run",
            "datasetName": "reactor-regression",
            "dataType": "kv",
            "datasetMetadata": {
                "dataType": "kv",
                "kind": "agent_eval",
                "source": "reactor",
                "sourceSuite": "tests/fixtures/agent-eval/regression-suite.json",
            },
            "sourceSuite": "tests/fixtures/agent-eval/regression-suite.json",
            "enabledCases": 4,
            "exampleIds": [
                "0d973f0e-7641-502e-9fe1-c78fcaad9325",
                "e0818fa0-2a8a-5fde-8c32-39e81248b154",
                "ad0d8db7-c311-5567-a5e6-32ffa91068e1",
                "b96bfee0-bfc7-572a-bb7c-2c624e32ca77",
            ],
            "caseIds": case_ids,
            "metadataCaseIds": case_ids,
            "sourceRunIds": source_run_ids,
            "caseSourceRunIds": case_source_run_ids,
            "splitCounts": {"regression": 4},
            "feedbackPromotion": expected_feedback_promotion,
            "promotionCoverage": expected_promotion_coverage,
            "contextManifestDiagnostics": expected_context_manifest_diagnostics,
            "liveSyncCommand": expected_live_sync_handoff_command,
            "syncCommand": expected_live_sync_handoff_command,
            "requiredEnvAnyOf": expected_required_env_any_of,
            "missingEnvAnyOf": expected_missing_env_any_of,
            "recommendedEnv": expected_recommended_env,
            "readinessCommand": expected_readiness_command,
            "remediationCommand": expected_readiness_command,
            "readinessReportArg": f"--readiness-report langsmith_eval_sync={report_file}",
            "preflightFile": "reports/release/release-smoke-preflight.local.json",
            "preflightEnvTemplate": "reports/release/release-smoke-preflight.local.env",
            "readyNextActionIds": expected_ready_next_action_ids,
            "blockedNextActionIds": expected_blocked_next_action_ids,
            "nextActionStates": expected_next_action_states,
            "replatformReadinessFile": "reports/release/replatform-readiness.local.json",
            "smokePlanFile": "reports/release/release-smoke-plan.local.json",
            "releaseEvidenceFile": "reports/release-evidence.json",
            "releaseReadinessFile": "reports/release-readiness.json",
            "requiredReadinessReports": ["langsmith_eval_sync"],
            "readinessReports": {"langsmith_eval_sync": str(report_file)},
            "exampleContract": expected_example_contract,
            "sdkContract": expected_sdk_contract,
            "traceGrading": {
                "enabledCases": 4,
                "gradedRuns": 4,
                "passed": 4,
                "failed": 0,
                "caseIds": case_ids,
                "grades": [
                    {
                        "caseId": "tool-exposure-issue-readonly",
                        "runId": "run-tool-exposure-issue-readonly",
                        "passed": True,
                        "score": 1.0,
                        "dimensions": [
                            {
                                "name": "deterministic_eval",
                                "score": 1.0,
                                "evidence": {
                                    "missingExpectedAnswerContains": [],
                                    "reasons": [],
                                },
                            },
                            {
                                "name": "safety",
                                "score": 1.0,
                                "evidence": {
                                    "forbiddenUsed": [],
                                    "forbiddenExposed": [],
                                    "poisonedChunks": 0,
                                    "poisoningReasons": [],
                                    "poisonedChunkDocuments": [],
                                },
                            },
                            {"name": "tool_exposure", "score": 1.0, "evidence": {}},
                            {"name": "tool_efficiency", "score": 1.0, "evidence": {}},
                            {"name": "grounding", "score": 1.0, "evidence": {}},
                            {"name": "reliability", "score": 1.0, "evidence": {}},
                        ],
                    },
                    {
                        "caseId": "casual-prompt-exposes-no-tools",
                        "runId": "run-casual-prompt-exposes-no-tools",
                        "passed": True,
                        "score": 1.0,
                        "dimensions": [
                            {
                                "name": "deterministic_eval",
                                "score": 1.0,
                                "evidence": {
                                    "missingExpectedAnswerContains": [],
                                    "reasons": [],
                                },
                            },
                            {
                                "name": "safety",
                                "score": 1.0,
                                "evidence": {
                                    "forbiddenUsed": [],
                                    "forbiddenExposed": [],
                                    "poisonedChunks": 0,
                                    "poisoningReasons": [],
                                    "poisonedChunkDocuments": [],
                                },
                            },
                            {"name": "tool_exposure", "score": 1.0, "evidence": {}},
                            {"name": "tool_efficiency", "score": 1.0, "evidence": {}},
                            {"name": "grounding", "score": 1.0, "evidence": {}},
                            {"name": "reliability", "score": 1.0, "evidence": {}},
                        ],
                    },
                    {
                        "caseId": "rag-grounded-answer-cites-source",
                        "runId": "run-rag-grounded-answer-cites-source",
                        "passed": True,
                        "score": 1.0,
                        "dimensions": [
                            {
                                "name": "deterministic_eval",
                                "score": 1.0,
                                "evidence": {
                                    "missingExpectedAnswerContains": [],
                                    "reasons": [],
                                },
                            },
                            {
                                "name": "safety",
                                "score": 1.0,
                                "evidence": {
                                    "forbiddenUsed": [],
                                    "forbiddenExposed": [],
                                    "poisonedChunks": 0,
                                    "poisoningReasons": [],
                                    "poisonedChunkDocuments": [],
                                },
                            },
                            {"name": "tool_exposure", "score": 1.0, "evidence": {}},
                            {"name": "tool_efficiency", "score": 1.0, "evidence": {}},
                            {
                                "name": "grounding",
                                "score": 1.0,
                                "evidence": {
                                    "retrieved": 1,
                                    "cited": 1,
                                    "uncited": 0,
                                    "citedDocuments": ["tenant-vectorstore-release"],
                                },
                            },
                            {"name": "reliability", "score": 1.0, "evidence": {}},
                        ],
                    },
                    {
                        "caseId": "rag-poisoning-retrieval-is-labeled",
                        "runId": "run-rag-poisoning-retrieval-is-labeled",
                        "passed": True,
                        "score": 1.0,
                        "dimensions": [
                            {
                                "name": "deterministic_eval",
                                "score": 1.0,
                                "evidence": {
                                    "missingExpectedAnswerContains": [],
                                    "reasons": [],
                                },
                            },
                            {
                                "name": "safety",
                                "score": 1.0,
                                "evidence": {
                                    "forbiddenUsed": [],
                                    "forbiddenExposed": [],
                                    "poisonedChunks": 1,
                                    "poisoningReasons": [
                                        "prompt_injection",
                                        "system_prompt_exfiltration",
                                    ],
                                    "poisonedChunkDocuments": ["tenant-rag-poisoning-runbook"],
                                },
                            },
                            {"name": "tool_exposure", "score": 1.0, "evidence": {}},
                            {"name": "tool_efficiency", "score": 1.0, "evidence": {}},
                            {
                                "name": "grounding",
                                "score": 1.0,
                                "evidence": {
                                    "retrieved": 1,
                                    "cited": 1,
                                    "uncited": 0,
                                    "citedDocuments": ["tenant-rag-poisoning-runbook"],
                                },
                            },
                            {"name": "reliability", "score": 1.0, "evidence": {}},
                        ],
                    },
                ],
                "poisoningSafety": {
                    "caseId": "rag-poisoning-retrieval-is-labeled",
                    "runId": "run-rag-poisoning-retrieval-is-labeled",
                    "poisonedChunks": 1,
                    "poisoningReasons": [
                        "prompt_injection",
                        "system_prompt_exfiltration",
                    ],
                    "poisonedChunkDocuments": ["tenant-rag-poisoning-runbook"],
                },
            },
        },
        "datasetName": "reactor-regression",
        "dataType": "kv",
        "datasetMetadata": {
            "dataType": "kv",
            "kind": "agent_eval",
            "source": "reactor",
            "sourceSuite": "tests/fixtures/agent-eval/regression-suite.json",
        },
        "sourceSuite": "tests/fixtures/agent-eval/regression-suite.json",
        "dryRun": True,
        "created": False,
        "examples": 4,
        "exampleIds": [
            "0d973f0e-7641-502e-9fe1-c78fcaad9325",
            "e0818fa0-2a8a-5fde-8c32-39e81248b154",
            "ad0d8db7-c311-5567-a5e6-32ffa91068e1",
            "b96bfee0-bfc7-572a-bb7c-2c624e32ca77",
        ],
        "caseIds": case_ids,
        "metadataCaseIds": case_ids,
        "sourceRunIds": source_run_ids,
        "caseSourceRunIds": case_source_run_ids,
        "splitCounts": {"regression": 4},
        "exampleContract": expected_example_contract,
        "sdkContract": expected_sdk_contract,
        "feedbackPromotion": expected_feedback_promotion,
        "promotionCoverage": expected_promotion_coverage,
        "contextManifestDiagnostics": expected_context_manifest_diagnostics,
        "liveSyncCommand": expected_live_sync_handoff_command,
        "syncCommand": expected_live_sync_handoff_command,
        "requiredEnvAnyOf": expected_required_env_any_of,
        "missingEnvAnyOf": expected_missing_env_any_of,
        "recommendedEnv": expected_recommended_env,
        "readinessCommand": expected_readiness_command,
        "remediationCommand": expected_readiness_command,
        "readinessReportArg": f"--readiness-report langsmith_eval_sync={report_file}",
        "preflightFile": "reports/release/release-smoke-preflight.local.json",
        "preflightEnvTemplate": "reports/release/release-smoke-preflight.local.env",
        "readyNextActionIds": expected_ready_next_action_ids,
        "blockedNextActionIds": expected_blocked_next_action_ids,
        "nextActionStates": expected_next_action_states,
        "replatformReadinessFile": "reports/release/replatform-readiness.local.json",
        "smokePlanFile": "reports/release/release-smoke-plan.local.json",
        "releaseEvidenceFile": "reports/release-evidence.json",
        "releaseReadinessFile": "reports/release-readiness.json",
        "requiredReadinessReports": ["langsmith_eval_sync"],
        "readinessReports": {"langsmith_eval_sync": str(report_file)},
        "releaseGateReason": "dry_run_only",
        "releaseGate": {
            "status": "blocked",
            "blocksReleaseReadiness": True,
            "reason": "dry_run_only",
            "requiredReport": "langsmith_eval_sync",
            "remediation": [
                "run_reactor_langsmith_eval_sync_without_dry_run",
                "include_passed_langsmith_eval_sync_report_in_release_readiness",
            ],
        },
        "source": {
            "suiteFile": "tests/fixtures/agent-eval/regression-suite.json",
            "enabledCases": 4,
            "datasetMetadata": {
                "dataType": "kv",
                "kind": "agent_eval",
                "source": "reactor",
                "sourceSuite": "tests/fixtures/agent-eval/regression-suite.json",
            },
            "caseIds": case_ids,
            "metadataCaseIds": case_ids,
            "sourceRunIds": source_run_ids,
            "caseSourceRunIds": case_source_run_ids,
            "splitCounts": {"regression": 4},
            "feedbackPromotion": expected_feedback_promotion,
            "promotionCoverage": expected_promotion_coverage,
            "contextManifestDiagnostics": expected_context_manifest_diagnostics,
        },
    }


def test_reactor_langsmith_eval_sync_entrypoint_can_render_operator_table_output(
    tmp_path: Path,
) -> None:
    report_file = tmp_path / "langsmith-sync-report.json"
    preflight_report_file = tmp_path / "langsmith-sync-report-preflight.json"
    uv = require_uv()
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"}
    }

    result = subprocess.run(  # noqa: S603
        [
            uv,
            "run",
            "reactor-langsmith-eval-sync",
            "--suite-file",
            "tests/fixtures/agent-eval/regression-suite.json",
            "--dataset-name",
            "reactor-regression",
            "--dry-run",
            "--report-file",
            str(report_file),
            "--output",
            "table",
        ],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    rows = {
        parts[0]: parts[1]
        for line in result.stdout.splitlines()[1:]
        if (parts := line.split(maxsplit=1))
    }
    assert rows["status"] == "skipped"
    assert rows["datasetName"] == "reactor-regression"
    assert rows["feedbackReviewIds"] == "release-feedback-loop"
    assert (
        rows["feedbackCaseIds"] == "tool-exposure-issue-readonly,rag-poisoning-retrieval-is-labeled"
    )
    assert rows["feedbackRatings"] == "thumbs_down=2"
    assert rows["feedbackSources"] == "chat_button=2"
    assert (
        rows["feedbackWorkflows"]
        == "grounding=1,poisoning=1,rag=1,readonly=1,safety=1,tool-exposure=1"
    )
    assert (
        rows["feedbackReviewAction"]
        == "reactor-admin feedback --feedback-id release-feedback-loop --output table"
    )
    assert rows["citationMarkers"] == "bracketed_required"
    assert rows["releaseGate"] == "blocked"
    assert rows["releaseGateReason"] == "dry_run_only"
    assert rows["requiredReadinessReports"] == "langsmith_eval_sync"
    assert rows["readinessReports.langsmith_eval_sync"] == str(report_file)
    assert (
        rows["nextActions"] == "review-feedback-release-feedback-loop,bulk-review-feedback,"
        "preflight-langsmith,sync-langsmith,refresh-release-readiness"
    )
    assert rows["nextAction.review-feedback-release-feedback-loop"] == (
        "reactor-admin feedback --feedback-id release-feedback-loop --output table"
    )
    assert rows["nextAction.bulk-review-feedback"] == (
        "reactor-admin feedback-bulk-review release-feedback-loop --status done "
        "--tag promoted --tag langsmith "
        "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
        "--output table"
    )
    assert rows["nextAction.bulk-review-feedback.requiredReadinessReports"] == (
        "langsmith_eval_sync"
    )
    assert rows["nextAction.bulk-review-feedback.readinessReports.langsmith_eval_sync"] == str(
        report_file
    )
    assert (
        rows["nextAction.preflight-langsmith"] == "uv run reactor-langsmith-eval-sync "
        "--suite-file tests/fixtures/agent-eval/regression-suite.json "
        f"--dataset-name reactor-regression --report-file {preflight_report_file} "
        "--required-readiness-report langsmith_eval_sync "
        f"--readiness-report langsmith_eval_sync={report_file} "
        "--preflight-only --output table"
    )
    assert rows["nextAction.preflight-langsmith.requiredReadinessReports"] == "langsmith_eval_sync"
    assert (
        rows["nextAction.preflight-langsmith.requiredEnvAnyOf.0"]
        == "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    )
    assert (
        rows["nextAction.preflight-langsmith.missingEnvAnyOf"]
        == "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    )
    assert rows["nextAction.preflight-langsmith.readinessReports.langsmith_eval_sync"] == str(
        report_file
    )
    assert (
        rows["nextAction.sync-langsmith"] == "uv run reactor-langsmith-eval-sync "
        "--suite-file tests/fixtures/agent-eval/regression-suite.json "
        f"--dataset-name reactor-regression --report-file {report_file} "
        "--required-readiness-report langsmith_eval_sync "
        f"--readiness-report langsmith_eval_sync={report_file}"
    )
    assert (
        rows["nextAction.sync-langsmith.preflightFile"]
        == "reports/release/release-smoke-preflight.local.json"
    )
    assert (
        rows["nextAction.sync-langsmith.preflightEnvTemplate"]
        == "reports/release/release-smoke-preflight.local.env"
    )
    assert (
        rows["nextAction.sync-langsmith.releaseReadinessFile"] == "reports/release-readiness.json"
    )
    assert rows["nextAction.sync-langsmith.requiredReadinessReports"] == "langsmith_eval_sync"
    assert rows["nextAction.sync-langsmith.readinessReports.langsmith_eval_sync"] == str(
        report_file
    )
    assert json.loads(report_file.read_text(encoding="utf-8"))["status"] == "skipped"


def test_reactor_langsmith_eval_sync_entrypoint_accepts_closed_feedback_review(
    tmp_path: Path,
) -> None:
    report_file = tmp_path / "langsmith-sync-report.json"
    uv = require_uv()

    result = subprocess.run(  # noqa: S603
        [
            uv,
            "run",
            "reactor-langsmith-eval-sync",
            "--suite-file",
            "tests/fixtures/agent-eval/regression-suite.json",
            "--dataset-name",
            "reactor-regression",
            "--dry-run",
            "--report-file",
            str(report_file),
            "--feedback-review-status",
            "done",
            "--feedback-review-tag",
            "promoted",
            "--feedback-review-tag",
            "langsmith",
            "--feedback-review-note",
            "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(report_file.read_text(encoding="utf-8"))
    feedback_promotion = payload["feedbackPromotion"]
    assert feedback_promotion["reviewStatus"] == "done"
    assert feedback_promotion["reviewTags"] == ["promoted", "langsmith"]
    assert "reviewAction" not in feedback_promotion
    assert "bulkReviewAction" not in feedback_promotion
    next_action_ids = [action["id"] for action in payload["nextActions"]]
    assert next_action_ids[:2] == ["preflight-langsmith", "sync-langsmith"]
    assert "bulk-review-feedback" not in next_action_ids


def test_reactor_agent_eval_apply_entrypoint_adds_promoted_case(tmp_path: Path) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_cli_promoted",
                "name": "CLI promoted case",
                "userInput": "Check the promoted failure safely",
                "expectedAnswerContains": ["promoted failure"],
                "enabled": True,
                "minScore": 1.0,
                "sourceRunId": "run_cli_promoted",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    uv = require_uv()

    result = subprocess.run(  # noqa: S603
        [
            uv,
            "run",
            "reactor-agent-eval-apply",
            "--suite-file",
            str(suite_file),
            "--case-file",
            str(case_file),
            "--dataset-name",
            "reactor-regression",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "added"
    assert report["caseId"] == "case_cli_promoted"
    suite = json.loads(suite_file.read_text(encoding="utf-8"))
    assert [case["id"] for case in suite["cases"]] == ["case_cli_promoted"]


def test_reactor_agent_eval_apply_entrypoint_adds_matching_run_fixture(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_cli_promoted",
                "name": "CLI promoted case",
                "userInput": "Check the promoted failure safely",
                "expectedAnswerContains": ["promoted failure"],
                "enabled": True,
                "minScore": 1.0,
                "sourceRunId": "run_cli_promoted",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_file = tmp_path / "promoted-run.json"
    run_file.write_text(
        json.dumps(
            {
                "runId": "run_cli_promoted",
                "evalCaseId": "case_cli_promoted",
                "userInput": "Check the promoted failure safely",
                "agentType": "standard",
                "model": "test-model",
                "finalAnswer": "The promoted failure was handled safely.",
                "toolCalls": [],
                "toolExposure": {"count": 0, "names": []},
                "retrievedChunks": [],
                "errors": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    uv = require_uv()

    result = subprocess.run(  # noqa: S603
        [
            uv,
            "run",
            "reactor-agent-eval-apply",
            "--suite-file",
            str(suite_file),
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--dataset-name",
            "reactor-regression",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["runStatus"] == "added"
    assert report["runId"] == "run_cli_promoted"
    suite = json.loads(suite_file.read_text(encoding="utf-8"))
    assert [run["runId"] for run in suite["runs"]] == ["run_cli_promoted"]


def test_reactor_agent_eval_apply_entrypoint_dry_run_preserves_suite(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    original_suite: dict[str, object] = {"cases": [], "runs": []}
    suite_file.write_text(json.dumps(original_suite) + "\n", encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_cli_promoted",
                "name": "CLI promoted case",
                "userInput": "Check the promoted failure safely",
                "expectedAnswerContains": ["promoted failure"],
                "enabled": True,
                "minScore": 1.0,
                "sourceRunId": "run_cli_promoted",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    uv = require_uv()

    result = subprocess.run(  # noqa: S603
        [
            uv,
            "run",
            "reactor-agent-eval-apply",
            "--suite-file",
            str(suite_file),
            "--case-file",
            str(case_file),
            "--dataset-name",
            "reactor-regression",
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "would_add"
    assert report["caseId"] == "case_cli_promoted"
    assert report["dryRun"] is True
    assert json.loads(suite_file.read_text(encoding="utf-8")) == original_suite


def test_reactor_agent_eval_apply_requires_source_run_id_when_requested(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    original_suite: dict[str, object] = {"cases": [], "runs": []}
    suite_file.write_text(json.dumps(original_suite) + "\n", encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_without_source",
                "name": "Missing source",
                "userInput": "Check a failure safely",
                "expectedAnswerContains": ["safe"],
                "enabled": True,
                "minScore": 1.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    uv = require_uv()

    result = subprocess.run(  # noqa: S603
        [
            uv,
            "run",
            "reactor-agent-eval-apply",
            "--suite-file",
            str(suite_file),
            "--case-file",
            str(case_file),
            "--dataset-name",
            "reactor-regression",
            "--require-source-run-id",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "sourceRunId is required for promoted eval cases" in result.stderr
    assert json.loads(suite_file.read_text(encoding="utf-8")) == original_suite


def test_reactor_agent_eval_apply_requires_run_file_when_requested(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    original_suite: dict[str, object] = {"cases": [], "runs": []}
    suite_file.write_text(json.dumps(original_suite) + "\n", encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_cli_promoted",
                "name": "CLI promoted case",
                "userInput": "Check the promoted failure safely",
                "expectedAnswerContains": ["promoted failure"],
                "enabled": True,
                "minScore": 1.0,
                "sourceRunId": "run_cli_promoted",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    uv = require_uv()

    result = subprocess.run(  # noqa: S603
        [
            uv,
            "run",
            "reactor-agent-eval-apply",
            "--suite-file",
            str(suite_file),
            "--case-file",
            str(case_file),
            "--dataset-name",
            "reactor-regression",
            "--require-run-file",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "run-file is required when applying promoted eval cases" in result.stderr
    assert json.loads(suite_file.read_text(encoding="utf-8")) == original_suite


def test_reactor_agent_eval_apply_entrypoint_writes_report_file(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_cli_promoted",
                "name": "CLI promoted case",
                "userInput": "Check the promoted failure safely",
                "expectedAnswerContains": ["promoted failure"],
                "enabled": True,
                "minScore": 1.0,
                "sourceRunId": "run_cli_promoted",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    report_file = tmp_path / "reports" / "eval-apply.json"
    uv = require_uv()

    result = subprocess.run(  # noqa: S603
        [
            uv,
            "run",
            "reactor-agent-eval-apply",
            "--suite-file",
            str(suite_file),
            "--case-file",
            str(case_file),
            "--dataset-name",
            "reactor-regression",
            "--dry-run",
            "--report-file",
            str(report_file),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout_report = json.loads(result.stdout)
    file_report = json.loads(report_file.read_text(encoding="utf-8"))
    assert stdout_report == file_report
    assert file_report["status"] == "would_add"
    assert file_report["dryRun"] is True


def test_reactor_agent_eval_apply_report_exposes_promotion_coverage(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_cli_promoted",
                "name": "CLI promoted case",
                "userInput": "Check the promoted failure safely",
                "expectedAnswerContains": ["promoted failure"],
                "enabled": True,
                "minScore": 1.0,
                "sourceRunId": "run_cli_promoted",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_file = tmp_path / "promoted-run.json"
    run_file.write_text(
        json.dumps(
            {
                "runId": "run_cli_promoted",
                "evalCaseId": "case_cli_promoted",
                "userInput": "Check the promoted failure safely",
                "agentType": "standard",
                "model": "test-model",
                "finalAnswer": "The promoted failure was handled safely.",
                "toolCalls": [],
                "toolExposure": {"count": 0, "names": []},
                "retrievedChunks": [],
                "errors": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    uv = require_uv()

    result = subprocess.run(  # noqa: S603
        [
            uv,
            "run",
            "reactor-agent-eval-apply",
            "--suite-file",
            str(suite_file),
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--dataset-name",
            "reactor-regression",
            "--dry-run",
            "--require-source-run-id",
            "--require-run-file",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["promotionCoverage"] == {
        "sourceRunIdPresent": True,
        "runFixturePresent": True,
        "runFixtureMatchedCase": True,
        "runContextDiagnosticsPresent": False,
        "requiredSourceRunId": True,
        "requiredRunFile": True,
        "requiredContextDiagnostics": False,
    }


def test_reactor_agent_eval_apply_table_exposes_promotion_coverage(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    case_file.write_text(
        json.dumps(
            {
                "id": "case_cli_promoted",
                "name": "CLI promoted case",
                "userInput": "Check the promoted failure safely",
                "expectedAnswerContains": ["promoted failure"],
                "enabled": True,
                "minScore": 1.0,
                "sourceRunId": "run_cli_promoted",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_file = tmp_path / "promoted-run.json"
    run_file.write_text(
        json.dumps(
            {
                "runId": "run_cli_promoted",
                "evalCaseId": "case_cli_promoted",
                "userInput": "Check the promoted failure safely",
                "agentType": "standard",
                "model": "test-model",
                "finalAnswer": "The promoted failure was handled safely.",
                "toolCalls": [],
                "toolExposure": {"count": 0, "names": []},
                "retrievedChunks": [],
                "errors": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    uv = require_uv()

    result = subprocess.run(  # noqa: S603
        [
            uv,
            "run",
            "reactor-agent-eval-apply",
            "--suite-file",
            str(suite_file),
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--dataset-name",
            "reactor-regression",
            "--require-source-run-id",
            "--require-run-file",
            "--output",
            "table",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    rows = dict(line.split(maxsplit=1) for line in result.stdout.splitlines()[1:])
    assert rows["coverageSourceRunId"] == "true"
    assert rows["coverageRunFixture"] == "true"
    assert rows["coverageRunMatchedCase"] == "true"
    assert rows["coverageRunContextDiagnostics"] == "false"
    assert rows["coverageRequiredSource"] == "true"
    assert rows["coverageRequiredRunFile"] == "true"


def test_reactor_langsmith_eval_sync_dry_run_rejects_secret_shaped_values(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "secret-suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case-secret",
                        "name": "Secret fixture",
                        "userInput": "Investigate password=sk-live-1234567890abcdef",
                    }
                ],
                "runs": [],
            }
        ),
        encoding="utf-8",
    )
    uv = require_uv()

    result = subprocess.run(  # noqa: S603
        [
            uv,
            "run",
            "reactor-langsmith-eval-sync",
            "--suite-file",
            str(suite_file),
            "--dataset-name",
            "reactor-regression",
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "case-secret" in result.stderr


def test_reactor_release_readiness_evidence_entrypoint_aggregates_reports(tmp_path: Path) -> None:
    gate_report = tmp_path / "hardening-report.json"
    gate_report.write_text(
        json.dumps(
            {
                "ok": True,
                "status": "passed",
                "scope": "agent_release_gate",
                "evidence": {
                    "artifact": "reports/hardening-suite.json",
                    "owner": "reactor.evals",
                    "mode": "local_agent_hardening_release_gate",
                    "mcpPreflight": mcp_preflight_evidence(),
                    "slackMcpSurfacePolicy": slack_mcp_surface_policy_evidence(),
                    "memoryMaintenanceLifecycle": memory_maintenance_lifecycle_evidence(),
                    "ragIngestionLifecycle": rag_ingestion_lifecycle_evidence(),
                    "artifactLifecycle": artifact_lifecycle_evidence(),
                    "promptReleaseLifecycle": prompt_release_lifecycle_evidence(),
                    "approvalLifecycle": approval_lifecycle_evidence(),
                    "providerFallbackPolicy": provider_fallback_policy_evidence(),
                    "langgraphFaultTolerance": langgraph_fault_tolerance_evidence(),
                    "checkpointRetentionPolicy": checkpoint_retention_policy_evidence(),
                    "streamingEventContract": streaming_event_contract_evidence(),
                    "toolProfileBudget": tool_profile_budget_evidence(),
                    "graphTopology": graph_topology_evidence(),
                    "contextManifest": context_manifest_evidence(),
                    "contextManifestDiagnostics": context_manifest_diagnostics_evidence(),
                    "langchainMiddlewarePolicy": langchain_middleware_policy_evidence(),
                    "langchainMiddlewareChain": langchain_middleware_chain_evidence(),
                    "langchainSerializationBoundary": langchain_serialization_boundary_evidence(),
                    "contextManagementLifecycle": context_management_lifecycle_evidence(),
                    "usageCostLifecycle": usage_cost_lifecycle_evidence(),
                    "checkpointProvenance": checkpoint_provenance_evidence(),
                    "structuredOutput": structured_output_evidence(),
                    "researchAnswerContract": research_answer_contract_evidence(),
                    "toolInvocationLifecycle": tool_invocation_lifecycle_evidence(),
                    "durableRunQueue": durable_run_queue_evidence(),
                    "outboxInboxLifecycle": outbox_inbox_lifecycle_evidence(),
                    "redisCoordination": redis_coordination_evidence(),
                },
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "release-readiness.json"
    uv = require_uv()

    result = subprocess.run(  # noqa: S603
        [
            uv,
            "run",
            "reactor-release-readiness-evidence",
            "--report",
            f"hardening_suite={gate_report}",
            "--output",
            str(output),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["status"] == "passed"
    assert payload["scope"] == "release_readiness"
    assert payload["summary"] == {"total": 1, "passed": 1, "failed": 0, "skipped": 0}


def require_uv() -> str:
    uv = shutil.which("uv")
    if uv is None:
        raise AssertionError("uv executable is required for packaged CLI entrypoint tests")
    return uv
