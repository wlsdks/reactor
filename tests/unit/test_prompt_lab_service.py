from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from langchain_core.messages import BaseMessage

from reactor.agents.runner import RunResult
from reactor.persistence.prompt_store import (
    LEGACY_PROMPT_STATUS_ACTIVE,
    LEGACY_PROMPT_STATUS_KEY,
    PromptTemplateRecord,
    PromptVersionRecord,
)
from reactor.prompt_lab.models import (
    EvaluationResult,
    EvaluationTier,
    PromptLabExperimentRecord,
    PromptLabExperimentStatus,
    PromptLabReportRecord,
    PromptLabTrialRecord,
)
from reactor.prompt_lab.models import (
    TestQuery as PromptLabTestQuery,
)
from reactor.prompt_lab.service import (
    LangChainPromptLabLlmJudge,
    PromptLabAutoOptimizer,
    PromptLabExecutor,
    PromptLabLlmJudgeOutput,
    PromptLabScheduledJobExecutor,
    PromptLabScheduler,
    token_usage_from_run_result,
)
from reactor.providers.usage import TokenUsage
from reactor.scheduler.service import ScheduledJobRecord, ScheduledJobType
from reactor.slack.feedback import Feedback, FeedbackRating


async def test_prompt_lab_executor_runs_langgraph_trials_and_saves_report() -> None:
    experiment_store = RecordingPromptLabStore()
    prompt_store = RecordingPromptStore()
    run_service = RecordingRunService()
    experiment = PromptLabExperimentRecord(
        id="exp-1",
        tenant_id="tenant_1",
        name="Support experiment",
        template_id="tmpl-1",
        baseline_version_id="v-1",
        candidate_version_ids=["v-2"],
        test_queries=[
            PromptLabTestQuery(
                query="How do I reset MFA?",
                expected_behavior="policy citation",
            )
        ],
        created_by="admin_1",
        created_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )
    experiment_store.experiments[experiment.id] = experiment

    executor = PromptLabExecutor(
        experiment_store=experiment_store,
        prompt_store=prompt_store,
        run_service=run_service,
    )

    result = await executor.execute(
        tenant_id="tenant_1",
        experiment_id="exp-1",
        user_id="admin_1",
    )

    assert result.status == PromptLabExperimentStatus.COMPLETED
    assert result.trial_count == 2
    assert experiment_store.experiments["exp-1"].status == PromptLabExperimentStatus.COMPLETED
    assert len(experiment_store.trials) == 2
    assert run_service.calls[0].metadata["systemPrompt"] == "Baseline policy citation prompt"
    assert run_service.calls[1].metadata["promptVersionId"] == "v-2"
    assert experiment_store.report is not None
    assert experiment_store.report.recommendation.best_version_id in {"v-1", "v-2"}


def test_prompt_lab_token_usage_rejects_mismatched_total_tokens() -> None:
    result = FakeRunResultWithTokenUsage(
        token_usage=FakeRunTokenUsage(
            input_tokens=5,
            output_tokens=7,
            total_tokens=99,
        )
    )

    assert token_usage_from_run_result(result) is None


def test_prompt_lab_token_usage_rejects_negative_token_counts() -> None:
    result = FakeRunResultWithTokenUsage(
        token_usage=FakeRunTokenUsage(
            input_tokens=-1,
            output_tokens=2,
            total_tokens=1,
        )
    )

    assert token_usage_from_run_result(result) is None


def test_prompt_lab_token_usage_rejects_malformed_token_counts() -> None:
    result = FakeRunResultWithTokenUsage(
        token_usage=FakeRunTokenUsage(
            input_tokens="five",
            output_tokens=7,
            total_tokens=12,
        )
    )

    assert token_usage_from_run_result(result) is None


def test_prompt_lab_token_usage_rejects_boolean_token_counts() -> None:
    result = FakeRunResultWithTokenUsage(
        token_usage=FakeRunTokenUsage(
            input_tokens=True,
            output_tokens=7,
            total_tokens=8,
        )
    )

    assert token_usage_from_run_result(result) is None


def test_prompt_lab_token_usage_rejects_fractional_token_counts() -> None:
    result = FakeRunResultWithTokenUsage(
        token_usage=FakeRunTokenUsage(
            input_tokens=5.5,
            output_tokens=7,
            total_tokens=12,
        )
    )

    assert token_usage_from_run_result(result) is None


