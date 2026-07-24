from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from shlex import quote
from typing import Annotated, Any, Protocol, cast

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.api.auth import principal_from_headers
from reactor.api.next_actions import (
    blocked_next_action_ids,
    next_action_states,
    ready_next_action_ids,
)
from reactor.api.schemas.rag_ingestion_candidates import (
    RagIngestionCandidateNextAction,
    RagIngestionCandidateResponse,
    ReviewRagIngestionCandidateRequest,
)
from reactor.auth.rbac import AuthPrincipal, current_actor
from reactor.core.container import AppContainer
from reactor.kernel.citations import is_citation_safe_id
from reactor.persistence.rag_ingest_store import (
    RagChunkMigrationRecord,
    RagDocumentMigrationRecord,
    RagSourceMigrationRecord,
    checksum,
    deterministic_rag_id,
)
from reactor.persistence.repositories.rag_postgres import stable_acl_hash
from reactor.rag.document_management import flatten_acl_metadata
from reactor.rag.ingestion_candidate_actions import (
    RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
    rag_candidate_eval_apply_action_command,
    rag_candidate_feedback_bulk_review_action,
)
from reactor.rag.ingestion_candidate_ids import (
    command_slug,
    rag_candidate_case_id,
    rag_candidate_workflow_tag,
)
from reactor.rag.ingestion_candidates import (
    RagIngestionCandidate,
    RagIngestionCandidateStatus,
    build_rag_candidate_content,
    epoch_millis,
    parse_candidate_status,
)
from reactor.release.readiness_actions import (
    HARDENING_SUITE_REPORT_FILE,
    LANGSMITH_SYNC_RECOMMENDED_ENV,
    LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
    LATEST_TAG_COMMAND,
    RECOMMENDED_TAG_SOURCE,
    RELEASE_EVIDENCE_FILE,
    RELEASE_READINESS_FILE,
    RELEASE_SMOKE_PLAN_FILE,
    RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
    RELEASE_SMOKE_PREFLIGHT_FILE,
    REPLATFORM_READINESS_FILE,
    env_file_command,
    rag_ingestion_lifecycle_remediation_command,
    readiness_report_args_for_reports,
    release_readiness_command_for_reports,
)

router = APIRouter(tags=["rag-ingestion-candidates"])
RAG_CANDIDATE_COLLECTION = "rag-ingestion-candidate"


class RagIngestionCandidateStore(Protocol):
    async def list(
        self,
        *,
        limit: int = 100,
        status: RagIngestionCandidateStatus | None = None,
        channel: str | None = None,
        tags: list[str] | None = None,
    ) -> list[RagIngestionCandidate]: ...

    async def find_by_id(self, candidate_id: str) -> RagIngestionCandidate | None: ...

    async def update_review(
        self,
        *,
        candidate_id: str,
        status: RagIngestionCandidateStatus,
        reviewed_by: str,
        review_comment: str | None,
        ingested_document_id: str | None = None,
    ) -> RagIngestionCandidate | None: ...


