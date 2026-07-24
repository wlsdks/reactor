from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.persistence.models import ScheduledJob, ScheduledJobDeadLetter, ScheduledJobExecution
from reactor.scheduler.service import (
    JobExecutionStatus,
    ScheduledJobDeadLetterRecord,
    ScheduledJobExecutionRecord,
    ScheduledJobLease,
    ScheduledJobRecord,
    ScheduledJobType,
    parse_execution_status,
    parse_tags,
    serialize_tags,
)


class SqlAlchemySchedulerStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(self, *, tenant_id: str) -> list[ScheduledJobRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_scheduled_job_list(tenant_id=tenant_id))
            return [scheduled_job_from_model(row) for row in rows]

    async def find_by_id(self, *, tenant_id: str, job_id: str) -> ScheduledJobRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(ScheduledJob).where(
                    ScheduledJob.tenant_id == tenant_id,
                    ScheduledJob.id == job_id,
                )
            )
            return scheduled_job_from_model(row) if row is not None else None

    async def find_by_name(self, *, tenant_id: str, name: str) -> ScheduledJobRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(ScheduledJob).where(
                    ScheduledJob.tenant_id == tenant_id,
                    ScheduledJob.name == name,
                )
            )
            return scheduled_job_from_model(row) if row is not None else None

    async def save(self, job: ScheduledJobRecord) -> ScheduledJobRecord:
        job.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(build_scheduled_job_upsert(job))
                if row is None:
                    raise RuntimeError("scheduled job upsert did not return a row")
                return scheduled_job_from_model(row)

    async def update(
        self,
        *,
        tenant_id: str,
        job_id: str,
        job: ScheduledJobRecord,
    ) -> ScheduledJobRecord | None:
        job.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    build_scheduled_job_update(tenant_id=tenant_id, job_id=job_id, job=job)
                )
                return scheduled_job_from_model(row) if row is not None else None

    async def delete(self, *, tenant_id: str, job_id: str) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                existing = await session.scalar(
                    select(ScheduledJob.id).where(
                        ScheduledJob.tenant_id == tenant_id,
                        ScheduledJob.id == job_id,
                    )
                )
                if existing is None:
                    return False
                await session.execute(
                    delete(ScheduledJob).where(
                        ScheduledJob.tenant_id == tenant_id,
                        ScheduledJob.id == job_id,
                    )
                )
                return True

    async def update_execution_result(
        self,
        *,
        tenant_id: str,
        job_id: str,
        status: JobExecutionStatus,
        result: str | None,
    ) -> ScheduledJobRecord | None:
        now = datetime.now(UTC)
        statement = (
            update(ScheduledJob)
            .where(ScheduledJob.tenant_id == tenant_id, ScheduledJob.id == job_id)
            .values(
                last_run_at=now,
                last_status=status.value,
                last_result=result[:5000] if result is not None else None,
                updated_at=now,
            )
            .returning(ScheduledJob)
        )
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(statement)
                return scheduled_job_from_model(row) if row is not None else None

    async def try_acquire_lease(
        self,
        *,
        tenant_id: str,
        job_id: str,
        lease_owner: str,
        lease_seconds: int,
    ) -> ScheduledJobLease | None:
        now = datetime.now(UTC)
        lease_expires_at = now + timedelta(seconds=max(1, lease_seconds))
        statement = (
            update(ScheduledJob)
            .where(
                ScheduledJob.tenant_id == tenant_id,
                ScheduledJob.id == job_id,
                or_(
                    ScheduledJob.lease_expires_at.is_(None),
                    ScheduledJob.lease_expires_at < now,
                    and_(
                        ScheduledJob.lease_owner == lease_owner,
                        ScheduledJob.lease_expires_at >= now,
                    ),
                ),
            )
            .values(
                lease_owner=lease_owner,
                lease_expires_at=lease_expires_at,
                fencing_token=ScheduledJob.fencing_token + 1,
                updated_at=now,
            )
            .returning(
                ScheduledJob.id,
                ScheduledJob.tenant_id,
                ScheduledJob.lease_owner,
                ScheduledJob.fencing_token,
                ScheduledJob.lease_expires_at,
            )
        )
        async with self._session_factory() as session:
            async with session.begin():
                row = (await session.execute(statement)).first()
                if row is None:
                    return None
                return ScheduledJobLease(
                    job_id=row.id,
                    tenant_id=row.tenant_id,
                    lease_owner=row.lease_owner,
                    fencing_token=row.fencing_token,
                    lease_expires_at=row.lease_expires_at,
                )

    async def release_lease(
        self,
        *,
        tenant_id: str,
        job_id: str,
        lease_owner: str,
        fencing_token: int,
    ) -> bool:
        statement = (
            update(ScheduledJob)
            .where(
                ScheduledJob.tenant_id == tenant_id,
                ScheduledJob.id == job_id,
                ScheduledJob.lease_owner == lease_owner,
                ScheduledJob.fencing_token == fencing_token,
            )
            .values(
                lease_owner=None,
                lease_expires_at=None,
                updated_at=datetime.now(UTC),
            )
            .returning(ScheduledJob.id)
        )
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.scalar(statement)
                return result == job_id


class SqlAlchemyScheduledJobExecutionStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, execution: ScheduledJobExecutionRecord) -> ScheduledJobExecutionRecord:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(build_execution_insert(execution))
                if row is None:
                    raise RuntimeError("scheduled job execution insert did not return a row")
                return scheduled_execution_from_model(row)

    async def find_by_job_id(
        self, *, tenant_id: str, job_id: str, limit: int = 20
    ) -> list[ScheduledJobExecutionRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(ScheduledJobExecution)
                .where(
                    ScheduledJobExecution.tenant_id == tenant_id,
                    ScheduledJobExecution.job_id == job_id,
                )
                .order_by(ScheduledJobExecution.started_at.desc())
                .limit(max(1, min(limit, 100)))
            )
            return [scheduled_execution_from_model(row) for row in rows]

    async def find_recent(
        self, *, tenant_id: str, limit: int = 50
    ) -> list[ScheduledJobExecutionRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(ScheduledJobExecution)
                .where(ScheduledJobExecution.tenant_id == tenant_id)
                .order_by(ScheduledJobExecution.started_at.desc())
                .limit(max(1, min(limit, 200)))
            )
            return [scheduled_execution_from_model(row) for row in rows]

    async def delete_oldest_executions(
        self, *, tenant_id: str, job_id: str, keep_count: int
    ) -> int:
        async with self._session_factory() as session:
            async with session.begin():
                ids = await session.scalars(
                    select(ScheduledJobExecution.id)
                    .where(
                        ScheduledJobExecution.tenant_id == tenant_id,
                        ScheduledJobExecution.job_id == job_id,
                    )
                    .order_by(ScheduledJobExecution.started_at.desc())
                    .offset(max(0, keep_count))
                )
                to_delete = list(ids)
                if not to_delete:
                    return 0
                await session.execute(
                    delete(ScheduledJobExecution).where(ScheduledJobExecution.id.in_(to_delete))
                )
                return len(to_delete)


class SqlAlchemyScheduledJobDeadLetterStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, dead_letter: ScheduledJobDeadLetterRecord) -> ScheduledJobDeadLetterRecord:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(build_dead_letter_insert(dead_letter))
                if row is None:
                    raise RuntimeError("scheduled job dead letter insert did not return a row")
                return scheduled_dead_letter_from_model(row)

    async def find_by_job_id(
        self, *, tenant_id: str, job_id: str, limit: int = 20
    ) -> list[ScheduledJobDeadLetterRecord]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(ScheduledJobDeadLetter)
                .where(
                    ScheduledJobDeadLetter.tenant_id == tenant_id,
                    ScheduledJobDeadLetter.job_id == job_id,
                )
                .order_by(ScheduledJobDeadLetter.created_at.desc())
                .limit(max(1, min(limit, 100)))
            )
            return [scheduled_dead_letter_from_model(row) for row in rows]


def build_scheduled_job_list(*, tenant_id: str):
    return (
        select(ScheduledJob)
        .where(ScheduledJob.tenant_id == tenant_id)
        .order_by(ScheduledJob.created_at.asc())
    )


def build_scheduled_job_upsert(job: ScheduledJobRecord):
    return (
        insert(ScheduledJob)
        .values(scheduled_job_values(job))
        .on_conflict_do_update(
            index_elements=[ScheduledJob.id],
            set_=scheduled_job_values(job, include_created_at=False),
        )
        .returning(ScheduledJob)
    )


def build_scheduled_job_update(*, tenant_id: str, job_id: str, job: ScheduledJobRecord):
    return (
        update(ScheduledJob)
        .where(ScheduledJob.tenant_id == tenant_id, ScheduledJob.id == job_id)
        .values(scheduled_job_values(job, include_id=False, include_created_at=False))
        .returning(ScheduledJob)
    )


def build_execution_insert(execution: ScheduledJobExecutionRecord):
    return (
        insert(ScheduledJobExecution)
        .values(scheduled_execution_values(execution))
        .returning(ScheduledJobExecution)
    )


def build_dead_letter_insert(dead_letter: ScheduledJobDeadLetterRecord):
    return (
        insert(ScheduledJobDeadLetter)
        .values(scheduled_dead_letter_values(dead_letter))
        .returning(ScheduledJobDeadLetter)
    )


