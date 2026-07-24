from __future__ import annotations

import json
from io import StringIO

from reactor.cli.admin import (
    AdminCliHttpResult,
    format_state_history_table,
    result_from_response,
    run_cli,
    state_history_checkpoint_fork_action,
    state_history_diagnose_next_action,
    state_history_replay_next_action,
)
from reactor.release.readiness_actions import (
    HARDENING_SUITE_REPORT_FILE,
    release_readiness_command_for_reports,
)

RAG_CANDIDATE_C1_BULK_REVIEW_ACTION = (
    "reactor-admin feedback-bulk-review --candidate-tag rag-candidate:c1 "
    "--status done --tag promoted --tag langsmith "
    "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 "
    "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
    "--output table"
)


def rag_candidate_release_readiness_command(eval_case_id: str) -> str:
    return release_readiness_command_for_reports(
        required_reports=["hardening_suite", "langsmith_eval_sync"],
        report_files={
            "hardening_suite": HARDENING_SUITE_REPORT_FILE,
            "langsmith_eval_sync": (
                f"artifacts/langsmith/rag-ingestion-candidate-{eval_case_id}.json"
            ),
        },
    )


class FakeAdminProbe:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
        self.calls.append({"method": "GET", "path": path, "headers": headers})
        if path == "/healthz":
            return AdminCliHttpResult(ok=True, status_code=200, body={"status": "ok"})
        if path == "/readyz":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "status": "ready",
                    "checks": {
                        "database": {"ok": True, "detail": "database ready"},
                        "redis": {"ok": True, "detail": "redis ready"},
                    },
                },
            )
        if path == "/api/admin/platform/health":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "pipelineBufferUsage": 0.0,
                    "pipelineDropRate": 0.0,
                    "pipelineWriteLatencyMs": 0.0,
                    "activeAlerts": 1,
                    "cacheExactHits": 3,
                    "cacheSemanticHits": 2,
                    "cacheMisses": 5,
                },
            )
        if path == "/api/admin/capabilities":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "generatedAt": 1783000000000,
                    "source": "fastapi-routes",
                    "paths": [
                        "/api/admin/capabilities",
                        "/api/admin/platform/health",
                        "/v1/runs",
                    ],
                },
            )
        if path == "/api/admin/evals/runs?days=30&limit=5":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body=[
                    {
                        "eval_run_id": "eval_run_1",
                        "total_cases": 2,
                        "pass_count": 1,
                        "avg_score": 0.65,
                    }
                ],
            )
        if path == "/api/admin/evals/pass-rate?days=30":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body={"total_cases": 2, "pass_count": 1, "pass_rate": 0.5},
            )
        if path == "/api/admin/tenant/overview":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "totalRequests": 7,
                    "successRate": 0.857143,
                    "avgResponseTimeMs": 240,
                    "monthlyCost": "0.00300000",
                    "activeAlerts": 1,
                },
            )
        if path == "/api/admin/tenant/usage":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "channelDistribution": {"slack": 4, "api": 3},
                    "topUsers": [{"userLabel": "operator_1", "requestCount": 5}],
                },
            )
        if path == "/api/admin/tenant/quality":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body={"latencyP50": 120, "latencyP95": 360, "errorDistribution": {"timeout": 1}},
            )
        if path == "/api/admin/tenant/tools":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "toolRanking": [{"toolName": "search", "calls": 3, "successRate": 0.666667}],
                    "statusCounts": {"succeeded": 2, "failed": 1},
                },
            )
        if path == "/api/admin/tenant/cost":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "monthlyCost": "0.00300000",
                    "costByModel": {"gpt-5-mini": "0.00100000"},
                },
            )
        if path == "/api/admin/slack-activity/channels?days=30":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body=[
                    {
                        "channel": "C123",
                        "session_count": 2,
                        "unique_users": 2,
                        "total_tokens": 150,
                        "total_cost_usd": "0.0150",
                        "avg_latency_ms": 240,
                    }
                ],
            )
        if path == "/api/admin/slack-activity/daily?days=30":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body=[
                    {
                        "date": "2026-07-01",
                        "message_count": 3,
                        "unique_users": 2,
                        "success_count": 2,
                        "failure_count": 1,
                    }
                ],
            )
        if path in {
            "/v1/feedback?rating=thumbs_down&reviewStatus=inbox&limit=10",
            "/v1/feedback?rating=thumbs_down&limit=10",
            "/v1/feedback?rating=thumbs_down&source=slack_button&limit=10",
            "/v1/feedback?rating=thumbs_down&source=slack_button&reviewStatus=inbox&limit=10",
            "/v1/feedback?rating=thumbs_down&reviewStatus=inbox&limit=10&tag=citation-failure",
        }:
            review_tags = ["citation-failure"] if path.endswith("&tag=citation-failure") else None
            item: dict[str, object] = {
                "feedbackId": "fb_1",
                "query": "private user question",
                "response": "private model response",
                "rating": "thumbs_down",
                "source": "slack_button",
                "reviewStatus": "inbox",
                "version": 1,
                "runId": "run_1",
                "model": "gpt-5-mini",
                "promptVersion": 7,
                "toolsUsed": ["Rag:hybrid_search"],
                "comment": "wrong citation",
                "readyNextActionIds": ["promote-eval"],
                "blockedNextActionIds": ["persist-eval-suite"],
                "nextActions": [
                    {
                        "id": "promote-eval",
                        "command": (
                            "reactor-runs promote-eval run_1 --case-id case_run_1 "
                            "--case-file promoted-case.json "
                            "--run-file promoted-run.json "
                            "--tag feedback:fb_1 "
                            "--tag feedback-rating:thumbs_down "
                            "--apply-suite-file "
                            "tests/fixtures/agent-eval/regression-suite.json "
                            "--apply-require-source-run-id "
                            "--apply-require-run-file --apply-require-context-diagnostics "
                            "--apply-suite-summary "
                            "--langsmith-dry-run-report-file "
                            "reports/langsmith-eval-sync-dry-run.json "
                            "--output table"
                        ),
                    },
                    {
                        "id": "persist-eval-suite",
                        "dependsOnActionIds": ["promote-eval"],
                        "command": (
                            "reactor-runs promote-eval run_1 --case-id case_run_1 "
                            "--apply-suite-file evals/regression/rag-ingestion-candidate.json "
                            "--output table"
                        ),
                    },
                ],
            }
            if review_tags is not None:
                item["reviewTags"] = review_tags
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body={"items": [item], "approximateTotal": 1},
            )
        if (
            path == "/v1/feedback/export?rating=thumbs_down&source=admin_cli"
            "&reviewStatus=inbox&limit=25&tag=collection%3Arag-ingestion-candidate"
        ):
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "version": 1,
                    "source": "reactor",
                    "items": [
                        {
                            "feedbackId": "fb_export",
                            "query": "private user question",
                            "response": "private model response",
                            "rating": "thumbs_down",
                            "source": "admin_cli",
                            "reviewStatus": "inbox",
                            "reviewTags": [],
                            "version": 1,
                            "updatedAt": "2026-07-04T00:00:00+00:00",
                            "nextActions": [
                                {
                                    "id": "promote-eval",
                                    "command": (
                                        "reactor-runs promote-eval run_export "
                                        "--case-id case_run_export --output table"
                                    ),
                                }
                            ],
                        }
                    ],
                },
            )
        if (
            path == "/v1/feedback/export?rating=thumbs_down&source=admin_cli"
            "&limit=25&tag=collection%3Arag-ingestion-candidate"
        ):
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "version": 1,
                    "source": "reactor",
                    "items": [
                        {
                            "feedbackId": "fb_export_all",
                            "query": "private user question",
                            "response": "private model response",
                            "rating": "thumbs_down",
                            "source": "admin_cli",
                            "reviewStatus": "done",
                            "reviewTags": ["no-eval-needed"],
                            "reviewNote": "Duplicate of case_rag_candidate_c1.",
                            "version": 2,
                            "updatedAt": "2026-07-04T00:00:00+00:00",
                            "nextActions": [],
                        }
                    ],
                },
            )
        if path in {
            "/v1/rag-ingestion/candidates?status=INGESTED&channel=slack&limit=50",
            (
                "/v1/rag-ingestion/candidates?status=INGESTED&channel=slack&limit=50"
                "&tag=collection%3Arag-ingestion-candidate&tag=rag-candidate%3Ac1"
            ),
            (
                "/v1/rag-ingestion/candidates?status=INGESTED&limit=50"
                "&tag=collection%3Arag-ingestion-candidate"
            ),
        }:
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body=[
                    {
                        "id": "c1",
                        "status": "INGESTED",
                        "channel": "slack",
                        "runId": "run_1",
                        "ingestedDocumentId": "rag_doc_1",
                        "nextAction": (
                            "reactor-admin feedback-submit --rating thumbs_down "
                            "--run-id run_1 --query 'release policy?' "
                            "--response 'release policy answer' "
                            "--source admin_cli "
                            "--tag collection:rag-ingestion-candidate "
                            "--tag rag-candidate:c1 --tag documents-ask --tag rag "
                            "--tag grounding --output table"
                        ),
                        "readyNextActionIds": ["submit-feedback"],
                        "blockedNextActionIds": ["promote-eval"],
                        "nextActionStates": {
                            "submit-feedback": "ready",
                            "promote-eval": "blocked",
                        },
                        "nextActions": [
                            {
                                "id": "submit-feedback",
                                "label": "Submit candidate answer feedback before eval promotion",
                                "command": (
                                    "reactor-admin feedback-submit --rating thumbs_down "
                                    "--run-id run_1 --query 'release policy?' "
                                    "--response 'release policy answer' "
                                    "--source admin_cli "
                                    "--tag collection:rag-ingestion-candidate "
                                    "--tag rag-candidate:c1 --tag documents-ask --tag rag "
                                    "--tag grounding --output table"
                                ),
                            },
                            {
                                "id": "promote-eval",
                                "label": (
                                    "Promote the candidate source run into the regression suite"
                                ),
                                "command": (
                                    "reactor-runs promote-eval run_1 "
                                    "--case-id case_rag_candidate_c1 "
                                    "--case-file evals/cases/case_rag_candidate_c1.json "
                                    "--run-file evals/runs/run_1.json "
                                    "--tag collection:rag-ingestion-candidate "
                                    "--tag rag-candidate:c1 --tag documents-ask "
                                    "--tag rag --tag grounding "
                                    "--feedback-source admin_cli "
                                    "--apply-suite-file "
                                    "evals/regression/rag-ingestion-candidate.json "
                                    "--apply-dataset-name reactor-rag-ingestion-candidate "
                                    "--apply-require-source-run-id "
                                    "--apply-require-run-file "
                                    "--apply-require-context-diagnostics "
                                    "--apply-suite-summary "
                                    "--langsmith-dry-run-report-file "
                                    "artifacts/langsmith/"
                                    "rag-ingestion-candidate-case_rag_candidate_c1.json "
                                    "--output table"
                                ),
                                "evalCaseId": "case_rag_candidate_c1",
                                "sourceRunId": "run_1",
                                "candidateTag": "rag-candidate:c1",
                                "caseFile": "evals/cases/case_rag_candidate_c1.json",
                                "runFile": "evals/runs/run_1.json",
                                "suiteFile": "evals/regression/rag-ingestion-candidate.json",
                                "datasetName": "reactor-rag-ingestion-candidate",
                                "reportFile": (
                                    "artifacts/langsmith/"
                                    "rag-ingestion-candidate-case_rag_candidate_c1.json"
                                ),
                                "requiredReadinessReports": [
                                    "hardening_suite",
                                    "langsmith_eval_sync",
                                ],
                                "readinessReports": {
                                    "hardening_suite": "reports/hardening-suite.json",
                                    "langsmith_eval_sync": (
                                        "artifacts/langsmith/"
                                        "rag-ingestion-candidate-case_rag_candidate_c1.json"
                                    ),
                                },
                                "workflowTags": [
                                    "collection:rag-ingestion-candidate",
                                    "rag-candidate:c1",
                                    "documents-ask",
                                    "rag",
                                    "grounding",
                                ],
                                "feedbackTags": [
                                    "collection:rag-ingestion-candidate",
                                    "rag-candidate:c1",
                                    "documents-ask",
                                    "rag",
                                    "grounding",
                                ],
                            },
                        ],
                    }
                ],
            )
        if path == "/v1/rag-ingestion/candidates?status=PENDING&limit=50":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body=[
                    {
                        "id": "c1",
                        "status": "PENDING",
                        "channel": "slack",
                        "runId": "run_1",
                        "ingestedDocumentId": None,
                        "nextAction": "reactor-runs diagnose run_1 --output table",
                        "nextActions": [
                            {
                                "id": "diagnose-run",
                                "label": "Inspect the source run before reviewing the candidate",
                                "sourceRunId": "run_1",
                                "command": "reactor-runs diagnose run_1 --output table",
                            }
                        ],
                    }
                ],
            )
        if path == "/v1/feedback/fb_1":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "feedbackId": "fb_1",
                    "query": "private user question",
                    "response": "private model response",
                    "rating": "thumbs_down",
                    "reviewStatus": "inbox",
                    "version": 1,
                    "runId": "run_1",
                    "model": "gpt-5-mini",
                    "promptVersion": 7,
                    "toolsUsed": ["Rag:hybrid_search"],
                    "comment": "wrong citation",
                    "nextActions": [
                        {
                            "id": "promote-eval",
                            "label": "Promote the feedback run into a source-controlled eval case",
                            "command": (
                                "reactor-runs promote-eval run_1 --case-id case_run_1 "
                                "--case-file promoted-case.json "
                                "--run-file promoted-run.json "
                                "--tag feedback:fb_1 "
                                "--tag feedback-rating:thumbs_down "
                                "--apply-suite-file "
                                "tests/fixtures/agent-eval/regression-suite.json "
                                "--apply-require-source-run-id "
                                "--apply-require-run-file --apply-require-context-diagnostics "
                                "--apply-suite-summary "
                                "--langsmith-dry-run-report-file "
                                "reports/langsmith-eval-sync-dry-run.json "
                                "--output table"
                            ),
                        }
                    ],
                },
            )
        return AdminCliHttpResult(ok=False, status_code=404, error="not found")

    def post_json(
        self,
        path: str,
        *,
        headers: dict[str, str],
        body: dict[str, object],
    ) -> AdminCliHttpResult:
        self.calls.append({"method": "POST", "path": path, "headers": headers, "body": body})
        if path == "/v1/feedback":
            return AdminCliHttpResult(
                ok=True,
                status_code=201,
                body={
                    "feedbackId": "fb_created",
                    "query": body.get("query", ""),
                    "response": body.get("response", ""),
                    "rating": body.get("rating", ""),
                    "reviewStatus": "inbox",
                    "reviewTags": [],
                    "version": 1,
                    "runId": body.get("runId"),
                    "model": None,
                    "comment": body.get("comment"),
                    "nextActions": [
                        {
                            "id": "promote-eval",
                            "label": "Promote the feedback run into a source-controlled eval case",
                            "expectedAnswers": ["[runbook.md]"],
                            "command": (
                                "reactor-runs promote-eval run_1 --case-id case_run_1 "
                                "--case-file promoted-case.json --run-file promoted-run.json"
                            ),
                        }
                    ],
                },
            )
        if path == "/v1/feedback/bulk-update":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "updated": ["fb_generic"],
                    "failed": [
                        {
                            "id": "fb_rag_candidate",
                            "reason": "eval_resolution_required",
                            "evalCaseId": "case_rag_candidate_c1",
                            "sourceRunId": "run_rag_candidate_c1",
                            "feedbackSource": "slack_button",
                            "nextAction": (
                                "reactor-admin feedback --feedback-id fb_rag_candidate "
                                "--output table"
                            ),
                            "bulkReviewAction": RAG_CANDIDATE_C1_BULK_REVIEW_ACTION,
                        }
                    ],
                },
            )
        if path == "/v1/rag-ingestion/candidates/c1/approve":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "id": "c1",
                    "status": "INGESTED",
                    "channel": "slack",
                    "runId": "run_1",
                    "ingestedDocumentId": "rag_doc_1",
                    "nextAction": (
                        "reactor-admin feedback-submit --rating thumbs_down "
                        "--run-id run_1 --query 'release policy?' "
                        "--response 'release policy answer' "
                        "--source admin_cli "
                        "--tag collection:rag-ingestion-candidate "
                        "--tag rag-candidate:c1 --tag documents-ask --tag rag "
                        "--tag grounding --output table"
                    ),
                    "nextActions": [
                        {
                            "id": "submit-feedback",
                            "label": "Submit candidate answer feedback before eval promotion",
                            "command": (
                                "reactor-admin feedback-submit --rating thumbs_down "
                                "--run-id run_1 --query 'release policy?' "
                                "--response 'release policy answer' "
                                "--source admin_cli "
                                "--tag collection:rag-ingestion-candidate "
                                "--tag rag-candidate:c1 --tag documents-ask "
                                "--tag rag --tag grounding --output table"
                            ),
                        },
                        {
                            "id": "inspect-submitted-feedback",
                            "label": (
                                "Inspect submitted feedback for the exact eval promotion action"
                            ),
                            "command": (
                                "reactor-admin feedback --rating thumbs_down "
                                "--source admin_cli "
                                "--review-status inbox "
                                "--tag collection:rag-ingestion-candidate "
                                "--tag rag-candidate:c1 --limit 10 --output table"
                            ),
                        },
                    ],
                },
            )
        if path == "/v1/rag-ingestion/candidates/c1/reject":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "id": "c1",
                    "status": "REJECTED",
                    "channel": "slack",
                    "runId": "run_1",
                    "ingestedDocumentId": None,
                    "nextAction": None,
                },
            )
        return AdminCliHttpResult(ok=False, status_code=404, error="not found")

    def patch_json(
        self,
        path: str,
        *,
        headers: dict[str, str],
        body: dict[str, object],
    ) -> AdminCliHttpResult:
        self.calls.append({"method": "PATCH", "path": path, "headers": headers, "body": body})
        if path == "/v1/feedback/fb_1":
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "feedbackId": "fb_1",
                    "query": "private user question",
                    "response": "private model response",
                    "rating": "thumbs_down",
                    "reviewStatus": "done",
                    "reviewTags": ["promoted", "langsmith"],
                    "reviewedBy": "operator_1",
                    "reviewNote": "promoted to regression",
                    "version": 2,
                    "runId": "run_1",
                    "model": "gpt-5-mini",
                    "nextActions": [],
                },
            )
        return AdminCliHttpResult(ok=False, status_code=404, error="not found")


