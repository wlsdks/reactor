from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from reactor.api.auth import require_permission
from reactor.api.schemas.scheduler import (
    PaginatedScheduledExecutionsResponse,
    PaginatedScheduledJobsResponse,
    ScheduledJobExecutionResponse,
    ScheduledJobRequest,
    ScheduledJobResponse,
    SchedulerTriggerResponse,
)
from reactor.auth.rbac import AuthPrincipal
from reactor.core.container import AppContainer
from reactor.persistence.scheduler_store import (
    SqlAlchemyScheduledJobDeadLetterStore,
    SqlAlchemyScheduledJobExecutionStore,
    SqlAlchemySchedulerStore,
)
from reactor.scheduler.service import (
    ScheduledJobExecutionRecord,
    ScheduledJobRecord,
    parse_job_type,
    scheduler_failure_reason,
    scheduler_result_preview,
)
from reactor.scheduler.worker import ScheduledJobExecutor, SchedulerWorker, SchedulerWorkerConfig

router = APIRouter(tags=["scheduler"])


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def scheduler_store(request: Request) -> SqlAlchemySchedulerStore | None:
    return get_container(request).scheduler_store()


def execution_store(request: Request) -> SqlAlchemyScheduledJobExecutionStore | None:
    return get_container(request).scheduled_job_execution_store()


def dead_letter_store(request: Request) -> SqlAlchemyScheduledJobDeadLetterStore | None:
    container = get_container(request)
    accessor = getattr(container, "scheduled_job_dead_letter_store", None)
    return accessor() if accessor is not None else None


def require_scheduler_store(request: Request) -> SqlAlchemySchedulerStore:
    store = scheduler_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "DynamicSchedulerService not configured"},
        )
    return store


def require_execution_store(request: Request) -> SqlAlchemyScheduledJobExecutionStore:
    store = execution_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "DynamicSchedulerService not configured"},
        )
    return store


@router.get(
    "/api/scheduler/jobs",
    response_model=PaginatedScheduledJobsResponse | list[object],
    response_model_by_alias=True,
)
@router.get(
    "/v1/scheduler/jobs",
    response_model=PaginatedScheduledJobsResponse | list[object],
    response_model_by_alias=True,
)
async def list_jobs(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("scheduler:read"))],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50),
    tag: str | None = None,
) -> PaginatedScheduledJobsResponse | list[object]:
    store = scheduler_store(request)
    if store is None:
        return []
    jobs = await store.list(tenant_id=principal.tenant_id)
    filtered = jobs if not (tag and tag.strip()) else [job for job in jobs if tag in job.tags]
    page = paginate(filtered, offset=offset, limit=clamp_limit(limit))
    return PaginatedScheduledJobsResponse(
        items=[job_response(job) for job in page.items],
        total=page.total,
        offset=page.offset,
        limit=page.limit,
    )


@router.post(
    "/api/scheduler/jobs",
    response_model=ScheduledJobResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/v1/scheduler/jobs",
    response_model=ScheduledJobResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    request: Request,
    body: ScheduledJobRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("scheduler:write"))],
) -> ScheduledJobResponse:
    try:
        job = request_to_job(body, tenant_id=principal.tenant_id)
        job.validate()
        saved = await require_scheduler_store(request).save(job)
    except ValueError as error:
        raise invalid_request(error) from error
    return job_response(saved)


@router.get(
    "/api/scheduler/jobs/{job_id}",
    response_model=ScheduledJobResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/scheduler/jobs/{job_id}",
    response_model=ScheduledJobResponse,
    response_model_by_alias=True,
)
async def get_job(
    request: Request,
    job_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("scheduler:read"))],
) -> ScheduledJobResponse:
    store = scheduler_store(request)
    if store is None:
        raise HTTPException(status_code=404, detail={"error": "Scheduler not configured"})
    job = await store.find_by_id(tenant_id=principal.tenant_id, job_id=job_id)
    if job is None:
        raise job_not_found(job_id)
    return job_response(job)


