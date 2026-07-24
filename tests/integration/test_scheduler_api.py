from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app
from reactor.core.settings import Settings
from reactor.scheduler.service import (
    JobExecutionStatus,
    ScheduledJobExecutionRecord,
    ScheduledJobLease,
    ScheduledJobRecord,
    ScheduledJobType,
)

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}

MANAGER_HEADERS = {
    "X-Reactor-User-Id": "manager_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN_MANAGER",
}


async def test_scheduler_stub_requires_developer_admin_and_returns_empty_lists() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/scheduler/jobs", headers=MANAGER_HEADERS)
        listed = await client.get("/api/scheduler/jobs", headers=ADMIN_HEADERS)
        executions = await client.get(
            "/api/scheduler/jobs/missing/executions", headers=ADMIN_HEADERS
        )
        create_disabled = await client.post(
            "/api/scheduler/jobs",
            headers=ADMIN_HEADERS,
            json={
                "name": "Daily",
                "cronExpression": "0 0 9 * * *",
                "mcpServerName": "atlas",
                "toolName": "search",
            },
        )

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "permission required: scheduler:read"
    assert listed.status_code == 200
    assert listed.json() == []
    assert executions.status_code == 200
    assert executions.json() == []
    assert create_disabled.status_code == 503
    assert create_disabled.json()["detail"] == {"error": "DynamicSchedulerService not configured"}


