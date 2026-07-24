from __future__ import annotations

from collections.abc import Mapping, Sequence
from shlex import quote
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status

from reactor.api.auth import PRINCIPAL_DEPENDENCY, require_any_admin
from reactor.api.next_actions import (
    blocked_next_action_ids,
    next_action_states,
    ready_next_action_ids,
)
from reactor.api.schemas.feedback import (
    BulkFeedbackReviewUpdateRequest,
    BulkFeedbackReviewUpdateResponse,
    FeedbackExportItem,
    FeedbackExportResponse,
    FeedbackExportWorkflow,
    FeedbackNextAction,
    FeedbackPageResponse,
    FeedbackResponse,
    ReviewUpdateRequest,
    SubmitFeedbackRequest,
)
from reactor.auth.rbac import AuthPrincipal, current_actor
from reactor.feedback.workflow import (
    feedback_eval_case_id as workflow_feedback_eval_case_id,
)
from reactor.feedback.workflow import (
    feedback_eval_expected_answers,
    feedback_expected_citation_tags,
    feedback_indicates_rag_candidate_collection,
    feedback_rag_candidate_id,
    feedback_requires_citation_marker_eval,
    feedback_review_closed,
    feedback_with_workflow_tags,
    feedback_workflow_tags,
    optional_safe_command_id,
    safe_command_id,
)
from reactor.feedback.workflow import (
    feedback_rag_candidate_id_from_run_id as workflow_feedback_rag_candidate_id_from_run_id,
)
from reactor.memory.lifecycle_actions import MEMORY_LIFECYCLE_GATE_ACTION
from reactor.rag.ingestion_candidate_actions import (
    RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
    rag_candidate_feedback_bulk_review_action,
)
from reactor.rag.ingestion_candidate_ids import (
    command_slug,
    rag_candidate_case_id,
    rag_candidate_workflow_tag,
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
    langsmith_release_readiness_command,
    rag_ingestion_lifecycle_remediation_command,
    readiness_report_args_for_reports,
    release_readiness_command_for_reports,
)
from reactor.slack.feedback import Feedback, FeedbackRating, feedback_review_matches

router = APIRouter(tags=["feedback"])
MEMORY_LIFECYCLE_ACTION = MEMORY_LIFECYCLE_GATE_ACTION
FEEDBACK_EVAL_RESOLUTION_TAGS = frozenset({"promoted", "no-eval-needed", "deferred"})
FEEDBACK_EVAL_EXCEPTION_RESOLUTION_TAGS = frozenset({"no-eval-needed", "deferred"})
FEEDBACK_EVAL_RESOLUTION_TAGS_REQUIRING_NOTE = frozenset({"promoted", "no-eval-needed", "deferred"})
HARDENING_FEEDBACK_REVIEW_NOTE = "Promoted to regression eval and reviewed in hardening/LangSmith."