def test_admin_state_history_actions_quote_shell_arguments() -> None:
    body = {
        "runId": "run needs quoting",
        "checkpointNs": "checkpoint namespace",
    }

    assert state_history_diagnose_next_action(body) == (
        "reactor-runs diagnose 'run needs quoting' --output table"
    )
    assert state_history_replay_next_action(body) == (
        "reactor-runs replay 'run needs quoting' --output table"
    )
    assert state_history_checkpoint_fork_action(body, "checkpoint needs quoting") == (
        "reactor-runs fork 'run needs quoting' --checkpoint-ns 'checkpoint namespace' "
        "--checkpoint-id 'checkpoint needs quoting' --output table"
    )


def test_admin_cli_diagnostics_fetches_platform_health_and_capabilities() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN_MANAGER",
            "diagnostics",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == {
        "status": "passed",
        "baseUrl": "http://reactor.local",
        "healthz": {"ok": True, "statusCode": 200, "body": {"status": "ok"}},
        "readyz": {
            "ok": True,
            "statusCode": 200,
            "body": {
                "status": "ready",
                "checks": {
                    "database": {"ok": True, "detail": "database ready"},
                    "redis": {"ok": True, "detail": "redis ready"},
                },
            },
        },
        "platformHealth": {
            "ok": True,
            "statusCode": 200,
            "body": {
                "pipelineBufferUsage": 0.0,
                "pipelineDropRate": 0.0,
                "pipelineWriteLatencyMs": 0.0,
                "activeAlerts": 1,
                "cacheExactHits": 3,
                "cacheSemanticHits": 2,
                "cacheMisses": 5,
            },
        },
        "capabilities": {
            "ok": True,
            "statusCode": 200,
            "pathCount": 3,
            "body": {
                "generatedAt": 1783000000000,
                "source": "fastapi-routes",
                "paths": [
                    "/api/admin/capabilities",
                    "/api/admin/platform/health",
                    "/v1/runs",
                ],
            },
        },
    }
    assert probe.calls == [
        {
            "method": "GET",
            "path": "/healthz",
            "headers": {
                "Content-Type": "application/json",
                "X-Reactor-Tenant-Id": "tenant_1",
                "X-Reactor-User-Id": "operator_1",
                "X-Reactor-Role": "ADMIN_MANAGER",
            },
        },
        {
            "method": "GET",
            "path": "/readyz",
            "headers": {
                "Content-Type": "application/json",
                "X-Reactor-Tenant-Id": "tenant_1",
                "X-Reactor-User-Id": "operator_1",
                "X-Reactor-Role": "ADMIN_MANAGER",
            },
        },
        {
            "method": "GET",
            "path": "/api/admin/platform/health",
            "headers": {
                "Content-Type": "application/json",
                "X-Reactor-Tenant-Id": "tenant_1",
                "X-Reactor-User-Id": "operator_1",
                "X-Reactor-Role": "ADMIN_MANAGER",
            },
        },
        {
            "method": "GET",
            "path": "/api/admin/capabilities",
            "headers": {
                "Content-Type": "application/json",
                "X-Reactor-Tenant-Id": "tenant_1",
                "X-Reactor-User-Id": "operator_1",
                "X-Reactor-Role": "ADMIN_MANAGER",
            },
        },
    ]


def test_admin_cli_state_history_fetches_langgraph_checkpoint_history() -> None:
    class StateHistoryProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if path == "/v1/admin/debug/state-history/run_1?limit=2":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "runId": "run_1",
                        "threadId": "thread_1",
                        "checkpointNs": "reactor",
                        "resolvedCheckpointNs": "reactor",
                        "namespaceFallbackUsed": False,
                        "entries": [
                            {
                                "checkpointId": "checkpoint_2",
                                "parentCheckpointId": "checkpoint_1",
                                "createdAt": "2026-07-02T00:00:01Z",
                                "source": "loop",
                                "step": 2,
                                "stateKeys": ["messages", "response_metadata"],
                                "updatedChannels": ["messages"],
                                "pendingWriteCount": 0,
                            }
                        ],
                    },
                )
            return super().get_json(path, headers)

    probe = StateHistoryProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "state-history",
            "run_1",
            "--limit",
            "2",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue())["entries"][0]["checkpointId"] == "checkpoint_2"
    assert probe.calls == [
        {
            "method": "GET",
            "path": "/v1/admin/debug/state-history/run_1?limit=2",
            "headers": {
                "Content-Type": "application/json",
                "X-Reactor-Tenant-Id": "tenant_1",
                "X-Reactor-User-Id": "operator_1",
                "X-Reactor-Role": "ADMIN",
            },
        }
    ]


def test_admin_cli_state_history_can_render_operator_table_output() -> None:
    class StateHistoryProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if path == "/v1/admin/debug/state-history/run_1?limit=25":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "runId": "run_1",
                        "threadId": "thread_1",
                        "checkpointNs": "reactor",
                        "resolvedCheckpointNs": "reactor",
                        "namespaceFallbackUsed": False,
                        "entries": [
                            {
                                "checkpointId": "checkpoint_2",
                                "parentCheckpointId": "checkpoint_1",
                                "createdAt": "2026-07-02T00:00:01Z",
                                "source": "loop",
                                "step": 2,
                                "stateKeys": ["messages", "response_metadata"],
                                "updatedChannels": ["messages"],
                                "pendingWriteCount": 0,
                            }
                        ],
                    },
                )
            return super().get_json(path, headers)

    probe = StateHistoryProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "state-history",
            "run_1",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "FIELD                   VALUE\n"
        "run_id                  run_1\n"
        "thread_id               thread_1\n"
        "checkpoint_ns           reactor\n"
        "resolved_checkpoint_ns  reactor\n"
        "namespace_fallback      false\n"
        "checkpoint_count        1\n"
        "latest_checkpoint_id    checkpoint_2\n"
        "diagnoseAction          reactor-runs diagnose run_1 --output table\n"
        "nextAction              reactor-runs fork run_1 --checkpoint-ns reactor "
        "--checkpoint-id checkpoint_2 --output table\n"
        "replayAction            reactor-runs replay run_1 --output table\n"
        "\n"
        "CHECKPOINT    PARENT        CREATED_AT            STEP  SOURCE  "
        "STATE_KEYS                   UPDATED_CHANNELS  PENDING  FORK_ACTION\n"
        "checkpoint_2  checkpoint_1  2026-07-02T00:00:01Z  2     loop    "
        "messages, response_metadata  messages          0        "
        "reactor-runs fork run_1 --checkpoint-ns reactor "
        "--checkpoint-id checkpoint_2 --output table\n"
    )


def test_admin_cli_state_history_fork_action_uses_resolved_namespace_after_fallback() -> None:
    class StateHistoryFallbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if path == "/v1/admin/debug/state-history/run_1?limit=25":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "runId": "run_1",
                        "threadId": "thread_1",
                        "checkpointNs": "reactor",
                        "resolvedCheckpointNs": "",
                        "namespaceFallbackUsed": True,
                        "entries": [
                            {
                                "checkpointId": "checkpoint_default",
                                "parentCheckpointId": None,
                                "createdAt": "2026-07-02T00:00:01Z",
                                "source": "loop",
                                "step": 2,
                                "stateKeys": ["response_metadata"],
                                "updatedChannels": ["response_text"],
                                "pendingWriteCount": 0,
                            }
                        ],
                    },
                )
            return super().get_json(path, headers)

    probe = StateHistoryFallbackProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "state-history",
            "run_1",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    assert (
        "nextAction              reactor-runs fork run_1 --checkpoint-ns '' "
        "--checkpoint-id checkpoint_default --output table\n"
    ) in stdout.getvalue()


def test_admin_cli_state_history_table_preserves_api_next_action_ids() -> None:
    body: dict[str, object] = {
        "runId": "run_1",
        "threadId": "thread_1",
        "checkpointNs": "reactor",
        "resolvedCheckpointNs": "reactor",
        "namespaceFallbackUsed": False,
        "entries": [
            {
                "checkpointId": "checkpoint_2",
                "parentCheckpointId": "checkpoint_1",
                "createdAt": "2026-07-02T00:00:01Z",
                "source": "loop",
                "step": 2,
                "stateKeys": ["messages"],
                "updatedChannels": ["messages"],
                "pendingWriteCount": 0,
            }
        ],
        "nextActions": [
            {
                "id": "fork-latest-checkpoint",
                "label": "Fork this run from its latest LangGraph checkpoint",
                "command": (
                    "reactor-runs fork run_1 --checkpoint-ns reactor "
                    "--checkpoint-id checkpoint_2 --output table"
                ),
            }
        ],
    }

    output = format_state_history_table(body)

    assert "nextAction.fork-latest-checkpoint" in output


def test_admin_cli_feedback_table_surfaces_eval_promotion_next_action() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback",
            "--rating",
            "thumbs_down",
            "--limit",
            "10",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert "ID    RATING       SOURCE" in stdout.getvalue()
    assert "fb_1" in stdout.getvalue()
    assert "thumbs_down" in stdout.getvalue()
    assert "slack_button" in stdout.getvalue()
    assert "prompt=7" in stdout.getvalue()
    assert "Rag:hybrid_search" in stdout.getvalue()
    assert "wrong citation" in stdout.getvalue()
    assert (
        "reactor-runs promote-eval run_1 --case-id case_run_1 "
        "--case-file promoted-case.json --run-file promoted-run.json"
    ) in stdout.getvalue()
    assert "nextAction.fb_1.readyNextActionIds  promote-eval" in stdout.getvalue()
    assert "nextAction.fb_1.blockedNextActionIds  persist-eval-suite" in stdout.getvalue()
    assert "nextAction.fb_1.persist-eval-suite" not in stdout.getvalue()
    assert probe.calls[-1]["path"] == (
        "/v1/feedback?rating=thumbs_down&reviewStatus=inbox&limit=10"
    )


def test_admin_cli_feedback_all_review_status_omits_review_status_filter() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback",
            "--rating",
            "thumbs_down",
            "--review-status",
            "all",
            "--limit",
            "10",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["path"] == "/v1/feedback?rating=thumbs_down&limit=10"


def test_admin_cli_feedback_can_filter_by_source() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback",
            "--rating",
            "thumbs_down",
            "--source",
            "slack_button",
            "--review-status",
            "inbox",
            "--limit",
            "10",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert "slack_button" in stdout.getvalue()
    assert probe.calls[-1]["path"] == (
        "/v1/feedback?rating=thumbs_down&source=slack_button&reviewStatus=inbox&limit=10"
    )


def test_admin_cli_feedback_export_can_filter_review_handoff_artifact() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-export",
            "--rating",
            "thumbs_down",
            "--source",
            "admin_cli",
            "--review-status",
            "inbox",
            "--tag",
            "collection:rag-ingestion-candidate",
            "--limit",
            "25",
            "--output",
            "json",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    body = json.loads(stdout.getvalue())
    assert body["version"] == 1
    assert body["source"] == "reactor"
    assert body["items"][0]["feedbackId"] == "fb_export"
    assert body["items"][0]["source"] == "admin_cli"
    assert body["items"][0]["nextActions"][0]["id"] == "promote-eval"
    assert "query" not in body["items"][0]
    assert "response" not in body["items"][0]
    assert probe.calls[-1]["path"] == (
        "/v1/feedback/export?rating=thumbs_down&source=admin_cli"
        "&reviewStatus=inbox&limit=25&tag=collection%3Arag-ingestion-candidate"
    )


def test_admin_cli_feedback_export_all_review_status_omits_review_status_filter() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-export",
            "--rating",
            "thumbs_down",
            "--source",
            "admin_cli",
            "--review-status",
            "all",
            "--tag",
            "collection:rag-ingestion-candidate",
            "--limit",
            "25",
            "--output",
            "json",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    body = json.loads(stdout.getvalue())
    assert body["items"][0]["feedbackId"] == "fb_export_all"
    assert probe.calls[-1]["path"] == (
        "/v1/feedback/export?rating=thumbs_down&source=admin_cli"
        "&limit=25&tag=collection%3Arag-ingestion-candidate"
    )


def test_admin_cli_feedback_export_filters_by_case_id() -> None:
    class CaseFeedbackExportProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if (
                path == "/v1/feedback/export?rating=thumbs_down&source=admin_cli"
                "&reviewStatus=inbox&caseId=case_rag_candidate_c1&limit=25"
                "&tag=collection%3Arag-ingestion-candidate"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "version": 1,
                        "source": "reactor",
                        "items": [{"feedbackId": "fb_case"}],
                    },
                )
            return super().get_json(path, headers)

    probe = CaseFeedbackExportProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-export",
            "--rating",
            "thumbs_down",
            "--source",
            "admin_cli",
            "--review-status",
            "inbox",
            "--case-id",
            "case_rag_candidate_c1",
            "--tag",
            "collection:rag-ingestion-candidate",
            "--limit",
            "25",
            "--output",
            "json",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue())["items"][0]["feedbackId"] == "fb_case"


def test_admin_cli_feedback_export_table_uses_feedback_handoff_columns() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-export",
            "--rating",
            "thumbs_down",
            "--source",
            "admin_cli",
            "--review-status",
            "all",
            "--tag",
            "collection:rag-ingestion-candidate",
            "--limit",
            "25",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    output = stdout.getvalue()
    assert "ID" in output
    assert "REVIEW_NOTE" in output
    assert "fb_export_all" in output
    assert "no-eval-needed" in output
    assert "Duplicate of case_rag_candidate_c1." in output
    assert "private user question" not in output
    assert "private model response" not in output


def test_admin_cli_rag_candidates_table_surfaces_eval_workflow_next_action() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "rag-candidates",
            "--status",
            "INGESTED",
            "--channel",
            "slack",
            "--tag",
            "collection:rag-ingestion-candidate",
            "--tag",
            "rag-candidate:c1",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert "ID  STATUS    CHANNEL  RUN    DOCUMENT   NEXT_ACTION" in stdout.getvalue()
    assert "c1  INGESTED  slack    run_1  rag_doc_1" in stdout.getvalue()
    assert (
        "reactor-admin feedback-submit --rating thumbs_down --run-id run_1 "
        "--query 'release policy?' --response 'release policy answer' "
        "--source admin_cli --tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:c1 --tag documents-ask --tag rag --tag grounding --output table"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.submit-feedback  Submit candidate answer feedback before eval promotion  "
        "reactor-admin feedback-submit --rating thumbs_down"
    ) in stdout.getvalue()
    assert "nextAction.c1.readyNextActionIds  submit-feedback" in stdout.getvalue()
    assert "nextAction.c1.blockedNextActionIds  promote-eval" in stdout.getvalue()
    assert (
        "nextAction.c1.nextActionStates  submit-feedback=ready,promote-eval=blocked"
        in stdout.getvalue()
    )
    assert "nextAction.c1.promote-eval" not in stdout.getvalue()
    assert "&&" not in stdout.getvalue()
    assert "--feedback-id fb_rag_candidate_c1" not in stdout.getvalue()
    assert "VERIFY_TIMESTAMP" not in stdout.getvalue()
    assert probe.calls[-1]["path"] == (
        "/v1/rag-ingestion/candidates?status=INGESTED&channel=slack&limit=50"
        "&tag=collection%3Arag-ingestion-candidate&tag=rag-candidate%3Ac1"
    )


