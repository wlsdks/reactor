from __future__ import annotations

import shlex
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.api.app import create_app
from reactor.core.settings import Settings
from reactor.persistence.rag_ingest_store import (
    RagChunkMigrationRecord,
    RagDocumentMigrationRecord,
    RagSourceMigrationRecord,
)
from reactor.rag.document_management import managed_chunk_records_to_langchain_documents
from reactor.rag.documents import langchain_document_to_chunk_candidate
from reactor.rag.ingestion_candidates import (
    RagIngestionCandidate,
    RagIngestionCandidateStatus,
)
from reactor.release.readiness_actions import release_readiness_command_for_reports

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}
USER_HEADERS = {
    "X-Reactor-User-Id": "user_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "USER",
}


async def test_rag_ingestion_candidates_require_admin_and_configured_store() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/rag-ingestion/candidates", headers=USER_HEADERS)
        unavailable = await client.get("/api/rag-ingestion/candidates", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert forbidden.json()["error"] == "관리자 권한이 필요합니다"
    assert unavailable.status_code == 503
    assert unavailable.json()["error"] == "RagIngestionCandidateStore 미등록 — DB 미구성"


async def test_rag_ingestion_candidate_list_approve_reject_contract() -> None:
    store = FakeRagIngestionCandidateStore()
    sink = FakeRagDocumentSink()
    audits = FakeAdminAuditStore()
    pending = await store.save(
        RagIngestionCandidate(
            id="c1",
            run_id="run-c1",
            user_id="user-1",
            session_id="session-1",
            channel="Slack",
            query="release policy?",
            response="release policy answer [candidate-runbook.md]",
        )
    )
    reject_target = await store.save(
        RagIngestionCandidate(
            id="c2",
            run_id="run-c2",
            user_id="user-2",
            channel="web",
            query="benefit policy?",
            response="benefit answer",
        )
    )
    app = create_app()
    app.state.reactor = FakeContainer(
        candidate_store=store,
        rag_document_sink=sink,
        admin_audit_store=audits,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        listed = await client.get(
            "/api/rag-ingestion/candidates?status=PENDING&channel=slack",
            headers=ADMIN_HEADERS,
        )
        approved = await client.post(
            f"/v1/rag-ingestion/candidates/{pending.id}/approve",
            headers=ADMIN_HEADERS,
            json={"comment": " good "},
        )
        conflict = await client.post(
            f"/api/rag-ingestion/candidates/{pending.id}/reject",
            headers=ADMIN_HEADERS,
            json={},
        )
        rejected = await client.post(
            f"/api/rag-ingestion/candidates/{reject_target.id}/reject",
            headers=ADMIN_HEADERS,
            json={"comment": "not useful"},
        )
        tagged = await client.get(
            "/api/rag-ingestion/candidates"
            "?status=INGESTED&tag=collection:rag-ingestion-candidate&tag=rag-candidate:c1",
            headers=ADMIN_HEADERS,
        )
        collection_tagged = await client.get(
            "/api/rag-ingestion/candidates?status=INGESTED&tag=collection:rag-ingestion-candidate",
            headers=ADMIN_HEADERS,
        )

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == ["c1"]
    assert listed.json()[0]["nextAction"] == "reactor-runs diagnose run-c1 --output table"
    assert listed.json()[0]["readyNextActionIds"] == [
        "diagnose-run",
        "approve-candidate",
        "reject-candidate",
    ]
    assert listed.json()[0]["blockedNextActionIds"] == []
    assert listed.json()[0]["nextActionStates"] == {
        "diagnose-run": "ready",
        "approve-candidate": "ready",
        "reject-candidate": "ready",
    }
    assert listed.json()[0]["nextActions"] == [
        {
            "id": "diagnose-run",
            "label": "Inspect the source run before reviewing the candidate",
            "sourceRunId": "run-c1",
            "command": "reactor-runs diagnose run-c1 --output table",
        },
        {
            "id": "approve-candidate",
            "label": "Approve the candidate into the RAG candidate collection",
            "evalCaseId": "case_rag_candidate_c1",
            "sourceRunId": "run-c1",
            "command": (
                "reactor-admin rag-candidate-approve c1 "
                "--comment 'approved for RAG candidate review' --output table"
            ),
        },
        {
            "id": "reject-candidate",
            "label": "Reject the candidate with a review reason",
            "evalCaseId": "case_rag_candidate_c1",
            "sourceRunId": "run-c1",
            "command": (
                "reactor-admin rag-candidate-reject c1 "
                "--comment 'not useful for RAG grounding' --output table"
            ),
        },
    ]
    assert approved.status_code == 200
    assert approved.json()["status"] == "INGESTED"
    assert approved.json()["reviewedBy"] == "admin_1"
    assert approved.json()["reviewComment"] == "good"
    assert approved.json()["ingestedDocumentId"] is not None
    assert approved.json()["readyNextActionIds"] == [
        "submit-feedback",
        "ask-and-apply-eval",
    ]
    assert approved.json()["blockedNextActionIds"] == [
        "inspect-submitted-feedback",
        "export-feedback",
        "bulk-review-candidate-feedback",
        "promote-eval",
        "persist-eval-suite",
        "summarize-langsmith",
        "preflight-langsmith",
        "sync-langsmith",
        "generate-hardening-suite",
        "inspect-candidate-feedback",
        "refresh-readiness",
    ]
    assert approved.json()["nextActionStates"] == {
        "submit-feedback": "ready",
        "inspect-submitted-feedback": "blocked",
        "export-feedback": "blocked",
        "bulk-review-candidate-feedback": "blocked",
        "ask-and-apply-eval": "ready",
        "promote-eval": "blocked",
        "persist-eval-suite": "blocked",
        "summarize-langsmith": "blocked",
        "preflight-langsmith": "blocked",
        "sync-langsmith": "blocked",
        "generate-hardening-suite": "blocked",
        "inspect-candidate-feedback": "blocked",
        "refresh-readiness": "blocked",
    }
    release_readiness_command = release_readiness_command_for_reports(
        required_reports=["hardening_suite", "langsmith_eval_sync"],
        report_files={
            "hardening_suite": "reports/hardening-suite.json",
            "langsmith_eval_sync": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
            ),
        },
    )
    feedback_review_args = (
        "--feedback-review-status done "
        "--feedback-review-tag promoted "
        "--feedback-review-tag langsmith "
        "--feedback-review-tag expected-citation:candidate-runbook.md "
        "--feedback-review-tag collection:rag-ingestion-candidate "
        "--feedback-review-tag rag-candidate:c1 "
        "--feedback-review-note 'Promoted to regression eval and reviewed in hardening/LangSmith. "
        "Required readiness reports: hardening_suite, langsmith_eval_sync.' "
    )
    assert approved.json()["nextActions"] == [
        {
            "id": "submit-feedback",
            "label": "Submit candidate answer feedback before eval promotion",
            "evalCaseId": "case_rag_candidate_c1",
            "sourceRunId": "run-c1",
            "feedbackRating": "thumbs_down",
            "feedbackSource": "admin_cli",
            "workflowTags": [
                "collection:rag-ingestion-candidate",
                "rag-candidate:c1",
                "expected-citation:candidate-runbook.md",
                "documents-ask",
                "rag",
                "grounding",
            ],
            "feedbackTags": [
                "collection:rag-ingestion-candidate",
                "rag-candidate:c1",
                "expected-citation:candidate-runbook.md",
                "documents-ask",
                "rag",
                "grounding",
            ],
            "command": (
                "reactor-admin feedback-submit --rating thumbs_down "
                "--run-id run-c1 --query 'release policy?' "
                "--response 'release policy answer [candidate-runbook.md]' "
                "--comment 'Approved RAG candidate answer needs regression review' "
                "--source admin_cli "
                "--tag collection:rag-ingestion-candidate "
                "--tag rag-candidate:c1 "
                "--tag expected-citation:candidate-runbook.md "
                "--tag documents-ask "
                "--tag rag "
                "--tag grounding "
                "--output table"
            ),
        },
        {
            "id": "inspect-submitted-feedback",
            "label": "Inspect submitted feedback for the exact eval promotion action",
            "dependsOnActionIds": ["submit-feedback"],
            "evalCaseId": "case_rag_candidate_c1",
            "sourceRunId": "run-c1",
            "feedbackRating": "thumbs_down",
            "feedbackSource": "admin_cli",
            "workflowTags": ["collection:rag-ingestion-candidate", "rag-candidate:c1"],
            "feedbackTags": ["collection:rag-ingestion-candidate", "rag-candidate:c1"],
            "command": (
                "reactor-admin feedback --rating thumbs_down "
                "--source admin_cli "
                "--review-status inbox "
                "--tag collection:rag-ingestion-candidate "
                "--tag rag-candidate:c1 --limit 10 --output table"
            ),
        },
        {
            "id": "export-feedback",
            "label": "Export filtered feedback handoff artifact with eval/review actions",
            "dependsOnActionIds": ["submit-feedback"],
            "evalCaseId": "case_rag_candidate_c1",
            "sourceRunId": "run-c1",
            "feedbackRating": "thumbs_down",
            "feedbackSource": "admin_cli",
            "workflowTags": ["collection:rag-ingestion-candidate", "rag-candidate:c1"],
            "feedbackTags": ["collection:rag-ingestion-candidate", "rag-candidate:c1"],
            "command": (
                "reactor-admin feedback-export --rating thumbs_down "
                "--source admin_cli "
                "--review-status inbox "
                "--tag collection:rag-ingestion-candidate "
                "--tag rag-candidate:c1 --limit 10 --output json"
            ),
        },
        {
            "id": "bulk-review-candidate-feedback",
            "label": "Close queued feedback for this RAG candidate after eval and LangSmith review",
            "dependsOnActionIds": ["refresh-readiness"],
            "evalCaseId": "case_rag_candidate_c1",
            "sourceRunId": "run-c1",
            "candidateTag": "rag-candidate:c1",
            "reportFile": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
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
                    "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                ),
            },
            "feedbackRating": "thumbs_down",
            "feedbackSource": "admin_cli",
            "workflowTags": [
                "collection:rag-ingestion-candidate",
                "rag-candidate:c1",
                "expected-citation:candidate-runbook.md",
                "documents-ask",
                "rag",
                "grounding",
            ],
            "feedbackTags": [
                "collection:rag-ingestion-candidate",
                "rag-candidate:c1",
                "expected-citation:candidate-runbook.md",
                "documents-ask",
                "rag",
                "grounding",
            ],
            "command": (
                "reactor-admin feedback-bulk-review "
                "--candidate-tag rag-candidate:c1 --source admin_cli --status done "
                "--tag promoted --tag langsmith "
                "--tag expected-citation:candidate-runbook.md "
                "--tag collection:rag-ingestion-candidate "
                "--tag rag-candidate:c1 "
                "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
                "--output table"
            ),
        },
        {
            "id": "ask-and-apply-eval",
            "label": "Ask from the ingested candidate and apply a regression case",
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
            "suiteFile": "evals/regression/rag-ingestion-candidate.json",
            "datasetName": "reactor-rag-ingestion-candidate",
            "caseFile": "evals/cases/case_rag_candidate_c1.json",
            "runFile": "evals/runs/run_c1.json",
            "reportFile": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
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
                    "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                ),
            },
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
            "command": (
                "reactor-documents ask --collection rag-ingestion-candidate "
                "--query 'release policy?' --require-citation "
                "--eval-case-id case_rag_candidate_c1 "
                "--eval-case-file evals/cases/case_rag_candidate_c1.json "
                "--eval-run-file evals/runs/run_c1.json "
                "--feedback-rating thumbs_down "
                "--feedback-source admin_cli "
                "--feedback-tag collection:rag-ingestion-candidate "
                "--feedback-tag rag-candidate:c1 "
                "--feedback-tag expected-citation:candidate-runbook.md "
                "--feedback-tag documents-ask "
                "--feedback-tag rag "
                "--feedback-tag grounding "
                "--apply-suite-file evals/regression/rag-ingestion-candidate.json "
                "--apply-dataset-name reactor-rag-ingestion-candidate "
                "--apply-require-source-run-id "
                "--apply-require-run-file "
                "--apply-require-context-diagnostics "
                "--apply-suite-summary "
                "--langsmith-dry-run-report-file "
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json "
                "--output summary"
            ),
        },
        {
            "id": "promote-eval",
            "label": "Promote the candidate source run into the regression suite",
            "dependsOnActionIds": ["ask-and-apply-eval"],
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
            "suiteFile": "evals/regression/rag-ingestion-candidate.json",
            "datasetName": "reactor-rag-ingestion-candidate",
            "caseFile": "evals/cases/case_rag_candidate_c1.json",
            "runFile": "evals/runs/run_c1.json",
            "reportFile": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
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
                    "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                ),
            },
            "feedbackSource": "admin_cli",
            "feedbackTags": [
                "collection:rag-ingestion-candidate",
                "rag-candidate:c1",
                "expected-citation:candidate-runbook.md",
                "documents-ask",
                "rag",
                "grounding",
            ],
            "command": (
                "reactor-runs promote-eval run-c1 "
                "--case-id case_rag_candidate_c1 "
                "--case-file evals/cases/case_rag_candidate_c1.json "
                "--run-file evals/runs/run_c1.json "
                "--tag collection:rag-ingestion-candidate "
                "--tag rag-candidate:c1 "
                "--tag expected-citation:candidate-runbook.md "
                "--tag documents-ask "
                "--tag rag "
                "--tag grounding "
                "--feedback-source admin_cli "
                "--apply-suite-file evals/regression/rag-ingestion-candidate.json "
                "--apply-dataset-name reactor-rag-ingestion-candidate "
                "--apply-require-source-run-id "
                "--apply-require-run-file "
                "--apply-require-context-diagnostics "
                "--apply-suite-summary "
                "--langsmith-dry-run-report-file "
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json "
                f"{feedback_review_args}"
                "--output table"
            ),
        },
        {
            "id": "persist-eval-suite",
            "label": "Persist the candidate regression case before LangSmith sync",
            "dependsOnActionIds": ["promote-eval"],
            "evalCaseId": "case_rag_candidate_c1",
            "sourceRunId": "run-c1",
            "suiteFile": "evals/regression/rag-ingestion-candidate.json",
            "datasetName": "reactor-rag-ingestion-candidate",
            "caseFile": "evals/cases/case_rag_candidate_c1.json",
            "runFile": "evals/runs/run_c1.json",
            "reportFile": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
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
                    "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                ),
            },
            "workflowTags": [
                "collection:rag-ingestion-candidate",
                "rag-candidate:c1",
                "expected-citation:candidate-runbook.md",
                "documents-ask",
                "rag",
                "grounding",
            ],
            "command": (
                "reactor-agent-eval-apply "
                "--case-file evals/cases/case_rag_candidate_c1.json "
                "--run-file evals/runs/run_c1.json "
                "--suite-file evals/regression/rag-ingestion-candidate.json "
                "--dataset-name reactor-rag-ingestion-candidate "
                "--require-source-run-id --require-run-file --require-context-diagnostics "
                "--langsmith-dry-run-report-file "
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json "
                "--output table"
            ),
        },
        {
            "id": "summarize-langsmith",
            "label": "Regenerate LangSmith dry-run evidence from the persisted suite",
            "dependsOnActionIds": ["persist-eval-suite"],
            "evalCaseId": "case_rag_candidate_c1",
            "sourceRunId": "run-c1",
            "suiteFile": "evals/regression/rag-ingestion-candidate.json",
            "datasetName": "reactor-rag-ingestion-candidate",
            "reportFile": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
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
                    "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                ),
            },
            "workflowTags": [
                "collection:rag-ingestion-candidate",
                "rag-candidate:c1",
                "expected-citation:candidate-runbook.md",
                "documents-ask",
                "rag",
                "grounding",
            ],
            "command": (
                "reactor-agent-eval-apply "
                "--suite-file evals/regression/rag-ingestion-candidate.json "
                "--dataset-name reactor-rag-ingestion-candidate "
                "--summary "
                "--langsmith-dry-run-report-file "
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json "
                f"{feedback_review_args}"
                "--output table"
            ),
        },
        {
            "id": "preflight-langsmith",
            "label": "Preflight LangSmith credentials before syncing the candidate eval",
            "dependsOnActionIds": ["summarize-langsmith"],
            "evalCaseId": "case_rag_candidate_c1",
            "sourceRunId": "run-c1",
            "suiteFile": "evals/regression/rag-ingestion-candidate.json",
            "datasetName": "reactor-rag-ingestion-candidate",
            "reportFile": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
            ),
            "preflightFile": "reports/release/release-smoke-preflight.local.json",
            "preflightEnvTemplate": "reports/release/release-smoke-preflight.local.env",
            "releaseReadinessFile": "reports/release-readiness.json",
            "releaseReadinessCommand": release_readiness_command,
            "remediationCommand": (
                "uv run reactor-langsmith-eval-sync "
                "--suite-file evals/regression/rag-ingestion-candidate.json "
                "--dataset-name reactor-rag-ingestion-candidate "
                "--report-file artifacts/langsmith/"
                "rag-ingestion-candidate-case_rag_candidate_c1.json "
                f"{feedback_review_args}"
                "--required-readiness-report hardening_suite "
                "--required-readiness-report langsmith_eval_sync "
                "--readiness-report hardening_suite=reports/hardening-suite.json "
                "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                "rag-ingestion-candidate-case_rag_candidate_c1.json "
                "--preflight-only --output table"
            ),
            "envFileCommand": (
                "uv run reactor-langsmith-eval-sync "
                "--suite-file evals/regression/rag-ingestion-candidate.json "
                "--dataset-name reactor-rag-ingestion-candidate "
                "--report-file artifacts/langsmith/"
                "rag-ingestion-candidate-case_rag_candidate_c1.json "
                f"{feedback_review_args}"
                "--required-readiness-report hardening_suite "
                "--required-readiness-report langsmith_eval_sync "
                "--readiness-report hardening_suite=reports/hardening-suite.json "
                "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                "rag-ingestion-candidate-case_rag_candidate_c1.json "
                "--preflight-only --output table "
                "--env-file reports/release/release-smoke-preflight.local.env"
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
                    "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                ),
            },
            "requiredEnvAnyOf": [["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]],
            "recommendedEnv": ["LANGSMITH_ENDPOINT"],
            "command": (
                "uv run reactor-langsmith-eval-sync "
                "--suite-file evals/regression/rag-ingestion-candidate.json "
                "--dataset-name reactor-rag-ingestion-candidate "
                "--report-file artifacts/langsmith/"
                "rag-ingestion-candidate-case_rag_candidate_c1.json "
                f"{feedback_review_args}"
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
            "dependsOnActionIds": ["preflight-langsmith"],
            "evalCaseId": "case_rag_candidate_c1",
            "sourceRunId": "run-c1",
            "suiteFile": "evals/regression/rag-ingestion-candidate.json",
            "datasetName": "reactor-rag-ingestion-candidate",
            "reportFile": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
            ),
            "preflightFile": "reports/release/release-smoke-preflight.local.json",
            "preflightEnvTemplate": "reports/release/release-smoke-preflight.local.env",
            "releaseReadinessFile": "reports/release-readiness.json",
            "releaseReadinessCommand": release_readiness_command,
            "remediationCommand": (
                "uv run reactor-langsmith-eval-sync "
                "--suite-file evals/regression/rag-ingestion-candidate.json "
                "--dataset-name reactor-rag-ingestion-candidate "
                "--report-file artifacts/langsmith/"
                "rag-ingestion-candidate-case_rag_candidate_c1.json "
                f"{feedback_review_args}"
                "--required-readiness-report hardening_suite "
                "--required-readiness-report langsmith_eval_sync "
                "--readiness-report hardening_suite=reports/hardening-suite.json "
                "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                "rag-ingestion-candidate-case_rag_candidate_c1.json "
                "--output table"
            ),
            "envFileCommand": (
                "uv run reactor-langsmith-eval-sync "
                "--suite-file evals/regression/rag-ingestion-candidate.json "
                "--dataset-name reactor-rag-ingestion-candidate "
                "--report-file artifacts/langsmith/"
                "rag-ingestion-candidate-case_rag_candidate_c1.json "
                f"{feedback_review_args}"
                "--required-readiness-report hardening_suite "
                "--required-readiness-report langsmith_eval_sync "
                "--readiness-report hardening_suite=reports/hardening-suite.json "
                "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                "rag-ingestion-candidate-case_rag_candidate_c1.json "
                "--output table "
                "--env-file reports/release/release-smoke-preflight.local.env"
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
                    "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                ),
            },
            "requiredEnvAnyOf": [["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]],
            "recommendedEnv": ["LANGSMITH_ENDPOINT"],
            "command": (
                "uv run reactor-langsmith-eval-sync "
                "--suite-file evals/regression/rag-ingestion-candidate.json "
                "--dataset-name reactor-rag-ingestion-candidate "
                "--report-file artifacts/langsmith/"
                "rag-ingestion-candidate-case_rag_candidate_c1.json "
                f"{feedback_review_args}"
                "--required-readiness-report hardening_suite "
                "--required-readiness-report langsmith_eval_sync "
                "--readiness-report hardening_suite=reports/hardening-suite.json "
                "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                "rag-ingestion-candidate-case_rag_candidate_c1.json "
                "--output table"
            ),
        },
        {
            "id": "generate-hardening-suite",
            "label": "Generate the hardening suite report required for minor boundary review",
            "dependsOnActionIds": ["summarize-langsmith"],
            "evalCaseId": "case_rag_candidate_c1",
            "sourceRunId": "run-c1",
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
                    "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                ),
            },
            "releaseReadinessCommand": release_readiness_command,
            "command": "uv run reactor-hardening-suite --report-file reports/hardening-suite.json",
        },
        {
            "id": "inspect-candidate-feedback",
            "label": "Review feedback promoted from the candidate eval",
            "dependsOnActionIds": ["sync-langsmith"],
            "evalCaseId": "case_rag_candidate_c1",
            "sourceRunId": "run-c1",
            "feedbackRating": "thumbs_down",
            "feedbackSource": "admin_cli",
            "workflowTags": ["collection:rag-ingestion-candidate", "rag-candidate:c1"],
            "feedbackTags": ["collection:rag-ingestion-candidate", "rag-candidate:c1"],
            "command": (
                "reactor-admin feedback --rating thumbs_down "
                "--source admin_cli "
                "--review-status inbox "
                "--tag collection:rag-ingestion-candidate "
                "--tag rag-candidate:c1 --limit 10 --output table"
            ),
        },
        {
            "id": "refresh-readiness",
            "label": ("Refresh release readiness with candidate LangSmith and hardening reports"),
            "dependsOnActionIds": ["generate-hardening-suite", "sync-langsmith"],
            "evalCaseId": "case_rag_candidate_c1",
            "sourceRunId": "run-c1",
            "suiteFile": "evals/regression/rag-ingestion-candidate.json",
            "datasetName": "reactor-rag-ingestion-candidate",
            "reportFile": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
            ),
            "replatformReadinessFile": "reports/release/replatform-readiness.local.json",
            "smokePlanFile": "reports/release/release-smoke-plan.local.json",
            "preflightFile": "reports/release/release-smoke-preflight.local.json",
            "preflightEnvTemplate": "reports/release/release-smoke-preflight.local.env",
            "releaseEvidenceFile": "reports/release-evidence.json",
            "releaseReadinessFile": "reports/release-readiness.json",
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
                "--readiness-report "
                "langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
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
                "--readiness-report "
                "langsmith_eval_sync=artifacts/langsmith/"
                "rag-ingestion-candidate-case_rag_candidate_c1.json"
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
                    "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                ),
            },
            "latestTagCommand": "git describe --tags --abbrev=0",
            "recommendedTagSource": "release_readiness.tagRecommendation.recommendedTag",
            "minorBoundaryReports": ["hardening_suite", "langsmith_eval_sync"],
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
                "--readiness-report "
                "langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
            ),
        },
    ]
    assert approved.json()["nextAction"] == (
        "reactor-admin feedback-submit --rating thumbs_down "
        "--run-id run-c1 --query 'release policy?' "
        "--response 'release policy answer [candidate-runbook.md]' "
        "--comment 'Approved RAG candidate answer needs regression review' "
        "--source admin_cli "
        "--tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:c1 "
        "--tag expected-citation:candidate-runbook.md "
        "--tag documents-ask "
        "--tag rag "
        "--tag grounding "
        "--output table"
    )
    assert "&&" not in approved.json()["nextAction"]
    assert "--feedback-id fb_rag_candidate_c1" not in approved.json()["nextAction"]
    assert "VERIFY_TIMESTAMP" not in approved.json()["nextAction"]
    assert sink.sources[0].collection == "rag-ingestion-candidate"
    assert sink.sources[0].metadata["candidate_id"] == "c1"
    assert sink.sources[0].metadata["evalCaseId"] == "case_rag_candidate_c1"
    assert sink.sources[0].metadata["workflowTags"] == [
        "collection:rag-ingestion-candidate",
        "rag-candidate:c1",
    ]
    assert sink.sources[0].metadata["acl"] == {"visibility": "tenant"}
    assert sink.sources[0].metadata["acl_visibility"] == "tenant"
    assert isinstance(sink.sources[0].metadata["acl_hash"], str)
    assert sink.chunks[0].metadata["acl"] == {"visibility": "tenant"}
    assert sink.chunks[0].metadata["acl_visibility"] == "tenant"
    assert sink.chunks[0].metadata["acl_hash"] == sink.sources[0].metadata["acl_hash"]
    assert sink.chunks[0].metadata["source_uri"] == "rag-ingestion-candidate:c1"
    assert sink.chunks[0].metadata["evalCaseId"] == "case_rag_candidate_c1"
    assert sink.chunks[0].metadata["workflowTags"] == [
        "collection:rag-ingestion-candidate",
        "rag-candidate:c1",
    ]
    assert sink.chunks[0].metadata["parent_document_id"] == approved.json()["ingestedDocumentId"]
    assert (
        sink.chunks[0].content
        == "Q: release policy?\n\nA: release policy answer [candidate-runbook.md]"
    )
    documents = managed_chunk_records_to_langchain_documents(sink.chunks)
    restored = langchain_document_to_chunk_candidate(documents[0])
    assert restored.tenant_id == "tenant_1"
    assert restored.collection == "rag-ingestion-candidate"
    assert restored.document_id == approved.json()["ingestedDocumentId"]
    assert restored.chunk_index == 0
    assert restored.content_hash == sink.chunks[0].content_hash
    assert restored.metadata["source_uri"] == "rag-ingestion-candidate:c1"
    assert restored.metadata["evalCaseId"] == "case_rag_candidate_c1"
    assert restored.metadata["workflowTags"] == [
        "collection:rag-ingestion-candidate",
        "rag-candidate:c1",
    ]
    assert restored.metadata["acl_visibility"] == "tenant"
    assert restored.metadata["parent_document_id"] == approved.json()["ingestedDocumentId"]
    assert conflict.status_code == 409
    assert conflict.json()["error"] == "Candidate is already reviewed"
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert "nextAction" not in rejected.json()
    assert tagged.status_code == 200
    assert [item["id"] for item in tagged.json()] == ["c1"]
    assert tagged.json()[0]["nextAction"] == approved.json()["nextAction"]
    assert tagged.json()[0]["nextActions"][0]["command"] == approved.json()["nextAction"]
    assert "--source admin_cli" in tagged.json()[0]["nextAction"]
    tagged_refresh_action = tagged.json()[0]["nextActions"][-1]
    assert tagged_refresh_action["id"] == "refresh-readiness"
    assert "recommendedVersionBump" not in tagged_refresh_action
    assert "recommendedTagPattern" not in tagged_refresh_action
    assert tagged_refresh_action["minorBoundaryReports"] == [
        "hardening_suite",
        "langsmith_eval_sync",
    ]
    assert (
        tagged_refresh_action["recommendedTagSource"]
        == "release_readiness.tagRecommendation.recommendedTag"
    )
    assert collection_tagged.status_code == 200
    assert [item["id"] for item in collection_tagged.json()] == ["c1"]
    assert [audit.action for audit in audits.saved] == [
        AdminAuditAction.APPROVE,
        AdminAuditAction.REJECT,
    ]
    approval_detail = audits.saved[0].detail
    assert approval_detail is not None
    assert approval_detail == (
        "runId=run-c1, candidateId=c1, collection=rag-ingestion-candidate, "
        "sourceUri=rag-ingestion-candidate:c1, evalCaseId=case_rag_candidate_c1, "
        f"documentId={approved.json()['ingestedDocumentId']}"
    )
    assert "release policy?" not in approval_detail
    assert "release policy answer" not in approval_detail


