from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping, Sequence
from shlex import quote
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from langsmith import Client as LangSmithClient
from langsmith.utils import LangSmithAuthError

from reactor.api.auth import require_permission
from reactor.api.schemas.eval import (
    AgentEvalCaseRequest,
    AgentEvalCaseResponse,
    AgentEvalNextAction,
    AgentEvalResultResponse,
    AgentEvalRunLogResponse,
    EvaluateRunRequest,
    LangSmithEvalSyncRequest,
    LangSmithEvalSyncResponse,
    PromoteEvalCaseRequest,
    ReplayEvalCaseResponse,
)
from reactor.auth.rbac import AuthPrincipal
from reactor.core.container import AppContainer
from reactor.core.settings import Settings
from reactor.evals.evaluator import AgentEvalRegressionEvaluator
from reactor.evals.judge import AgentEvalLlmJudgeResult
from reactor.evals.langsmith_dataset import (
    LangSmithEvalDatasetExporter,
    LangSmithEvalDatasetSecretError,
)
from reactor.evals.models import (
    DOCUMENTS_ASK_TAG,
    EXPECTED_CITATION_TAG_PREFIX,
    RAG_TAG,
    AgentEvalCaseRecord,
    AgentEvalRunRecord,
    AgentEvalStoredResultRecord,
    is_bracketed_citation_marker,
    is_citation_safe_id,
)
from reactor.observability.tracing import redact_trace_payload
from reactor.persistence.run_store import SessionRunRecord
from reactor.response.structured import (
    context_manifest_citation_ids,
    context_manifest_unsafe_citation_ids,
)
from reactor.runs.service import RunService

router = APIRouter(tags=["agent-eval"])


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


@router.get(
    "/api/admin/agent-eval/cases",
    response_model=list[AgentEvalCaseResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/agent-eval/cases",
    response_model=list[AgentEvalCaseResponse],
    response_model_by_alias=True,
)
async def list_eval_cases(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("eval:read"))],
    enabledOnly: bool = True,
    tags: str | None = None,
    limit: int = Query(default=100, ge=0, le=500),
) -> list[AgentEvalCaseResponse]:
    records = await require_eval_case_store(request).list(
        tenant_id=principal.tenant_id,
        enabled_only=enabledOnly,
        tags=parse_tags(tags),
        limit=limit,
    )
    return [eval_case_response(record) for record in records]


@router.post(
    "/api/admin/agent-eval/cases",
    response_model=AgentEvalCaseResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/v1/admin/agent-eval/cases",
    response_model=AgentEvalCaseResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_eval_case(
    request: Request,
    body: AgentEvalCaseRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("eval:write"))],
) -> AgentEvalCaseResponse:
    record = eval_case_from_request(body, tenant_id=principal.tenant_id)
    try:
        record.validate()
        saved = await require_eval_case_store(request).save(record)
    except ValueError as error:
        raise invalid_request(error) from error
    return eval_case_response(saved)


@router.get(
    "/api/admin/agent-eval/run-logs",
    response_model=list[AgentEvalRunLogResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/agent-eval/run-logs",
    response_model=list[AgentEvalRunLogResponse],
    response_model_by_alias=True,
)
async def list_eval_run_logs(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("eval:read"))],
    limit: int = Query(default=50, ge=0, le=500),
) -> list[AgentEvalRunLogResponse]:
    records = await require_run_store(request).list_recent_runs(
        tenant_id=principal.tenant_id,
        limit=limit,
    )
    return [eval_run_log_response(record) for record in records]


