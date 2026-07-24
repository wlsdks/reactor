from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Protocol, cast

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)

from reactor.api.auth import require_permission
from reactor.api.schemas.prompt_lab import (
    AnalyzeFeedbackRequest,
    AutoOptimizeRequest,
    CreateExperimentRequest,
    EvaluationConfigRequest,
    ExperimentResponse,
    ExperimentStatusResponse,
    FeedbackAnalysisResponse,
    PromptLabActivationResponse,
    PromptLabRunAcceptedResponse,
    RecommendationResponse,
    ReportResponse,
    TestQueryRequest,
    TrialResponse,
    VersionSummaryResponse,
    WeaknessResponse,
)
from reactor.auth.rbac import AuthPrincipal, current_actor
from reactor.core.container import AppContainer
from reactor.persistence.prompt_store import PromptVersionRecord, legacy_version_number
from reactor.prompt_lab.models import (
    EvaluationConfig,
    FeedbackAnalysis,
    PromptLabExperimentRecord,
    PromptLabExperimentStatus,
    PromptLabReportRecord,
    PromptLabTrialRecord,
    PromptWeakness,
    TestQuery,
    sanitize_prompt_lab_error,
)

router = APIRouter(tags=["prompt-lab"])


class PromptLabStore(Protocol):
    async def save_experiment(
        self, record: PromptLabExperimentRecord
    ) -> PromptLabExperimentRecord: ...

    async def list_experiments(
        self,
        *,
        tenant_id: str,
        status: PromptLabExperimentStatus | None = None,
        template_id: str | None = None,
    ) -> list[PromptLabExperimentRecord]: ...

    async def find_experiment(
        self, *, tenant_id: str, experiment_id: str
    ) -> PromptLabExperimentRecord | None: ...

    async def update_status(
        self,
        *,
        tenant_id: str,
        experiment_id: str,
        status: PromptLabExperimentStatus,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> PromptLabExperimentRecord | None: ...

    async def delete_experiment(self, *, tenant_id: str, experiment_id: str) -> None: ...

    async def list_trials(
        self, *, tenant_id: str, experiment_id: str
    ) -> list[PromptLabTrialRecord]: ...

    async def save_trial(self, record: PromptLabTrialRecord) -> PromptLabTrialRecord: ...

    async def find_report(
        self, *, tenant_id: str, experiment_id: str
    ) -> PromptLabReportRecord | None: ...

    async def save_report(self, record: PromptLabReportRecord) -> PromptLabReportRecord: ...


class PromptVersionActivator(Protocol):
    async def activate_legacy_version(
        self,
        *,
        tenant_id: str,
        template_id: str,
        version_id: str,
    ) -> PromptVersionRecord | None: ...


class PromptLabExecutorService(Protocol):
    async def execute(self, *, tenant_id: str, experiment_id: str, user_id: str) -> object: ...


class PromptLabAutoOptimizerService(Protocol):
    async def analyze(
        self,
        *,
        tenant_id: str,
        template_id: str,
        max_samples: int = 50,
    ) -> FeedbackAnalysis: ...

    async def run_auto_pipeline(
        self,
        *,
        tenant_id: str,
        template_id: str,
        user_id: str,
        candidate_count: int | None = None,
        judge_model: str | None = None,
    ) -> PromptLabExperimentRecord: ...


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def require_prompt_lab_store(request: Request) -> PromptLabStore:
    accessor = getattr(get_container(request), "prompt_lab_store", None)
    store = accessor() if callable(accessor) else None
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="prompt lab persistence is not configured",
        )
    return cast(PromptLabStore, store)


def require_prompt_version_activator(request: Request) -> PromptVersionActivator:
    store = get_container(request).prompt_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="prompt persistence is not configured",
        )
    return cast(PromptVersionActivator, store)


def prompt_lab_executor(request: Request) -> PromptLabExecutorService | None:
    accessor = getattr(get_container(request), "prompt_lab_executor", None)
    value = accessor() if callable(accessor) else None
    return cast(PromptLabExecutorService | None, value)


def require_prompt_lab_auto_optimizer(request: Request) -> PromptLabAutoOptimizerService:
    accessor = getattr(get_container(request), "prompt_lab_auto_optimizer", None)
    optimizer = accessor() if callable(accessor) else None
    if optimizer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="prompt lab auto optimizer is not configured",
        )
    return cast(PromptLabAutoOptimizerService, optimizer)


