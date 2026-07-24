from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScheduledJobRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    cron_expression: str = Field(alias="cronExpression", min_length=1)
    timezone: str = "Asia/Seoul"
    job_type: str = Field(default="MCP_TOOL", alias="jobType")
    mcp_server_name: str | None = Field(default=None, alias="mcpServerName")
    tool_name: str | None = Field(default=None, alias="toolName")
    tool_arguments: dict[str, Any] = Field(default_factory=dict, alias="toolArguments")
    agent_prompt: str | None = Field(default=None, alias="agentPrompt")
    persona_id: str | None = Field(default=None, alias="personaId")
    agent_system_prompt: str | None = Field(default=None, alias="agentSystemPrompt")
    agent_model: str | None = Field(default=None, alias="agentModel")
    agent_max_tool_calls: int | None = Field(default=None, alias="agentMaxToolCalls", ge=0)
    tags: set[str] = Field(default_factory=set)
    slack_channel_id: str | None = Field(default=None, alias="slackChannelId")
    teams_webhook_url: str | None = Field(default=None, alias="teamsWebhookUrl")
    retry_on_failure: bool = Field(default=False, alias="retryOnFailure")
    max_retry_count: int = Field(default=3, alias="maxRetryCount", ge=0)
    execution_timeout_ms: int | None = Field(default=None, alias="executionTimeoutMs", ge=1000)
    enabled: bool = True


class ScheduledJobResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    description: str | None
    cron_expression: str = Field(alias="cronExpression")
    timezone: str
    job_type: str = Field(alias="jobType")
    mcp_server_name: str | None = Field(alias="mcpServerName")
    tool_name: str | None = Field(alias="toolName")
    tool_arguments: dict[str, Any] = Field(alias="toolArguments")
    agent_prompt: str | None = Field(alias="agentPrompt")
    persona_id: str | None = Field(alias="personaId")
    agent_system_prompt: str | None = Field(alias="agentSystemPrompt")
    agent_model: str | None = Field(alias="agentModel")
    agent_max_tool_calls: int | None = Field(alias="agentMaxToolCalls")
    tags: set[str]
    slack_channel_id: str | None = Field(alias="slackChannelId")
    teams_webhook_url: str | None = Field(alias="teamsWebhookUrl")
    retry_on_failure: bool = Field(alias="retryOnFailure")
    max_retry_count: int = Field(alias="maxRetryCount")
    execution_timeout_ms: int | None = Field(alias="executionTimeoutMs")
    enabled: bool
    last_run_at: int | None = Field(alias="lastRunAt")
    last_status: str | None = Field(alias="lastStatus")
    last_result: str | None = Field(alias="lastResult")
    last_result_preview: str | None = Field(alias="lastResultPreview")
    last_failure_reason: str | None = Field(alias="lastFailureReason")
    created_at: int = Field(alias="createdAt")
    updated_at: int = Field(alias="updatedAt")


class ScheduledJobExecutionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    job_id: str = Field(alias="jobId")
    job_name: str = Field(alias="jobName")
    status: str
    result: str | None
    result_preview: str | None = Field(alias="resultPreview")
    failure_reason: str | None = Field(alias="failureReason")
    duration_ms: int = Field(alias="durationMs")
    dry_run: bool = Field(alias="dryRun")
    started_at: int = Field(alias="startedAt")
    completed_at: int | None = Field(alias="completedAt")


class PaginatedScheduledJobsResponse(BaseModel):
    items: list[ScheduledJobResponse]
    total: int
    offset: int
    limit: int


class PaginatedScheduledExecutionsResponse(BaseModel):
    items: list[ScheduledJobExecutionResponse]
    total: int
    offset: int
    limit: int


class SchedulerTriggerResponse(BaseModel):
    result: str
    dry_run: bool | None = Field(default=None, alias="dryRun")