@router.post(
    "/api/admin/agent-eval/cases/promote",
    response_model=AgentEvalCaseResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/agent-eval/cases/promote",
    response_model=AgentEvalCaseResponse,
    response_model_by_alias=True,
)
async def promote_eval_case(
    request: Request,
    body: PromoteEvalCaseRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("eval:write"))],
) -> AgentEvalCaseResponse:
    run = await find_tenant_run(request, tenant_id=principal.tenant_id, run_id=body.runId)
    try:
        validate_promoted_context_manifest_citation_ids(run, body)
    except ValueError as error:
        raise invalid_request(error) from error
    tags = promoted_tags(run, body)
    record = AgentEvalCaseRecord(
        id=body.id or AgentEvalCaseRecord().id,
        tenant_id=principal.tenant_id,
        name=body.name or f"Eval case from {run.run_id}",
        user_input=run.input_text,
        expected_answer_contains=promoted_expected_answer_contains(run, body, tags=tags),
        forbidden_answer_contains=promoted_forbidden_answer_contains(run, body),
        expected_tool_names=body.expectedToolNames,
        forbidden_tool_names=body.forbiddenToolNames,
        expected_exposed_tool_names=body.expectedExposedToolNames,
        forbidden_exposed_tool_names=body.forbiddenExposedToolNames,
        max_tool_exposure_count=body.maxToolExposureCount,
        agent_type=string_metadata(run.metadata, "agentType", "agent_type"),
        model=string_metadata(run.metadata, "model"),
        enabled=body.enabled,
        tags=tags,
        min_score=body.minScore,
        source_run_id=run.run_id,
    )
    try:
        record.validate()
        saved = await require_eval_case_store(request).save(record)
    except ValueError as error:
        raise invalid_request(error) from error
    return eval_case_response(saved)


@router.post(
    "/api/admin/agent-eval/langsmith/sync",
    response_model=LangSmithEvalSyncResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/agent-eval/langsmith/sync",
    response_model=LangSmithEvalSyncResponse,
    response_model_by_alias=True,
)
async def sync_eval_cases_to_langsmith(
    request: Request,
    body: LangSmithEvalSyncRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("eval:write"))],
) -> LangSmithEvalSyncResponse:
    container = get_container(request)
    api_key = container.settings.observability_langsmith_api_key.strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LangSmith API key is not configured",
        )
    cases = await langsmith_sync_cases(
        request,
        tenant_id=principal.tenant_id,
        case_ids=body.caseIds,
    )
    if not cases:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="at least one enabled eval case is required for LangSmith sync",
        )
    try:
        result = await asyncio.to_thread(
            export_langsmith_cases,
            settings=container.settings,
            dataset_name=body.datasetName,
            cases=cases,
            description=body.description,
        )
    except LangSmithAuthError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LangSmith authentication failed",
        ) from error
    except (LangSmithEvalDatasetSecretError, ValueError) as error:
        raise invalid_request(error) from error
    return langsmith_sync_response(result)


@router.get(
    "/api/admin/agent-eval/cases/{case_id}",
    response_model=AgentEvalCaseResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/agent-eval/cases/{case_id}",
    response_model=AgentEvalCaseResponse,
    response_model_by_alias=True,
)
async def get_eval_case(
    request: Request,
    case_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("eval:read"))],
) -> AgentEvalCaseResponse:
    record = await require_eval_case_store(request).find_by_id(
        tenant_id=principal.tenant_id,
        case_id=case_id,
    )
    if record is None:
        raise eval_case_not_found(case_id)
    return eval_case_response(record)


@router.delete("/api/admin/agent-eval/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/v1/admin/agent-eval/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_eval_case(
    request: Request,
    case_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("eval:write"))],
) -> Response:
    result_store = require_eval_result_store(request)
    await result_store.delete_by_case_id(tenant_id=principal.tenant_id, case_id=case_id)
    deleted = await require_eval_case_store(request).delete(
        tenant_id=principal.tenant_id,
        case_id=case_id,
    )
    if not deleted:
        raise eval_case_not_found(case_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/admin/agent-eval/cases/{case_id}/evaluate-run",
    response_model=ReplayEvalCaseResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/agent-eval/cases/{case_id}/evaluate-run",
    response_model=ReplayEvalCaseResponse,
    response_model_by_alias=True,
)
async def evaluate_run_against_case(
    request: Request,
    case_id: str,
    body: EvaluateRunRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("eval:write"))],
) -> ReplayEvalCaseResponse:
    case_store = require_eval_case_store(request)
    result_store = require_eval_result_store(request)
    case = await case_store.find_by_id(tenant_id=principal.tenant_id, case_id=case_id)
    if case is None:
        raise eval_case_not_found(case_id)
    deterministic = AgentEvalRegressionEvaluator().evaluate(
        case,
        AgentEvalRunRecord(
            run_id=body.runId,
            final_answer=body.finalAnswer,
            tool_names=body.toolNames,
            exposed_tool_names=body.exposedToolNames,
            agent_type=body.agentType,
            model=body.model,
        ),
    )
    stored = await result_store.save(deterministic.to_stored_result(tenant_id=principal.tenant_id))
    related = await result_store.list(
        tenant_id=principal.tenant_id,
        case_id=case.id,
        tier=stored.tier,
        limit=50,
    )
    return ReplayEvalCaseResponse(
        case=eval_case_response(case),
        deterministic=eval_result_response(stored),
        storedResults=tuple(eval_result_response(result) for result in related),
    )