async def test_scheduler_crud_tag_filter_trigger_dry_run_and_executions() -> None:
    job_store = FakeSchedulerStore()
    execution_store = FakeSchedulerExecutionStore()
    app = create_app()
    app.state.reactor = FakeContainer(job_store, execution_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        created = await client.post(
            "/api/scheduler/jobs",
            headers=ADMIN_HEADERS,
            json={
                "name": "Daily report",
                "description": "Generate a daily digest",
                "cronExpression": "0 0 9 * * *",
                "mcpServerName": "atlas",
                "toolName": "search",
                "toolArguments": {"query": "release risk"},
                "tags": ["daily", "reporting"],
                "retryOnFailure": True,
                "maxRetryCount": 2,
            },
        )
        job_id = created.json()["id"]
        listed = await client.get(
            "/api/scheduler/jobs?tag=daily&offset=0&limit=1", headers=ADMIN_HEADERS
        )
        fetched = await client.get(f"/v1/scheduler/jobs/{job_id}", headers=ADMIN_HEADERS)
        updated = await client.put(
            f"/api/scheduler/jobs/{job_id}",
            headers=ADMIN_HEADERS,
            json={
                "name": "Daily agent report",
                "cronExpression": "0 30 9 * * *",
                "jobType": "AGENT",
                "agentPrompt": "Summarize release risk",
                "tags": ["daily"],
                "enabled": False,
            },
        )
        dry_run = await client.post(f"/v1/scheduler/jobs/{job_id}/dry-run", headers=ADMIN_HEADERS)
        trigger = await client.post(f"/api/scheduler/jobs/{job_id}/trigger", headers=ADMIN_HEADERS)
        executions = await client.get(
            f"/api/scheduler/jobs/{job_id}/executions?limit=20&pageLimit=10",
            headers=ADMIN_HEADERS,
        )
        deleted = await client.delete(f"/api/scheduler/jobs/{job_id}", headers=ADMIN_HEADERS)

    assert created.status_code == 201
    assert created.json()["jobType"] == "MCP_TOOL"
    assert created.json()["toolArguments"] == {"query": "release risk"}
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == job_id
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Daily report"
    assert updated.status_code == 200
    assert updated.json()["jobType"] == "AGENT"
    assert updated.json()["enabled"] is False
    assert dry_run.status_code == 200
    assert dry_run.json()["dryRun"] is True
    assert trigger.status_code == 200
    assert trigger.json()["result"] == "Scheduled job 'Daily agent report' queued for execution"
    assert executions.status_code == 200
    assert executions.json()["total"] == 2
    assert executions.json()["items"][0]["dryRun"] is False
    assert executions.json()["items"][1]["dryRun"] is True
    assert deleted.status_code == 204


async def test_scheduler_rejects_invalid_type_specific_request() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(FakeSchedulerStore(), FakeSchedulerExecutionStore())
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        invalid = await client.post(
            "/api/scheduler/jobs",
            headers=ADMIN_HEADERS,
            json={"name": "bad", "cronExpression": "0 0 9 * * *"},
        )

    assert invalid.status_code == 400
    assert invalid.json()["detail"] == "Invalid request"


async def test_scheduler_rejects_invalid_cron_before_store_write() -> None:
    job_store = FakeSchedulerStore()
    app = create_app()
    app.state.reactor = FakeContainer(job_store, FakeSchedulerExecutionStore())
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        invalid = await client.post(
            "/api/scheduler/jobs",
            headers=ADMIN_HEADERS,
            json={
                "name": "Bad cron",
                "cronExpression": "not a cron",
                "mcpServerName": "atlas",
                "toolName": "search",
            },
        )

    assert invalid.status_code == 400
    assert invalid.json()["detail"] == "Invalid request"
    assert job_store.jobs == {}


async def test_scheduler_trigger_routes_prompt_lab_auto_optimize_job_to_executor() -> None:
    job_store = FakeSchedulerStore()
    execution_store = FakeSchedulerExecutionStore()
    prompt_lab_executor = FakePromptLabScheduledJobExecutor()
    app = create_app()
    app.state.reactor = FakeContainer(
        job_store,
        execution_store,
        prompt_lab_executor=prompt_lab_executor,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        created = await client.post(
            "/api/scheduler/jobs",
            headers=ADMIN_HEADERS,
            json={
                "name": "PromptLab auto optimize",
                "cronExpression": "0 0 9 * * *",
                "jobType": "PROMPT_LAB_AUTO_OPTIMIZE",
                "toolArguments": {"templateId": "tmpl-1", "candidateCount": 2},
            },
        )
        job_id = created.json()["id"]
        trigger = await client.post(f"/api/scheduler/jobs/{job_id}/trigger", headers=ADMIN_HEADERS)

    assert created.status_code == 201
    assert created.json()["jobType"] == "PROMPT_LAB_AUTO_OPTIMIZE"
    assert trigger.status_code == 200
    assert trigger.json()["result"] == "prompt lab queued: tmpl-1"
    assert [job.job_type for job in prompt_lab_executor.calls] == [
        ScheduledJobType.PROMPT_LAB_AUTO_OPTIMIZE
    ]
    assert prompt_lab_executor.calls[0].tool_arguments == {
        "templateId": "tmpl-1",
        "candidateCount": 2,
    }


class FakeContainer:
    def __init__(
        self,
        scheduler_store: FakeSchedulerStore,
        execution_store: FakeSchedulerExecutionStore,
        *,
        prompt_lab_executor: FakePromptLabScheduledJobExecutor | None = None,
    ) -> None:
        self.settings = Settings()
        self._scheduler_store = scheduler_store
        self._execution_store = execution_store
        self._prompt_lab_executor = prompt_lab_executor

    def scheduler_store(self) -> FakeSchedulerStore:
        return self._scheduler_store

    def scheduled_job_execution_store(self) -> FakeSchedulerExecutionStore:
        return self._execution_store

    def prompt_lab_scheduled_job_executor(self) -> FakePromptLabScheduledJobExecutor | None:
        return self._prompt_lab_executor


class FakePromptLabScheduledJobExecutor:
    def __init__(self) -> None:
        self.calls: list[ScheduledJobRecord] = []

    async def execute(self, job: ScheduledJobRecord) -> str:
        self.calls.append(job)
        return f"prompt lab queued: {job.tool_arguments['templateId']}"


class FakeSchedulerStore:
    def __init__(self) -> None:
        self.jobs: dict[str, ScheduledJobRecord] = {}

    async def list(self, *, tenant_id: str) -> list[ScheduledJobRecord]:
        return sorted(
            [job for job in self.jobs.values() if job.tenant_id == tenant_id],
            key=lambda job: job.created_at,
        )

    async def find_by_id(self, *, tenant_id: str, job_id: str) -> ScheduledJobRecord | None:
        job = self.jobs.get(job_id)
        return job if job is not None and job.tenant_id == tenant_id else None

    async def find_by_name(self, *, tenant_id: str, name: str) -> ScheduledJobRecord | None:
        for job in self.jobs.values():
            if job.tenant_id == tenant_id and job.name == name:
                return job
        return None

    async def save(self, job: ScheduledJobRecord) -> ScheduledJobRecord:
        job.validate()
        self.jobs[job.id] = job
        return job

    async def update(
        self,
        *,
        tenant_id: str,
        job_id: str,
        job: ScheduledJobRecord,
    ) -> ScheduledJobRecord | None:
        if job_id not in self.jobs or self.jobs[job_id].tenant_id != tenant_id:
            return None
        existing = self.jobs[job_id]
        job.validate()
        updated = replace(job, created_at=existing.created_at, updated_at=datetime.now(UTC))
        self.jobs[job_id] = updated
        return updated

    async def delete(self, *, tenant_id: str, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if job is None or job.tenant_id != tenant_id:
            return False
        self.jobs.pop(job_id)
        return True

    async def update_execution_result(
        self,
        *,
        tenant_id: str,
        job_id: str,
        status: JobExecutionStatus,
        result: str | None,
    ) -> ScheduledJobRecord | None:
        job = await self.find_by_id(tenant_id=tenant_id, job_id=job_id)
        if job is None:
            return None
        updated = job.with_execution_result(status=status, result=result)
        self.jobs[job_id] = updated
        return updated

    async def try_acquire_lease(
        self,
        *,
        tenant_id: str,
        job_id: str,
        lease_owner: str,
        lease_seconds: int,
    ) -> ScheduledJobLease | None:
        job = await self.find_by_id(tenant_id=tenant_id, job_id=job_id)
        if job is None:
            return None
        return ScheduledJobLease(
            job_id=job_id,
            tenant_id=tenant_id,
            lease_owner=lease_owner,
            fencing_token=1,
            lease_expires_at=datetime.now(UTC) + timedelta(seconds=lease_seconds),
        )

    async def release_lease(
        self,
        *,
        tenant_id: str,
        job_id: str,
        lease_owner: str,
        fencing_token: int,
    ) -> bool:
        del tenant_id, job_id, lease_owner, fencing_token
        return True


class FakeSchedulerExecutionStore:
    def __init__(self) -> None:
        self.executions: list[ScheduledJobExecutionRecord] = []

    async def save(self, execution: ScheduledJobExecutionRecord) -> ScheduledJobExecutionRecord:
        self.executions.insert(0, execution)
        return execution

    async def find_by_job_id(
        self, *, tenant_id: str, job_id: str, limit: int = 20
    ) -> list[ScheduledJobExecutionRecord]:
        return [
            execution
            for execution in self.executions
            if execution.tenant_id == tenant_id and execution.job_id == job_id
        ][:limit]

    async def find_recent(
        self, *, tenant_id: str, limit: int = 50
    ) -> list[ScheduledJobExecutionRecord]:
        return [execution for execution in self.executions if execution.tenant_id == tenant_id][
            :limit
        ]

    async def delete_oldest_executions(
        self, *, tenant_id: str, job_id: str, keep_count: int
    ) -> int:
        return 0