@router.put(
    "/api/scheduler/jobs/{job_id}",
    response_model=ScheduledJobResponse,
    response_model_by_alias=True,
)
@router.put(
    "/v1/scheduler/jobs/{job_id}",
    response_model=ScheduledJobResponse,
    response_model_by_alias=True,
)
async def update_job(
    request: Request,
    job_id: str,
    body: ScheduledJobRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("scheduler:write"))],
) -> ScheduledJobResponse:
    try:
        job = request_to_job(body, tenant_id=principal.tenant_id, job_id=job_id)
        job.validate()
        updated = await require_scheduler_store(request).update(
            tenant_id=principal.tenant_id,
            job_id=job_id,
            job=job,
        )
    except ValueError as error:
        raise invalid_request(error) from error
    if updated is None:
        raise job_not_found(job_id)
    return job_response(updated)


@router.delete("/api/scheduler/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/v1/scheduler/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    request: Request,
    job_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("scheduler:write"))],
) -> Response:
    deleted = await require_scheduler_store(request).delete(
        tenant_id=principal.tenant_id,
        job_id=job_id,
    )
    if not deleted:
        raise job_not_found(job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/scheduler/jobs/{job_id}/trigger",
    response_model=SchedulerTriggerResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/scheduler/jobs/{job_id}/trigger",
    response_model=SchedulerTriggerResponse,
    response_model_by_alias=True,
)
async def trigger_job(
    request: Request,
    job_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("scheduler:write"))],
) -> SchedulerTriggerResponse:
    execution = await scheduler_worker(request).run_job(
        tenant_id=principal.tenant_id,
        job_id=job_id,
        lease_owner=f"http:{principal.user_id}",
    )
    return SchedulerTriggerResponse(
        result=execution.result or "",
        dryRun=False,
    )


@router.post(
    "/api/scheduler/jobs/{job_id}/dry-run",
    response_model=SchedulerTriggerResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/scheduler/jobs/{job_id}/dry-run",
    response_model=SchedulerTriggerResponse,
    response_model_by_alias=True,
)
async def dry_run_job(
    request: Request,
    job_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("scheduler:write"))],
) -> SchedulerTriggerResponse:
    execution = await scheduler_worker(request).run_job(
        tenant_id=principal.tenant_id,
        job_id=job_id,
        lease_owner=f"http:{principal.user_id}",
        dry_run=True,
    )
    return SchedulerTriggerResponse(result=execution.result or "", dryRun=True)


@router.get(
    "/api/scheduler/jobs/{job_id}/executions",
    response_model=PaginatedScheduledExecutionsResponse | list[object],
    response_model_by_alias=True,
)
@router.get(
    "/v1/scheduler/jobs/{job_id}/executions",
    response_model=PaginatedScheduledExecutionsResponse | list[object],
    response_model_by_alias=True,
)
async def get_executions(
    request: Request,
    job_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("scheduler:read"))],
    limit: int = Query(default=20),
    offset: int = Query(default=0, ge=0),
    page_limit: int = Query(default=50, alias="pageLimit"),
) -> PaginatedScheduledExecutionsResponse | list[object]:
    store = scheduler_store(request)
    histories = execution_store(request)
    if store is None or histories is None:
        return []
    job = await store.find_by_id(tenant_id=principal.tenant_id, job_id=job_id)
    if job is None:
        raise job_not_found(job_id)
    executions = await histories.find_by_job_id(
        tenant_id=principal.tenant_id,
        job_id=job_id,
        limit=max(1, min(limit, 100)),
    )
    page = paginate(executions, offset=offset, limit=clamp_limit(page_limit))
    return PaginatedScheduledExecutionsResponse(
        items=[execution_response(execution) for execution in page.items],
        total=page.total,
        offset=page.offset,
        limit=page.limit,
    )


async def require_existing_job(
    request: Request,
    tenant_id: str,
    job_id: str,
) -> ScheduledJobRecord:
    job = await require_scheduler_store(request).find_by_id(tenant_id=tenant_id, job_id=job_id)
    if job is None:
        raise job_not_found(job_id)
    return job


def scheduler_worker(request: Request) -> SchedulerWorker:
    container = get_container(request)
    settings = container.settings
    executor_accessor = getattr(container, "prompt_lab_scheduled_job_executor", None)
    executor = (
        cast(ScheduledJobExecutor | None, executor_accessor())
        if callable(executor_accessor)
        else None
    )
    return SchedulerWorker(
        job_store=require_scheduler_store(request),
        execution_store=require_execution_store(request),
        executor=executor,
        dead_letter_store=dead_letter_store(request),
        config=SchedulerWorkerConfig(
            default_execution_timeout_ms=settings.scheduler_default_execution_timeout_ms,
            lease_buffer_ms=settings.scheduler_lease_buffer_ms,
            minimum_lease_ms=settings.scheduler_minimum_lease_ms,
            retry_delay_ms=settings.scheduler_retry_delay_ms,
            max_executions_per_job=settings.scheduler_max_executions_per_job,
        ),
    )


