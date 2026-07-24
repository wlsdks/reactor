from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from reactor.scheduler.service import (
    JobExecutionStatus,
    ScheduledJobDeadLetterRecord,
    ScheduledJobExecutionRecord,
    ScheduledJobLease,
    ScheduledJobRecord,
)
from reactor.scheduler.worker import (
    ScheduledJobExecutor,
    SchedulerWorker,
    SchedulerWorkerConfig,
)


async def test_scheduler_worker_success_records_execution_and_updates_last_result() -> None:
    job_store = FakeSchedulerStore()
    execution_store = FakeExecutionStore()
    job = await job_store.save(job_record("job_1", "Daily report"))
    worker = SchedulerWorker(
        job_store=job_store,
        execution_store=execution_store,
        executor=RecordingExecutor(["report complete"]),
        config=SchedulerWorkerConfig(retry_delay_ms=0),
    )

    result = await worker.run_job(tenant_id=job.tenant_id, job_id=job.id, lease_owner="worker_1")

    assert result.status == JobExecutionStatus.SUCCESS
    assert result.result == "report complete"
    assert job_store.jobs[job.id].last_status == JobExecutionStatus.SUCCESS
    assert job_store.jobs[job.id].last_result == "report complete"
    assert execution_store.executions[0].status == JobExecutionStatus.SUCCESS
    assert execution_store.executions[0].dry_run is False
    assert job_store.released == [(job.id, "worker_1", 1)]


async def test_scheduler_worker_dry_run_does_not_update_last_result_or_acquire_lease() -> None:
    job_store = FakeSchedulerStore()
    execution_store = FakeExecutionStore()
    job = await job_store.save(job_record("job_1", "Daily report"))
    worker = SchedulerWorker(
        job_store=job_store,
        execution_store=execution_store,
        executor=RecordingExecutor(["dry ok"]),
        config=SchedulerWorkerConfig(retry_delay_ms=0),
    )

    result = await worker.run_job(
        tenant_id=job.tenant_id,
        job_id=job.id,
        lease_owner="worker_1",
        dry_run=True,
    )

    assert result.status == JobExecutionStatus.SUCCESS
    assert result.dry_run is True
    assert job_store.jobs[job.id].last_status is None
    assert job_store.leases == []
    assert execution_store.executions[0].dry_run is True


async def test_scheduler_worker_skips_when_another_worker_holds_the_lease() -> None:
    job_store = FakeSchedulerStore(lease_available=False)
    execution_store = FakeExecutionStore()
    job = await job_store.save(job_record("job_1", "Daily report"))
    executor = RecordingExecutor(["unused"])
    worker = SchedulerWorker(
        job_store=job_store,
        execution_store=execution_store,
        executor=executor,
        config=SchedulerWorkerConfig(retry_delay_ms=0),
    )

    result = await worker.run_job(tenant_id=job.tenant_id, job_id=job.id, lease_owner="worker_1")

    assert result.status == JobExecutionStatus.SKIPPED
    assert result.result == "skipped: another instance holds lock"
    assert executor.calls == []
    assert job_store.jobs[job.id].last_status is None
    assert execution_store.executions[0].status == JobExecutionStatus.SKIPPED


async def test_scheduler_worker_retries_then_succeeds() -> None:
    job_store = FakeSchedulerStore()
    execution_store = FakeExecutionStore()
    job = await job_store.save(
        replace(job_record("job_1", "Daily report"), retry_on_failure=True, max_retry_count=2)
    )
    executor = RecordingExecutor([RuntimeError("temporary outage"), "recovered"])
    worker = SchedulerWorker(
        job_store=job_store,
        execution_store=execution_store,
        executor=executor,
        config=SchedulerWorkerConfig(retry_delay_ms=0),
    )

    result = await worker.run_job(tenant_id=job.tenant_id, job_id=job.id, lease_owner="worker_1")

    assert result.status == JobExecutionStatus.SUCCESS
    assert result.result == "recovered"
    assert executor.calls == [job.id, job.id]
    assert len(execution_store.executions) == 1


async def test_scheduler_worker_dead_letters_after_retry_exhaustion() -> None:
    job_store = FakeSchedulerStore()
    execution_store = FakeExecutionStore()
    dead_letter_store = FakeDeadLetterStore()
    job = await job_store.save(
        replace(job_record("job_1", "Daily report"), retry_on_failure=True, max_retry_count=2)
    )
    worker = SchedulerWorker(
        job_store=job_store,
        execution_store=execution_store,
        dead_letter_store=dead_letter_store,
        executor=RecordingExecutor(
            [
                RuntimeError("first"),
                RuntimeError("second: private-scheduler-detail"),
            ]
        ),
        config=SchedulerWorkerConfig(retry_delay_ms=0),
    )

    result = await worker.run_job(tenant_id=job.tenant_id, job_id=job.id, lease_owner="worker_1")

    assert result.status == JobExecutionStatus.FAILED
    assert result.result == "Job 'Daily report' failed: scheduled_job_execution_failed"
    assert job_store.jobs[job.id].last_status == JobExecutionStatus.FAILED
    assert (
        job_store.jobs[job.id].last_result
        == "Job 'Daily report' failed: scheduled_job_execution_failed"
    )
    assert execution_store.executions[0].status == JobExecutionStatus.FAILED
    assert (
        execution_store.executions[0].result
        == "Job 'Daily report' failed: scheduled_job_execution_failed"
    )
    assert dead_letter_store.records[0].job_id == job.id
    assert dead_letter_store.records[0].reason == "scheduled_job_execution_failed"
    assert (
        dead_letter_store.records[0].result
        == "Job 'Daily report' failed: scheduled_job_execution_failed"
    )