async def test_prompt_lab_auto_optimizer_generates_candidates_and_runs_experiment() -> None:
    experiment_store = RecordingPromptLabStore()
    prompt_store = RecordingPromptStore()
    feedback_store = RecordingFeedbackStore()
    run_service = RecordingRunService()
    executor = PromptLabExecutor(
        experiment_store=experiment_store,
        prompt_store=prompt_store,
        run_service=run_service,
    )
    optimizer = PromptLabAutoOptimizer(
        experiment_store=experiment_store,
        prompt_store=prompt_store,
        feedback_store=feedback_store,
        executor=executor,
    )

    analysis = await optimizer.analyze(
        tenant_id="tenant_1",
        template_id="tmpl-1",
        max_samples=10,
    )
    experiment = await optimizer.run_auto_pipeline(
        tenant_id="tenant_1",
        template_id="tmpl-1",
        user_id="admin_1",
        candidate_count=2,
        judge_model="openai:gpt-4.1",
    )

    assert analysis.negative_count == 1
    assert analysis.weaknesses[0].category == "missing_sources"
    assert experiment.auto_generated is True
    assert experiment.baseline_version_id == "v-1"
    assert len(experiment.candidate_version_ids) == 2
    assert len(prompt_store.created_versions) == 2
    assert "Auto-optimization guidance" in prompt_store.created_versions[0].system_policy
    assert experiment_store.experiments[experiment.id].status == PromptLabExperimentStatus.COMPLETED
    assert run_service.calls


async def test_prompt_lab_scheduler_runs_configured_templates_and_is_non_reentrant() -> None:
    prompt_store = RecordingPromptStore()
    optimizer = RecordingPromptLabAutoOptimizer()
    scheduler = PromptLabScheduler(
        prompt_store=prompt_store,
        optimizer=optimizer,
        template_ids=["tmpl-1", "tmpl-2"],
    )
    block_event = asyncio.Event()
    optimizer.block_event = block_event
    optimizer.fail_template_ids.add("tmpl-2")

    first_run = asyncio.create_task(scheduler.run_scheduled(tenant_id="tenant_1", user_id="system"))
    await asyncio.sleep(0)
    second_run = await scheduler.run_scheduled(tenant_id="tenant_1", user_id="system")
    block_event.set()
    first_result = await first_run

    assert second_run.skipped is True
    assert first_result.skipped is False
    assert first_result.attempted == 2
    assert first_result.succeeded == 1
    assert first_result.failed == 1
    assert [call.template_id for call in optimizer.calls] == ["tmpl-1", "tmpl-2"]
    assert scheduler.last_run_at is not None


async def test_prompt_lab_scheduler_defaults_to_all_prompt_templates() -> None:
    prompt_store = RecordingPromptStore()
    optimizer = RecordingPromptLabAutoOptimizer()
    scheduler = PromptLabScheduler(
        prompt_store=prompt_store,
        optimizer=optimizer,
    )

    result = await scheduler.run_scheduled(tenant_id="tenant_1", user_id="system")

    assert result.attempted == 2
    assert result.succeeded == 2
    assert [call.template_id for call in optimizer.calls] == ["tmpl-1", "tmpl-2"]


async def test_prompt_lab_scheduled_job_executor_runs_auto_optimizer_job() -> None:
    optimizer = RecordingPromptLabAutoOptimizer()
    executor = PromptLabScheduledJobExecutor(optimizer)
    job = ScheduledJobRecord(
        id="job-1",
        tenant_id="tenant_1",
        name="PromptLab auto optimize",
        cron_expression="0 0 9 * * *",
        job_type=ScheduledJobType.PROMPT_LAB_AUTO_OPTIMIZE,
        tool_arguments={
            "templateId": "tmpl-1",
            "candidateCount": "2",
            "judgeModel": "openai:gpt-5-mini",
        },
    )

    result = await executor.execute(job)

    assert (
        result
        == "PromptLab auto-optimization queued for template 'tmpl-1' as experiment 'exp-tmpl-1'"
    )
    assert optimizer.calls == [
        PromptLabAutoOptimizeCall(
            tenant_id="tenant_1",
            template_id="tmpl-1",
            user_id="scheduler",
            candidate_count=2,
            judge_model="openai:gpt-5-mini",
        )
    ]