def request_to_job(
    body: ScheduledJobRequest,
    *,
    tenant_id: str,
    job_id: str | None = None,
) -> ScheduledJobRecord:
    job_type = parse_job_type(body.job_type)
    now = datetime.now(UTC)
    return ScheduledJobRecord(
        id=job_id or ScheduledJobRecord().id,
        tenant_id=tenant_id,
        name=body.name,
        description=body.description,
        cron_expression=body.cron_expression,
        timezone=body.timezone,
        job_type=job_type,
        mcp_server_name=body.mcp_server_name,
        tool_name=body.tool_name,
        tool_arguments=body.tool_arguments,
        agent_prompt=body.agent_prompt,
        persona_id=body.persona_id,
        agent_system_prompt=body.agent_system_prompt,
        agent_model=body.agent_model,
        agent_max_tool_calls=body.agent_max_tool_calls,
        tags=frozenset(body.tags),
        slack_channel_id=body.slack_channel_id,
        teams_webhook_url=body.teams_webhook_url,
        retry_on_failure=body.retry_on_failure,
        max_retry_count=body.max_retry_count,
        execution_timeout_ms=body.execution_timeout_ms,
        enabled=body.enabled,
        created_at=now,
        updated_at=now,
    )


def invalid_request(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request")


def job_not_found(job_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Scheduled job not found: {job_id}",
    )


def epoch_millis(value: datetime | None) -> int | None:
    return int(value.timestamp() * 1000) if value is not None else None


def job_response(job: ScheduledJobRecord) -> ScheduledJobResponse:
    return ScheduledJobResponse(
        id=job.id,
        name=job.name,
        description=job.description,
        cronExpression=job.cron_expression,
        timezone=job.timezone,
        jobType=job.job_type.value,
        mcpServerName=job.mcp_server_name,
        toolName=job.tool_name,
        toolArguments=job.tool_arguments,
        agentPrompt=job.agent_prompt,
        personaId=job.persona_id,
        agentSystemPrompt=job.agent_system_prompt,
        agentModel=job.agent_model,
        agentMaxToolCalls=job.agent_max_tool_calls,
        tags=set(job.tags),
        slackChannelId=job.slack_channel_id,
        teamsWebhookUrl=job.teams_webhook_url,
        retryOnFailure=job.retry_on_failure,
        maxRetryCount=job.max_retry_count,
        executionTimeoutMs=job.execution_timeout_ms,
        enabled=job.enabled,
        lastRunAt=epoch_millis(job.last_run_at),
        lastStatus=job.last_status.value if job.last_status is not None else None,
        lastResult=job.last_result,
        lastResultPreview=scheduler_result_preview(job.last_result),
        lastFailureReason=scheduler_failure_reason(job.last_result),
        createdAt=cast(int, epoch_millis(job.created_at)),
        updatedAt=cast(int, epoch_millis(job.updated_at)),
    )


def execution_response(execution: ScheduledJobExecutionRecord) -> ScheduledJobExecutionResponse:
    return ScheduledJobExecutionResponse(
        id=execution.id,
        jobId=execution.job_id,
        jobName=execution.job_name,
        status=execution.status.value,
        result=execution.result,
        resultPreview=scheduler_result_preview(execution.result),
        failureReason=scheduler_failure_reason(execution.result),
        durationMs=execution.duration_ms,
        dryRun=execution.dry_run,
        startedAt=cast(int, epoch_millis(execution.started_at)),
        completedAt=epoch_millis(execution.completed_at),
    )


class Page[T]:
    def __init__(self, items: list[T], total: int, offset: int, limit: int) -> None:
        self.items = items
        self.total = total
        self.offset = offset
        self.limit = limit


def clamp_limit(raw: int) -> int:
    return max(1, min(raw, 200))


def paginate[T](items: list[T], *, offset: int, limit: int) -> Page[T]:
    safe_offset = max(offset, 0)
    total = len(items)
    end = min(safe_offset + limit, total)
    page_items = [] if safe_offset >= total else items[safe_offset:end]
    return Page(items=page_items, total=total, offset=safe_offset, limit=limit)