def test_admin_cli_rag_candidates_accepts_collection_only_tag_filter() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "rag-candidates",
            "--status",
            "INGESTED",
            "--tag",
            "collection:rag-ingestion-candidate",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert "c1  INGESTED" in stdout.getvalue()
    assert probe.calls[-1]["path"] == (
        "/v1/rag-ingestion/candidates?status=INGESTED&limit=50"
        "&tag=collection%3Arag-ingestion-candidate"
    )


def test_admin_cli_rag_candidates_table_surfaces_pending_review_actions() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "rag-candidates",
            "--status",
            "PENDING",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert "c1  PENDING  slack    run_1" in stdout.getvalue()
    assert "reactor-runs diagnose run_1 --output table" in stdout.getvalue()
    assert "nextAction.c1.diagnose-run.sourceRunId  run_1" in stdout.getvalue()
    assert probe.calls[-1]["path"] == "/v1/rag-ingestion/candidates?status=PENDING&limit=50"


def test_admin_cli_rag_candidates_defaults_to_pending_review_queue() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "rag-candidates",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert "c1  PENDING  slack    run_1" in stdout.getvalue()
    assert probe.calls[-1]["path"] == "/v1/rag-ingestion/candidates?status=PENDING&limit=50"


def test_admin_cli_rag_candidate_approve_surfaces_eval_workflow_next_action() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "rag-candidate-approve",
            "c1",
            "--comment",
            "good candidate",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert "c1  INGESTED  slack    run_1  rag_doc_1" in stdout.getvalue()
    assert (
        "reactor-admin feedback-submit --rating thumbs_down --run-id run_1 "
        "--query 'release policy?' --response 'release policy answer' "
        "--source admin_cli --tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:c1 --tag documents-ask --tag rag --tag grounding --output table"
    ) in stdout.getvalue()
    assert (
        "reactor-admin feedback --rating thumbs_down --source admin_cli "
        "--review-status inbox --tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:c1 --limit 10 --output table"
    ) in stdout.getvalue()
    assert "&&" not in stdout.getvalue()
    assert "--feedback-id fb_rag_candidate_c1" not in stdout.getvalue()
    assert "VERIFY_TIMESTAMP" not in stdout.getvalue()
    assert probe.calls[-1]["method"] == "POST"
    assert probe.calls[-1]["path"] == "/v1/rag-ingestion/candidates/c1/approve"
    assert probe.calls[-1]["body"] == {"comment": "good candidate"}


def test_admin_cli_rag_candidate_approve_surfaces_structured_next_actions() -> None:
    class StructuredActionsProbe(FakeAdminProbe):
        def post_json(
            self,
            path: str,
            *,
            headers: dict[str, str],
            body: dict[str, object],
        ) -> AdminCliHttpResult:
            result = super().post_json(path, headers=headers, body=body)
            if result.ok and isinstance(result.body, dict):
                result.body["nextActions"] = [
                    {
                        "id": "ask-and-apply-eval",
                        "label": "Ask from the ingested candidate and apply a regression case",
                        "suiteFile": "evals/regression/rag-ingestion-candidate.json",
                        "datasetName": "reactor-rag-ingestion-candidate",
                        "evalCaseId": "case_rag_candidate_c1",
                        "sourceRunId": "run-c1",
                        "candidateTag": "rag-candidate:c1",
                        "workflowTags": [
                            "collection:rag-ingestion-candidate",
                            "rag-candidate:c1",
                            "expected-citation:candidate-runbook.md",
                            "documents-ask",
                            "rag",
                            "grounding",
                        ],
                        "caseFile": "evals/cases/case_rag_candidate_c1.json",
                        "runFile": "evals/runs/run_c1.json",
                        "feedbackRating": "thumbs_down",
                        "feedbackSource": "admin_cli",
                        "feedbackTags": [
                            "collection:rag-ingestion-candidate",
                            "rag-candidate:c1",
                            "expected-citation:candidate-runbook.md",
                            "documents-ask",
                            "rag",
                            "grounding",
                        ],
                        "command": "reactor-documents ask --collection rag-ingestion-candidate",
                    },
                    {
                        "id": "preflight-langsmith",
                        "label": (
                            "Preflight LangSmith credentials before syncing the candidate eval"
                        ),
                        "reportFile": (
                            "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                        ),
                        "suiteFile": "evals/regression/rag-ingestion-candidate.json",
                        "datasetName": "reactor-rag-ingestion-candidate",
                        "requiredEnvAnyOf": [
                            ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                        ],
                        "missingEnvAnyOf": [
                            "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
                        ],
                        "recommendedEnv": ["LANGSMITH_ENDPOINT"],
                        "preflightFile": "reports/release/release-smoke-preflight.local.json",
                        "preflightEnvTemplate": (
                            "reports/release/release-smoke-preflight.local.env"
                        ),
                        "releaseReadinessFile": "reports/release-readiness.json",
                        "envFileCommand": (
                            "uv run reactor-langsmith-eval-sync --suite-file "
                            "evals/regression/rag-ingestion-candidate.json "
                            "--required-readiness-report hardening_suite "
                            "--required-readiness-report langsmith_eval_sync "
                            "--readiness-report hardening_suite=reports/hardening-suite.json "
                            "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                            "rag-ingestion-candidate-case_rag_candidate_c1.json "
                            "--preflight-only --output table "
                            "--env-file reports/release/release-smoke-preflight.local.env"
                        ),
                        "remediationCommand": (
                            "uv run reactor-langsmith-eval-sync --suite-file "
                            "evals/regression/rag-ingestion-candidate.json "
                            "--required-readiness-report hardening_suite "
                            "--required-readiness-report langsmith_eval_sync "
                            "--readiness-report hardening_suite=reports/hardening-suite.json "
                            "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                            "rag-ingestion-candidate-case_rag_candidate_c1.json "
                            "--preflight-only --output table"
                        ),
                        "readinessReportArg": (
                            "--readiness-report hardening_suite=reports/hardening-suite.json "
                            "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                            "rag-ingestion-candidate-case_rag_candidate_c1.json"
                        ),
                        "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                        "readinessReports": {
                            "hardening_suite": "reports/hardening-suite.json",
                            "langsmith_eval_sync": (
                                "artifacts/langsmith/"
                                "rag-ingestion-candidate-case_rag_candidate_c1.json"
                            ),
                        },
                        "command": (
                            "uv run reactor-langsmith-eval-sync --suite-file "
                            "evals/regression/rag-ingestion-candidate.json "
                            "--required-readiness-report hardening_suite "
                            "--required-readiness-report langsmith_eval_sync "
                            "--readiness-report hardening_suite=reports/hardening-suite.json "
                            "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                            "rag-ingestion-candidate-case_rag_candidate_c1.json "
                            "--preflight-only --output table"
                        ),
                    },
                    {
                        "id": "sync-langsmith",
                        "label": "Sync the candidate regression case to LangSmith",
                        "reportFile": (
                            "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                        ),
                        "preflightFile": "reports/release/release-smoke-preflight.local.json",
                        "preflightEnvTemplate": (
                            "reports/release/release-smoke-preflight.local.env"
                        ),
                        "envFileCommand": (
                            "uv run reactor-langsmith-eval-sync --suite-file "
                            "evals/regression/rag-ingestion-candidate.json "
                            "--required-readiness-report hardening_suite "
                            "--required-readiness-report langsmith_eval_sync "
                            "--readiness-report hardening_suite=reports/hardening-suite.json "
                            "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                            "rag-ingestion-candidate-case_rag_candidate_c1.json "
                            "--output table "
                            "--env-file reports/release/release-smoke-preflight.local.env"
                        ),
                        "remediationCommand": (
                            "uv run reactor-langsmith-eval-sync --suite-file "
                            "evals/regression/rag-ingestion-candidate.json "
                            "--required-readiness-report hardening_suite "
                            "--required-readiness-report langsmith_eval_sync "
                            "--readiness-report hardening_suite=reports/hardening-suite.json "
                            "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                            "rag-ingestion-candidate-case_rag_candidate_c1.json "
                            "--preflight-only --output table"
                        ),
                        "readinessReportArg": (
                            "--readiness-report hardening_suite=reports/hardening-suite.json "
                            "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                            "rag-ingestion-candidate-case_rag_candidate_c1.json"
                        ),
                        "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                        "readinessReports": {
                            "hardening_suite": "reports/hardening-suite.json",
                            "langsmith_eval_sync": (
                                "artifacts/langsmith/"
                                "rag-ingestion-candidate-case_rag_candidate_c1.json"
                            ),
                        },
                        "requiredEnvAnyOf": [
                            ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                        ],
                        "missingEnvAnyOf": [
                            "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
                        ],
                        "recommendedEnv": ["LANGSMITH_ENDPOINT"],
                        "command": (
                            "uv run reactor-langsmith-eval-sync --suite-file "
                            "evals/regression/rag-ingestion-candidate.json "
                            "--required-readiness-report hardening_suite "
                            "--required-readiness-report langsmith_eval_sync "
                            "--readiness-report hardening_suite=reports/hardening-suite.json "
                            "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                            "rag-ingestion-candidate-case_rag_candidate_c1.json"
                        ),
                    },
                    {
                        "id": "generate-hardening-suite",
                        "label": (
                            "Generate the hardening suite report required for minor boundary review"
                        ),
                        "suiteFile": "evals/regression/rag-ingestion-candidate.json",
                        "datasetName": "reactor-rag-ingestion-candidate",
                        "reportFile": (
                            "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                        ),
                        "readinessReportArg": (
                            "--readiness-report hardening_suite=reports/hardening-suite.json"
                        ),
                        "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                        "readinessReports": {
                            "hardening_suite": "reports/hardening-suite.json",
                            "langsmith_eval_sync": (
                                "artifacts/langsmith/"
                                "rag-ingestion-candidate-case_rag_candidate_c1.json"
                            ),
                        },
                        "releaseReadinessCommand": (
                            "uv run reactor-replatform-readiness --output "
                            "reports/release/replatform-readiness.local.json "
                            "--allow-deferred-release-gates && uv run reactor-release-smoke-plan "
                            "--readiness reports/release/replatform-readiness.local.json "
                            "--output reports/release/release-smoke-plan.local.json && "
                            "uv run reactor-release-smoke-run --plan "
                            "reports/release/release-smoke-plan.local.json "
                            "--preflight-file reports/release/release-smoke-preflight.local.json "
                            "--env-file "
                            "reports/release/release-smoke-preflight.local.env "
                            "--report-file reports/release-smoke-run.json "
                            "--evidence-output reports/release-evidence.json "
                            "--verified-at $(date -u +%Y-%m-%dT%H:%M:%SZ) "
                            "--latest-tag $(git describe --tags --abbrev=0) "
                            "--readiness-output reports/release-readiness.json "
                            "--required-readiness-report hardening_suite "
                            "--required-readiness-report langsmith_eval_sync "
                            "--readiness-report hardening_suite=reports/hardening-suite.json "
                            "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                            "rag-ingestion-candidate-case_rag_candidate_c1.json"
                        ),
                        "command": (
                            "uv run reactor-hardening-suite "
                            "--report-file reports/hardening-suite.json"
                        ),
                    },
                    {
                        "id": "refresh-readiness",
                        "label": (
                            "Refresh release readiness with candidate LangSmith "
                            "and hardening reports"
                        ),
                        "suiteFile": "evals/regression/rag-ingestion-candidate.json",
                        "datasetName": "reactor-rag-ingestion-candidate",
                        "reportFile": (
                            "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                        ),
                        "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                        "readinessReports": {
                            "hardening_suite": "reports/hardening-suite.json",
                            "langsmith_eval_sync": (
                                "artifacts/langsmith/"
                                "rag-ingestion-candidate-case_rag_candidate_c1.json"
                            ),
                        },
                        "preflightFile": "reports/release/release-smoke-preflight.local.json",
                        "preflightEnvTemplate": (
                            "reports/release/release-smoke-preflight.local.env"
                        ),
                        "replatformReadinessFile": (
                            "reports/release/replatform-readiness.local.json"
                        ),
                        "smokePlanFile": "reports/release/release-smoke-plan.local.json",
                        "releaseEvidenceFile": "reports/release-evidence.json",
                        "releaseReadinessFile": "reports/release-readiness.json",
                        "remediationCommand": (
                            "uv run reactor-replatform-readiness --output "
                            "reports/release/replatform-readiness.local.json"
                        ),
                        "envFileCommand": (
                            "uv run reactor-replatform-readiness --output "
                            "reports/release/replatform-readiness.local.json "
                            "--allow-deferred-release-gates && uv run reactor-release-smoke-plan "
                            "--readiness reports/release/replatform-readiness.local.json "
                            "--output reports/release/release-smoke-plan.local.json && "
                            "uv run reactor-release-smoke-run --plan "
                            "reports/release/release-smoke-plan.local.json "
                            "--preflight-file reports/release/release-smoke-preflight.local.json "
                            "--env-file "
                            "reports/release/release-smoke-preflight.local.env "
                            "--report-file reports/release-smoke-run.json "
                            "--evidence-output reports/release-evidence.json "
                            "--verified-at $(date -u +%Y-%m-%dT%H:%M:%SZ) "
                            "--latest-tag $(git describe --tags --abbrev=0) "
                            "--readiness-output reports/release-readiness.json "
                            "--required-readiness-report hardening_suite "
                            "--required-readiness-report langsmith_eval_sync "
                            "--readiness-report hardening_suite=reports/hardening-suite.json "
                            "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                            "rag-ingestion-candidate-case_rag_candidate_c1.json "
                            "--env-file reports/release/release-smoke-preflight.local.env"
                        ),
                        "readinessReportArg": (
                            "--readiness-report hardening_suite=reports/hardening-suite.json "
                            "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                            "rag-ingestion-candidate-case_rag_candidate_c1.json"
                        ),
                        "latestTagCommand": "git describe --tags --abbrev=0",
                        "recommendedTagSource": (
                            "release_readiness.tagRecommendation.recommendedTag"
                        ),
                        "minorBoundaryReports": ["hardening_suite", "langsmith_eval_sync"],
                        "minorBlockedReports": ["langsmith_eval_sync"],
                        "minorBoundaryMissingEvidence": ["feedback_promotion.reviewed_feedback"],
                        "command": (
                            "uv run reactor-replatform-readiness --output "
                            "reports/release/replatform-readiness.local.json "
                            "--allow-deferred-release-gates && uv run reactor-release-smoke-plan "
                            "--readiness reports/release/replatform-readiness.local.json "
                            "--output reports/release/release-smoke-plan.local.json && "
                            "uv run reactor-release-smoke-run --plan "
                            "reports/release/release-smoke-plan.local.json "
                            "--preflight-file reports/release/release-smoke-preflight.local.json "
                            "--env-file "
                            "reports/release/release-smoke-preflight.local.env "
                            "--report-file reports/release-smoke-run.json "
                            "--evidence-output reports/release-evidence.json "
                            "--verified-at $(date -u +%Y-%m-%dT%H:%M:%SZ) "
                            "--latest-tag $(git describe --tags --abbrev=0) "
                            "--readiness-output reports/release-readiness.json "
                            "--required-readiness-report hardening_suite "
                            "--required-readiness-report langsmith_eval_sync "
                            "--readiness-report hardening_suite=reports/hardening-suite.json "
                            "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                            "rag-ingestion-candidate-case_rag_candidate_c1.json"
                        ),
                    },
                ]
            return result

    probe = StructuredActionsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "rag-candidate-approve",
            "c1",
            "--comment",
            "good candidate",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert "nextAction.c1.ask-and-apply-eval" in stdout.getvalue()
    assert "Ask from the ingested candidate and apply a regression case" in stdout.getvalue()
    assert (
        "nextAction.c1.ask-and-apply-eval.caseFile  evals/cases/case_rag_candidate_c1.json"
    ) in stdout.getvalue()
    assert ("nextAction.c1.ask-and-apply-eval.runFile  evals/runs/run_c1.json") in stdout.getvalue()
    assert (
        "nextAction.c1.ask-and-apply-eval.suiteFile  evals/regression/rag-ingestion-candidate.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.ask-and-apply-eval.datasetName  reactor-rag-ingestion-candidate"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.ask-and-apply-eval.evalCaseId  case_rag_candidate_c1"
    ) in stdout.getvalue()
    assert "nextAction.c1.ask-and-apply-eval.sourceRunId  run-c1" in stdout.getvalue()
    assert "nextAction.c1.ask-and-apply-eval.candidateTag  rag-candidate:c1" in stdout.getvalue()
    assert (
        "nextAction.c1.ask-and-apply-eval.workflowTags  "
        "collection:rag-ingestion-candidate,rag-candidate:c1,"
        "expected-citation:candidate-runbook.md,documents-ask,rag,grounding"
    ) in stdout.getvalue()
    assert "nextAction.c1.ask-and-apply-eval.feedbackRating  thumbs_down" in stdout.getvalue()
    assert "nextAction.c1.ask-and-apply-eval.feedbackSource  admin_cli" in stdout.getvalue()
    assert (
        "nextAction.c1.ask-and-apply-eval.feedbackTags  "
        "collection:rag-ingestion-candidate,rag-candidate:c1,"
        "expected-citation:candidate-runbook.md,documents-ask,rag,grounding"
    ) in stdout.getvalue()
    assert "reactor-documents ask --collection rag-ingestion-candidate" in stdout.getvalue()
    assert "nextAction.c1.preflight-langsmith" in stdout.getvalue()
    assert (
        "nextAction.c1.preflight-langsmith.requiredEnvAnyOf.0  "
        "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.preflight-langsmith.missingEnvAnyOf  "
        "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.preflight-langsmith.recommendedEnv  LANGSMITH_ENDPOINT"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.preflight-langsmith.preflightFile  "
        "reports/release/release-smoke-preflight.local.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.preflight-langsmith.preflightEnvTemplate  "
        "reports/release/release-smoke-preflight.local.env"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.preflight-langsmith.releaseReadinessFile  reports/release-readiness.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.preflight-langsmith.envFileCommand  "
        "uv run reactor-langsmith-eval-sync --suite-file "
        "evals/regression/rag-ingestion-candidate.json "
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync "
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json "
        "--preflight-only --output table "
        "--env-file reports/release/release-smoke-preflight.local.env"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.preflight-langsmith.remediationCommand  "
        "uv run reactor-langsmith-eval-sync --suite-file "
        "evals/regression/rag-ingestion-candidate.json "
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync "
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json "
        "--preflight-only --output table"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.preflight-langsmith.readinessReportArg  "
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.preflight-langsmith.requiredReadinessReports  "
        "hardening_suite,langsmith_eval_sync"
    ) in stdout.getvalue()
    assert "nextAction.c1.sync-langsmith" in stdout.getvalue()
    assert "Sync the candidate regression case to LangSmith" in stdout.getvalue()
    assert (
        "nextAction.c1.sync-langsmith.requiredEnvAnyOf.0  "
        "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.sync-langsmith.missingEnvAnyOf  "
        "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    ) in stdout.getvalue()
    assert ("nextAction.c1.sync-langsmith.recommendedEnv  LANGSMITH_ENDPOINT") in stdout.getvalue()
    assert (
        "nextAction.c1.sync-langsmith.preflightFile  "
        "reports/release/release-smoke-preflight.local.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.sync-langsmith.reportFile  "
        "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.sync-langsmith.preflightEnvTemplate  "
        "reports/release/release-smoke-preflight.local.env"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.sync-langsmith.envFileCommand  "
        "uv run reactor-langsmith-eval-sync --suite-file "
        "evals/regression/rag-ingestion-candidate.json "
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync "
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json "
        "--output table "
        "--env-file reports/release/release-smoke-preflight.local.env"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.sync-langsmith.remediationCommand  "
        "uv run reactor-langsmith-eval-sync --suite-file "
        "evals/regression/rag-ingestion-candidate.json "
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync "
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json "
        "--preflight-only --output table"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.sync-langsmith.readinessReportArg  "
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.sync-langsmith.requiredReadinessReports  hardening_suite,langsmith_eval_sync"
    ) in stdout.getvalue()
    assert (
        "uv run reactor-langsmith-eval-sync --suite-file "
        "evals/regression/rag-ingestion-candidate.json"
    ) in stdout.getvalue()
    assert "nextAction.c1.generate-hardening-suite" in stdout.getvalue()
    assert (
        "nextAction.c1.generate-hardening-suite.releaseReadinessCommand  "
        "uv run reactor-replatform-readiness --output "
        "reports/release/replatform-readiness.local.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.generate-hardening-suite.readinessReports.hardening_suite  "
        "reports/hardening-suite.json"
    ) in stdout.getvalue()
    assert "nextAction.c1.refresh-readiness" in stdout.getvalue()
    assert (
        "Refresh release readiness with candidate LangSmith and hardening reports"
        in stdout.getvalue()
    )
    assert (
        "nextAction.c1.refresh-readiness.requiredReadinessReports  "
        "hardening_suite,langsmith_eval_sync"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.refresh-readiness.readinessReports.hardening_suite  "
        "reports/hardening-suite.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.refresh-readiness.readinessReports.langsmith_eval_sync  "
        "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.refresh-readiness.replatformReadinessFile  "
        "reports/release/replatform-readiness.local.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.refresh-readiness.smokePlanFile  "
        "reports/release/release-smoke-plan.local.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.refresh-readiness.releaseEvidenceFile  reports/release-evidence.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.refresh-readiness.releaseReadinessFile  reports/release-readiness.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.refresh-readiness.remediationCommand  "
        "uv run reactor-replatform-readiness --output "
        "reports/release/replatform-readiness.local.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.refresh-readiness.envFileCommand  "
        "uv run reactor-replatform-readiness --output "
        "reports/release/replatform-readiness.local.json "
        "--allow-deferred-release-gates && uv run reactor-release-smoke-plan "
        "--readiness reports/release/replatform-readiness.local.json "
        "--output reports/release/release-smoke-plan.local.json && "
        "uv run reactor-release-smoke-run --plan "
        "reports/release/release-smoke-plan.local.json "
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
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json "
        "--env-file reports/release/release-smoke-preflight.local.env"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.refresh-readiness.readinessReportArg  "
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.refresh-readiness.latestTagCommand  git describe --tags --abbrev=0"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.refresh-readiness.recommendedTagSource  "
        "release_readiness.tagRecommendation.recommendedTag"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.refresh-readiness.minorBoundaryReports  hardening_suite,langsmith_eval_sync"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.refresh-readiness.minorBlockedReports  langsmith_eval_sync"
    ) in stdout.getvalue()
    assert (
        "nextAction.c1.refresh-readiness.minorBoundaryMissingEvidence  "
        "feedback_promotion.reviewed_feedback"
    ) in stdout.getvalue()
    assert "--required-readiness-report hardening_suite" in stdout.getvalue()
    assert "--required-readiness-report langsmith_eval_sync" in stdout.getvalue()


def test_admin_cli_rag_candidates_scopes_structured_next_actions_by_candidate() -> None:
    class MultiCandidateActionsProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            self.calls.append({"method": "GET", "path": path, "headers": headers})
            if path == "/v1/rag-ingestion/candidates?status=INGESTED&limit=50":
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "id": "c1",
                            "status": "INGESTED",
                            "channel": "slack",
                            "runId": "run_1",
                            "ingestedDocumentId": "rag_doc_1",
                            "nextAction": (
                                "reactor-documents ask --collection rag-ingestion-candidate"
                            ),
                            "nextActions": [
                                {
                                    "id": "ask-and-apply-eval",
                                    "label": "Ask from candidate c1",
                                    "command": "reactor-documents ask --query c1",
                                }
                            ],
                        },
                        {
                            "id": "c2",
                            "status": "INGESTED",
                            "channel": "slack",
                            "runId": "run_2",
                            "ingestedDocumentId": "rag_doc_2",
                            "nextAction": (
                                "reactor-documents ask --collection rag-ingestion-candidate"
                            ),
                            "nextActions": [
                                {
                                    "id": "ask-and-apply-eval",
                                    "label": "Ask from candidate c2",
                                    "command": "reactor-documents ask --query c2",
                                }
                            ],
                        },
                    ],
                )
            return super().get_json(path, headers)

    probe = MultiCandidateActionsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "rag-candidates",
            "--status",
            "INGESTED",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    output = stdout.getvalue()
    assert (
        "nextAction.c1.ask-and-apply-eval  Ask from candidate c1  reactor-documents ask --query c1"
    ) in output
    assert (
        "nextAction.c2.ask-and-apply-eval  Ask from candidate c2  reactor-documents ask --query c2"
    ) in output
    assert "nextAction.ask-and-apply-eval  reactor-documents ask --query" not in output


