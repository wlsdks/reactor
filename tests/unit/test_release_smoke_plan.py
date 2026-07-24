from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

from pytest import CaptureFixture, MonkeyPatch, raises

from reactor.evals.hardening_suite import memory_maintenance_lifecycle_evidence
from reactor.evals.langsmith_dataset import (
    build_langsmith_eval_sync_dry_run_report,
    deterministic_langsmith_example_id,
)
from reactor.memory.lifecycle_actions import MEMORY_LIFECYCLE_GATE_ACTION
from reactor.rag.ingestion_candidate_actions import rag_candidate_review_action
from reactor.release.smoke_plan import (
    CommandResult,
    build_preflight_env_template,
    build_release_smoke_plan,
    extra_readiness_reports,
    main,
    preflight_readiness_report,
    read_env_file,
    release_smoke_preflight_failure_summary,
    report_item_feedback_details,
    run_release_smoke_plan,
    run_release_smoke_preflight,
)

READINESS_REPORT = {
    "local_automation_ready": True,
    "release_ready": False,
    "release_evidence_requirements": [
        {
            "code": "live_provider_runtime_smoke",
            "description": "Live LangChain/LangGraph provider runtime smoke.",
            "evidence_schema": {
                "status": "passed",
                "scope": "live",
                "evidence_uri": "reports/live-provider-runtime-smoke.json",
                "verified_at": "ISO-8601 timestamp",
            },
            "suggested_command": (
                "uv run reactor-live-provider-smoke "
                "--output reports/live-provider-runtime-smoke.json"
            ),
        },
        {
            "code": "live_provider_runtime_local_contract",
            "description": "Local LangChain/LangGraph provider runtime contract.",
            "evidence_schema": {
                "status": "passed",
                "scope": "live",
                "evidence_uri": "reports/live-provider-runtime-smoke.json",
                "verified_at": "ISO-8601 timestamp",
            },
            "suggested_command": (
                "uv run pytest tests/unit/test_langchain_agent.py tests/unit/test_run_service.py "
                "# plus reactor-live-provider-smoke"
            ),
        },
        {
            "code": "full_backup_db_dress_rehearsal",
            "description": "Full backup database migration dress rehearsal.",
            "evidence_schema": {
                "status": "passed",
                "scope": "dress_rehearsal",
                "evidence_uri": "reports/full-backup-db-dress-rehearsal.json",
                "verified_at": "ISO-8601 timestamp",
            },
            "suggested_command": (
                "uv run reactor-migration-dress-rehearsal --help "
                "# then run against the full backup source/target files"
            ),
        },
    ],
}


def api_smoke_passed_report() -> dict[str, object]:
    return {
        "ok": True,
        "status": "passed",
        "scope": "dress_rehearsal",
        "evidence": {
            "artifact": "reports/full-backup-db-api-dress-rehearsal.json",
            "owner": "reactor.release",
            "mode": "dress_api_smoke",
            "apiBoundary": {
                "status": "verified",
                "framework": "FastAPI",
                "schema": "OpenAPI",
                "validation": "Pydantic",
                "openapiPath": "/openapi.json",
                "openapiVersion": "3.1.0",
                "routeCount": 2,
                "schemaCount": 6,
                "requiredPaths": ["/api/admin/capabilities", "/api/chat"],
                "nextActionSchemas": [
                    "FeedbackNextAction",
                    "RagIngestionCandidateNextAction",
                    "MemoryNextAction",
                    "RunOperatorNextAction",
                ],
                "nextActionSchemaFields": [
                    "candidateTag",
                    "caseFile",
                    "command",
                    "datasetName",
                    "envFileCommand",
                    "id",
                    "label",
                    "preflightEnvTemplate",
                    "preflightFile",
                    "releaseEvidenceFile",
                    "releaseReadinessFile",
                    "recommendedEnv",
                    "readinessReportArg",
                    "readinessReports",
                    "remediationCommand",
                    "replatformReadinessFile",
                    "reportFile",
                    "requiredEnvAnyOf",
                    "requiredReadinessReports",
                    "runFile",
                    "smokePlanFile",
                    "suiteFile",
                ],
                "runOperatorNextActionSchemaFields": [
                    "approvalId",
                    "checkpointId",
                    "checkpointNs",
                    "command",
                    "id",
                    "label",
                    "sourceRunId",
                    "threadId",
                ],
                "nextActionFieldsNonEmpty": True,
                "requestResponseModels": True,
                "publicMetadataAllowlist": True,
                "chatPolicyBoundary": {
                    "invokeAndStreamSharedRunService": True,
                    "sharedRunServiceComponents": [
                        "tool_provider",
                        "tool_handler",
                        "tool_invocation_store",
                        "builtin_tool_specs",
                    ],
                    "verificationSensors": [
                        "uv run pytest tests/integration/test_chat_api.py -q "
                        "-k 'chat_request_uses_reactor_tool_policy_components or "
                        "chat_stream_uses_reactor_tool_policy_components'"
                    ],
                    "covers": [
                        "chat_invoke_shares_reactor_tool_policy_components",
                        "chat_stream_shares_reactor_tool_policy_components",
                    ],
                },
                "secretFree": True,
            },
        },
    }


def test_report_item_feedback_details_includes_run_operator_action_fields() -> None:
    api_smoke = api_smoke_passed_report()
    evidence = cast(dict[str, object], api_smoke["evidence"])
    item: dict[str, object] = {
        "name": "dress_api_smoke",
        "status": "failed",
        "apiBoundary": evidence["apiBoundary"],
    }

    details = report_item_feedback_details(item)

    assert (
        "apiRunOperatorNextActionFields=approvalId,checkpointId,checkpointNs,command,"
        "id,label,sourceRunId,threadId"
    ) in details


def valid_langsmith_eval_sync_evidence(
    *,
    enabled_cases: int = 4,
    case_ids: list[str] | None = None,
    artifact: str = "reports/langsmith-eval-sync.json",
) -> dict[str, object]:
    dataset_name = "reactor-regression"
    default_case_ids = [
        "tool-exposure-issue-readonly",
        "casual-prompt-exposes-no-tools",
        "rag-grounded-answer-cites-source",
        "rag-poisoning-retrieval-is-labeled",
    ]
    case_ids = case_ids if case_ids is not None else default_case_ids[:enabled_cases]
    return {
        "artifact": artifact,
        "owner": "reactor.evals",
        "mode": "langsmith_dataset_sync",
        "datasetName": dataset_name,
        "dataType": "kv",
        "sourceSuite": "evals/agent-hardening.json",
        "datasetMetadata": {
            "source": "reactor",
            "kind": "agent_eval",
            "dataType": "kv",
            "sourceSuite": "evals/agent-hardening.json",
        },
        "enabledCases": enabled_cases,
        "exampleIds": [
            str(deterministic_langsmith_example_id(dataset_name=dataset_name, case_id=case_id))
            for case_id in case_ids
        ],
        "caseIds": case_ids,
        "metadataCaseIds": case_ids,
        "sourceRunIds": [f"run_{case_id}" for case_id in case_ids],
        "caseSourceRunIds": {case_id: f"run_{case_id}" for case_id in case_ids},
        "splitCounts": {"regression": enabled_cases},
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
        },
        "promotionCoverage": {
            "sourceRunIdPresent": True,
            "runFixturePresent": True,
            "runFixtureMatchedCase": True,
            "runContextDiagnosticsPresent": True,
            "requiredSourceRunId": True,
            "requiredRunFile": True,
            "requiredContextDiagnostics": True,
        },
        "exampleContract": {
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
        },
        "sdkContract": {
            "sdk": "langsmith",
            "client": "langsmith.Client",
            "datasetApi": "create_dataset",
            "exampleApi": "create_examples",
            "lookupApi": "has_dataset",
            "dataType": "kv",
            "maxConcurrency": 1,
            "deterministicExampleIds": True,
            "sourceControlledCases": True,
        },
        "readinessCommand": (
            "uv run reactor-release-smoke-run "
            "--plan reports/release/release-smoke-plan.local.json "
            "--preflight-file reports/release/release-smoke-preflight.local.json "
            "--env-file reports/release/release-smoke-preflight.local.env "
            "--report-file reports/release-smoke-run.json "
            "--evidence-output reports/release-evidence.json "
            "--verified-at $(date -u +%Y-%m-%dT%H:%M:%SZ) "
            "--latest-tag $(git describe --tags --abbrev=0) "
            "--readiness-output reports/release-readiness.json "
            "--required-readiness-report langsmith_eval_sync "
            f"--readiness-report langsmith_eval_sync={artifact}"
        ),
        "requiredReadinessReports": ["langsmith_eval_sync"],
        "readinessReports": {
            "langsmith_eval_sync": artifact,
        },
        "traceGrading": valid_langsmith_trace_grading(case_ids=case_ids),
    }


def valid_langsmith_trace_grading(*, case_ids: list[str]) -> dict[str, object]:
    return {
        "enabledCases": len(case_ids),
        "gradedRuns": len(case_ids),
        "passed": len(case_ids),
        "failed": 0,
        "caseIds": case_ids,
        "grades": [
            {
                "caseId": case_id,
                "runId": f"run-{case_id}",
                "passed": True,
                "score": 1.0,
                "dimensions": [
                    {
                        "name": "safety",
                        "score": 1.0,
                        "evidence": (
                            {
                                "forbiddenUsed": [],
                                "forbiddenExposed": [],
                                "poisonedChunks": 1,
                                "poisoningReasons": [
                                    "prompt_injection",
                                    "system_prompt_exfiltration",
                                ],
                                "poisonedChunkDocuments": ["tenant-rag-poisoning-runbook"],
                            }
                            if case_id == "rag-poisoning-retrieval-is-labeled"
                            else {
                                "forbiddenUsed": [],
                                "forbiddenExposed": [],
                                "poisonedChunks": 0,
                                "poisoningReasons": [],
                                "poisonedChunkDocuments": [],
                            }
                        ),
                    },
                    {"name": "tool_exposure", "score": 1.0, "evidence": {}},
                    {"name": "tool_efficiency", "score": 1.0, "evidence": {}},
                    {
                        "name": "grounding",
                        "score": 1.0,
                        "evidence": (
                            {
                                "retrieved": 1,
                                "cited": 1,
                                "uncited": 0,
                                "citedDocuments": ["tenant-vectorstore-release"],
                            }
                            if case_id == "rag-grounded-answer-cites-source"
                            else {}
                        ),
                    },
                    {"name": "reliability", "score": 1.0, "evidence": {}},
                ],
            }
            for case_id in case_ids
        ],
        "poisoningSafety": {
            "caseId": "rag-poisoning-retrieval-is-labeled",
            "runId": "run-rag-poisoning-retrieval-is-labeled",
            "poisonedChunks": 1,
            "poisoningReasons": ["prompt_injection", "system_prompt_exfiltration"],
            "poisonedChunkDocuments": ["tenant-rag-poisoning-runbook"],
        },
    }


def test_build_release_smoke_plan_separates_live_automated_local_and_manual_work() -> None:
    plan = build_release_smoke_plan(READINESS_REPORT)

    assert plan == {
        "summary": {"total": 3, "automated": 2, "manual": 1},
        "steps": [
            {
                "code": "live_provider_runtime_smoke",
                "description": "Live LangChain/LangGraph provider runtime smoke.",
                "scope": "live",
                "evidence_scope": "live",
                "release_gate_closer": True,
                "evidence_uri": "reports/live-provider-runtime-smoke.json",
                "mode": "automated",
                "command": [
                    "uv",
                    "run",
                    "reactor-live-provider-smoke",
                    "--output",
                    "reports/live-provider-runtime-smoke.json",
                ],
                "required_env": {"variables": ["OPENAI_API_KEY"]},
                "manual_note": "",
            },
            {
                "code": "live_provider_runtime_local_contract",
                "description": "Local LangChain/LangGraph provider runtime contract.",
                "scope": "live",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/live-provider-runtime-smoke.json",
                "mode": "automated",
                "command": [
                    "uv",
                    "run",
                    "pytest",
                    "tests/unit/test_langchain_agent.py",
                    "tests/unit/test_run_service.py",
                ],
                "manual_note": "reactor-live-provider-smoke",
            },
            {
                "code": "full_backup_db_dress_rehearsal",
                "description": "Full backup database migration dress rehearsal.",
                "scope": "dress_rehearsal",
                "evidence_scope": "dress_rehearsal",
                "release_gate_closer": True,
                "evidence_uri": "reports/full-backup-db-dress-rehearsal.json",
                "mode": "manual",
                "command": [
                    "uv",
                    "run",
                    "reactor-migration-dress-rehearsal",
                    "--help",
                ],
                "required_env": {
                    "variables": [
                        "REACTOR_FULL_BACKUP_EXPORTED_NDJSON",
                        "REACTOR_FULL_BACKUP_ROLLBACK_NDJSON",
                        "REACTOR_FULL_BACKUP_RETAINED_TABLE_MANIFEST",
                        "REACTOR_FULL_BACKUP_DRESS_IMPORTED_OUTPUT",
                        "REACTOR_FULL_BACKUP_DRESS_READINESS_OUTPUT",
                        "REACTOR_FULL_BACKUP_DRESS_BATCH_ID",
                    ]
                },
                "manual_note": "then run against the full backup source/target files",
            },
        ],
    }


def test_release_smoke_plan_cli_writes_json(tmp_path: Path) -> None:
    readiness_path = tmp_path / "readiness.json"
    output_path = tmp_path / "smoke-plan.json"
    readiness_path.write_text(json.dumps(READINESS_REPORT), encoding="utf-8")

    exit_code = main(["--readiness", str(readiness_path), "--output", str(output_path)])

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"] == {"total": 3, "automated": 2, "manual": 1}
    assert payload["steps"][0]["release_gate_closer"] is True
    assert payload["steps"][0]["required_env"] == {"variables": ["OPENAI_API_KEY"]}


def test_release_smoke_plan_cli_marks_missing_requirements_blocked(tmp_path: Path) -> None:
    readiness_path = tmp_path / "readiness.json"
    output_path = tmp_path / "smoke-plan.json"
    readiness_path.write_text(
        json.dumps({"ok": True, "status": "passed", "items": []}),
        encoding="utf-8",
    )

    exit_code = main(["--readiness", str(readiness_path), "--output", str(output_path)])

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"] == {"total": 0, "automated": 0, "manual": 0}
    assert payload["status"] == "blocked"
    assert payload["failure"] == "release evidence requirements missing"
    assert payload["remediationCommand"] == (
        "uv run reactor-replatform-readiness --output "
        "reports/release/replatform-readiness.local.json "
        "--allow-deferred-release-gates "
        "&& uv run reactor-release-smoke-plan "
        "--readiness reports/release/replatform-readiness.local.json "
        "--output reports/release/release-smoke-plan.local.json"
    )


def test_release_smoke_plan_preserves_readiness_next_actions_when_blocked() -> None:
    plan = build_release_smoke_plan(
        {
            "status": "blocked",
            "release_ready": False,
            "items": [
                {
                    "name": "langsmith_eval_sync",
                    "status": "skipped",
                    "failure": "dry_run_only",
                    "nextActions": [
                        {
                            "id": "sync-langsmith",
                            "command": (
                                "uv run reactor-langsmith-eval-sync "
                                "--suite-file evals/regression/rag-ingestion-candidate.json "
                                "--dataset-name reactor-rag-ingestion-candidate "
                                "--report-file artifacts/langsmith/"
                                "rag-ingestion-candidate-c1.json"
                            ),
                            "readinessReportArg": (
                                "--readiness-report "
                                "langsmith_eval_sync=artifacts/langsmith/"
                                "rag-ingestion-candidate-c1.json"
                            ),
                            "requiredReadinessReports": ["langsmith_eval_sync"],
                            "readinessReports": {
                                "langsmith_eval_sync": (
                                    "artifacts/langsmith/rag-ingestion-candidate-c1.json"
                                ),
                            },
                        },
                    ],
                },
            ],
        }
    )

    assert plan["status"] == "blocked"
    assert plan["nextActions"] == [
        {
            "sourceReport": "langsmith_eval_sync",
            "id": "sync-langsmith",
            "command": (
                "uv run reactor-langsmith-eval-sync "
                "--suite-file evals/regression/rag-ingestion-candidate.json "
                "--dataset-name reactor-rag-ingestion-candidate "
                "--report-file artifacts/langsmith/rag-ingestion-candidate-c1.json"
            ),
            "readinessReportArg": (
                "--readiness-report "
                "langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate-c1.json"
            ),
            "requiredReadinessReports": ["langsmith_eval_sync"],
            "readinessReports": {
                "langsmith_eval_sync": "artifacts/langsmith/rag-ingestion-candidate-c1.json",
            },
        },
    ]


def test_release_smoke_plan_filters_to_local_contract_scope() -> None:
    plan = build_release_smoke_plan(
        READINESS_REPORT,
        evidence_scopes=("local_contract",),
    )

    assert plan["summary"] == {"total": 1, "automated": 1, "manual": 0}
    assert plan["evidenceScopeFilter"] == ["local_contract"]
    assert plan["excludedSummary"] == {"total": 2, "automated": 1, "manual": 1}
    steps = cast(list[dict[str, object]], plan["steps"])
    assert [step["code"] for step in steps] == ["live_provider_runtime_local_contract"]
    assert steps[0]["evidence_scope"] == "local_contract"