@router.post(
    "/api/prompt-lab/experiments",
    response_model=ExperimentResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_experiment(
    request: Request,
    body: CreateExperimentRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:write"))],
) -> ExperimentResponse:
    record = PromptLabExperimentRecord(
        tenant_id=principal.tenant_id,
        name=body.name.strip(),
        description=body.description.strip(),
        template_id=body.templateId.strip(),
        baseline_version_id=body.baselineVersionId.strip(),
        candidate_version_ids=[item.strip() for item in body.candidateVersionIds],
        test_queries=[test_query_from_request(item) for item in body.testQueries],
        evaluation_config=evaluation_config_from_request(body.evaluationConfig),
        model=body.model.strip() if body.model is not None else None,
        judge_model=body.judgeModel.strip() if body.judgeModel is not None else None,
        temperature=body.temperature if body.temperature is not None else 0.3,
        repetitions=body.repetitions if body.repetitions is not None else 1,
        created_by=current_actor(principal),
        created_at=datetime.now(UTC),
    )
    try:
        saved = await require_prompt_lab_store(request).save_experiment(record)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return experiment_response(saved)


@router.get(
    "/api/prompt-lab/experiments",
    response_model=list[ExperimentResponse],
    response_model_by_alias=True,
)
async def list_experiments(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:read"))],
    status_filter: str | None = Query(default=None, alias="status"),
    templateId: str | None = None,
) -> list[ExperimentResponse]:
    records = await require_prompt_lab_store(request).list_experiments(
        tenant_id=principal.tenant_id,
        status=parse_status(status_filter) if status_filter is not None else None,
        template_id=templateId,
    )
    return [experiment_response(record) for record in records]


@router.get(
    "/api/prompt-lab/experiments/{experiment_id}",
    response_model=ExperimentResponse,
    response_model_by_alias=True,
)
async def get_experiment(
    request: Request,
    experiment_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:read"))],
) -> ExperimentResponse:
    return experiment_response(await require_experiment(request, principal, experiment_id))


@router.post(
    "/api/prompt-lab/experiments/{experiment_id}/run",
    response_model=PromptLabRunAcceptedResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_experiment(
    request: Request,
    background_tasks: BackgroundTasks,
    experiment_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:write"))],
) -> PromptLabRunAcceptedResponse:
    experiment = await require_experiment(request, principal, experiment_id)
    if experiment.status != PromptLabExperimentStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Experiment must be PENDING to run, current: {experiment.status.value}",
        )
    await require_prompt_lab_store(request).update_status(
        tenant_id=principal.tenant_id,
        experiment_id=experiment_id,
        status=PromptLabExperimentStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    executor = prompt_lab_executor(request)
    if executor is not None:
        background_tasks.add_task(
            executor.execute,
            tenant_id=principal.tenant_id,
            experiment_id=experiment_id,
            user_id=principal.user_id,
        )
    return PromptLabRunAcceptedResponse(status="RUNNING", experimentId=experiment_id)


@router.post(
    "/api/prompt-lab/experiments/{experiment_id}/cancel",
    response_model=ExperimentResponse,
    response_model_by_alias=True,
)
async def cancel_experiment(
    request: Request,
    experiment_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:write"))],
) -> ExperimentResponse:
    experiment = await require_experiment(request, principal, experiment_id)
    if experiment.status != PromptLabExperimentStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only RUNNING experiments can be cancelled",
        )
    cancelled = await require_prompt_lab_store(request).update_status(
        tenant_id=principal.tenant_id,
        experiment_id=experiment_id,
        status=PromptLabExperimentStatus.CANCELLED,
        completed_at=datetime.now(UTC),
    )
    if cancelled is None:
        raise prompt_lab_not_found(experiment_id)
    return experiment_response(cancelled)


@router.get(
    "/api/prompt-lab/experiments/{experiment_id}/status",
    response_model=ExperimentStatusResponse,
    response_model_by_alias=True,
)
async def get_experiment_status(
    request: Request,
    experiment_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:read"))],
) -> ExperimentStatusResponse:
    experiment = await require_experiment(request, principal, experiment_id)
    return ExperimentStatusResponse(
        experimentId=experiment.id,
        status=experiment.status.value,
        startedAt=epoch_millis(experiment.started_at),
        completedAt=epoch_millis(experiment.completed_at),
        errorMessage=sanitize_prompt_lab_error(experiment.error_message),
    )


@router.get(
    "/api/prompt-lab/experiments/{experiment_id}/trials",
    response_model=list[TrialResponse],
    response_model_by_alias=True,
)
async def get_trials(
    request: Request,
    experiment_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:read"))],
) -> list[TrialResponse]:
    trials = await require_prompt_lab_store(request).list_trials(
        tenant_id=principal.tenant_id,
        experiment_id=experiment_id,
    )
    return [trial_response(record) for record in trials]


@router.get(
    "/api/prompt-lab/experiments/{experiment_id}/report",
    response_model=ReportResponse,
    response_model_by_alias=True,
)
async def get_report(
    request: Request,
    experiment_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:read"))],
) -> ReportResponse:
    report = await require_prompt_lab_store(request).find_report(
        tenant_id=principal.tenant_id,
        experiment_id=experiment_id,
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment report not found: {experiment_id}",
        )
    return report_response(report)


@router.delete(
    "/api/prompt-lab/experiments/{experiment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_experiment(
    request: Request,
    experiment_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:write"))],
) -> Response:
    await require_prompt_lab_store(request).delete_experiment(
        tenant_id=principal.tenant_id,
        experiment_id=experiment_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/prompt-lab/auto-optimize",
    response_model=PromptLabRunAcceptedResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def auto_optimize(
    request: Request,
    background_tasks: BackgroundTasks,
    body: AutoOptimizeRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:write"))],
) -> PromptLabRunAcceptedResponse:
    optimizer = require_prompt_lab_auto_optimizer(request)
    job_id = f"auto-{body.templateId}"
    background_tasks.add_task(
        optimizer.run_auto_pipeline,
        tenant_id=principal.tenant_id,
        template_id=body.templateId,
        user_id=principal.user_id,
        candidate_count=body.candidateCount,
        judge_model=body.judgeModel,
    )
    return PromptLabRunAcceptedResponse(
        status="STARTED",
        templateId=body.templateId,
        jobId=job_id,
    )


@router.post(
    "/api/prompt-lab/analyze",
    response_model=FeedbackAnalysisResponse,
    response_model_by_alias=True,
)
async def analyze_feedback(
    request: Request,
    body: AnalyzeFeedbackRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:write"))],
) -> FeedbackAnalysisResponse:
    analysis = await require_prompt_lab_auto_optimizer(request).analyze(
        tenant_id=principal.tenant_id,
        template_id=body.templateId,
        max_samples=body.maxSamples or 50,
    )
    return feedback_analysis_response(analysis)


@router.post(
    "/api/prompt-lab/experiments/{experiment_id}/activate",
    response_model=PromptLabActivationResponse,
    response_model_by_alias=True,
)
async def activate_recommended(
    request: Request,
    experiment_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("prompt:write"))],
) -> PromptLabActivationResponse:
    experiment = await require_experiment(request, principal, experiment_id)
    report = await require_prompt_lab_store(request).find_report(
        tenant_id=principal.tenant_id,
        experiment_id=experiment_id,
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No report available for this experiment",
        )
    activated = await require_prompt_version_activator(request).activate_legacy_version(
        tenant_id=principal.tenant_id,
        template_id=experiment.template_id,
        version_id=report.recommendation.best_version_id,
    )
    if activated is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to activate version: {report.recommendation.best_version_id}",
        )
    return PromptLabActivationResponse(
        activated=True,
        templateId=experiment.template_id,
        versionId=activated.id,
        versionNumber=legacy_version_number(activated),
    )