def test_admin_cli_rag_candidate_approve_url_encodes_candidate_id() -> None:
    class EncodedCandidateProbe(FakeAdminProbe):
        def post_json(
            self,
            path: str,
            *,
            headers: dict[str, str],
            body: dict[str, object],
        ) -> AdminCliHttpResult:
            self.calls.append({"method": "POST", "path": path, "headers": headers, "body": body})
            if path == "/v1/rag-ingestion/candidates/candidate%2Fneeds%20encoding/approve":
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "id": "candidate/needs encoding",
                        "status": "INGESTED",
                        "channel": "slack",
                        "runId": "run_1",
                        "ingestedDocumentId": "rag_doc_1",
                        "nextAction": None,
                    },
                )
            return AdminCliHttpResult(ok=False, status_code=404, error="not found")

    probe = EncodedCandidateProbe()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "rag-candidate-approve",
            "candidate/needs encoding",
            "--comment",
            "good candidate",
        ],
        http_probe=probe,
        stdout=StringIO(),
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["method"] == "POST"
    assert (
        probe.calls[-1]["path"]
        == "/v1/rag-ingestion/candidates/candidate%2Fneeds%20encoding/approve"
    )
    assert probe.calls[-1]["body"] == {"comment": "good candidate"}


def test_admin_cli_rag_candidate_reject_marks_candidate_reviewed() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "rag-candidate-reject",
            "c1",
            "--comment",
            "not generally useful",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert "c1  REJECTED  slack    run_1" in stdout.getvalue()
    assert "reactor-documents ask" not in stdout.getvalue()
    assert probe.calls[-1]["method"] == "POST"
    assert probe.calls[-1]["path"] == "/v1/rag-ingestion/candidates/c1/reject"
    assert probe.calls[-1]["body"] == {"comment": "not generally useful"}


def test_admin_cli_feedback_can_filter_by_review_tag() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback",
            "--rating",
            "thumbs_down",
            "--tag",
            "citation-failure",
            "--limit",
            "10",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["path"] == (
        "/v1/feedback?rating=thumbs_down&reviewStatus=inbox&limit=10&tag=citation-failure"
    )
    assert "REVIEW_TAGS" in stdout.getvalue()
    assert "citation-failure" in stdout.getvalue()


def test_admin_cli_feedback_table_can_fetch_exact_feedback_id() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback",
            "--feedback-id",
            "fb_1",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert "fb_1" in stdout.getvalue()
    assert "thumbs_down" in stdout.getvalue()
    assert "wrong citation" in stdout.getvalue()
    assert (
        "reactor-runs promote-eval run_1 --case-id case_run_1 "
        "--case-file promoted-case.json --run-file promoted-run.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.fb_1.promote-eval  "
        "Promote the feedback run into a source-controlled eval case  "
    ) in stdout.getvalue()
    assert probe.calls[-1]["path"] == "/v1/feedback/fb_1"


def test_admin_cli_feedback_table_surfaces_no_eval_review_rationale() -> None:
    class ResolvedFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if path == (
                "/v1/feedback?rating=thumbs_down&reviewStatus=done&limit=10&tag=no-eval-needed"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "items": [
                            {
                                "feedbackId": "fb_no_eval",
                                "rating": "thumbs_down",
                                "source": "slack_button",
                                "reviewStatus": "done",
                                "reviewTags": ["no-eval-needed"],
                                "reviewNote": "Duplicate of case_rag_candidate_c1.",
                                "version": 2,
                                "runId": "run_rag_candidate_c1",
                                "comment": "same failure",
                                "nextActions": [],
                            }
                        ],
                        "approximateTotal": 1,
                    },
                )
            return super().get_json(path, headers)

    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback",
            "--rating",
            "thumbs_down",
            "--review-status",
            "done",
            "--tag",
            "no-eval-needed",
            "--limit",
            "10",
            "--output",
            "table",
        ],
        http_probe=ResolvedFeedbackProbe(),
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert "REVIEW_NOTE" in stdout.getvalue()
    assert "Duplicate of case_rag_candidate_c1." in stdout.getvalue()


def test_admin_cli_feedback_submit_posts_reviewable_feedback() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-submit",
            "--rating",
            "thumbs_down",
            "--run-id",
            "run_1",
            "--query",
            "release policy?",
            "--response",
            "release policy answer",
            "--comment",
            "candidate answer still needs review",
            "--source",
            "admin_cli",
            "--tag",
            "collection:rag-ingestion-candidate",
            "--tag",
            "documents-ask",
            "--tag",
            "rag",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert "fb_created" in stdout.getvalue()
    assert "release policy answer" not in stdout.getvalue()
    assert "reactor-runs promote-eval run_1 --case-id case_run_1" in stdout.getvalue()
    assert (
        "nextAction.fb_created.promote-eval  "
        "Promote the feedback run into a source-controlled eval case  "
    ) in stdout.getvalue()
    assert "nextAction.fb_created.promote-eval.expectedAnswers  [runbook.md]" in stdout.getvalue()
    assert probe.calls[-1] == {
        "method": "POST",
        "path": "/v1/feedback",
        "headers": {
            "Content-Type": "application/json",
            "X-Reactor-Tenant-Id": "tenant_1",
            "X-Reactor-User-Id": "operator_1",
            "X-Reactor-Role": "ADMIN",
        },
        "body": {
            "rating": "thumbs_down",
            "runId": "run_1",
            "query": "release policy?",
            "response": "release policy answer",
            "comment": "candidate answer still needs review",
            "source": "admin_cli",
            "tags": ["collection:rag-ingestion-candidate", "documents-ask", "rag"],
        },
    }


def test_admin_cli_feedback_table_surfaces_promote_and_review_done_actions() -> None:
    class MultiActionFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if path == "/v1/feedback?rating=thumbs_down&reviewStatus=inbox&limit=10":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "items": [
                            {
                                "feedbackId": "fb_1",
                                "rating": "thumbs_down",
                                "source": "slack_button",
                                "reviewStatus": "inbox",
                                "version": 1,
                                "runId": "run_1",
                                "model": "gpt-5-mini",
                                "comment": "wrong citation",
                                "nextActions": [
                                    {
                                        "id": "promote-eval",
                                        "label": "Promote feedback to eval",
                                        "command": "reactor-runs promote-eval run_1",
                                    },
                                    {
                                        "id": "review-done",
                                        "label": "Mark feedback review done",
                                        "command": (
                                            "reactor-admin feedback-review fb_1 "
                                            "--if-match 1 --status done --tag promoted"
                                        ),
                                    },
                                ],
                            }
                        ],
                    },
                )
            return super().get_json(path, headers)

    probe = MultiActionFeedbackProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback",
            "--rating",
            "thumbs_down",
            "--limit",
            "10",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    output = stdout.getvalue()
    assert "reactor-runs promote-eval run_1" in output
    assert (
        "reactor-runs promote-eval run_1; "
        "reactor-admin feedback-review fb_1 --if-match 1 --status done --tag promoted"
    ) in output
    assert "nextAction.fb_1.promote-eval  Promote feedback to eval  " in output
    assert "nextAction.fb_1.review-done  Mark feedback review done  " in output


def test_admin_cli_feedback_table_surfaces_memory_review_subject() -> None:
    class MemoryActionFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if path == "/v1/feedback?rating=thumbs_down&reviewStatus=inbox&limit=10":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "items": [
                            {
                                "feedbackId": "fb_memory",
                                "rating": "thumbs_down",
                                "source": "slack_button",
                                "reviewStatus": "inbox",
                                "version": 1,
                                "runId": "run_memory",
                                "tags": ["slack", "memory"],
                                "nextActions": [
                                    {
                                        "id": "review-memory",
                                        "label": "Inspect memory state",
                                        "subjectUserId": "user_1",
                                        "command": (
                                            "reactor-memory get --target-user-id user_1 "
                                            "--output table"
                                        ),
                                    },
                                ],
                            }
                        ],
                    },
                )
            return super().get_json(path, headers)

    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback",
            "--rating",
            "thumbs_down",
            "--limit",
            "10",
            "--output",
            "table",
        ],
        http_probe=MemoryActionFeedbackProbe(),
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert "nextAction.fb_memory.review-memory.subjectUserId  user_1" in stdout.getvalue()