@router.post(
    "/api/admin/agent-eval/cases/{case_id}/evaluate-run/{run_id}",
    response_model=ReplayEvalCaseResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/agent-eval/cases/{case_id}/evaluate-run/{run_id}",
    response_model=ReplayEvalCaseResponse,
    response_model_by_alias=True,
)
async def evaluate_persisted_run_against_case(
    request: Request,
    case_id: str,
    run_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("eval:write"))],
) -> ReplayEvalCaseResponse:
    run = await find_tenant_run(request, tenant_id=principal.tenant_id, run_id=run_id)
    return await evaluate_run_record_against_case(
        request,
        tenant_id=principal.tenant_id,
        case_id=case_id,
        run=eval_run_from_session(run),
    )


@router.post(
    "/api/admin/agent-eval/cases/{case_id}/replay",
    response_model=ReplayEvalCaseResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/agent-eval/cases/{case_id}/replay",
    response_model=ReplayEvalCaseResponse,
    response_model_by_alias=True,
)
async def replay_eval_case(
    request: Request,
    case_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("eval:write"))],
    llmJudge: bool = False,
) -> ReplayEvalCaseResponse:
    case = await require_eval_case_store(request).find_by_id(
        tenant_id=principal.tenant_id,
        case_id=case_id,
    )
    if case is None:
        raise eval_case_not_found(case_id)
    container = get_container(request)
    run_lifecycle_publisher_factory = getattr(container, "run_lifecycle_publisher", None)
    runtime_settings_store_factory = getattr(container, "runtime_settings_store", None)
    result = await RunService(
        container.settings,
        container.run_store(),
        container.graph,
        usage_ledger=getattr(container, "usage_ledger", lambda: None)(),
        tool_provider=getattr(container, "tool_store", lambda: None)(),
        tool_handler=getattr(container, "agent_tool_handler", lambda: None)(),
        tool_invocation_store=getattr(container, "tool_invocation_store", lambda: None)(),
        builtin_tool_specs=getattr(container, "builtin_tool_specs", None),
        checkpointer=getattr(container, "checkpointer", None),
        graph_store=getattr(container, "graph_store", None),
        run_lifecycle_publisher=run_lifecycle_publisher_factory()
        if run_lifecycle_publisher_factory is not None
        else None,
        runtime_settings_store=runtime_settings_store_factory()
        if runtime_settings_store_factory is not None
        else None,
        approval_store=getattr(container, "approval_store", lambda: None)(),
    ).create_run(
        case.user_input,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        thread_id=f"eval-{case.id}",
        metadata={
            "agentEval.replay": True,
            "evalCaseId": case.id,
            "agentType": case.agent_type,
            "model": case.model,
        },
    )
    run = AgentEvalRunRecord(
        run_id=result.run_id,
        final_answer=result.response,
        agent_type=case.agent_type,
        model=case.model,
    )
    return await evaluate_run_record_against_case(
        request,
        tenant_id=principal.tenant_id,
        case_id=case.id,
        run=run,
        llm_judge=llmJudge,
    )