def scheduled_job_values(
    job: ScheduledJobRecord,
    *,
    include_id: bool = True,
    include_created_at: bool = True,
) -> dict[str, object]:
    values: dict[str, object] = {
        "tenant_id": job.tenant_id,
        "name": job.name,
        "description": job.description,
        "cron_expression": job.cron_expression,
        "timezone": job.timezone,
        "job_type": job.job_type.value,
        "mcp_server_name": job.mcp_server_name,
        "tool_name": job.tool_name,
        "tool_arguments": dict(job.tool_arguments),
        "agent_prompt": job.agent_prompt,
        "persona_id": job.persona_id,
        "agent_system_prompt": job.agent_system_prompt,
        "agent_model": job.agent_model,
        "agent_max_tool_calls": job.agent_max_tool_calls,
        "tags": serialize_tags(job.tags),
        "slack_channel_id": job.slack_channel_id,
        "teams_webhook_url": job.teams_webhook_url,
        "retry_on_failure": job.retry_on_failure,
        "max_retry_count": job.max_retry_count,
        "execution_timeout_ms": job.execution_timeout_ms,
        "enabled": job.enabled,
        "last_run_at": job.last_run_at,
        "last_status": job.last_status.value if job.last_status is not None else None,
        "last_result": job.last_result,
        "updated_at": job.updated_at,
    }
    if include_id:
        values["id"] = job.id
    if include_created_at:
        values["created_at"] = job.created_at
    return values


def scheduled_execution_values(execution: ScheduledJobExecutionRecord) -> dict[str, object]:
    return {
        "id": execution.id,
        "tenant_id": execution.tenant_id,
        "job_id": execution.job_id,
        "job_name": execution.job_name,
        "job_type": execution.job_type.value if execution.job_type is not None else None,
        "status": execution.status.value,
        "result": execution.result,
        "duration_ms": execution.duration_ms,
        "dry_run": execution.dry_run,
        "started_at": execution.started_at,
        "completed_at": execution.completed_at,
    }


def scheduled_dead_letter_values(dead_letter: ScheduledJobDeadLetterRecord) -> dict[str, object]:
    return {
        "id": dead_letter.id,
        "tenant_id": dead_letter.tenant_id,
        "job_id": dead_letter.job_id,
        "job_name": dead_letter.job_name,
        "job_type": dead_letter.job_type.value if dead_letter.job_type is not None else None,
        "reason": dead_letter.reason,
        "result": dead_letter.result,
        "dry_run": dead_letter.dry_run,
        "created_at": dead_letter.created_at,
    }


def scheduled_job_from_model(row: ScheduledJob) -> ScheduledJobRecord:
    record = ScheduledJobRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        description=row.description,
        cron_expression=row.cron_expression,
        timezone=row.timezone,
        job_type=ScheduledJobType(row.job_type),
        mcp_server_name=row.mcp_server_name,
        tool_name=row.tool_name,
        tool_arguments=dict(row.tool_arguments),
        agent_prompt=row.agent_prompt,
        persona_id=row.persona_id,
        agent_system_prompt=row.agent_system_prompt,
        agent_model=row.agent_model,
        agent_max_tool_calls=row.agent_max_tool_calls,
        tags=parse_tags(row.tags),
        slack_channel_id=row.slack_channel_id,
        teams_webhook_url=row.teams_webhook_url,
        retry_on_failure=row.retry_on_failure,
        max_retry_count=row.max_retry_count,
        execution_timeout_ms=row.execution_timeout_ms,
        enabled=row.enabled,
        last_run_at=row.last_run_at,
        last_status=parse_execution_status(row.last_status),
        last_result=row.last_result,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    record.validate()
    return record


def scheduled_execution_from_model(row: ScheduledJobExecution) -> ScheduledJobExecutionRecord:
    return ScheduledJobExecutionRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        job_id=row.job_id,
        job_name=row.job_name,
        job_type=ScheduledJobType(row.job_type) if row.job_type is not None else None,
        status=JobExecutionStatus(row.status),
        result=row.result,
        duration_ms=row.duration_ms,
        dry_run=row.dry_run,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def scheduled_dead_letter_from_model(
    row: ScheduledJobDeadLetter,
) -> ScheduledJobDeadLetterRecord:
    return ScheduledJobDeadLetterRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        job_id=row.job_id,
        job_name=row.job_name,
        job_type=ScheduledJobType(row.job_type) if row.job_type is not None else None,
        reason=row.reason,
        result=row.result,
        dry_run=row.dry_run,
        created_at=row.created_at,
    )