@router.post(
    "/api/feedback",
    response_model=FeedbackResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/v1/feedback",
    response_model=FeedbackResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
async def submit_feedback(
    request: Request,
    body: SubmitFeedbackRequest,
    principal: AuthPrincipal = PRINCIPAL_DEPENDENCY,
) -> FeedbackResponse:
    feedback = Feedback(
        tenant_id=principal.tenant_id,
        query=body.query or "",
        response=body.response or "",
        rating=parse_feedback_rating(body.rating),
        comment=body.comment,
        session_id=body.sessionId or "",
        run_id=body.runId,
        user_id=principal.user_id,
        intent=body.intent,
        domain=body.domain,
        model=body.model,
        prompt_version=body.promptVersion,
        tools_used=body.toolsUsed,
        duration_ms=body.durationMs,
        tags=body.tags,
        template_id=body.templateId,
        source=body.source.strip() if body.source and body.source.strip() else "api",
    )
    saved = await require_feedback_store(request).save(feedback_with_workflow_tags(feedback))
    return feedback_response(saved, include_next_actions=principal.is_any_admin())


@router.get(
    "/api/feedback",
    response_model=FeedbackPageResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
@router.get(
    "/v1/feedback",
    response_model=FeedbackPageResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
async def list_feedback(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    rating: str | None = None,
    source: str | None = None,
    reviewStatus: str | None = None,
    caseId: str | None = None,
    tag: Annotated[list[str] | None, Query()] = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> FeedbackPageResponse:
    items = await require_feedback_store(request).list(
        tenant_id=principal.tenant_id,
        rating=parse_feedback_rating(rating) if rating is not None else None,
        source=normalize_feedback_source_filter(source),
        review_status=parse_review_status(reviewStatus) if reviewStatus is not None else None,
        tags=normalize_feedback_tag_filter(tag),
        case_id=normalize_feedback_case_id_filter(caseId),
        limit=limit,
    )
    return FeedbackPageResponse(
        items=[feedback_response(item, include_next_actions=True) for item in items],
        approximateTotal=len(items),
    )


@router.get("/api/feedback/unreviewed-count")
@router.get("/v1/feedback/unreviewed-count")
async def feedback_unreviewed_count(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> dict[str, int]:
    count = await require_feedback_store(request).unreviewed_count(tenant_id=principal.tenant_id)
    return {"count": count}


@router.get("/api/feedback/stats")
@router.get("/v1/feedback/stats")
async def feedback_stats(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> dict[str, object]:
    stats = await require_feedback_store(request).stats(tenant_id=principal.tenant_id)
    return dict(stats)


@router.get("/api/feedback/analytics")
@router.get("/v1/feedback/analytics")
async def feedback_analytics(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    groupBy: str = Query(default="model", min_length=1, max_length=32),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, object]:
    try:
        analytics = await require_feedback_store(request).analytics(
            tenant_id=principal.tenant_id,
            group_by=groupBy,
            limit=limit,
        )
    except ValueError as error:
        raise invalid_request(str(error)) from error
    return dict(analytics)


@router.get(
    "/api/feedback/export",
    response_model=FeedbackExportResponse,
    response_model_exclude_none=True,
)
@router.get(
    "/v1/feedback/export",
    response_model=FeedbackExportResponse,
    response_model_exclude_none=True,
)
async def export_feedback(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    rating: str | None = None,
    source: str | None = None,
    reviewStatus: str | None = None,
    caseId: str | None = None,
    tag: Annotated[list[str] | None, Query()] = None,
    limit: int = Query(default=100, ge=1, le=100),
) -> FeedbackExportResponse:
    items = await require_feedback_store(request).list(
        tenant_id=principal.tenant_id,
        rating=parse_feedback_rating(rating) if rating is not None else None,
        source=normalize_feedback_source_filter(source),
        review_status=parse_review_status(reviewStatus) if reviewStatus is not None else None,
        tags=normalize_feedback_tag_filter(tag),
        case_id=normalize_feedback_case_id_filter(caseId),
        limit=limit,
    )
    return FeedbackExportResponse(
        version=1,
        source="reactor",
        items=[feedback_export_item(item) for item in items],
    )


@router.post(
    "/api/feedback/bulk-update",
    response_model=BulkFeedbackReviewUpdateResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
@router.post(
    "/v1/feedback/bulk-update",
    response_model=BulkFeedbackReviewUpdateResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
async def bulk_update_feedback_review(
    request: Request,
    body: BulkFeedbackReviewUpdateRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> BulkFeedbackReviewUpdateResponse:
    store = require_feedback_store(request)
    resolved_status = parse_review_status(body.status) if body.status is not None else None
    allowed_ids: list[str] = []
    allowed_feedback_by_id: dict[str, Feedback] = {}
    blocked: list[dict[str, object]] = []
    for feedback_id in body.ids:
        feedback = await store.get(tenant_id=principal.tenant_id, feedback_id=feedback_id)
        if isinstance(feedback, Feedback) and feedback_done_resolution_failure(
            feedback,
            review_status=resolved_status,
            tags=body.tags,
        ):
            blocked.append(blocked_feedback_failure(feedback, "eval_resolution_required"))
            continue
        if isinstance(feedback, Feedback) and feedback_resolution_note_failure(
            feedback,
            review_status=resolved_status,
            tags=body.tags,
            note=body.note,
        ):
            blocked.append(blocked_feedback_failure(feedback, "eval_resolution_note_required"))
            continue
        if isinstance(feedback, Feedback) and feedback_promoted_langsmith_failure(
            feedback,
            review_status=resolved_status,
            tags=body.tags,
        ):
            blocked.append(blocked_feedback_failure(feedback, "langsmith_resolution_required"))
            continue
        if isinstance(feedback, Feedback) and feedback_promoted_readiness_note_failure(
            feedback,
            review_status=resolved_status,
            tags=body.tags,
            note=body.note,
        ):
            blocked.append(blocked_feedback_failure(feedback, "readiness_note_required"))
            continue
        allowed_ids.append(feedback_id)
        if isinstance(feedback, Feedback):
            allowed_feedback_by_id[feedback_id] = feedback
    result: dict[str, object] = (
        cast(
            dict[str, object],
            await store.bulk_update_review(
                tenant_id=principal.tenant_id,
                ids=allowed_ids,
                status=resolved_status,
                tags=body.tags,
                note=body.note,
                actor=current_actor(principal),
            ),
        )
        if allowed_ids
        else {"updated": [], "failed": []}
    )
    failed: list[dict[str, object]] = [*blocked]
    raw_failed: object = result.get("failed")
    if isinstance(raw_failed, list):
        for item in cast(list[object], raw_failed):
            if not isinstance(item, Mapping):
                continue
            item_mapping = cast(Mapping[object, object], item)
            failed.append({str(key): str(value) for key, value in item_mapping.items()})
    response: dict[str, object] = {**result, "failed": failed}
    updated_details = updated_feedback_handoff_details(
        result.get("updated"),
        allowed_feedback_by_id=allowed_feedback_by_id,
        review_tags=body.tags,
        review_note=body.note,
    )
    if updated_details:
        response["updatedDetails"] = updated_details
    return BulkFeedbackReviewUpdateResponse.model_validate(response)


def blocked_feedback_failure(feedback: Feedback, reason: str) -> dict[str, object]:
    failure: dict[str, object] = {
        "id": feedback.feedback_id,
        "reason": reason,
        "nextAction": feedback_lookup_action(feedback),
    }
    failure.update(feedback_handoff_metadata(feedback))
    failure.update(feedback_readiness_handoff_metadata(feedback))
    required_review_note = feedback_required_review_note(feedback)
    if required_review_note is not None:
        failure["requiredReviewNote"] = required_review_note
    if feedback_requires_eval_resolution(feedback):
        failure["requiredEnvAnyOf"] = LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF
        failure["recommendedEnv"] = LANGSMITH_SYNC_RECOMMENDED_ENV
    next_actions = feedback_next_actions(feedback)
    if next_actions:
        failure["readyNextActionIds"] = ready_feedback_next_action_ids(next_actions)
        failure["blockedNextActionIds"] = blocked_feedback_next_action_ids(next_actions)
        failure["nextActionStates"] = feedback_next_action_states(next_actions)
        failure["nextActions"] = [
            action.model_dump(by_alias=True, exclude_none=True) for action in next_actions
        ]
    return failure


def updated_feedback_handoff_details(
    updated: object,
    *,
    allowed_feedback_by_id: Mapping[str, Feedback],
    review_tags: list[str] | None = None,
    review_note: str | None = None,
) -> list[dict[str, object]]:
    if not isinstance(updated, Sequence) or isinstance(updated, str | bytes | bytearray):
        return []
    details: list[dict[str, object]] = []
    for item in cast(Sequence[object], updated):
        if not isinstance(item, str):
            continue
        feedback = allowed_feedback_by_id.get(item)
        if feedback is None:
            continue
        readiness_metadata = feedback_readiness_handoff_metadata(feedback)
        if not readiness_metadata:
            continue
        required_reports = readiness_metadata.get("requiredReadinessReports")
        readiness_reports = readiness_metadata.get("readinessReports")
        next_action = feedback_lookup_action(feedback)
        if isinstance(required_reports, Sequence) and isinstance(readiness_reports, Mapping):
            report_names = [
                report_name.strip()
                for report_name in cast(Sequence[object], required_reports)
                if isinstance(report_name, str) and report_name.strip()
            ]
            report_files = {
                str(report_name): str(report_file)
                for report_name, report_file in cast(
                    Mapping[object, object], readiness_reports
                ).items()
                if isinstance(report_name, str)
                and report_name.strip()
                and isinstance(report_file, str)
                and report_file.strip()
            }
            if report_names and set(report_names).issubset(report_files):
                next_action = release_readiness_command_for_reports(
                    required_reports=report_names,
                    report_files=report_files,
                )
        detail: dict[str, object] = {
            "feedbackId": feedback.feedback_id,
            "nextAction": next_action,
        }
        if review_tags is not None:
            detail["reviewTags"] = review_tags
        if review_note is not None:
            detail["reviewNote"] = review_note
        detail.update(feedback_handoff_metadata(feedback))
        detail.update(readiness_metadata)
        detail["requiredEnvAnyOf"] = LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF
        detail["recommendedEnv"] = LANGSMITH_SYNC_RECOMMENDED_ENV
        details.append(detail)
    return details


def feedback_handoff_metadata(feedback: Feedback) -> dict[str, str]:
    run_id = (feedback.run_id or "").strip()
    if not run_id:
        return {}
    metadata = {
        "evalCaseId": feedback_eval_case_id(feedback=feedback, run_id=run_id),
        "sourceRunId": run_id,
    }
    feedback_source = feedback_action_source(feedback)
    if feedback_source is not None:
        metadata["feedbackSource"] = feedback_source
    candidate_id = feedback_resolved_rag_candidate_id(feedback)
    if candidate_id is not None:
        metadata["bulkReviewAction"] = rag_candidate_feedback_bulk_review_action(
            rag_candidate_workflow_tag(candidate_id),
            source=feedback.source,
        )
    return metadata


def feedback_readiness_handoff_metadata(feedback: Feedback) -> dict[str, object]:
    run_id = (feedback.run_id or "").strip()
    if not run_id or not feedback_requires_eval_resolution(feedback):
        return {}
    case_id = feedback_eval_case_id(feedback=feedback, run_id=run_id)
    langsmith_report_file = feedback_langsmith_dry_run_report_file(
        feedback=feedback,
        case_id=case_id,
    )
    required_reports, readiness_reports, readiness_report_arg = (
        feedback_langsmith_readiness_metadata(
            feedback=feedback,
            langsmith_report_file=langsmith_report_file,
        )
    )
    return {
        "readinessReportArg": readiness_report_arg,
        "requiredReadinessReports": required_reports,
        "readinessReports": readiness_reports,
        "releaseReadinessCommand": release_readiness_command_for_reports(
            required_reports=required_reports,
            report_files=readiness_reports,
        ),
    }


@router.get(
    "/api/feedback/{feedback_id}",
    response_model=FeedbackResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
@router.get(
    "/v1/feedback/{feedback_id}",
    response_model=FeedbackResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
async def get_feedback(
    request: Request,
    feedback_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> FeedbackResponse:
    feedback = await require_feedback_record(
        request,
        tenant_id=principal.tenant_id,
        feedback_id=feedback_id,
    )
    return feedback_response(feedback, include_next_actions=True)


@router.patch(
    "/api/feedback/{feedback_id}",
    response_model=FeedbackResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
@router.patch(
    "/v1/feedback/{feedback_id}",
    response_model=FeedbackResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
)
async def update_feedback_review(
    request: Request,
    feedback_id: str,
    body: ReviewUpdateRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> FeedbackResponse:
    expected_version = parse_if_match(if_match)
    store = require_feedback_store(request)
    current_feedback = await store.get(tenant_id=principal.tenant_id, feedback_id=feedback_id)
    if not isinstance(current_feedback, Feedback):
        raise feedback_not_found(feedback_id)
    resolved_status = parse_review_status(body.status) if body.status is not None else None
    validate_feedback_done_resolution(
        current_feedback,
        review_status=resolved_status,
        tags=body.tags,
        note=body.note,
    )
    try:
        feedback = await store.update_review(
            tenant_id=principal.tenant_id,
            feedback_id=feedback_id,
            expected_version=expected_version,
            status=resolved_status,
            tags=body.tags,
            note=body.note,
            actor=current_actor(principal),
        )
    except KeyError as error:
        raise feedback_not_found(feedback_id) from error
    except ValueError as error:
        if str(error) == "version_conflict":
            current = await store.get(tenant_id=principal.tenant_id, feedback_id=feedback_id)
            if not isinstance(current, Feedback):
                raise feedback_not_found(feedback_id) from error
            if feedback_review_matches(
                current,
                status=resolved_status,
                tags=body.tags,
                note=body.note,
            ):
                return feedback_response(current, include_next_actions=True)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=feedback_review_version_conflict_detail(
                    current,
                    expected_version=expected_version,
                ),
            ) from error
        raise invalid_request(str(error)) from error
    return feedback_response(feedback, include_next_actions=True)


@router.delete("/api/feedback/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/v1/feedback/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feedback(
    request: Request,
    feedback_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> Response:
    store = require_feedback_store(request)
    feedback = await store.get(tenant_id=principal.tenant_id, feedback_id=feedback_id)
    if isinstance(feedback, Feedback) and feedback_delete_resolution_failure(feedback):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=feedback_resolution_error_detail(
                feedback,
                message="feedback delete requires eval resolution first",
            ),
        )
    await store.delete(
        tenant_id=principal.tenant_id,
        feedback_id=feedback_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def feedback_store(request: Request):
    container = request.app.state.reactor
    accessor = getattr(container, "feedback_store", None)
    return accessor() if accessor is not None else None


def require_feedback_store(request: Request):
    store = feedback_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="feedback persistence is not configured",
        )
    return store


async def require_feedback_record(
    request: Request,
    *,
    tenant_id: str,
    feedback_id: str,
) -> Feedback:
    feedback = await require_feedback_store(request).get(
        tenant_id=tenant_id,
        feedback_id=feedback_id,
    )
    if not isinstance(feedback, Feedback):
        raise feedback_not_found(feedback_id)
    return feedback


def feedback_response(
    feedback: Feedback,
    *,
    include_next_actions: bool = False,
) -> FeedbackResponse:
    actions = feedback_next_actions(feedback) if include_next_actions else None
    return FeedbackResponse(
        feedbackId=feedback.feedback_id,
        query=feedback.query,
        response=feedback.response,
        rating=feedback.rating.value.lower(),
        source=feedback.source,
        timestamp=feedback.created_at.isoformat(),
        comment=feedback.comment,
        sessionId=feedback.session_id or None,
        runId=feedback.run_id,
        userId=feedback.user_id or None,
        intent=feedback.intent,
        domain=feedback.domain,
        model=feedback.model,
        promptVersion=feedback.prompt_version,
        toolsUsed=feedback.tools_used,
        durationMs=feedback.duration_ms,
        tags=feedback.tags,
        templateId=feedback.template_id,
        reviewStatus=feedback.review_status,
        reviewTags=feedback.review_tags,
        reviewedBy=feedback.reviewed_by,
        reviewedAt=feedback.reviewed_at.isoformat() if feedback.reviewed_at is not None else None,
        reviewNote=feedback.review_note,
        version=feedback.version,
        updatedAt=feedback.updated_at.isoformat(),
        readyNextActionIds=ready_feedback_next_action_ids(actions) if actions is not None else None,
        blockedNextActionIds=(
            blocked_feedback_next_action_ids(actions) if actions is not None else None
        ),
        nextActionStates=feedback_next_action_states(actions) if actions is not None else None,
        nextActions=actions,
    )


def ready_feedback_next_action_ids(actions: list[FeedbackNextAction]) -> list[str]:
    return ready_next_action_ids(actions)


def blocked_feedback_next_action_ids(actions: list[FeedbackNextAction]) -> list[str]:
    return blocked_next_action_ids(actions)


def feedback_next_action_states(actions: list[FeedbackNextAction]) -> dict[str, str]:
    return next_action_states(actions)


def feedback_next_actions(feedback: Feedback) -> list[FeedbackNextAction]:
    if (
        feedback.review_status != "inbox"
        or feedback.rating != FeedbackRating.THUMBS_DOWN
        or not feedback.run_id
    ):
        return []
    run_id = feedback.run_id.strip()
    if not run_id:
        return []
    citation_marker_action = feedback_missing_citation_marker_action(feedback)
    if citation_marker_action is not None:
        actions = [citation_marker_action]
        candidate_review_action = feedback_rag_candidate_review_action(feedback)
        if candidate_review_action:
            actions.append(candidate_review_action)
        candidate_export_action = feedback_rag_candidate_export_action(feedback)
        if candidate_export_action:
            actions.append(candidate_export_action)
        memory_review_action = feedback_memory_review_action(feedback)
        if memory_review_action:
            actions.append(memory_review_action)
        memory_lifecycle_action = feedback_memory_lifecycle_action(feedback)
        if memory_lifecycle_action:
            actions.append(memory_lifecycle_action)
        return actions
    case_id = feedback_eval_case_id(feedback=feedback, run_id=run_id)
    workflow_tags = feedback_eval_workflow_tags(feedback=feedback, run_id=run_id)
    workflow_tags_response = workflow_tags or None
    expected_answers = feedback_eval_expected_answers(feedback)
    promotion_tags = feedback_eval_promotion_tags(
        feedback=feedback,
        workflow_tags=workflow_tags,
        expected_answers=expected_answers,
    )
    tag_args = command_tag_args(promotion_tags)
    source_args = feedback_source_arg(feedback)
    feedback_source = feedback_action_source(feedback)
    expected_answer_args = command_expected_answer_args(expected_answers)
    promotion_assertion_args = command_args(tag_args, source_args, expected_answer_args)
    promotion_apply_args = feedback_eval_apply_args(feedback=feedback, case_id=case_id)
    promotion_apply_dry_run_arg = (
        "" if feedback_indicates_rag_candidate_collection(feedback) else "--apply-dry-run "
    )
    langsmith_report_file = feedback_langsmith_dry_run_report_file(
        feedback=feedback,
        case_id=case_id,
    )
    required_readiness_reports, readiness_reports, readiness_report_arg = (
        feedback_langsmith_readiness_metadata(
            feedback=feedback,
            langsmith_report_file=langsmith_report_file,
        )
    )
    suite_file = feedback_eval_suite_file(feedback)
    dataset_name = feedback_eval_dataset_name(feedback)
    case_file, run_file = feedback_eval_artifact_files(
        feedback=feedback,
        case_id=case_id,
        run_id=run_id,
    )
    review_tag_args = command_tag_args(["promoted", "langsmith", *workflow_tags])
    feedback_review_tag_args = command_feedback_review_tag_args(
        ["promoted", "langsmith", *workflow_tags]
    )
    review_note = feedback_review_done_note(required_readiness_reports)
    actions = [
        FeedbackNextAction(
            id="promote-eval",
            label="Promote the feedback run into a source-controlled eval case",
            feedbackId=feedback.feedback_id,
            evalCaseId=case_id,
            sourceRunId=run_id,
            reportFile=langsmith_report_file,
            releaseReadinessFile=RELEASE_READINESS_FILE,
            caseFile=case_file,
            runFile=run_file,
            suiteFile=suite_file,
            datasetName=dataset_name,
            readinessReportArg=readiness_report_arg,
            requiredReadinessReports=required_readiness_reports,
            readinessReports=readiness_reports,
            feedbackTags=promotion_tags,
            feedbackSource=feedback_source,
            workflowTags=workflow_tags_response,
            expectedAnswers=expected_answers or None,
            command=(
                f"reactor-runs promote-eval {quote(run_id)} --case-id {case_id} "
                f"--case-file {case_file} --run-file {run_file} "
                f"{promotion_assertion_args} "
                f"{promotion_apply_args} "
                f"{promotion_apply_dry_run_arg}"
                "--apply-require-source-run-id "
                "--apply-require-run-file --apply-require-context-diagnostics "
                "--apply-suite-summary "
                f"--langsmith-dry-run-report-file {langsmith_report_file} "
                f"--feedback-review-status done {feedback_review_tag_args} "
                f"--feedback-review-note {quote(review_note)} "
                "--output table"
            ),
        ),
    ]
    actions.append(
        FeedbackNextAction(
            id="persist-eval-suite",
            label="Persist the promoted eval case before LangSmith sync",
            feedbackId=feedback.feedback_id,
            evalCaseId=case_id,
            sourceRunId=run_id,
            reportFile=langsmith_report_file,
            releaseReadinessFile=RELEASE_READINESS_FILE,
            caseFile=case_file,
            runFile=run_file,
            suiteFile=suite_file,
            datasetName=dataset_name,
            readinessReportArg=readiness_report_arg,
            requiredReadinessReports=required_readiness_reports,
            readinessReports=readiness_reports,
            dependsOnActionIds=["promote-eval"],
            feedbackTags=promotion_tags,
            feedbackSource=feedback_source,
            workflowTags=workflow_tags_response,
            expectedAnswers=expected_answers or None,
            command=feedback_eval_persist_command(
                feedback=feedback,
                case_file=case_file,
                run_file=run_file,
                langsmith_report_file=langsmith_report_file,
            ),
        )
    )
    actions.append(
        FeedbackNextAction(
            id="summarize-langsmith",
            label="Regenerate LangSmith dry-run evidence from the persisted suite",
            feedbackId=feedback.feedback_id,
            evalCaseId=case_id,
            sourceRunId=run_id,
            reportFile=langsmith_report_file,
            releaseReadinessFile=RELEASE_READINESS_FILE,
            suiteFile=suite_file,
            datasetName=dataset_name,
            readinessReportArg=readiness_report_arg,
            requiredReadinessReports=required_readiness_reports,
            readinessReports=readiness_reports,
            dependsOnActionIds=["persist-eval-suite"],
            feedbackTags=promotion_tags,
            feedbackSource=feedback_source,
            workflowTags=workflow_tags_response,
            expectedAnswers=expected_answers or None,
            command=feedback_eval_summary_command(
                feedback=feedback,
                langsmith_report_file=langsmith_report_file,
                review_status="done",
                review_tags=["promoted", "langsmith", *workflow_tags],
                review_note=review_note,
            ),
        )
    )
    langsmith_actions = feedback_langsmith_next_actions(
        feedback=feedback,
        case_id=case_id,
        run_id=run_id,
        langsmith_report_file=langsmith_report_file,
    )
    actions.extend(langsmith_actions)
    candidate_review_action = feedback_rag_candidate_review_action(feedback)
    if candidate_review_action:
        actions.append(candidate_review_action)
    candidate_export_action = feedback_rag_candidate_export_action(feedback)
    if candidate_export_action:
        actions.append(candidate_export_action)
    candidate_bulk_review_action = feedback_rag_candidate_bulk_review_action(
        feedback=feedback,
        case_id=case_id,
        run_id=run_id,
        langsmith_report_file=langsmith_report_file,
        readiness_report_arg=readiness_report_arg,
        required_readiness_reports=required_readiness_reports,
        readiness_reports=readiness_reports,
    )
    if candidate_bulk_review_action:
        actions.append(candidate_bulk_review_action)
    memory_review_action = feedback_memory_review_action(feedback)
    if memory_review_action:
        actions.append(memory_review_action)
    memory_lifecycle_action = feedback_memory_lifecycle_action(feedback)
    if memory_lifecycle_action:
        actions.append(memory_lifecycle_action)
    actions.append(
        FeedbackNextAction(
            id="review-done",
            label="Mark the feedback as promoted after eval and readiness are captured",
            feedbackId=feedback.feedback_id,
            evalCaseId=case_id,
            sourceRunId=run_id,
            suiteFile=suite_file,
            datasetName=dataset_name,
            reportFile=langsmith_report_file,
            releaseReadinessFile=RELEASE_READINESS_FILE,
            readinessReportArg=readiness_report_arg,
            requiredReadinessReports=required_readiness_reports,
            readinessReports=readiness_reports,
            dependsOnActionIds=["refresh-readiness"],
            feedbackTags=promotion_tags,
            feedbackSource=feedback_source,
            workflowTags=workflow_tags_response,
            command=(
                f"reactor-admin feedback-review {quote(feedback.feedback_id)} "
                f"--if-match {feedback.version} --status done {review_tag_args} "
                f"--note {quote(review_note)} "
                "--output table"
            ),
        )
    )
    return actions


def validate_feedback_done_resolution(
    feedback: Feedback,
    *,
    review_status: str | None,
    tags: list[str] | None,
    note: str | None,
) -> None:
    if feedback_done_resolution_failure(
        feedback,
        review_status=review_status,
        tags=tags,
    ):
        detail = feedback_resolution_error_detail(
            feedback,
            message="feedback done requires eval resolution tag",
        )
        detail["requiredAnyReviewTag"] = sorted(FEEDBACK_EVAL_RESOLUTION_TAGS)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )
    if feedback_resolution_note_failure(
        feedback,
        review_status=review_status,
        tags=tags,
        note=note,
    ):
        detail: dict[str, object] = {
            "message": "feedback eval resolution note is required",
            "feedbackId": feedback.feedback_id,
            "resolutionTagsRequiringNote": sorted(FEEDBACK_EVAL_RESOLUTION_TAGS_REQUIRING_NOTE),
            "nextAction": feedback_lookup_action(feedback),
        }
        detail.update(feedback_handoff_metadata(feedback))
        detail.update(feedback_readiness_handoff_metadata(feedback))
        required_review_note = (
            feedback_required_review_note(feedback)
            if feedback_promoted_langsmith_tags(feedback, tags=tags)
            else None
        )
        if required_review_note is not None:
            detail["requiredReviewNote"] = required_review_note
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )
    if feedback_promoted_langsmith_failure(
        feedback,
        review_status=review_status,
        tags=tags,
    ):
        detail = feedback_resolution_error_detail(
            feedback,
            message="promoted feedback requires LangSmith resolution tag",
        )
        detail["requiredAllReviewTags"] = ["promoted", "langsmith"]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )
    if feedback_promoted_readiness_note_failure(
        feedback,
        review_status=review_status,
        tags=tags,
        note=note,
    ):
        detail = feedback_resolution_error_detail(
            feedback,
            message="promoted feedback requires readiness report note",
        )
        detail["requiredReviewNote"] = feedback_required_review_note(feedback)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )


def feedback_resolution_error_detail(feedback: Feedback, *, message: str) -> dict[str, object]:
    detail: dict[str, object] = {
        "message": message,
        "feedbackId": feedback.feedback_id,
        "nextAction": feedback_lookup_action(feedback),
    }
    detail.update(feedback_handoff_metadata(feedback))
    detail.update(feedback_readiness_handoff_metadata(feedback))
    next_actions = feedback_next_actions(feedback)
    if next_actions:
        detail["readyNextActionIds"] = ready_feedback_next_action_ids(next_actions)
        detail["blockedNextActionIds"] = blocked_feedback_next_action_ids(next_actions)
        detail["nextActionStates"] = feedback_next_action_states(next_actions)
        detail["nextActions"] = [
            action.model_dump(by_alias=True, exclude_none=True) for action in next_actions
        ]
    return detail


def feedback_done_resolution_failure(
    feedback: Feedback,
    *,
    review_status: str | None,
    tags: list[str] | None,
) -> bool:
    if review_status != "done" or not feedback_requires_eval_resolution(feedback):
        return False
    resolved_tags = {tag.strip() for tag in tags or feedback.review_tags if tag.strip()}
    return not resolved_tags.intersection(FEEDBACK_EVAL_RESOLUTION_TAGS)


def feedback_resolution_note_failure(
    feedback: Feedback,
    *,
    review_status: str | None,
    tags: list[str] | None,
    note: str | None,
) -> bool:
    if review_status != "done" or not feedback_requires_eval_resolution(feedback):
        return False
    resolved_tags = {tag.strip() for tag in tags or feedback.review_tags if tag.strip()}
    requires_note = bool(resolved_tags.intersection(FEEDBACK_EVAL_EXCEPTION_RESOLUTION_TAGS))
    requires_note = requires_note or {"promoted", "langsmith"}.issubset(resolved_tags)
    if not requires_note:
        return False
    resolved_note = note if note is not None else feedback.review_note
    return not isinstance(resolved_note, str) or not resolved_note.strip()


def feedback_promoted_langsmith_failure(
    feedback: Feedback,
    *,
    review_status: str | None,
    tags: list[str] | None,
) -> bool:
    if review_status != "done" or not feedback_requires_eval_resolution(feedback):
        return False
    resolved_tags = feedback_resolved_review_tag_set(feedback, tags=tags)
    return "promoted" in resolved_tags and "langsmith" not in resolved_tags


def feedback_promoted_readiness_note_failure(
    feedback: Feedback,
    *,
    review_status: str | None,
    tags: list[str] | None,
    note: str | None,
) -> bool:
    if (
        review_status != "done"
        or not feedback_requires_eval_resolution(feedback)
        or not feedback_requires_hardening_readiness(feedback)
    ):
        return False
    if not feedback_promoted_langsmith_tags(feedback, tags=tags):
        return False
    resolved_note = note if note is not None else feedback.review_note
    if not isinstance(resolved_note, str) or not resolved_note.strip():
        return False
    return not feedback_review_closed(
        feedback_review_resolution_mapping(
            feedback,
            review_status=review_status,
            tags=tags,
            note=note,
        )
    )


def feedback_review_resolution_mapping(
    feedback: Feedback,
    *,
    review_status: str | None,
    tags: list[str] | None,
    note: str | None,
) -> dict[str, object]:
    return {
        "reviewStatus": review_status or feedback.review_status,
        "reviewTags": tags if tags is not None else feedback.review_tags,
        "reviewNote": note if note is not None else feedback.review_note,
    }


def feedback_promoted_langsmith_tags(feedback: Feedback, *, tags: list[str] | None) -> bool:
    return {"promoted", "langsmith"}.issubset(feedback_resolved_review_tag_set(feedback, tags=tags))


def feedback_resolved_review_tag_set(feedback: Feedback, *, tags: list[str] | None) -> set[str]:
    return {tag.strip() for tag in tags or feedback.review_tags if tag.strip()}


def feedback_required_review_note(feedback: Feedback) -> str | None:
    if not feedback.run_id or not feedback.run_id.strip():
        return None
    required_reports, _, _ = feedback_langsmith_readiness_metadata(
        feedback=feedback,
        langsmith_report_file=feedback_langsmith_dry_run_report_file(
            feedback=feedback,
            case_id=feedback_eval_case_id(
                feedback=feedback,
                run_id=feedback.run_id.strip(),
            ),
        ),
    )
    return feedback_review_done_note(required_reports)


def feedback_lookup_action(feedback: Feedback) -> str:
    return f"reactor-admin feedback --feedback-id {quote(feedback.feedback_id)} --output table"


def feedback_requires_eval_resolution(feedback: Feedback) -> bool:
    return (
        feedback.rating == FeedbackRating.THUMBS_DOWN
        and bool((feedback.run_id or "").strip())
        and (
            feedback_indicates_rag_candidate_collection(feedback)
            or feedback_requires_citation_marker_eval(feedback)
        )
    )


def feedback_delete_resolution_failure(feedback: Feedback) -> bool:
    return feedback.review_status == "inbox" and feedback_requires_eval_resolution(feedback)


def feedback_missing_citation_marker_action(feedback: Feedback) -> FeedbackNextAction | None:
    if not feedback_requires_citation_marker_eval(feedback):
        return None
    if feedback_eval_expected_answers(feedback):
        return None
    run_id = (feedback.run_id or "").strip()
    case_id = feedback_eval_case_id(feedback=feedback, run_id=run_id) if run_id else None
    return FeedbackNextAction(
        id="add-citation-marker",
        label="Add the missing bracketed citation marker before promoting an eval",
        feedbackId=feedback.feedback_id,
        evalCaseId=case_id,
        sourceRunId=run_id or None,
        feedbackSource=feedback_action_source(feedback),
        command=(
            f"reactor-admin feedback-review {quote(feedback.feedback_id)} "
            f"--if-match {feedback.version} --status inbox "
            "--tag citation-marker-required "
            "--note 'Expected citation marker: [replace-with-source-id]' "
            "--output table"
        ),
    )


def feedback_rag_candidate_review_action(feedback: Feedback) -> FeedbackNextAction | None:
    if not feedback_indicates_rag_candidate_collection(feedback):
        return None
    candidate_id = feedback_resolved_rag_candidate_id(feedback)
    run_id = (feedback.run_id or "").strip()
    case_id = feedback_eval_case_id(feedback=feedback, run_id=run_id) if run_id else None
    candidate_tag_arg = (
        f"--tag {quote(rag_candidate_workflow_tag(candidate_id))} "
        if candidate_id is not None
        else ""
    )
    source = optional_safe_command_id(feedback.source)
    source_arg = f"--source {quote(source)} " if source else ""
    return FeedbackNextAction(
        id="inspect-candidate-feedback",
        label="Inspect feedback for this RAG candidate workflow before closing the review",
        feedbackId=feedback.feedback_id,
        evalCaseId=case_id,
        sourceRunId=run_id or None,
        feedbackSource=feedback_action_source(feedback),
        command=(
            "reactor-admin feedback --rating thumbs_down "
            f"{source_arg}"
            "--review-status inbox "
            "--tag collection:rag-ingestion-candidate "
            f"{candidate_tag_arg}"
            "--limit 10 --output table"
        ),
    )


def feedback_rag_candidate_export_action(feedback: Feedback) -> FeedbackNextAction | None:
    if not feedback_indicates_rag_candidate_collection(feedback):
        return None
    candidate_id = feedback_resolved_rag_candidate_id(feedback)
    run_id = (feedback.run_id or "").strip()
    case_id = feedback_eval_case_id(feedback=feedback, run_id=run_id) if run_id else None
    candidate_tag_arg = (
        f"--tag {quote(rag_candidate_workflow_tag(candidate_id))} "
        if candidate_id is not None
        else ""
    )
    source = optional_safe_command_id(feedback.source)
    source_arg = f"--source {quote(source)} " if source else ""
    return FeedbackNextAction(
        id="export-candidate-feedback",
        label="Export filtered candidate workflow feedback handoff actions as JSON",
        feedbackId=feedback.feedback_id,
        evalCaseId=case_id,
        sourceRunId=run_id or None,
        feedbackSource=feedback_action_source(feedback),
        command=(
            "reactor-admin feedback-export --rating thumbs_down "
            f"{source_arg}"
            "--review-status inbox "
            "--tag collection:rag-ingestion-candidate "
            f"{candidate_tag_arg}"
            "--limit 10 --output json"
        ),
    )


def feedback_rag_candidate_bulk_review_action(
    *,
    feedback: Feedback,
    case_id: str,
    run_id: str,
    langsmith_report_file: str,
    readiness_report_arg: str,
    required_readiness_reports: list[str],
    readiness_reports: dict[str, str],
) -> FeedbackNextAction | None:
    if not feedback_indicates_rag_candidate_collection(feedback):
        return None
    candidate_id = feedback_resolved_rag_candidate_id(feedback)
    if candidate_id is None:
        return None
    candidate_tag = rag_candidate_workflow_tag(candidate_id)
    expected_citation_tags = expected_citation_tags_from_answers(
        feedback_eval_expected_answers(feedback)
    )
    filtered_feedback_tags = [
        "collection:rag-ingestion-candidate",
        candidate_tag,
        *expected_citation_tags,
    ]
    return FeedbackNextAction(
        id="bulk-review-candidate-feedback",
        label="Close queued feedback for this RAG candidate after eval and LangSmith review",
        feedbackId=feedback.feedback_id,
        evalCaseId=case_id,
        sourceRunId=run_id,
        candidateTag=candidate_tag,
        reportFile=langsmith_report_file,
        releaseReadinessFile=RELEASE_READINESS_FILE,
        readinessReportArg=readiness_report_arg,
        requiredReadinessReports=required_readiness_reports,
        readinessReports=readiness_reports,
        dependsOnActionIds=["refresh-readiness"],
        feedbackSource=feedback_action_source(feedback),
        workflowTags=filtered_feedback_tags,
        feedbackTags=filtered_feedback_tags,
        requiredReviewNote=RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
        command=rag_candidate_feedback_bulk_review_action(
            candidate_tag,
            source=feedback.source,
            extra_review_tags=expected_citation_tags,
        ),
    )


def feedback_eval_persist_command(
    *,
    feedback: Feedback,
    case_file: str,
    run_file: str,
    langsmith_report_file: str,
) -> str:
    return (
        "reactor-agent-eval-apply "
        f"--case-file {case_file} "
        f"--run-file {run_file} "
        f"--suite-file {feedback_eval_suite_file(feedback)} "
        f"--dataset-name {feedback_eval_dataset_name(feedback)} "
        "--require-source-run-id --require-run-file --require-context-diagnostics "
        f"--langsmith-dry-run-report-file {langsmith_report_file} "
        "--output table"
    )


def feedback_eval_summary_command(
    *,
    feedback: Feedback,
    langsmith_report_file: str,
    review_status: str = "",
    review_tags: Sequence[str] = (),
    review_note: str = "",
) -> str:
    feedback_review_args = command_args(
        f"--feedback-review-status {quote(review_status)}" if review_status.strip() else "",
        command_feedback_review_tag_args(list(review_tags)),
        f"--feedback-review-note {quote(review_note)}" if review_note.strip() else "",
    )
    return (
        "reactor-agent-eval-apply "
        f"--suite-file {feedback_eval_suite_file(feedback)} "
        f"--dataset-name {feedback_eval_dataset_name(feedback)} "
        "--summary "
        f"--langsmith-dry-run-report-file {langsmith_report_file} "
        f"{feedback_review_args} "
        "--output table"
    )


def feedback_eval_case_id(*, feedback: Feedback, run_id: str) -> str:
    return workflow_feedback_eval_case_id(feedback, run_id=run_id) or (
        f"case_{safe_command_id(run_id)}"
    )


def feedback_rag_candidate_id_from_run_id(run_id: str) -> str:
    return workflow_feedback_rag_candidate_id_from_run_id(run_id)


def feedback_eval_artifact_files(
    *,
    feedback: Feedback,
    case_id: str,
    run_id: str,
) -> tuple[str, str]:
    if feedback_indicates_rag_candidate_collection(feedback):
        return (
            f"evals/cases/{case_id}.json",
            f"evals/runs/{command_slug(run_id)}.json",
        )
    return "promoted-case.json", "promoted-run.json"


def feedback_eval_apply_args(*, feedback: Feedback, case_id: str) -> str:
    if feedback_indicates_rag_candidate_collection(feedback):
        return (
            "--apply-suite-file evals/regression/rag-ingestion-candidate.json "
            "--apply-dataset-name reactor-rag-ingestion-candidate"
        )
    return "--apply-suite-file tests/fixtures/agent-eval/regression-suite.json"


def feedback_langsmith_dry_run_report_file(*, feedback: Feedback, case_id: str) -> str:
    if feedback_indicates_rag_candidate_collection(feedback):
        return f"artifacts/langsmith/rag-ingestion-candidate-{case_id}.json"
    return "reports/langsmith-eval-sync-dry-run.json"


def feedback_langsmith_next_actions(
    *,
    feedback: Feedback,
    case_id: str,
    run_id: str,
    langsmith_report_file: str,
) -> list[FeedbackNextAction]:
    suite_file = feedback_eval_suite_file(feedback)
    dataset_name = feedback_eval_dataset_name(feedback)
    required_readiness_reports, readiness_reports, readiness_report_arg = (
        feedback_langsmith_readiness_metadata(
            feedback=feedback,
            langsmith_report_file=langsmith_report_file,
        )
    )
    feedback_source = feedback_action_source(feedback)
    requires_hardening_readiness = feedback_requires_hardening_readiness(feedback)
    readiness_command = langsmith_release_readiness_command(langsmith_report_file)
    readiness_label = "Refresh release readiness with the promoted LangSmith report"
    if requires_hardening_readiness:
        readiness_label = "Refresh release readiness with promoted LangSmith and hardening reports"
        if feedback_indicates_rag_candidate_collection(feedback):
            readiness_label = (
                "Refresh release readiness with candidate LangSmith and hardening reports"
            )
        readiness_command = release_readiness_command_for_reports(
            required_reports=required_readiness_reports,
            report_files=readiness_reports,
        )
    preflight_command = (
        "uv run reactor-langsmith-eval-sync "
        f"--suite-file {suite_file} "
        f"--dataset-name {dataset_name} "
        f"--report-file {langsmith_report_file} "
        "--preflight-only --output table"
    )
    sync_command = (
        "uv run reactor-langsmith-eval-sync "
        f"--suite-file {suite_file} "
        f"--dataset-name {dataset_name} "
        f"--report-file {langsmith_report_file} "
        "--output table"
    )
    actions = [
        FeedbackNextAction(
            id="preflight-langsmith",
            label="Preflight LangSmith credentials before syncing the promoted eval",
            feedbackId=feedback.feedback_id,
            evalCaseId=case_id,
            sourceRunId=run_id,
            reportFile=langsmith_report_file,
            suiteFile=suite_file,
            datasetName=dataset_name,
            preflightFile=RELEASE_SMOKE_PREFLIGHT_FILE,
            preflightEnvTemplate=RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
            releaseReadinessFile=RELEASE_READINESS_FILE,
            releaseReadinessCommand=readiness_command,
            readinessReportArg=readiness_report_arg,
            requiredReadinessReports=required_readiness_reports,
            readinessReports=readiness_reports,
            requiredEnvAnyOf=LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
            dependsOnActionIds=["summarize-langsmith"],
            recommendedEnv=LANGSMITH_SYNC_RECOMMENDED_ENV,
            feedbackSource=feedback_source,
            remediationCommand=preflight_command,
            envFileCommand=env_file_command(preflight_command),
            command=preflight_command,
        ),
        FeedbackNextAction(
            id="sync-langsmith",
            label="Sync the promoted eval to LangSmith",
            feedbackId=feedback.feedback_id,
            evalCaseId=case_id,
            sourceRunId=run_id,
            reportFile=langsmith_report_file,
            suiteFile=suite_file,
            datasetName=dataset_name,
            releaseReadinessFile=RELEASE_READINESS_FILE,
            releaseReadinessCommand=readiness_command,
            readinessReportArg=readiness_report_arg,
            requiredReadinessReports=required_readiness_reports,
            readinessReports=readiness_reports,
            requiredEnvAnyOf=LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
            dependsOnActionIds=["preflight-langsmith"],
            recommendedEnv=LANGSMITH_SYNC_RECOMMENDED_ENV,
            feedbackSource=feedback_source,
            remediationCommand=sync_command,
            envFileCommand=env_file_command(sync_command),
            command=sync_command,
        ),
    ]
    if "hardening_suite" in required_readiness_reports:
        actions.append(
            FeedbackNextAction(
                id="generate-hardening-suite",
                label="Generate the hardening suite report required for minor boundary review",
                feedbackId=feedback.feedback_id,
                evalCaseId=case_id,
                sourceRunId=run_id,
                reportFile=langsmith_report_file,
                suiteFile=suite_file,
                datasetName=dataset_name,
                readinessReportArg=(
                    f"--readiness-report hardening_suite={HARDENING_SUITE_REPORT_FILE}"
                ),
                requiredReadinessReports=required_readiness_reports,
                readinessReports=readiness_reports,
                releaseReadinessCommand=readiness_command,
                dependsOnActionIds=["sync-langsmith"],
                feedbackSource=feedback_source,
                command=rag_ingestion_lifecycle_remediation_command(),
            )
        )
    actions.append(
        FeedbackNextAction(
            id="refresh-readiness",
            label=readiness_label,
            feedbackId=feedback.feedback_id,
            evalCaseId=case_id,
            sourceRunId=run_id,
            reportFile=langsmith_report_file,
            suiteFile=suite_file,
            datasetName=dataset_name,
            preflightFile=RELEASE_SMOKE_PREFLIGHT_FILE,
            preflightEnvTemplate=RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
            replatformReadinessFile=REPLATFORM_READINESS_FILE,
            smokePlanFile=RELEASE_SMOKE_PLAN_FILE,
            releaseEvidenceFile=RELEASE_EVIDENCE_FILE,
            releaseReadinessFile=RELEASE_READINESS_FILE,
            remediationCommand=readiness_command,
            readinessReportArg=readiness_report_arg,
            requiredReadinessReports=required_readiness_reports,
            readinessReports=readiness_reports,
            latestTagCommand=LATEST_TAG_COMMAND,
            recommendedTagSource=RECOMMENDED_TAG_SOURCE,
            minorBoundaryReports=(
                required_readiness_reports
                if feedback_indicates_rag_candidate_collection(feedback)
                else None
            ),
            dependsOnActionIds=(
                ["generate-hardening-suite"]
                if "hardening_suite" in required_readiness_reports
                else ["sync-langsmith"]
            ),
            feedbackSource=feedback_source,
            command=readiness_command,
        )
    )
    return actions


def feedback_langsmith_readiness_metadata(
    *,
    feedback: Feedback,
    langsmith_report_file: str,
) -> tuple[list[str], dict[str, str], str]:
    if feedback_requires_hardening_readiness(feedback):
        required_reports = ["hardening_suite", "langsmith_eval_sync"]
        report_files = {
            "hardening_suite": HARDENING_SUITE_REPORT_FILE,
            "langsmith_eval_sync": langsmith_report_file,
        }
    else:
        required_reports = ["langsmith_eval_sync"]
        report_files = {"langsmith_eval_sync": langsmith_report_file}
    return (
        required_reports,
        report_files,
        readiness_report_args_for_reports(
            required_reports=required_reports,
            report_files=report_files,
        ),
    )


def feedback_review_done_note(required_readiness_reports: list[str]) -> str:
    if "hardening_suite" in required_readiness_reports:
        return (
            f"{HARDENING_FEEDBACK_REVIEW_NOTE} "
            f"Required readiness reports: {', '.join(required_readiness_reports)}."
        )
    return RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE


def feedback_requires_hardening_readiness(feedback: Feedback) -> bool:
    return feedback_indicates_rag_candidate_collection(
        feedback
    ) or feedback_requires_citation_marker_eval(feedback)


def feedback_memory_review_action(feedback: Feedback) -> FeedbackNextAction | None:
    if "memory" not in feedback_workflow_tags(feedback):
        return None
    subject_id = (feedback.user_id or "").strip()
    if not subject_id:
        return None
    return FeedbackNextAction(
        id="review-memory",
        label="Inspect memory state and proposed memory review queue",
        feedbackId=feedback.feedback_id,
        subjectUserId=subject_id,
        command=(
            f"reactor-memory get --target-user-id {quote(subject_id)} --output table; "
            f"reactor-memory proposals --status proposed --subject-id {quote(subject_id)} "
            "--output table"
        ),
    )


def feedback_memory_lifecycle_action(feedback: Feedback) -> FeedbackNextAction | None:
    if "memory" not in feedback_workflow_tags(feedback):
        return None
    return FeedbackNextAction(
        id="verify-memory-lifecycle",
        label="Verify memory lifecycle hardening before closing the feedback",
        feedbackId=feedback.feedback_id,
        preflightFile=RELEASE_SMOKE_PREFLIGHT_FILE,
        preflightEnvTemplate=RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
        replatformReadinessFile=REPLATFORM_READINESS_FILE,
        smokePlanFile=RELEASE_SMOKE_PLAN_FILE,
        releaseEvidenceFile=RELEASE_EVIDENCE_FILE,
        releaseReadinessFile=RELEASE_READINESS_FILE,
        readinessReportArg=f"--readiness-report hardening_suite={HARDENING_SUITE_REPORT_FILE}",
        requiredReadinessReports=["hardening_suite"],
        readinessReports={"hardening_suite": HARDENING_SUITE_REPORT_FILE},
        command=MEMORY_LIFECYCLE_ACTION,
    )


def feedback_eval_suite_file(feedback: Feedback) -> str:
    if feedback_indicates_rag_candidate_collection(feedback):
        return "evals/regression/rag-ingestion-candidate.json"
    return "tests/fixtures/agent-eval/regression-suite.json"


def feedback_eval_dataset_name(feedback: Feedback) -> str:
    if feedback_indicates_rag_candidate_collection(feedback):
        return "reactor-rag-ingestion-candidate"
    return "reactor-regression"


def feedback_eval_workflow_tags(*, feedback: Feedback, run_id: str) -> list[str]:
    tags = list(feedback_workflow_tags(feedback))
    source_workflow_tag = feedback_source_workflow_tag(feedback)
    if source_workflow_tag:
        tags.append(source_workflow_tag)
    if feedback_rag_candidate_id(feedback) is None and feedback_indicates_rag_candidate_collection(
        feedback
    ):
        tags.append(rag_candidate_workflow_tag(feedback_rag_candidate_id_from_run_id(run_id)))
    return list(dict.fromkeys(tags))


def feedback_source_workflow_tag(feedback: Feedback) -> str:
    source = optional_safe_command_id(feedback.source)
    if source.startswith("slack"):
        return "slack"
    return ""


def feedback_eval_promotion_tags(
    *,
    feedback: Feedback,
    workflow_tags: list[str],
    expected_answers: list[str],
) -> list[str]:
    tags = [
        f"feedback:{feedback.feedback_id}",
        f"feedback-rating:{feedback.rating.value.lower()}",
    ]
    tags.extend(workflow_tags)
    tags.extend(feedback_expected_citation_tags(feedback))
    tags.extend(expected_citation_tags_from_answers(expected_answers))
    return list(dict.fromkeys(tags))


def expected_citation_tags_from_answers(expected_answers: list[str]) -> list[str]:
    tags: list[str] = []
    for answer in expected_answers:
        value = answer.strip()
        if not value.startswith("[") or not value.endswith("]"):
            continue
        citation_id = value[1:-1].strip()
        if citation_id:
            tags.append(f"expected-citation:{citation_id}")
    return tags


def feedback_source_arg(feedback: Feedback) -> str:
    source = optional_safe_command_id(feedback.source)
    if not source:
        return ""
    return f"--feedback-source {quote(source)}"


def feedback_action_source(feedback: Feedback) -> str | None:
    return optional_safe_command_id(feedback.source) or None


def command_tag_args(tags: list[str]) -> str:
    return " ".join(f"--tag {quote(tag)}" for tag in tags)


def command_feedback_review_tag_args(tags: list[str]) -> str:
    return " ".join(f"--feedback-review-tag {quote(tag)}" for tag in tags)


def command_expected_answer_args(expected_answers: list[str]) -> str:
    if not expected_answers:
        return ""
    return " ".join(f"--expected-answer {quote(value)}" for value in expected_answers)


def command_args(*values: str) -> str:
    return " ".join(value.strip() for value in values if value.strip())


def feedback_export_item(feedback: Feedback) -> FeedbackExportItem:
    return FeedbackExportItem(
        feedbackId=feedback.feedback_id,
        query=feedback.query,
        response=feedback.response,
        rating=feedback.rating.value.lower(),
        source=feedback.source,
        timestamp=feedback.created_at.isoformat(),
        comment=feedback.comment,
        runId=feedback.run_id,
        sessionId=feedback.session_id,
        userId=feedback.user_id,
        intent=feedback.intent,
        domain=feedback.domain,
        model=feedback.model,
        promptVersion=feedback.prompt_version,
        toolsUsed=feedback.tools_used,
        durationMs=feedback.duration_ms,
        tags=feedback.tags,
        templateId=feedback.template_id,
        reviewStatus=feedback.review_status,
        reviewTags=feedback.review_tags,
        reviewedBy=feedback.reviewed_by,
        reviewedAt=feedback.reviewed_at.isoformat() if feedback.reviewed_at is not None else None,
        reviewNote=feedback.review_note,
        version=feedback.version,
        updatedAt=feedback.updated_at.isoformat(),
        workflow=feedback_export_workflow(feedback),
        nextActions=feedback_next_actions(feedback),
    )


def feedback_export_workflow(feedback: Feedback) -> FeedbackExportWorkflow | None:
    candidate_id = feedback_resolved_rag_candidate_id(feedback)
    if candidate_id is None:
        return None
    candidate_tag = rag_candidate_workflow_tag(candidate_id)
    return FeedbackExportWorkflow(
        type="rag_ingestion_candidate",
        candidateId=candidate_id,
        collection="rag-ingestion-candidate",
        sourceUri=f"rag-ingestion-candidate:{candidate_id}",
        evalCaseId=rag_candidate_case_id(candidate_id),
        runId=feedback.run_id,
        sourceRunId=feedback.run_id,
        feedbackSource=feedback.source,
        feedbackTag=candidate_tag,
    )


def feedback_resolved_rag_candidate_id(feedback: Feedback) -> str | None:
    candidate_id = feedback_rag_candidate_id(feedback)
    if candidate_id is not None:
        return candidate_id
    if not feedback_indicates_rag_candidate_collection(feedback):
        return None
    run_id = (feedback.run_id or "").strip()
    if not run_id:
        return None
    return feedback_rag_candidate_id_from_run_id(run_id)


def parse_feedback_rating(value: str | None) -> FeedbackRating:
    normalized = str(value or "").strip().upper()
    if normalized in {"THUMBS_UP", "UP", "POSITIVE"}:
        return FeedbackRating.THUMBS_UP
    if normalized in {"THUMBS_DOWN", "DOWN", "NEGATIVE"}:
        return FeedbackRating.THUMBS_DOWN
    raise invalid_request(f"Invalid rating: {value}")


def normalize_feedback_tag_filter(values: list[str] | None) -> list[str] | None:
    tags = sorted({value.strip() for value in values or [] if value.strip()})
    return tags or None


def normalize_feedback_source_filter(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def normalize_feedback_case_id_filter(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def parse_review_status(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"inbox", "done"}:
        raise invalid_request(f"Invalid review status: {value}")
    return normalized


def parse_if_match(value: str | None) -> int:
    if value is None:
        raise invalid_request("If-Match header is required")
    normalized = value.strip().strip('"')
    try:
        return int(normalized)
    except ValueError as error:
        raise invalid_request("If-Match header must be an integer version") from error


def feedback_review_version_conflict_detail(
    feedback: Feedback,
    *,
    expected_version: int,
) -> dict[str, object]:
    detail: dict[str, object] = {
        "message": "feedback review version conflict",
        "feedbackId": feedback.feedback_id,
        "expectedVersion": expected_version,
        "currentVersion": feedback.version,
        "nextAction": (
            f"reactor-admin feedback --feedback-id {quote(feedback.feedback_id)} --output table"
        ),
        "reviewQueueAction": feedback_review_queue_action(feedback),
    }
    detail.update(feedback_handoff_metadata(feedback))
    detail.update(feedback_readiness_handoff_metadata(feedback))
    next_actions = feedback_next_actions(feedback)
    if next_actions:
        detail["readyNextActionIds"] = ready_feedback_next_action_ids(next_actions)
        detail["blockedNextActionIds"] = blocked_feedback_next_action_ids(next_actions)
        detail["nextActionStates"] = feedback_next_action_states(next_actions)
        detail["nextActions"] = [
            action.model_dump(by_alias=True, exclude_none=True) for action in next_actions
        ]
    return detail


def feedback_review_queue_action(feedback: Feedback) -> str:
    source_arg = f" --source {quote(feedback.source)}" if feedback.source else ""
    tag_args = "".join(f" --tag {quote(tag)}" for tag in feedback_workflow_tags(feedback))
    return (
        f"reactor-admin feedback --rating {quote(feedback.rating.value.lower())}"
        f"{source_arg} --review-status inbox{tag_args} --limit 10 --output table"
    )


def feedback_not_found(feedback_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Feedback not found: {feedback_id}",
    )


def invalid_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