def test_release_smoke_plan_cli_filters_to_local_contract_scope(tmp_path: Path) -> None:
    readiness_path = tmp_path / "readiness.json"
    output_path = tmp_path / "smoke-plan.json"
    readiness_path.write_text(json.dumps(READINESS_REPORT), encoding="utf-8")

    exit_code = main(
        [
            "--readiness",
            str(readiness_path),
            "--output",
            str(output_path),
            "--evidence-scope",
            "local_contract",
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"] == {"total": 1, "automated": 1, "manual": 0}
    assert payload["evidenceScopeFilter"] == ["local_contract"]
    assert [step["code"] for step in payload["steps"]] == ["live_provider_runtime_local_contract"]


def test_release_smoke_preflight_allows_local_contract_scope_without_live_env() -> None:
    plan = build_release_smoke_plan(
        READINESS_REPORT,
        evidence_scopes=("local_contract",),
    )

    preflight = run_release_smoke_preflight(plan, environ={})

    assert preflight["ok"] is True
    assert preflight["summary"] == {"total": 1, "ready": 1, "blocked": 0, "optional_missing": 0}
    steps = cast(list[dict[str, object]], preflight["steps"])
    assert steps[0]["code"] == "live_provider_runtime_local_contract"
    assert steps[0]["status"] == "ready"


def test_release_smoke_plan_reports_empty_scope_filter_without_env_blocker() -> None:
    plan = build_release_smoke_plan(
        {
            "release_ready": False,
            "release_evidence_requirements": [
                {
                    "code": "live_provider_runtime_smoke",
                    "description": "Live provider smoke.",
                    "suggested_command": (
                        "uv run reactor-live-provider-smoke "
                        "--output reports/live-provider-runtime-smoke.json"
                    ),
                    "evidence_schema": {
                        "scope": "live",
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                    },
                }
            ],
        },
        evidence_scopes=("local_contract",),
    )

    assert plan["status"] == "blocked"
    assert plan["failure"] == "release evidence requirements missing for evidence scope"
    assert plan["evidenceScopeFilter"] == ["local_contract"]

    preflight = run_release_smoke_preflight(plan, environ={})

    assert preflight["ok"] is False
    assert preflight["status"] == "blocked"
    assert preflight["failure"] == "release evidence requirements missing for evidence scope"
    assert preflight["summary"] == {"total": 0, "ready": 0, "blocked": 1, "optional_missing": 0}


def test_preflight_readiness_report_preserves_empty_scope_remediation() -> None:
    report: dict[str, object] = {
        "ok": False,
        "status": "blocked",
        "failure": "release evidence requirements missing for evidence scope",
        "summary": {"total": 0, "ready": 0, "blocked": 1, "optional_missing": 0},
        "steps": [],
        "remediationCommand": (
            "uv run reactor-replatform-readiness --output "
            "reports/release/replatform-readiness.local.json "
            "--allow-deferred-release-gates"
        ),
    }

    readiness = preflight_readiness_report(report, "reports/release-smoke-preflight.json")

    assert readiness["status"] == "blocked"
    assert readiness["error"] == "release evidence requirements missing for evidence scope"
    assert readiness["evidence"]["remediationCommand"] == (
        "uv run reactor-replatform-readiness --output "
        "reports/release/replatform-readiness.local.json "
        "--allow-deferred-release-gates"
    )


def test_release_smoke_plan_marks_ready_report_with_no_requirements_satisfied() -> None:
    plan = build_release_smoke_plan(
        {
            "local_automation_ready": True,
            "release_ready": True,
            "release_evidence_requirements": [],
            "satisfied_release_gates": [
                {
                    "code": "live_provider_smoke",
                    "scope": "live",
                    "evidence_uri": "reports/live-provider-smoke.json",
                    "verified_at": "2026-07-03T00:00:00Z",
                }
            ],
        }
    )

    assert plan["summary"] == {"total": 0, "automated": 0, "manual": 0}
    assert plan["status"] == "passed"
    assert plan["reason"] == "release evidence requirements already satisfied"


def test_release_smoke_plan_exposes_required_env_by_gate() -> None:
    plan = build_release_smoke_plan(
        {
            "release_evidence_requirements": [
                {
                    "code": "live_slack_workspace_smoke",
                    "description": "Live Slack workspace command/event smoke.",
                    "evidence_schema": {
                        "scope": "live",
                        "evidence_uri": "reports/live-slack-workspace-smoke.json",
                    },
                    "suggested_command": (
                        "uv run reactor-live-slack-smoke "
                        "--output reports/live-slack-workspace-smoke.json"
                    ),
                },
                {
                    "code": "live_peer_network_interoperability_smoke",
                    "description": "Live A2A peer-network interoperability smoke.",
                    "evidence_schema": {
                        "scope": "live",
                        "evidence_uri": "reports/live-peer-network-interoperability-smoke.json",
                    },
                    "suggested_command": (
                        "uv run reactor-live-a2a-peer-smoke "
                        "--output reports/live-peer-network-interoperability-smoke.json"
                    ),
                },
                {
                    "code": "live_backend_provider_integration",
                    "description": "Live backend/provider observability integration proof.",
                    "evidence_schema": {
                        "scope": "live",
                        "evidence_uri": "reports/live-backend-provider-integration.json",
                    },
                    "suggested_command": (
                        "uv run reactor-live-backend-provider-smoke "
                        "--output reports/live-backend-provider-integration.json"
                    ),
                },
                {
                    "code": "observability_langsmith_local_contract",
                    "description": (
                        "Local LangSmith observability configuration and redaction smoke."
                    ),
                    "evidence_schema": {
                        "scope": "local_contract",
                        "evidence_uri": "reports/observability-smoke.json",
                    },
                    "suggested_command": (
                        "uv run reactor-observability-smoke "
                        "--output reports/observability-smoke.json"
                    ),
                },
            ]
        }
    )

    steps = cast(list[dict[str, object]], plan["steps"])
    assert steps[0]["required_env"] == {
        "variables": ["REACTOR_SLACK_SIGNING_SECRET", "REACTOR_SLACK_BOT_TOKEN"]
    }
    assert steps[1]["required_env"] == {
        "variables": ["REACTOR_A2A_BASE_URL", "REACTOR_A2A_API_KEY"],
    }
    assert steps[2]["required_env"] == {
        "variables": ["OPENAI_API_KEY"],
        "any_of": [["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]],
        "recommended": ["LANGSMITH_ENDPOINT"],
    }
    assert steps[3]["mode"] == "automated"
    assert steps[3]["evidence_scope"] == "local_contract"
    assert steps[3]["release_gate_closer"] is False
    assert steps[3]["required_env"] == {
        "any_of": [["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]],
        "recommended": ["LANGSMITH_ENDPOINT"],
    }


def test_release_smoke_plan_preserves_prior_evidence_revision_status() -> None:
    plan = build_release_smoke_plan(
        {
            "release_evidence_requirements": [
                {
                    "code": "live_provider_runtime_smoke",
                    "description": "Live LangChain/LangGraph provider runtime smoke.",
                    "evidence_status": "passed",
                    "evidence_scope": "live",
                    "evidence_revision_status": "stale",
                    "evidence_git_commit": "old123",
                    "evidence_schema": {
                        "scope": "live",
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                    },
                    "suggested_command": (
                        "uv run reactor-live-provider-smoke "
                        "--output reports/live-provider-runtime-smoke.json"
                    ),
                }
            ]
        }
    )

    steps = cast(list[dict[str, object]], plan["steps"])
    assert steps[0]["prior_evidence"] == {
        "status": "passed",
        "scope": "live",
        "revision_status": "stale",
        "git_commit": "old123",
    }


def test_release_smoke_preflight_preserves_prior_evidence_revision_status() -> None:
    report = run_release_smoke_preflight(
        {
            "steps": [
                {
                    "code": "live_provider_runtime_smoke",
                    "mode": "automated",
                    "evidence_scope": "live",
                    "release_gate_closer": True,
                    "evidence_uri": "reports/live-provider-runtime-smoke.json",
                    "command": ["uv", "run", "reactor-live-provider-smoke"],
                    "required_env": {"variables": ["OPENAI_API_KEY"]},
                    "prior_evidence": {
                        "status": "passed",
                        "scope": "live",
                        "revision_status": "missing",
                    },
                }
            ]
        },
        environ={},
    )

    steps = cast(list[dict[str, object]], report["steps"])
    assert steps[0]["prior_evidence"] == {
        "status": "passed",
        "scope": "live",
        "revision_status": "missing",
    }


def test_release_smoke_run_cli_can_write_release_evidence(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    evidence_path = tmp_path / "release-evidence.json"
    readiness_path = tmp_path / "release-readiness.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": [
                            "uv",
                            "run",
                            "reactor-live-provider-smoke",
                            "--output",
                            str(tmp_path / "provider.json"),
                        ],
                    },
                    {
                        "code": "local_contract",
                        "mode": "automated",
                        "evidence_scope": "local_contract",
                        "release_gate_closer": False,
                        "evidence_uri": "reports/local.json",
                        "command": ["uv", "run", "pytest", "tests/unit/test_langchain_agent.py"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout=command[2], stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)
    monkeypatch.setattr("reactor.release.smoke_plan.current_git_commit", lambda: "abc123")

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--verified-at",
            "2026-06-28T00:00:00Z",
            "--evidence-output",
            str(evidence_path),
            "--readiness-output",
            str(readiness_path),
            "--required-readiness-report",
            "smoke_run",
            "--required-readiness-report",
            "release_evidence",
        ]
    )

    assert exit_code == 0
    assert json.loads(evidence_path.read_text(encoding="utf-8")) == {
        "live_provider_runtime_smoke": {
            "status": "passed",
            "scope": "live",
            "evidence_uri": "reports/live-provider-runtime-smoke.json",
            "verified_at": "2026-06-28T00:00:00Z",
            "git_commit": "abc123",
        }
    }
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["ok"] is True
    assert readiness["status"] == "passed"
    assert readiness["scope"] == "release_readiness"
    assert readiness["summary"] == {"total": 2, "passed": 2, "failed": 0, "skipped": 0}
    assert [item["name"] for item in readiness["items"]] == [
        "smoke_run",
        "release_evidence",
    ]
    release_evidence_item = readiness["items"][1]
    assert release_evidence_item["releaseEvidence"] == {
        "gateCount": 1,
        "gateCodes": ["live_provider_runtime_smoke"],
        "scopes": {"live": 1},
        "statusCounts": {"passed": 1},
    }
    assert readiness["requiredReports"] == ["smoke_run", "release_evidence"]
    assert readiness["missingReports"] == []


def test_release_smoke_run_cli_merges_existing_release_evidence(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    existing_path = tmp_path / "existing-evidence.json"
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    evidence_path = tmp_path / "release-evidence.json"
    existing_path.write_text(
        json.dumps(
            {
                "live_slack_workspace_smoke": {
                    "status": "passed",
                    "scope": "live",
                    "evidence_uri": "reports/live-slack-workspace-smoke.json",
                    "verified_at": "2026-06-27T00:00:00Z",
                }
            }
        ),
        encoding="utf-8",
    )
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout=command[2], stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)
    monkeypatch.setattr("reactor.release.smoke_plan.current_git_commit", lambda: "abc123")

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--evidence-input",
            str(existing_path),
            "--verified-at",
            "2026-06-28T00:00:00Z",
            "--evidence-output",
            str(evidence_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(evidence_path.read_text(encoding="utf-8")) == {
        "live_provider_runtime_smoke": {
            "status": "passed",
            "scope": "live",
            "evidence_uri": "reports/live-provider-runtime-smoke.json",
            "verified_at": "2026-06-28T00:00:00Z",
            "git_commit": "abc123",
        },
        "live_slack_workspace_smoke": {
            "status": "passed",
            "scope": "live",
            "evidence_uri": "reports/live-slack-workspace-smoke.json",
            "verified_at": "2026-06-27T00:00:00Z",
        },
    }


def test_release_smoke_run_readiness_output_blocks_without_release_evidence(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    evidence_path = tmp_path / "release-evidence.json"
    readiness_path = tmp_path / "release-readiness.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "local_contract",
                        "mode": "automated",
                        "evidence_scope": "local_contract",
                        "release_gate_closer": False,
                        "evidence_uri": "reports/local.json",
                        "command": ["uv", "run", "pytest", "tests/unit/test_langchain_agent.py"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--verified-at",
            "2026-07-06T00:00:00Z",
            "--evidence-output",
            str(evidence_path),
            "--readiness-output",
            str(readiness_path),
        ]
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "release_readiness status=blocked" in stderr
    assert (
        "release_evidence: status=skipped failure=release evidence missing "
        "remediationCommand='uv run reactor-release-smoke-run "
        f"--plan {plan_path} "
        f"--report-file {report_path} --verified-at <ISO-8601> "
        f"--evidence-output {evidence_path}' "
        "readinessReportArg='--readiness-report "
        f"release_evidence={evidence_path}'"
    ) in stderr
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["ok"] is False
    assert readiness["status"] == "blocked"
    assert readiness["summary"] == {"total": 2, "passed": 1, "failed": 0, "skipped": 1}
    assert readiness["requiredReports"] == ["smoke_run", "release_evidence"]
    assert readiness["missingReports"] == []
    assert readiness["items"][1]["name"] == "release_evidence"
    assert readiness["items"][1]["status"] == "skipped"
    assert readiness["items"][1]["failure"] == "release evidence missing"
    assert readiness["items"][1]["remediationCommand"] == (
        f"uv run reactor-release-smoke-run --plan {plan_path} "
        f"--report-file {report_path} --verified-at <ISO-8601> "
        f"--evidence-output {evidence_path}"
    )
    assert readiness["items"][1]["readinessReportArg"] == (
        f"--readiness-report release_evidence={evidence_path}"
    )


def test_release_smoke_run_readiness_preserves_skipped_smoke_run_status(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    readiness_path = tmp_path / "release-readiness.json"
    plan_path.write_text(json.dumps({"steps": []}), encoding="utf-8")

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--readiness-output",
            str(readiness_path),
            "--skip-release-evidence-readiness",
        ]
    )

    assert exit_code == 1
    assert "smoke_run: status=skipped" in capsys.readouterr().err
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["ok"] is False
    assert readiness["status"] == "blocked"
    assert readiness["summary"] == {"total": 1, "passed": 0, "failed": 0, "skipped": 1}
    assert readiness["requiredReports"] == ["smoke_run"]
    assert readiness["items"][0]["name"] == "smoke_run"
    assert readiness["items"][0]["status"] == "skipped"
    assert readiness["items"][0]["failure"] == "no automated release smoke steps configured"


def test_release_smoke_run_readiness_preserves_blocked_plan_next_actions(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    readiness_path = tmp_path / "release-readiness.json"
    plan_path.write_text(
        json.dumps(
            {
                "status": "blocked",
                "failure": "release evidence requirements missing",
                "remediationCommand": (
                    "uv run reactor-replatform-readiness --output "
                    "reports/release/replatform-readiness.local.json"
                ),
                "nextActions": [
                    {
                        "sourceReport": "langsmith_eval_sync",
                        "id": "sync-langsmith",
                        "command": (
                            "uv run reactor-langsmith-eval-sync "
                            "--suite-file evals/regression/rag-ingestion-candidate.json "
                            "--dataset-name reactor-rag-ingestion-candidate "
                            "--report-file artifacts/langsmith/rag-ingestion-candidate-c1.json"
                        ),
                        "readinessReportArg": (
                            "--readiness-report "
                            "langsmith_eval_sync=artifacts/langsmith/"
                            "rag-ingestion-candidate-c1.json"
                        ),
                        "releaseReadinessCommand": (
                            "uv run reactor-release-smoke-run "
                            "--readiness-output reports/release-readiness.json "
                            "--required-readiness-report langsmith_eval_sync "
                            "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                            "rag-ingestion-candidate-c1.json"
                        ),
                        "requiredReadinessReports": ["langsmith_eval_sync"],
                        "readinessReports": {
                            "langsmith_eval_sync": (
                                "artifacts/langsmith/rag-ingestion-candidate-c1.json"
                            ),
                        },
                    },
                ],
                "steps": [],
                "summary": {"total": 0, "automated": 0, "manual": 0},
            }
        ),
        encoding="utf-8",
    )

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--readiness-output",
            str(readiness_path),
            "--skip-release-evidence-readiness",
        ]
    )

    assert exit_code == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["nextActions"][0]["id"] == "sync-langsmith"
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    smoke_run = readiness["items"][0]
    assert smoke_run["name"] == "smoke_run"
    assert smoke_run["status"] == "blocked"
    assert smoke_run["nextActions"][0]["id"] == "sync-langsmith"
    assert smoke_run["nextActions"][0]["readinessReportArg"] == (
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate-c1.json"
    )
    assert smoke_run["nextActions"][0]["releaseReadinessCommand"] == (
        "uv run reactor-release-smoke-run "
        "--readiness-output reports/release-readiness.json "
        "--required-readiness-report langsmith_eval_sync "
        "--readiness-report "
        "langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate-c1.json"
    )
    stderr = capsys.readouterr().err
    assert "nextActions=sync-langsmith" in stderr
    assert "nextAction.sync-langsmith.sourceReport='langsmith_eval_sync'" in stderr
    assert (
        "nextAction.sync-langsmith.readinessReportArg='--readiness-report "
        "langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate-c1.json'"
    ) in stderr
    assert (
        "nextAction.sync-langsmith.releaseReadinessCommand='uv run "
        "reactor-release-smoke-run --readiness-output reports/release-readiness.json "
        "--required-readiness-report langsmith_eval_sync --readiness-report "
        "langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate-c1.json'"
    ) in stderr


def test_release_smoke_run_can_skip_release_evidence_readiness_for_local_handoffs(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    readiness_path = tmp_path / "release-readiness.json"
    operator_check_path = tmp_path / "operator-check.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "operator_local_contract",
                        "mode": "automated",
                        "evidence_scope": "local_contract",
                        "release_gate_closer": False,
                        "evidence_uri": str(operator_check_path),
                        "command": ["uv", "run", "pytest", "tests/unit/test_release_smoke_plan.py"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    operator_check_path.write_text(
        json.dumps(
            {
                "ok": True,
                "status": "passed",
                "scope": "operator_check",
                "evidence": {
                    "artifact": str(operator_check_path),
                    "owner": "reactor.evals",
                    "mode": "operator_check",
                },
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--readiness-output",
            str(readiness_path),
            "--skip-release-evidence-readiness",
            "--required-readiness-report",
            "operator_check",
            "--readiness-report",
            f"operator_check={operator_check_path}",
        ]
    )

    assert exit_code == 0
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["ok"] is True
    assert readiness["requiredReports"] == ["smoke_run", "operator_check"]
    assert readiness["missingReports"] == []
    assert [item["name"] for item in readiness["items"]] == ["smoke_run", "operator_check"]


def test_release_smoke_run_readiness_output_defaults_required_reports(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    evidence_path = tmp_path / "release-evidence.json"
    readiness_path = tmp_path / "release-readiness.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--verified-at",
            "2026-06-28T00:00:00Z",
            "--evidence-output",
            str(evidence_path),
            "--readiness-output",
            str(readiness_path),
        ]
    )

    assert exit_code == 0
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["ok"] is True
    assert readiness["status"] == "passed"
    assert readiness["requiredReports"] == ["smoke_run", "release_evidence"]
    assert readiness["missingReports"] == []


def test_release_smoke_run_readiness_output_selects_next_tag_from_latest_tag(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    evidence_path = tmp_path / "release-evidence.json"
    readiness_path = tmp_path / "release-readiness.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--verified-at",
            "2026-07-05T00:00:00Z",
            "--evidence-output",
            str(evidence_path),
            "--readiness-output",
            str(readiness_path),
            "--latest-tag",
            "v1.0.219",
        ]
    )

    assert exit_code == 0
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    recommendation = readiness["tagRecommendation"]
    assert recommendation["latestTag"] == "v1.0.219"
    assert recommendation["recommendedTag"] == "v1.0.220"
    assert recommendation["tagSelectionReason"] == "next patch tag after latestTag"


def test_release_smoke_run_readiness_output_includes_extra_readiness_reports(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    evidence_path = tmp_path / "release-evidence.json"
    readiness_path = tmp_path / "release-readiness.json"
    langsmith_path = tmp_path / "langsmith-eval-sync.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    langsmith_evidence = valid_langsmith_eval_sync_evidence(
        enabled_cases=1,
        case_ids=["rag-poisoning-retrieval-is-labeled"],
        artifact=str(langsmith_path),
    )
    langsmith_evidence["feedbackPromotion"] = {
        "caseIds": ["rag-poisoning-retrieval-is-labeled"],
        "feedbackIds": ["fb_rag_1"],
        "feedbackReviewIds": ["fb_rag_1"],
        "feedbackRatingCounts": {"thumbs_down": 1},
        "feedbackSourceCounts": {"slack_button": 1},
        "workflowTagCounts": {"documents-ask": 1, "grounding": 1, "rag": 1},
        "reviewAction": "reactor-admin feedback --feedback-id fb_rag_1 --output table",
        "bulkReviewAction": (
            "reactor-admin feedback-bulk-review --case-id "
            "rag-poisoning-retrieval-is-labeled --status done "
            "--tag promoted --tag langsmith "
            "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
            "--output table"
        ),
    }
    langsmith_path.write_text(
        json.dumps(
            {
                "ok": True,
                "status": "passed",
                "scope": "langsmith_eval_dataset_sync",
                "evidence": langsmith_evidence,
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--verified-at",
            "2026-06-28T00:00:00Z",
            "--evidence-output",
            str(evidence_path),
            "--readiness-output",
            str(readiness_path),
            "--required-readiness-report",
            "smoke_run",
            "--required-readiness-report",
            "release_evidence",
            "--readiness-report",
            f"langsmith_eval_sync={langsmith_path}",
        ]
    )

    assert exit_code == 0
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["ok"] is True
    assert readiness["requiredReports"] == [
        "smoke_run",
        "release_evidence",
        "langsmith_eval_sync",
    ]
    assert readiness["missingReports"] == []
    items = {item["name"]: item for item in readiness["items"]}
    langsmith_item = items["langsmith_eval_sync"]
    assert langsmith_item["caseIds"] == ["rag-poisoning-retrieval-is-labeled"]
    trace_grading = cast(dict[str, object], langsmith_item["traceGrading"])
    grades = cast(list[dict[str, object]], trace_grading["grades"])
    poisoning_grade = next(
        grade for grade in grades if grade["caseId"] == "rag-poisoning-retrieval-is-labeled"
    )
    dimensions = cast(list[dict[str, object]], poisoning_grade["dimensions"])
    safety = next(dimension for dimension in dimensions if dimension["name"] == "safety")
    assert safety["evidence"] == {
        "forbiddenUsed": [],
        "forbiddenExposed": [],
        "poisonedChunks": 1,
        "poisoningReasons": ["prompt_injection", "system_prompt_exfiltration"],
        "poisonedChunkDocuments": ["tenant-rag-poisoning-runbook"],
    }
    assert items["langsmith_eval_sync"]["feedbackPromotion"] == {
        "caseIds": ["rag-poisoning-retrieval-is-labeled"],
        "feedbackIds": ["fb_rag_1"],
        "feedbackReviewIds": ["fb_rag_1"],
        "feedbackRatingCounts": {"thumbs_down": 1},
        "feedbackSourceCounts": {"slack_button": 1},
        "workflowTagCounts": {"documents-ask": 1, "grounding": 1, "rag": 1},
        "reviewAction": "reactor-admin feedback --feedback-id fb_rag_1 --output table",
        "bulkReviewAction": (
            "reactor-admin feedback-bulk-review --case-id "
            "rag-poisoning-retrieval-is-labeled --status done "
            "--tag promoted --tag langsmith "
            "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
            "--output table"
        ),
    }


def test_release_smoke_run_main_creates_output_parent_directories(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "reports" / "release" / "smoke-run.json"
    evidence_path = tmp_path / "reports" / "release" / "evidence.json"
    readiness_path = tmp_path / "reports" / "release" / "readiness.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)
    monkeypatch.setattr("reactor.release.smoke_plan.current_git_commit", lambda: "abc123")

    from reactor.release.smoke_plan import run_main

    assert (
        run_main(
            [
                "--plan",
                str(plan_path),
                "--report-file",
                str(report_path),
                "--verified-at",
                "2026-06-28T00:00:00Z",
                "--evidence-output",
                str(evidence_path),
                "--readiness-output",
                str(readiness_path),
                "--skip-release-evidence-readiness",
            ]
        )
        == 0
    )

    assert json.loads(report_path.read_text(encoding="utf-8"))["ok"] is True
    assert json.loads(evidence_path.read_text(encoding="utf-8")) == {
        "live_provider_runtime_smoke": {
            "status": "passed",
            "scope": "live",
            "evidence_uri": "reports/live-provider-runtime-smoke.json",
            "verified_at": "2026-06-28T00:00:00Z",
            "git_commit": "abc123",
        }
    }
    assert json.loads(readiness_path.read_text(encoding="utf-8"))["ok"] is True


def test_extra_readiness_reports_rejects_duplicate_names(tmp_path: Path) -> None:
    report_a = tmp_path / "langsmith-a.json"
    report_b = tmp_path / "langsmith-b.json"
    for path in (report_a, report_b):
        path.write_text(
            json.dumps({"ok": True, "status": "passed", "scope": "langsmith_eval_dataset_sync"}),
            encoding="utf-8",
        )

    with raises(ValueError, match="duplicate --readiness-report name: langsmith_eval_sync"):
        extra_readiness_reports(
            [
                f"langsmith_eval_sync={report_a}",
                f"langsmith_eval_sync={report_b}",
            ]
        )


def test_release_smoke_run_readiness_output_handles_missing_extra_report(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    evidence_path = tmp_path / "release-evidence.json"
    readiness_path = tmp_path / "release-readiness.json"
    missing_langsmith_path = tmp_path / "missing-langsmith.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--verified-at",
            "2026-07-05T00:00:00Z",
            "--evidence-output",
            str(evidence_path),
            "--readiness-output",
            str(readiness_path),
            "--readiness-report",
            f"langsmith_eval_sync={missing_langsmith_path}",
        ]
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "Traceback" not in stderr
    assert "missingReports=langsmith_eval_sync" in stderr
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["ok"] is False
    assert readiness["status"] == "blocked"
    assert readiness["requiredReports"] == [
        "smoke_run",
        "release_evidence",
        "langsmith_eval_sync",
    ]
    assert readiness["missingReports"] == ["langsmith_eval_sync"]
    items = {item["name"]: item for item in readiness["items"]}
    assert items["smoke_run"]["status"] == "passed"
    assert items["release_evidence"]["status"] == "passed"
    assert items["langsmith_eval_sync"]["ok"] is False
    assert items["langsmith_eval_sync"]["status"] == "skipped"
    assert items["langsmith_eval_sync"]["failure"] == "required report missing"
    assert items["langsmith_eval_sync"]["remediationCommand"] == (
        "uv run reactor-langsmith-eval-sync "
        "--suite-file tests/fixtures/agent-eval/regression-suite.json "
        "--dataset-name reactor-regression --report-file reports/langsmith-eval-sync.json "
        "--required-readiness-report langsmith_eval_sync "
        "--readiness-report langsmith_eval_sync=reports/langsmith-eval-sync.json"
    )
    assert items["langsmith_eval_sync"]["readinessReportArg"] == (
        "--readiness-report langsmith_eval_sync=reports/langsmith-eval-sync.json"
    )


def test_release_smoke_run_readiness_output_handles_malformed_extra_report(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    evidence_path = tmp_path / "release-evidence.json"
    readiness_path = tmp_path / "release-readiness.json"
    malformed_langsmith_path = tmp_path / "malformed-langsmith.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    malformed_langsmith_path.write_text("{", encoding="utf-8")

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--verified-at",
            "2026-07-05T00:00:00Z",
            "--evidence-output",
            str(evidence_path),
            "--readiness-output",
            str(readiness_path),
            "--readiness-report",
            f"langsmith_eval_sync={malformed_langsmith_path}",
        ]
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "Traceback" not in stderr
    assert "failure=readiness report unreadable" in stderr
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["ok"] is False
    assert readiness["status"] == "failed"
    assert readiness["requiredReports"] == [
        "smoke_run",
        "release_evidence",
        "langsmith_eval_sync",
    ]
    assert readiness["missingReports"] == []
    items = {item["name"]: item for item in readiness["items"]}
    assert items["langsmith_eval_sync"]["ok"] is False
    assert items["langsmith_eval_sync"]["status"] == "failed"
    assert str(items["langsmith_eval_sync"]["failure"]).startswith("readiness report unreadable:")
    assert items["langsmith_eval_sync"]["artifact"] == str(malformed_langsmith_path)


def test_release_smoke_run_readiness_output_preserves_rag_candidate_dry_run_handoff(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    evidence_path = tmp_path / "release-evidence.json"
    readiness_path = tmp_path / "release-readiness.json"
    langsmith_path = tmp_path / "rag-ingestion-candidate.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    langsmith_path.write_text(
        json.dumps(
            build_langsmith_eval_sync_dry_run_report(
                suite_file=Path("evals/regression/rag-ingestion-candidate.json"),
                dataset_name="reactor-rag-ingestion-candidate",
                report_file=langsmith_path,
            )
        ),
        encoding="utf-8",
    )

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--verified-at",
            "2026-07-03T00:00:00Z",
            "--evidence-output",
            str(evidence_path),
            "--readiness-output",
            str(readiness_path),
            "--required-readiness-report",
            "langsmith_eval_sync",
            "--readiness-report",
            f"langsmith_eval_sync={langsmith_path}",
        ]
    )

    assert exit_code == 1
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["ok"] is False
    assert readiness["status"] == "blocked"
    assert readiness["requiredReports"] == [
        "smoke_run",
        "release_evidence",
        "langsmith_eval_sync",
        "hardening_suite",
    ]
    assert readiness["missingReports"] == ["hardening_suite"]
    items = {item["name"]: item for item in readiness["items"]}
    assert items["hardening_suite"]["status"] == "skipped"
    assert items["hardening_suite"]["failure"] == "required report missing"
    langsmith_item = items["langsmith_eval_sync"]
    assert langsmith_item["status"] == "skipped"
    assert langsmith_item["datasetName"] == "reactor-rag-ingestion-candidate"
    assert langsmith_item["caseIds"] == ["case_rag_candidate_grounded_citation"]
    assert langsmith_item["sourceRunIds"] == ["run_rag_candidate_grounded_citation"]
    assert langsmith_item["caseSourceRunIds"] == {
        "case_rag_candidate_grounded_citation": "run_rag_candidate_grounded_citation"
    }
    assert langsmith_item["releaseGate"]["reason"] == "dry_run_only"
    assert langsmith_item["feedbackReviewQueue"] == {
        "caseIds": ["case_rag_candidate_grounded_citation"],
        "candidateTag": "rag-candidate:grounded_citation",
        "feedbackRatingCounts": {"thumbs_down": 1},
        "feedbackSourceCounts": {"slack_button": 1},
        "workflowTagCounts": {
            "collection:rag-ingestion-candidate": 1,
            "documents-ask": 1,
            "expected-citation:candidate-runbook.md": 1,
            "grounding": 1,
            "rag": 1,
            "rag-candidate:grounded_citation": 1,
        },
        "expectedCitationCounts": {"candidate-runbook.md": 1},
        "reviewAction": (
            "reactor-admin feedback --rating thumbs_down "
            "--source slack_button "
            "--review-status inbox "
            "--case-id case_rag_candidate_grounded_citation "
            "--tag collection:rag-ingestion-candidate "
            "--tag rag-candidate:grounded_citation --limit 10 --output table"
        ),
        "exportAction": (
            "reactor-admin feedback-export --rating thumbs_down "
            "--source slack_button "
            "--review-status inbox "
            "--case-id case_rag_candidate_grounded_citation "
            "--tag collection:rag-ingestion-candidate "
            "--tag rag-candidate:grounded_citation --limit 10 --output json"
        ),
        "candidateReviewAction": (
            "reactor-admin rag-candidates --status INGESTED "
            "--tag collection:rag-ingestion-candidate "
            "--tag rag-candidate:grounded_citation --limit 10 --output table"
        ),
        "bulkReviewAction": (
            "reactor-admin feedback-bulk-review --candidate-tag "
            "rag-candidate:grounded_citation --source slack_button "
            "--status done --tag promoted "
            "--tag langsmith --tag expected-citation:candidate-runbook.md "
            "--tag collection:rag-ingestion-candidate --tag rag-candidate:grounded_citation "
            "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
            "--output table"
        ),
    }
    stderr = capsys.readouterr().err
    assert "release_readiness status=blocked" in stderr
    assert "datasetName=reactor-rag-ingestion-candidate" in stderr
    assert "releaseNext=run_reactor_langsmith_eval_sync_without_dry_run" in stderr
    assert "feedbackQueueCases=1" in stderr
    assert (
        "feedbackQueueExportAction='reactor-admin feedback-export --rating thumbs_down "
        "--source slack_button "
        "--review-status inbox "
        "--case-id case_rag_candidate_grounded_citation "
        "--tag collection:rag-ingestion-candidate --tag rag-candidate:grounded_citation "
        "--limit 10 --output json'"
    ) in stderr
    assert (
        "feedbackQueueReviewAction='reactor-admin feedback --rating thumbs_down "
        "--source slack_button "
        "--review-status inbox "
        "--case-id case_rag_candidate_grounded_citation "
        "--tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:grounded_citation --limit 10 --output table'"
    ) in stderr
    assert (
        "feedbackQueueCandidateAction='reactor-admin rag-candidates "
        "--status INGESTED --tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:grounded_citation --limit 10 --output table'"
    ) in stderr
    assert (
        'feedbackQueueBulkReviewAction="reactor-admin feedback-bulk-review '
        "--candidate-tag rag-candidate:grounded_citation --source slack_button "
        "--status done --tag promoted "
        "--tag langsmith --tag expected-citation:candidate-runbook.md "
        "--tag collection:rag-ingestion-candidate --tag rag-candidate:grounded_citation "
        "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
        '--output table"'
    ) in stderr
    assert (
        "hardening_suite: status=skipped failure=required report missing "
        "remediationCommand='uv run "
        "reactor-hardening-suite --report-file reports/hardening-suite.json' "
        "readinessReportArg='--readiness-report "
        "hardening_suite=reports/hardening-suite.json'"
    ) in stderr


def test_release_smoke_run_readiness_required_reports_extend_defaults(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    evidence_path = tmp_path / "release-evidence.json"
    readiness_path = tmp_path / "release-readiness.json"
    langsmith_path = tmp_path / "langsmith-eval-sync.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    langsmith_path.write_text(
        json.dumps(
            {
                "ok": True,
                "status": "passed",
                "scope": "langsmith_eval_dataset_sync",
                "evidence": valid_langsmith_eval_sync_evidence(artifact=str(langsmith_path)),
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--verified-at",
            "2026-06-28T00:00:00Z",
            "--evidence-output",
            str(evidence_path),
            "--readiness-output",
            str(readiness_path),
            "--required-readiness-report",
            "langsmith_eval_sync",
            "--readiness-report",
            f"langsmith_eval_sync={langsmith_path}",
        ]
    )

    assert exit_code == 0
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["requiredReports"] == [
        "smoke_run",
        "release_evidence",
        "langsmith_eval_sync",
    ]


def test_release_evidence_readiness_report_fails_when_any_gate_failed() -> None:
    from reactor.release.smoke_plan import release_evidence_readiness_report

    report = release_evidence_readiness_report(
        {
            "live_provider_runtime_smoke": {
                "status": "failed",
                "scope": "live",
                "evidence_uri": "reports/live-provider-runtime-smoke.json",
                "verified_at": "2026-06-28T00:00:00Z",
            }
        },
        "reports/release-evidence.json",
    )

    assert report == {
        "ok": False,
        "status": "failed",
        "scope": "release_evidence",
        "evidence": {
            "artifact": "reports/release-evidence.json",
            "owner": "reactor.release",
            "mode": "release_evidence",
            "releaseEvidence": {
                "gateCount": 1,
                "gateCodes": ["live_provider_runtime_smoke"],
                "scopes": {"live": 1},
                "statusCounts": {"failed": 1},
            },
        },
        "error": "release evidence gate failed: live_provider_runtime_smoke",
    }


def test_release_smoke_preflight_reports_missing_required_env() -> None:
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "live_backend_provider_integration",
                "mode": "automated",
                "evidence_scope": "live",
                "release_gate_closer": True,
                "evidence_uri": "reports/live-backend-provider-integration.json",
                "command": ["uv", "run", "reactor-live-backend-provider-smoke"],
                "required_env": {
                    "variables": ["OPENAI_API_KEY"],
                    "any_of": [["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]],
                },
            },
            {
                "code": "live_peer_network_interoperability_smoke",
                "mode": "automated",
                "evidence_scope": "live",
                "release_gate_closer": True,
                "evidence_uri": "reports/live-peer-network-interoperability-smoke.json",
                "command": ["uv", "run", "reactor-live-a2a-peer-smoke"],
                "required_env": {
                    "variables": ["REACTOR_A2A_BASE_URL", "REACTOR_A2A_API_KEY"],
                },
            },
            {
                "code": "full_backup_db_dress_rehearsal",
                "mode": "manual",
                "evidence_scope": "dress_rehearsal",
                "release_gate_closer": True,
                "evidence_uri": "reports/full-backup-db-dress-rehearsal.json",
                "command": ["uv", "run", "reactor-migration-dress-rehearsal", "--help"],
                "required_env": {
                    "variables": [
                        "REACTOR_FULL_BACKUP_EXPORTED_NDJSON",
                        "REACTOR_FULL_BACKUP_ROLLBACK_NDJSON",
                    ]
                },
            },
        ]
    }

    report = run_release_smoke_preflight(
        plan,
        environ={
            "OPENAI_API_KEY": "provider-key",
            "REACTOR_A2A_BASE_URL": "https://reactor.example",
        },
    )

    assert report == {
        "ok": False,
        "summary": {
            "total": 3,
            "ready": 0,
            "blocked": 3,
            "optional_missing": 0,
        },
        "steps": [
            {
                "code": "live_backend_provider_integration",
                "mode": "automated",
                "status": "blocked",
                "missing": [],
                "missing_any_of": [
                    ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                ],
                "optional_missing": [],
                "command": ["uv", "run", "reactor-live-backend-provider-smoke"],
                "evidence_uri": "reports/live-backend-provider-integration.json",
                "evidence_scope": "live",
            },
            {
                "code": "live_peer_network_interoperability_smoke",
                "mode": "automated",
                "status": "blocked",
                "missing": ["REACTOR_A2A_API_KEY"],
                "missing_any_of": [],
                "optional_missing": [],
                "command": ["uv", "run", "reactor-live-a2a-peer-smoke"],
                "evidence_uri": "reports/live-peer-network-interoperability-smoke.json",
                "evidence_scope": "live",
            },
            {
                "code": "full_backup_db_dress_rehearsal",
                "mode": "manual",
                "status": "blocked",
                "missing": [
                    "REACTOR_FULL_BACKUP_EXPORTED_NDJSON",
                    "REACTOR_FULL_BACKUP_ROLLBACK_NDJSON",
                ],
                "missing_any_of": [],
                "optional_missing": [],
                "command": ["uv", "run", "reactor-migration-dress-rehearsal", "--help"],
                "evidence_uri": "reports/full-backup-db-dress-rehearsal.json",
                "evidence_scope": "dress_rehearsal",
            },
        ],
    }


def test_release_smoke_preflight_preserves_step_execution_metadata() -> None:
    report = run_release_smoke_preflight(
        {
            "steps": [
                {
                    "code": "live_provider_runtime_smoke",
                    "mode": "automated",
                    "evidence_scope": "live",
                    "release_gate_closer": True,
                    "evidence_uri": "reports/live-provider-runtime-smoke.json",
                    "command": ["uv", "run", "reactor-live-provider-smoke"],
                    "required_env": {"variables": ["OPENAI_API_KEY"]},
                }
            ]
        },
        environ={},
    )

    step = cast(list[dict[str, object]], report["steps"])[0]
    assert step["command"] == ["uv", "run", "reactor-live-provider-smoke"]
    assert step["evidence_uri"] == "reports/live-provider-runtime-smoke.json"
    assert step["evidence_scope"] == "live"


def test_release_smoke_run_cli_can_write_preflight_file(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    preflight_path = tmp_path / "preflight.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                        "required_env": {
                            "variables": ["OPENAI_API_KEY"],
                            "any_of": [["LANGSMITH_API_KEY", "REACTOR_LANGSMITH_API_KEY"]],
                            "recommended": ["LANGSMITH_ENDPOINT"],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--preflight-file",
            str(preflight_path),
            "--preflight-only",
        ]
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "release_smoke_preflight ok=false blocked=1 ready=0 optional_missing=0" in stderr
    assert "blockedStep=live_provider_runtime_smoke" in stderr
    assert "missingEnv=OPENAI_API_KEY" in stderr
    assert "missingAnyOf=LANGSMITH_API_KEY|REACTOR_LANGSMITH_API_KEY" in stderr
    payload = json.loads(preflight_path.read_text(encoding="utf-8"))
    assert payload["summary"] == {"total": 1, "ready": 0, "blocked": 1, "optional_missing": 0}
    assert payload["steps"][0]["missing"] == ["OPENAI_API_KEY"]


def test_release_smoke_run_cli_writes_readiness_for_blocked_preflight(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    preflight_path = tmp_path / "preflight.json"
    preflight_env_template_path = tmp_path / "preflight.env"
    readiness_path = tmp_path / "release-readiness.json"
    evidence_path = tmp_path / "release-evidence.json"
    operator_check_path = tmp_path / "operator-check.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                        "required_env": {
                            "variables": ["OPENAI_API_KEY"],
                            "any_of": [["LANGSMITH_API_KEY", "REACTOR_LANGSMITH_API_KEY"]],
                            "recommended": ["LANGSMITH_ENDPOINT"],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    operator_check_path.write_text(
        json.dumps(
            {
                "ok": True,
                "status": "passed",
                "scope": "operator_check",
                "evidence": {"checked": True},
            }
        ),
        encoding="utf-8",
    )

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--preflight-file",
            str(preflight_path),
            "--preflight-env-template",
            str(preflight_env_template_path),
            "--preflight-only",
            "--readiness-output",
            str(readiness_path),
            "--evidence-output",
            str(evidence_path),
            "--required-readiness-report",
            "operator_check",
            "--readiness-report",
            f"operator_check={operator_check_path}",
        ]
    )

    assert exit_code == 1
    assert preflight_path.exists()
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    assert preflight["status"] == "blocked"
    assert preflight["scope"] == "release_smoke_preflight"
    assert preflight["failure"] == "release smoke preflight blocked by missing environment"
    assert preflight["preflightEnvTemplate"] == str(preflight_env_template_path)
    assert preflight["remediationCommand"] == (
        f"uv run reactor-release-smoke-run --plan {plan_path} "
        f"--env-file {preflight_env_template_path} "
        f"--preflight-file {preflight_path} "
        f"--preflight-only --readiness-output {readiness_path} "
        f"--readiness-report operator_check={operator_check_path} "
        "--required-readiness-report operator_check"
    )
    assert preflight["releaseSmokeEnvFileCommand"] == (
        f"uv run reactor-release-smoke-run --plan {plan_path} "
        f"--env-file {preflight_env_template_path} "
        f"--preflight-file {preflight_path} "
        "--report-file reports/release-smoke-run.json "
        "--verified-at $(date -u +%Y-%m-%dT%H:%M:%SZ) "
        f"--evidence-output {evidence_path} "
        f"--readiness-output {readiness_path} "
        f"--readiness-report operator_check={operator_check_path} "
        "--required-readiness-report operator_check"
    )
    assert preflight["readyNextActionIds"] == ["set-release-smoke-preflight-env"]
    assert preflight["nextActionStates"] == {"set-release-smoke-preflight-env": "ready"}
    assert preflight["nextActions"][0]["id"] == "set-release-smoke-preflight-env"
    assert preflight["nextActions"][0]["command"] == preflight["preflightEnvFileCommand"]
    assert preflight["nextActions"][0]["requiredEnvAnyOf"] == [
        ["LANGSMITH_API_KEY", "REACTOR_LANGSMITH_API_KEY"]
    ]
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["ok"] is False
    assert readiness["status"] == "blocked"
    assert readiness["requiredReports"] == ["preflight", "operator_check"]
    assert readiness["missingReports"] == []
    items = readiness["items"]
    assert items[0]["name"] == "preflight"
    assert items[0]["status"] == "blocked"
    assert items[0]["failure"] == "release smoke preflight blocked by missing environment"
    assert items[1]["name"] == "operator_check"
    assert items[1]["status"] == "passed"
    assert items[0]["preflightSummary"] == {
        "total": 1,
        "ready": 0,
        "blocked": 1,
        "optional_missing": 0,
    }
    assert items[0]["preflightMissingEnv"] == ["OPENAI_API_KEY"]
    assert items[0]["preflightMissingAnyOf"] == ["LANGSMITH_API_KEY|REACTOR_LANGSMITH_API_KEY"]
    assert items[0]["preflightRecommendedEnv"] == ["LANGSMITH_ENDPOINT"]
    assert items[0]["remediationCommand"] == (
        f"uv run reactor-release-smoke-run --plan {plan_path} "
        f"--env-file {preflight_env_template_path} "
        f"--preflight-file {preflight_path} "
        f"--preflight-only --readiness-output {readiness_path} "
        f"--readiness-report operator_check={operator_check_path} "
        "--required-readiness-report operator_check"
    )
    assert items[0]["preflightEnvTemplate"] == str(preflight_env_template_path)
    assert items[0]["preflightBlockedGates"] == [
        {
            "code": "live_provider_runtime_smoke",
            "command": ["uv", "run", "reactor-live-provider-smoke"],
            "evidence_uri": "reports/live-provider-runtime-smoke.json",
            "evidence_scope": "live",
            "missing": ["OPENAI_API_KEY"],
            "missing_any_of": [["LANGSMITH_API_KEY", "REACTOR_LANGSMITH_API_KEY"]],
            "recommended_env": ["LANGSMITH_ENDPOINT"],
        }
    ]
    assert items[0]["nextActions"][0]["recommendedEnv"] == ["LANGSMITH_ENDPOINT"]
    from reactor.release.readiness_evidence import readiness_failure_summary

    summary = readiness_failure_summary(readiness)
    assert "nextAction.set-release-smoke-preflight-env.recommendedEnv=LANGSMITH_ENDPOINT" in summary


def test_release_smoke_preflight_only_exits_nonzero_when_readiness_blocks(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    preflight_path = tmp_path / "preflight.json"
    readiness_path = tmp_path / "release-readiness.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "local_contract",
                        "mode": "automated",
                        "evidence_scope": "local_contract",
                        "release_gate_closer": False,
                        "evidence_uri": "reports/local-contract.json",
                        "command": ["uv", "run", "pytest", "tests/unit/test_langchain_agent.py"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--preflight-file",
            str(preflight_path),
            "--preflight-only",
            "--readiness-output",
            str(readiness_path),
            "--required-readiness-report",
            "langsmith_eval_sync",
        ]
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "release_readiness status=blocked" in stderr
    assert "missingReports=langsmith_eval_sync" in stderr
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["ok"] is False
    assert readiness["status"] == "blocked"
    assert readiness["requiredReports"] == ["preflight", "langsmith_eval_sync"]
    assert readiness["missingReports"] == ["langsmith_eval_sync"]


def test_release_smoke_run_readiness_preserves_blocked_step_metadata(
    tmp_path: Path,
) -> None:
    marker_path = tmp_path / "should-not-run.txt"
    plan_path = tmp_path / "smoke-plan.json"
    preflight_path = tmp_path / "preflight.json"
    preflight_env_template_path = tmp_path / "preflight.env"
    report_path = tmp_path / "smoke-run.json"
    readiness_path = tmp_path / "release-readiness.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": str(marker_path),
                        "command": [
                            sys.executable,
                            "-c",
                            (
                                "from pathlib import Path; "
                                f"Path({str(marker_path)!r}).write_text('ran', encoding='utf-8')"
                            ),
                        ],
                        "required_env": {
                            "variables": ["OPENAI_API_KEY"],
                            "any_of": [["LANGSMITH_API_KEY", "REACTOR_LANGSMITH_API_KEY"]],
                            "recommended": ["LANGSMITH_ENDPOINT"],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--preflight-file",
            str(preflight_path),
            "--preflight-env-template",
            str(preflight_env_template_path),
            "--report-file",
            str(report_path),
            "--readiness-output",
            str(readiness_path),
            "--skip-release-evidence-readiness",
        ]
    )

    assert exit_code == 1
    assert marker_path.exists() is False
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["status"] == "blocked"
    smoke_run = readiness["items"][0]
    assert smoke_run["name"] == "smoke_run"
    assert smoke_run["status"] == "blocked"
    assert smoke_run["failure"] == "release smoke run blocked by missing environment"
    assert smoke_run["smokeRunSummary"] == {
        "total": 1,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "blocked": 1,
    }
    assert smoke_run["smokeRunMissingEnv"] == ["OPENAI_API_KEY"]
    assert smoke_run["smokeRunMissingAnyOf"] == ["LANGSMITH_API_KEY|REACTOR_LANGSMITH_API_KEY"]
    assert smoke_run["smokeRunRecommendedEnv"] == ["LANGSMITH_ENDPOINT"]
    assert smoke_run["remediationCommand"] == (
        f"uv run reactor-release-smoke-run --plan {plan_path} "
        f"--env-file {preflight_env_template_path} "
        f"--preflight-file {preflight_path} "
        f"--preflight-only --readiness-output {readiness_path} "
        "--skip-release-evidence-readiness"
    )
    assert smoke_run["preflightEnvFileCommand"] == (
        f"uv run reactor-release-smoke-run --plan {plan_path} "
        f"--env-file {preflight_env_template_path} "
        f"--preflight-file {preflight_path} "
        f"--preflight-only --readiness-output {readiness_path} "
        "--skip-release-evidence-readiness"
    )
    assert smoke_run["releaseSmokeEnvFileCommand"] == (
        f"uv run reactor-release-smoke-run --plan {plan_path} "
        f"--env-file {preflight_env_template_path} "
        f"--preflight-file {preflight_path} "
        f"--report-file {report_path} "
        "--verified-at $(date -u +%Y-%m-%dT%H:%M:%SZ) "
        f"--readiness-output {readiness_path} "
        "--skip-release-evidence-readiness"
    )
    assert smoke_run["preflightEnvTemplate"] == str(preflight_env_template_path)
    assert smoke_run["smokeRunBlockedGates"][0]["code"] == "live_provider_runtime_smoke"
    assert smoke_run["smokeRunBlockedGates"][0]["missing_any_of"] == [
        ["LANGSMITH_API_KEY", "REACTOR_LANGSMITH_API_KEY"]
    ]


def test_release_smoke_run_cli_uses_env_file_for_preflight_handoff_without_template(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    env_path = tmp_path / "release-smoke-preflight.local.env"
    preflight_path = tmp_path / "preflight.json"
    readiness_path = tmp_path / "release-readiness.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                        "required_env": {"variables": ["OPENAI_API_KEY"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    env_path.write_text("OPENAI_API_KEY=\n", encoding="utf-8")

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--env-file",
            str(env_path),
            "--preflight-file",
            str(preflight_path),
            "--preflight-only",
            "--readiness-output",
            str(readiness_path),
        ]
    )

    assert exit_code == 1
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    assert preflight["preflightEnvTemplate"] == str(env_path)
    assert preflight["preflightEnvFileCommand"] == (
        f"uv run reactor-release-smoke-run --plan {plan_path} "
        f"--env-file {env_path} "
        f"--preflight-file {preflight_path} "
        f"--preflight-only --readiness-output {readiness_path}"
    )
    assert preflight["preflightEnvTemplateRefreshPath"] == f"{env_path}.example"
    assert preflight["preflightEnvTemplateRefreshCommand"] == (
        f"uv run reactor-release-smoke-run --plan {plan_path} "
        f"--preflight-file {preflight_path} "
        f"--preflight-env-template {env_path}.example "
        f"--preflight-only --readiness-output {readiness_path}"
    )
    assert preflight["remediationCommand"] == preflight["preflightEnvFileCommand"]
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    recommendation = readiness["tagRecommendation"]
    assert recommendation["preflightEnvTemplate"] == str(env_path)
    assert recommendation["preflightEnvTemplateRefreshPath"] == f"{env_path}.example"
    assert recommendation["preflightEnvTemplateRefreshCommand"] == (
        f"uv run reactor-release-smoke-run --plan {plan_path} "
        f"--preflight-file {preflight_path} "
        f"--preflight-env-template {env_path}.example "
        f"--preflight-only --readiness-output {readiness_path}"
    )
    assert recommendation["remediationCommand"] == recommendation["preflightEnvFileCommand"]
    assert recommendation["blockingNextActions"][0]["preflightEnvFileCommand"] == (
        f"uv run reactor-release-smoke-run --plan {plan_path} "
        f"--env-file {env_path} "
        f"--preflight-file {preflight_path} "
        f"--preflight-only --readiness-output {readiness_path}"
    )
    assert (
        recommendation["blockingNextActions"][0]["preflightEnvTemplateRefreshCommand"]
        == recommendation["preflightEnvTemplateRefreshCommand"]
    )
    assert (
        recommendation["blockingNextActions"][0]["remediationCommand"]
        == recommendation["blockingNextActions"][0]["preflightEnvFileCommand"]
    )


def test_release_smoke_run_cli_uses_env_file_for_handoff_with_template_output(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    env_path = tmp_path / "release-smoke-preflight.local.env"
    template_path = tmp_path / "release-smoke-preflight.local.env.example"
    preflight_path = tmp_path / "preflight.json"
    readiness_path = tmp_path / "release-readiness.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                        "required_env": {"variables": ["OPENAI_API_KEY"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    env_path.write_text("OPENAI_API_KEY=\n", encoding="utf-8")

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--env-file",
            str(env_path),
            "--preflight-file",
            str(preflight_path),
            "--preflight-env-template",
            str(template_path),
            "--preflight-only",
            "--readiness-output",
            str(readiness_path),
        ]
    )

    assert exit_code == 1
    assert template_path.exists()
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    assert preflight["preflightEnvTemplate"] == str(env_path)
    assert preflight["preflightEnvTemplateRefreshPath"] == str(template_path)
    assert preflight["preflightEnvFileCommand"] == (
        f"uv run reactor-release-smoke-run --plan {plan_path} "
        f"--env-file {env_path} "
        f"--preflight-file {preflight_path} "
        f"--preflight-only --readiness-output {readiness_path}"
    )
    assert preflight["preflightEnvTemplateRefreshCommand"] == (
        f"uv run reactor-release-smoke-run --plan {plan_path} "
        f"--preflight-file {preflight_path} "
        f"--preflight-env-template {template_path} "
        f"--preflight-only --readiness-output {readiness_path}"
    )
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    recommendation = readiness["tagRecommendation"]
    assert recommendation["preflightEnvTemplate"] == str(env_path)
    assert recommendation["preflightEnvTemplateRefreshPath"] == str(template_path)
    assert recommendation["preflightEnvFileCommand"] == preflight["preflightEnvFileCommand"]


def test_release_smoke_run_cli_does_not_execute_preflight_blocked_steps(
    tmp_path: Path,
) -> None:
    marker_path = tmp_path / "should-not-run.txt"
    plan_path = tmp_path / "smoke-plan.json"
    preflight_path = tmp_path / "preflight.json"
    report_path = tmp_path / "smoke-run.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": str(marker_path),
                        "command": [
                            sys.executable,
                            "-c",
                            (
                                "from pathlib import Path; "
                                f"Path({str(marker_path)!r}).write_text('ran', encoding='utf-8')"
                            ),
                        ],
                        "required_env": {"variables": ["OPENAI_API_KEY"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--preflight-file",
            str(preflight_path),
            "--report-file",
            str(report_path),
        ]
    )

    assert exit_code == 1
    assert marker_path.exists() is False
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["summary"] == {
        "total": 1,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "blocked": 1,
    }
    assert report["steps"][0]["status"] == "blocked"
    assert report["steps"][0]["exit_code"] == 0
    assert report["steps"][0]["stderr"] == "required environment is missing"
    assert report["steps"][0]["missing"] == ["OPENAI_API_KEY"]


def test_preflight_readiness_report_preserves_blocked_gate_execution_metadata() -> None:
    report = preflight_readiness_report(
        {
            "ok": False,
            "summary": {"total": 1, "ready": 0, "blocked": 1, "optional_missing": 0},
            "steps": [
                {
                    "code": "live_provider_runtime_smoke",
                    "mode": "automated",
                    "status": "blocked",
                    "missing": ["OPENAI_API_KEY"],
                    "missing_any_of": [],
                    "optional_missing": [],
                    "command": ["uv", "run", "reactor-live-provider-smoke"],
                    "evidence_uri": "reports/live-provider-runtime-smoke.json",
                    "evidence_scope": "live",
                }
            ],
        },
        "reports/release-smoke-preflight.local.json",
    )

    evidence = cast(dict[str, object], report["evidence"])
    assert evidence["preflightBlockedGates"] == [
        {
            "code": "live_provider_runtime_smoke",
            "command": ["uv", "run", "reactor-live-provider-smoke"],
            "evidence_uri": "reports/live-provider-runtime-smoke.json",
            "evidence_scope": "live",
            "missing": ["OPENAI_API_KEY"],
            "missing_any_of": [],
        }
    ]


def test_preflight_readiness_report_preserves_blocked_plan_next_actions() -> None:
    report = preflight_readiness_report(
        {
            "ok": False,
            "status": "blocked",
            "summary": {"total": 0, "ready": 0, "blocked": 1, "optional_missing": 0},
            "nextActions": [
                {
                    "sourceReport": "langsmith_eval_sync",
                    "id": "sync-langsmith",
                    "command": (
                        "uv run reactor-langsmith-eval-sync "
                        "--suite-file evals/regression/rag-ingestion-candidate.json "
                        "--dataset-name reactor-rag-ingestion-candidate "
                        "--report-file artifacts/langsmith/rag-ingestion-candidate-c1.json"
                    ),
                    "readinessReportArg": (
                        "--readiness-report "
                        "langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate-c1.json"
                    ),
                }
            ],
        },
        "reports/release-smoke-preflight.local.json",
    )

    evidence = cast(dict[str, object], report["evidence"])
    assert evidence["nextActions"] == [
        {
            "sourceReport": "langsmith_eval_sync",
            "id": "sync-langsmith",
            "command": (
                "uv run reactor-langsmith-eval-sync "
                "--suite-file evals/regression/rag-ingestion-candidate.json "
                "--dataset-name reactor-rag-ingestion-candidate "
                "--report-file artifacts/langsmith/rag-ingestion-candidate-c1.json"
            ),
            "readinessReportArg": (
                "--readiness-report "
                "langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate-c1.json"
            ),
        }
    ]


def test_preflight_readiness_report_remediation_preserves_readiness_cli_options() -> None:
    report = preflight_readiness_report(
        {
            "ok": False,
            "summary": {"total": 1, "ready": 0, "blocked": 1, "optional_missing": 0},
            "steps": [
                {
                    "code": "live_provider_runtime_smoke",
                    "status": "blocked",
                    "missing": ["OPENAI_API_KEY"],
                    "missing_any_of": [],
                }
            ],
        },
        "reports/release/release-smoke-preflight.local.json",
        plan_file="reports/release/release-smoke-plan.local.json",
        preflight_env_template="reports/release/release-smoke-preflight.local.env",
        readiness_output="reports/release-readiness.json",
        readiness_reports=["langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate.json"],
        required_readiness_reports=["hardening_suite", "langsmith_eval_sync"],
        latest_tag="v1.0.240",
        skip_release_evidence_readiness=True,
    )

    evidence = cast(dict[str, object], report["evidence"])
    assert evidence["remediationCommand"] == (
        "uv run reactor-release-smoke-run "
        "--plan reports/release/release-smoke-plan.local.json "
        "--env-file reports/release/release-smoke-preflight.local.env "
        "--preflight-file reports/release/release-smoke-preflight.local.json "
        "--preflight-only "
        "--readiness-output reports/release-readiness.json "
        "--readiness-report "
        "langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate.json "
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync "
        "--latest-tag v1.0.240 "
        "--skip-release-evidence-readiness"
    )


def test_release_smoke_preflight_blocks_empty_plan_with_remediation(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    preflight_path = tmp_path / "preflight.json"
    plan_path.write_text(
        json.dumps(
            {
                "status": "blocked",
                "failure": "release evidence requirements missing",
                "remediationCommand": (
                    "uv run reactor-replatform-readiness --output "
                    "reports/release/replatform-readiness.local.json"
                ),
                "nextActions": [
                    {
                        "sourceReport": "langsmith_eval_sync",
                        "id": "sync-langsmith",
                        "command": (
                            "uv run reactor-langsmith-eval-sync "
                            "--suite-file evals/regression/rag-ingestion-candidate.json "
                            "--dataset-name reactor-rag-ingestion-candidate "
                            "--report-file artifacts/langsmith/rag-ingestion-candidate-c1.json"
                        ),
                        "readinessReportArg": (
                            "--readiness-report "
                            "langsmith_eval_sync=artifacts/langsmith/"
                            "rag-ingestion-candidate-c1.json"
                        ),
                    },
                ],
                "steps": [],
                "summary": {"total": 0, "automated": 0, "manual": 0},
            }
        ),
        encoding="utf-8",
    )

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--preflight-file",
            str(preflight_path),
            "--preflight-only",
        ]
    )

    assert exit_code == 1
    payload = json.loads(preflight_path.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["status"] == "blocked"
    assert payload["failure"] == "release evidence requirements missing"
    assert payload["remediationCommand"] == (
        "uv run reactor-replatform-readiness --output "
        "reports/release/replatform-readiness.local.json"
    )
    assert payload["nextActions"] == [
        {
            "sourceReport": "langsmith_eval_sync",
            "id": "sync-langsmith",
            "command": (
                "uv run reactor-langsmith-eval-sync "
                "--suite-file evals/regression/rag-ingestion-candidate.json "
                "--dataset-name reactor-rag-ingestion-candidate "
                "--report-file artifacts/langsmith/rag-ingestion-candidate-c1.json"
            ),
            "readinessReportArg": (
                "--readiness-report "
                "langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate-c1.json"
            ),
        },
    ]
    assert payload["summary"] == {"total": 0, "ready": 0, "blocked": 1, "optional_missing": 0}
    stderr = capsys.readouterr().err
    assert "nextActions=sync-langsmith" in stderr
    assert (
        "nextAction.sync-langsmith.readinessReportArg='--readiness-report "
        "langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate-c1.json'"
    ) in stderr


def test_build_preflight_env_template_lists_missing_required_any_of_and_optional_values() -> None:
    template = build_preflight_env_template(
        {
            "steps": [
                {
                    "code": "live_backend_provider_integration",
                    "missing": ["OPENAI_API_KEY"],
                    "missing_any_of": [
                        ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                    ],
                    "recommended_env": ["LANGSMITH_ENDPOINT"],
                    "optional_missing": [],
                },
                {
                    "code": "live_peer_network_interoperability_smoke",
                    "missing": ["REACTOR_A2A_BASE_URL", "OPENAI_API_KEY"],
                    "missing_any_of": [],
                    "optional_missing": ["REACTOR_A2A_API_KEY"],
                },
            ]
        }
    )

    assert template == "\n".join(
        [
            "# Required",
            "OPENAI_API_KEY=",
            "REACTOR_A2A_BASE_URL=",
            "",
            "# Required alternatives: set at least one value in each group",
            (
                "# any-of group 1 (live_backend_provider_integration): "
                "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
            ),
            "LANGSMITH_API_KEY=",
            "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY=",
            "",
            "# Recommended",
            "LANGSMITH_ENDPOINT=",
            "",
            "# Optional",
            "REACTOR_A2A_API_KEY=",
            "",
        ]
    )


def test_tracked_release_smoke_preflight_env_file_preserves_any_of_group_context() -> None:
    template = Path("reports/release/release-smoke-preflight.local.env").read_text(encoding="utf-8")

    assert (
        "# any-of group 1 (live_backend_provider_integration): "
        "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    ) in template
    assert (
        "# live_backend_provider_integration: missing=OPENAI_API_KEY "
        "missingAnyOf=LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    ) in template


def test_build_preflight_env_template_preserves_required_any_of_groups() -> None:
    template = build_preflight_env_template(
        {
            "steps": [
                {
                    "code": "langsmith_eval_sync",
                    "missing": [],
                    "missing_any_of": [
                        ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"],
                    ],
                    "optional_missing": [],
                },
                {
                    "code": "external_peer",
                    "missing": [],
                    "missing_any_of": [
                        ["REACTOR_A2A_API_KEY", "REACTOR_A2A_CLIENT_SECRET"],
                    ],
                    "optional_missing": [],
                },
            ]
        }
    )

    assert (
        "# any-of group 1 (langsmith_eval_sync): "
        "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    ) in template
    assert (
        "# any-of group 2 (external_peer): REACTOR_A2A_API_KEY|REACTOR_A2A_CLIENT_SECRET"
        in template
    )


def test_build_preflight_env_template_preserves_all_gate_codes_for_shared_any_of_group() -> None:
    template = build_preflight_env_template(
        {
            "steps": [
                {
                    "code": "langsmith_eval_sync",
                    "missing": [],
                    "missing_any_of": [
                        ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"],
                    ],
                    "optional_missing": [],
                },
                {
                    "code": "live_backend_provider_integration",
                    "missing": [],
                    "missing_any_of": [
                        ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"],
                    ],
                    "optional_missing": [],
                },
            ]
        }
    )

    assert (
        "# any-of group 1 (langsmith_eval_sync,live_backend_provider_integration): "
        "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    ) in template


def test_build_preflight_env_template_maps_blocked_gates_to_missing_env() -> None:
    template = build_preflight_env_template(
        {
            "steps": [
                {
                    "code": "live_backend_provider_integration",
                    "status": "blocked",
                    "missing": ["OPENAI_API_KEY"],
                    "missing_any_of": [
                        ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                    ],
                    "optional_missing": [],
                },
                {
                    "code": "live_peer_network_interoperability_smoke",
                    "status": "ready",
                    "missing": [],
                    "missing_any_of": [],
                    "optional_missing": ["REACTOR_A2A_API_KEY"],
                },
                {
                    "code": "live_slack_workspace_smoke",
                    "status": "blocked",
                    "missing": ["REACTOR_SLACK_SIGNING_SECRET", "REACTOR_SLACK_BOT_TOKEN"],
                    "missing_any_of": [],
                    "optional_missing": [],
                },
            ]
        }
    )

    assert "# Blocked gates" in template
    assert (
        "# live_backend_provider_integration: missing=OPENAI_API_KEY "
        "missingAnyOf=LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    ) in template
    assert (
        "# live_slack_workspace_smoke: missing=REACTOR_SLACK_BOT_TOKEN,REACTOR_SLACK_SIGNING_SECRET"
    ) in template
    assert "live_peer_network_interoperability_smoke" not in template


def test_release_smoke_preflight_summary_sorts_missing_env_names() -> None:
    summary = release_smoke_preflight_failure_summary(
        {
            "ok": False,
            "summary": {"total": 1, "ready": 0, "blocked": 1, "optional_missing": 0},
            "steps": [
                {
                    "code": "live_slack_workspace_smoke",
                    "status": "blocked",
                    "missing": ["REACTOR_SLACK_SIGNING_SECRET", "REACTOR_SLACK_BOT_TOKEN"],
                    "missing_any_of": [],
                    "optional_missing": [],
                }
            ],
        }
    )

    assert "missingEnv=REACTOR_SLACK_BOT_TOKEN,REACTOR_SLACK_SIGNING_SECRET" in summary


def test_release_smoke_preflight_summary_lists_ready_local_contract_steps() -> None:
    summary = release_smoke_preflight_failure_summary(
        {
            "ok": False,
            "summary": {"total": 2, "ready": 1, "blocked": 1, "optional_missing": 0},
            "steps": [
                {
                    "code": "live_provider_runtime_smoke",
                    "status": "blocked",
                    "evidence_scope": "live",
                    "missing": ["OPENAI_API_KEY"],
                    "missing_any_of": [],
                    "optional_missing": [],
                },
                {
                    "code": "live_provider_runtime_local_contract",
                    "status": "ready",
                    "evidence_scope": "local_contract",
                    "command": [
                        "uv",
                        "run",
                        "pytest",
                        "tests/unit/test_langchain_agent.py",
                        "tests/unit/test_run_service.py",
                    ],
                },
            ],
        }
    )

    assert (
        "- readyLocalContract=live_provider_runtime_local_contract "
        "command='uv run pytest tests/unit/test_langchain_agent.py "
        "tests/unit/test_run_service.py'"
    ) in summary


def test_build_preflight_env_template_lists_prior_evidence_freshness() -> None:
    template = build_preflight_env_template(
        {
            "steps": [
                {
                    "code": "live_provider_runtime_smoke",
                    "missing": ["OPENAI_API_KEY"],
                    "missing_any_of": [],
                    "optional_missing": [],
                    "prior_evidence": {
                        "status": "passed",
                        "scope": "live",
                        "revision_status": "missing",
                    },
                },
                {
                    "code": "live_slack_workspace_smoke",
                    "missing": ["REACTOR_SLACK_BOT_TOKEN"],
                    "missing_any_of": [],
                    "optional_missing": [],
                    "prior_evidence": {
                        "status": "passed",
                        "scope": "live",
                        "revision_status": "stale",
                        "git_commit": "old123",
                    },
                },
            ]
        }
    )

    assert "# Prior release evidence" in template
    assert "# live_provider_runtime_smoke: status=passed scope=live revision=missing" in template
    assert (
        "# live_slack_workspace_smoke: status=passed scope=live revision=stale git_commit=old123"
    ) in template


def test_release_smoke_run_cli_can_write_preflight_env_template(tmp_path: Path) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    preflight_path = tmp_path / "preflight.json"
    template_path = tmp_path / "preflight.env"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                        "required_env": {"variables": ["OPENAI_API_KEY"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--preflight-file",
            str(preflight_path),
            "--preflight-env-template",
            str(template_path),
            "--preflight-only",
        ]
    )

    assert exit_code == 1
    assert template_path.read_text(encoding="utf-8") == (
        "# Required\n"
        "OPENAI_API_KEY=\n"
        "\n"
        "# Blocked gates\n"
        "# live_provider_runtime_smoke: missing=OPENAI_API_KEY\n"
    )


def test_read_env_file_ignores_comments_and_supports_export_prefix(tmp_path: Path) -> None:
    env_path = tmp_path / "release.env"
    env_path.write_text(
        "\n".join(
            [
                "# comment",
                "OPENAI_API_KEY=provider-key",
                "export REACTOR_A2A_BASE_URL=https://reactor.example",
                "BLANK=",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert read_env_file(env_path) == {
        "OPENAI_API_KEY": "provider-key",
        "REACTOR_A2A_BASE_URL": "https://reactor.example",
        "BLANK": "",
    }


def test_release_smoke_run_cli_uses_env_file_for_preflight(tmp_path: Path) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    env_path = tmp_path / "release.env"
    preflight_path = tmp_path / "preflight.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                        "required_env": {"variables": ["OPENAI_API_KEY"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    env_path.write_text("OPENAI_API_KEY=provider-key\n", encoding="utf-8")

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--env-file",
            str(env_path),
            "--preflight-file",
            str(preflight_path),
            "--preflight-only",
        ]
    )

    assert exit_code == 0
    payload = json.loads(preflight_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["summary"] == {"total": 1, "ready": 1, "blocked": 0, "optional_missing": 0}


def test_release_smoke_preflight_blocks_placeholder_env_file_values(tmp_path: Path) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    env_path = tmp_path / "release.env"
    preflight_path = tmp_path / "preflight.json"
    template_path = tmp_path / "release.env.example"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_backend_provider_integration",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-backend-provider-integration.json",
                        "command": ["uv", "run", "reactor-live-backend-provider-smoke"],
                        "required_env": {
                            "variables": ["OPENAI_API_KEY"],
                            "any_of": [
                                [
                                    "LANGSMITH_API_KEY",
                                    "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY",
                                ]
                            ],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=<OPENAI_API_KEY>",
                "LANGSMITH_API_KEY=REPLACE_ME",
                "",
            ]
        ),
        encoding="utf-8",
    )

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--env-file",
            str(env_path),
            "--preflight-file",
            str(preflight_path),
            "--preflight-env-template",
            str(template_path),
            "--preflight-only",
        ]
    )

    assert exit_code == 1
    payload = json.loads(preflight_path.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["summary"] == {"total": 1, "ready": 0, "blocked": 1, "optional_missing": 0}
    step = payload["steps"][0]
    assert step["status"] == "blocked"
    assert step["missing"] == ["OPENAI_API_KEY"]
    assert step["missing_any_of"] == [
        ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
    ]
    assert step["placeholder_env"] == ["LANGSMITH_API_KEY", "OPENAI_API_KEY"]
    assert "placeholder=LANGSMITH_API_KEY,OPENAI_API_KEY" in template_path.read_text(
        encoding="utf-8"
    )


def test_release_smoke_run_cli_uses_env_file_for_command_execution(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    env_path = tmp_path / "release.env"
    report_path = tmp_path / "smoke-run.json"
    captured_env: dict[str, str] = {}
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                        "required_env": {"variables": ["OPENAI_API_KEY"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    env_path.write_text("OPENAI_API_KEY=provider-key\n", encoding="utf-8")

    def fake_subprocess_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: int,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert capture_output is True
        assert text is True
        assert timeout == 120
        captured_env.update(env or {})
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.subprocess.run", fake_subprocess_run)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--env-file",
            str(env_path),
            "--report-file",
            str(report_path),
        ]
    )

    assert exit_code == 0
    assert captured_env["OPENAI_API_KEY"] == "provider-key"


def test_release_smoke_run_cli_blocks_placeholder_env_file_before_command_execution(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    env_path = tmp_path / "release.env"
    report_path = tmp_path / "smoke-run.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                        "required_env": {"variables": ["OPENAI_API_KEY"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    env_path.write_text("OPENAI_API_KEY=<OPENAI_API_KEY>\n", encoding="utf-8")

    def fake_subprocess_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError(
            "placeholder credentials must block before release smoke command execution"
        )

    monkeypatch.setattr("reactor.release.smoke_plan.subprocess.run", fake_subprocess_run)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--env-file",
            str(env_path),
            "--report-file",
            str(report_path),
        ]
    )

    assert exit_code == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["summary"] == {"total": 1, "passed": 0, "failed": 0, "skipped": 0, "blocked": 1}
    step = report["steps"][0]
    assert step["status"] == "blocked"
    assert step["failure"] == "release smoke run blocked by missing environment"
    assert step["missing"] == ["OPENAI_API_KEY"]
    assert step["placeholder_env"] == ["OPENAI_API_KEY"]
    assert "<OPENAI_API_KEY>" not in json.dumps(report)


def test_release_smoke_run_cli_writes_blocked_report_for_missing_env_file(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    missing_env_path = tmp_path / "missing.env"
    report_path = tmp_path / "smoke-run.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                        "required_env": {"variables": ["OPENAI_API_KEY"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--env-file",
            str(missing_env_path),
            "--report-file",
            str(report_path),
        ]
    )

    assert exit_code == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["status"] == "blocked"
    assert report["failure"] == "release smoke env file unreadable"
    assert report["envFile"] == str(missing_env_path)
    assert report["remediationCommand"] == (
        f"uv run reactor-release-smoke-run --plan {plan_path} "
        f"--preflight-file reports/release-smoke-preflight.json "
        f"--preflight-env-template {missing_env_path}.example "
        "--preflight-only"
    )
    stderr = capsys.readouterr().err
    assert "failure='release smoke env file unreadable'" in stderr
    assert f"envFile='{missing_env_path}'" in stderr


def test_release_smoke_run_cli_writes_readiness_for_missing_env_file(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    missing_env_path = tmp_path / "missing.env"
    report_path = tmp_path / "smoke-run.json"
    readiness_path = tmp_path / "release-readiness.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                        "required_env": {"variables": ["OPENAI_API_KEY"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--env-file",
            str(missing_env_path),
            "--report-file",
            str(report_path),
            "--readiness-output",
            str(readiness_path),
            "--latest-tag",
            "v1.0.255",
        ]
    )

    assert exit_code == 1
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["ok"] is False
    assert readiness["status"] == "blocked"
    assert readiness["requiredReports"] == ["preflight"]
    assert readiness["tagRecommendation"]["status"] == "defer"
    assert readiness["tagRecommendation"]["recommendedVersionBump"] == "none"
    item = readiness["items"][0]
    assert item["name"] == "preflight"
    assert item["envFile"] == str(missing_env_path)
    assert item["failure"] == "release smoke env file unreadable"
    assert f"envFile='{missing_env_path}'" in readiness["failureSummary"]


def test_release_smoke_plan_keeps_ollama_provider_smoke_unblocked() -> None:
    plan = build_release_smoke_plan(
        {
            "release_evidence_requirements": [
                {
                    "code": "live_provider_runtime_smoke",
                    "description": "Local Ollama provider smoke.",
                    "suggested_command": (
                        "uv run reactor-live-provider-smoke "
                        "--provider ollama --model gemma4:12b "
                        "--output reports/release/live-provider-runtime-smoke.json"
                    ),
                    "evidence_schema": {
                        "scope": "live",
                        "evidence_uri": "reports/release/live-provider-runtime-smoke.json",
                    },
                }
            ]
        }
    )

    steps = cast(list[dict[str, object]], plan["steps"])
    assert steps[0]["mode"] == "automated"
    assert steps[0]["required_env"] == {"variables": []}

    preflight = run_release_smoke_preflight(plan, environ={})

    assert preflight["ok"] is True
    assert preflight["summary"] == {"total": 1, "ready": 1, "blocked": 0, "optional_missing": 0}


def test_release_smoke_plan_applies_local_provider_overrides_to_provider_commands() -> None:
    plan = build_release_smoke_plan(
        {
            "release_evidence_requirements": [
                {
                    "code": "live_backend_provider_integration",
                    "description": "Live backend/provider observability integration proof.",
                    "suggested_command": (
                        "uv run reactor-live-backend-provider-smoke "
                        "--output reports/live-backend-provider-integration.json"
                    ),
                    "evidence_schema": {
                        "scope": "live",
                        "evidence_uri": "reports/live-backend-provider-integration.json",
                    },
                },
                {
                    "code": "live_provider_runtime_smoke",
                    "description": "Live LangChain/LangGraph provider runtime smoke.",
                    "suggested_command": (
                        "uv run reactor-live-provider-smoke "
                        "--output reports/live-provider-runtime-smoke.json"
                    ),
                    "evidence_schema": {
                        "scope": "live",
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                    },
                },
            ]
        },
        environ={
            "REACTOR_RELEASE_SMOKE_PROVIDER": "ollama",
            "REACTOR_RELEASE_SMOKE_MODEL": "gemma4:12b",
            "REACTOR_RELEASE_SMOKE_TRACE_EXPORTER": "console",
        },
    )

    steps = cast(list[dict[str, object]], plan["steps"])
    assert steps[0]["command"] == [
        "uv",
        "run",
        "reactor-live-backend-provider-smoke",
        "--output",
        "reports/live-backend-provider-integration.json",
        "--provider",
        "ollama",
        "--model",
        "gemma4:12b",
        "--trace-exporter",
        "console",
    ]
    assert steps[0]["required_env"] == {"variables": []}
    assert steps[1]["command"] == [
        "uv",
        "run",
        "reactor-live-provider-smoke",
        "--output",
        "reports/live-provider-runtime-smoke.json",
        "--provider",
        "ollama",
        "--model",
        "gemma4:12b",
    ]
    assert steps[1]["required_env"] == {"variables": []}

    preflight = run_release_smoke_preflight(plan, environ={})

    assert preflight["ok"] is True
    assert preflight["summary"] == {"total": 2, "ready": 2, "blocked": 0, "optional_missing": 0}


def test_release_smoke_run_cli_redacts_env_file_values_from_command_output(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    env_path = tmp_path / "release.env"
    report_path = tmp_path / "smoke-run.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_provider_runtime_smoke",
                        "mode": "automated",
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-provider-runtime-smoke.json",
                        "command": ["uv", "run", "reactor-live-provider-smoke"],
                        "required_env": {"variables": ["OPENAI_API_KEY"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    env_path.write_text(
        "OPENAI_API_KEY=provider-secret\nLANGSMITH_API_KEY=trace-secret\n",
        encoding="utf-8",
    )

    def fake_subprocess_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: int,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="provider-secret leaked in stdout",
            stderr="trace-secret leaked in stderr",
        )

    monkeypatch.setattr("reactor.release.smoke_plan.subprocess.run", fake_subprocess_run)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--env-file",
            str(env_path),
            "--report-file",
            str(report_path),
        ]
    )

    assert exit_code == 1
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    step = payload["steps"][0]
    assert step["stdout"] == "[redacted] leaked in stdout"
    assert step["stderr"] == "[redacted] leaked in stderr"


def test_build_release_smoke_plan_automates_full_backup_dress_when_artifacts_are_configured(
    tmp_path: Path,
) -> None:
    exported = tmp_path / "exported.ndjson"
    rollback = tmp_path / "rollback.ndjson"
    manifest = tmp_path / "retained-tables.txt"
    imported = tmp_path / "imported.ndjson"
    readiness = tmp_path / "readiness.json"
    exported.write_text("", encoding="utf-8")
    rollback.write_text("", encoding="utf-8")
    manifest.write_text("runtime_settings\n", encoding="utf-8")

    plan = build_release_smoke_plan(
        READINESS_REPORT,
        environ={
            "REACTOR_FULL_BACKUP_EXPORTED_NDJSON": str(exported),
            "REACTOR_FULL_BACKUP_ROLLBACK_NDJSON": str(rollback),
            "REACTOR_FULL_BACKUP_RETAINED_TABLE_MANIFEST": str(manifest),
            "REACTOR_FULL_BACKUP_DRESS_IMPORTED_OUTPUT": str(imported),
            "REACTOR_FULL_BACKUP_DRESS_READINESS_OUTPUT": str(readiness),
            "REACTOR_FULL_BACKUP_DRESS_BATCH_ID": "full-backup-dress",
        },
    )

    assert plan["summary"] == {"total": 3, "automated": 3, "manual": 0}
    steps = cast(list[dict[str, object]], plan["steps"])
    dress_step = steps[2]
    assert dress_step == {
        "code": "full_backup_db_dress_rehearsal",
        "description": "Full backup database migration dress rehearsal.",
        "scope": "dress_rehearsal",
        "evidence_scope": "dress_rehearsal",
        "release_gate_closer": True,
        "evidence_uri": "reports/full-backup-db-dress-rehearsal.json",
        "mode": "automated",
        "command": [
            "uv",
            "run",
            "reactor-migration-dress-rehearsal",
            "--exported",
            str(exported),
            "--rollback",
            str(rollback),
            "--imported-output",
            str(imported),
            "--readiness-output",
            str(readiness),
            "--batch-id",
            "full-backup-dress",
            "--required-table-file",
            str(manifest),
        ],
        "required_env": {
            "variables": [
                "REACTOR_FULL_BACKUP_EXPORTED_NDJSON",
                "REACTOR_FULL_BACKUP_ROLLBACK_NDJSON",
                "REACTOR_FULL_BACKUP_RETAINED_TABLE_MANIFEST",
                "REACTOR_FULL_BACKUP_DRESS_IMPORTED_OUTPUT",
                "REACTOR_FULL_BACKUP_DRESS_READINESS_OUTPUT",
                "REACTOR_FULL_BACKUP_DRESS_BATCH_ID",
            ]
        },
        "manual_note": "",
    }


def test_build_release_smoke_plan_automates_full_backup_db_api_dress_when_api_is_configured(
    tmp_path: Path,
) -> None:
    exported = tmp_path / "exported.ndjson"
    rollback = tmp_path / "rollback.ndjson"
    manifest = tmp_path / "retained-tables.txt"
    imported = tmp_path / "imported.ndjson"
    readiness = tmp_path / "readiness.json"
    api_smoke = tmp_path / "api-smoke.json"
    exported.write_text("", encoding="utf-8")
    rollback.write_text("", encoding="utf-8")
    manifest.write_text("runtime_settings\n", encoding="utf-8")
    report = {
        "release_evidence_requirements": [
            {
                "code": "full_backup_db_api_dress_rehearsal",
                "description": "Full backup database and API migration dress rehearsal.",
                "evidence_schema": {
                    "status": "passed",
                    "scope": "dress_rehearsal",
                    "evidence_uri": "reports/full-backup-db-api-dress-rehearsal.json",
                },
                "suggested_command": (
                    "uv run reactor-migration-dress-rehearsal --help "
                    "# then run against the full backup source/target files and API smoke"
                ),
            },
        ],
    }

    plan = build_release_smoke_plan(
        report,
        environ={
            "REACTOR_FULL_BACKUP_EXPORTED_NDJSON": str(exported),
            "REACTOR_FULL_BACKUP_ROLLBACK_NDJSON": str(rollback),
            "REACTOR_FULL_BACKUP_RETAINED_TABLE_MANIFEST": str(manifest),
            "REACTOR_FULL_BACKUP_DRESS_IMPORTED_OUTPUT": str(imported),
            "REACTOR_FULL_BACKUP_DRESS_READINESS_OUTPUT": str(readiness),
            "REACTOR_FULL_BACKUP_DRESS_BATCH_ID": "full-backup-dress",
            "REACTOR_FULL_BACKUP_API_SMOKE_OUTPUT": str(api_smoke),
            "REACTOR_API_BASE_URL": "https://reactor.example",
            "REACTOR_API_KEY": "api-secret",
        },
    )

    assert plan["summary"] == {"total": 1, "automated": 1, "manual": 0}
    steps = cast(list[dict[str, object]], plan["steps"])
    assert steps[0] == {
        "code": "full_backup_db_api_dress_rehearsal",
        "description": "Full backup database and API migration dress rehearsal.",
        "scope": "dress_rehearsal",
        "evidence_scope": "dress_rehearsal",
        "release_gate_closer": True,
        "evidence_uri": "reports/full-backup-db-api-dress-rehearsal.json",
        "mode": "automated",
        "command": [
            "uv",
            "run",
            "reactor-migration-dress-rehearsal",
            "--exported",
            str(exported),
            "--rollback",
            str(rollback),
            "--imported-output",
            str(imported),
            "--readiness-output",
            str(readiness),
            "--batch-id",
            "full-backup-dress",
            "--required-table-file",
            str(manifest),
        ],
        "commands": [
            [
                "uv",
                "run",
                "reactor-migration-dress-rehearsal",
                "--exported",
                str(exported),
                "--rollback",
                str(rollback),
                "--imported-output",
                str(imported),
                "--readiness-output",
                str(readiness),
                "--batch-id",
                "full-backup-dress",
                "--required-table-file",
                str(manifest),
            ],
            [
                "uv",
                "run",
                "reactor-dress-api-smoke",
                "--output",
                str(api_smoke),
            ],
        ],
        "report_paths": [str(readiness), str(api_smoke)],
        "readiness_reports": [
            {
                "name": "dress_api_smoke",
                "path": str(api_smoke),
                "required": True,
            }
        ],
        "required_env": {
            "variables": [
                "REACTOR_FULL_BACKUP_EXPORTED_NDJSON",
                "REACTOR_FULL_BACKUP_ROLLBACK_NDJSON",
                "REACTOR_FULL_BACKUP_RETAINED_TABLE_MANIFEST",
                "REACTOR_FULL_BACKUP_DRESS_IMPORTED_OUTPUT",
                "REACTOR_FULL_BACKUP_DRESS_READINESS_OUTPUT",
                "REACTOR_FULL_BACKUP_DRESS_BATCH_ID",
                "REACTOR_API_BASE_URL",
                "REACTOR_API_KEY",
            ]
        },
        "manual_note": "",
    }


def test_full_backup_db_api_dress_remains_manual_without_api_smoke_env(tmp_path: Path) -> None:
    exported = tmp_path / "exported.ndjson"
    rollback = tmp_path / "rollback.ndjson"
    manifest = tmp_path / "retained-tables.txt"
    imported = tmp_path / "imported.ndjson"
    readiness = tmp_path / "readiness.json"
    exported.write_text("", encoding="utf-8")
    rollback.write_text("", encoding="utf-8")
    manifest.write_text("runtime_settings\n", encoding="utf-8")
    report = {
        "release_evidence_requirements": [
            {
                "code": "full_backup_db_api_dress_rehearsal",
                "description": "Full backup database and API migration dress rehearsal.",
                "evidence_schema": {"scope": "dress_rehearsal"},
                "suggested_command": (
                    "uv run reactor-migration-dress-rehearsal --help "
                    "# then run against the full backup source/target files and API smoke"
                ),
            },
        ],
    }

    plan = build_release_smoke_plan(
        report,
        environ={
            "REACTOR_FULL_BACKUP_EXPORTED_NDJSON": str(exported),
            "REACTOR_FULL_BACKUP_ROLLBACK_NDJSON": str(rollback),
            "REACTOR_FULL_BACKUP_RETAINED_TABLE_MANIFEST": str(manifest),
            "REACTOR_FULL_BACKUP_DRESS_IMPORTED_OUTPUT": str(imported),
            "REACTOR_FULL_BACKUP_DRESS_READINESS_OUTPUT": str(readiness),
            "REACTOR_FULL_BACKUP_DRESS_BATCH_ID": "full-backup-dress",
        },
    )

    steps = cast(list[dict[str, object]], plan["steps"])
    assert steps[0]["mode"] == "manual"
    assert (
        steps[0]["manual_note"]
        == "then run against the full backup source/target files and API smoke"
    )


def test_run_release_smoke_plan_executes_composite_step_until_first_failure(tmp_path: Path) -> None:
    executed: list[list[str]] = []
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "full_backup_db_api_dress_rehearsal",
                "mode": "automated",
                "evidence_scope": "dress_rehearsal",
                "release_gate_closer": True,
                "evidence_uri": "reports/full-backup-db-api-dress-rehearsal.json",
                "command": ["uv", "run", "reactor-migration-dress-rehearsal"],
                "commands": [
                    ["uv", "run", "reactor-migration-dress-rehearsal"],
                    ["uv", "run", "reactor-dress-api-smoke"],
                ],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        executed.append(command)
        return CommandResult(
            exit_code=1 if command[2] == "reactor-dress-api-smoke" else 0,
            duration_ms=timeout_seconds,
            stdout=f"{command[2]} stdout",
            stderr=f"{command[2]} stderr",
        )

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    assert executed == [
        ["uv", "run", "reactor-migration-dress-rehearsal"],
        ["uv", "run", "reactor-dress-api-smoke"],
    ]
    assert report["ok"] is False
    steps = cast(list[dict[str, object]], report["steps"])
    assert steps[0]["status"] == "failed"
    assert steps[0]["exit_code"] == 1
    assert (
        steps[0]["stdout"]
        == "reactor-migration-dress-rehearsal stdout\nreactor-dress-api-smoke stdout"
    )
    assert (
        steps[0]["stderr"]
        == "reactor-migration-dress-rehearsal stderr\nreactor-dress-api-smoke stderr"
    )


def test_run_release_smoke_plan_fails_when_supporting_report_does_not_pass(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "readiness.json"
    api_smoke = tmp_path / "api-smoke.json"
    readiness.write_text(json.dumps({"ok": True}), encoding="utf-8")
    api_smoke.write_text(json.dumps({"ok": False, "error": "api not ready"}), encoding="utf-8")
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "full_backup_db_api_dress_rehearsal",
                "mode": "automated",
                "evidence_scope": "dress_rehearsal",
                "release_gate_closer": True,
                "evidence_uri": "reports/full-backup-db-api-dress-rehearsal.json",
                "command": ["uv", "run", "reactor-migration-dress-rehearsal"],
                "commands": [
                    ["uv", "run", "reactor-migration-dress-rehearsal"],
                    ["uv", "run", "reactor-dress-api-smoke"],
                ],
                "report_paths": [str(readiness), str(api_smoke)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        return CommandResult(
            exit_code=0,
            duration_ms=timeout_seconds,
            stdout=f"{command[2]} stdout",
            stderr="",
        )

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    assert report["ok"] is False
    steps = cast(list[dict[str, object]], report["steps"])
    assert steps[0]["status"] == "failed"
    assert steps[0]["exit_code"] == 1
    assert steps[0]["report_paths"] == [str(readiness), str(api_smoke)]
    assert steps[0]["stderr"] == f"supporting report failed: {api_smoke}: api not ready"


def test_release_smoke_run_includes_plan_readiness_reports(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    evidence_path = tmp_path / "release-evidence.json"
    readiness_path = tmp_path / "release-readiness.json"
    api_smoke = tmp_path / "api-smoke.json"
    api_smoke.write_text(json.dumps(api_smoke_passed_report()), encoding="utf-8")
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "full_backup_db_api_dress_rehearsal",
                        "mode": "automated",
                        "evidence_scope": "dress_rehearsal",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/full-backup-db-api-dress-rehearsal.json",
                        "command": ["uv", "run", "reactor-migration-dress-rehearsal"],
                        "report_paths": [str(api_smoke)],
                        "readiness_reports": [
                            {
                                "name": "dress_api_smoke",
                                "path": str(api_smoke),
                                "required": True,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--verified-at",
            "2026-07-04T00:00:00Z",
            "--evidence-output",
            str(evidence_path),
            "--readiness-output",
            str(readiness_path),
        ]
    )

    assert exit_code == 0
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["ok"] is True
    assert readiness["requiredReports"] == [
        "smoke_run",
        "release_evidence",
        "dress_api_smoke",
    ]
    assert readiness["missingReports"] == []
    items = {item["name"]: item for item in readiness["items"]}
    assert items["dress_api_smoke"]["apiBoundary"]["nextActionSchemas"] == [
        "FeedbackNextAction",
        "RagIngestionCandidateNextAction",
        "MemoryNextAction",
        "RunOperatorNextAction",
    ]
    assert "candidateTag" in items["dress_api_smoke"]["apiBoundary"]["nextActionSchemaFields"]
    assert items["dress_api_smoke"]["apiBoundary"]["runOperatorNextActionSchemaFields"] == [
        "approvalId",
        "checkpointId",
        "checkpointNs",
        "command",
        "id",
        "label",
        "sourceRunId",
        "threadId",
    ]


def test_release_smoke_run_readiness_output_handles_missing_plan_report(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    evidence_path = tmp_path / "release-evidence.json"
    readiness_path = tmp_path / "release-readiness.json"
    missing_api_smoke = tmp_path / "missing-api-smoke.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "full_backup_db_api_dress_rehearsal",
                        "mode": "automated",
                        "evidence_scope": "dress_rehearsal",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/full-backup-db-api-dress-rehearsal.json",
                        "command": ["uv", "run", "reactor-migration-dress-rehearsal"],
                        "readiness_reports": [
                            {
                                "name": "dress_api_smoke",
                                "path": str(missing_api_smoke),
                                "required": True,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--verified-at",
            "2026-07-05T00:00:00Z",
            "--evidence-output",
            str(evidence_path),
            "--readiness-output",
            str(readiness_path),
        ]
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "Traceback" not in stderr
    assert "missingReports=dress_api_smoke" in stderr
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["ok"] is False
    assert readiness["status"] == "blocked"
    assert readiness["requiredReports"] == [
        "smoke_run",
        "release_evidence",
        "dress_api_smoke",
    ]
    assert readiness["missingReports"] == ["dress_api_smoke"]
    items = {item["name"]: item for item in readiness["items"]}
    assert items["dress_api_smoke"]["status"] == "skipped"
    assert items["dress_api_smoke"]["failure"] == "required report missing"


def test_release_smoke_run_readiness_output_handles_malformed_plan_report(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    evidence_path = tmp_path / "release-evidence.json"
    readiness_path = tmp_path / "release-readiness.json"
    malformed_api_smoke = tmp_path / "malformed-api-smoke.json"
    malformed_api_smoke.write_text("{", encoding="utf-8")
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "full_backup_db_api_dress_rehearsal",
                        "mode": "automated",
                        "evidence_scope": "dress_rehearsal",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/full-backup-db-api-dress-rehearsal.json",
                        "command": ["uv", "run", "reactor-migration-dress-rehearsal"],
                        "readiness_reports": [
                            {
                                "name": "dress_api_smoke",
                                "path": str(malformed_api_smoke),
                                "required": True,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--verified-at",
            "2026-07-05T00:00:00Z",
            "--evidence-output",
            str(evidence_path),
            "--readiness-output",
            str(readiness_path),
        ]
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "Traceback" not in stderr
    assert "failure=readiness report unreadable" in stderr
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["ok"] is False
    assert readiness["status"] == "failed"
    assert readiness["requiredReports"] == [
        "smoke_run",
        "release_evidence",
        "dress_api_smoke",
    ]
    assert readiness["missingReports"] == []
    items = {item["name"]: item for item in readiness["items"]}
    assert items["dress_api_smoke"]["status"] == "failed"
    assert str(items["dress_api_smoke"]["failure"]).startswith("readiness report unreadable:")
    assert items["dress_api_smoke"]["artifact"] == str(malformed_api_smoke)


def test_release_smoke_run_surfaces_skipped_api_smoke_next_action(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    evidence_path = tmp_path / "release-evidence.json"
    readiness_path = tmp_path / "release-readiness.json"
    api_smoke = tmp_path / "api-smoke.json"
    api_smoke.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "skipped",
                "scope": "dress_rehearsal",
                "error": "missing required API smoke environment",
                "nextActions": [
                    {
                        "id": "configure_api_smoke_env",
                        "label": "Configure API smoke environment",
                        "command": (
                            "REACTOR_API_BASE_URL=<api-url> "
                            "REACTOR_API_KEY=<api-key> "
                            "uv run reactor-dress-api-smoke --output "
                            "reports/full-backup-db-api-dress-rehearsal.json"
                        ),
                        "requiredEnv": ["REACTOR_API_BASE_URL", "REACTOR_API_KEY"],
                        "missingEnv": ["REACTOR_API_BASE_URL", "REACTOR_API_KEY"],
                        "reportFile": "reports/full-backup-db-api-dress-rehearsal.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "full_backup_db_api_dress_rehearsal",
                        "mode": "automated",
                        "evidence_scope": "dress_rehearsal",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/full-backup-db-api-dress-rehearsal.json",
                        "command": ["uv", "run", "reactor-migration-dress-rehearsal"],
                        "readiness_reports": [
                            {
                                "name": "dress_api_smoke",
                                "path": str(api_smoke),
                                "required": True,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--verified-at",
            "2026-07-05T00:00:00Z",
            "--evidence-output",
            str(evidence_path),
            "--readiness-output",
            str(readiness_path),
        ]
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "nextActions=configure_api_smoke_env" in stderr
    assert (
        "nextAction.configure_api_smoke_env.requiredEnv=REACTOR_API_BASE_URL,REACTOR_API_KEY"
    ) in stderr
    assert (
        "nextAction.configure_api_smoke_env.missingEnv=REACTOR_API_BASE_URL,REACTOR_API_KEY"
    ) in stderr
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    tag_recommendation = cast(dict[str, object], readiness["tagRecommendation"])
    assert tag_recommendation["nextActionId"] == "configure_api_smoke_env"


def test_release_smoke_run_readiness_output_handles_duplicate_plan_report_name(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    evidence_path = tmp_path / "release-evidence.json"
    readiness_path = tmp_path / "release-readiness.json"
    api_smoke = tmp_path / "api-smoke.json"
    langsmith = tmp_path / "langsmith.json"
    api_smoke.write_text(
        json.dumps({"ok": True, "status": "passed", "scope": "dress_rehearsal"}),
        encoding="utf-8",
    )
    langsmith.write_text(
        json.dumps(
            {
                "ok": True,
                "status": "passed",
                "scope": "langsmith_eval_dataset_sync",
                "evidence": valid_langsmith_eval_sync_evidence(artifact=str(langsmith)),
            }
        ),
        encoding="utf-8",
    )
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "full_backup_db_api_dress_rehearsal",
                        "mode": "automated",
                        "evidence_scope": "dress_rehearsal",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/full-backup-db-api-dress-rehearsal.json",
                        "command": ["uv", "run", "reactor-migration-dress-rehearsal"],
                        "readiness_reports": [
                            {
                                "name": "dress_api_smoke",
                                "path": str(api_smoke),
                                "required": True,
                            },
                            {
                                "name": "dress_api_smoke",
                                "path": str(api_smoke),
                                "required": True,
                            },
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--verified-at",
            "2026-07-05T00:00:00Z",
            "--evidence-output",
            str(evidence_path),
            "--readiness-output",
            str(readiness_path),
            "--readiness-report",
            f"langsmith_eval_sync={langsmith}",
        ]
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "Traceback" not in stderr
    assert "failure=invalid readiness report configuration" in stderr
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["ok"] is False
    assert readiness["status"] == "failed"
    assert readiness["requiredReports"] == [
        "smoke_run",
        "release_evidence",
        "langsmith_eval_sync",
        "readiness_report_config",
    ]
    assert readiness["missingReports"] == []
    items = {item["name"]: item for item in readiness["items"]}
    assert items["langsmith_eval_sync"]["status"] == "passed"
    assert items["langsmith_eval_sync"]["artifact"] == str(langsmith)
    assert items["readiness_report_config"]["status"] == "failed"
    assert items["readiness_report_config"]["failure"] == (
        "invalid readiness report configuration: "
        "duplicate plan readiness report name: dress_api_smoke"
    )
    assert items["readiness_report_config"]["artifact"] == str(plan_path)


def test_release_smoke_run_readiness_output_preserves_plan_reports_on_extra_config_error(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "smoke-plan.json"
    report_path = tmp_path / "smoke-run.json"
    evidence_path = tmp_path / "release-evidence.json"
    readiness_path = tmp_path / "release-readiness.json"
    api_smoke = tmp_path / "api-smoke.json"
    api_smoke.write_text(json.dumps(api_smoke_passed_report()), encoding="utf-8")
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "full_backup_db_api_dress_rehearsal",
                        "mode": "automated",
                        "evidence_scope": "dress_rehearsal",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/full-backup-db-api-dress-rehearsal.json",
                        "command": ["uv", "run", "reactor-migration-dress-rehearsal"],
                        "readiness_reports": [
                            {
                                "name": "dress_api_smoke",
                                "path": str(api_smoke),
                                "required": True,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_command(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    monkeypatch.setattr("reactor.release.smoke_plan.run_command", fake_run_command)

    from reactor.release.smoke_plan import run_main

    exit_code = run_main(
        [
            "--plan",
            str(plan_path),
            "--report-file",
            str(report_path),
            "--verified-at",
            "2026-07-05T00:00:00Z",
            "--evidence-output",
            str(evidence_path),
            "--readiness-output",
            str(readiness_path),
            "--readiness-report",
            "malformed-readiness-report",
        ]
    )

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "Traceback" not in stderr
    assert "failure=invalid readiness report configuration" in stderr
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["ok"] is False
    assert readiness["status"] == "failed"
    assert readiness["requiredReports"] == [
        "smoke_run",
        "release_evidence",
        "dress_api_smoke",
        "readiness_report_config",
    ]
    assert readiness["missingReports"] == []
    items = {item["name"]: item for item in readiness["items"]}
    assert items["dress_api_smoke"]["status"] == "passed"
    assert items["dress_api_smoke"]["artifact"] == "reports/full-backup-db-api-dress-rehearsal.json"
    assert items["dress_api_smoke"]["apiBoundary"]["framework"] == "FastAPI"
    assert items["readiness_report_config"]["status"] == "failed"
    assert items["readiness_report_config"]["failure"] == (
        "invalid readiness report configuration: --readiness-report must use name=path"
    )


def test_run_release_smoke_plan_surfaces_readiness_item_failure(tmp_path: Path) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "failed",
                "tagRecommendation": {
                    "status": "defer",
                    "eligible": False,
                    "recommendedVersionBump": "none",
                    "recommendedTagPattern": "none",
                    "minorEligible": False,
                    "minorBlockedReason": "no passed product capability boundary evidence",
                    "blockingReports": ["langsmith_eval_sync"],
                    "nextAction": (
                        "resolve blocked/skipped release readiness reports before tagging"
                    ),
                },
                "items": [
                    {
                        "name": "langsmith_eval_sync",
                        "status": "failed",
                        "failure": "feedback loop promotion evidence missing",
                        "feedbackPromotion": {
                            "caseIds": ["rag-poisoning-retrieval-is-labeled"],
                            "feedbackIds": ["fb_rag_1"],
                            "feedbackReviewIds": ["fb_rag_1"],
                            "feedbackRatingCounts": {"thumbs_down": 1},
                            "feedbackSourceCounts": {"slack_button": 1},
                            "workflowTagCounts": {"documents-ask": 1, "rag": 1},
                            "reviewAction": (
                                "reactor-admin feedback --feedback-id fb_rag_1 --output table"
                            ),
                            "bulkReviewAction": (
                                "reactor-admin feedback-bulk-review --case-id "
                                "rag-poisoning-retrieval-is-labeled --status done "
                                "--tag promoted --tag langsmith "
                                "--note 'Promoted to regression eval and reviewed in "
                                "hardening/LangSmith. Required readiness reports: "  # noqa: E501
                                "hardening_suite, langsmith_eval_sync.' "
                                "--output table"
                            ),
                        },
                        "sourceRunIds": ["run_rag_poisoning"],
                        "caseSourceRunIds": {
                            "rag-poisoning-retrieval-is-labeled": "run_rag_poisoning"
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    assert steps[0]["status"] == "failed"
    assert steps[0]["stderr"] == (
        f"supporting report failed: {readiness}: "
        "failed: langsmith_eval_sync: feedback loop promotion evidence missing "
        "feedbackReviewIds=fb_rag_1 "
        "feedbackRatings=thumbs_down=1 "
        "feedbackSources=slack_button=1 "
        "feedbackWorkflows=documents-ask=1,rag=1 "
        'tagRecommendation="status=defer eligible=false '
        "recommendedVersionBump=none recommendedTagPattern=none minorEligible=false "
        "blockingReports=langsmith_eval_sync "
        "minorBlockedReason='no passed product capability boundary evidence' "
        'nextAction=\\"resolve blocked/skipped release readiness reports before tagging\\"" '
        "sourceRunIds=1 "
        "caseSourceRunMappings=1 "
        "reviewAction='reactor-admin feedback --feedback-id fb_rag_1 --output table' "
        'feedbackBulkReviewAction="reactor-admin feedback-bulk-review --case-id '
        "rag-poisoning-retrieval-is-labeled --status done --tag promoted "
        "--tag langsmith "
        "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
        '--output table"'
    )


def test_run_release_smoke_plan_surfaces_tag_warning_review_fields(tmp_path: Path) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "failed",
                "tagRecommendation": {
                    "status": "eligible_with_warnings",
                    "eligible": True,
                    "recommendedVersionBump": "patch",
                    "recommendedTagPattern": "v1.0.x",
                    "minorEligible": False,
                    "passedReports": ["hardening_suite"],
                    "warningReports": ["hardening_suite"],
                    "warningReviewRequired": True,
                    "nextAction": (
                        "review release readiness warnings, then verify clean worktree "
                        "and choose the next patch version tag"
                    ),
                },
                "items": [
                    {
                        "name": "hardening_suite",
                        "status": "failed",
                        "failure": "operator review required",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert "tagRecommendation=" in stderr
    assert "status=eligible_with_warnings eligible=true" in stderr
    assert "passedReports=hardening_suite" in stderr
    assert "warningReports=hardening_suite" in stderr
    assert "warningReviewRequired=true" in stderr
    assert (
        'nextAction="review release readiness warnings, then verify clean worktree '
        'and choose the next patch version tag"'
    ) in stderr


def test_run_release_smoke_plan_surfaces_tag_recommendation_action_identity(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "blocked",
                "tagRecommendation": {
                    "status": "defer",
                    "eligible": False,
                    "recommendedVersionBump": "none",
                    "recommendedTagPattern": "none",
                    "minorEligible": False,
                    "blockingReports": ["langsmith_eval_sync"],
                    "nextAction": "run nextAction.review-done before tagging",
                    "nextActionId": "review-done",
                    "nextActionCommand": (
                        "reactor-admin feedback-review fb_rag_candidate --if-match 2 "
                        "--status done --tag promoted --tag langsmith --output table"
                    ),
                    "nextActionEnvFileCommand": (
                        "reactor-admin feedback-review fb_rag_candidate --if-match 2 "
                        "--status done --tag promoted --tag langsmith --output table "
                        "--env-file reports/release/release-smoke-preflight.local.env"
                    ),
                    "feedbackId": "fb_rag_candidate",
                    "evalCaseId": "case_rag_candidate_c1",
                    "sourceRunId": "run_rag_candidate_c1",
                    "feedbackTags": [
                        "feedback:fb_rag_candidate",
                        "feedback-rating:thumbs_down",
                        "rag",
                        "grounding",
                    ],
                    "workflowTags": ["rag", "grounding"],
                },
                "items": [
                    {
                        "name": "langsmith_eval_sync",
                        "status": "blocked",
                        "failure": "feedback_review_required",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert "nextActionId=review-done" in stderr
    assert (
        "nextActionCommand='reactor-admin feedback-review fb_rag_candidate --if-match 2 "
        "--status done --tag promoted --tag langsmith --output table'"
    ) in stderr
    assert (
        "nextActionEnvFileCommand='reactor-admin feedback-review fb_rag_candidate --if-match 2 "
        "--status done --tag promoted --tag langsmith --output table "
        "--env-file reports/release/release-smoke-preflight.local.env'"
    ) in stderr
    assert "feedbackId='fb_rag_candidate'" in stderr
    assert "evalCaseId='case_rag_candidate_c1'" in stderr
    assert "sourceRunId='run_rag_candidate_c1'" in stderr
    assert "feedbackTags=feedback:fb_rag_candidate,feedback-rating:thumbs_down,rag,grounding" in (
        stderr
    )
    assert "workflowTags=rag,grounding" in stderr


def test_run_release_smoke_plan_surfaces_tag_env_handoff_fields(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "blocked",
                "tagRecommendation": {
                    "status": "defer",
                    "eligible": False,
                    "recommendedVersionBump": "none",
                    "recommendedTagPattern": "none",
                    "minorEligible": False,
                    "blockingReports": [
                        "smoke_run",
                        "release_evidence",
                        "langsmith_eval_sync",
                    ],
                    "rootBlockingReports": ["smoke_run", "langsmith_eval_sync"],
                    "downstreamBlockedReports": ["release_evidence"],
                    "nextAction": "set release smoke preflight environment before tagging",
                    "missingEnv": ["OPENAI_API_KEY", "REACTOR_A2A_API_KEY"],
                    "missingEnvAnyOf": [
                        "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
                    ],
                    "preflightFile": "reports/release/release-smoke-preflight.local.json",
                    "preflightEnvTemplate": ("reports/release/release-smoke-preflight.local.env"),
                    "remediationCommand": (
                        "uv run reactor-release-smoke-run "
                        "--plan reports/release/release-smoke-plan.local.json "
                        "--env-file "
                        "reports/release/release-smoke-preflight.local.env "
                        "--preflight-only"
                    ),
                    "blockingNextActions": [
                        {
                            "report": "smoke_run",
                            "nextAction": "set release smoke preflight environment before tagging",
                            "preflightEnvFileCommand": (
                                "uv run reactor-release-smoke-run "
                                "--plan reports/release/release-smoke-plan.local.json "
                                "--env-file reports/release/release-smoke-preflight.local.env "
                                "--preflight-only"
                            ),
                        },
                        {
                            "report": "langsmith_eval_sync",
                            "nextActionId": "preflight-langsmith",
                            "readyNextActionIds": ["preflight-langsmith"],
                            "blockedNextActionIds": ["sync-langsmith"],
                            "nextActionStates": {
                                "preflight-langsmith": "ready",
                                "sync-langsmith": "blocked",
                            },
                            "nextActionCommand": (
                                "uv run reactor-langsmith-eval-sync "
                                "--suite-file evals/regression/rag-ingestion-candidate.json "
                                "--dataset-name reactor-rag-ingestion-candidate "
                                "--preflight-only --output table"
                            ),
                            "requiredReviewNote": (
                                "Promoted to regression eval and reviewed in hardening/LangSmith. "
                                "Required readiness reports: hardening_suite, langsmith_eval_sync."
                            ),
                            "missingEnvAnyOf": [
                                "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
                            ],
                        },
                    ],
                },
                "items": [
                    {
                        "name": "smoke_run",
                        "status": "blocked",
                        "failure": "release smoke run blocked by missing environment",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert "rootBlockingReports=smoke_run,langsmith_eval_sync" in stderr
    assert "blockingNextActions=smoke_run,langsmith_eval_sync" in stderr
    assert (
        "blockingNextAction.smoke_run.nextAction="
        "'set release smoke preflight environment before tagging'"
    ) in stderr
    assert (
        "blockingNextAction.smoke_run.preflightEnvFileCommand="
        "'uv run reactor-release-smoke-run --plan reports/release/release-smoke-plan.local.json "
        "--env-file reports/release/release-smoke-preflight.local.env --preflight-only'"
    ) in stderr
    assert "blockingNextAction.langsmith_eval_sync.nextActionId=preflight-langsmith" in stderr
    assert "blockingNextAction.langsmith_eval_sync.readyNextActionIds=preflight-langsmith" in stderr
    assert "blockingNextAction.langsmith_eval_sync.blockedNextActionIds=sync-langsmith" in stderr
    assert (
        "blockingNextAction.langsmith_eval_sync.nextActionStates="
        "preflight-langsmith=ready,sync-langsmith=blocked"
    ) in stderr
    assert (
        "blockingNextAction.langsmith_eval_sync.nextActionCommand="
        "'uv run reactor-langsmith-eval-sync "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate --preflight-only --output table'"
    ) in stderr
    assert (
        "blockingNextAction.langsmith_eval_sync.requiredReviewNote="
        "'Promoted to regression eval and reviewed in hardening/LangSmith. "
        "Required readiness reports: hardening_suite, langsmith_eval_sync.'"
    ) in stderr
    assert "downstreamBlockedReports=release_evidence" in stderr
    assert "missingEnv=OPENAI_API_KEY,REACTOR_A2A_API_KEY" in stderr
    assert ("missingEnvAnyOf=LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY") in stderr
    assert ("preflightFile='reports/release/release-smoke-preflight.local.json'") in stderr
    assert ("preflightEnvTemplate='reports/release/release-smoke-preflight.local.env'") in stderr
    assert (
        "remediationCommand='uv run reactor-release-smoke-run "
        "--plan reports/release/release-smoke-plan.local.json "
        "--env-file reports/release/release-smoke-preflight.local.env "
        "--preflight-only'"
    ) in stderr


def test_run_release_smoke_plan_surfaces_tag_readiness_handoff_fields(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "blocked",
                "tagRecommendation": {
                    "status": "defer",
                    "eligible": False,
                    "recommendedVersionBump": "none",
                    "recommendedTagPattern": "none",
                    "minorEligible": False,
                    "blockingReports": ["langsmith_eval_sync"],
                    "nextAction": "run nextAction.sync-langsmith before tagging",
                    "nextActionId": "sync-langsmith",
                    "readyNextActionIds": ["sync-langsmith"],
                    "blockedNextActionIds": ["refresh-release-readiness"],
                    "nextActionCommand": (
                        "uv run reactor-langsmith-eval-sync "
                        "--suite-file evals/regression/rag-ingestion-candidate.json "
                        "--dataset-name reactor-rag-ingestion-candidate "
                        "--report-file reports/langsmith-rag-candidate.json"
                    ),
                    "releaseReadinessCommand": (
                        "uv run reactor-release-smoke-run --readiness-output "
                        "reports/release-readiness.json --required-readiness-report "
                        "langsmith_eval_sync"
                    ),
                    "readinessReportArg": (
                        "--readiness-report "
                        "langsmith_eval_sync=reports/langsmith-rag-candidate.json"
                    ),
                    "requiredReadinessReports": ["langsmith_eval_sync"],
                    "readinessReports": {
                        "langsmith_eval_sync": "reports/langsmith-rag-candidate.json"
                    },
                    "requiredEnvAnyOf": [
                        ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                    ],
                    "blockingEnvActionId": "preflight-langsmith",
                    "blockingMissingEnvAnyOf": [
                        "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
                    ],
                    "blockingRequiredEnvAnyOf": [
                        ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                    ],
                    "blockingRecommendedEnv": ["LANGSMITH_ENDPOINT"],
                },
                "items": [
                    {
                        "name": "langsmith_eval_sync",
                        "status": "blocked",
                        "failure": "langsmith_auth_failed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert (
        "releaseReadinessCommand='uv run reactor-release-smoke-run --readiness-output "
        "reports/release-readiness.json --required-readiness-report langsmith_eval_sync'"
    ) in stderr
    assert (
        "readinessReportArg='--readiness-report "
        "langsmith_eval_sync=reports/langsmith-rag-candidate.json'"
    ) in stderr
    assert "requiredReadinessReports=langsmith_eval_sync" in stderr
    assert "readyNextActionIds=sync-langsmith" in stderr
    assert "blockedNextActionIds=refresh-release-readiness" in stderr
    assert "readinessReports=langsmith_eval_sync=reports/langsmith-rag-candidate.json" in stderr
    assert (
        "requiredEnvAnyOf.0=LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    ) in stderr
    assert "blockingEnvActionId=preflight-langsmith" in stderr
    assert (
        "blockingRequiredEnvAnyOf.0=LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    ) in stderr
    assert (
        "blockingMissingEnvAnyOf=LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    ) in stderr
    assert "blockingRecommendedEnv=LANGSMITH_ENDPOINT" in stderr


def test_run_release_smoke_plan_surfaces_langsmith_release_gate_remediation(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "blocked",
                "tagRecommendation": {
                    "status": "defer",
                    "eligible": False,
                    "recommendedVersionBump": "none",
                    "recommendedTagPattern": "none",
                    "minorEligible": False,
                    "blockingReports": ["langsmith_eval_sync"],
                    "nextAction": (
                        "resolve blocked/skipped release readiness reports before tagging"
                    ),
                },
                "items": [
                    {
                        "name": "langsmith_eval_sync",
                        "status": "blocked",
                        "failure": "langsmith_auth_failed",
                        "requiredEnvAnyOf": [
                            ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                        ],
                        "recommendedEnv": ["LANGSMITH_ENDPOINT"],
                        "releaseGate": {
                            "status": "blocked",
                            "reason": "langsmith_auth_failed",
                            "requiredReport": "langsmith_eval_sync",
                            "remediation": [
                                "set_langsmith_api_key",
                                "rerun_reactor_langsmith_eval_sync",
                                "include_passed_langsmith_eval_sync_report_in_release_readiness",
                            ],
                            "remediationCommand": (
                                "uv run reactor-langsmith-eval-sync "
                                "--suite-file evals/regression/rag-ingestion-candidate.json"
                            ),
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert (
        "tagRecommendation='status=defer eligible=false "
        "recommendedVersionBump=none recommendedTagPattern=none minorEligible=false "
        "blockingReports=langsmith_eval_sync "
        'nextAction="resolve blocked/skipped release readiness reports before tagging"\''
    ) in stderr
    assert "releaseGate=blocked" in stderr
    assert "gateReason=langsmith_auth_failed" in stderr
    assert "releaseNext=set_langsmith_api_key" in stderr
    assert (
        "releasePlan=set_langsmith_api_key,"
        "rerun_reactor_langsmith_eval_sync,"
        "include_passed_langsmith_eval_sync_report_in_release_readiness"
    ) in stderr
    assert (
        "requiredEnvAnyOf.0=LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    ) in stderr
    assert "recommendedEnv=LANGSMITH_ENDPOINT" in stderr
    assert (
        "releaseGateRemediationCommand='uv run reactor-langsmith-eval-sync "
        "--suite-file evals/regression/rag-ingestion-candidate.json'"
    ) in stderr


def test_run_release_smoke_plan_surfaces_product_boundary_gap(tmp_path: Path) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "blocked",
                "tagRecommendation": {
                    "status": "defer",
                    "eligible": False,
                    "recommendedVersionBump": "none",
                    "minorEligible": False,
                    "blockingReports": ["langsmith_eval_sync"],
                    "minorBlockedReports": ["langsmith_eval_sync"],
                    "minorBoundaryMissingEvidence": [
                        "eval_promotion_apply_coverage.requiredContextDiagnostics"
                    ],
                    "minorBoundaryRemediationCommand": (
                        "reactor-runs promote-eval run_c1 "
                        "--case-id case_rag_candidate_c1 "
                        "--apply-suite-file evals/regression/rag-ingestion-candidate.json "
                        "--apply-dry-run --output table"
                    ),
                    "nextAction": (
                        "resolve blocked/skipped release readiness reports before tagging"
                    ),
                },
                "items": [
                    {
                        "name": "langsmith_eval_sync",
                        "status": "skipped",
                        "failure": "dry_run_only",
                        "productCapabilityBoundary": {
                            "minorEligible": False,
                            "capability": "rag_ingest_to_feedback_eval_langsmith_readiness",
                            "evidence": [
                                "rag_ingestion_lifecycle",
                                "rag_ingestion_candidate_feedback_queue",
                                "langsmith_trace_grading",
                                "release_readiness_command",
                            ],
                            "missingEvidence": [
                                "eval_promotion_apply_coverage.requiredContextDiagnostics"
                            ],
                        },
                        "productBoundaryResolvedEvidence": ["rag_ingestion_lifecycle"],
                        "productBoundaryResolvedByReports": {
                            "rag_ingestion_lifecycle": "hardening_suite"
                        },
                        "ragCandidateEvalApplyAction": (
                            "reactor-runs promote-eval run_c1 "
                            "--case-id case_rag_candidate_c1 "
                            "--apply-suite-file evals/regression/rag-ingestion-candidate.json "
                            "--apply-dry-run --output table"
                        ),
                        "productBoundaryReadinessCommand": (
                            "uv run reactor-release-smoke-run "
                            "--required-readiness-report hardening_suite "
                            "--required-readiness-report langsmith_eval_sync"
                        ),
                        "requiredReadinessReports": [
                            "hardening_suite",
                            "langsmith_eval_sync",
                        ],
                        "readinessReportArg": (
                            "--readiness-report "
                            "hardening_suite=reports/hardening-suite.json "
                            "--readiness-report "
                            "langsmith_eval_sync=reports/langsmith-rag-candidate.json"
                        ),
                        "readinessReports": {
                            "hardening_suite": "reports/hardening-suite.json",
                            "langsmith_eval_sync": "reports/langsmith-rag-candidate.json",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert "productCapability=rag_ingest_to_feedback_eval_langsmith_readiness" in stderr
    assert "productBoundaryMinorEligible=false" in stderr
    assert (
        "productBoundaryEvidence=rag_ingestion_lifecycle,"
        "rag_ingestion_candidate_feedback_queue,"
        "langsmith_trace_grading,release_readiness_command"
    ) in stderr
    assert "productBoundaryResolved=rag_ingestion_lifecycle" in stderr
    assert "productBoundaryResolvedBy.rag_ingestion_lifecycle=hardening_suite" in stderr
    assert (
        "minorBoundaryRemediationCommand='reactor-runs promote-eval run_c1 "
        "--case-id case_rag_candidate_c1 "
        "--apply-suite-file evals/regression/rag-ingestion-candidate.json "
        "--output table'"
    ) in stderr
    assert (
        "minorBoundaryRemediationCommand='reactor-runs promote-eval run_c1 "
        "--case-id case_rag_candidate_c1 "
        "--apply-suite-file evals/regression/rag-ingestion-candidate.json "
        "--apply-dry-run"
    ) not in stderr
    assert (
        "productBoundaryMissing=eval_promotion_apply_coverage.requiredContextDiagnostics" in stderr
    )
    assert (
        "productBoundaryRemediationAction='reactor-runs promote-eval run_c1 "
        "--case-id case_rag_candidate_c1 "
        "--apply-suite-file evals/regression/rag-ingestion-candidate.json "
        "--output table'"
    ) in stderr
    assert (
        "productBoundaryRemediationAction='reactor-runs promote-eval run_c1 "
        "--case-id case_rag_candidate_c1 "
        "--apply-suite-file evals/regression/rag-ingestion-candidate.json "
        "--apply-dry-run"
    ) not in stderr
    assert (
        "productBoundaryReadinessCommand='uv run reactor-release-smoke-run "
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync'"
    ) in stderr
    assert "requiredReadinessReports=hardening_suite,langsmith_eval_sync" in stderr
    assert (
        "readinessReportArg='--readiness-report "
        "hardening_suite=reports/hardening-suite.json --readiness-report "
        "langsmith_eval_sync=reports/langsmith-rag-candidate.json'"
    ) in stderr
    assert (
        "readinessReports=hardening_suite=reports/hardening-suite.json,"
        "langsmith_eval_sync=reports/langsmith-rag-candidate.json"
    ) in stderr


def test_run_release_smoke_plan_surfaces_hardening_lifecycle_remediation(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "blocked",
                "items": [
                    {
                        "name": "langsmith_eval_sync",
                        "status": "skipped",
                        "failure": "dry_run_only",
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
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert "productBoundaryMissing=rag_ingestion_lifecycle" in stderr
    assert (
        "productBoundaryRemediationAction='uv run reactor-hardening-suite "
        "--report-file reports/hardening-suite.json'"
    ) in stderr


def test_run_release_smoke_plan_surfaces_product_boundary_feedback_review_action(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "blocked",
                "items": [
                    {
                        "name": "langsmith_eval_sync",
                        "status": "skipped",
                        "failure": "dry_run_only",
                        "productCapabilityBoundary": {
                            "minorEligible": False,
                            "capability": "rag_ingest_to_feedback_eval_langsmith_readiness",
                            "evidence": ["rag_ingestion_candidate_feedback_queue"],
                            "missingEvidence": ["feedback_promotion.reviewed_feedback"],
                        },
                        "feedbackReviewQueue": {
                            "bulkReviewAction": (
                                "reactor-admin feedback-bulk-review --candidate-tag "
                                "rag-candidate:grounded_citation --source slack_button "
                                "--status done --tag promoted --tag langsmith --output table"
                            ),
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert (
        "productBoundaryFeedbackReviewAction='reactor-admin feedback-bulk-review "
        "--candidate-tag rag-candidate:grounded_citation --source slack_button "
        "--status done --tag promoted --tag langsmith --output table'"
    ) in stderr


def test_run_release_smoke_plan_surfaces_feedback_review_note_action(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "failed",
                "items": [
                    {
                        "name": "langsmith_eval_sync",
                        "status": "failed",
                        "failure": "langsmith eval sync contract missing",
                        "productCapabilityBoundary": {
                            "minorEligible": False,
                            "capability": "rag_ingest_to_feedback_eval_langsmith_readiness",
                            "evidence": ["rag_ingestion_candidate_feedback_queue"],
                            "missingEvidence": ["feedback_promotion.reviewNote"],
                        },
                        "feedbackReviewQueue": {
                            "bulkReviewAction": (
                                "reactor-admin feedback-bulk-review --candidate-tag "
                                "rag-candidate:grounded_citation --source slack_button "
                                "--status done --tag promoted --tag langsmith "
                                "--note 'Promoted to regression eval and reviewed in "
                                "hardening/LangSmith. Required readiness reports: "
                                "hardening_suite, langsmith_eval_sync.' --output table"
                            ),
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert (
        'productBoundaryFeedbackReviewAction="reactor-admin feedback-bulk-review '
        "--candidate-tag rag-candidate:grounded_citation --source slack_button "
        "--status done --tag promoted --tag langsmith "
        "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. "
        "Required readiness reports: hardening_suite, langsmith_eval_sync.' "
        '--output table"'
    ) in stderr


def test_run_release_smoke_plan_surfaces_citation_workflow_remediation_action(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "blocked",
                "items": [
                    {
                        "name": "langsmith_eval_sync",
                        "status": "skipped",
                        "failure": "dry_run_only",
                        "productCapabilityBoundary": {
                            "minorEligible": False,
                            "capability": "rag_ingest_to_feedback_eval_langsmith_readiness",
                            "evidence": ["rag_ingestion_candidate_feedback_queue"],
                            "missingEvidence": [
                                "context_manifest_diagnostics.citationWorkflowEvalCaseIds"
                            ],
                        },
                        "ragCandidateEvalApplyAction": (
                            "reactor-runs promote-eval run_c1 "
                            "--case-id case_rag_candidate_c1 "
                            "--apply-suite-file evals/regression/rag-ingestion-candidate.json "
                            "--apply-dry-run --output table"
                        ),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert (
        "productBoundaryMissing=context_manifest_diagnostics.citationWorkflowEvalCaseIds"
    ) in stderr
    assert (
        "productBoundaryRemediationAction='reactor-runs promote-eval run_c1 "
        "--case-id case_rag_candidate_c1 "
        "--apply-suite-file evals/regression/rag-ingestion-candidate.json "
        "--output table'"
    ) in stderr
    assert (
        "productBoundaryRemediationAction='reactor-runs promote-eval run_c1 "
        "--case-id case_rag_candidate_c1 "
        "--apply-suite-file evals/regression/rag-ingestion-candidate.json "
        "--apply-dry-run"
    ) not in stderr


def test_run_release_smoke_plan_surfaces_context_diagnostic_findings(tmp_path: Path) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "failed",
                "items": [
                    {
                        "name": "hardening_suite",
                        "status": "failed",
                        "failure": "context manifest diagnostics failed",
                        "contextManifestDiagnostics": {
                            "memoryStatusCounts": {"active": 1, "deleted": 1},
                            "findings": [
                                {
                                    "code": "unknown_memory_status_count",
                                    "section": "session_memory",
                                    "path": "metadata.status_counts.deleted",
                                    "status": "deleted",
                                }
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    assert "contextFindings=unknown_memory_status_count" in str(steps[0]["stderr"])


def test_run_release_smoke_plan_surfaces_stream_terminal_action_gap(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "failed",
                "items": [
                    {
                        "name": "hardening_suite",
                        "status": "failed",
                        "failure": "streaming event contract missing",
                        "streamingEventContract": {
                            "terminalNextActions": {
                                "includedInCompletedPayload": False,
                                "actionIds": ["diagnose-run"],
                                "commands": ["reactor-runs diagnose {run_id} --output table"],
                                "identityFields": ["sourceRunId", "threadId", "checkpointNs"],
                            }
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert "streamTerminalNextActions=missing_from_completed_payload" in stderr
    assert "streamTerminalActionIds=diagnose-run" in stderr
    assert ("streamTerminalCommands='reactor-runs diagnose {run_id} --output table'") in stderr
    assert "streamTerminalIdentityFields=sourceRunId,threadId,checkpointNs" in stderr


def test_run_release_smoke_plan_surfaces_invalid_memory_status_labels(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "failed",
                "items": [
                    {
                        "name": "langsmith_eval_sync",
                        "status": "failed",
                        "failure": "context manifest diagnostics contract missing",
                        "contextManifestDiagnostics": {
                            "memoryStatusCounts": {"active": 1, "deleted": 1},
                            "skippedMemoryStatusCounts": {"archived": 1},
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    assert "invalidMemoryStatusLabels=archived,deleted" in str(steps[0]["stderr"])


def test_run_release_smoke_plan_surfaces_langsmith_citation_workflow_metadata(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "failed",
                "items": [
                    {
                        "name": "langsmith_eval_sync",
                        "status": "failed",
                        "failure": "context manifest diagnostics contract missing",
                        "contextManifestDiagnostics": {
                            "citationWorkflowEvalCaseIds": ["case_rag_candidate_c1"],
                            "citationWorkflowTags": [
                                "collection:rag-ingestion-candidate",
                                "rag-candidate:c1",
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert "citationWorkflowEvalCaseIds=case_rag_candidate_c1" in stderr
    assert "citationWorkflowTags=collection:rag-ingestion-candidate,rag-candidate:c1" in stderr


def test_run_release_smoke_plan_quotes_feedback_actions_with_inner_single_quotes(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "failed",
                "items": [
                    {
                        "name": "langsmith_eval_sync",
                        "status": "failed",
                        "failure": "feedback loop promotion evidence missing",
                        "feedbackPromotion": {
                            "feedbackReviewIds": ["feedback/needs quoting"],
                            "reviewAction": (
                                "reactor-admin feedback --feedback-id "
                                "'feedback/needs quoting' --output table"
                            ),
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    assert (
        'reviewAction="reactor-admin feedback --feedback-id '
        "'feedback/needs quoting' --output table\""
    ) in str(steps[0]["stderr"])


def test_run_release_smoke_plan_surfaces_multiple_feedback_review_actions(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "failed",
                "items": [
                    {
                        "name": "langsmith_eval_sync",
                        "status": "failed",
                        "failure": "feedback loop promotion evidence missing",
                        "feedbackPromotion": {
                            "caseIds": ["rag-poisoning-retrieval-is-labeled"],
                            "feedbackIds": ["fb_rag_1", "fb_rag_2"],
                            "feedbackReviewIds": ["fb_rag_1", "fb_rag_2"],
                            "feedbackRatingCounts": {"thumbs_down": 2},
                            "workflowTagCounts": {"documents-ask": 1, "rag": 1},
                            "reviewActions": [
                                "reactor-admin feedback --feedback-id fb_rag_1 --output table",
                                "reactor-admin feedback --feedback-id fb_rag_2 --output table",
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert "reviewActions='reactor-admin feedback --feedback-id fb_rag_1 --output table; " in stderr
    assert "reactor-admin feedback --feedback-id fb_rag_2 --output table'" in stderr


def test_run_release_smoke_plan_surfaces_feedback_review_queue(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "failed",
                "items": [
                    {
                        "name": "langsmith_eval_sync",
                        "status": "failed",
                        "failure": "langsmith eval sync contract missing",
                        "datasetName": "reactor-regression",
                        "sourceSuite": "evals/regression/rag-ingestion-candidate.json",
                        "liveSyncCommand": (
                            "uv run reactor-langsmith-eval-sync "
                            "--suite-file evals/regression/rag-ingestion-candidate.json "
                            "--dataset-name reactor-rag-ingestion-candidate "
                            "--report-file artifacts/langsmith/rag-ingestion-candidate-c1.json"
                        ),
                        "readinessCommand": (
                            "uv run reactor-release-smoke-run "
                            "--plan reports/release/release-smoke-plan.local.json "
                            "--report-file reports/release-smoke-run.json "
                            "--evidence-output reports/release-evidence.json "
                            "--verified-at $(date -u +%Y-%m-%dT%H:%M:%SZ) "
                            "--latest-tag $(git describe --tags --abbrev=0) "
                            "--readiness-output reports/release-readiness.json "
                            "--required-readiness-report hardening_suite "
                            "--required-readiness-report langsmith_eval_sync "
                            "--readiness-report hardening_suite=reports/hardening-suite.json "
                            "--readiness-report "
                            "langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate-c1.json"
                        ),
                        "nextActions": [
                            {
                                "id": "review-rag-candidate-c1",
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
                                "id": "sync-langsmith",
                                "command": (
                                    "uv run reactor-langsmith-eval-sync "
                                    "--suite-file evals/regression/rag-ingestion-candidate.json "
                                    "--dataset-name reactor-rag-ingestion-candidate "
                                    "--report-file artifacts/langsmith/"
                                    "rag-ingestion-candidate-c1.json"
                                ),
                                "readinessReportArg": (
                                    "--readiness-report "
                                    "hardening_suite=reports/hardening-suite.json "
                                    "--readiness-report "
                                    "langsmith_eval_sync=artifacts/langsmith/"
                                    "rag-ingestion-candidate-c1.json"
                                ),
                                "requiredEnvAnyOf": [
                                    [
                                        "LANGSMITH_API_KEY",
                                        "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY",
                                    ]
                                ],
                                "requiredReadinessReports": [
                                    "hardening_suite",
                                    "langsmith_eval_sync",
                                ],
                                "readinessReports": {
                                    "hardening_suite": "reports/hardening-suite.json",
                                    "langsmith_eval_sync": (
                                        "artifacts/langsmith/rag-ingestion-candidate-c1.json"
                                    ),
                                },
                            },
                        ],
                        "feedbackReviewQueue": {
                            "caseIds": ["case-rag-candidate-c1"],
                            "feedbackRatingCounts": {"thumbs_down": 1},
                            "feedbackSourceCounts": {"slack_button": 1},
                            "workflowTagCounts": {
                                "collection:rag-ingestion-candidate": 1,
                                "expected-citation:doc_1": 1,
                                "rag": 1,
                            },
                            "expectedCitationCounts": {"doc_1": 1},
                            "reviewAction": (
                                "reactor-admin feedback --rating thumbs_down "
                                "--review-status inbox "
                                "--case-id case-rag-candidate-c1 "
                                "--tag collection:rag-ingestion-candidate --limit 10 --output table"
                            ),
                            "memoryLifecycleAction": MEMORY_LIFECYCLE_GATE_ACTION,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert "datasetName=reactor-regression" in stderr
    assert "sourceSuite=evals/regression/rag-ingestion-candidate.json" in stderr
    assert (
        "liveSyncCommand='uv run reactor-langsmith-eval-sync "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate "
        "--report-file artifacts/langsmith/rag-ingestion-candidate-c1.json'"
    ) in stderr
    assert (
        "readinessCommand='uv run reactor-release-smoke-run "
        "--plan reports/release/release-smoke-plan.local.json "
        "--report-file reports/release-smoke-run.json "
        "--evidence-output reports/release-evidence.json "
        "--verified-at $(date -u +%Y-%m-%dT%H:%M:%SZ) "
        "--latest-tag $(git describe --tags --abbrev=0) "
        "--readiness-output reports/release-readiness.json "
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync "
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report "
        "langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate-c1.json'"
    ) in stderr
    assert "nextActions=review-rag-candidate-c1,sync-langsmith" in stderr
    assert (
        "nextAction.review-rag-candidate-c1='reactor-admin rag-candidates --status INGESTED "
        "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 --limit 10 --output table'"
    ) in stderr
    assert "nextAction.review-rag-candidate-c1.candidateTag='rag-candidate:c1'" in stderr
    assert "nextAction.review-rag-candidate-c1.evalCaseId='case_rag_candidate_c1'" in stderr
    assert "nextAction.review-rag-candidate-c1.sourceRunId='run_rag_candidate_c1'" in stderr
    assert (
        "nextAction.sync-langsmith='uv run reactor-langsmith-eval-sync "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate "
        "--report-file artifacts/langsmith/rag-ingestion-candidate-c1.json'"
    ) in stderr
    assert (
        "nextAction.sync-langsmith.readinessReportArg='--readiness-report "
        "hardening_suite=reports/hardening-suite.json --readiness-report "
        "langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate-c1.json'"
    ) in stderr
    assert (
        "nextAction.sync-langsmith.requiredReadinessReports=hardening_suite,langsmith_eval_sync"
    ) in stderr
    assert (
        "nextAction.sync-langsmith.requiredEnvAnyOf.0="
        "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    ) in stderr
    assert (
        "nextAction.sync-langsmith.readinessReports.langsmith_eval_sync="
        "artifacts/langsmith/rag-ingestion-candidate-c1.json"
    ) in stderr
    assert "feedbackQueueRatings=thumbs_down=1" in stderr
    assert "feedbackQueueSources=slack_button=1" in stderr
    assert (
        "feedbackQueueWorkflows=collection:rag-ingestion-candidate=1,"
        "expected-citation:doc_1=1,rag=1"
    ) in stderr
    assert "feedbackQueueExpectedCitations=doc_1=1" in stderr
    assert (
        "feedbackQueueReviewAction='reactor-admin feedback --rating thumbs_down "
        "--source slack_button "
        "--review-status inbox "
        "--case-id case-rag-candidate-c1 "
        "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 --limit 10 --output table'"
    ) in stderr
    assert f'feedbackQueueMemoryAction="{MEMORY_LIFECYCLE_GATE_ACTION}"' in stderr


def test_run_release_smoke_plan_surfaces_memory_lifecycle_action(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "failed",
                "items": [
                    {
                        "name": "hardening_suite",
                        "status": "failed",
                        "failure": "memory maintenance lifecycle contract missing",
                        "contextManifestDiagnostics": {
                            "memoryAdmissionPolicy": {
                                "activeOnly": True,
                                "missingStatusExcluded": True,
                                "tombstonedExcluded": True,
                                "supersededExcluded": True,
                            },
                            "memoryStatusCounts": {
                                "active": 1,
                                "superseded": 1,
                                "tombstoned": 1,
                            },
                            "skippedMemoryStatusCounts": {
                                "superseded": 1,
                                "tombstoned": 1,
                            },
                        },
                        "memoryMaintenanceLifecycle": memory_maintenance_lifecycle_evidence(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert (
        "memoryStatusCounts=active=1,superseded=1,tombstoned=1 "
        "skippedMemoryStatusCounts=superseded=1,tombstoned=1 "
        "memoryAdmissionPolicy='activeOnly=true; missingStatusExcluded=true; "
        "supersededExcluded=true; tombstonedExcluded=true' "
        "memoryContractAreas=manager,statuses,consolidation,review,privacy,dependencies "
        f"memoryLifecycleAction='{MEMORY_LIFECYCLE_GATE_ACTION}' "
        "memoryProposalNextActions='approve-memory; reject-memory; "
        "review-memory-dependencies; verify-memory-lifecycle' "
        'memoryVerificationSensors="uv run pytest tests/unit/test_rag_memory.py -q; '
        "uv run pytest tests/unit/test_prompt_assembler.py -q -k memory; "
        "uv run pytest tests/unit/test_context_manifest.py -q -k memory; "
        "uv run pytest tests/unit/test_memory_cli.py "
        "tests/unit/test_memory_lifecycle_actions.py "
        "-q -k 'memory_lifecycle or sensitive_recovery_actions or structured_error_body'; "
        "REACTOR_TEST_POSTGRES=1 uv run pytest "
        "tests/integration/test_memory_postgres_lifecycle.py -q; "
        "uv run pytest tests/integration/test_admin_api.py -q -k memory; "
        "uv run pytest tests/integration/test_feedback_api.py -q -k memory; "
        "uv run pytest tests/unit/test_slack_worker.py "
        "-q -k 'reaction_feedback_memory_handoff'; "
        "uv run pytest tests/unit/test_slack_feedback.py "
        "-q -k 'negative_ack_preserves_memory_review_tag'\" "
        "memoryReadinessContracts='memoryMaintenanceLifecycle; "
        "contextManifestDiagnostics.memoryAdmissionPolicy' "
        "memoryArtifactOutputs='reports/hardening-suite.json; "
        "reports/release/replatform-readiness.local.json; "
        "reports/release/release-smoke-plan.local.json; "
        "reports/release/release-smoke-preflight.local.json; "
        "reports/release/release-smoke-preflight.local.env; "
        "reports/release-smoke-run.json; reports/release-evidence.json; "
        "reports/release-readiness.json' "
        "memoryVerificationCovers='langmem_manager_shape_exercised; "
        "langmem_manager_lifecycle_policy_explicitly_configured; "
        "langmem_extracted_memory_id_required; "
        "langmem_extracted_memory_content_required; "
        "langmem_extraction_candidate_budget_enforced; "
        "proposal_promotion_requires_reviewer; sensitive_memory_proposals_blocked; "
        "memory_source_payload_secret_markers_flagged; "
        "source_payload_sensitive_memory_proposals_blocked; "
        "supersession_marks_prior_active_memory; self_supersession_rejected; "
        "tombstone_deletes_embedding; "
        "active_namespace_memory_retrieval_boundary_exercised; "
        "superseded_and_tombstoned_memory_excluded_from_model_context; "
        "memory_review_api_and_cli_surface_exercised; "
        "memory_feedback_review_handoff_exercised; "
        "slack_reaction_feedback_enters_memory_review_handoff; "
        "slack_button_feedback_preserves_memory_review_tags' "
        "memoryDependencyWarnings=1 "
        "memoryDependencyPackages=langgraph,langmem,trustcall "
        "memoryDependencyDirectPins=langgraph==1.2.7,langmem==0.0.30 "
        "memoryDependencyPinSource=pyproject.toml "
        "memoryDependencyReviewCommand='uv pip show langmem trustcall langgraph' "
        "memoryDependencyRemediationCommand='monitor upstream trustcall/langmem compatibility; "
        "keep dependency warning visible until trustcall stops importing langgraph.constants.Send "
        "or Reactor replaces the dependency path'"
    ) in stderr


def test_run_release_smoke_plan_surfaces_memory_dependency_warning_action(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "failed",
                "items": [
                    {
                        "name": "hardening_suite",
                        "status": "failed",
                        "failure": "memory maintenance lifecycle contract missing",
                        "memoryMaintenanceLifecycle": {
                            "dependencyWarnings": {
                                "findings": [
                                    {
                                        "package": "trustcall",
                                        "module": "trustcall._base",
                                        "warning": "deprecated API warning",
                                    }
                                ],
                                "checkedPackages": ["langmem", "trustcall", "langgraph"],
                                "directPins": {
                                    "langmem": "==0.0.30",
                                    "langgraph": "==1.2.7",
                                },
                                "pinSource": "pyproject.toml",
                                "reviewCommand": "uv pip show langmem trustcall langgraph",
                                "resolverCheck": {
                                    "command": (
                                        "uv lock --upgrade-package langmem "
                                        "--upgrade-package trustcall --upgrade-package langgraph "
                                        "--dry-run"
                                    ),
                                    "status": "no_lockfile_changes",
                                    "latestKnownFrom": "resolver",
                                },
                                "remediationCommand": (
                                    "monitor upstream trustcall/langmem compatibility; keep "
                                    "dependency warning visible until trustcall stops importing "
                                    "langgraph.constants.Send or Reactor replaces the dependency "
                                    "path"
                                ),
                            }
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert "memoryDependencyWarnings=1" in stderr
    assert "memoryDependencyPackages=langgraph,langmem,trustcall" in stderr
    assert "memoryDependencyDirectPins=langgraph==1.2.7,langmem==0.0.30" in stderr
    assert "memoryDependencyPinSource=pyproject.toml" in stderr
    assert "memoryDependencyReviewCommand='uv pip show langmem trustcall langgraph'" in stderr
    assert (
        "memoryDependencyRemediationCommand='monitor upstream trustcall/langmem compatibility; "
        "keep dependency warning visible until trustcall stops importing langgraph.constants.Send "
        "or Reactor replaces the dependency path'"
    ) in stderr


def test_run_release_smoke_plan_recovers_memory_feedback_queue_action(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "failed",
                "items": [
                    {
                        "name": "langsmith_eval_sync",
                        "status": "failed",
                        "failure": "langsmith eval sync contract missing",
                        "feedbackReviewQueue": {
                            "caseIds": ["memory-supersession-review"],
                            "feedbackRatingCounts": {"thumbs_down": 1},
                            "workflowTagCounts": {"memory": 1},
                            "reviewAction": (
                                "reactor-admin feedback --rating thumbs_down "
                                "--review-status inbox "
                                "--tag memory --limit 10 --output table"
                            ),
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert f'feedbackQueueMemoryAction="{MEMORY_LIFECYCLE_GATE_ACTION}"' in stderr


def test_run_release_smoke_plan_recovers_rag_candidate_feedback_queue_action(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "failed",
                "items": [
                    {
                        "name": "langsmith_eval_sync",
                        "status": "failed",
                        "failure": "langsmith eval sync contract missing",
                        "feedbackReviewQueue": {
                            "caseIds": ["case-rag-candidate-c1"],
                            "feedbackRatingCounts": {"thumbs_down": 1},
                            "workflowTagCounts": {"collection:rag-ingestion-candidate": 1},
                            "reviewAction": (
                                "reactor-admin feedback --rating thumbs_down "
                                "--review-status inbox "
                                "--tag collection:rag-ingestion-candidate --limit 10 "
                                "--output table"
                            ),
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert (
        f"feedbackQueueCandidateAction='{rag_candidate_review_action('rag-candidate:c1')}'"
        in stderr
    )
    assert (
        'feedbackQueueBulkReviewAction="reactor-admin feedback-bulk-review '
        "--candidate-tag rag-candidate:c1 --status done --tag promoted --tag langsmith "
        "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 "
        "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
        '--output table"' in stderr
    )


def test_run_release_smoke_plan_recovers_feedback_queue_action_from_candidate_tag(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "failed",
                "items": [
                    {
                        "name": "langsmith_eval_sync",
                        "status": "failed",
                        "failure": "langsmith eval sync contract missing",
                        "feedbackReviewQueue": {
                            "caseIds": ["case_feedback_queue_custom"],
                            "candidateTag": "rag-candidate:c1",
                            "feedbackRatingCounts": {"thumbs_down": 1},
                            "workflowTagCounts": {"collection:rag-ingestion-candidate": 1},
                            "reviewAction": (
                                "reactor-admin feedback --rating thumbs_down "
                                "--review-status inbox "
                                "--tag collection:rag-ingestion-candidate --limit 10 "
                                "--output table"
                            ),
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert (
        f"feedbackQueueCandidateAction='{rag_candidate_review_action('rag-candidate:c1')}'"
        in stderr
    )
    assert (
        'feedbackQueueBulkReviewAction="reactor-admin feedback-bulk-review '
        "--candidate-tag rag-candidate:c1 --status done --tag promoted --tag langsmith "
        "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 "
        "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
        '--output table"' in stderr
    )


def test_run_release_smoke_plan_surfaces_rag_verification_sensors(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "release-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "ok": False,
                "status": "failed",
                "items": [
                    {
                        "name": "hardening_suite",
                        "status": "failed",
                        "failure": "rag ingestion lifecycle contract missing",
                        "ragIngestionLifecycle": {
                            "verificationSensors": {
                                "focusedTests": [
                                    (
                                        "uv run pytest "
                                        "tests/unit/test_rag_document_management.py "
                                        "tests/unit/test_rag_retriever.py "
                                        "tests/unit/test_rag_vector_store.py -q"
                                    ),
                                    "uv run pytest tests/unit/test_prompt_assembler.py -q -k rag",
                                    (
                                        "uv run pytest tests/unit/test_agent_graph_policy.py "
                                        "-q -k research_profile_marks_plan"
                                    ),
                                    (
                                        "uv run pytest tests/unit/test_documents_cli.py "
                                        "-q -k 'ask and citation'"
                                    ),
                                    (
                                        "uv run pytest "
                                        "tests/unit/test_eval_regression_suite_apply.py "
                                        "-q -k documents_ask"
                                    ),
                                    (
                                        "uv run pytest tests/unit/test_rag_candidate_actions.py "
                                        "tests/unit/test_dress_api_smoke.py -q"
                                    ),
                                ]
                            }
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan: dict[str, object] = {
        "steps": [
            {
                "code": "release_readiness_smoke",
                "mode": "automated",
                "evidence_scope": "local_contract",
                "release_gate_closer": False,
                "evidence_uri": "reports/release-readiness.json",
                "command": ["uv", "run", "reactor-release-readiness-evidence"],
                "report_paths": [str(readiness)],
            }
        ]
    }

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        _ = command
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    steps = cast(list[dict[str, object]], report["steps"])
    stderr = str(steps[0]["stderr"])
    assert (
        'ragVerificationSensors="uv run pytest tests/unit/test_rag_document_management.py '
        "tests/unit/test_rag_retriever.py tests/unit/test_rag_vector_store.py -q; "
        "uv run pytest tests/unit/test_prompt_assembler.py -q -k rag; "
        "uv run pytest tests/unit/test_agent_graph_policy.py "
        "-q -k research_profile_marks_plan; "
        "uv run pytest tests/unit/test_documents_cli.py -q -k 'ask and citation'; "
        "uv run pytest tests/unit/test_eval_regression_suite_apply.py -q -k documents_ask; "
        "uv run pytest tests/unit/test_rag_candidate_actions.py "
        'tests/unit/test_dress_api_smoke.py -q"'
    ) in stderr


def test_run_release_smoke_plan_executes_automated_and_skips_manual(tmp_path: Path) -> None:
    executed: list[list[str]] = []
    plan = build_release_smoke_plan(READINESS_REPORT)

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        executed.append(command)
        return CommandResult(exit_code=0, duration_ms=timeout_seconds, stdout="ok", stderr="")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    assert executed == [
        [
            "uv",
            "run",
            "reactor-live-provider-smoke",
            "--output",
            "reports/live-provider-runtime-smoke.json",
        ],
        [
            "uv",
            "run",
            "pytest",
            "tests/unit/test_langchain_agent.py",
            "tests/unit/test_run_service.py",
        ],
    ]
    assert report["ok"] is True
    assert report["summary"] == {"total": 3, "passed": 2, "failed": 0, "skipped": 1}
    assert report["steps"] == [
        {
            "code": "live_provider_runtime_smoke",
            "mode": "automated",
            "evidence_scope": "live",
            "release_gate_closer": True,
            "evidence_uri": "reports/live-provider-runtime-smoke.json",
            "required_env": {"variables": ["OPENAI_API_KEY"]},
            "status": "passed",
            "exit_code": 0,
            "duration_ms": 120,
            "stdout": "ok",
            "stderr": "",
        },
        {
            "code": "live_provider_runtime_local_contract",
            "mode": "automated",
            "evidence_scope": "local_contract",
            "release_gate_closer": False,
            "evidence_uri": "reports/live-provider-runtime-smoke.json",
            "status": "passed",
            "exit_code": 0,
            "duration_ms": 120,
            "stdout": "ok",
            "stderr": "",
        },
        {
            "code": "full_backup_db_dress_rehearsal",
            "mode": "manual",
            "evidence_scope": "dress_rehearsal",
            "release_gate_closer": True,
            "evidence_uri": "reports/full-backup-db-dress-rehearsal.json",
            "required_env": {
                "variables": [
                    "REACTOR_FULL_BACKUP_EXPORTED_NDJSON",
                    "REACTOR_FULL_BACKUP_ROLLBACK_NDJSON",
                    "REACTOR_FULL_BACKUP_RETAINED_TABLE_MANIFEST",
                    "REACTOR_FULL_BACKUP_DRESS_IMPORTED_OUTPUT",
                    "REACTOR_FULL_BACKUP_DRESS_READINESS_OUTPUT",
                    "REACTOR_FULL_BACKUP_DRESS_BATCH_ID",
                ]
            },
            "status": "skipped",
            "exit_code": 0,
            "duration_ms": 0,
            "stdout": "",
            "stderr": "manual release evidence required",
        },
    ]


def test_run_release_smoke_plan_does_not_pass_empty_plan(tmp_path: Path) -> None:
    report = run_release_smoke_plan(
        {"summary": {"total": 0, "automated": 0, "manual": 0}, "steps": []},
        report_file=tmp_path / "smoke-run.json",
        command_runner=lambda command, timeout_seconds: CommandResult(
            exit_code=0,
            duration_ms=timeout_seconds,
            stdout="unexpected",
            stderr="",
        ),
    )

    assert report["ok"] is False
    assert report["status"] == "skipped"
    assert report["failure"] == "no automated release smoke steps configured"
    assert report["summary"] == {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
    assert json.loads((tmp_path / "smoke-run.json").read_text(encoding="utf-8")) == report


def test_run_release_smoke_plan_passes_already_satisfied_empty_plan(tmp_path: Path) -> None:
    report = run_release_smoke_plan(
        {
            "status": "passed",
            "reason": "release evidence requirements already satisfied",
            "summary": {"total": 0, "automated": 0, "manual": 0},
            "steps": [],
        },
        report_file=tmp_path / "smoke-run.json",
        command_runner=lambda command, timeout_seconds: CommandResult(
            exit_code=1,
            duration_ms=timeout_seconds,
            stdout="should not run",
            stderr="should not run",
        ),
    )

    assert report["ok"] is True
    assert report["status"] == "passed"
    assert report["reason"] == "release evidence requirements already satisfied"
    assert report["summary"] == {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
    assert json.loads((tmp_path / "smoke-run.json").read_text(encoding="utf-8")) == report


def test_run_release_smoke_plan_marks_failed_automated_step(tmp_path: Path) -> None:
    plan = build_release_smoke_plan(READINESS_REPORT)

    def fake_runner(command: list[str], timeout_seconds: int) -> CommandResult:
        return CommandResult(exit_code=1, duration_ms=timeout_seconds, stdout="", stderr="failed")

    report = run_release_smoke_plan(
        plan,
        report_file=tmp_path / "smoke-run.json",
        command_runner=fake_runner,
    )

    assert report["ok"] is False
    assert report["summary"] == {"total": 3, "passed": 0, "failed": 2, "skipped": 1}
    steps = cast(list[dict[str, object]], report["steps"])
    assert steps[0]["status"] == "failed"
    assert steps[0]["release_gate_closer"] is True
