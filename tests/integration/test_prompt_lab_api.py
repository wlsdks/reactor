from __future__ import annotations

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app
from reactor.persistence.prompt_store import (
    LEGACY_PROMPT_STATUS_ACTIVE,
    LEGACY_PROMPT_STATUS_KEY,
    PromptVersionRecord,
)
from reactor.prompt_lab.models import (
    EvaluationResult,
    EvaluationTier,
    FeedbackAnalysis,
    PromptLabExperimentRecord,
    PromptLabExperimentStatus,
    PromptLabReportRecord,
    PromptLabTrialRecord,
    PromptWeakness,
    Recommendation,
    RecommendationConfidence,
    VersionSummary,
)
from reactor.prompt_lab.models import (
    TestQuery as PromptLabTestQuery,
)

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}


async def test_prompt_lab_requires_admin_and_persistence() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/prompt-lab/experiments")
        unavailable = await client.get("/api/prompt-lab/experiments", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "permission required: prompt:read"
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"] == "prompt lab persistence is not configured"


async def test_prompt_lab_experiment_flow_with_store() -> None:
    store = FakePromptLabStore()
    prompt_store = FakePromptStore()
    executor = FakePromptLabExecutor()
    optimizer = FakePromptLabAutoOptimizer()
    app = create_app()
    app.state.reactor = FakeContainer(store, prompt_store, executor, optimizer)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        created = await client.post(
            "/api/prompt-lab/experiments",
            headers=ADMIN_HEADERS,
            json={
                "name": "Support prompt experiment",
                "description": "Compare baseline and candidate",
                "templateId": "tmpl-1",
                "baselineVersionId": "v-1",
                "candidateVersionIds": ["v-2"],
                "testQueries": [
                    {
                        "query": "How do I reset MFA?",
                        "intent": "support",
                        "expectedBehavior": "Answer with policy citation.",
                        "tags": ["auth"],
                    }
                ],
                "evaluationConfig": {
                    "structuralEnabled": True,
                    "rulesEnabled": True,
                    "llmJudgeEnabled": True,
                    "llmJudgeBudgetTokens": 1000,
                },
                "model": "openai:gpt-4.1-mini",
                "judgeModel": "openai:gpt-4.1",
                "temperature": 0.2,
                "repetitions": 2,
            },
        )
        experiment_id = created.json()["id"]
        listed = await client.get("/api/prompt-lab/experiments", headers=ADMIN_HEADERS)
        fetched = await client.get(
            f"/api/prompt-lab/experiments/{experiment_id}",
            headers=ADMIN_HEADERS,
        )
        accepted = await client.post(
            f"/api/prompt-lab/experiments/{experiment_id}/run",
            headers=ADMIN_HEADERS,
        )
        status_response = await client.get(
            f"/api/prompt-lab/experiments/{experiment_id}/status",
            headers=ADMIN_HEADERS,
        )
        cancelled = await client.post(
            f"/api/prompt-lab/experiments/{experiment_id}/cancel",
            headers=ADMIN_HEADERS,
        )
        trials = await client.get(
            f"/api/prompt-lab/experiments/{experiment_id}/trials",
            headers=ADMIN_HEADERS,
        )
        report = await client.get(
            f"/api/prompt-lab/experiments/{experiment_id}/report",
            headers=ADMIN_HEADERS,
        )
        activated = await client.post(
            f"/api/prompt-lab/experiments/{experiment_id}/activate",
            headers=ADMIN_HEADERS,
        )
        auto = await client.post(
            "/api/prompt-lab/auto-optimize",
            headers=ADMIN_HEADERS,
            json={"templateId": "tmpl-1", "candidateCount": 2},
        )
        analysis = await client.post(
            "/api/prompt-lab/analyze",
            headers=ADMIN_HEADERS,
            json={"templateId": "tmpl-1"},
        )
        deleted = await client.delete(
            f"/api/prompt-lab/experiments/{experiment_id}",
            headers=ADMIN_HEADERS,
        )
        missing = await client.get(
            f"/api/prompt-lab/experiments/{experiment_id}",
            headers=ADMIN_HEADERS,
        )

    assert created.status_code == 201
    assert created.json()["status"] == "PENDING"
    assert created.json()["createdBy"] == "admin_1"
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == experiment_id
    assert fetched.status_code == 200
    assert accepted.status_code == 202
    assert accepted.json() == {"status": "RUNNING", "experimentId": experiment_id}
    assert executor.calls == [("tenant_1", experiment_id, "admin_1")]
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "RUNNING"
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert trials.status_code == 200
    assert trials.json()[0]["score"] == 0.8
    assert trials.json()[0]["passed"] is True
    assert report.status_code == 200
    assert report.json()["recommendation"]["bestVersionId"] == "v-2"
    assert activated.status_code == 200
    assert activated.json()["versionId"] == "v-2"
    assert auto.status_code == 202
    assert auto.json()["status"] == "STARTED"
    assert optimizer.pipeline_calls == [("tenant_1", "tmpl-1", "admin_1", 2, None)]
    assert analysis.status_code == 200
    assert analysis.json()["negativeCount"] == 1
    assert analysis.json()["weaknesses"][0]["category"] == "missing_sources"
    assert deleted.status_code == 204
    assert missing.status_code == 404


async def test_prompt_lab_status_sanitizes_error_message() -> None:
    store = FakePromptLabStore()
    experiment = build_experiment(status=PromptLabExperimentStatus.FAILED)
    store.experiments[experiment.id] = PromptLabExperimentRecord(
        id=experiment.id,
        tenant_id=experiment.tenant_id,
        name=experiment.name,
        template_id=experiment.template_id,
        baseline_version_id=experiment.baseline_version_id,
        candidate_version_ids=experiment.candidate_version_ids,
        test_queries=experiment.test_queries,
        status=PromptLabExperimentStatus.FAILED,
        created_by=experiment.created_by,
        created_at=experiment.created_at,
        error_message="Provider failed\n    at internal.secret.File.kt:42",
    )
    app = create_app()
    app.state.reactor = FakeContainer(store, FakePromptStore())
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            f"/api/prompt-lab/experiments/{experiment.id}/status",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 200
    assert response.json()["errorMessage"] == "Provider failed"


class FakeContainer:
    def __init__(
        self,
        store: FakePromptLabStore,
        prompt_store: FakePromptStore,
        executor: FakePromptLabExecutor | None = None,
        optimizer: FakePromptLabAutoOptimizer | None = None,
    ) -> None:
        self._store = store
        self._prompt_store = prompt_store
        self._executor = executor
        self._optimizer = optimizer

    def prompt_lab_store(self) -> FakePromptLabStore:
        return self._store

    def prompt_store(self) -> FakePromptStore:
        return self._prompt_store

    def prompt_lab_executor(self) -> FakePromptLabExecutor | None:
        return self._executor

    def prompt_lab_auto_optimizer(self) -> FakePromptLabAutoOptimizer | None:
        return self._optimizer


class FakePromptLabExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def execute(self, *, tenant_id: str, experiment_id: str, user_id: str) -> None:
        self.calls.append((tenant_id, experiment_id, user_id))


class FakePromptLabAutoOptimizer:
    def __init__(self) -> None:
        self.pipeline_calls: list[tuple[str, str, str, int | None, str | None]] = []

    async def analyze(
        self,
        *,
        tenant_id: str,
        template_id: str,
        max_samples: int = 50,
    ) -> FeedbackAnalysis:
        return FeedbackAnalysis(
            total_feedback=2,
            negative_count=1,
            weaknesses=[
                PromptWeakness(
                    category="missing_sources",
                    description="Answers need citations.",
                    frequency=1,
                    example_queries=["How do I reset MFA?"],
                )
            ],
            sample_queries=[
                PromptLabTestQuery(
                    query="How do I reset MFA?",
                    intent="support",
                    expected_behavior="Answer with policy citation.",
                    tags=["auth"],
                )
            ],
            analyzed_at=datetime(2026, 6, 27, 12, 3, tzinfo=UTC),
        )

    async def run_auto_pipeline(
        self,
        *,
        tenant_id: str,
        template_id: str,
        user_id: str,
        candidate_count: int | None = None,
        judge_model: str | None = None,
    ) -> PromptLabExperimentRecord:
        self.pipeline_calls.append((tenant_id, template_id, user_id, candidate_count, judge_model))
        return build_experiment()


class FakePromptLabStore:
    def __init__(self) -> None:
        self.experiments: dict[str, PromptLabExperimentRecord] = {}
        self.trials: dict[str, PromptLabTrialRecord] = {}
        self.reports: dict[str, PromptLabReportRecord] = {}

    async def save_experiment(self, record: PromptLabExperimentRecord) -> PromptLabExperimentRecord:
        record.validate()
        self.experiments[record.id] = record
        self.trials.setdefault(build_trial(record).id, build_trial(record))
        self.reports.setdefault(record.id, build_report(record))
        return record

    async def list_experiments(
        self,
        *,
        tenant_id: str,
        status: PromptLabExperimentStatus | None = None,
        template_id: str | None = None,
    ) -> list[PromptLabExperimentRecord]:
        records = [record for record in self.experiments.values() if record.tenant_id == tenant_id]
        if status is not None:
            records = [record for record in records if record.status == status]
        if template_id is not None:
            records = [record for record in records if record.template_id == template_id]
        return records

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
        self.experiments[record.id] = updated
        return updated

    async def delete_experiment(self, *, tenant_id: str, experiment_id: str) -> None:
        record = await self.find_experiment(tenant_id=tenant_id, experiment_id=experiment_id)
        if record is not None:
            self.experiments.pop(experiment_id, None)

    async def list_trials(
        self, *, tenant_id: str, experiment_id: str
    ) -> list[PromptLabTrialRecord]:
        return [
            record
            for record in self.trials.values()
            if record.tenant_id == tenant_id and record.experiment_id == experiment_id
        ]

    async def find_report(
        self, *, tenant_id: str, experiment_id: str
    ) -> PromptLabReportRecord | None:
        report = self.reports.get(experiment_id)
        return report if report is not None and report.tenant_id == tenant_id else None


class FakePromptStore:
    async def activate_legacy_version(
        self,
        *,
        tenant_id: str,
        template_id: str,
        version_id: str,
    ) -> PromptVersionRecord | None:
        return PromptVersionRecord(
            id=version_id,
            template_id=template_id,
            tenant_id=tenant_id,
            version="2",
            system_policy="candidate",
            developer_policy="",
            examples=[],
            metadata={LEGACY_PROMPT_STATUS_KEY: LEGACY_PROMPT_STATUS_ACTIVE},
            content_hash="sha256:abc",
            created_by="admin_1",
            created_at=datetime.now(UTC),
        )


def build_experiment(
    status: PromptLabExperimentStatus = PromptLabExperimentStatus.PENDING,
) -> PromptLabExperimentRecord:
    return PromptLabExperimentRecord(
        id="exp-1",
        tenant_id="tenant_1",
        name="Support prompt experiment",
        template_id="tmpl-1",
        baseline_version_id="v-1",
        candidate_version_ids=["v-2"],
        test_queries=[PromptLabTestQuery(query="How do I reset MFA?")],
        status=status,
        created_by="admin_1",
        created_at=datetime(2026, 6, 27, 12, 0, tzinfo=UTC),
    )


def build_trial(experiment: PromptLabExperimentRecord) -> PromptLabTrialRecord:
    return PromptLabTrialRecord(
        id=f"trial-{experiment.id}",
        tenant_id=experiment.tenant_id,
        experiment_id=experiment.id,
        prompt_version_id="v-2",
        prompt_version_number=2,
        test_query=experiment.test_queries[0],
        response="Use the MFA reset policy.",
        success=True,
        duration_ms=100,
        evaluations=[
            EvaluationResult(
                tier=EvaluationTier.RULES,
                passed=True,
                score=0.8,
                reason="Matched expected behavior.",
            )
        ],
        executed_at=datetime(2026, 6, 27, 12, 1, tzinfo=UTC),
    )


def build_report(experiment: PromptLabExperimentRecord) -> PromptLabReportRecord:
    return PromptLabReportRecord(
        experiment_id=experiment.id,
        tenant_id=experiment.tenant_id,
        experiment_name=experiment.name,
        total_trials=1,
        version_summaries=[
            VersionSummary(
                version_id="v-2",
                version_number=2,
                is_baseline=False,
                total_trials=1,
                pass_count=1,
                pass_rate=1.0,
                avg_score=0.8,
                avg_duration_ms=100,
                total_tokens=42,
                tier_breakdown={"RULES": {"passCount": 1, "failCount": 0}},
                tool_usage_frequency={},
                error_rate=0.0,
            )
        ],
        recommendation=Recommendation(
            best_version_id="v-2",
            best_version_number=2,
            confidence=RecommendationConfidence.HIGH,
            reasoning="Candidate passed.",
        ),
        generated_at=datetime(2026, 6, 27, 12, 2, tzinfo=UTC),
    )