@router.get(
    "/api/rag-ingestion/candidates",
    response_model=list[RagIngestionCandidateResponse],
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
@router.get(
    "/v1/rag-ingestion/candidates",
    response_model=list[RagIngestionCandidateResponse],
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
async def list_rag_ingestion_candidates(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
    status_filter: str | None = Query(default=None, alias="status"),
    tags: Annotated[list[str] | None, Query(alias="tag")] = None,
    channel: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[RagIngestionCandidateResponse] | JSONResponse:
    permission_error = require_admin(principal)
    if permission_error is not None:
        return permission_error
    parsed_status = parse_candidate_status(status_filter)
    if status_filter is not None and parsed_status is None:
        return legacy_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            error=f"Invalid candidate status: {status_filter}",
        )
    store = require_candidate_store(request)
    if isinstance(store, JSONResponse):
        return store
    records = await store.list(limit=limit, status=parsed_status, channel=channel, tags=tags)
    return [candidate_response(record) for record in records]


@router.post(
    "/api/rag-ingestion/candidates/{candidate_id}/approve",
    response_model=RagIngestionCandidateResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
@router.post(
    "/v1/rag-ingestion/candidates/{candidate_id}/approve",
    response_model=RagIngestionCandidateResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
async def approve_rag_ingestion_candidate(
    request: Request,
    candidate_id: str,
    body: ReviewRagIngestionCandidateRequest,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> RagIngestionCandidateResponse | JSONResponse:
    permission_error = require_admin(principal)
    if permission_error is not None:
        return permission_error
    store = require_candidate_store(request)
    if isinstance(store, JSONResponse):
        return store
    candidate = await store.find_by_id(candidate_id)
    if candidate is None:
        return candidate_not_found(candidate_id)
    if (
        candidate.status == RagIngestionCandidateStatus.INGESTED
        and candidate.ingested_document_id is not None
    ):
        return candidate_response(candidate)
    if candidate.status != RagIngestionCandidateStatus.PENDING:
        return candidate_conflict()
    sink = require_rag_document_sink(request)
    if isinstance(sink, JSONResponse):
        return sink
    document_id = await ingest_candidate_document(
        sink=sink,
        tenant_id=principal.tenant_id,
        candidate=candidate,
    )
    reviewed = await store.update_review(
        candidate_id=candidate_id,
        status=RagIngestionCandidateStatus.INGESTED,
        reviewed_by=current_actor(principal),
        review_comment=trim_comment(body.comment),
        ingested_document_id=document_id,
    )
    if reviewed is None:
        return await not_found_or_reviewed_conflict(
            store,
            candidate_id,
            expected_status=RagIngestionCandidateStatus.INGESTED,
        )
    await record_candidate_audit(
        request=request,
        principal=principal,
        action=AdminAuditAction.APPROVE,
        record=reviewed,
        detail=candidate_approval_audit_detail(reviewed),
    )
    return candidate_response(reviewed)


@router.post(
    "/api/rag-ingestion/candidates/{candidate_id}/reject",
    response_model=RagIngestionCandidateResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
@router.post(
    "/v1/rag-ingestion/candidates/{candidate_id}/reject",
    response_model=RagIngestionCandidateResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
async def reject_rag_ingestion_candidate(
    request: Request,
    candidate_id: str,
    body: ReviewRagIngestionCandidateRequest,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> RagIngestionCandidateResponse | JSONResponse:
    permission_error = require_admin(principal)
    if permission_error is not None:
        return permission_error
    store = require_candidate_store(request)
    if isinstance(store, JSONResponse):
        return store
    candidate = await store.find_by_id(candidate_id)
    if candidate is None:
        return candidate_not_found(candidate_id)
    if candidate.status == RagIngestionCandidateStatus.REJECTED:
        return candidate_response(candidate)
    if candidate.status != RagIngestionCandidateStatus.PENDING:
        return candidate_conflict()
    reviewed = await store.update_review(
        candidate_id=candidate_id,
        status=RagIngestionCandidateStatus.REJECTED,
        reviewed_by=current_actor(principal),
        review_comment=trim_comment(body.comment),
    )
    if reviewed is None:
        return await not_found_or_reviewed_conflict(
            store,
            candidate_id,
            expected_status=RagIngestionCandidateStatus.REJECTED,
        )
    await record_candidate_audit(
        request=request,
        principal=principal,
        action=AdminAuditAction.REJECT,
        record=reviewed,
        detail=f"runId={reviewed.run_id}",
    )
    return candidate_response(reviewed)


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def require_admin(principal: AuthPrincipal) -> JSONResponse | None:
    if principal.is_any_admin():
        return None
    return legacy_error_response(
        status_code=status.HTTP_403_FORBIDDEN,
        error="관리자 권한이 필요합니다",
    )


def require_candidate_store(request: Request) -> RagIngestionCandidateStore | JSONResponse:
    container = get_container(request)
    accessor = getattr(container, "rag_ingestion_candidate_store", None)
    store = accessor() if accessor is not None else None
    if store is None:
        return legacy_error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error="RagIngestionCandidateStore 미등록 — DB 미구성",
        )
    return cast(RagIngestionCandidateStore, store)


def require_rag_document_sink(request: Request) -> Any | JSONResponse:
    container = get_container(request)
    accessor = getattr(container, "faq_document_sink", None)
    sink = accessor() if accessor is not None else None
    if sink is None:
        return legacy_error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error="VectorStore is not configured",
        )
    return sink


async def ingest_candidate_document(
    *,
    sink: Any,
    tenant_id: str,
    candidate: RagIngestionCandidate,
) -> str:
    now = datetime.now(UTC)
    content = build_rag_candidate_content(candidate)
    source_uri = f"rag-ingestion-candidate:{candidate.id}"
    source_id = deterministic_rag_id("rag_src", f"{tenant_id}:{source_uri}")
    document_id = deterministic_rag_id("rag_doc", f"{tenant_id}:{source_uri}")
    chunk_id = deterministic_rag_id("rag_chk", f"{tenant_id}:{source_uri}:0")
    metadata = candidate_metadata(candidate, source_uri=source_uri)
    metadata["parent_document_id"] = document_id
    acl = {"visibility": "tenant"}
    metadata["acl"] = acl
    metadata["acl_hash"] = stable_acl_hash(acl)
    metadata.update(flatten_acl_metadata(acl))
    saved_source_id = await sink.save_source(
        RagSourceMigrationRecord(
            id=source_id,
            tenant_id=tenant_id,
            collection=RAG_CANDIDATE_COLLECTION,
            source_uri=source_uri,
            source_type=RAG_CANDIDATE_COLLECTION,
            checksum=checksum(content),
            metadata=metadata,
            created_at=now,
        )
    )
    await sink.save_document(
        RagDocumentMigrationRecord(
            id=document_id,
            tenant_id=tenant_id,
            source_id=str(saved_source_id or source_id),
            collection=RAG_CANDIDATE_COLLECTION,
            title=f"RAG ingestion candidate {candidate.run_id}",
            version=checksum(content)[:16],
            acl=acl,
            metadata=metadata,
            created_at=now,
        )
    )
    await sink.save_chunk(
        RagChunkMigrationRecord(
            id=chunk_id,
            tenant_id=tenant_id,
            document_id=document_id,
            collection=RAG_CANDIDATE_COLLECTION,
            chunk_index=0,
            content=content,
            content_hash=checksum(content),
            embedding=None,
            metadata=metadata,
            created_at=now,
        )
    )
    return document_id


def candidate_metadata(
    candidate: RagIngestionCandidate,
    *,
    source_uri: str,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "source": RAG_CANDIDATE_COLLECTION,
        "source_uri": source_uri,
        "candidate_id": candidate.id,
        "evalCaseId": rag_candidate_case_id(candidate.id),
        "workflowTags": [
            "collection:rag-ingestion-candidate",
            rag_candidate_workflow_tag(candidate.id),
        ],
        "runId": candidate.run_id,
        "userId": candidate.user_id,
        "capturedAt": candidate.captured_at.isoformat(),
    }
    if candidate.session_id is not None and candidate.session_id.strip():
        metadata["session_id"] = candidate.session_id.strip()
    if candidate.channel is not None and candidate.channel.strip():
        metadata["channel"] = candidate.channel.strip()
    return metadata


def candidate_approval_audit_detail(record: RagIngestionCandidate) -> str:
    source_uri = f"{RAG_CANDIDATE_COLLECTION}:{record.id}"
    return (
        f"runId={record.run_id}, candidateId={record.id}, collection={RAG_CANDIDATE_COLLECTION}, "
        f"sourceUri={source_uri}, evalCaseId={rag_candidate_case_id(record.id)}, "
        f"documentId={record.ingested_document_id}"
    )


async def record_candidate_audit(
    *,
    request: Request,
    principal: AuthPrincipal,
    action: AdminAuditAction,
    record: RagIngestionCandidate,
    detail: str,
) -> None:
    store = admin_audit_store(request)
    if store is None:
        return
    await store.save(
        AdminAuditLog(
            category="rag_ingestion_candidate",
            action=action,
            actor=current_actor(principal),
            resource_type="rag_ingestion_candidate",
            resource_id=record.id,
            detail=detail,
        ),
        tenant_id=principal.tenant_id,
    )


def admin_audit_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "admin_audit_store", None)
    return accessor() if accessor is not None else None


def candidate_not_found(candidate_id: str) -> JSONResponse:
    return legacy_error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        error=f"Candidate not found: {candidate_id}",
    )


def candidate_conflict() -> JSONResponse:
    return legacy_error_response(
        status_code=status.HTTP_409_CONFLICT,
        error="Candidate is already reviewed",
    )


async def not_found_or_reviewed_conflict(
    store: RagIngestionCandidateStore,
    candidate_id: str,
    *,
    expected_status: RagIngestionCandidateStatus | None = None,
) -> JSONResponse:
    latest = await store.find_by_id(candidate_id)
    if latest is None:
        return candidate_not_found(candidate_id)
    if expected_status is not None and latest.status == expected_status:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=candidate_response(latest).model_dump(by_alias=True, exclude_none=True),
        )
    return candidate_conflict()


def legacy_error_response(*, status_code: int, error: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


def trim_comment(comment: str | None) -> str | None:
    if comment is None:
        return None
    return comment.strip()


def candidate_response(record: RagIngestionCandidate) -> RagIngestionCandidateResponse:
    actions = candidate_next_actions(record)
    return RagIngestionCandidateResponse(
        id=record.id,
        runId=record.run_id,
        channel=record.channel,
        query=record.query,
        response=record.response,
        status=record.status.value,
        capturedAt=epoch_millis(record.captured_at),
        reviewedAt=epoch_millis(record.reviewed_at) if record.reviewed_at is not None else None,
        reviewedBy=record.reviewed_by,
        reviewComment=record.review_comment,
        ingestedDocumentId=record.ingested_document_id,
        nextAction=actions[0].command if actions else None,
        readyNextActionIds=ready_next_action_ids(actions),
        blockedNextActionIds=blocked_next_action_ids(actions),
        nextActionStates=next_action_states(actions),
        nextActions=actions,
    )


def candidate_next_action(record: RagIngestionCandidate) -> str | None:
    if record.status == RagIngestionCandidateStatus.PENDING:
        run_id = quote(record.run_id)
        return f"reactor-runs diagnose {run_id} --output table"
    actions = candidate_next_actions(record)
    if actions:
        return actions[0].command
    return None


def candidate_next_actions(record: RagIngestionCandidate) -> list[RagIngestionCandidateNextAction]:
    if record.status == RagIngestionCandidateStatus.PENDING:
        candidate_id = quote(record.id)
        run_id = quote(record.run_id)
        case_id = rag_candidate_case_id(record.id)
        return [
            RagIngestionCandidateNextAction(
                id="diagnose-run",
                label="Inspect the source run before reviewing the candidate",
                command=f"reactor-runs diagnose {run_id} --output table",
                sourceRunId=record.run_id,
            ),
            RagIngestionCandidateNextAction(
                id="approve-candidate",
                label="Approve the candidate into the RAG candidate collection",
                evalCaseId=case_id,
                sourceRunId=record.run_id,
                command=(
                    f"reactor-admin rag-candidate-approve {candidate_id} "
                    "--comment 'approved for RAG candidate review' --output table"
                ),
            ),
            RagIngestionCandidateNextAction(
                id="reject-candidate",
                label="Reject the candidate with a review reason",
                evalCaseId=case_id,
                sourceRunId=record.run_id,
                command=(
                    f"reactor-admin rag-candidate-reject {candidate_id} "
                    "--comment 'not useful for RAG grounding' --output table"
                ),
            ),
        ]
    return approved_candidate_next_actions(record)


def approved_candidate_next_action(record: RagIngestionCandidate) -> str | None:
    actions = approved_candidate_next_actions(record)
    return actions[0].command if actions else None


def approved_candidate_next_actions(
    record: RagIngestionCandidate,
) -> list[RagIngestionCandidateNextAction]:
    if record.status != RagIngestionCandidateStatus.INGESTED or record.ingested_document_id is None:
        return []
    suite_file = "evals/regression/rag-ingestion-candidate.json"
    dataset_name = "reactor-rag-ingestion-candidate"
    run_slug = command_slug(record.run_id)
    case_id = rag_candidate_case_id(record.id)
    case_file = f"evals/cases/{case_id}.json"
    run_file = f"evals/runs/{run_slug}.json"
    langsmith_report = f"artifacts/langsmith/rag-ingestion-candidate-{case_id}.json"
    candidate_feedback_tag = rag_candidate_workflow_tag(record.id)
    filtered_feedback_tags = ["collection:rag-ingestion-candidate", candidate_feedback_tag]
    expected_citation_tags = candidate_expected_citation_tags(record.response)
    submitted_feedback_tags = [
        *filtered_feedback_tags,
        *expected_citation_tags,
        "documents-ask",
        "rag",
        "grounding",
    ]
    candidate_feedback_review_command = (
        "reactor-admin feedback --rating thumbs_down "
        "--source admin_cli "
        "--review-status inbox "
        "--tag collection:rag-ingestion-candidate "
        f"--tag {quote(candidate_feedback_tag)} --limit 10 --output table"
    )
    candidate_feedback_export_command = (
        "reactor-admin feedback-export --rating thumbs_down "
        "--source admin_cli "
        "--review-status inbox "
        "--tag collection:rag-ingestion-candidate "
        f"--tag {quote(candidate_feedback_tag)} --limit 10 --output json"
    )
    candidate_feedback_bulk_review_command = rag_candidate_feedback_bulk_review_action(
        candidate_feedback_tag,
        source="admin_cli",
        extra_review_tags=expected_citation_tags,
    )
    feedback_review_tags = [
        "promoted",
        "langsmith",
        *expected_citation_tags,
        "collection:rag-ingestion-candidate",
        candidate_feedback_tag,
    ]
    feedback_review_args = command_feedback_review_args(
        status="done",
        tags=feedback_review_tags,
        note=RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
    )
    feedback_submit_command = (
        "reactor-admin feedback-submit --rating thumbs_down "
        f"--run-id {quote(record.run_id)} "
        f"--query {quote(record.query)} "
        f"--response {quote(record.response)} "
        "--comment 'Approved RAG candidate answer needs regression review' "
        "--source admin_cli "
        f"{admin_feedback_tag_args(submitted_feedback_tags)}"
        "--output table"
    )
    ask_command = (
        "reactor-documents ask --collection rag-ingestion-candidate "
        f"--query {quote(record.query)} --require-citation "
        f"--eval-case-id {case_id} "
        f"--eval-case-file {case_file} "
        f"--eval-run-file {run_file} "
        "--feedback-rating thumbs_down "
        "--feedback-source admin_cli "
        f"{command_feedback_tag_args(submitted_feedback_tags)}"
        "--apply-suite-file evals/regression/rag-ingestion-candidate.json "
        "--apply-dataset-name reactor-rag-ingestion-candidate "
        "--apply-require-source-run-id "
        "--apply-require-run-file "
        "--apply-require-context-diagnostics "
        "--apply-suite-summary "
        "--langsmith-dry-run-report-file "
        f"{langsmith_report} "
        "--output summary"
    )
    promote_eval_command = rag_candidate_eval_apply_action_command(
        source_run_id=record.run_id,
        case_id=case_id,
        source_suite=suite_file,
        dataset_name=dataset_name,
        feedback_source="admin_cli",
        extra_tags=expected_citation_tags,
        feedback_review_status="done",
        feedback_review_tags=feedback_review_tags,
        feedback_review_note=RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
    )
    required_readiness_reports = ["hardening_suite", "langsmith_eval_sync"]
    readiness_reports = {
        "hardening_suite": HARDENING_SUITE_REPORT_FILE,
        "langsmith_eval_sync": langsmith_report,
    }
    readiness_report_arg = readiness_report_args_for_reports(
        required_reports=required_readiness_reports,
        report_files=readiness_reports,
    )
    readiness_command = release_readiness_command_for_reports(
        required_reports=required_readiness_reports,
        report_files=readiness_reports,
    )
    langsmith_sync_command = (
        "uv run reactor-langsmith-eval-sync "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate "
        f"--report-file {langsmith_report} "
        f"{feedback_review_args}"
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync "
        f"{readiness_report_arg} "
        "--output table"
    )
    langsmith_preflight_command = (
        "uv run reactor-langsmith-eval-sync "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate "
        f"--report-file {langsmith_report} "
        f"{feedback_review_args}"
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync "
        f"{readiness_report_arg} "
        "--preflight-only --output table"
    )
    persist_command = (
        "reactor-agent-eval-apply "
        f"--case-file {case_file} "
        f"--run-file {run_file} "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate "
        "--require-source-run-id --require-run-file --require-context-diagnostics "
        f"--langsmith-dry-run-report-file {langsmith_report} "
        "--output table"
    )
    summarize_langsmith_command = (
        "reactor-agent-eval-apply "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate "
        "--summary "
        f"--langsmith-dry-run-report-file {langsmith_report} "
        f"{feedback_review_args}"
        "--output table"
    )
    return [
        RagIngestionCandidateNextAction(
            id="submit-feedback",
            label="Submit candidate answer feedback before eval promotion",
            command=feedback_submit_command,
            evalCaseId=case_id,
            sourceRunId=record.run_id,
            feedbackRating="thumbs_down",
            feedbackSource="admin_cli",
            workflowTags=submitted_feedback_tags,
            feedbackTags=submitted_feedback_tags,
        ),
        RagIngestionCandidateNextAction(
            id="inspect-submitted-feedback",
            label="Inspect submitted feedback for the exact eval promotion action",
            command=candidate_feedback_review_command,
            dependsOnActionIds=["submit-feedback"],
            evalCaseId=case_id,
            sourceRunId=record.run_id,
            feedbackRating="thumbs_down",
            feedbackSource="admin_cli",
            workflowTags=filtered_feedback_tags,
            feedbackTags=filtered_feedback_tags,
        ),
        RagIngestionCandidateNextAction(
            id="export-feedback",
            label="Export filtered feedback handoff artifact with eval/review actions",
            command=candidate_feedback_export_command,
            dependsOnActionIds=["submit-feedback"],
            evalCaseId=case_id,
            sourceRunId=record.run_id,
            feedbackRating="thumbs_down",
            feedbackSource="admin_cli",
            workflowTags=filtered_feedback_tags,
            feedbackTags=filtered_feedback_tags,
        ),
        RagIngestionCandidateNextAction(
            id="bulk-review-candidate-feedback",
            label="Close queued feedback for this RAG candidate after eval and LangSmith review",
            command=candidate_feedback_bulk_review_command,
            dependsOnActionIds=["refresh-readiness"],
            evalCaseId=case_id,
            sourceRunId=record.run_id,
            candidateTag=candidate_feedback_tag,
            reportFile=langsmith_report,
            readinessReportArg=readiness_report_arg,
            requiredReadinessReports=required_readiness_reports,
            readinessReports=readiness_reports,
            feedbackRating="thumbs_down",
            feedbackSource="admin_cli",
            workflowTags=submitted_feedback_tags,
            feedbackTags=submitted_feedback_tags,
        ),
        RagIngestionCandidateNextAction(
            id="ask-and-apply-eval",
            label="Ask from the ingested candidate and apply a regression case",
            command=ask_command,
            evalCaseId=case_id,
            sourceRunId=record.run_id,
            candidateTag=candidate_feedback_tag,
            workflowTags=submitted_feedback_tags,
            reportFile=langsmith_report,
            caseFile=case_file,
            runFile=run_file,
            suiteFile=suite_file,
            datasetName=dataset_name,
            readinessReportArg=readiness_report_arg,
            requiredReadinessReports=required_readiness_reports,
            readinessReports=readiness_reports,
            feedbackRating="thumbs_down",
            feedbackSource="admin_cli",
            feedbackTags=submitted_feedback_tags,
        ),
        RagIngestionCandidateNextAction(
            id="promote-eval",
            label="Promote the candidate source run into the regression suite",
            command=promote_eval_command,
            dependsOnActionIds=["ask-and-apply-eval"],
            evalCaseId=case_id,
            sourceRunId=record.run_id,
            candidateTag=candidate_feedback_tag,
            workflowTags=submitted_feedback_tags,
            reportFile=langsmith_report,
            caseFile=case_file,
            runFile=run_file,
            suiteFile=suite_file,
            datasetName=dataset_name,
            readinessReportArg=readiness_report_arg,
            requiredReadinessReports=required_readiness_reports,
            readinessReports=readiness_reports,
            feedbackSource="admin_cli",
            feedbackTags=submitted_feedback_tags,
        ),
        RagIngestionCandidateNextAction(
            id="persist-eval-suite",
            label="Persist the candidate regression case before LangSmith sync",
            command=persist_command,
            dependsOnActionIds=["promote-eval"],
            evalCaseId=case_id,
            sourceRunId=record.run_id,
            reportFile=langsmith_report,
            caseFile=case_file,
            runFile=run_file,
            suiteFile=suite_file,
            datasetName=dataset_name,
            readinessReportArg=readiness_report_arg,
            requiredReadinessReports=required_readiness_reports,
            readinessReports=readiness_reports,
            workflowTags=submitted_feedback_tags,
        ),
        RagIngestionCandidateNextAction(
            id="summarize-langsmith",
            label="Regenerate LangSmith dry-run evidence from the persisted suite",
            command=summarize_langsmith_command,
            dependsOnActionIds=["persist-eval-suite"],
            evalCaseId=case_id,
            sourceRunId=record.run_id,
            reportFile=langsmith_report,
            suiteFile=suite_file,
            datasetName=dataset_name,
            readinessReportArg=readiness_report_arg,
            requiredReadinessReports=required_readiness_reports,
            readinessReports=readiness_reports,
            workflowTags=submitted_feedback_tags,
        ),
        RagIngestionCandidateNextAction(
            id="preflight-langsmith",
            label="Preflight LangSmith credentials before syncing the candidate eval",
            dependsOnActionIds=["summarize-langsmith"],
            evalCaseId=case_id,
            sourceRunId=record.run_id,
            reportFile=langsmith_report,
            suiteFile=suite_file,
            datasetName=dataset_name,
            preflightFile=RELEASE_SMOKE_PREFLIGHT_FILE,
            preflightEnvTemplate=RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
            releaseReadinessFile=RELEASE_READINESS_FILE,
            releaseReadinessCommand=readiness_command,
            remediationCommand=langsmith_preflight_command,
            readinessReportArg=readiness_report_arg,
            requiredReadinessReports=required_readiness_reports,
            readinessReports=readiness_reports,
            requiredEnvAnyOf=LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
            recommendedEnv=LANGSMITH_SYNC_RECOMMENDED_ENV,
            envFileCommand=env_file_command(langsmith_preflight_command),
            command=langsmith_preflight_command,
        ),
        RagIngestionCandidateNextAction(
            id="sync-langsmith",
            label="Sync the candidate regression case to LangSmith",
            dependsOnActionIds=["preflight-langsmith"],
            evalCaseId=case_id,
            sourceRunId=record.run_id,
            reportFile=langsmith_report,
            suiteFile=suite_file,
            datasetName=dataset_name,
            preflightFile=RELEASE_SMOKE_PREFLIGHT_FILE,
            preflightEnvTemplate=RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
            releaseReadinessFile=RELEASE_READINESS_FILE,
            releaseReadinessCommand=readiness_command,
            remediationCommand=langsmith_sync_command,
            readinessReportArg=readiness_report_arg,
            requiredReadinessReports=required_readiness_reports,
            readinessReports=readiness_reports,
            requiredEnvAnyOf=LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
            recommendedEnv=LANGSMITH_SYNC_RECOMMENDED_ENV,
            envFileCommand=env_file_command(langsmith_sync_command),
            command=langsmith_sync_command,
        ),
        RagIngestionCandidateNextAction(
            id="generate-hardening-suite",
            label="Generate the hardening suite report required for minor boundary review",
            dependsOnActionIds=["summarize-langsmith"],
            evalCaseId=case_id,
            sourceRunId=record.run_id,
            reportFile=langsmith_report,
            suiteFile=suite_file,
            datasetName=dataset_name,
            readinessReportArg=f"--readiness-report hardening_suite={HARDENING_SUITE_REPORT_FILE}",
            requiredReadinessReports=required_readiness_reports,
            readinessReports=readiness_reports,
            releaseReadinessCommand=readiness_command,
            command=rag_ingestion_lifecycle_remediation_command(),
        ),
        RagIngestionCandidateNextAction(
            id="inspect-candidate-feedback",
            label="Review feedback promoted from the candidate eval",
            command=candidate_feedback_review_command,
            dependsOnActionIds=["sync-langsmith"],
            evalCaseId=case_id,
            sourceRunId=record.run_id,
            feedbackRating="thumbs_down",
            feedbackSource="admin_cli",
            workflowTags=filtered_feedback_tags,
            feedbackTags=filtered_feedback_tags,
        ),
        RagIngestionCandidateNextAction(
            id="refresh-readiness",
            label="Refresh release readiness with candidate LangSmith and hardening reports",
            dependsOnActionIds=["generate-hardening-suite", "sync-langsmith"],
            evalCaseId=case_id,
            sourceRunId=record.run_id,
            reportFile=langsmith_report,
            suiteFile=suite_file,
            datasetName=dataset_name,
            preflightFile=RELEASE_SMOKE_PREFLIGHT_FILE,
            preflightEnvTemplate=RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
            replatformReadinessFile=REPLATFORM_READINESS_FILE,
            smokePlanFile=RELEASE_SMOKE_PLAN_FILE,
            releaseEvidenceFile=RELEASE_EVIDENCE_FILE,
            releaseReadinessFile=RELEASE_READINESS_FILE,
            remediationCommand=readiness_command,
            envFileCommand=env_file_command(readiness_command),
            readinessReportArg=readiness_report_arg,
            requiredReadinessReports=required_readiness_reports,
            readinessReports=readiness_reports,
            latestTagCommand=LATEST_TAG_COMMAND,
            recommendedTagSource=RECOMMENDED_TAG_SOURCE,
            minorBoundaryReports=required_readiness_reports,
            command=readiness_command,
        ),
    ]


def command_feedback_tag_args(tags: Sequence[str]) -> str:
    return "".join(f"--feedback-tag {quote(tag)} " for tag in tags)


def admin_feedback_tag_args(tags: Sequence[str]) -> str:
    return "".join(f"--tag {quote(tag)} " for tag in tags)


def command_feedback_review_args(
    *,
    status: str,
    tags: Sequence[str],
    note: str,
) -> str:
    parts: list[str] = []
    if status.strip():
        parts.append(f"--feedback-review-status {quote(status.strip())}")
    parts.extend(
        f"--feedback-review-tag {quote(tag.strip())}" for tag in dict.fromkeys(tags) if tag.strip()
    )
    if note.strip():
        parts.append(f"--feedback-review-note {quote(note.strip())}")
    if not parts:
        return ""
    return f"{' '.join(parts)} "


def candidate_expected_citation_tags(response: str) -> list[str]:
    seen: set[str] = set()
    tags: list[str] = []
    for citation_id in re.findall(r"\[([A-Za-z0-9_.:-]+)\]", response):
        if citation_id == "unknown" or citation_id in seen or not is_citation_safe_id(citation_id):
            continue
        seen.add(citation_id)
        tags.append(f"expected-citation:{citation_id}")
    return tags