def test_admin_cli_feedback_json_omits_raw_payload_fields() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback",
            "--rating",
            "thumbs_down",
            "--limit",
            "10",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == {
        "items": [
            {
                "feedbackId": "fb_1",
                "rating": "thumbs_down",
                "source": "slack_button",
                "reviewStatus": "inbox",
                "version": 1,
                "runId": "run_1",
                "model": "gpt-5-mini",
                "promptVersion": 7,
                "toolsUsed": ["Rag:hybrid_search"],
                "comment": "wrong citation",
                "readyNextActionIds": ["promote-eval"],
                "blockedNextActionIds": ["persist-eval-suite"],
                "nextActions": [
                    {
                        "id": "promote-eval",
                        "command": (
                            "reactor-runs promote-eval run_1 --case-id case_run_1 "
                            "--case-file promoted-case.json "
                            "--run-file promoted-run.json "
                            "--tag feedback:fb_1 "
                            "--tag feedback-rating:thumbs_down "
                            "--apply-suite-file "
                            "tests/fixtures/agent-eval/regression-suite.json "
                            "--apply-require-source-run-id "
                            "--apply-require-run-file --apply-require-context-diagnostics "
                            "--apply-suite-summary "
                            "--langsmith-dry-run-report-file "
                            "reports/langsmith-eval-sync-dry-run.json "
                            "--output table"
                        ),
                    },
                    {
                        "id": "persist-eval-suite",
                        "dependsOnActionIds": ["promote-eval"],
                        "command": (
                            "reactor-runs promote-eval run_1 --case-id case_run_1 "
                            "--apply-suite-file evals/regression/rag-ingestion-candidate.json "
                            "--output table"
                        ),
                    },
                ],
            }
        ],
        "approximateTotal": 1,
    }
    assert "private user question" not in stdout.getvalue()
    assert "private model response" not in stdout.getvalue()
    assert probe.calls[-1]["path"] == (
        "/v1/feedback?rating=thumbs_down&reviewStatus=inbox&limit=10"
    )


def test_admin_cli_feedback_review_updates_status_without_raw_payload_output() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-review",
            "fb_1",
            "--if-match",
            "1",
            "--status",
            "done",
            "--tag",
            "promoted",
            "--tag",
            "langsmith",
            "--note",
            "promoted to regression",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == {
        "feedbackId": "fb_1",
        "rating": "thumbs_down",
        "reviewStatus": "done",
        "reviewTags": ["promoted", "langsmith"],
        "reviewedBy": "operator_1",
        "reviewNote": "promoted to regression",
        "version": 2,
        "runId": "run_1",
        "model": "gpt-5-mini",
        "nextActions": [],
    }
    assert "private user question" not in stdout.getvalue()
    assert "private model response" not in stdout.getvalue()
    assert probe.calls[-1] == {
        "method": "PATCH",
        "path": "/v1/feedback/fb_1",
        "headers": {
            "Content-Type": "application/json",
            "X-Reactor-Tenant-Id": "tenant_1",
            "X-Reactor-User-Id": "operator_1",
            "X-Reactor-Role": "ADMIN",
            "If-Match": "1",
        },
        "body": {
            "status": "done",
            "tags": ["promoted", "langsmith"],
            "note": "promoted to regression",
        },
    }


def test_admin_cli_feedback_review_skips_already_done_resolution() -> None:
    class DoneFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if path == "/v1/feedback/fb_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "feedbackId": "fb_1",
                        "query": "private user question",
                        "response": "private model response",
                        "rating": "thumbs_down",
                        "reviewStatus": "done",
                        "reviewTags": ["promoted", "langsmith"],
                        "reviewedBy": "operator_1",
                        "reviewNote": "promoted to regression",
                        "version": 2,
                        "runId": "run_1",
                        "model": "gpt-5-mini",
                        "nextActions": [],
                    },
                )
            return super().get_json(path, headers)

        def patch_json(
            self,
            path: str,
            *,
            headers: dict[str, str],
            body: dict[str, object],
        ) -> AdminCliHttpResult:
            self.calls.append({"method": "PATCH", "path": path, "headers": headers, "body": body})
            return AdminCliHttpResult(ok=False, status_code=412, error="version mismatch")

    probe = DoneFeedbackProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-review",
            "fb_1",
            "--if-match",
            "1",
            "--status",
            "done",
            "--tag",
            "promoted",
            "--tag",
            "langsmith",
            "--note",
            "promoted to regression",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["method"] == "GET"
    assert json.loads(stdout.getvalue()) == {
        "feedbackId": "fb_1",
        "rating": "thumbs_down",
        "reviewStatus": "done",
        "reviewTags": ["promoted", "langsmith"],
        "reviewedBy": "operator_1",
        "reviewNote": "promoted to regression",
        "version": 2,
        "runId": "run_1",
        "model": "gpt-5-mini",
        "nextActions": [],
    }
    assert "private user question" not in stdout.getvalue()
    assert "private model response" not in stdout.getvalue()


def test_admin_cli_feedback_bulk_review_posts_ids_and_preserves_recovery_actions() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "fb_rag_candidate",
            "fb_generic",
            "--status",
            "done",
            "--tag",
            "triaged",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == {
        "failed": [
            {
                "id": "fb_rag_candidate",
                "reason": "eval_resolution_required",
                "evalCaseId": "case_rag_candidate_c1",
                "sourceRunId": "run_rag_candidate_c1",
                "feedbackSource": "slack_button",
                "nextAction": (
                    "reactor-admin feedback --feedback-id fb_rag_candidate --output table"
                ),
                "bulkReviewAction": RAG_CANDIDATE_C1_BULK_REVIEW_ACTION,
            }
        ],
        "updated": ["fb_generic"],
    }
    assert probe.calls[-1] == {
        "method": "POST",
        "path": "/v1/feedback/bulk-update",
        "headers": {
            "Content-Type": "application/json",
            "X-Reactor-Tenant-Id": "tenant_1",
            "X-Reactor-User-Id": "operator_1",
            "X-Reactor-Role": "ADMIN",
        },
        "body": {
            "ids": ["fb_rag_candidate", "fb_generic"],
            "status": "done",
            "tags": ["triaged"],
        },
    }


def test_admin_cli_feedback_bulk_review_table_preserves_handoff_metadata() -> None:
    class ReadinessHandoffProbe(FakeAdminProbe):
        def post_json(
            self,
            path: str,
            *,
            headers: dict[str, str],
            body: dict[str, object],
        ) -> AdminCliHttpResult:
            result = super().post_json(path, headers=headers, body=body)
            if path == "/v1/feedback/bulk-update" and isinstance(result.body, dict):
                result.body["updatedDetails"] = [
                    {
                        "feedbackId": "fb_generic",
                        "evalCaseId": "case_generic_review",
                        "sourceRunId": "run_generic_review",
                        "feedbackSource": "admin_cli",
                        "nextAction": (
                            "uv run reactor-release-smoke-run --readiness-output "
                            "reports/release-readiness.json --required-readiness-report "
                            "hardening_suite"
                        ),
                        "readinessReportArg": (
                            "--readiness-report hardening_suite=reports/hardening-suite.json"
                        ),
                        "requiredReadinessReports": ["hardening_suite"],
                        "readinessReports": {
                            "hardening_suite": "reports/hardening-suite.json",
                        },
                        "requiredEnvAnyOf": [
                            ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                        ],
                        "recommendedEnv": ["LANGSMITH_ENDPOINT"],
                    }
                ]
                failed = result.body.get("failed")
                if isinstance(failed, list) and failed and isinstance(failed[0], dict):
                    failed[0]["readinessReportArg"] = (
                        "--readiness-report hardening_suite=reports/hardening-suite.json "
                        "--readiness-report "
                        "langsmith_eval_sync=artifacts/langsmith/"
                        "rag-ingestion-candidate-case_rag_candidate_c1.json"
                    )
                    failed[0]["requiredReadinessReports"] = [
                        "hardening_suite",
                        "langsmith_eval_sync",
                    ]
                    failed[0]["readinessReports"] = {
                        "hardening_suite": "reports/hardening-suite.json",
                        "langsmith_eval_sync": (
                            "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                        ),
                    }
            return result

    probe = ReadinessHandoffProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "fb_rag_candidate",
            "fb_generic",
            "--status",
            "done",
            "--tag",
            "triaged",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    output = stdout.getvalue()
    assert "EVAL_CASE_ID" in output
    assert "SOURCE_RUN_ID" in output
    assert "FEEDBACK_SOURCE" in output
    assert "BULK_REVIEW_ACTION" in output
    assert "READINESS_REPORT_ARG" in output
    assert "REQUIRED_READINESS_REPORTS" in output
    assert "REQUIRED_ENV_ANY_OF" in output
    assert "RECOMMENDED_ENV" in output
    assert "READINESS_REPORTS" in output
    assert "case_rag_candidate_c1" in output
    assert "run_rag_candidate_c1" in output
    assert "slack_button" in output
    assert RAG_CANDIDATE_C1_BULK_REVIEW_ACTION in output
    assert "updated  fb_generic" in output
    assert "case_generic_review" in output
    assert "run_generic_review" in output
    assert (
        "uv run reactor-release-smoke-run --readiness-output "
        "reports/release-readiness.json --required-readiness-report hardening_suite"
    ) in output
    assert "--readiness-report hardening_suite=reports/hardening-suite.json" in output
    assert "hardening_suite,langsmith_eval_sync" in output
    assert "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY" in output
    assert "LANGSMITH_ENDPOINT" in output
    assert (
        "hardening_suite=reports/hardening-suite.json;"
        "langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json"
    ) in output


def test_admin_cli_feedback_bulk_review_resolves_case_id_handoff() -> None:
    class CaseFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if (
                path == "/v1/feedback?reviewStatus=inbox&caseId="
                "case_rag_candidate_grounded&limit=100"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "items": [
                            {
                                "feedbackId": "fb_rag_1",
                                "reviewStatus": "inbox",
                                "nextActions": [
                                    {
                                        "id": "promote-eval",
                                        "evalCaseId": "case_rag_candidate_grounded",
                                    }
                                ],
                            },
                            {
                                "feedbackId": "fb_other",
                                "reviewStatus": "inbox",
                                "nextActions": [
                                    {
                                        "id": "promote-eval",
                                        "evalCaseId": "case_other",
                                    }
                                ],
                            },
                        ],
                        "approximateTotal": 2,
                    },
                )
            return super().get_json(path, headers)

    probe = CaseFeedbackProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "--case-id",
            "case_rag_candidate_grounded",
            "--status",
            "done",
            "--tag",
            "promoted",
            "--tag",
            "langsmith",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["method"] == "POST"
    assert probe.calls[-1]["path"] == "/v1/feedback/bulk-update"
    assert probe.calls[-1]["body"] == {
        "ids": ["fb_rag_1"],
        "status": "done",
        "tags": ["promoted", "langsmith"],
        "note": "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
    }


def test_admin_cli_feedback_bulk_review_resolves_already_done_case_id_handoff() -> None:
    class DoneCaseFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if (
                path == "/v1/feedback?reviewStatus=inbox&caseId="
                "case_rag_candidate_grounded&limit=100"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={"items": [], "approximateTotal": 0},
                )
            if (
                path == "/v1/feedback?reviewStatus=done&caseId="
                "case_rag_candidate_grounded&limit=100"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "items": [
                            {
                                "feedbackId": "fb_rag_1",
                                "reviewStatus": "done",
                                "reviewTags": ["promoted", "langsmith"],
                                "reviewNote": (
                                    "Promoted to regression eval and reviewed in "
                                    "hardening/LangSmith."
                                ),
                                "nextActions": [
                                    {
                                        "id": "promote-eval",
                                        "evalCaseId": "case_rag_candidate_grounded",
                                    }
                                ],
                            }
                        ],
                        "approximateTotal": 1,
                    },
                )
            return super().get_json(path, headers)

    probe = DoneCaseFeedbackProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "--case-id",
            "case_rag_candidate_grounded",
            "--status",
            "done",
            "--tag",
            "promoted",
            "--tag",
            "langsmith",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["method"] == "GET"
    assert json.loads(stdout.getvalue()) == {
        "updated": [],
        "alreadyDone": ["fb_rag_1"],
        "alreadyDoneDetails": [
            {
                "feedbackId": "fb_rag_1",
                "reviewStatus": "done",
                "reviewTags": ["promoted", "langsmith"],
                "reviewNote": (
                    "Promoted to regression eval and reviewed in hardening/LangSmith. "
                    "Required readiness reports: hardening_suite, langsmith_eval_sync."
                ),
                "evalCaseId": "case_rag_candidate_grounded",
                "langsmithReviewArgs": (
                    "--feedback-review-status done --feedback-review-tag promoted "
                    "--feedback-review-tag langsmith "
                    "--feedback-review-note 'Promoted to regression eval and reviewed "
                    "in hardening/LangSmith. Required readiness reports: "
                    "hardening_suite, langsmith_eval_sync.'"
                ),
                "langsmithReviewCommand": (
                    "uv run reactor-langsmith-eval-sync "
                    "--suite-file evals/regression/rag-ingestion-candidate.json "
                    "--dataset-name reactor-rag-ingestion-candidate --dry-run "
                    "--report-file artifacts/langsmith/"
                    "rag-ingestion-candidate-case_rag_candidate_grounded.json "
                    "--feedback-review-status done --feedback-review-tag promoted "
                    "--feedback-review-tag langsmith "
                    "--feedback-review-note 'Promoted to regression eval and reviewed "
                    "in hardening/LangSmith. Required readiness reports: "
                    "hardening_suite, langsmith_eval_sync.' --output table"
                ),
                "readinessReportArg": (
                    "--readiness-report hardening_suite=reports/hardening-suite.json "
                    "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                    "rag-ingestion-candidate-case_rag_candidate_grounded.json"
                ),
                "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                "requiredEnvAnyOf": [
                    ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                ],
                "recommendedEnv": ["LANGSMITH_ENDPOINT"],
                "readinessReports": {
                    "hardening_suite": "reports/hardening-suite.json",
                    "langsmith_eval_sync": (
                        "artifacts/langsmith/"
                        "rag-ingestion-candidate-case_rag_candidate_grounded.json"
                    ),
                },
                "releaseReadinessCommand": rag_candidate_release_readiness_command(
                    "case_rag_candidate_grounded"
                ),
            }
        ],
        "failed": [],
    }


def test_admin_cli_feedback_bulk_review_resolves_generic_done_case_id_handoff() -> None:
    class DoneCaseFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if path == "/v1/feedback?reviewStatus=inbox&caseId=case_triaged&limit=100":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={"items": [], "approximateTotal": 0},
                )
            if path == "/v1/feedback?reviewStatus=done&caseId=case_triaged&limit=100":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "items": [
                            {
                                "feedbackId": "fb_triaged",
                                "reviewStatus": "done",
                                "reviewTags": ["triaged"],
                                "nextActions": [
                                    {
                                        "id": "triage-feedback",
                                        "evalCaseId": "case_triaged",
                                    }
                                ],
                            }
                        ],
                        "approximateTotal": 1,
                    },
                )
            return super().get_json(path, headers)

    probe = DoneCaseFeedbackProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "--case-id",
            "case_triaged",
            "--status",
            "done",
            "--tag",
            "triaged",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["path"] == "/v1/feedback?reviewStatus=done&caseId=case_triaged&limit=100"
    assert json.loads(stdout.getvalue()) == {
        "updated": [],
        "alreadyDone": ["fb_triaged"],
        "failed": [],
    }


def test_admin_cli_feedback_bulk_review_resolves_candidate_tag_handoff() -> None:
    class CandidateFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if (
                path == "/v1/feedback?reviewStatus=inbox&limit=100"
                "&tag=collection%3Arag-ingestion-candidate&tag=rag-candidate%3Ac1"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "items": [
                            {
                                "feedbackId": "fb_rag_1",
                                "reviewStatus": "inbox",
                                "tags": [
                                    "collection:rag-ingestion-candidate",
                                    "rag-candidate:c1",
                                ],
                            }
                        ],
                        "approximateTotal": 1,
                    },
                )
            return super().get_json(path, headers)

    probe = CandidateFeedbackProbe()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "--candidate-tag",
            "rag-candidate:c1",
            "--status",
            "done",
            "--tag",
            "promoted",
            "--tag",
            "langsmith",
        ],
        http_probe=probe,
        stdout=StringIO(),
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["method"] == "POST"
    assert probe.calls[-1]["path"] == "/v1/feedback/bulk-update"
    assert probe.calls[-1]["body"] == {
        "ids": ["fb_rag_1"],
        "status": "done",
        "tags": ["promoted", "langsmith"],
        "note": "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
    }


def test_admin_cli_feedback_bulk_review_scopes_candidate_handoff_by_source() -> None:
    class CandidateFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if (
                path == "/v1/feedback?reviewStatus=inbox&source=documents_ask&limit=100"
                "&tag=collection%3Arag-ingestion-candidate&tag=rag-candidate%3Ac1"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "items": [
                            {
                                "feedbackId": "fb_documents_ask",
                                "reviewStatus": "inbox",
                                "source": "documents_ask",
                                "tags": [
                                    "collection:rag-ingestion-candidate",
                                    "rag-candidate:c1",
                                ],
                            }
                        ],
                        "approximateTotal": 1,
                    },
                )
            return super().get_json(path, headers)

    probe = CandidateFeedbackProbe()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "--candidate-tag",
            "rag-candidate:c1",
            "--source",
            "documents_ask",
            "--status",
            "done",
            "--tag",
            "promoted",
            "--tag",
            "langsmith",
        ],
        http_probe=probe,
        stdout=StringIO(),
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["method"] == "POST"
    assert probe.calls[-1]["path"] == "/v1/feedback/bulk-update"
    assert probe.calls[-1]["body"] == {
        "ids": ["fb_documents_ask"],
        "status": "done",
        "tags": ["promoted", "langsmith"],
        "note": "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
    }


