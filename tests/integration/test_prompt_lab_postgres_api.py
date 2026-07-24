from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from docker.errors import DockerException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from reactor.api.app import create_app
from reactor.core.settings import Settings, get_settings
from reactor.persistence.models import PromptLabExperiment, PromptLabReport, PromptLabTrial
from reactor.persistence.prompt_lab_store import SqlAlchemyPromptLabStore
from reactor.persistence.prompt_store import (
    LEGACY_PROMPT_STATUS_ACTIVE,
    LEGACY_PROMPT_STATUS_KEY,
    PromptVersionRecord,
)
from reactor.prompt_lab.models import (
    EvaluationResult,
    EvaluationTier,
    PromptLabReportRecord,
    PromptLabTrialRecord,
    Recommendation,
    RecommendationConfidence,
    VersionSummary,
)
from reactor.prompt_lab.models import TestQuery as PromptLabTestQuery

pytestmark = pytest.mark.skipif(
    os.environ.get("REACTOR_TEST_POSTGRES") != "1",
    reason="set REACTOR_TEST_POSTGRES=1 to run Docker-backed PromptLab API tests",
)

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}


async def test_prompt_lab_api_persists_experiment_flow_against_postgres() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for PromptLab API test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        prompt_lab_store = SqlAlchemyPromptLabStore(session_factory)
        app = create_app()
        app.state.reactor = PromptLabApiContainer(prompt_lab_store)
        transport = ASGITransport(app=app)

        try:
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                created = await client.post(
                    "/api/prompt-lab/experiments",
                    headers=ADMIN_HEADERS,
                    json={
                        "name": "Generic support prompt experiment",
                        "description": "Compare baseline and candidate responses",
                        "templateId": "tmpl-1",
                        "baselineVersionId": "v-1",
                        "candidateVersionIds": ["v-2"],
                        "testQueries": [
                            {
                                "query": "How do I reset my access factor?",
                                "intent": "support",
                                "domain": "identity",
                                "expectedBehavior": "Answer with a citation.",
                                "tags": ["identity"],
                            }
                        ],
                        "evaluationConfig": {
                            "structuralEnabled": True,
                            "rulesEnabled": True,
                            "llmJudgeEnabled": False,
                            "llmJudgeBudgetTokens": 1000,
                        },
                        "model": "openai:gpt-5-mini",
                        "judgeModel": "openai:gpt-5",
                        "temperature": 0.2,
                        "repetitions": 2,
                    },
                )
                experiment_id = created.json()["id"]
                accepted = await client.post(
                    f"/api/prompt-lab/experiments/{experiment_id}/run",
                    headers=ADMIN_HEADERS,
                )
                running_status = await client.get(
                    f"/api/prompt-lab/experiments/{experiment_id}/status",
                    headers=ADMIN_HEADERS,
                )

                experiment = await prompt_lab_store.find_experiment(
                    tenant_id="tenant_1",
                    experiment_id=experiment_id,
                )
                assert experiment is not None
                await prompt_lab_store.save_trial(build_trial(experiment_id=experiment_id))
                await prompt_lab_store.save_report(
                    build_report(
                        experiment_id=experiment_id,
                        experiment_name=experiment.name,
                    )
                )

                listed = await client.get(
                    "/api/prompt-lab/experiments",
                    params={"status": "RUNNING", "templateId": "tmpl-1"},
                    headers=ADMIN_HEADERS,
                )
                fetched = await client.get(
                    f"/api/prompt-lab/experiments/{experiment_id}",
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
                cancelled = await client.post(
                    f"/api/prompt-lab/experiments/{experiment_id}/cancel",
                    headers=ADMIN_HEADERS,
                )
                deleted = await client.delete(
                    f"/api/prompt-lab/experiments/{experiment_id}",
                    headers=ADMIN_HEADERS,
                )
                missing = await client.get(
                    f"/api/prompt-lab/experiments/{experiment_id}",
                    headers=ADMIN_HEADERS,
                )

            async with session_factory() as session:
                experiment_count = await session.scalar(select(func.count(PromptLabExperiment.id)))
                trial_count = await session.scalar(select(func.count(PromptLabTrial.id)))
                report_count = await session.scalar(
                    select(func.count(PromptLabReport.experiment_id))
                )

            assert created.status_code == 201
            assert created.json()["status"] == "PENDING"
            assert created.json()["createdBy"] == "admin_1"
            assert accepted.status_code == 202
            assert accepted.json() == {"status": "RUNNING", "experimentId": experiment_id}
            assert running_status.status_code == 200
            assert running_status.json()["status"] == "RUNNING"
            assert listed.status_code == 200
            assert [item["id"] for item in listed.json()] == [experiment_id]
            assert fetched.status_code == 200
            assert fetched.json()["candidateVersionIds"] == ["v-2"]
            assert trials.status_code == 200
            assert trials.json()[0]["promptVersionId"] == "v-2"
            assert trials.json()[0]["score"] == 0.9
            assert report.status_code == 200
            assert report.json()["recommendation"]["bestVersionId"] == "v-2"
            assert activated.status_code == 200
            assert activated.json()["versionId"] == "v-2"
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "CANCELLED"
            assert deleted.status_code == 204
            assert missing.status_code == 404
            assert experiment_count == 0
            assert trial_count == 0
            assert report_count == 0
        finally:
            await engine.dispose()


class PromptLabApiContainer:
    def __init__(self, prompt_lab_store: SqlAlchemyPromptLabStore) -> None:
        self.settings = Settings()
        self._prompt_lab_store = prompt_lab_store
        self._prompt_store = FakePromptStore()

    def prompt_lab_store(self) -> SqlAlchemyPromptLabStore:
        return self._prompt_lab_store

    def prompt_store(self) -> FakePromptStore:
        return self._prompt_store


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
            content_hash="sha256:prompt-lab-postgres",
            created_by="admin_1",
            created_at=datetime.now(UTC),
        )