async def test_ingested_rag_candidate_next_actions_shell_quote_run_and_answer_text() -> None:
    store = FakeRagIngestionCandidateStore()
    sink = FakeRagDocumentSink()
    candidate = await store.save(
        RagIngestionCandidate(
            id="quote-candidate",
            run_id="run quote; rm -rf /",
            user_id="user-1",
            channel="slack",
            query="What's the release policy; echo nope?",
            response="Use citation 'A' && never run shell.",
        )
    )
    app = create_app()
    app.state.reactor = FakeContainer(candidate_store=store, rag_document_sink=sink)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        approved = await client.post(
            f"/api/rag-ingestion/candidates/{candidate.id}/approve",
            headers=ADMIN_HEADERS,
            json={"comment": "good"},
        )

    assert approved.status_code == 200
    actions = {action["id"]: action for action in approved.json()["nextActions"]}
    submit_feedback_argv = shlex.split(actions["submit-feedback"]["command"])
    ask_and_apply_argv = shlex.split(actions["ask-and-apply-eval"]["command"])
    promote_eval_argv = shlex.split(actions["promote-eval"]["command"])
    assert submit_feedback_argv[submit_feedback_argv.index("--run-id") + 1] == (
        "run quote; rm -rf /"
    )
    assert submit_feedback_argv[submit_feedback_argv.index("--query") + 1] == (
        "What's the release policy; echo nope?"
    )
    assert submit_feedback_argv[submit_feedback_argv.index("--response") + 1] == (
        "Use citation 'A' && never run shell."
    )
    assert ask_and_apply_argv[ask_and_apply_argv.index("--query") + 1] == (
        "What's the release policy; echo nope?"
    )
    assert ask_and_apply_argv[ask_and_apply_argv.index("--eval-run-file") + 1] == (
        "evals/runs/run_quote_rm_rf.json"
    )
    assert "--apply-dry-run" not in ask_and_apply_argv
    assert promote_eval_argv[:3] == [
        "reactor-runs",
        "promote-eval",
        "run quote; rm -rf /",
    ]
    assert promote_eval_argv[promote_eval_argv.index("--case-id") + 1] == (
        "case_rag_candidate_quote_candidate"
    )
    assert promote_eval_argv[promote_eval_argv.index("--case-file") + 1] == (
        "evals/cases/case_rag_candidate_quote_candidate.json"
    )
    assert promote_eval_argv[promote_eval_argv.index("--run-file") + 1] == (
        "evals/runs/run_quote_rm_rf.json"
    )
    assert "--apply-require-context-diagnostics" in promote_eval_argv
    assert "--apply-suite-summary" in promote_eval_argv
    feedback_tags = [
        value
        for index, value in enumerate(ask_and_apply_argv)
        if index > 0 and ask_and_apply_argv[index - 1] == "--feedback-tag"
    ]
    assert feedback_tags == [
        "collection:rag-ingestion-candidate",
        "rag-candidate:quote_candidate",
        "documents-ask",
        "rag",
        "grounding",
    ]