async def require_experiment(
    request: Request,
    principal: AuthPrincipal,
    experiment_id: str,
) -> PromptLabExperimentRecord:
    experiment = await require_prompt_lab_store(request).find_experiment(
        tenant_id=principal.tenant_id,
        experiment_id=experiment_id,
    )
    if experiment is None:
        raise prompt_lab_not_found(experiment_id)
    return experiment


def prompt_lab_not_found(experiment_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Experiment not found: {experiment_id}",
    )


def parse_status(value: str) -> PromptLabExperimentStatus:
    try:
        return PromptLabExperimentStatus(value.strip().upper())
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown experiment status: {value}",
        ) from error


def test_query_from_request(body: TestQueryRequest) -> TestQuery:
    return TestQuery(
        query=body.query.strip(),
        intent=body.intent.strip() if body.intent is not None else None,
        domain=body.domain.strip() if body.domain is not None else None,
        expected_behavior=body.expectedBehavior.strip()
        if body.expectedBehavior is not None
        else None,
        tags=[tag.strip() for tag in body.tags],
    )


def evaluation_config_from_request(body: EvaluationConfigRequest | None) -> EvaluationConfig:
    if body is None:
        return EvaluationConfig()
    return EvaluationConfig(
        structural_enabled=body.structuralEnabled,
        rules_enabled=body.rulesEnabled,
        llm_judge_enabled=body.llmJudgeEnabled,
        llm_judge_budget_tokens=body.llmJudgeBudgetTokens,
        custom_rubric=body.customRubric,
    )


