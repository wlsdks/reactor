from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.persistence.models import PromptLabExperiment, PromptLabReport, PromptLabTrial
from reactor.prompt_lab.models import (
    EvaluationConfig,
    EvaluationResult,
    EvaluationTier,
    PromptLabExperimentRecord,
    PromptLabExperimentStatus,
    PromptLabReportRecord,
    PromptLabTrialRecord,
    Recommendation,
    RecommendationConfidence,
    TestQuery,
    TokenUsageSummary,
    VersionSummary,
)


class SqlAlchemyPromptLabStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_experiment(self, record: PromptLabExperimentRecord) -> PromptLabExperimentRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    insert(PromptLabExperiment)
                    .values(experiment_values(record))
                    .on_conflict_do_update(
                        index_elements=[PromptLabExperiment.id],
                        set_=experiment_values(record, include_id=False),
                    )
                    .returning(PromptLabExperiment)
                )
                if row is None:
                    raise RuntimeError("prompt lab experiment upsert did not return a row")
                return experiment_from_model(row)

    async def list_experiments(
        self,
        *,
        tenant_id: str,
        status: PromptLabExperimentStatus | None = None,
        template_id: str | None = None,
    ) -> list[PromptLabExperimentRecord]:
        conditions = [PromptLabExperiment.tenant_id == tenant_id]
        if status is not None:
            conditions.append(PromptLabExperiment.status == status.value)
        if template_id is not None and template_id.strip():
            conditions.append(PromptLabExperiment.template_id == template_id.strip())
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(PromptLabExperiment)
                .where(*conditions)
                .order_by(PromptLabExperiment.created_at.desc())
            )
            return [experiment_from_model(row) for row in rows]

    async def find_experiment(
        self, *, tenant_id: str, experiment_id: str
    ) -> PromptLabExperimentRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(PromptLabExperiment).where(
                    PromptLabExperiment.tenant_id == tenant_id,
                    PromptLabExperiment.id == experiment_id,
                )
            )
            return experiment_from_model(row) if row is not None else None

    async def update_status(
        self,
        *,
        tenant_id: str,
        experiment_id: str,
        status: PromptLabExperimentStatus,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> PromptLabExperimentRecord | None:
        values: dict[str, object | None] = {"status": status.value}
        if started_at is not None:
            values["started_at"] = started_at
        if completed_at is not None:
            values["completed_at"] = completed_at
        if error_message is not None:
            values["error_message"] = error_message
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    update(PromptLabExperiment)
                    .where(
                        PromptLabExperiment.tenant_id == tenant_id,
                        PromptLabExperiment.id == experiment_id,
                    )
                    .values(**values)
                    .returning(PromptLabExperiment)
                )
                return experiment_from_model(row) if row is not None else None

    async def delete_experiment(self, *, tenant_id: str, experiment_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    delete(PromptLabExperiment).where(
                        PromptLabExperiment.tenant_id == tenant_id,
                        PromptLabExperiment.id == experiment_id,
                    )
                )

    async def list_trials(
        self, *, tenant_id: str, experiment_id: str
    ) -> list[PromptLabTrialRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(PromptLabTrial)
                .where(
                    PromptLabTrial.tenant_id == tenant_id,
                    PromptLabTrial.experiment_id == experiment_id,
                )
                .order_by(PromptLabTrial.executed_at.asc())
            )
            return [trial_from_model(row) for row in rows]

    async def save_trial(self, record: PromptLabTrialRecord) -> PromptLabTrialRecord:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    insert(PromptLabTrial)
                    .values(trial_values(record))
                    .on_conflict_do_update(
                        index_elements=[PromptLabTrial.id],
                        set_=trial_values(record, include_id=False),
                    )
                    .returning(PromptLabTrial)
                )
                if row is None:
                    raise RuntimeError("prompt lab trial upsert did not return a row")
                return trial_from_model(row)

    async def find_report(
        self, *, tenant_id: str, experiment_id: str
    ) -> PromptLabReportRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(PromptLabReport).where(
                    PromptLabReport.tenant_id == tenant_id,
                    PromptLabReport.experiment_id == experiment_id,
                )
            )
            return report_from_model(row) if row is not None else None

    async def save_report(self, record: PromptLabReportRecord) -> PromptLabReportRecord:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    insert(PromptLabReport)
                    .values(report_values(record))
                    .on_conflict_do_update(
                        index_elements=[PromptLabReport.experiment_id],
                        set_=report_values(record, include_experiment_id=False),
                    )
                    .returning(PromptLabReport)
                )
                if row is None:
                    raise RuntimeError("prompt lab report upsert did not return a row")
                return report_from_model(row)