@router.get(
    "/api/admin/agent-eval/results",
    response_model=list[AgentEvalResultResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/agent-eval/results",
    response_model=list[AgentEvalResultResponse],
    response_model_by_alias=True,
)
async def list_eval_results(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("eval:read"))],
    caseId: str | None = None,
    tier: str | None = None,
    limit: int = Query(default=100, ge=0, le=500),
) -> list[AgentEvalResultResponse]:
    results = await require_eval_result_store(request).list(
        tenant_id=principal.tenant_id,
        case_id=caseId,
        tier=tier,
        limit=limit,
    )
    return [eval_result_response(result) for result in results]


def eval_case_from_request(body: AgentEvalCaseRequest, *, tenant_id: str) -> AgentEvalCaseRecord:
    return AgentEvalCaseRecord(
        id=body.id or AgentEvalCaseRecord().id,
        tenant_id=tenant_id,
        name=body.name,
        user_input=body.userInput,
        expected_answer_contains=body.expectedAnswerContains,
        forbidden_answer_contains=body.forbiddenAnswerContains,
        expected_tool_names=body.expectedToolNames,
        forbidden_tool_names=body.forbiddenToolNames,
        expected_exposed_tool_names=body.expectedExposedToolNames,
        forbidden_exposed_tool_names=body.forbiddenExposedToolNames,
        max_tool_exposure_count=body.maxToolExposureCount,
        agent_type=body.agentType,
        model=body.model,
        enabled=body.enabled,
        tags=body.tags,
        min_score=body.minScore,
        source_run_id=body.sourceRunId,
    )


def eval_case_response(record: AgentEvalCaseRecord) -> AgentEvalCaseResponse:
    return AgentEvalCaseResponse(
        id=record.id,
        name=record.name,
        userInput=record.user_input,
        expectedAnswerContains=record.expected_answer_contains,
        forbiddenAnswerContains=record.forbidden_answer_contains,
        expectedToolNames=record.expected_tool_names,
        forbiddenToolNames=record.forbidden_tool_names,
        expectedExposedToolNames=record.expected_exposed_tool_names,
        forbiddenExposedToolNames=record.forbidden_exposed_tool_names,
        maxToolExposureCount=record.max_tool_exposure_count,
        agentType=record.agent_type,
        model=record.model,
        enabled=record.enabled,
        tags=record.tags,
        minScore=record.min_score,
        sourceRunId=record.source_run_id,
        assertionCount=record.assertion_count,
        createdAt=record.created_at.isoformat(),
        updatedAt=record.updated_at.isoformat(),
        nextActions=eval_case_next_actions(record),
    )


def eval_case_next_actions(record: AgentEvalCaseRecord) -> tuple[AgentEvalNextAction, ...]:
    if record.source_run_id is None or not record.source_run_id.strip():
        return ()
    command = (
        f"reactor-runs promote-eval {quote(record.source_run_id)} --case-id {quote(record.id)} "
        "--case-file promoted-case.json --run-file promoted-run.json "
        "--apply-suite-file tests/fixtures/agent-eval/regression-suite.json "
        "--apply-dry-run --apply-require-source-run-id "
        "--apply-require-run-file --apply-require-context-diagnostics "
        "--apply-suite-summary "
        "--langsmith-dry-run-report-file reports/langsmith-eval-sync-dry-run.json "
        "--output table"
    )
    return (
        AgentEvalNextAction(
            id="apply-to-regression-suite",
            label="Apply this promoted case and source run to the regression suite",
            command=command,
        ),
    )


def eval_result_response(record: AgentEvalStoredResultRecord) -> AgentEvalResultResponse:
    return AgentEvalResultResponse(
        id=record.id,
        caseId=record.case_id,
        runId=record.run_id,
        tier=record.tier,
        passed=record.passed,
        score=record.score,
        reasons=record.reasons,
        evaluatedAt=record.evaluated_at.isoformat(),
    )