def test_admin_cli_feedback_bulk_review_resolves_already_done_candidate_tag_handoff() -> None:
    class DoneCandidateFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if (
                path == "/v1/feedback?reviewStatus=inbox&limit=100"
                "&tag=collection%3Arag-ingestion-candidate&tag=rag-candidate%3Ac1"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={"items": [], "approximateTotal": 0},
                )
            if (
                path == "/v1/feedback?reviewStatus=done&limit=100"
                "&tag=collection%3Arag-ingestion-candidate&tag=rag-candidate%3Ac1"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "items": [
                            {
                                "feedbackId": "fb_rag_1",
                                "reviewStatus": "done",
                                "reviewTags": ["promoted", "langsmith"],
                                "reviewNote": (
                                    "Promoted to regression eval and reviewed in "
                                    "hardening/LangSmith."
                                ),
                                "source": "slack_button",
                                "tags": [
                                    "collection:rag-ingestion-candidate",
                                    "rag-candidate:c1",
                                ],
                                "nextActions": [
                                    {
                                        "id": "bulk-review-candidate-feedback",
                                        "evalCaseId": "case_rag_candidate_c1",
                                        "sourceRunId": "run_rag_candidate_c1",
                                        "feedbackSource": "slack_button",
                                    }
                                ],
                            }
                        ],
                        "approximateTotal": 1,
                    },
                )
            return super().get_json(path, headers)

    probe = DoneCandidateFeedbackProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "--candidate-tag",
            "rag-candidate:c1",
            "--status",
            "done",
            "--tag",
            "promoted",
            "--tag",
            "langsmith",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["method"] == "GET"
    assert json.loads(stdout.getvalue()) == {
        "updated": [],
        "alreadyDone": ["fb_rag_1"],
        "alreadyDoneDetails": [
            {
                "feedbackId": "fb_rag_1",
                "reviewStatus": "done",
                "reviewTags": ["promoted", "langsmith"],
                "reviewNote": (
                    "Promoted to regression eval and reviewed in hardening/LangSmith. "
                    "Required readiness reports: hardening_suite, langsmith_eval_sync."
                ),
                "feedbackSource": "slack_button",
                "evalCaseId": "case_rag_candidate_c1",
                "sourceRunId": "run_rag_candidate_c1",
                "langsmithReviewArgs": (
                    "--feedback-review-status done --feedback-review-tag promoted "
                    "--feedback-review-tag langsmith "
                    "--feedback-review-note 'Promoted to regression eval and reviewed "
                    "in hardening/LangSmith. Required readiness reports: "
                    "hardening_suite, langsmith_eval_sync.'"
                ),
                "langsmithReviewCommand": (
                    "uv run reactor-langsmith-eval-sync "
                    "--suite-file evals/regression/rag-ingestion-candidate.json "
                    "--dataset-name reactor-rag-ingestion-candidate --dry-run "
                    "--report-file artifacts/langsmith/"
                    "rag-ingestion-candidate-case_rag_candidate_c1.json "
                    "--feedback-review-status done --feedback-review-tag promoted "
                    "--feedback-review-tag langsmith "
                    "--feedback-review-note 'Promoted to regression eval and reviewed "
                    "in hardening/LangSmith. Required readiness reports: "
                    "hardening_suite, langsmith_eval_sync.' --output table"
                ),
                "readinessReportArg": (
                    "--readiness-report hardening_suite=reports/hardening-suite.json "
                    "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                    "rag-ingestion-candidate-case_rag_candidate_c1.json"
                ),
                "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                "requiredEnvAnyOf": [
                    ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                ],
                "recommendedEnv": ["LANGSMITH_ENDPOINT"],
                "readinessReports": {
                    "hardening_suite": "reports/hardening-suite.json",
                    "langsmith_eval_sync": (
                        "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                    ),
                },
                "releaseReadinessCommand": rag_candidate_release_readiness_command(
                    "case_rag_candidate_c1"
                ),
            }
        ],
        "failed": [],
    }


def test_admin_cli_feedback_bulk_review_treats_review_tag_superset_as_done() -> None:
    class DoneCandidateFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if (
                path == "/v1/feedback?reviewStatus=inbox&limit=100"
                "&tag=collection%3Arag-ingestion-candidate&tag=rag-candidate%3Ac1"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={"items": [], "approximateTotal": 0},
                )
            if (
                path == "/v1/feedback?reviewStatus=done&limit=100"
                "&tag=collection%3Arag-ingestion-candidate&tag=rag-candidate%3Ac1"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "items": [
                            {
                                "feedbackId": "fb_rag_1",
                                "reviewStatus": "done",
                                "reviewTags": [
                                    "promoted",
                                    "langsmith",
                                    "collection:rag-ingestion-candidate",
                                    "rag-candidate:c1",
                                    "operator-reviewed",
                                ],
                                "reviewNote": (
                                    "Promoted to regression eval and reviewed in "
                                    "hardening/LangSmith."
                                ),
                                "tags": [
                                    "collection:rag-ingestion-candidate",
                                    "rag-candidate:c1",
                                ],
                            }
                        ],
                        "approximateTotal": 1,
                    },
                )
            return super().get_json(path, headers)

    probe = DoneCandidateFeedbackProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "--candidate-tag",
            "rag-candidate:c1",
            "--status",
            "done",
            "--tag",
            "promoted",
            "--tag",
            "langsmith",
            "--tag",
            "collection:rag-ingestion-candidate",
            "--tag",
            "rag-candidate:c1",
            "--note",
            "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["method"] == "GET"
    assert json.loads(stdout.getvalue()) == {
        "updated": [],
        "alreadyDone": ["fb_rag_1"],
        "failed": [],
    }


def test_admin_cli_feedback_bulk_review_table_surfaces_done_candidate_review_details() -> None:
    class DoneCandidateFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if (
                path == "/v1/feedback?reviewStatus=inbox&limit=100"
                "&tag=collection%3Arag-ingestion-candidate&tag=rag-candidate%3Ac1"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={"items": [], "approximateTotal": 0},
                )
            if (
                path == "/v1/feedback?reviewStatus=done&limit=100"
                "&tag=collection%3Arag-ingestion-candidate&tag=rag-candidate%3Ac1"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "items": [
                            {
                                "feedbackId": "fb_rag_1",
                                "reviewStatus": "done",
                                "reviewTags": ["promoted", "langsmith"],
                                "reviewNote": (
                                    "Promoted to regression eval and reviewed in "
                                    "hardening/LangSmith."
                                ),
                                "source": "slack_button",
                                "tags": [
                                    "collection:rag-ingestion-candidate",
                                    "rag-candidate:c1",
                                ],
                                "nextActions": [
                                    {
                                        "id": "bulk-review-candidate-feedback",
                                        "evalCaseId": "case_rag_candidate_c1",
                                        "sourceRunId": "run_rag_candidate_c1",
                                        "feedbackSource": "slack_button",
                                    }
                                ],
                            }
                        ],
                        "approximateTotal": 1,
                    },
                )
            return super().get_json(path, headers)

    probe = DoneCandidateFeedbackProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "--candidate-tag",
            "rag-candidate:c1",
            "--status",
            "done",
            "--tag",
            "promoted",
            "--tag",
            "langsmith",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "REVIEW_TAGS" in output
    assert "REVIEW_NOTE" in output
    assert "LANGSMITH_REVIEW_ARGS" in output
    assert "LANGSMITH_REVIEW_COMMAND" in output
    assert "already_done" in output
    assert "fb_rag_1" in output
    assert "case_rag_candidate_c1" in output
    assert "run_rag_candidate_c1" in output
    assert "slack_button" in output
    assert "promoted,langsmith" in output
    assert (
        "Promoted to regression eval and reviewed in hardening/LangSmith. "
        "Required readiness reports: hardening_suite, langsmith_eval_sync." in output
    )
    assert "--feedback-review-status done" in output
    assert "--feedback-review-tag promoted --feedback-review-tag langsmith" in output
    assert (
        "--feedback-review-note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.'"  # noqa: E501
        in output
    )
    assert "uv run reactor-langsmith-eval-sync" in output
    assert "--suite-file evals/regression/rag-ingestion-candidate.json" in output
    assert "--dataset-name reactor-rag-ingestion-candidate" in output
    assert (
        "--report-file artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
        in output
    )
    assert "hardening_suite,langsmith_eval_sync" in output
    assert (
        "hardening_suite=reports/hardening-suite.json;langsmith_eval_sync="
        "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json" in output
    )
    assert "uv run reactor-replatform-readiness" in output
    assert "uv run reactor-release-smoke-run" in output
    assert "--required-readiness-report hardening_suite" in output
    assert "--required-readiness-report langsmith_eval_sync" in output


def test_admin_cli_feedback_bulk_review_resolves_generic_done_candidate_tag_handoff() -> None:
    class DoneCandidateFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if (
                path == "/v1/feedback?reviewStatus=inbox&limit=100"
                "&tag=collection%3Arag-ingestion-candidate&tag=rag-candidate%3Atriaged"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={"items": [], "approximateTotal": 0},
                )
            if (
                path == "/v1/feedback?reviewStatus=done&limit=100"
                "&tag=collection%3Arag-ingestion-candidate&tag=rag-candidate%3Atriaged"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "items": [
                            {
                                "feedbackId": "fb_triaged",
                                "reviewStatus": "done",
                                "reviewTags": ["triaged"],
                                "tags": [
                                    "collection:rag-ingestion-candidate",
                                    "rag-candidate:triaged",
                                ],
                            }
                        ],
                        "approximateTotal": 1,
                    },
                )
            return super().get_json(path, headers)

    probe = DoneCandidateFeedbackProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "--candidate-tag",
            "rag-candidate:triaged",
            "--status",
            "done",
            "--tag",
            "triaged",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["path"] == (
        "/v1/feedback?reviewStatus=done&limit=100"
        "&tag=collection%3Arag-ingestion-candidate&tag=rag-candidate%3Atriaged"
    )
    assert json.loads(stdout.getvalue()) == {
        "updated": [],
        "alreadyDone": ["fb_triaged"],
        "failed": [],
    }


def test_admin_cli_feedback_bulk_review_posts_review_note() -> None:
    probe = FakeAdminProbe()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "fb_rag_1",
            "--status",
            "done",
            "--tag",
            "promoted",
            "--tag",
            "langsmith",
            "--note",
            "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
        ],
        http_probe=probe,
        stdout=StringIO(),
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["method"] == "POST"
    assert probe.calls[-1]["path"] == "/v1/feedback/bulk-update"
    assert probe.calls[-1]["body"] == {
        "ids": ["fb_rag_1"],
        "status": "done",
        "tags": ["promoted", "langsmith"],
        "note": "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
    }


def test_admin_cli_feedback_bulk_review_skips_already_done_explicit_id() -> None:
    class DoneFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if path == "/v1/feedback/fb_rag_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "feedbackId": "fb_rag_1",
                        "reviewStatus": "done",
                        "reviewTags": ["promoted", "langsmith"],
                        "reviewNote": (
                            "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync."  # noqa: E501
                        ),
                    },
                )
            return super().get_json(path, headers)

    probe = DoneFeedbackProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "fb_rag_1",
            "--status",
            "done",
            "--tag",
            "promoted",
            "--tag",
            "langsmith",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["method"] == "GET"
    assert json.loads(stdout.getvalue()) == {
        "updated": [],
        "alreadyDone": ["fb_rag_1"],
        "failed": [],
    }


def test_admin_cli_feedback_bulk_review_table_keeps_already_done_readiness_handoff() -> None:
    class DoneFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if path == "/v1/feedback/fb_rag_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "feedbackId": "fb_rag_1",
                        "reviewStatus": "done",
                        "reviewTags": ["promoted", "langsmith"],
                        "reviewNote": (
                            "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync."  # noqa: E501
                        ),
                        "evalCaseId": "case_rag_candidate_c1",
                        "sourceRunId": "run_rag_candidate_c1",
                        "feedbackSource": "slack_button",
                        "readinessReportArg": (
                            "--readiness-report hardening_suite=reports/hardening-suite.json "
                            "--readiness-report "
                            "langsmith_eval_sync=artifacts/langsmith/"
                            "rag-ingestion-candidate-case_rag_candidate_c1.json"
                        ),
                        "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                        "readinessReports": {
                            "hardening_suite": "reports/hardening-suite.json",
                            "langsmith_eval_sync": (
                                "artifacts/langsmith/"
                                "rag-ingestion-candidate-case_rag_candidate_c1.json"
                            ),
                        },
                        "nextActions": [
                            {
                                "id": "refresh-readiness",
                                "command": (
                                    "uv run reactor-release-smoke-run --readiness-output "
                                    "reports/release-readiness.json --required-readiness-report "
                                    "hardening_suite --required-readiness-report "
                                    "langsmith_eval_sync --readiness-report "
                                    "hardening_suite=reports/hardening-suite.json "
                                    "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                                    "rag-ingestion-candidate-case_rag_candidate_c1.json"
                                ),
                                "evalCaseId": "case_rag_candidate_c1",
                                "sourceRunId": "run_rag_candidate_c1",
                                "feedbackSource": "slack_button",
                            }
                        ],
                    },
                )
            return super().get_json(path, headers)

    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "fb_rag_1",
            "--status",
            "done",
            "--tag",
            "promoted",
            "--tag",
            "langsmith",
            "--output",
            "table",
        ],
        http_probe=DoneFeedbackProbe(),
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "already_done  fb_rag_1" in output
    assert (
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json"
    ) in output
    assert "hardening_suite,langsmith_eval_sync" in output
    assert (
        "hardening_suite=reports/hardening-suite.json;"
        "langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json"
    ) in output
    assert (
        "uv run reactor-release-smoke-run --readiness-output "
        "reports/release-readiness.json --required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync"
    ) in output


def test_admin_cli_feedback_bulk_review_skips_generic_done_explicit_id() -> None:
    class DoneFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if path == "/v1/feedback/fb_triaged":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "feedbackId": "fb_triaged",
                        "reviewStatus": "done",
                        "reviewTags": ["triaged"],
                    },
                )
            return super().get_json(path, headers)

    probe = DoneFeedbackProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "fb_triaged",
            "--status",
            "done",
            "--tag",
            "triaged",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["method"] == "GET"
    assert json.loads(stdout.getvalue()) == {
        "updated": [],
        "alreadyDone": ["fb_triaged"],
        "failed": [],
    }


def test_admin_cli_feedback_bulk_review_posts_only_unresolved_explicit_ids() -> None:
    class MixedFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if path == "/v1/feedback/fb_done":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "feedbackId": "fb_done",
                        "reviewStatus": "done",
                        "reviewTags": ["promoted", "langsmith"],
                        "reviewNote": (
                            "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync."  # noqa: E501
                        ),
                    },
                )
            if path == "/v1/feedback/fb_open":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(ok=False, status_code=404, error="not found")
            return super().get_json(path, headers)

        def post_json(
            self,
            path: str,
            *,
            headers: dict[str, str],
            body: dict[str, object],
        ) -> AdminCliHttpResult:
            self.calls.append({"method": "POST", "path": path, "headers": headers, "body": body})
            if path == "/v1/feedback/bulk-update":
                ids = body.get("ids")
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={"updated": ids if isinstance(ids, list) else [], "failed": []},
                )
            return super().post_json(path, headers=headers, body=body)

    probe = MixedFeedbackProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "fb_done",
            "fb_open",
            "--status",
            "done",
            "--tag",
            "promoted",
            "--tag",
            "langsmith",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["method"] == "POST"
    post_body = probe.calls[-1]["body"]
    assert isinstance(post_body, dict)
    assert post_body["ids"] == ["fb_open"]
    assert json.loads(stdout.getvalue()) == {
        "updated": ["fb_open"],
        "alreadyDone": ["fb_done"],
        "failed": [],
    }


def test_admin_cli_feedback_bulk_review_table_surfaces_already_done_ids() -> None:
    class DoneFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if path == "/v1/feedback/fb_done":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "feedbackId": "fb_done",
                        "reviewStatus": "done",
                        "reviewTags": ["promoted", "langsmith"],
                        "reviewNote": (
                            "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync."  # noqa: E501
                        ),
                    },
                )
            return super().get_json(path, headers)

    probe = DoneFeedbackProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "fb_done",
            "--status",
            "done",
            "--tag",
            "promoted",
            "--tag",
            "langsmith",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert "already_done  fb_done" in stdout.getvalue()