def experiment_values(
    record: PromptLabExperimentRecord, *, include_id: bool = True
) -> dict[str, object | None]:
    values: dict[str, object | None] = {
        "tenant_id": record.tenant_id,
        "name": record.name,
        "description": record.description,
        "template_id": record.template_id,
        "baseline_version_id": record.baseline_version_id,
        "candidate_version_ids": list(record.candidate_version_ids),
        "test_queries": [test_query_payload(query) for query in record.test_queries],
        "evaluation_config": evaluation_config_payload(record.evaluation_config),
        "model": record.model,
        "judge_model": record.judge_model,
        "temperature": record.temperature,
        "repetitions": record.repetitions,
        "auto_generated": record.auto_generated,
        "status": record.status.value,
        "created_by": record.created_by,
        "created_at": record.created_at,
        "started_at": record.started_at,
        "completed_at": record.completed_at,
        "error_message": record.error_message,
    }
    if include_id:
        values["id"] = record.id
    return values


def trial_values(
    record: PromptLabTrialRecord, *, include_id: bool = True
) -> dict[str, object | None]:
    values: dict[str, object | None] = {
        "tenant_id": record.tenant_id,
        "experiment_id": record.experiment_id,
        "prompt_version_id": record.prompt_version_id,
        "prompt_version_number": record.prompt_version_number,
        "test_query": test_query_payload(record.test_query),
        "repetition_index": record.repetition_index,
        "response": record.response,
        "success": record.success,
        "error_message": record.error_message,
        "tools_used": list(record.tools_used),
        "token_usage": token_usage_payload(record.token_usage),
        "duration_ms": record.duration_ms,
        "evaluations": [evaluation_result_payload(item) for item in record.evaluations],
        "executed_at": record.executed_at,
    }
    if include_id:
        values["id"] = record.id
    return values


def report_values(
    record: PromptLabReportRecord, *, include_experiment_id: bool = True
) -> dict[str, object]:
    values: dict[str, object] = {
        "tenant_id": record.tenant_id,
        "experiment_name": record.experiment_name,
        "generated_at": record.generated_at,
        "total_trials": record.total_trials,
        "version_summaries": [version_summary_payload(item) for item in record.version_summaries],
        "recommendation": recommendation_payload(record.recommendation),
    }
    if include_experiment_id:
        values["experiment_id"] = record.experiment_id
    return values


def experiment_from_model(row: PromptLabExperiment) -> PromptLabExperimentRecord:
    return PromptLabExperimentRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        description=row.description,
        template_id=row.template_id,
        baseline_version_id=row.baseline_version_id,
        candidate_version_ids=list(row.candidate_version_ids),
        test_queries=[test_query_from_payload(item) for item in row.test_queries],
        evaluation_config=evaluation_config_from_payload(row.evaluation_config),
        model=row.model,
        judge_model=row.judge_model,
        temperature=row.temperature,
        repetitions=row.repetitions,
        auto_generated=row.auto_generated,
        status=PromptLabExperimentStatus(row.status),
        created_by=row.created_by,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        error_message=row.error_message,
    )


def trial_from_model(row: PromptLabTrial) -> PromptLabTrialRecord:
    return PromptLabTrialRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        experiment_id=row.experiment_id,
        prompt_version_id=row.prompt_version_id,
        prompt_version_number=row.prompt_version_number,
        test_query=test_query_from_payload(row.test_query),
        repetition_index=row.repetition_index,
        response=row.response,
        success=row.success,
        error_message=row.error_message,
        tools_used=list(row.tools_used),
        token_usage=token_usage_from_payload(row.token_usage),
        duration_ms=row.duration_ms,
        evaluations=[evaluation_result_from_payload(item) for item in row.evaluations],
        executed_at=row.executed_at,
    )


def report_from_model(row: PromptLabReport) -> PromptLabReportRecord:
    return PromptLabReportRecord(
        experiment_id=row.experiment_id,
        tenant_id=row.tenant_id,
        experiment_name=row.experiment_name,
        generated_at=row.generated_at,
        total_trials=row.total_trials,
        version_summaries=[version_summary_from_payload(item) for item in row.version_summaries],
        recommendation=recommendation_from_payload(row.recommendation),
    )


def test_query_payload(query: TestQuery) -> dict[str, object | None]:
    return {
        "query": query.query,
        "intent": query.intent,
        "domain": query.domain,
        "expectedBehavior": query.expected_behavior,
        "tags": list(query.tags),
    }


def test_query_from_payload(payload: dict[str, Any]) -> TestQuery:
    return TestQuery(
        query=str(payload.get("query") or ""),
        intent=optional_string(payload.get("intent")),
        domain=optional_string(payload.get("domain")),
        expected_behavior=optional_string(payload.get("expectedBehavior")),
        tags=[str(item) for item in payload.get("tags", [])],
    )


