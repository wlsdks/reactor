from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from reactor.persistence.models import Base, ScheduledJob
from reactor.persistence.scheduler_store import (
    build_dead_letter_insert,
    build_execution_insert,
    build_scheduled_job_list,
    build_scheduled_job_update,
    build_scheduled_job_upsert,
    scheduled_job_from_model,
)
from reactor.scheduler.service import (
    JobExecutionStatus,
    ScheduledJobDeadLetterRecord,
    ScheduledJobExecutionRecord,
    ScheduledJobRecord,
    ScheduledJobType,
    parse_job_type,
    parse_tags,
    scheduler_failure_reason,
    scheduler_result_preview,
    serialize_tags,
)


def test_scheduler_models_are_registered_in_metadata() -> None:
    assert "scheduled_jobs" in Base.metadata.tables
    assert "scheduled_job_executions" in Base.metadata.tables
    assert "scheduled_job_dead_letters" in Base.metadata.tables
    job_constraints = Base.metadata.tables["scheduled_jobs"].constraints
    execution_constraints = Base.metadata.tables["scheduled_job_executions"].constraints
    job_indexes = Base.metadata.tables["scheduled_jobs"].indexes

    assert "ck_scheduled_jobs_type" in {constraint.name for constraint in job_constraints}
    assert "ck_scheduled_jobs_last_status" in {constraint.name for constraint in job_constraints}
    assert "uq_scheduled_jobs_name" in {constraint.name for constraint in job_constraints}
    assert "ix_scheduled_jobs_lease" in {index.name for index in job_indexes}
    assert "ck_scheduled_job_executions_status" in {
        constraint.name for constraint in execution_constraints
    }


def test_scheduler_store_queries_are_tenant_scoped() -> None:
    job = ScheduledJobRecord(
        id="job_1",
        tenant_id="tenant_1",
        name="Daily report",
        cron_expression="0 0 9 * * *",
        mcp_server_name="atlas",
        tool_name="report",
    )
    execution = ScheduledJobExecutionRecord(
        id="exec_1",
        tenant_id="tenant_1",
        job_id="job_1",
        job_name="Daily report",
        job_type=ScheduledJobType.MCP_TOOL,
        status=JobExecutionStatus.SUCCESS,
    )
    dead_letter = ScheduledJobDeadLetterRecord(
        id="dead_1",
        tenant_id="tenant_1",
        job_id="job_1",
        job_name="Daily report",
        job_type=ScheduledJobType.MCP_TOOL,
        reason="tool timeout",
        result="Job 'Daily report' failed: tool timeout",
    )

    upsert = str(build_scheduled_job_upsert(job).compile(dialect=postgresql.dialect()))
    update = build_scheduled_job_update(tenant_id="tenant_1", job_id="job_1", job=job).compile(
        dialect=postgresql.dialect()
    )
    listed = build_scheduled_job_list(tenant_id="tenant_1").compile(dialect=postgresql.dialect())
    insert_execution = str(build_execution_insert(execution).compile(dialect=postgresql.dialect()))
    insert_dead_letter = str(
        build_dead_letter_insert(dead_letter).compile(dialect=postgresql.dialect())
    )

    assert "scheduled_jobs" in upsert
    assert "ON CONFLICT" in upsert
    assert "scheduled_jobs.tenant_id" in str(update)
    assert update.params["tenant_id_1"] == "tenant_1"
    assert listed.params["tenant_id_1"] == "tenant_1"
    assert "scheduled_job_executions" in insert_execution
    assert "scheduled_job_dead_letters" in insert_dead_letter


def test_scheduler_domain_validation_requires_type_specific_fields() -> None:
    mcp = ScheduledJobRecord(
        name="MCP",
        cron_expression="0 0 9 * * *",
        mcp_server_name="atlas",
        tool_name="search",
    )
    agent = ScheduledJobRecord(
        name="Agent",
        cron_expression="0 0 9 * * *",
        job_type=ScheduledJobType.AGENT,
        agent_prompt="summarize release risk",
    )
    prompt_lab = ScheduledJobRecord(
        name="PromptLab",
        cron_expression="0 0 9 * * *",
        job_type=ScheduledJobType.PROMPT_LAB_AUTO_OPTIMIZE,
        tool_arguments={"templateId": "tmpl-1"},
    )

    mcp.validate()
    agent.validate()
    prompt_lab.validate()
    assert parse_job_type("agent") == ScheduledJobType.AGENT
    assert parse_job_type("prompt_lab_auto_optimize") == ScheduledJobType.PROMPT_LAB_AUTO_OPTIMIZE


def test_scheduled_job_from_model_rejects_invalid_persisted_cron() -> None:
    row = ScheduledJob(
        id="job_bad",
        tenant_id="tenant_1",
        name="Bad persisted cron",
        job_type=ScheduledJobType.MCP_TOOL.value,
        cron_expression="not a cron",
        timezone="Asia/Seoul",
        mcp_server_name="atlas",
        tool_name="search",
        tool_arguments={},
        tags="",
        retry_on_failure=False,
        max_retry_count=3,
        enabled=True,
        fencing_token=0,
        created_at=datetime(2026, 6, 28, tzinfo=UTC),
        updated_at=datetime(2026, 6, 28, tzinfo=UTC),
    )

    try:
        scheduled_job_from_model(row)
    except ValueError as error:
        assert "Cron expression is invalid" in str(error)
    else:  # pragma: no cover - exercised only if validation regresses
        raise AssertionError("invalid persisted cron must fail closed")


def test_scheduler_helpers_match_legacy_preview_and_failure_reason() -> None:
    assert (
        scheduler_failure_reason(
            "Job 'Release digest' failed: MCP server 'atlassian' is not connected"
        )
        == "MCP server 'atlassian' is not connected"
    )
    assert scheduler_failure_reason("Release digest completed successfully") is None
    assert scheduler_result_preview("alpha\nbeta\tgamma", max_length=12) == "alpha beta…"
    assert serialize_tags(frozenset({"weekly", "daily"})) == "daily,weekly"
    assert parse_tags("daily, weekly") == frozenset({"daily", "weekly"})