def test_admin_cli_feedback_bulk_review_resolves_candidate_tag_from_next_action_command() -> None:
    class CandidateCommandProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if (
                path == "/v1/feedback?reviewStatus=inbox&limit=100"
                "&tag=collection%3Arag-ingestion-candidate&tag=rag-candidate%3Ac1"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "items": [
                            {
                                "feedbackId": "fb_rag_1",
                                "reviewStatus": "inbox",
                                "nextActions": [
                                    {
                                        "id": "bulk-review-candidate-feedback",
                                        "command": (
                                            "reactor-admin feedback-bulk-review "
                                            "--candidate-tag rag-candidate:c1 --status done "
                                            "--tag promoted --tag langsmith "
                                            "--tag collection:rag-ingestion-candidate "
                                            "--tag rag-candidate:c1 --output table"
                                        ),
                                    }
                                ],
                            }
                        ],
                        "approximateTotal": 1,
                    },
                )
            return super().get_json(path, headers)

    probe = CandidateCommandProbe()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "--candidate-tag",
            "rag-candidate:c1",
            "--status",
            "done",
            "--tag",
            "promoted",
            "--tag",
            "langsmith",
        ],
        http_probe=probe,
        stdout=StringIO(),
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["method"] == "POST"
    assert probe.calls[-1]["path"] == "/v1/feedback/bulk-update"
    assert probe.calls[-1]["body"] == {
        "ids": ["fb_rag_1"],
        "status": "done",
        "tags": ["promoted", "langsmith"],
        "note": "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
    }


def test_admin_cli_feedback_bulk_review_reports_unmatched_case_id() -> None:
    class EmptyCaseFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if path == "/v1/feedback?reviewStatus=inbox&caseId=case_missing_feedback&limit=100":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={"items": [], "approximateTotal": 0},
                )
            return super().get_json(path, headers)

    stderr = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "--case-id",
            "case_missing_feedback",
            "--status",
            "done",
            "--tag",
            "promoted",
        ],
        http_probe=EmptyCaseFeedbackProbe(),
        stdout=StringIO(),
        stderr=stderr,
        environ={},
    )

    assert exit_code == 1
    assert "no inbox feedback matched case id: case_missing_feedback" in stderr.getvalue()
    assert (
        "reviewQueueAction: reactor-admin feedback --review-status all "
        "--case-id case_missing_feedback --limit 10 --output table"
    ) in stderr.getvalue()


def test_admin_cli_feedback_bulk_review_reports_unmatched_candidate_tag_recovery_action() -> None:
    class EmptyCandidateFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if (
                path == "/v1/feedback?reviewStatus=inbox&limit=100"
                "&tag=collection%3Arag-ingestion-candidate&tag=rag-candidate%3Amissing"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={"items": [], "approximateTotal": 0},
                )
            return super().get_json(path, headers)

    stderr = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "--candidate-tag",
            "rag-candidate:missing",
            "--status",
            "done",
            "--tag",
            "promoted",
        ],
        http_probe=EmptyCandidateFeedbackProbe(),
        stdout=StringIO(),
        stderr=stderr,
        environ={},
    )

    assert exit_code == 1
    assert "no inbox feedback matched candidate tag: rag-candidate:missing" in stderr.getvalue()
    assert (
        "reviewQueueAction: reactor-admin feedback --review-status all "
        "--tag collection:rag-ingestion-candidate --tag rag-candidate:missing "
        "--limit 10 --output table"
    ) in stderr.getvalue()


def test_admin_cli_feedback_bulk_review_unmatched_candidate_preserves_source_recovery() -> None:
    class EmptyCandidateFeedbackProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if (
                path == "/v1/feedback?reviewStatus=inbox&source=documents_ask&limit=100"
                "&tag=collection%3Arag-ingestion-candidate&tag=rag-candidate%3Amissing"
            ):
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={"items": [], "approximateTotal": 0},
                )
            return super().get_json(path, headers)

    stderr = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "--candidate-tag",
            "rag-candidate:missing",
            "--source",
            "documents_ask",
            "--status",
            "done",
            "--tag",
            "promoted",
        ],
        http_probe=EmptyCandidateFeedbackProbe(),
        stdout=StringIO(),
        stderr=stderr,
        environ={},
    )

    assert exit_code == 1
    assert "no inbox feedback matched candidate tag: rag-candidate:missing" in stderr.getvalue()
    assert (
        "reviewQueueAction: reactor-admin feedback --review-status all "
        "--source documents_ask "
        "--tag collection:rag-ingestion-candidate --tag rag-candidate:missing "
        "--limit 10 --output table"
    ) in stderr.getvalue()


def test_admin_cli_feedback_bulk_review_table_surfaces_failed_next_action() -> None:
    class BulkReviewRecoveryActionsProbe(FakeAdminProbe):
        def post_json(
            self,
            path: str,
            *,
            headers: dict[str, str],
            body: dict[str, object],
        ) -> AdminCliHttpResult:
            if path == "/v1/feedback/bulk-update":
                self.calls.append(
                    {"method": "POST", "path": path, "headers": headers, "body": body}
                )
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "updated": ["fb_generic"],
                        "failed": [
                            {
                                "id": "fb_rag_candidate",
                                "reason": "eval_resolution_required",
                                "evalCaseId": "case_rag_candidate_c1",
                                "sourceRunId": "run_rag_candidate_c1",
                                "feedbackSource": "slack_button",
                                "requiredReviewNote": "Use exact API-required close note.",
                                "nextAction": (
                                    "reactor-admin feedback --feedback-id "
                                    "fb_rag_candidate --output table"
                                ),
                                "bulkReviewAction": RAG_CANDIDATE_C1_BULK_REVIEW_ACTION,
                                "nextActions": [
                                    {
                                        "id": "promote-eval",
                                        "label": "Promote this feedback into a regression eval",
                                        "feedbackId": "fb_rag_candidate",
                                        "command": (
                                            "reactor-runs promote-eval run_rag_candidate_c1 "
                                            "--case-id case_rag_candidate_c1 --output table"
                                        ),
                                    },
                                    {
                                        "id": "bulk-review-candidate-feedback",
                                        "label": "Close queued feedback for this RAG candidate",
                                        "feedbackId": "fb_rag_candidate",
                                        "dependsOnActionIds": ["refresh-readiness"],
                                        "requiredReviewNote": "Use exact API-required close note.",
                                        "command": RAG_CANDIDATE_C1_BULK_REVIEW_ACTION,
                                    },
                                ],
                            }
                        ],
                    },
                )
            return super().post_json(path, headers=headers, body=body)

    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-bulk-review",
            "fb_rag_candidate",
            "fb_generic",
            "--status",
            "done",
            "--tag",
            "triaged",
            "--output",
            "table",
        ],
        http_probe=BulkReviewRecoveryActionsProbe(),
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert "updated  fb_generic" in stdout.getvalue()
    assert "failed   fb_rag_candidate  eval_resolution_required" in stdout.getvalue()
    assert ("Use exact API-required close note.") in stdout.getvalue()
    assert "reactor-admin feedback --feedback-id fb_rag_candidate --output table" in (
        stdout.getvalue()
    )
    assert (
        "nextAction.fb_rag_candidate.promote-eval  "
        "Promote this feedback into a regression eval  "
        "reactor-runs promote-eval run_rag_candidate_c1 "
        "--case-id case_rag_candidate_c1 --output table"
    ) in stdout.getvalue()
    assert (
        "nextAction.fb_rag_candidate.bulk-review-candidate-feedback  "
        "Close queued feedback for this RAG candidate  "
        f"{RAG_CANDIDATE_C1_BULK_REVIEW_ACTION}" not in stdout.getvalue()
    )
    assert (
        "nextAction.fb_rag_candidate.bulk-review-candidate-feedback.requiredReviewNote  "
        "Use exact API-required close note."
    ) in stdout.getvalue()


def test_admin_cli_feedback_review_surfaces_structured_recovery_actions() -> None:
    class FeedbackReviewConflictProbe(FakeAdminProbe):
        def patch_json(
            self,
            path: str,
            *,
            headers: dict[str, str],
            body: dict[str, object],
        ) -> AdminCliHttpResult:
            self.calls.append({"method": "PATCH", "path": path, "headers": headers, "body": body})
            return AdminCliHttpResult(
                ok=False,
                status_code=409,
                body={
                    "detail": {
                        "message": "feedback review version conflict",
                        "feedbackId": "fb_1",
                        "expectedVersion": 1,
                        "currentVersion": 2,
                        "evalCaseId": "case_rag_candidate_c1",
                        "sourceRunId": "run_rag_candidate_c1",
                        "requiredReviewNote": (
                            "Promoted to regression eval and reviewed in hardening/LangSmith. "
                            "Required readiness reports: hardening_suite, langsmith_eval_sync."
                        ),
                        "nextAction": "reactor-admin feedback --feedback-id fb_1 --output table",
                        "reviewQueueAction": (
                            "reactor-admin feedback --rating thumbs_down --limit 10 --output table"
                        ),
                        "readyNextActionIds": ["preflight-langsmith"],
                        "blockedNextActionIds": ["review-done"],
                        "nextActionStates": {
                            "preflight-langsmith": "ready",
                            "review-done": "blocked",
                        },
                        "nextActions": [
                            {
                                "id": "preflight-langsmith",
                                "label": "Preflight LangSmith credentials",
                                "feedbackId": "fb_1",
                                "command": (
                                    "uv run reactor-langsmith-eval-sync "
                                    "--preflight-only --output table"
                                ),
                                "readinessReportArg": (
                                    "--readiness-report "
                                    "langsmith_eval_sync=reports/langsmith-eval-sync.json"
                                ),
                                "requiredReadinessReports": ["langsmith_eval_sync"],
                                "readinessReports": {
                                    "langsmith_eval_sync": "reports/langsmith-eval-sync.json"
                                },
                            },
                            {
                                "id": "review-done",
                                "label": "Mark feedback review done",
                                "feedbackId": "fb_1",
                                "command": (
                                    "reactor-admin feedback-review fb_1 --if-match 2 "
                                    "--status done --tag promoted --tag langsmith"
                                ),
                            },
                        ],
                    }
                },
                error="conflict",
            )

    stderr = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-review",
            "fb_1",
            "--if-match",
            "1",
            "--status",
            "done",
        ],
        http_probe=FeedbackReviewConflictProbe(),
        stdout=StringIO(),
        stderr=stderr,
        environ={},
    )

    assert exit_code == 1
    assert "feedback review version conflict" in stderr.getvalue()
    assert "feedbackId: fb_1" in stderr.getvalue()
    assert "expectedVersion: 1" in stderr.getvalue()
    assert "currentVersion: 2" in stderr.getvalue()
    assert "evalCaseId: case_rag_candidate_c1" in stderr.getvalue()
    assert "sourceRunId: run_rag_candidate_c1" in stderr.getvalue()
    assert (
        "requiredReviewNote: Promoted to regression eval and reviewed in "
        "hardening/LangSmith. Required readiness reports: hardening_suite, "
        "langsmith_eval_sync."
    ) in stderr.getvalue()
    assert "reactor-admin feedback --feedback-id fb_1 --output table" in stderr.getvalue()
    assert (
        "reactor-admin feedback --rating thumbs_down --limit 10 --output table" in stderr.getvalue()
    )
    assert (
        "nextAction.fb_1.preflight-langsmith  Preflight LangSmith credentials  "
        "uv run reactor-langsmith-eval-sync --preflight-only --output table"
    ) in stderr.getvalue()
    assert (
        "nextAction.fb_1.preflight-langsmith.requiredReadinessReports  langsmith_eval_sync"
    ) in stderr.getvalue()
    assert "readyNextActionIds: preflight-langsmith" in stderr.getvalue()
    assert "blockedNextActionIds: review-done" in stderr.getvalue()
    assert "nextActionStates: preflight-langsmith=ready,review-done=blocked" in stderr.getvalue()
    assert "nextAction.fb_1.review-done  Mark feedback review done  " not in stderr.getvalue()


def test_admin_cli_feedback_review_surfaces_required_resolution_tags() -> None:
    class FeedbackReviewResolutionProbe(FakeAdminProbe):
        def patch_json(
            self,
            path: str,
            *,
            headers: dict[str, str],
            body: dict[str, object],
        ) -> AdminCliHttpResult:
            self.calls.append({"method": "PATCH", "path": path, "headers": headers, "body": body})
            return AdminCliHttpResult(
                ok=False,
                status_code=400,
                body={
                    "detail": {
                        "message": "feedback done requires eval resolution tag",
                        "feedbackId": "fb_rag_candidate",
                        "evalCaseId": "case_rag_candidate_c1",
                        "sourceRunId": "run_rag_candidate_c1",
                        "requiredAnyReviewTag": ["deferred", "no-eval-needed", "promoted"],
                        "nextAction": (
                            "reactor-admin feedback --feedback-id fb_rag_candidate --output table"
                        ),
                        "nextActions": [
                            {
                                "id": "promote-eval",
                                "label": "Promote this feedback into a regression eval case",
                                "command": (
                                    "reactor-runs promote-eval run_rag_candidate_c1 "
                                    "--case-id case_rag_candidate_c1 --output table"
                                ),
                            },
                            {
                                "id": "bulk-review-candidate-feedback",
                                "label": (
                                    "Close queued feedback for this RAG candidate after eval "
                                    "and LangSmith review"
                                ),
                                "command": RAG_CANDIDATE_C1_BULK_REVIEW_ACTION,
                            },
                        ],
                    }
                },
                error="bad request",
            )

    stderr = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-review",
            "fb_rag_candidate",
            "--if-match",
            "1",
            "--status",
            "done",
            "--tag",
            "triaged",
        ],
        http_probe=FeedbackReviewResolutionProbe(),
        stdout=StringIO(),
        stderr=stderr,
        environ={},
    )

    assert exit_code == 1
    assert "feedback done requires eval resolution tag" in stderr.getvalue()
    assert "feedbackId: fb_rag_candidate" in stderr.getvalue()
    assert "evalCaseId: case_rag_candidate_c1" in stderr.getvalue()
    assert "sourceRunId: run_rag_candidate_c1" in stderr.getvalue()
    assert "requiredAnyReviewTag: deferred,no-eval-needed,promoted" in stderr.getvalue()
    assert "reactor-admin feedback --feedback-id fb_rag_candidate --output table" in (
        stderr.getvalue()
    )
    assert (
        "nextAction.fb_rag_candidate.promote-eval  "
        "Promote this feedback into a regression eval case  "
        "reactor-runs promote-eval run_rag_candidate_c1 "
        "--case-id case_rag_candidate_c1 --output table"
    ) in stderr.getvalue()
    assert (
        "nextAction.fb_rag_candidate.bulk-review-candidate-feedback  "
        "Close queued feedback for this RAG candidate after eval and LangSmith review  "
        f"{RAG_CANDIDATE_C1_BULK_REVIEW_ACTION}"
    ) in stderr.getvalue()


def test_admin_cli_feedback_review_surfaces_resolution_note_requirements() -> None:
    class FeedbackReviewResolutionNoteProbe(FakeAdminProbe):
        def patch_json(
            self,
            path: str,
            *,
            headers: dict[str, str],
            body: dict[str, object],
        ) -> AdminCliHttpResult:
            self.calls.append({"method": "PATCH", "path": path, "headers": headers, "body": body})
            return AdminCliHttpResult(
                ok=False,
                status_code=400,
                body={
                    "detail": {
                        "message": "feedback eval resolution note is required",
                        "feedbackId": "fb_rag_candidate",
                        "resolutionTagsRequiringNote": [
                            "deferred",
                            "no-eval-needed",
                            "promoted",
                        ],
                        "nextAction": (
                            "reactor-admin feedback --feedback-id fb_rag_candidate --output table"
                        ),
                    }
                },
                error="bad request",
            )

    stderr = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-review",
            "fb_rag_candidate",
            "--if-match",
            "1",
            "--status",
            "done",
            "--tag",
            "no-eval-needed",
        ],
        http_probe=FeedbackReviewResolutionNoteProbe(),
        stdout=StringIO(),
        stderr=stderr,
        environ={},
    )

    assert exit_code == 1
    assert "feedback eval resolution note is required" in stderr.getvalue()
    assert "feedbackId: fb_rag_candidate" in stderr.getvalue()
    assert "resolutionTagsRequiringNote: deferred,no-eval-needed,promoted" in stderr.getvalue()
    assert "reactor-admin feedback --feedback-id fb_rag_candidate --output table" in (
        stderr.getvalue()
    )