async def test_prompt_lab_executor_records_provider_llm_judge_tier_when_available() -> None:
    experiment_store = RecordingPromptLabStore()
    prompt_store = RecordingPromptStore()
    run_service = RecordingRunService()
    judge = RecordingPromptLabJudge()
    experiment = PromptLabExperimentRecord(
        id="exp-judge",
        tenant_id="tenant_1",
        name="Judge experiment",
        template_id="tmpl-1",
        baseline_version_id="v-1",
        candidate_version_ids=["v-2"],
        test_queries=[PromptLabTestQuery(query="How do I reset MFA?")],
        judge_model="openai:gpt-4.1",
        created_by="admin_1",
        created_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )
    experiment_store.experiments[experiment.id] = experiment
    executor = PromptLabExecutor(
        experiment_store=experiment_store,
        prompt_store=prompt_store,
        run_service=run_service,
        llm_judge=judge,
    )

    await executor.execute(
        tenant_id="tenant_1",
        experiment_id=experiment.id,
        user_id="admin_1",
    )

    assert len(judge.calls) == 2
    assert judge.calls[0].query == "How do I reset MFA?"
    assert judge.calls[0].response == "Follow the policy citation."
    assert judge.calls[0].judge_model == "openai:gpt-4.1"
    assert experiment_store.trials[0].evaluations[-1] == EvaluationResult(
        tier=EvaluationTier.LLM_JUDGE,
        passed=True,
        score=0.9,
        reason="grounded answer",
        evaluator_name="prompt_lab_llm_judge",
    )


async def test_prompt_lab_llm_judge_uses_native_structured_output_schema() -> None:
    model = RecordingStructuredPromptLabChatModel(
        PromptLabLlmJudgeOutput.model_validate({"pass": True, "score": 0.82, "reason": "grounded"})
    )
    judge = LangChainPromptLabLlmJudge(model)
    experiment = PromptLabExperimentRecord(
        id="exp-judge",
        tenant_id="tenant_1",
        name="Judge experiment",
        template_id="tmpl-1",
        baseline_version_id="v-1",
        candidate_version_ids=[],
        test_queries=[PromptLabTestQuery(query="How do I reset MFA?")],
        created_by="admin_1",
        created_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )
    versions = await RecordingPromptStore().list_versions(
        tenant_id="tenant_1",
        template_id="tmpl-1",
    )
    version = versions[0]

    result = await judge.judge(
        experiment=experiment,
        version=version,
        query=PromptLabTestQuery(query="How do I reset MFA?", expected_behavior="policy"),
        response="Follow the policy citation.",
    )

    assert result == EvaluationResult(
        tier=EvaluationTier.LLM_JUDGE,
        passed=True,
        score=0.82,
        reason="grounded",
        evaluator_name="prompt_lab_llm_judge",
    )
    assert model.structured_schema is PromptLabLlmJudgeOutput
    assert model.messages is not None


class RecordingPromptLabStore:
    def __init__(self) -> None:
        self.experiments: dict[str, PromptLabExperimentRecord] = {}
        self.trials: list[PromptLabTrialRecord] = []
        self.report: PromptLabReportRecord | None = None

    async def save_experiment(self, record: PromptLabExperimentRecord) -> PromptLabExperimentRecord:
        record.validate()
        self.experiments[record.id] = record
        return record

    async def find_experiment(
        self, *, tenant_id: str, experiment_id: str
    ) -> PromptLabExperimentRecord | None:
        record = self.experiments.get(experiment_id)
        return record if record is not None and record.tenant_id == tenant_id else None

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
        record = await self.find_experiment(tenant_id=tenant_id, experiment_id=experiment_id)
        if record is None:
            return None
        updated = PromptLabExperimentRecord(
            id=record.id,
            tenant_id=record.tenant_id,
            name=record.name,
            description=record.description,
            template_id=record.template_id,
            baseline_version_id=record.baseline_version_id,
            candidate_version_ids=record.candidate_version_ids,
            test_queries=record.test_queries,
            evaluation_config=record.evaluation_config,
            model=record.model,
            judge_model=record.judge_model,
            temperature=record.temperature,
            repetitions=record.repetitions,
            auto_generated=record.auto_generated,
            status=status,
            created_by=record.created_by,
            created_at=record.created_at,
            started_at=started_at or record.started_at,
            completed_at=completed_at or record.completed_at,
            error_message=error_message or record.error_message,
        )
        self.experiments[experiment_id] = updated
        return updated

    async def save_trial(self, record: PromptLabTrialRecord) -> PromptLabTrialRecord:
        self.trials.append(record)
        return record

    async def save_report(self, record: PromptLabReportRecord) -> PromptLabReportRecord:
        self.report = record
        return record


