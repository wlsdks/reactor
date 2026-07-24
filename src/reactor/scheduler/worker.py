from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

from reactor.scheduler.service import (
    JobExecutionStatus,
    ScheduledJobDeadLetterRecord,
    ScheduledJobExecutionRecord,
    ScheduledJobLease,
    ScheduledJobRecord,
)

SCHEDULED_JOB_EXECUTION_FAILED = "scheduled_job_execution_failed"


class ScheduledJobExecutor(Protocol):
    async def execute(self, job: ScheduledJobRecord) -> str: ...


class SchedulerJobStore(Protocol):
    async def list(self, *, tenant_id: str) -> list[ScheduledJobRecord]: ...

    async def find_by_id(self, *, tenant_id: str, job_id: str) -> ScheduledJobRecord | None: ...

    async def update_execution_result(
        self,
        *,
        tenant_id: str,
        job_id: str,
        status: JobExecutionStatus,
        result: str | None,
    ) -> ScheduledJobRecord | None: ...

    async def try_acquire_lease(
        self,
        *,
        tenant_id: str,
        job_id: str,
        lease_owner: str,
        lease_seconds: int,
    ) -> ScheduledJobLease | None: ...

    async def release_lease(
        self,
        *,
        tenant_id: str,
        job_id: str,
        lease_owner: str,
        fencing_token: int,
    ) -> bool: ...


class ScheduledJobExecutionStore(Protocol):
    async def save(self, execution: ScheduledJobExecutionRecord) -> ScheduledJobExecutionRecord: ...

    async def delete_oldest_executions(
        self, *, tenant_id: str, job_id: str, keep_count: int
    ) -> int: ...


class ScheduledJobDeadLetterStore(Protocol):
    async def save(
        self, dead_letter: ScheduledJobDeadLetterRecord
    ) -> ScheduledJobDeadLetterRecord: ...


@dataclass(frozen=True)
class SchedulerWorkerConfig:
    default_execution_timeout_ms: int = 300_000
    lease_buffer_ms: int = 10_000
    minimum_lease_ms: int = 5_000
    retry_delay_ms: int = 2_000
    max_executions_per_job: int = 200


class BoundaryScheduledJobExecutor:
    async def execute(self, job: ScheduledJobRecord) -> str:
        return f"Scheduled job '{job.name}' queued for execution"