def test_admin_cli_feedback_review_surfaces_required_all_resolution_tags() -> None:
    class FeedbackReviewLangSmithResolutionProbe(FakeAdminProbe):
        def patch_json(
            self,
            path: str,
            *,
            headers: dict[str, str],
            body: dict[str, object],
        ) -> AdminCliHttpResult:
            self.calls.append({"method": "PATCH", "path": path, "headers": headers, "body": body})
            return AdminCliHttpResult(
                ok=False,
                status_code=400,
                body={
                    "detail": {
                        "message": "promoted feedback requires LangSmith resolution tag",
                        "feedbackId": "fb_rag_candidate",
                        "requiredAllReviewTags": ["promoted", "langsmith"],
                        "feedbackSource": "slack_button",
                        "readinessReportArg": (
                            "--readiness-report hardening_suite=reports/hardening-suite.json "
                            "--readiness-report "
                            "langsmith_eval_sync=artifacts/langsmith/"
                            "rag-ingestion-candidate-case_rag_candidate_c1.json"
                        ),
                        "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                        "readinessReports": {
                            "hardening_suite": "reports/hardening-suite.json",
                            "langsmith_eval_sync": (
                                "artifacts/langsmith/"
                                "rag-ingestion-candidate-case_rag_candidate_c1.json"
                            ),
                        },
                        "bulkReviewAction": RAG_CANDIDATE_C1_BULK_REVIEW_ACTION,
                        "nextAction": (
                            "reactor-admin feedback --feedback-id fb_rag_candidate --output table"
                        ),
                    }
                },
                error="bad request",
            )

    stderr = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-review",
            "fb_rag_candidate",
            "--if-match",
            "1",
            "--status",
            "done",
            "--tag",
            "promoted",
        ],
        http_probe=FeedbackReviewLangSmithResolutionProbe(),
        stdout=StringIO(),
        stderr=stderr,
        environ={},
    )

    assert exit_code == 1
    assert "promoted feedback requires LangSmith resolution tag" in stderr.getvalue()
    assert "feedbackId: fb_rag_candidate" in stderr.getvalue()
    assert "feedbackSource: slack_button" in stderr.getvalue()
    assert "requiredAllReviewTags: promoted,langsmith" in stderr.getvalue()
    assert (
        "readinessReportArg: --readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json"
    ) in stderr.getvalue()
    assert ("requiredReadinessReports: hardening_suite,langsmith_eval_sync") in stderr.getvalue()
    assert ("readinessReports.hardening_suite: reports/hardening-suite.json") in stderr.getvalue()
    assert (
        "readinessReports.langsmith_eval_sync: "
        "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
    ) in stderr.getvalue()
    assert "reactor-admin feedback --feedback-id fb_rag_candidate --output table" in (
        stderr.getvalue()
    )
    assert f"bulkReviewAction: {RAG_CANDIDATE_C1_BULK_REVIEW_ACTION}" in stderr.getvalue()


def test_admin_cli_http_result_preserves_structured_error_body() -> None:
    import httpx

    response = httpx.Response(
        409,
        json={
            "detail": {
                "message": "feedback review version conflict",
                "nextAction": "reactor-admin feedback --feedback-id fb_1 --output table",
            }
        },
    )

    result = result_from_response(response)

    assert result.ok is False
    assert result.status_code == 409
    assert result.body == {
        "detail": {
            "message": "feedback review version conflict",
            "nextAction": "reactor-admin feedback --feedback-id fb_1 --output table",
        }
    }


def test_admin_cli_feedback_review_table_suggests_next_inbox_review() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-review",
            "fb_1",
            "--if-match",
            "1",
            "--status",
            "done",
            "--tag",
            "promoted",
            "--tag",
            "langsmith",
            "--note",
            "promoted to regression",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert (
        "nextAction     reactor-admin feedback --rating thumbs_down "
        "--review-status inbox --limit 10 --output table\n" in stdout.getvalue()
    )
    assert "private user question" not in stdout.getvalue()
    assert "private model response" not in stdout.getvalue()


def test_admin_cli_feedback_review_table_surfaces_structured_next_actions() -> None:
    class StructuredReviewProbe(FakeAdminProbe):
        def patch_json(
            self,
            path: str,
            *,
            headers: dict[str, str],
            body: dict[str, object],
        ) -> AdminCliHttpResult:
            if path == "/v1/feedback/fb_1":
                self.calls.append(
                    {
                        "method": "PATCH",
                        "path": path,
                        "headers": headers,
                        "body": body,
                    }
                )
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "feedbackId": "fb_1",
                        "rating": "thumbs_down",
                        "reviewStatus": "inbox",
                        "version": 2,
                        "runId": "run_1",
                        "nextActions": [
                            {
                                "id": "sync-langsmith",
                                "label": "Sync the promoted eval to LangSmith",
                                "feedbackId": "fb_1",
                                "reportFile": "reports/langsmith-eval-sync-dry-run.json",
                                "suiteFile": "suite.json",
                                "datasetName": "reactor-regression",
                                "readinessReportArg": (
                                    "--readiness-report "
                                    "langsmith_eval_sync=reports/langsmith-eval-sync-dry-run.json"
                                ),
                                "requiredReadinessReports": ["langsmith_eval_sync"],
                                "readinessReports": {
                                    "langsmith_eval_sync": (
                                        "reports/langsmith-eval-sync-dry-run.json"
                                    ),
                                },
                                "command": (
                                    "uv run reactor-langsmith-eval-sync --suite-file suite.json"
                                ),
                            },
                            {
                                "id": "refresh-readiness",
                                "label": (
                                    "Refresh release readiness with the promoted LangSmith report"
                                ),
                                "reportFile": "reports/langsmith-eval-sync-dry-run.json",
                                "requiredReadinessReports": ["langsmith_eval_sync"],
                                "readinessReports": {
                                    "langsmith_eval_sync": (
                                        "reports/langsmith-eval-sync-dry-run.json"
                                    ),
                                },
                                "preflightFile": (
                                    "reports/release/release-smoke-preflight.local.json"
                                ),
                                "preflightEnvTemplate": (
                                    "reports/release/release-smoke-preflight.local.env"
                                ),
                                "replatformReadinessFile": (
                                    "reports/release/replatform-readiness.local.json"
                                ),
                                "smokePlanFile": "reports/release/release-smoke-plan.local.json",
                                "releaseEvidenceFile": "reports/release-evidence.json",
                                "releaseReadinessFile": "reports/release-readiness.json",
                                "remediationCommand": (
                                    "uv run reactor-release-smoke-run "
                                    "--readiness-report "
                                    "langsmith_eval_sync=reports/langsmith-eval-sync-dry-run.json"
                                ),
                                "readinessReportArg": (
                                    "--readiness-report "
                                    "langsmith_eval_sync=reports/langsmith-eval-sync-dry-run.json"
                                ),
                                "command": (
                                    "uv run reactor-release-smoke-run "
                                    "--readiness-report "
                                    "langsmith_eval_sync=reports/langsmith-eval-sync-dry-run.json"
                                ),
                            },
                        ],
                    },
                )
            return super().patch_json(path, headers=headers, body=body)

    probe = StructuredReviewProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-review",
            "fb_1",
            "--if-match",
            "1",
            "--note",
            "needs readiness",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert (
        "nextAction.fb_1.sync-langsmith  "
        "Sync the promoted eval to LangSmith  "
        "uv run reactor-langsmith-eval-sync --suite-file suite.json"
    ) in stdout.getvalue()
    assert ("nextAction.fb_1.sync-langsmith.suiteFile  suite.json") in stdout.getvalue()
    assert ("nextAction.fb_1.sync-langsmith.datasetName  reactor-regression") in stdout.getvalue()
    assert ("nextAction.fb_1.sync-langsmith.feedbackId  fb_1") in stdout.getvalue()
    assert (
        "nextAction.fb_1.sync-langsmith.readinessReportArg  "
        "--readiness-report langsmith_eval_sync=reports/langsmith-eval-sync-dry-run.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.fb_1.sync-langsmith.requiredReadinessReports  langsmith_eval_sync"
    ) in stdout.getvalue()
    assert (
        "nextAction.fb_1.sync-langsmith.readinessReports.langsmith_eval_sync  "
        "reports/langsmith-eval-sync-dry-run.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.fb_1.refresh-readiness.preflightFile  "
        "reports/release/release-smoke-preflight.local.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.fb_1.refresh-readiness.reportFile  reports/langsmith-eval-sync-dry-run.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.fb_1.refresh-readiness.requiredReadinessReports  langsmith_eval_sync"
    ) in stdout.getvalue()
    assert (
        "nextAction.fb_1.refresh-readiness.readinessReports.langsmith_eval_sync  "
        "reports/langsmith-eval-sync-dry-run.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.fb_1.refresh-readiness.preflightEnvTemplate  "
        "reports/release/release-smoke-preflight.local.env"
    ) in stdout.getvalue()
    assert (
        "nextAction.fb_1.refresh-readiness.replatformReadinessFile  "
        "reports/release/replatform-readiness.local.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.fb_1.refresh-readiness.smokePlanFile  "
        "reports/release/release-smoke-plan.local.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.fb_1.refresh-readiness.releaseEvidenceFile  reports/release-evidence.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.fb_1.refresh-readiness.releaseReadinessFile  reports/release-readiness.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.fb_1.refresh-readiness.remediationCommand  "
        "uv run reactor-release-smoke-run --readiness-report "
        "langsmith_eval_sync=reports/langsmith-eval-sync-dry-run.json"
    ) in stdout.getvalue()
    assert (
        "nextAction.fb_1.refresh-readiness.readinessReportArg  "
        "--readiness-report langsmith_eval_sync=reports/langsmith-eval-sync-dry-run.json"
    ) in stdout.getvalue()


def test_admin_cli_feedback_review_table_preserves_review_tag_filter() -> None:
    class TaggedReviewProbe(FakeAdminProbe):
        def patch_json(
            self,
            path: str,
            *,
            headers: dict[str, str],
            body: dict[str, object],
        ) -> AdminCliHttpResult:
            if path == "/v1/feedback/fb_1":
                self.calls.append(
                    {
                        "method": "PATCH",
                        "path": path,
                        "headers": headers,
                        "body": body,
                    }
                )
                return AdminCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "feedbackId": "fb_1",
                        "rating": "thumbs_down",
                        "source": "admin_cli",
                        "tags": ["documents-ask", "citation-failure"],
                        "reviewStatus": "done",
                        "reviewTags": ["promoted", "langsmith"],
                        "version": 2,
                        "runId": "run_1",
                        "nextActions": [],
                    },
                )
            return super().patch_json(path, headers=headers, body=body)

    probe = TaggedReviewProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "feedback-review",
            "fb_1",
            "--if-match",
            "1",
            "--status",
            "done",
            "--tag",
            "citation-failure",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert (
        "nextAction     reactor-admin feedback --rating thumbs_down --review-status inbox "
        "--source admin_cli --tag documents-ask --tag citation-failure --limit 10 --output table\n"
    ) in stdout.getvalue()
    assert "--tag promoted" not in stdout.getvalue()


def test_admin_cli_diagnostics_can_render_operator_table_output() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "diagnostics",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "SECTION         OK    STATUS  SUMMARY\n"
        "healthz         true  200     ok\n"
        "readyz          true  200     ready checks=2\n"
        "platformHealth  true  200     alerts=1 buffer=0.0 drops=0.0 latencyMs=0.0 "
        "cacheHits=5 cacheMisses=5\n"
        "capabilities    true  200     paths=3\n"
    )


def test_admin_cli_diagnostics_can_include_eval_dashboard_summary() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN_MANAGER",
            "diagnostics",
            "--include-evals",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    body = json.loads(stdout.getvalue())
    assert body["evals"] == {
        "ok": True,
        "statusCode": 200,
        "runs": {
            "ok": True,
            "statusCode": 200,
            "body": [
                {
                    "eval_run_id": "eval_run_1",
                    "total_cases": 2,
                    "pass_count": 1,
                    "avg_score": 0.65,
                }
            ],
            "runCount": 1,
        },
        "passRate": {
            "ok": True,
            "statusCode": 200,
            "body": {"total_cases": 2, "pass_count": 1, "pass_rate": 0.5},
        },
    }
    assert [call["path"] for call in probe.calls[-2:]] == [
        "/api/admin/evals/runs?days=30&limit=5",
        "/api/admin/evals/pass-rate?days=30",
    ]


def test_admin_cli_diagnostics_table_can_include_eval_dashboard_summary() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "diagnostics",
            "--include-evals",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert (
        "evals           true  200     runs=1 latestRun=eval_run_1 avgScore=0.65 "
        "passRate=0.5 cases=2 passed=1 failed=1 "
        "nextAction='reactor-admin feedback --rating thumbs_down "
        "--review-status inbox --limit 10 --output table'\n"
    ) in stdout.getvalue()


def test_admin_cli_diagnostics_can_include_tenant_dashboard_summary() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN_MANAGER",
            "diagnostics",
            "--include-tenant-dashboard",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    body = json.loads(stdout.getvalue())
    assert body["tenantDashboard"] == {
        "ok": True,
        "statusCode": 200,
        "overview": {
            "ok": True,
            "statusCode": 200,
            "body": {
                "totalRequests": 7,
                "successRate": 0.857143,
                "avgResponseTimeMs": 240,
                "monthlyCost": "0.00300000",
                "activeAlerts": 1,
            },
        },
        "usage": {
            "ok": True,
            "statusCode": 200,
            "body": {
                "channelDistribution": {"slack": 4, "api": 3},
                "topUsers": [{"userLabel": "operator_1", "requestCount": 5}],
            },
        },
        "quality": {
            "ok": True,
            "statusCode": 200,
            "body": {
                "latencyP50": 120,
                "latencyP95": 360,
                "errorDistribution": {"timeout": 1},
            },
        },
        "tools": {
            "ok": True,
            "statusCode": 200,
            "body": {
                "toolRanking": [{"toolName": "search", "calls": 3, "successRate": 0.666667}],
                "statusCounts": {"succeeded": 2, "failed": 1},
            },
        },
        "cost": {
            "ok": True,
            "statusCode": 200,
            "body": {
                "monthlyCost": "0.00300000",
                "costByModel": {"gpt-5-mini": "0.00100000"},
            },
        },
    }
    assert [call["path"] for call in probe.calls[-5:]] == [
        "/api/admin/tenant/overview",
        "/api/admin/tenant/usage",
        "/api/admin/tenant/quality",
        "/api/admin/tenant/tools",
        "/api/admin/tenant/cost",
    ]


def test_admin_cli_diagnostics_table_can_include_tenant_dashboard_summary() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "diagnostics",
            "--include-tenant-dashboard",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert (
        "tenantDashboard  true  200     requests=7 successRate=0.857143 "
        "latencyP95=360 alerts=1 tools=1 monthlyCost=0.00300000\n"
    ) in stdout.getvalue()


def test_admin_cli_diagnostics_can_include_slack_activity_summary() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "--role",
            "ADMIN",
            "diagnostics",
            "--include-slack-activity",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    body = json.loads(stdout.getvalue())
    assert body["slackActivity"] == {
        "ok": True,
        "statusCode": 200,
        "days": 30,
        "channels": {
            "ok": True,
            "statusCode": 200,
            "body": [
                {
                    "channel": "C123",
                    "session_count": 2,
                    "unique_users": 2,
                    "total_tokens": 150,
                    "total_cost_usd": "0.0150",
                    "avg_latency_ms": 240,
                }
            ],
            "channelCount": 1,
        },
        "daily": {
            "ok": True,
            "statusCode": 200,
            "body": [
                {
                    "date": "2026-07-01",
                    "message_count": 3,
                    "unique_users": 2,
                    "success_count": 2,
                    "failure_count": 1,
                }
            ],
            "dayCount": 1,
        },
    }
    assert [call["path"] for call in probe.calls[-2:]] == [
        "/api/admin/slack-activity/channels?days=30",
        "/api/admin/slack-activity/daily?days=30",
    ]


def test_admin_cli_diagnostics_table_can_include_slack_activity_summary() -> None:
    probe = FakeAdminProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "diagnostics",
            "--include-slack-activity",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert (
        "slackActivity   true  200     channels=1 sessions=2 messages=3 failures=1 "
        "cost=0.0150 topChannel=C123 "
        "slackChannelAction='curl /api/admin/slack-activity/channels?days=30'\n"
    ) in stdout.getvalue()


def test_admin_cli_diagnostics_fails_when_readiness_is_not_ready() -> None:
    class NotReadyProbe(FakeAdminProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
            if path == "/readyz":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return AdminCliHttpResult(
                    ok=False,
                    status_code=503,
                    error='{"status":"not_ready"}',
                )
            return super().get_json(path, headers)

    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnostics"],
        http_probe=NotReadyProbe(),
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    body = json.loads(stdout.getvalue())
    assert body["status"] == "failed"
    assert body["readyz"] == {
        "ok": False,
        "statusCode": 503,
        "error": '{"status":"not_ready"}',
    }