def evaluation_config_payload(config: EvaluationConfig) -> dict[str, object | None]:
    return {
        "structuralEnabled": config.structural_enabled,
        "rulesEnabled": config.rules_enabled,
        "llmJudgeEnabled": config.llm_judge_enabled,
        "llmJudgeBudgetTokens": config.llm_judge_budget_tokens,
        "customRubric": config.custom_rubric,
    }


def evaluation_config_from_payload(payload: dict[str, Any]) -> EvaluationConfig:
    return EvaluationConfig(
        structural_enabled=bool(payload.get("structuralEnabled", True)),
        rules_enabled=bool(payload.get("rulesEnabled", True)),
        llm_judge_enabled=bool(payload.get("llmJudgeEnabled", True)),
        llm_judge_budget_tokens=int(payload.get("llmJudgeBudgetTokens", 100_000)),
        custom_rubric=optional_string(payload.get("customRubric")),
    )


def token_usage_payload(usage: TokenUsageSummary | None) -> dict[str, int] | None:
    if usage is None:
        return None
    return {
        "promptTokens": usage.prompt_tokens,
        "completionTokens": usage.completion_tokens,
        "totalTokens": usage.total_tokens,
    }


def token_usage_from_payload(payload: dict[str, Any] | None) -> TokenUsageSummary | None:
    if payload is None:
        return None
    return TokenUsageSummary(
        prompt_tokens=int(payload.get("promptTokens", 0)),
        completion_tokens=int(payload.get("completionTokens", 0)),
        total_tokens=int(payload.get("totalTokens", 0)),
    )


def evaluation_result_payload(result: EvaluationResult) -> dict[str, object | None]:
    return {
        "tier": result.tier.value,
        "passed": result.passed,
        "score": result.score,
        "reason": result.reason,
        "evaluatorName": result.evaluator_name or result.tier.value,
    }


def evaluation_result_from_payload(payload: dict[str, Any]) -> EvaluationResult:
    tier = EvaluationTier(str(payload.get("tier") or EvaluationTier.RULES.value))
    return EvaluationResult(
        tier=tier,
        passed=bool(payload.get("passed", False)),
        score=float(payload.get("score", 0)),
        reason=str(payload.get("reason") or ""),
        evaluator_name=optional_string(payload.get("evaluatorName")),
    )


def version_summary_payload(summary: VersionSummary) -> dict[str, object]:
    return {
        "versionId": summary.version_id,
        "versionNumber": summary.version_number,
        "isBaseline": summary.is_baseline,
        "totalTrials": summary.total_trials,
        "passCount": summary.pass_count,
        "passRate": summary.pass_rate,
        "avgScore": summary.avg_score,
        "avgDurationMs": summary.avg_duration_ms,
        "totalTokens": summary.total_tokens,
        "tierBreakdown": summary.tier_breakdown,
        "toolUsageFrequency": summary.tool_usage_frequency,
        "errorRate": summary.error_rate,
    }


def version_summary_from_payload(payload: dict[str, Any]) -> VersionSummary:
    return VersionSummary(
        version_id=str(payload.get("versionId") or ""),
        version_number=int(payload.get("versionNumber", 0)),
        is_baseline=bool(payload.get("isBaseline", False)),
        total_trials=int(payload.get("totalTrials", 0)),
        pass_count=int(payload.get("passCount", 0)),
        pass_rate=float(payload.get("passRate", 0)),
        avg_score=float(payload.get("avgScore", 0)),
        avg_duration_ms=float(payload.get("avgDurationMs", 0)),
        total_tokens=int(payload.get("totalTokens", 0)),
        tier_breakdown=cast(dict[str, dict[str, float | int]], payload.get("tierBreakdown", {})),
        tool_usage_frequency=cast(dict[str, int], payload.get("toolUsageFrequency", {})),
        error_rate=float(payload.get("errorRate", 0)),
    )


def recommendation_payload(recommendation: Recommendation) -> dict[str, object]:
    return {
        "bestVersionId": recommendation.best_version_id,
        "bestVersionNumber": recommendation.best_version_number,
        "confidence": recommendation.confidence.value,
        "reasoning": recommendation.reasoning,
        "improvements": list(recommendation.improvements),
        "warnings": list(recommendation.warnings),
    }


def recommendation_from_payload(payload: dict[str, Any]) -> Recommendation:
    return Recommendation(
        best_version_id=str(payload.get("bestVersionId") or ""),
        best_version_number=int(payload.get("bestVersionNumber", 0)),
        confidence=RecommendationConfidence(str(payload.get("confidence") or "LOW")),
        reasoning=str(payload.get("reasoning") or ""),
        improvements=[str(item) for item in payload.get("improvements", [])],
        warnings=[str(item) for item in payload.get("warnings", [])],
    )


def optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
