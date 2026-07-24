from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from croniter import croniter

from reactor.kernel.ids import new_id

RESULT_TRUNCATION_LIMIT = 5000


def empty_arguments() -> dict[str, Any]:
    return {}


class ScheduledJobType(StrEnum):
    MCP_TOOL = "MCP_TOOL"
    AGENT = "AGENT"
    PROMPT_LAB_AUTO_OPTIMIZE = "PROMPT_LAB_AUTO_OPTIMIZE"


class JobExecutionStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RUNNING = "RUNNING"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class ScheduledJobRecord:
    id: str = field(default_factory=lambda: new_id("scheduled_job"))
    tenant_id: str = "global"
    name: str = ""
    description: str | None = None
    cron_expression: str = ""
    timezone: str = "Asia/Seoul"
    job_type: ScheduledJobType = ScheduledJobType.MCP_TOOL
    mcp_server_name: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = field(default_factory=empty_arguments)
    agent_prompt: str | None = None
    persona_id: str | None = None
    agent_system_prompt: str | None = None
    agent_model: str | None = None
    agent_max_tool_calls: int | None = None
    tags: frozenset[str] = frozenset()
    slack_channel_id: str | None = None
    teams_webhook_url: str | None = None
    retry_on_failure: bool = False
    max_retry_count: int = 3
    execution_timeout_ms: int | None = None
    enabled: bool = True
    last_run_at: datetime | None = None
    last_status: JobExecutionStatus | None = None
    last_result: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not self.name.strip():
            raise ValueError("Job name is required")
        if len(self.name) > 200:
            raise ValueError("Job name must not exceed 200 characters")
        if not self.cron_expression.strip():
            raise ValueError("Cron expression is required")
        if not croniter.is_valid(
            self.cron_expression,
            second_at_beginning=uses_spring_seconds_field(self.cron_expression),
        ):
            raise ValueError("Cron expression is invalid")
        if not self.timezone.strip():
            raise ValueError("timezone is required")
        if self.job_type == ScheduledJobType.MCP_TOOL:
            if not (self.mcp_server_name or "").strip():
                raise ValueError("MCP_TOOL jobs require mcpServerName")
            if not (self.tool_name or "").strip():
                raise ValueError("MCP_TOOL jobs require toolName")
        if self.job_type == ScheduledJobType.AGENT and not (self.agent_prompt or "").strip():
            raise ValueError("AGENT jobs require agentPrompt")
        if self.job_type == ScheduledJobType.PROMPT_LAB_AUTO_OPTIMIZE:
            template_id = str(self.tool_arguments.get("templateId") or "").strip()
            if not template_id:
                raise ValueError("PROMPT_LAB_AUTO_OPTIMIZE jobs require toolArguments.templateId")
        if self.max_retry_count < 0:
            raise ValueError("maxRetryCount must be >= 0")
        if self.execution_timeout_ms is not None and self.execution_timeout_ms < 1000:
            raise ValueError("executionTimeoutMs must be >= 1000")
        if self.agent_max_tool_calls is not None and self.agent_max_tool_calls < 0:
            raise ValueError("agentMaxToolCalls must be >= 0")

    def with_execution_result(
        self,
        *,
        status: JobExecutionStatus,
        result: str | None,
        now: datetime | None = None,
    ) -> ScheduledJobRecord:
        actual_now = now or datetime.now(UTC)
        return replace(
            self,
            last_run_at=actual_now,
            last_status=status,
            last_result=result[:RESULT_TRUNCATION_LIMIT] if result is not None else None,
            updated_at=actual_now,
        )


@dataclass(frozen=True)
class ScheduledJobExecutionRecord:
    id: str = field(default_factory=lambda: new_id("scheduled_job_execution"))
    tenant_id: str = "global"
    job_id: str = ""
    job_name: str = ""
    job_type: ScheduledJobType | None = None
    status: JobExecutionStatus = JobExecutionStatus.RUNNING
    result: str | None = None
    duration_ms: int = 0
    dry_run: bool = False
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


@dataclass(frozen=True)
class ScheduledJobLease:
    job_id: str
    tenant_id: str
    lease_owner: str
    fencing_token: int
    lease_expires_at: datetime


@dataclass(frozen=True)
class ScheduledJobDeadLetterRecord:
    id: str = field(default_factory=lambda: new_id("scheduled_job_dead_letter"))
    tenant_id: str = "global"
    job_id: str = ""
    job_name: str = ""
    job_type: ScheduledJobType | None = None
    reason: str = ""
    result: str | None = None
    dry_run: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def parse_job_type(value: str) -> ScheduledJobType:
    try:
        return ScheduledJobType(value.strip().upper())
    except ValueError as error:
        allowed = ", ".join(item.value for item in ScheduledJobType)
        raise ValueError(f"Invalid jobType '{value}'. Must be one of: {allowed}") from error


def parse_execution_status(value: str | None) -> JobExecutionStatus | None:
    if value is None:
        return None
    return JobExecutionStatus(value)


def serialize_tags(tags: frozenset[str] | set[str]) -> str | None:
    cleaned = sorted(tag.strip() for tag in tags if tag.strip())
    return ",".join(cleaned) if cleaned else None


def parse_tags(value: str | None) -> frozenset[str]:
    if value is None or not value.strip():
        return frozenset()
    return frozenset(tag.strip() for tag in value.split(",") if tag.strip())


def uses_spring_seconds_field(cron_expression: str) -> bool:
    return len(cron_expression.split()) == 6


SCHEDULER_FAILURE_PREFIX = re.compile(r"^Job\s+'[^']+'\s+failed:\s*", re.IGNORECASE)
WHITESPACE_PATTERN = re.compile(r"\s+")


def scheduler_failure_reason(result: str | None) -> str | None:
    value = (result or "").strip()
    if not value or "failed:" not in value.lower():
        return None
    reason = SCHEDULER_FAILURE_PREFIX.sub("", value).strip()
    return reason or None


def scheduler_result_preview(result: str | None, *, max_length: int = 140) -> str | None:
    normalized = WHITESPACE_PATTERN.sub(" ", result or "").strip()
    if not normalized:
        return None
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip() + "…"