async def test_rag_ingestion_candidate_openapi_names_next_action_contract() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(candidate_store=FakeRagIngestionCandidateStore())
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/openapi.json")

    schemas = response.json()["components"]["schemas"]
    assert schemas["RagIngestionCandidateNextAction"]["required"] == [
        "id",
        "label",
        "command",
    ]
    assert schemas["RagIngestionCandidateNextAction"]["properties"] == {
        "id": {"type": "string", "minLength": 1, "title": "Id"},
        "label": {"type": "string", "minLength": 1, "title": "Label"},
        "command": {"type": "string", "minLength": 1, "title": "Command"},
        "evalCaseId": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Evalcaseid",
        },
        "sourceRunId": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Sourcerunid",
        },
        "candidateTag": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Candidatetag",
        },
        "workflowTags": {
            "anyOf": [
                {"items": {"type": "string"}, "type": "array"},
                {"type": "null"},
            ],
            "title": "Workflowtags",
        },
        "reportFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Reportfile",
        },
        "caseFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Casefile",
        },
        "runFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Runfile",
        },
        "suiteFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Suitefile",
        },
        "datasetName": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Datasetname",
        },
        "feedbackRating": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Feedbackrating",
        },
        "feedbackSource": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Feedbacksource",
        },
        "feedbackTags": {
            "anyOf": [
                {"items": {"type": "string"}, "type": "array"},
                {"type": "null"},
            ],
            "title": "Feedbacktags",
        },
        "preflightFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Preflightfile",
        },
        "preflightEnvTemplate": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Preflightenvtemplate",
        },
        "replatformReadinessFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Replatformreadinessfile",
        },
        "smokePlanFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Smokeplanfile",
        },
        "releaseEvidenceFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Releaseevidencefile",
        },
        "releaseReadinessFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Releasereadinessfile",
        },
        "releaseReadinessCommand": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Releasereadinesscommand",
        },
        "remediationCommand": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Remediationcommand",
        },
        "envFileCommand": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Envfilecommand",
        },
        "readinessReportArg": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Readinessreportarg",
        },
        "requiredReadinessReports": {
            "anyOf": [
                {"items": {"type": "string"}, "type": "array", "minItems": 1},
                {"type": "null"},
            ],
            "title": "Requiredreadinessreports",
        },
        "readinessReports": {
            "anyOf": [
                {
                    "additionalProperties": {"type": "string"},
                    "type": "object",
                    "minProperties": 1,
                },
                {"type": "null"},
            ],
            "title": "Readinessreports",
        },
        "requiredEnvAnyOf": {
            "anyOf": [
                {
                    "items": {"items": {"type": "string"}, "type": "array"},
                    "type": "array",
                    "minItems": 1,
                },
                {"type": "null"},
            ],
            "title": "Requiredenvanyof",
        },
        "missingEnvAnyOf": {
            "anyOf": [
                {"items": {"type": "string"}, "type": "array", "minItems": 1},
                {"type": "null"},
            ],
            "title": "Missingenvanyof",
        },
        "recommendedEnv": {
            "anyOf": [
                {"items": {"type": "string"}, "type": "array", "minItems": 1},
                {"type": "null"},
            ],
            "title": "Recommendedenv",
        },
        "recommendedVersionBump": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Recommendedversionbump",
        },
        "recommendedTagPattern": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Recommendedtagpattern",
        },
        "latestTagCommand": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Latesttagcommand",
        },
        "recommendedTagSource": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Recommendedtagsource",
        },
        "minorBoundaryReports": {
            "anyOf": [
                {"items": {"type": "string"}, "type": "array", "minItems": 1},
                {"type": "null"},
            ],
            "title": "Minorboundaryreports",
        },
        "dependsOnActionIds": {
            "anyOf": [
                {"items": {"type": "string"}, "type": "array", "minItems": 1},
                {"type": "null"},
            ],
            "title": "Dependsonactionids",
        },
    }
    candidate_response = schemas["RagIngestionCandidateResponse"]
    next_actions = candidate_response["properties"]["nextActions"]
    assert next_actions["items"] == {"$ref": "#/components/schemas/RagIngestionCandidateNextAction"}