def experiment_response(record: PromptLabExperimentRecord) -> ExperimentResponse:
    return ExperimentResponse(
        id=record.id,
        name=record.name,
        description=record.description,
        templateId=record.template_id,
        baselineVersionId=record.baseline_version_id,
        candidateVersionIds=record.candidate_version_ids,
        status=record.status.value,
        autoGenerated=record.auto_generated,
        createdBy=record.created_by,
        createdAt=epoch_millis(record.created_at) or 0,
        startedAt=epoch_millis(record.started_at),
        completedAt=epoch_millis(record.completed_at),
    )


def trial_response(record: PromptLabTrialRecord) -> TrialResponse:
    scores = [item.score for item in record.evaluations]
    score = sum(scores) / len(scores) if scores else 0.0
    return TrialResponse(
        id=record.id,
        promptVersionId=record.prompt_version_id,
        promptVersionNumber=record.prompt_version_number,
        query=record.test_query.query,
        response=record.response,
        success=record.success,
        score=score,
        durationMs=record.duration_ms,
        toolsUsed=record.tools_used,
        passed=all(item.passed for item in record.evaluations),
        executedAt=epoch_millis(record.executed_at) or 0,
    )


def report_response(record: PromptLabReportRecord) -> ReportResponse:
    return ReportResponse(
        experimentId=record.experiment_id,
        experimentName=record.experiment_name,
        generatedAt=epoch_millis(record.generated_at) or 0,
        totalTrials=record.total_trials,
        versionSummaries=[
            VersionSummaryResponse(
                versionId=item.version_id,
                versionNumber=item.version_number,
                isBaseline=item.is_baseline,
                totalTrials=item.total_trials,
                passCount=item.pass_count,
                passRate=item.pass_rate,
                avgScore=item.avg_score,
                avgDurationMs=item.avg_duration_ms,
                totalTokens=item.total_tokens,
                errorRate=item.error_rate,
                tierBreakdown=item.tier_breakdown,
                toolUsageFrequency=item.tool_usage_frequency,
            )
            for item in record.version_summaries
        ],
        recommendation=RecommendationResponse(
            bestVersionId=record.recommendation.best_version_id,
            bestVersionNumber=record.recommendation.best_version_number,
            confidence=record.recommendation.confidence.value,
            reasoning=record.recommendation.reasoning,
            improvements=record.recommendation.improvements,
            warnings=record.recommendation.warnings,
        ),
    )


def feedback_analysis_response(record: FeedbackAnalysis) -> FeedbackAnalysisResponse:
    return FeedbackAnalysisResponse(
        totalFeedback=record.total_feedback,
        negativeCount=record.negative_count,
        weaknesses=[weakness_response(item) for item in record.weaknesses],
        sampleQueries=[test_query_payload(item) for item in record.sample_queries],
        analyzedAt=epoch_millis(record.analyzed_at) or 0,
    )


def weakness_response(record: PromptWeakness) -> WeaknessResponse:
    return WeaknessResponse(
        category=record.category,
        description=record.description,
        frequency=record.frequency,
        exampleQueries=record.example_queries,
    )


def test_query_payload(record: TestQuery) -> dict[str, object]:
    payload: dict[str, object] = {
        "query": record.query,
        "tags": record.tags,
    }
    if record.intent is not None:
        payload["intent"] = record.intent
    if record.domain is not None:
        payload["domain"] = record.domain
    if record.expected_behavior is not None:
        payload["expectedBehavior"] = record.expected_behavior
    return payload


def epoch_millis(value: datetime | None) -> int | None:
    if value is None:
        return None
    return int(value.timestamp() * 1000)