def build_trial(*, experiment_id: str) -> PromptLabTrialRecord:
    return PromptLabTrialRecord(
        tenant_id="tenant_1",
        experiment_id=experiment_id,
        prompt_version_id="v-2",
        prompt_version_number=2,
        test_query=PromptLabTestQuery(
            query="How do I reset my access factor?",
            intent="support",
            domain="identity",
            expected_behavior="Answer with a citation.",
            tags=["identity"],
        ),
        response="Use the verified reset workflow and cite the source.",
        success=True,
        duration_ms=125,
        evaluations=[
            EvaluationResult(
                tier=EvaluationTier.RULES,
                passed=True,
                score=0.9,
                reason="Matched expected citation behavior.",
            )
        ],
        executed_at=datetime(2026, 6, 27, 12, 1, tzinfo=UTC),
    )


def build_report(*, experiment_id: str, experiment_name: str) -> PromptLabReportRecord:
    return PromptLabReportRecord(
        experiment_id=experiment_id,
        tenant_id="tenant_1",
        experiment_name=experiment_name,
        total_trials=1,
        version_summaries=[
            VersionSummary(
                version_id="v-2",
                version_number=2,
                is_baseline=False,
                total_trials=1,
                pass_count=1,
                pass_rate=1.0,
                avg_score=0.9,
                avg_duration_ms=125,
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
            reasoning="Candidate passed the generic regression query.",
        ),
        generated_at=datetime(2026, 6, 27, 12, 2, tzinfo=UTC),
    )


def postgres_container() -> PostgresContainer:
    return PostgresContainer(
        image="pgvector/pgvector:0.8.3-pg18-trixie",
        username="reactor",
        password="reactor",  # noqa: S106 - ephemeral Docker test credential
        dbname="reactor",
    )


def migrate_postgres(sync_url: str) -> None:
    previous_url = os.environ.get("REACTOR_DATABASE_URL")
    os.environ["REACTOR_DATABASE_URL"] = sync_url
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        if previous_url is None:
            os.environ.pop("REACTOR_DATABASE_URL", None)
        else:
            os.environ["REACTOR_DATABASE_URL"] = previous_url
        get_settings.cache_clear()