class SchedulerWorker:
    def __init__(
        self,
        *,
        job_store: SchedulerJobStore,
        execution_store: ScheduledJobExecutionStore,
        executor: ScheduledJobExecutor | None = None,
        dead_letter_store: ScheduledJobDeadLetterStore | None = None,
        config: SchedulerWorkerConfig | None = None,
    ) -> None:
        self._job_store = job_store
        self._execution_store = execution_store
        self._dead_letter_store = dead_letter_store
        self._executor = executor or BoundaryScheduledJobExecutor()
        self._config = config or SchedulerWorkerConfig()

    async def run_due_jobs(
        self,
        *,
        tenant_id: str,
        lease_owner: str,
        now: datetime | None = None,
    ) -> list[ScheduledJobExecutionRecord]:
        actual_now = now or datetime.now(UTC)
        jobs = await self._job_store.list(tenant_id=tenant_id)
        due_jobs = [job for job in jobs if is_job_due(job, now=actual_now)]
        results: list[ScheduledJobExecutionRecord] = []
        for job in due_jobs:
            results.append(
                await self.run_job(
                    tenant_id=tenant_id,
                    job_id=job.id,
                    lease_owner=lease_owner,
                )
            )
        return results

    async def run_job(
        self,
        *,
        tenant_id: str,
        job_id: str,
        lease_owner: str,
        dry_run: bool = False,
    ) -> ScheduledJobExecutionRecord:
        job = await self._job_store.find_by_id(tenant_id=tenant_id, job_id=job_id)
        if job is None:
            return await self._record_missing_job(tenant_id=tenant_id, job_id=job_id)

        lease: ScheduledJobLease | None = None
        if not dry_run:
            lease = await self._job_store.try_acquire_lease(
                tenant_id=tenant_id,
                job_id=job_id,
                lease_owner=lease_owner,
                lease_seconds=self._lease_seconds(job),
            )
            if lease is None:
                return await self._record_skipped(
                    job,
                    "skipped: another instance holds lock",
                    dry_run=False,
                )
            await self._job_store.update_execution_result(
                tenant_id=tenant_id,
                job_id=job_id,
                status=JobExecutionStatus.RUNNING,
                result=None,
            )

        try:
            execution = await self._execute_and_record(job, dry_run=dry_run)
            if not dry_run:
                await self._job_store.update_execution_result(
                    tenant_id=tenant_id,
                    job_id=job_id,
                    status=execution.status,
                    result=execution.result,
                )
            return execution
        finally:
            if lease is not None:
                await self._job_store.release_lease(
                    tenant_id=tenant_id,
                    job_id=job_id,
                    lease_owner=lease_owner,
                    fencing_token=lease.fencing_token,
                )

    async def _execute_and_record(
        self, job: ScheduledJobRecord, *, dry_run: bool
    ) -> ScheduledJobExecutionRecord:
        started_at = datetime.now(UTC)
        started = monotonic()
        try:
            result = await self._run_with_timeout_and_retry(job)
            status = JobExecutionStatus.SUCCESS
        except asyncio.CancelledError:
            raise
        except Exception:
            result = f"Job '{job.name}' failed: {SCHEDULED_JOB_EXECUTION_FAILED}"
            status = JobExecutionStatus.FAILED
            if not dry_run and self._dead_letter_store is not None:
                await self._dead_letter_store.save(
                    ScheduledJobDeadLetterRecord(
                        tenant_id=job.tenant_id,
                        job_id=job.id,
                        job_name=job.name,
                        job_type=job.job_type,
                        reason=SCHEDULED_JOB_EXECUTION_FAILED,
                        result=result,
                        dry_run=dry_run,
                    )
                )
        execution = ScheduledJobExecutionRecord(
            tenant_id=job.tenant_id,
            job_id=job.id,
            job_name=job.name,
            job_type=job.job_type,
            status=status,
            result=result,
            duration_ms=int((monotonic() - started) * 1000),
            dry_run=dry_run,
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
        saved = await self._execution_store.save(execution)
        await self._execution_store.delete_oldest_executions(
            tenant_id=job.tenant_id,
            job_id=job.id,
            keep_count=self._config.max_executions_per_job,
        )
        return saved

    async def _run_with_timeout_and_retry(self, job: ScheduledJobRecord) -> str:
        attempts = max(1, job.max_retry_count) if job.retry_on_failure else 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await asyncio.wait_for(
                    self._executor.execute(job),
                    timeout=self._timeout_seconds(job),
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                last_error = error
                if attempt < attempts and self._config.retry_delay_ms > 0:
                    await asyncio.sleep(self._config.retry_delay_ms / 1000)
        if last_error is not None:
            raise last_error
        raise RuntimeError("scheduled job failed without an error")

    async def _record_skipped(
        self,
        job: ScheduledJobRecord,
        result: str,
        *,
        dry_run: bool,
    ) -> ScheduledJobExecutionRecord:
        now = datetime.now(UTC)
        execution = ScheduledJobExecutionRecord(
            tenant_id=job.tenant_id,
            job_id=job.id,
            job_name=job.name,
            job_type=job.job_type,
            status=JobExecutionStatus.SKIPPED,
            result=result,
            dry_run=dry_run,
            started_at=now,
            completed_at=now,
        )
        return await self._execution_store.save(execution)

    async def _record_missing_job(
        self, *, tenant_id: str, job_id: str
    ) -> ScheduledJobExecutionRecord:
        now = datetime.now(UTC)
        return ScheduledJobExecutionRecord(
            tenant_id=tenant_id,
            job_id=job_id,
            job_name="",
            status=JobExecutionStatus.FAILED,
            result=f"Scheduled job not found: {job_id}",
            started_at=now,
            completed_at=now,
        )

    def _timeout_seconds(self, job: ScheduledJobRecord) -> float:
        timeout_ms = job.execution_timeout_ms or self._config.default_execution_timeout_ms
        return max(timeout_ms, 1_000) / 1000

    def _lease_seconds(self, job: ScheduledJobRecord) -> int:
        timeout_ms = job.execution_timeout_ms or self._config.default_execution_timeout_ms
        lease_ms = max(timeout_ms + self._config.lease_buffer_ms, self._config.minimum_lease_ms)
        return max(1, lease_ms // 1000)


def is_job_due(job: ScheduledJobRecord, *, now: datetime | None = None) -> bool:
    if not job.enabled:
        return False
    actual_now = now or datetime.now(UTC)
    local_now = actual_now.astimezone(job_timezone(job))
    previous_due = croniter(
        job.cron_expression,
        local_now,
        second_at_beginning=uses_spring_seconds_field(job.cron_expression),
    ).get_prev(datetime)
    last_run_at = job.last_run_at
    if last_run_at is None:
        return previous_due <= local_now
    return last_run_at.astimezone(local_now.tzinfo) < previous_due <= local_now


def job_timezone(job: ScheduledJobRecord):
    try:
        return ZoneInfo(job.timezone)
    except ZoneInfoNotFoundError:
        return UTC


def uses_spring_seconds_field(cron_expression: str) -> bool:
    return len(cron_expression.split()) == 6


@dataclass(frozen=True)
class SchedulerRunnerConfig:
    poll_interval_seconds: float = 60.0
    lease_owner: str = "reactor-scheduler"
    tenant_ids: tuple[str, ...] = ("default",)


class SchedulerRunner:
    def __init__(
        self,
        *,
        worker: SchedulerWorker,
        config: SchedulerRunnerConfig,
    ) -> None:
        self._worker = worker
        self._config = config
        self._task: asyncio.Task[None] | None = None
        self.tick_count = 0
        self.last_error: str | None = None

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop())

    async def close(self) -> None:
        task = self._task
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._task = None

    async def run_once(self) -> int:
        executed = 0
        try:
            for tenant_id in self._config.tenant_ids:
                results = await self._worker.run_due_jobs(
                    tenant_id=tenant_id,
                    lease_owner=self._config.lease_owner,
                )
                executed += len(results)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.last_error = f"{error.__class__.__name__}: {error}"
            raise
        self.tick_count += 1
        self.last_error = None
        return executed

    async def _run_loop(self) -> None:
        while True:
            with contextlib.suppress(Exception):
                await self.run_once()
            await asyncio.sleep(self._config.poll_interval_seconds)