def eval_run_log_response(record: SessionRunRecord) -> AgentEvalRunLogResponse:
    tool_names = tuple_metadata(record.metadata, "toolNames", "tool_names", "toolsUsed")
    exposed_tools = tuple_metadata(record.metadata, "exposedToolNames", "exposed_tool_names")
    errors = tuple_metadata(record.metadata, "errors")
    return AgentEvalRunLogResponse(
        runId=record.run_id,
        evalCaseId=string_metadata(record.metadata, "evalCaseId", "eval_case_id"),
        agentType=string_metadata(record.metadata, "agentType", "agent_type") or "unknown",
        model=string_metadata(record.metadata, "model") or "unknown",
        toolExposureCount=len(exposed_tools),
        toolExposureNames=exposed_tools,
        toolCallCount=len(tool_names),
        retrievedChunkCount=int_metadata(
            record.metadata,
            "retrievedChunkCount",
            "retrieved_chunk_count",
        ),
        errorCount=len(errors),
        finalAnswerPreview=(record.response_text or "")[:240],
    )


def eval_run_from_session(record: SessionRunRecord) -> AgentEvalRunRecord:
    return AgentEvalRunRecord(
        run_id=record.run_id,
        final_answer=record.response_text or "",
        tool_names=tuple_metadata(record.metadata, "toolNames", "tool_names", "toolsUsed"),
        exposed_tool_names=tuple_metadata(
            record.metadata,
            "exposedToolNames",
            "exposed_tool_names",
        ),
        agent_type=string_metadata(record.metadata, "agentType", "agent_type"),
        model=string_metadata(record.metadata, "model"),
    )


def promoted_forbidden_answer_contains(
    run: SessionRunRecord,
    body: PromoteEvalCaseRequest,
) -> tuple[str, ...]:
    if body.forbiddenAnswerContains:
        return body.forbiddenAnswerContains
    if run.status != "failed":
        return ()
    observed = str(redact_trace_payload(run.response_text or "")).strip()
    return (observed[:240],) if observed else ()


def promoted_expected_answer_contains(
    run: SessionRunRecord,
    body: PromoteEvalCaseRequest,
    *,
    tags: Sequence[str],
) -> tuple[str, ...]:
    expected = list(body.expectedAnswerContains)
    if not is_documents_ask_tags(tags):
        return tuple(expected)
    if any(is_bracketed_citation_marker(item) for item in expected):
        return tuple(expected)
    for citation_id in promoted_context_manifest_citation_ids(run):
        marker = f"[{citation_id}]"
        if marker not in expected:
            expected.append(marker)
    return tuple(expected)


def promoted_tags(
    run: SessionRunRecord,
    body: PromoteEvalCaseRequest,
) -> tuple[str, ...]:
    tags = list(body.tags)
    citation_ids = promoted_context_manifest_citation_ids(run)
    if run_is_documents_ask_with_rag_citations(run, citation_ids):
        tags.extend([RAG_TAG, DOCUMENTS_ASK_TAG])
    if is_documents_ask_tags(tags):
        for citation_id in citation_ids:
            if is_citation_safe_id(citation_id):
                tags.append(f"{EXPECTED_CITATION_TAG_PREFIX}{citation_id}")
    if run.status != "failed":
        return tuple(tags)
    tags.append("promoted-from-failed-run")
    reasons = tuple_metadata(run.metadata, "errors", "failureReasons", "failure_reasons", "error")
    for reason in reasons or ("run_failed",):
        tags.append(f"failure-reason:{normalized_failure_tag(reason)}")
    return tuple(dict.fromkeys(tags))


def validate_promoted_context_manifest_citation_ids(
    run: SessionRunRecord,
    body: PromoteEvalCaseRequest,
) -> None:
    unsafe_citation_ids = promoted_context_manifest_unsafe_citation_ids(run)
    if not unsafe_citation_ids:
        return
    if not (
        string_metadata(run.metadata, "agentType", "agent_type") == DOCUMENTS_ASK_TAG
        or is_documents_ask_tags(body.tags)
    ):
        return
    raise ValueError(
        "documents-ask eval promotion requires citation-safe context manifest citation ids"
    )


def promoted_context_manifest_citation_ids(run: SessionRunRecord) -> tuple[str, ...]:
    manifest = metadata_json_object(run.metadata, "contextManifest", "context_manifest")
    if manifest is None:
        return ()
    return tuple(context_manifest_citation_ids(manifest))