class RecordingPromptStore:
    def __init__(self) -> None:
        self.created_versions: list[PromptVersionRecord] = []

    async def list_templates(self, *, tenant_id: str) -> list[PromptTemplateRecord]:
        return [
            PromptTemplateRecord(
                id="tmpl-1",
                tenant_id=tenant_id,
                name="Support",
                graph_profile="default",
                description=None,
                created_by="admin_1",
                created_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
                updated_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
            ),
            PromptTemplateRecord(
                id="tmpl-2",
                tenant_id=tenant_id,
                name="Ops",
                graph_profile="default",
                description=None,
                created_by="admin_1",
                created_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
                updated_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
            ),
        ]

    async def list_versions(self, *, tenant_id: str, template_id: str) -> list[PromptVersionRecord]:
        versions = [
            PromptVersionRecord(
                id="v-1",
                template_id=template_id,
                tenant_id=tenant_id,
                version="1",
                system_policy="Baseline policy citation prompt",
                developer_policy="",
                examples=[],
                metadata={LEGACY_PROMPT_STATUS_KEY: LEGACY_PROMPT_STATUS_ACTIVE},
                content_hash="sha256:baseline",
                created_by="admin_1",
                created_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
            ),
            PromptVersionRecord(
                id="v-2",
                template_id=template_id,
                tenant_id=tenant_id,
                version="2",
                system_policy="Candidate policy citation prompt",
                developer_policy="",
                examples=[],
                metadata={},
                content_hash="sha256:candidate",
                created_by="admin_1",
                created_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
            ),
        ]
        return [*versions, *self.created_versions]

    async def create_legacy_version(
        self,
        *,
        tenant_id: str,
        template_id: str,
        content: str,
        change_log: str,
        created_by: str,
        created_at: datetime,
        version_id: str,
    ) -> PromptVersionRecord | None:
        record = PromptVersionRecord(
            id=version_id,
            template_id=template_id,
            tenant_id=tenant_id,
            version=str(3 + len(self.created_versions)),
            system_policy=content,
            developer_policy="",
            examples=[],
            metadata={"changeLog": change_log},
            content_hash=f"sha256:auto-{len(self.created_versions)}",
            created_by=created_by,
            created_at=created_at,
        )
        self.created_versions.append(record)
        return record


class RecordingFeedbackStore:
    def __init__(self) -> None:
        self.records = [
            Feedback(
                feedback_id="fb_1",
                tenant_id="tenant_1",
                query="How do I reset MFA?",
                response="Reset MFA in settings.",
                rating=FeedbackRating.THUMBS_DOWN,
                session_id="session_1",
                user_id="user_1",
                comment="Needs source citation.",
                intent="support",
                domain="auth",
                tags=["citation"],
                template_id="tmpl-1",
                created_at=datetime(2026, 6, 27, 11, 0, tzinfo=UTC),
                updated_at=datetime(2026, 6, 27, 11, 0, tzinfo=UTC),
            ),
            Feedback(
                feedback_id="fb_2",
                tenant_id="tenant_1",
                query="Thanks",
                response="You are welcome.",
                rating=FeedbackRating.THUMBS_UP,
                session_id="session_2",
                user_id="user_1",
                template_id="tmpl-1",
                created_at=datetime(2026, 6, 27, 11, 1, tzinfo=UTC),
                updated_at=datetime(2026, 6, 27, 11, 1, tzinfo=UTC),
            ),
        ]

    async def list(
        self,
        *,
        tenant_id: str,
        rating: FeedbackRating | None = None,
        template_id: str | None = None,
        limit: int = 50,
    ) -> list[Feedback]:
        records = [record for record in self.records if record.tenant_id == tenant_id]
        if rating is not None:
            records = [record for record in records if record.rating == rating]
        if template_id is not None:
            records = [record for record in records if record.template_id == template_id]
        return records[:limit]