async def test_scheduler_worker_runs_only_due_enabled_jobs_for_tenant() -> None:
    now = datetime(2026, 6, 27, 9, 1, tzinfo=UTC)
    job_store = FakeSchedulerStore()
    execution_store = FakeExecutionStore()
    due = await job_store.save(
        replace(
            job_record("due", "Due report"),
            cron_expression="0 0 9 * * *",
            last_run_at=datetime(2026, 6, 26, 9, 0, tzinfo=UTC),
        )
    )
    await job_store.save(
        replace(
            job_record("already_ran", "Already ran"),
            cron_expression="0 0 9 * * *",
            last_run_at=datetime(2026, 6, 27, 9, 0, tzinfo=UTC),
        )
    )
    await job_store.save(
        replace(
            job_record("disabled", "Disabled report"),
            cron_expression="0 0 9 * * *",
            enabled=False,
            last_run_at=datetime(2026, 6, 26, 9, 0, tzinfo=UTC),
        )
    )
    worker = SchedulerWorker(
        job_store=job_store,
        execution_store=execution_store,
        executor=RecordingExecutor(["due complete"]),
        config=SchedulerWorkerConfig(retry_delay_ms=0),
    )

    results = await worker.run_due_jobs(
        tenant_id=due.tenant_id,
        lease_owner="worker_1",
        now=now,
    )

    assert [result.job_id for result in results] == ["due"]
    assert job_store.jobs["due"].last_status == JobExecutionStatus.SUCCESS
    assert job_store.jobs["already_ran"].last_status is None
    assert job_store.jobs["disabled"].last_status is None


def job_record(job_id: str, name: str) -> ScheduledJobRecord:
    return ScheduledJobRecord(
        id=job_id,
        tenant_id="tenant_1",
        name=name,
        cron_expression="0 0 9 * * *",
        mcp_server_name="atlas",
        tool_name="search",
    )


class RecordingExecutor(ScheduledJobExecutor):
    def __init__(self, outcomes: list[str | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[str] = []

    async def execute(self, job: ScheduledJobRecord) -> str:
        self.calls.append(job.id)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeSchedulerStore:
    def __init__(self, *, lease_available: bool = True) -> None:
        self.jobs: dict[str, ScheduledJobRecord] = {}
        self.lease_available = lease_available
        self.leases: list[tuple[str, str]] = []
        self.released: list[tuple[str, str, int]] = []

    async def save(self, job: ScheduledJobRecord) -> ScheduledJobRecord:
        self.jobs[job.id] = job
        return job

    async def find_by_id(self, *, tenant_id: str, job_id: str) -> ScheduledJobRecord | None:
        job = self.jobs.get(job_id)
        return job if job is not None and job.tenant_id == tenant_id else None

    async def list(self, *, tenant_id: str) -> list[ScheduledJobRecord]:
        return [job for job in self.jobs.values() if job.tenant_id == tenant_id]

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
        del lease_seconds
        if not self.lease_available:
            return None
        job = await self.find_by_id(tenant_id=tenant_id, job_id=job_id)
        if job is None:
            return None
        self.leases.append((job_id, lease_owner))
        return ScheduledJobLease(
            job_id=job_id,
            tenant_id=tenant_id,
            lease_owner=lease_owner,
            fencing_token=1,
            lease_expires_at=datetime.now(UTC) + timedelta(seconds=30),
        )

    async def release_lease(
        self,
        *,
        tenant_id: str,
        job_id: str,
        lease_owner: str,
        fencing_token: int,
    ) -> bool:
        del tenant_id
        self.released.append((job_id, lease_owner, fencing_token))
        return True


class FakeExecutionStore:
    def __init__(self) -> None:
        self.executions: list[ScheduledJobExecutionRecord] = []

    async def save(self, execution: ScheduledJobExecutionRecord) -> ScheduledJobExecutionRecord:
        self.executions.insert(0, execution)
        return execution

    async def delete_oldest_executions(
        self, *, tenant_id: str, job_id: str, keep_count: int
    ) -> int:
        del tenant_id, job_id, keep_count
        return 0


class FakeDeadLetterStore:
    def __init__(self) -> None:
        self.records: list[ScheduledJobDeadLetterRecord] = []

    async def save(self, dead_letter: ScheduledJobDeadLetterRecord) -> ScheduledJobDeadLetterRecord:
        self.records.append(dead_letter)
        return dead_letter