def promoted_context_manifest_unsafe_citation_ids(run: SessionRunRecord) -> tuple[str, ...]:
    manifest = metadata_json_object(run.metadata, "contextManifest", "context_manifest")
    if manifest is None:
        return ()
    return tuple(context_manifest_unsafe_citation_ids(manifest))


def metadata_json_object(metadata: Mapping[str, Any], *keys: str) -> dict[str, object] | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, Mapping):
            typed_value = cast(Mapping[object, object], value)
            return {str(item_key): item_value for item_key, item_value in typed_value.items()}
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, Mapping):
            typed_decoded = cast(Mapping[object, object], decoded)
            return {str(item_key): item_value for item_key, item_value in typed_decoded.items()}
    return None


def is_documents_ask_tags(tags: Sequence[str]) -> bool:
    return any(tag.strip() == DOCUMENTS_ASK_TAG for tag in tags)


def run_is_documents_ask_with_rag_citations(
    run: SessionRunRecord,
    citation_ids: Sequence[str],
) -> bool:
    return (
        bool(citation_ids)
        and (string_metadata(run.metadata, "agentType", "agent_type") or "").strip()
        == DOCUMENTS_ASK_TAG
    )


def normalized_failure_tag(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(redact_trace_payload(value)).strip())
    normalized = normalized.strip("._-").lower()
    return normalized or "unknown"


async def evaluate_run_record_against_case(
    request: Request,
    *,
    tenant_id: str,
    case_id: str,
    run: AgentEvalRunRecord,
    llm_judge: bool = False,
) -> ReplayEvalCaseResponse:
    case_store = require_eval_case_store(request)
    result_store = require_eval_result_store(request)
    case = await case_store.find_by_id(tenant_id=tenant_id, case_id=case_id)
    if case is None:
        raise eval_case_not_found(case_id)
    deterministic = AgentEvalRegressionEvaluator().evaluate(case, run)
    stored = await result_store.save(deterministic.to_stored_result(tenant_id=tenant_id))
    stored_results = [stored]
    if llm_judge:
        stored_results.append(
            await result_store.save(await judge_stored_result(request, tenant_id, case, run))
        )
    related = await result_store.list(
        tenant_id=tenant_id,
        case_id=case.id,
        limit=50,
    )
    return ReplayEvalCaseResponse(
        case=eval_case_response(case),
        deterministic=eval_result_response(stored),
        storedResults=tuple(
            eval_result_response(result) for result in preserve_saved_order(stored_results, related)
        ),
    )


async def judge_stored_result(
    request: Request,
    tenant_id: str,
    case: AgentEvalCaseRecord,
    run: AgentEvalRunRecord,
) -> AgentEvalStoredResultRecord:
    judge = optional_eval_llm_judge(request)
    if judge is None:
        return AgentEvalLlmJudgeResult(
            passed=False,
            score=0.0,
            reason="LLM judge unavailable",
        ).to_stored_result(tenant_id=tenant_id, case_id=case.id, run_id=run.run_id)
    result = await judge.judge(case, run)
    return result.to_stored_result(tenant_id=tenant_id, case_id=case.id, run_id=run.run_id)


def preserve_saved_order(
    saved: list[AgentEvalStoredResultRecord],
    related: list[AgentEvalStoredResultRecord],
) -> list[AgentEvalStoredResultRecord]:
    saved_ids = {record.id for record in saved}
    return [*saved, *(record for record in related if record.id not in saved_ids)]


async def find_tenant_run(request: Request, *, tenant_id: str, run_id: str) -> SessionRunRecord:
    run = await require_run_store(request).find_session(run_id=run_id)
    if run is None or run.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"run log not found: {run_id}",
        )
    return run