class RecordingRunService:
    def __init__(self) -> None:
        self.calls: list[RecordedRunCall] = []

    async def create_run(
        self,
        message: str,
        *,
        tenant_id: str = "local",
        user_id: str = "anonymous",
        thread_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> RunResult:
        self.calls.append(
            RecordedRunCall(
                message=message,
                tenant_id=tenant_id,
                user_id=user_id,
                thread_id=thread_id,
                metadata=metadata or {},
            )
        )
        return RunResult(
            run_id=f"run-{len(self.calls)}",
            tenant_id=tenant_id,
            user_id=user_id,
            thread_id=thread_id or "thread_1",
            checkpoint_ns="default",
            status="completed",
            response="Follow the policy citation.",
            provider="openai",
            model="gpt-4.1-mini",
            token_usage=TokenUsage(input_tokens=5, output_tokens=7, max_output_tokens=100),
        )


@dataclass(frozen=True)
class PromptLabAutoOptimizeCall:
    tenant_id: str
    template_id: str
    user_id: str
    candidate_count: int | None = None
    judge_model: str | None = None


@dataclass(frozen=True)
class FakeRunTokenUsage:
    input_tokens: object
    output_tokens: object
    total_tokens: object


@dataclass(frozen=True)
class FakeRunResultWithTokenUsage:
    token_usage: FakeRunTokenUsage


class RecordingPromptLabAutoOptimizer:
    def __init__(self) -> None:
        self.calls: list[PromptLabAutoOptimizeCall] = []
        self.block_event: asyncio.Event | None = None
        self.fail_template_ids: set[str] = set()

    async def run_auto_pipeline(
        self,
        *,
        tenant_id: str,
        template_id: str,
        user_id: str,
        candidate_count: int | None = None,
        judge_model: str | None = None,
    ) -> PromptLabExperimentRecord:
        if self.block_event is not None:
            await self.block_event.wait()
        self.calls.append(
            PromptLabAutoOptimizeCall(
                tenant_id=tenant_id,
                template_id=template_id,
                user_id=user_id,
                candidate_count=candidate_count,
                judge_model=judge_model,
            )
        )
        if template_id in self.fail_template_ids:
            raise RuntimeError("template failed")
        return PromptLabExperimentRecord(
            id=f"exp-{template_id}",
            tenant_id=tenant_id,
            name=f"Auto {template_id}",
            template_id=template_id,
            baseline_version_id="v-1",
            candidate_version_ids=["v-2"],
            created_by=user_id,
            created_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
        )


@dataclass(frozen=True)
class RecordedRunCall:
    message: str
    tenant_id: str
    user_id: str
    thread_id: str | None
    metadata: dict[str, object]


@dataclass(frozen=True)
class JudgeCall:
    query: str
    response: str
    judge_model: str | None


class RecordingPromptLabJudge:
    def __init__(self) -> None:
        self.calls: list[JudgeCall] = []

    async def judge(
        self,
        *,
        experiment: PromptLabExperimentRecord,
        version: PromptVersionRecord,
        query: PromptLabTestQuery,
        response: str,
    ) -> EvaluationResult:
        del version
        self.calls.append(
            JudgeCall(
                query=query.query,
                response=response,
                judge_model=experiment.judge_model,
            )
        )
        return EvaluationResult(
            tier=EvaluationTier.LLM_JUDGE,
            passed=True,
            score=0.9,
            reason="grounded answer",
            evaluator_name="prompt_lab_llm_judge",
        )


class RecordingStructuredPromptLabChatModel:
    def __init__(self, response: object) -> None:
        self._response = response
        self.structured_schema: object | None = None
        self.messages: list[BaseMessage] | None = None

    def with_structured_output(
        self,
        schema: object,
    ) -> RecordingStructuredPromptLabChatModel:
        self.structured_schema = schema
        return self

    async def ainvoke(self, input: list[BaseMessage]) -> object:
        self.messages = input
        return self._response