async def test_rag_ingestion_candidate_approve_requires_vector_sink_and_pending_status() -> None:
    store = FakeRagIngestionCandidateStore()
    candidate = await store.save(
        RagIngestionCandidate(
            id="missing-sink",
            run_id="run-missing-sink",
            user_id="user-1",
            query="q",
            response="a",
        )
    )
    app = create_app()
    app.state.reactor = FakeContainer(candidate_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        missing = await client.post(
            "/api/rag-ingestion/candidates/nope/approve",
            headers=ADMIN_HEADERS,
            json={},
        )
        no_sink = await client.post(
            f"/api/rag-ingestion/candidates/{candidate.id}/approve",
            headers=ADMIN_HEADERS,
            json={},
        )

    assert missing.status_code == 404
    assert missing.json()["error"] == "Candidate not found: nope"
    assert no_sink.status_code == 503
    assert no_sink.json()["error"] == "VectorStore is not configured"
    unchanged = await store.find_by_id(candidate.id)
    assert unchanged is not None
    assert unchanged.status == RagIngestionCandidateStatus.PENDING


async def test_rag_ingestion_candidate_approve_retry_returns_ingested_candidate() -> None:
    reviewed_at = datetime(2026, 6, 26, tzinfo=UTC)
    store = FakeRagIngestionCandidateStore()
    candidate = await store.save(
        RagIngestionCandidate(
            id="already-ingested",
            run_id="run-ingested",
            user_id="user-1",
            query="q",
            response="a",
            status=RagIngestionCandidateStatus.INGESTED,
            reviewed_at=reviewed_at,
            reviewed_by="admin_1",
            review_comment="good",
            ingested_document_id="rag_doc_existing",
        )
    )
    app = create_app()
    app.state.reactor = FakeContainer(candidate_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        retry = await client.post(
            f"/api/rag-ingestion/candidates/{candidate.id}/approve",
            headers=ADMIN_HEADERS,
            json={"comment": "good"},
        )

    assert retry.status_code == 200
    assert retry.json()["id"] == "already-ingested"
    assert retry.json()["status"] == "INGESTED"
    assert retry.json()["reviewedBy"] == "admin_1"
    assert retry.json()["reviewComment"] == "good"
    assert retry.json()["ingestedDocumentId"] == "rag_doc_existing"


async def test_rag_ingestion_candidate_approve_race_returns_latest_ingested_candidate() -> None:
    class RacingCandidateStore(FakeRagIngestionCandidateStore):
        async def update_review(
            self,
            *,
            candidate_id: str,
            status: RagIngestionCandidateStatus,
            reviewed_by: str,
            review_comment: str | None,
            ingested_document_id: str | None = None,
        ) -> RagIngestionCandidate | None:
            existing = self.records[candidate_id]
            self.records[candidate_id] = existing.with_review(
                status=RagIngestionCandidateStatus.INGESTED,
                reviewed_by="other-admin",
                review_comment="other approval",
                ingested_document_id="rag_doc_race",
            )
            return None

    store = RacingCandidateStore()
    sink = FakeRagDocumentSink()
    candidate = await store.save(
        RagIngestionCandidate(
            id="race-approve",
            run_id="run-race-approve",
            user_id="user-1",
            query="q",
            response="a",
        )
    )
    app = create_app()
    app.state.reactor = FakeContainer(candidate_store=store, rag_document_sink=sink)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            f"/api/rag-ingestion/candidates/{candidate.id}/approve",
            headers=ADMIN_HEADERS,
            json={"comment": "good"},
        )

    assert response.status_code == 200
    assert response.json()["id"] == "race-approve"
    assert response.json()["status"] == "INGESTED"
    assert response.json()["reviewedBy"] == "other-admin"
    assert response.json()["reviewComment"] == "other approval"
    assert response.json()["ingestedDocumentId"] == "rag_doc_race"


async def test_rag_ingestion_candidate_reject_retry_returns_rejected_candidate() -> None:
    reviewed_at = datetime(2026, 6, 26, tzinfo=UTC)
    store = FakeRagIngestionCandidateStore()
    candidate = await store.save(
        RagIngestionCandidate(
            id="already-rejected",
            run_id="run-rejected",
            user_id="user-1",
            query="q",
            response="a",
            status=RagIngestionCandidateStatus.REJECTED,
            reviewed_at=reviewed_at,
            reviewed_by="admin_1",
            review_comment="not useful",
        )
    )
    app = create_app()
    app.state.reactor = FakeContainer(candidate_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        retry = await client.post(
            f"/api/rag-ingestion/candidates/{candidate.id}/reject",
            headers=ADMIN_HEADERS,
            json={"comment": "not useful"},
        )

    assert retry.status_code == 200
    assert retry.json()["id"] == "already-rejected"
    assert retry.json()["status"] == "REJECTED"
    assert retry.json()["reviewedBy"] == "admin_1"
    assert retry.json()["reviewComment"] == "not useful"
    assert "ingestedDocumentId" not in retry.json()


async def test_rag_ingestion_candidate_reject_race_returns_latest_rejected_candidate() -> None:
    class RacingCandidateStore(FakeRagIngestionCandidateStore):
        async def update_review(
            self,
            *,
            candidate_id: str,
            status: RagIngestionCandidateStatus,
            reviewed_by: str,
            review_comment: str | None,
            ingested_document_id: str | None = None,
        ) -> RagIngestionCandidate | None:
            existing = self.records[candidate_id]
            self.records[candidate_id] = existing.with_review(
                status=RagIngestionCandidateStatus.REJECTED,
                reviewed_by="other-admin",
                review_comment="other rejection",
            )
            return None

    store = RacingCandidateStore()
    candidate = await store.save(
        RagIngestionCandidate(
            id="race-reject",
            run_id="run-race-reject",
            user_id="user-1",
            query="q",
            response="a",
        )
    )
    app = create_app()
    app.state.reactor = FakeContainer(candidate_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            f"/api/rag-ingestion/candidates/{candidate.id}/reject",
            headers=ADMIN_HEADERS,
            json={"comment": "not useful"},
        )

    assert response.status_code == 200
    assert response.json()["id"] == "race-reject"
    assert response.json()["status"] == "REJECTED"
    assert response.json()["reviewedBy"] == "other-admin"
    assert response.json()["reviewComment"] == "other rejection"


class FakeContainer:
    def __init__(
        self,
        *,
        candidate_store: FakeRagIngestionCandidateStore | None = None,
        rag_document_sink: FakeRagDocumentSink | None = None,
        admin_audit_store: FakeAdminAuditStore | None = None,
    ) -> None:
        self.settings = Settings()
        self._candidate_store = candidate_store
        self._rag_document_sink = rag_document_sink
        self._admin_audit_store = admin_audit_store

    def rag_ingestion_candidate_store(self) -> FakeRagIngestionCandidateStore | None:
        return self._candidate_store

    def faq_document_sink(self) -> FakeRagDocumentSink | None:
        return self._rag_document_sink

    def admin_audit_store(self) -> FakeAdminAuditStore | None:
        return self._admin_audit_store


class FakeRagIngestionCandidateStore:
    def __init__(self) -> None:
        self.records: dict[str, RagIngestionCandidate] = {}
        self.by_run_id: dict[str, str] = {}

    async def save(self, candidate: RagIngestionCandidate) -> RagIngestionCandidate:
        existing_id = self.by_run_id.get(candidate.run_id)
        if existing_id is not None:
            return self.records[existing_id]
        candidate.validate()
        self.records[candidate.id] = candidate
        self.by_run_id[candidate.run_id] = candidate.id
        return candidate

    async def find_by_id(self, candidate_id: str) -> RagIngestionCandidate | None:
        return self.records.get(candidate_id)

    async def list(
        self,
        *,
        limit: int = 100,
        status: RagIngestionCandidateStatus | None = None,
        channel: str | None = None,
        tags: list[str] | None = None,
    ) -> list[RagIngestionCandidate]:
        normalized_channel = channel.strip().lower() if channel else ""
        items = sorted(self.records.values(), key=lambda item: item.captured_at, reverse=True)
        if status is not None:
            items = [item for item in items if item.status == status]
        if normalized_channel:
            items = [
                item
                for item in items
                if item.channel is not None and item.channel.lower() == normalized_channel
            ]
        candidate_tags = set(tags or ())
        candidate_ids = [
            tag.removeprefix("rag-candidate:")
            for tag in candidate_tags
            if tag.startswith("rag-candidate:")
        ]
        if candidate_ids:
            items = [item for item in items if item.id in candidate_ids]
        return items[:limit]

    async def update_review(
        self,
        *,
        candidate_id: str,
        status: RagIngestionCandidateStatus,
        reviewed_by: str,
        review_comment: str | None,
        ingested_document_id: str | None = None,
    ) -> RagIngestionCandidate | None:
        existing = self.records.get(candidate_id)
        if existing is None:
            return None
        if existing.status != RagIngestionCandidateStatus.PENDING:
            return None
        updated = existing.with_review(
            status=status,
            reviewed_by=reviewed_by,
            review_comment=review_comment,
            ingested_document_id=ingested_document_id,
        )
        self.records[candidate_id] = updated
        return updated


class FakeRagDocumentSink:
    def __init__(self) -> None:
        self.sources: list[RagSourceMigrationRecord] = []
        self.documents: list[RagDocumentMigrationRecord] = []
        self.chunks: list[RagChunkMigrationRecord] = []

    async def save_source(self, record: RagSourceMigrationRecord) -> str:
        self.sources.append(record)
        return record.id

    async def save_document(self, record: RagDocumentMigrationRecord) -> str:
        self.documents.append(record)
        return record.id

    async def save_chunk(self, record: RagChunkMigrationRecord) -> str:
        self.chunks.append(record)
        return record.id


class FakeAdminAuditStore:
    def __init__(self) -> None:
        self.saved: list[AdminAuditLog] = []

    async def save(self, log: AdminAuditLog, *, tenant_id: str = "tenant_1") -> AdminAuditLog:
        del tenant_id
        self.saved.append(log)
        return log