async def langsmith_sync_cases(
    request: Request,
    *,
    tenant_id: str,
    case_ids: Sequence[str],
) -> list[AgentEvalCaseRecord]:
    store = require_eval_case_store(request)
    normalized_ids = tuple(
        dict.fromkeys(case_id.strip() for case_id in case_ids if case_id.strip())
    )
    if not normalized_ids:
        return await store.list(tenant_id=tenant_id, enabled_only=True, limit=100)
    cases: list[AgentEvalCaseRecord] = []
    for case_id in normalized_ids:
        record = await store.find_by_id(tenant_id=tenant_id, case_id=case_id)
        if record is None:
            raise eval_case_not_found(case_id)
        if not record.enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"disabled eval case cannot be synced: {case_id}",
            )
        cases.append(record)
    return cases


def export_langsmith_cases(
    *,
    settings: Settings,
    dataset_name: str,
    cases: Sequence[AgentEvalCaseRecord],
    description: str | None,
) -> dict[str, object]:
    endpoint = settings.observability_langsmith_endpoint.strip() or None
    client = LangSmithClient(
        api_url=endpoint,
        api_key=settings.observability_langsmith_api_key.strip(),
        hide_inputs=True,
        hide_outputs=True,
        hide_metadata=True,
    )
    return LangSmithEvalDatasetExporter(client).export_cases(
        dataset_name=dataset_name,
        cases=cases,
        description=description,
        source_suite="reactor-admin:persisted-eval-cases",
    )


def langsmith_sync_response(result: Mapping[str, object]) -> LangSmithEvalSyncResponse:
    sdk_contract = object_mapping(result.get("sdkContract"))
    sdk_contract.update(
        {
            "source": "persisted_tenant_eval_cases",
            "sourceControlledCases": False,
        }
    )
    return LangSmithEvalSyncResponse(
        ok=True,
        status="passed",
        scope="langsmith_persisted_eval_dataset_sync",
        mode="langsmith_dataset_sync",
        datasetName=str(result.get("datasetName", "")),
        created=result.get("created") is True,
        examples=int_value(result.get("examples")),
        exampleIds=string_sequence(result.get("exampleIds")) or (),
        caseIds=string_sequence(result.get("caseIds")) or (),
        metadataCaseIds=string_sequence(result.get("metadataCaseIds")) or (),
        sourceRunIds=string_sequence(result.get("sourceRunIds")) or (),
        caseSourceRunIds=string_mapping(result.get("caseSourceRunIds")),
        splitCounts=int_mapping(result.get("splitCounts")),
        secretFree=True,
        exampleContract=object_mapping(result.get("exampleContract")),
        sdkContract=sdk_contract,
    )


def string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): item
        for key, item in cast(Mapping[object, object], value).items()
        if isinstance(item, str)
    }


def int_mapping(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): item
        for key, item in cast(Mapping[object, object], value).items()
        if isinstance(item, int) and not isinstance(item, bool)
    }


def int_value(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def object_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in cast(Mapping[object, object], value).items()}


def string_metadata(metadata: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def int_metadata(metadata: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, int):
            return value
    return 0


def tuple_metadata(metadata: Mapping[str, Any], *keys: str) -> tuple[str, ...]:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str):
            return (value,)
        strings = string_sequence(value)
        if strings is not None:
            return strings
    return ()


def string_sequence(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return None
    strings: list[str] = []
    for item in cast(Sequence[object], value):
        if not isinstance(item, str):
            return None
        strings.append(item)
    return tuple(strings)


def parse_tags(raw: str | None) -> set[str] | None:
    if raw is None:
        return None
    tags = {part.strip() for part in raw.split(",") if part.strip()}
    return tags or None


def require_eval_case_store(request: Request):
    store = get_container(request).eval_case_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="eval store unavailable",
        )
    return store


def require_eval_result_store(request: Request):
    store = get_container(request).eval_result_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="eval store unavailable",
        )
    return store


def require_run_store(request: Request):
    store = get_container(request).run_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="run store unavailable",
        )
    return store


def optional_eval_llm_judge(request: Request):
    container = get_container(request)
    if not hasattr(container, "eval_llm_judge"):
        return None
    return container.eval_llm_judge()


def eval_case_not_found(case_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"agent eval case not found: {case_id}",
    )


def invalid_request(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
