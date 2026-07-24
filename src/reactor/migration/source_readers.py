from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from reactor.mcp.security_policy import (
    MCP_SECURITY_CATEGORY,
    MCP_SECURITY_DESCRIPTION,
    MCP_SECURITY_POLICY_SETTING_KEY,
    normalize_allowed_server_names,
)
from reactor.migration.export import LegacyRow
from reactor.persistence.models import (
    A2AAccessPolicy,
    A2AAgentCard,
    A2APeerAgent,
    A2APushSubscription,
    A2ATask,
    A2ATaskEvent,
    AdminAudit,
    AgentEvalCase,
    AgentEvalResult,
    AgentRun,
    AgentRunEvent,
    AgentSpecRow,
    AlertInstanceRow,
    AlertRuleRow,
    AuthTokenRevocation,
    AuthUser,
    ChannelFaqRegistration,
    DeadLetterJob,
    FeedbackRecord,
    IdempotencyRecord,
    InboxEvent,
    InputGuardRule,
    IntentDefinitionModel,
    McpAccessPolicy,
    McpServer,
    McpServerStatus,
    McpToolSnapshot,
    MemoryEmbedding,
    MemoryItem,
    MemoryNamespace,
    MemoryProposal,
    MetricGuardEvent,
    ModelPricing,
    OutboxEvent,
    OutputGuardRule,
    OutputGuardRuleAudit,
    PendingApproval,
    PersonaRow,
    PromptLabExperiment,
    PromptLabReport,
    PromptLabTrial,
    PromptRelease,
    PromptTemplate,
    PromptVersion,
    RagChunk,
    RagDocument,
    RagIngestionCandidateRow,
    RagSource,
    RunQueue,
    RuntimeSetting,
    ScheduledJob,
    ScheduledJobDeadLetter,
    ScheduledJobExecution,
    SlackBotInstance,
    SlackProactiveChannel,
    Tenant,
    ToolCatalog,
    ToolInvocation,
    UsageLedger,
    UserIdentity,
)
from reactor.rag.ingestion_policy import (
    RAG_INGESTION_POLICY_SETTING_KEY,
    RagIngestionPolicy,
    normalize_policy,
    policy_to_payload,
)
from reactor.scheduler.service import parse_tags
from reactor.tools.policy import (
    TOOL_POLICY_SETTING_KEY,
    DynamicToolPolicy,
    normalize_values,
    tool_policy_to_json,
)


def agent_run_legacy_row(row: AgentRun) -> LegacyRow:
    return LegacyRow(
        source_table="agent_runs",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "user_id": row.user_id,
            "thread_id": row.thread_id,
            "checkpoint_ns": row.checkpoint_ns,
            "status": row.status,
            "input_text": row.input_text,
            "response_text": row.response_text,
            "error_code": row.error_code,
            "metadata": dict(row.run_metadata),
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def agent_run_event_legacy_row(row: AgentRunEvent) -> LegacyRow:
    return LegacyRow(
        source_table="agent_run_events",
        source_pk=f"{row.tenant_id}:{row.run_id}:{row.sequence}:{row.id}",
        payload={
            "id": row.id,
            "run_id": row.run_id,
            "tenant_id": row.tenant_id,
            "sequence": row.sequence,
            "event_type": row.event_type,
            "payload": dict(row.payload),
            "created_at": isoformat(row.created_at),
        },
    )


def legacy_conversation_message_rows(row: Mapping[str, Any], *, tenant_id: str) -> list[LegacyRow]:
    session_id = required_legacy_identity_text(row, "session_id")
    user_id = optional_legacy_identity_text(row, "user_id") or "anonymous"
    message_id = optional_legacy_int(row, "id", default=None)
    timestamp_ms = optional_legacy_int(row, "timestamp", default=0) or 0
    sequence = message_id if message_id is not None else max(1, timestamp_ms)
    created_at = legacy_identity_timestamp(row, "created_at")
    run_id = legacy_conversation_run_id(tenant_id, session_id)
    return [
        LegacyRow(
            source_table="agent_runs",
            source_pk=f"legacy_conversation:{tenant_id}:{session_id}",
            payload={
                "id": run_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "thread_id": session_id,
                "checkpoint_ns": "legacy-conversation",
                "status": "completed",
                "input_text": f"Legacy conversation session {session_id}",
                "response_text": None,
                "error_code": None,
                "metadata": {
                    "source": "spring_conversation_messages",
                    "legacy_session_id": session_id,
                },
                "created_at": created_at,
                "updated_at": created_at,
            },
        ),
        LegacyRow(
            source_table="agent_run_events",
            source_pk=f"legacy_conversation_message:{tenant_id}:{session_id}:{sequence}",
            payload={
                "id": None,
                "run_id": run_id,
                "tenant_id": tenant_id,
                "sequence": sequence,
                "event_type": "legacy.conversation.message",
                "payload": {
                    "role": required_legacy_identity_text(row, "role"),
                    "content": required_legacy_identity_text(row, "content"),
                    "legacy_message_id": message_id,
                    "legacy_session_id": session_id,
                    "user_id": user_id,
                    "timestamp_ms": timestamp_ms,
                },
                "created_at": created_at,
            },
        ),
    ]


def legacy_conversation_summary_rows(row: Mapping[str, Any], *, tenant_id: str) -> list[LegacyRow]:
    session_id = required_legacy_identity_text(row, "session_id")
    narrative = required_legacy_identity_text(row, "narrative")
    summarized_up_to = optional_legacy_int(row, "summarized_up_to", default=0) or 0
    created_at = legacy_identity_timestamp(row, "created_at")
    updated_at = legacy_identity_timestamp(row, "updated_at")
    run_id = legacy_conversation_summary_run_id(tenant_id, session_id)
    return [
        LegacyRow(
            source_table="agent_runs",
            source_pk=f"legacy_conversation_summary:{tenant_id}:{session_id}",
            payload={
                "id": run_id,
                "tenant_id": tenant_id,
                "user_id": "anonymous",
                "thread_id": session_id,
                "checkpoint_ns": "legacy-conversation-summary",
                "status": "completed",
                "input_text": f"Legacy conversation summary session {session_id}",
                "response_text": narrative,
                "error_code": None,
                "metadata": {
                    "source": "spring_conversation_summaries",
                    "legacy_session_id": session_id,
                    "summarized_up_to": summarized_up_to,
                },
                "created_at": created_at,
                "updated_at": updated_at,
            },
        ),
        LegacyRow(
            source_table="agent_run_events",
            source_pk=f"legacy_conversation_summary:{tenant_id}:{session_id}:event",
            payload={
                "id": None,
                "run_id": run_id,
                "tenant_id": tenant_id,
                "sequence": 1,
                "event_type": "legacy.conversation.summary",
                "payload": {
                    "legacy_session_id": session_id,
                    "narrative": narrative,
                    "facts": legacy_summary_facts(row),
                    "summarized_up_to": summarized_up_to,
                },
                "created_at": updated_at,
            },
        ),
    ]


def run_queue_legacy_row(row: RunQueue) -> LegacyRow:
    return LegacyRow(
        source_table="run_queue",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "run_id": row.run_id,
            "tenant_id": row.tenant_id,
            "status": row.status,
            "priority": row.priority,
            "attempt": row.attempt,
            "max_attempts": row.max_attempts,
            "available_at": isoformat(row.available_at),
            "lease_owner": row.lease_owner,
            "lease_expires_at": optional_isoformat(row.lease_expires_at),
            "fencing_token": row.fencing_token,
            "payload": dict(row.payload),
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def dead_letter_job_legacy_row(row: DeadLetterJob) -> LegacyRow:
    return LegacyRow(
        source_table="dead_letter_jobs",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "queue_id": row.queue_id,
            "run_id": row.run_id,
            "tenant_id": row.tenant_id,
            "reason": row.reason,
            "last_checkpoint_id": row.last_checkpoint_id,
            "trace_id": row.trace_id,
            "payload": dict(row.payload),
            "created_at": isoformat(row.created_at),
        },
    )


def idempotency_record_legacy_row(row: IdempotencyRecord) -> LegacyRow:
    return LegacyRow(
        source_table="idempotency_records",
        source_pk=f"{row.tenant_id}:{row.scope}:{row.key}",
        payload={
            "key": row.key,
            "tenant_id": row.tenant_id,
            "scope": row.scope,
            "request_checksum": row.request_checksum,
            "status": row.status,
            "response_payload": dict(row.response_payload) if row.response_payload else None,
            "locked_until": optional_isoformat(row.locked_until),
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def outbox_event_legacy_row(row: OutboxEvent) -> LegacyRow:
    return LegacyRow(
        source_table="outbox_events",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "run_id": row.run_id,
            "destination": row.destination,
            "event_type": row.event_type,
            "idempotency_key": row.idempotency_key,
            "status": row.status,
            "attempt": row.attempt,
            "max_attempts": row.max_attempts,
            "available_at": isoformat(row.available_at),
            "payload": dict(row.payload),
            "last_error": row.last_error,
            "lease_owner": row.lease_owner,
            "lease_expires_at": optional_isoformat(row.lease_expires_at),
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def inbox_event_legacy_row(row: InboxEvent) -> LegacyRow:
    return LegacyRow(
        source_table="inbox_events",
        source_pk=f"{row.tenant_id}:{row.source}:{row.source_event_id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "source": row.source,
            "source_event_id": row.source_event_id,
            "event_type": row.event_type,
            "status": row.status,
            "payload": dict(row.payload),
            "received_at": isoformat(row.received_at),
            "processed_at": optional_isoformat(row.processed_at),
        },
    )


def runtime_setting_legacy_row(row: RuntimeSetting) -> LegacyRow:
    return LegacyRow(
        source_table="runtime_settings",
        source_pk=f"{row.tenant_id}:{row.key}",
        payload={
            "tenant_id": row.tenant_id,
            "key": row.key,
            "value": row.value,
            "value_type": row.value_type,
            "category": row.category,
            "description": row.description,
            "updated_by": row.updated_by,
            "metadata": dict(row.setting_metadata),
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def legacy_tool_policy_row(row: Mapping[str, Any], *, tenant_id: str) -> LegacyRow:
    created_at = legacy_datetime(row, "created_at")
    updated_at = legacy_datetime(row, "updated_at")
    policy = DynamicToolPolicy(
        enabled=optional_legacy_bool(row, "enabled", default=False),
        write_tool_names=normalize_values(legacy_text_sequence(row, "write_tool_names")),
        deny_write_channels=normalize_values(
            legacy_text_sequence(row, "deny_write_channels"),
            lowercase=True,
        ),
        allow_write_tool_names_in_deny_channels=normalize_values(
            legacy_text_sequence(row, "allow_write_tool_names_in_deny_channels")
        ),
        allow_write_tool_names_by_channel=legacy_text_sequence_mapping(
            row,
            "allow_write_tool_names_by_channel",
        ),
        deny_write_message=optional_legacy_identity_text(row, "deny_write_message")
        or "Error: This tool is not allowed in this channel",
        created_at=created_at,
        updated_at=updated_at,
    )
    legacy_id = optional_legacy_identity_text(row, "id") or "default"
    return LegacyRow(
        source_table="runtime_settings",
        source_pk=f"{tenant_id}:{TOOL_POLICY_SETTING_KEY}",
        payload={
            "tenant_id": tenant_id,
            "key": TOOL_POLICY_SETTING_KEY,
            "value": tool_policy_to_json(policy),
            "value_type": "JSON",
            "category": "tools",
            "description": "Dynamic tool execution policy",
            "updated_by": "migration",
            "metadata": {
                "source": "spring_tool_policy",
                "legacy_id": legacy_id,
            },
            "created_at": isoformat(created_at),
            "updated_at": isoformat(updated_at),
        },
    )


def legacy_mcp_security_policy_row(row: Mapping[str, Any]) -> LegacyRow:
    created_at = legacy_datetime(row, "created_at")
    updated_at = legacy_datetime(row, "updated_at")
    allowed_server_names = sorted(
        normalize_allowed_server_names(legacy_text_sequence(row, "allowed_server_names"))
    )
    max_tool_output_length = optional_legacy_int(
        row,
        "max_tool_output_length",
        default=50_000,
    )
    legacy_id = optional_legacy_identity_text(row, "id") or "default"
    return LegacyRow(
        source_table="runtime_settings",
        source_pk=f"global:{MCP_SECURITY_POLICY_SETTING_KEY}",
        payload={
            "tenant_id": "global",
            "key": MCP_SECURITY_POLICY_SETTING_KEY,
            "value": json.dumps(
                {
                    "allowedServerNames": allowed_server_names,
                    "maxToolOutputLength": max_tool_output_length or 50_000,
                },
                separators=(",", ":"),
            ),
            "value_type": "JSON",
            "category": MCP_SECURITY_CATEGORY,
            "description": MCP_SECURITY_DESCRIPTION,
            "updated_by": "migration",
            "metadata": {
                "source": "spring_mcp_security_policy",
                "legacy_id": legacy_id,
            },
            "created_at": isoformat(created_at),
            "updated_at": isoformat(updated_at),
        },
    )


def legacy_rag_ingestion_policy_row(row: Mapping[str, Any]) -> LegacyRow:
    created_at = legacy_datetime(row, "created_at")
    updated_at = legacy_datetime(row, "updated_at")
    policy = normalize_policy(
        RagIngestionPolicy(
            enabled=optional_legacy_bool(row, "enabled", default=False),
            require_review=optional_legacy_bool(row, "require_review", default=True),
            allowed_channels=tuple(legacy_text_sequence(row, "allowed_channels")),
            min_query_chars=optional_legacy_int(row, "min_query_chars", default=10) or 10,
            min_response_chars=optional_legacy_int(
                row,
                "min_response_chars",
                default=20,
            )
            or 20,
            blocked_patterns=tuple(legacy_text_sequence(row, "blocked_patterns")),
            created_at=created_at,
            updated_at=updated_at,
        )
    )
    legacy_id = optional_legacy_identity_text(row, "id") or "default"
    return LegacyRow(
        source_table="runtime_settings",
        source_pk=f"global:{RAG_INGESTION_POLICY_SETTING_KEY}",
        payload={
            "tenant_id": "global",
            "key": RAG_INGESTION_POLICY_SETTING_KEY,
            "value": json.dumps(policy_to_payload(policy), ensure_ascii=False),
            "value_type": "JSON",
            "category": "rag",
            "description": "Dynamic RAG ingestion capture policy",
            "updated_by": "migration",
            "metadata": {
                "source": "spring_rag_ingestion_policy",
                "legacy_id": legacy_id,
            },
            "created_at": isoformat(created_at),
            "updated_at": isoformat(updated_at),
        },
    )


def prompt_template_legacy_row(row: PromptTemplate) -> LegacyRow:
    return LegacyRow(
        source_table="prompt_templates",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "name": row.name,
            "graph_profile": row.graph_profile,
            "description": row.description,
            "created_by": row.created_by,
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def prompt_version_legacy_row(row: PromptVersion) -> LegacyRow:
    return LegacyRow(
        source_table="prompt_versions",
        source_pk=f"{row.tenant_id}:{row.template_id}:{row.id}",
        payload={
            "id": row.id,
            "template_id": row.template_id,
            "tenant_id": row.tenant_id,
            "version": row.version,
            "system_policy": row.system_policy,
            "developer_policy": row.developer_policy,
            "examples": list(row.examples),
            "metadata": dict(row.prompt_metadata),
            "content_hash": row.content_hash,
            "created_by": row.created_by,
            "created_at": isoformat(row.created_at),
        },
    )


def prompt_release_legacy_row(row: PromptRelease) -> LegacyRow:
    return LegacyRow(
        source_table="prompt_releases",
        source_pk=f"{row.tenant_id}:{row.template_id}:{row.environment}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "template_id": row.template_id,
            "version_id": row.version_id,
            "environment": row.environment,
            "released_by": row.released_by,
            "released_at": isoformat(row.released_at),
            "metadata": dict(row.release_metadata),
        },
    )


def persona_legacy_row(row: PersonaRow) -> LegacyRow:
    return LegacyRow(
        source_table="personas",
        source_pk=row.id,
        payload={
            "id": row.id,
            "name": row.name,
            "system_prompt": row.system_prompt,
            "is_default": row.is_default,
            "description": row.description,
            "response_guideline": row.response_guideline,
            "welcome_message": row.welcome_message,
            "icon": row.icon,
            "is_active": row.is_active,
            "prompt_template_id": row.prompt_template_id,
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def agent_spec_legacy_row(row: AgentSpecRow) -> LegacyRow:
    return LegacyRow(
        source_table="agent_specs",
        source_pk=row.id,
        payload={
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "tool_names": list(row.tool_names),
            "keywords": list(row.keywords),
            "system_prompt": row.system_prompt,
            "mode": row.mode,
            "independent_execution": row.independent_execution,
            "enabled": row.enabled,
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def intent_definition_legacy_row(row: IntentDefinitionModel) -> LegacyRow:
    return LegacyRow(
        source_table="intent_definitions",
        source_pk=row.name,
        payload={
            "name": row.name,
            "description": row.description,
            "examples": list(row.examples),
            "keywords": list(row.keywords),
            "profile": row.profile,
            "enabled": row.enabled,
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def prompt_lab_experiment_legacy_row(row: PromptLabExperiment) -> LegacyRow:
    return LegacyRow(
        source_table="prompt_lab_experiments",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "name": row.name,
            "description": row.description,
            "template_id": row.template_id,
            "baseline_version_id": row.baseline_version_id,
            "candidate_version_ids": list(row.candidate_version_ids),
            "test_queries": list(row.test_queries),
            "evaluation_config": dict(row.evaluation_config),
            "model": row.model,
            "judge_model": row.judge_model,
            "temperature": row.temperature,
            "repetitions": row.repetitions,
            "auto_generated": row.auto_generated,
            "status": row.status,
            "created_by": row.created_by,
            "created_at": isoformat(row.created_at),
            "started_at": optional_isoformat(row.started_at),
            "completed_at": optional_isoformat(row.completed_at),
            "error_message": row.error_message,
        },
    )


def prompt_lab_trial_legacy_row(row: PromptLabTrial) -> LegacyRow:
    return LegacyRow(
        source_table="prompt_lab_trials",
        source_pk=f"{row.tenant_id}:{row.experiment_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "experiment_id": row.experiment_id,
            "prompt_version_id": row.prompt_version_id,
            "prompt_version_number": row.prompt_version_number,
            "test_query": dict(row.test_query),
            "repetition_index": row.repetition_index,
            "response": row.response,
            "success": row.success,
            "error_message": row.error_message,
            "tools_used": list(row.tools_used),
            "token_usage": dict(row.token_usage) if row.token_usage is not None else None,
            "duration_ms": row.duration_ms,
            "evaluations": list(row.evaluations),
            "executed_at": isoformat(row.executed_at),
        },
    )


def prompt_lab_report_legacy_row(row: PromptLabReport) -> LegacyRow:
    return LegacyRow(
        source_table="prompt_lab_reports",
        source_pk=f"{row.tenant_id}:{row.experiment_id}",
        payload={
            "experiment_id": row.experiment_id,
            "tenant_id": row.tenant_id,
            "experiment_name": row.experiment_name,
            "generated_at": isoformat(row.generated_at),
            "total_trials": row.total_trials,
            "version_summaries": list(row.version_summaries),
            "recommendation": dict(row.recommendation),
        },
    )


def slack_bot_legacy_row(row: SlackBotInstance) -> LegacyRow:
    return LegacyRow(
        source_table="slack_bot_instances",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "name": row.name,
            "bot_token": row.bot_token,
            "app_token": row.app_token,
            "persona_id": row.persona_id,
            "default_channel": row.default_channel,
            "enabled": row.enabled,
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def legacy_slack_bot_instance_row(row: Mapping[str, Any], *, tenant_id: str) -> LegacyRow:
    bot_id = required_legacy_identity_text(row, "id")
    return LegacyRow(
        source_table="slack_bot_instances",
        source_pk=f"{tenant_id}:{bot_id}",
        payload={
            "id": bot_id,
            "tenant_id": tenant_id,
            "name": required_legacy_identity_text(row, "name"),
            "bot_token": required_legacy_identity_text(row, "bot_token"),
            "app_token": required_legacy_identity_text(row, "app_token"),
            "persona_id": required_legacy_identity_text(row, "persona_id"),
            "default_channel": optional_legacy_identity_text(row, "default_channel"),
            "enabled": optional_legacy_bool(row, "enabled", default=True),
            "created_at": legacy_identity_timestamp(row, "created_at"),
            "updated_at": legacy_identity_timestamp(row, "updated_at"),
        },
    )


def proactive_channel_legacy_row(row: SlackProactiveChannel) -> LegacyRow:
    return LegacyRow(
        source_table="slack_proactive_channels",
        source_pk=f"{row.tenant_id}:{row.channel_id}",
        payload={
            "tenant_id": row.tenant_id,
            "channel_id": row.channel_id,
            "channel_name": row.channel_name,
            "added_at": isoformat(row.added_at),
        },
    )


def faq_registration_legacy_row(row: ChannelFaqRegistration) -> LegacyRow:
    return LegacyRow(
        source_table="channel_faq_registrations",
        source_pk=f"{row.tenant_id}:{row.channel_id}",
        payload={
            "tenant_id": row.tenant_id,
            "channel_id": row.channel_id,
            "channel_name": row.channel_name,
            "enabled": row.enabled,
            "auto_reply_mode": row.auto_reply_mode,
            "confidence_threshold": row.confidence_threshold,
            "days_back": row.days_back,
            "re_ingest_interval_hours": row.re_ingest_interval_hours,
            "last_ingested_at": optional_isoformat(row.last_ingested_at),
            "last_message_count": row.last_message_count,
            "last_chunk_count": row.last_chunk_count,
            "last_status": row.last_status,
            "last_error": row.last_error,
            "registered_by": row.registered_by,
            "registered_at": isoformat(row.registered_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def legacy_channel_faq_registration_row(row: Mapping[str, Any], *, tenant_id: str) -> LegacyRow:
    channel_id = required_legacy_identity_text(row, "channel_id")
    return LegacyRow(
        source_table="channel_faq_registrations",
        source_pk=f"{tenant_id}:{channel_id}",
        payload={
            "tenant_id": tenant_id,
            "channel_id": channel_id,
            "channel_name": optional_legacy_identity_text(row, "channel_name"),
            "enabled": optional_legacy_bool(row, "enabled", default=True),
            "auto_reply_mode": optional_legacy_identity_text(row, "auto_reply_mode") or "mention",
            "confidence_threshold": optional_legacy_float(
                row, "confidence_threshold", default=0.75
            ),
            "days_back": optional_legacy_int(row, "days_back", default=30),
            "re_ingest_interval_hours": optional_legacy_int(
                row, "re_ingest_interval_hours", default=24
            ),
            "last_ingested_at": optional_legacy_timestamp(row, "last_ingested_at"),
            "last_message_count": optional_legacy_int(row, "last_message_count"),
            "last_chunk_count": optional_legacy_int(row, "last_chunk_count"),
            "last_status": optional_legacy_identity_text(row, "last_status"),
            "last_error": optional_legacy_identity_text(row, "last_error"),
            "registered_by": optional_legacy_identity_text(row, "registered_by"),
            "registered_at": legacy_identity_timestamp(row, "registered_at"),
            "updated_at": legacy_identity_timestamp(row, "updated_at"),
        },
    )


def feedback_legacy_row(row: FeedbackRecord) -> LegacyRow:
    return LegacyRow(
        source_table="feedback",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "feedback_id": row.id,
            "tenant_id": row.tenant_id,
            "query": row.query,
            "response": row.response,
            "rating": row.rating,
            "source": row.source,
            "comment": row.comment,
            "session_id": row.session_id,
            "run_id": row.run_id,
            "user_id": row.user_id,
            "review_status": row.review_status,
            "review_tags": list(row.review_tags),
            "reviewed_by": row.reviewed_by,
            "reviewed_at": optional_isoformat(row.reviewed_at),
            "review_note": row.review_note,
            "version": row.version,
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def legacy_feedback_row(row: Mapping[str, Any], *, tenant_id: str) -> LegacyRow:
    feedback_id = required_legacy_identity_text(row, "feedback_id")
    timestamp = legacy_identity_timestamp(row, "timestamp")
    return LegacyRow(
        source_table="feedback",
        source_pk=f"{tenant_id}:{feedback_id}",
        payload={
            "feedback_id": feedback_id,
            "tenant_id": tenant_id,
            "query": required_legacy_identity_text(row, "query"),
            "response": required_legacy_identity_text(row, "response"),
            "rating": required_legacy_identity_text(row, "rating"),
            "source": "legacy_feedback",
            "comment": optional_legacy_identity_text(row, "comment"),
            "session_id": optional_legacy_identity_text(row, "session_id"),
            "run_id": optional_legacy_identity_text(row, "run_id"),
            "user_id": optional_legacy_identity_text(row, "user_id"),
            "intent": optional_legacy_identity_text(row, "intent"),
            "domain": optional_legacy_identity_text(row, "domain"),
            "model": optional_legacy_identity_text(row, "model"),
            "prompt_version": optional_legacy_int(row, "prompt_version"),
            "tools_used": optional_legacy_text_list(row, "tools_used"),
            "duration_ms": optional_legacy_int(row, "duration_ms"),
            "tags": optional_legacy_text_list(row, "tags"),
            "review_status": "inbox",
            "review_tags": [],
            "reviewed_by": None,
            "reviewed_at": None,
            "review_note": None,
            "version": 1,
            "created_at": timestamp,
            "updated_at": timestamp,
        },
    )


def eval_case_legacy_row(row: AgentEvalCase) -> LegacyRow:
    return LegacyRow(
        source_table="agent_eval_cases",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "name": row.name,
            "user_input": row.user_input,
            "expected_answer_contains": list(row.expected_answer_contains),
            "forbidden_answer_contains": list(row.forbidden_answer_contains),
            "expected_tool_names": list(row.expected_tool_names),
            "forbidden_tool_names": list(row.forbidden_tool_names),
            "expected_exposed_tool_names": list(row.expected_exposed_tool_names),
            "forbidden_exposed_tool_names": list(row.forbidden_exposed_tool_names),
            "max_tool_exposure_count": row.max_tool_exposure_count,
            "agent_type": row.agent_type,
            "model": row.model,
            "enabled": row.enabled,
            "tags": list(row.tags),
            "min_score": row.min_score,
            "source_run_id": row.source_run_id,
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def eval_result_legacy_row(row: AgentEvalResult) -> LegacyRow:
    return LegacyRow(
        source_table="agent_eval_results",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "case_id": row.case_id,
            "run_id": row.run_id,
            "tier": row.tier,
            "passed": row.passed,
            "score": row.score,
            "reasons": list(row.reasons),
            "evaluated_at": isoformat(row.evaluated_at),
        },
    )


def scheduled_job_legacy_row(row: ScheduledJob) -> LegacyRow:
    return LegacyRow(
        source_table="scheduled_jobs",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "name": row.name,
            "description": row.description,
            "cron_expression": row.cron_expression,
            "timezone": row.timezone,
            "job_type": row.job_type,
            "mcp_server_name": row.mcp_server_name,
            "tool_name": row.tool_name,
            "tool_arguments": dict(row.tool_arguments),
            "agent_prompt": row.agent_prompt,
            "persona_id": row.persona_id,
            "agent_system_prompt": row.agent_system_prompt,
            "agent_model": row.agent_model,
            "agent_max_tool_calls": row.agent_max_tool_calls,
            "tags": sorted(parse_tags(row.tags)),
            "slack_channel_id": row.slack_channel_id,
            "teams_webhook_url": row.teams_webhook_url,
            "retry_on_failure": row.retry_on_failure,
            "max_retry_count": row.max_retry_count,
            "execution_timeout_ms": row.execution_timeout_ms,
            "enabled": row.enabled,
            "last_run_at": optional_isoformat(row.last_run_at),
            "last_status": row.last_status,
            "last_result": row.last_result,
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def legacy_scheduled_job_row(row: Mapping[str, Any], *, tenant_id: str) -> LegacyRow:
    job_id = required_legacy_identity_text(row, "id")
    return LegacyRow(
        source_table="scheduled_jobs",
        source_pk=f"{tenant_id}:{job_id}",
        payload={
            "id": job_id,
            "tenant_id": tenant_id,
            "name": required_legacy_identity_text(row, "name"),
            "description": optional_legacy_identity_text(row, "description"),
            "cron_expression": required_legacy_identity_text(row, "cron_expression"),
            "timezone": optional_legacy_identity_text(row, "timezone") or "Asia/Seoul",
            "job_type": "MCP_TOOL",
            "mcp_server_name": required_legacy_identity_text(row, "mcp_server_name"),
            "tool_name": required_legacy_identity_text(row, "tool_name"),
            "tool_arguments": optional_legacy_json_mapping(row, "tool_arguments"),
            "agent_prompt": None,
            "persona_id": None,
            "agent_system_prompt": None,
            "agent_model": None,
            "agent_max_tool_calls": None,
            "tags": [],
            "slack_channel_id": optional_legacy_identity_text(row, "slack_channel_id"),
            "teams_webhook_url": None,
            "retry_on_failure": optional_legacy_bool(row, "retry_on_failure", default=False),
            "max_retry_count": optional_legacy_int(row, "max_retry_count", default=3),
            "execution_timeout_ms": optional_legacy_int(row, "execution_timeout_ms"),
            "enabled": optional_legacy_bool(row, "enabled", default=True),
            "last_run_at": optional_legacy_timestamp(row, "last_run_at"),
            "last_status": optional_legacy_identity_text(row, "last_status"),
            "last_result": optional_legacy_identity_text(row, "last_result"),
            "created_at": legacy_identity_timestamp(row, "created_at"),
            "updated_at": legacy_identity_timestamp(row, "updated_at"),
        },
    )


def scheduled_job_execution_legacy_row(row: ScheduledJobExecution) -> LegacyRow:
    return LegacyRow(
        source_table="scheduled_job_executions",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "job_id": row.job_id,
            "job_name": row.job_name,
            "job_type": row.job_type,
            "status": row.status,
            "result": row.result,
            "duration_ms": row.duration_ms,
            "dry_run": row.dry_run,
            "started_at": isoformat(row.started_at),
            "completed_at": optional_isoformat(row.completed_at),
        },
    )


def legacy_scheduled_job_execution_row(row: Mapping[str, Any], *, tenant_id: str) -> LegacyRow:
    execution_id = required_legacy_identity_text(row, "id")
    return LegacyRow(
        source_table="scheduled_job_executions",
        source_pk=f"{tenant_id}:{execution_id}",
        payload={
            "id": execution_id,
            "tenant_id": tenant_id,
            "job_id": required_legacy_identity_text(row, "job_id"),
            "job_name": required_legacy_identity_text(row, "job_name"),
            "job_type": "MCP_TOOL",
            "status": required_legacy_identity_text(row, "status"),
            "result": optional_legacy_identity_text(row, "result"),
            "duration_ms": optional_legacy_int(row, "duration_ms", default=0),
            "dry_run": optional_legacy_bool(row, "dry_run", default=False),
            "started_at": legacy_identity_timestamp(row, "started_at"),
            "completed_at": optional_legacy_timestamp(row, "completed_at"),
        },
    )


def scheduled_job_dead_letter_legacy_row(row: ScheduledJobDeadLetter) -> LegacyRow:
    return LegacyRow(
        source_table="scheduled_job_dead_letters",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "job_id": row.job_id,
            "job_name": row.job_name,
            "job_type": row.job_type,
            "reason": row.reason,
            "result": row.result,
            "dry_run": row.dry_run,
            "created_at": isoformat(row.created_at),
        },
    )


def model_pricing_legacy_row(row: ModelPricing) -> LegacyRow:
    return LegacyRow(
        source_table="model_pricing",
        source_pk=f"{row.provider}:{row.model}:{row.id}",
        payload={
            "id": row.id,
            "provider": row.provider,
            "model": row.model,
            "prompt_price_per_1m": decimal_str(row.prompt_price_per_1m),
            "completion_price_per_1m": decimal_str(row.completion_price_per_1m),
            "cached_input_price_per_1m": decimal_str(row.cached_input_price_per_1m),
            "reasoning_price_per_1m": decimal_str(row.reasoning_price_per_1m),
            "batch_prompt_price_per_1m": decimal_str(row.batch_prompt_price_per_1m),
            "batch_completion_price_per_1m": decimal_str(row.batch_completion_price_per_1m),
            "effective_from": isoformat(row.effective_from),
            "effective_to": optional_isoformat(row.effective_to),
        },
    )


def legacy_v42_model_pricing_row(row: Mapping[str, Any]) -> LegacyRow:
    provider = required_legacy_identity_text(row, "provider")
    model = required_legacy_identity_text(row, "model")
    pricing_id = required_legacy_identity_text(row, "id")
    return LegacyRow(
        source_table="model_pricing",
        source_pk=f"{provider}:{model}:{pricing_id}",
        payload={
            "id": pricing_id,
            "provider": provider,
            "model": model,
            "prompt_price_per_1m": decimal_str(
                legacy_price_per_1k_to_1m(row, "prompt_price_per_1k")
            ),
            "completion_price_per_1m": decimal_str(
                legacy_price_per_1k_to_1m(row, "completion_price_per_1k")
            ),
            "cached_input_price_per_1m": decimal_str(
                legacy_price_per_1k_to_1m(row, "cached_input_price_per_1k")
            ),
            "reasoning_price_per_1m": decimal_str(
                legacy_price_per_1k_to_1m(row, "reasoning_price_per_1k")
            ),
            "batch_prompt_price_per_1m": decimal_str(
                legacy_price_per_1k_to_1m(row, "batch_prompt_price_per_1k")
            ),
            "batch_completion_price_per_1m": decimal_str(
                legacy_price_per_1k_to_1m(row, "batch_completion_price_per_1k")
            ),
            "effective_from": legacy_identity_timestamp(row, "effective_from"),
            "effective_to": optional_legacy_timestamp(row, "effective_to"),
        },
    )


def tenant_legacy_row(row: Tenant) -> LegacyRow:
    return LegacyRow(
        source_table="tenants",
        source_pk=row.id,
        payload={
            "id": row.id,
            "name": row.name,
            "slug": row.slug,
            "plan": row.plan,
            "status": row.status,
            "max_requests_per_month": row.max_requests_per_month,
            "max_tokens_per_month": row.max_tokens_per_month,
            "max_users": row.max_users,
            "max_agents": row.max_agents,
            "max_mcp_servers": row.max_mcp_servers,
            "billing_cycle_start": row.billing_cycle_start,
            "billing_email": row.billing_email,
            "slo_availability": row.slo_availability,
            "slo_latency_p99_ms": row.slo_latency_p99_ms,
            "metadata": dict(row.tenant_metadata),
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def legacy_slo_config_row(row: Mapping[str, Any]) -> LegacyRow:
    tenant_id = required_legacy_identity_text(row, "tenant_id")
    created_at = legacy_identity_timestamp(row, "created_at")
    updated_at = legacy_identity_timestamp(row, "updated_at")
    return LegacyRow(
        source_table="tenant_slo_config",
        source_pk=tenant_id,
        payload={
            "tenant_id": tenant_id,
            "slo_availability": optional_legacy_float(
                row,
                "availability_target",
                default=0.995,
            ),
            "slo_latency_p99_ms": optional_legacy_int(
                row,
                "latency_p99_target_ms",
                default=10000,
            )
            or 10000,
            "metadata": {
                "legacy_slo_config": {
                    "id": optional_legacy_identity_text(row, "id") or tenant_id,
                    "apdex_satisfied_ms": optional_legacy_int(
                        row,
                        "apdex_satisfied_ms",
                        default=5000,
                    )
                    or 5000,
                    "apdex_tolerating_ms": optional_legacy_int(
                        row,
                        "apdex_tolerating_ms",
                        default=20000,
                    )
                    or 20000,
                    "error_budget_window_days": optional_legacy_int(
                        row,
                        "error_budget_window_days",
                        default=30,
                    )
                    or 30,
                    "created_at": created_at,
                    "updated_at": updated_at,
                }
            },
            "updated_at": updated_at,
        },
    )


def usage_ledger_legacy_row(row: UsageLedger) -> LegacyRow:
    return LegacyRow(
        source_table="usage_ledger",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "run_id": row.run_id,
            "provider": row.provider,
            "model": row.model,
            "step_type": row.step_type,
            "prompt_tokens": row.prompt_tokens,
            "cached_tokens": row.cached_tokens,
            "completion_tokens": row.completion_tokens,
            "reasoning_tokens": row.reasoning_tokens,
            "total_tokens": row.total_tokens,
            "estimated_cost_usd": decimal_str(row.estimated_cost_usd),
            "occurred_at": isoformat(row.occurred_at),
        },
    )


def legacy_metric_token_usage_row(row: Mapping[str, Any]) -> LegacyRow:
    tenant_id = required_legacy_identity_text(row, "tenant_id")
    run_id = required_legacy_identity_text(row, "run_id")
    provider = required_legacy_identity_text(row, "provider")
    model = required_legacy_identity_text(row, "model")
    step_type = optional_legacy_identity_text(row, "step_type") or "act"
    occurred_at = legacy_identity_timestamp(row, "time")
    usage_id = legacy_metric_usage_id(
        tenant_id=tenant_id,
        run_id=run_id,
        occurred_at=occurred_at,
        provider=provider,
        model=model,
        step_type=step_type,
    )
    return LegacyRow(
        source_table="usage_ledger",
        source_pk=f"{tenant_id}:{usage_id}",
        payload={
            "id": usage_id,
            "tenant_id": tenant_id,
            "run_id": run_id,
            "provider": provider,
            "model": model,
            "step_type": step_type,
            "prompt_tokens": optional_legacy_int(row, "prompt_tokens", default=0) or 0,
            "cached_tokens": optional_legacy_int(row, "prompt_cached_tokens", default=0) or 0,
            "completion_tokens": optional_legacy_int(row, "completion_tokens", default=0) or 0,
            "reasoning_tokens": optional_legacy_int(row, "reasoning_tokens", default=0) or 0,
            "total_tokens": optional_legacy_int(row, "total_tokens", default=0) or 0,
            "estimated_cost_usd": optional_legacy_decimal_text(row, "estimated_cost_usd")
            or "0.00000000",
            "occurred_at": occurred_at,
        },
    )


def legacy_metric_agent_execution_row(row: Mapping[str, Any]) -> LegacyRow:
    tenant_id = required_legacy_identity_text(row, "tenant_id")
    run_id = required_legacy_identity_text(row, "run_id")
    recorded_at = legacy_identity_timestamp(row, "time")
    return LegacyRow(
        source_table="metric_agent_executions",
        source_pk=f"{tenant_id}:{run_id}:{recorded_at}",
        payload={
            "type": "agent_execution",
            "recordedAt": recorded_at,
            "tenantId": tenant_id,
            "runId": run_id,
            "userId": optional_legacy_identity_text(row, "user_id"),
            "sessionId": optional_legacy_identity_text(row, "session_id"),
            "channel": optional_legacy_identity_text(row, "channel") or "api",
            "success": optional_legacy_bool(row, "success", default=True),
            "errorCode": optional_legacy_identity_text(row, "error_code"),
            "errorClass": optional_legacy_identity_text(row, "error_class"),
            "durationMs": optional_legacy_int(row, "duration_ms", default=0) or 0,
            "llmDurationMs": optional_legacy_int(row, "llm_duration_ms", default=0) or 0,
            "toolDurationMs": optional_legacy_int(row, "tool_duration_ms", default=0) or 0,
            "guardDurationMs": optional_legacy_int(row, "guard_duration_ms", default=0) or 0,
            "queueWaitMs": optional_legacy_int(row, "queue_wait_ms", default=0) or 0,
            "streaming": optional_legacy_bool(row, "is_streaming", default=False),
            "toolCount": optional_legacy_int(row, "tool_count", default=0) or 0,
            "personaId": optional_legacy_identity_text(row, "persona_id"),
            "promptTemplateId": optional_legacy_identity_text(row, "prompt_template_id"),
            "intentCategory": optional_legacy_identity_text(row, "intent_category"),
            "guardRejected": optional_legacy_bool(row, "guard_rejected", default=False),
            "guardStage": optional_legacy_identity_text(row, "guard_stage"),
            "guardCategory": optional_legacy_identity_text(row, "guard_category"),
            "retryCount": optional_legacy_int(row, "retry_count", default=0) or 0,
            "fallbackUsed": optional_legacy_bool(row, "fallback_used", default=False),
        },
    )


def legacy_metric_session_row(row: Mapping[str, Any]) -> LegacyRow:
    tenant_id = required_legacy_identity_text(row, "tenant_id")
    session_id = required_legacy_identity_text(row, "session_id")
    recorded_at = legacy_identity_timestamp(row, "time")
    return LegacyRow(
        source_table="metric_sessions",
        source_pk=f"{tenant_id}:{session_id}:{recorded_at}",
        payload={
            "type": "session",
            "recordedAt": recorded_at,
            "tenantId": tenant_id,
            "sessionId": session_id,
            "userId": optional_legacy_identity_text(row, "user_id"),
            "channel": optional_legacy_identity_text(row, "channel") or "api",
            "turnCount": optional_legacy_int(row, "turn_count", default=0) or 0,
            "totalDurationMs": optional_legacy_int(row, "total_duration_ms", default=0) or 0,
            "totalTokens": optional_legacy_int(row, "total_tokens", default=0) or 0,
            "totalCostUsd": optional_legacy_decimal_text(row, "total_cost_usd") or "0.00000000",
            "firstResponseLatencyMs": optional_legacy_int(
                row,
                "first_response_latency_ms",
                default=0,
            )
            or 0,
            "outcome": optional_legacy_identity_text(row, "outcome") or "resolved",
            "startedAt": legacy_identity_timestamp(row, "started_at"),
            "endedAt": legacy_identity_timestamp(row, "ended_at"),
        },
    )


def legacy_metric_span_row(row: Mapping[str, Any]) -> LegacyRow:
    tenant_id = required_legacy_identity_text(row, "tenant_id")
    trace_id = required_legacy_identity_text(row, "trace_id")
    span_id = required_legacy_identity_text(row, "span_id")
    return LegacyRow(
        source_table="metric_spans",
        source_pk=f"{tenant_id}:{trace_id}:{span_id}",
        payload={
            "type": "span",
            "recordedAt": legacy_identity_timestamp(row, "time"),
            "tenantId": tenant_id,
            "traceId": trace_id,
            "spanId": span_id,
            "parentSpanId": optional_legacy_identity_text(row, "parent_span_id"),
            "runId": optional_legacy_identity_text(row, "run_id"),
            "operationName": required_legacy_identity_text(row, "operation_name"),
            "serviceName": required_legacy_identity_text(row, "service_name"),
            "durationMs": optional_legacy_int(row, "duration_ms", default=0) or 0,
            "success": optional_legacy_bool(row, "success", default=True),
            "errorClass": optional_legacy_identity_text(row, "error_class"),
            "attributes": optional_legacy_json_mapping(row, "attributes"),
        },
    )


def legacy_metric_audit_trail_row(row: Mapping[str, Any]) -> LegacyRow:
    tenant_id = required_legacy_identity_text(row, "tenant_id")
    event_type = required_legacy_identity_text(row, "event_type")
    recorded_at = legacy_identity_timestamp(row, "time")
    resource_id = optional_legacy_identity_text(row, "resource_id")
    return LegacyRow(
        source_table="metric_audit_trail",
        source_pk=f"{tenant_id}:{event_type}:{resource_id or 'none'}:{recorded_at}",
        payload={
            "type": "audit_trail",
            "recordedAt": recorded_at,
            "tenantId": tenant_id,
            "actorId": optional_legacy_identity_text(row, "actor_id"),
            "actorEmail": optional_legacy_identity_text(row, "actor_email"),
            "eventType": event_type,
            "resourceType": optional_legacy_identity_text(row, "resource_type"),
            "resourceId": resource_id,
            "detail": optional_legacy_json_mapping(row, "detail"),
            "sourceIp": optional_legacy_identity_text(row, "source_ip"),
        },
    )


def legacy_metric_quota_event_row(row: Mapping[str, Any]) -> LegacyRow:
    tenant_id = required_legacy_identity_text(row, "tenant_id")
    action = required_legacy_identity_text(row, "action")
    recorded_at = legacy_identity_timestamp(row, "time")
    return LegacyRow(
        source_table="metric_quota_events",
        source_pk=f"{tenant_id}:{action}:{recorded_at}",
        payload={
            "type": "quota_event",
            "recordedAt": recorded_at,
            "tenantId": tenant_id,
            "action": action,
            "currentUsage": optional_legacy_int(row, "current_usage", default=0) or 0,
            "quotaLimit": optional_legacy_int(row, "quota_limit", default=0) or 0,
            "usagePercent": optional_legacy_float(row, "usage_percent", default=0.0),
            "reason": optional_legacy_identity_text(row, "reason"),
        },
    )


def legacy_metric_hitl_event_row(row: Mapping[str, Any]) -> LegacyRow:
    tenant_id = required_legacy_identity_text(row, "tenant_id")
    run_id = required_legacy_identity_text(row, "run_id")
    tool_name = required_legacy_identity_text(row, "tool_name")
    recorded_at = legacy_identity_timestamp(row, "time")
    return LegacyRow(
        source_table="metric_hitl_events",
        source_pk=f"{tenant_id}:{run_id}:{tool_name}:{recorded_at}",
        payload={
            "type": "hitl_event",
            "recordedAt": recorded_at,
            "tenantId": tenant_id,
            "runId": run_id,
            "toolName": tool_name,
            "approved": optional_legacy_bool(row, "approved", default=False),
            "waitMs": optional_legacy_int(row, "wait_ms", default=0) or 0,
            "rejectionReason": optional_legacy_identity_text(row, "rejection_reason"),
        },
    )


def legacy_metric_guard_event_row(row: Mapping[str, Any]) -> LegacyRow:
    tenant_id = required_legacy_identity_text(row, "tenant_id")
    user_id = optional_legacy_identity_text(row, "user_id")
    stage = required_legacy_identity_text(row, "stage")
    occurred_at = legacy_identity_timestamp(row, "time")
    return LegacyRow(
        source_table="metric_guard_events",
        source_pk=f"{tenant_id}:{user_id or 'anonymous'}:{stage}:{occurred_at}",
        payload={
            "time": occurred_at,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "channel": optional_legacy_identity_text(row, "channel") or "api",
            "stage": stage,
            "category": optional_legacy_identity_text(row, "category"),
            "reason_class": optional_legacy_identity_text(row, "reason_class"),
            "reason_detail": optional_legacy_identity_text(row, "reason_detail"),
            "is_output_guard": optional_legacy_bool(row, "is_output_guard", default=False),
            "action": optional_legacy_identity_text(row, "action") or "rejected",
        },
    )


def input_guard_metric_legacy_row(row: MetricGuardEvent) -> LegacyRow:
    return legacy_metric_guard_event_row(
        {
            "time": row.time,
            "tenant_id": row.tenant_id,
            "user_id": row.user_id,
            "channel": row.channel,
            "stage": row.stage,
            "category": row.category,
            "reason_class": row.reason_class,
            "reason_detail": row.reason_detail,
            "is_output_guard": row.is_output_guard,
            "action": row.action,
        }
    )


def legacy_metric_tool_call_row(row: Mapping[str, Any]) -> LegacyRow:
    tenant_id = required_legacy_identity_text(row, "tenant_id")
    run_id = required_legacy_identity_text(row, "run_id")
    tool_name = required_legacy_identity_text(row, "tool_name")
    call_index = optional_legacy_int(row, "call_index", default=0) or 0
    return LegacyRow(
        source_table="metric_tool_calls",
        source_pk=f"{tenant_id}:{run_id}:{call_index}:{tool_name}",
        payload={
            "type": "tool_call",
            "recordedAt": legacy_identity_timestamp(row, "time"),
            "tenantId": tenant_id,
            "runId": run_id,
            "toolName": tool_name,
            "toolSource": optional_legacy_identity_text(row, "tool_source") or "local",
            "mcpServerName": optional_legacy_identity_text(row, "mcp_server_name"),
            "callIndex": call_index,
            "success": optional_legacy_bool(row, "success", default=True),
            "durationMs": optional_legacy_int(row, "duration_ms", default=0) or 0,
            "errorClass": optional_legacy_identity_text(row, "error_class"),
            "errorMessage": optional_legacy_identity_text(row, "error_message"),
        },
    )


def legacy_mcp_health_metric_row(row: Mapping[str, Any]) -> LegacyRow:
    tenant_id = required_legacy_identity_text(row, "tenant_id")
    server_name = required_legacy_identity_text(row, "server_name")
    recorded_at = legacy_identity_timestamp(row, "time")
    return LegacyRow(
        source_table="metric_mcp_health",
        source_pk=f"{tenant_id}:{server_name}:{recorded_at}",
        payload={
            "type": "mcp_health",
            "recordedAt": recorded_at,
            "tenantId": tenant_id,
            "serverName": server_name,
            "status": optional_legacy_identity_text(row, "status") or "CONNECTED",
            "responseTimeMs": optional_legacy_int(row, "response_time_ms", default=0) or 0,
            "errorClass": optional_legacy_identity_text(row, "error_class"),
            "errorMessage": optional_legacy_identity_text(row, "error_message"),
            "toolCount": optional_legacy_int(row, "tool_count", default=0) or 0,
        },
    )


def legacy_eval_result_metric_row(row: Mapping[str, Any]) -> LegacyRow:
    tenant_id = required_legacy_identity_text(row, "tenant_id")
    eval_run_id = required_legacy_identity_text(row, "eval_run_id")
    test_case_id = required_legacy_identity_text(row, "test_case_id")
    recorded_at = legacy_identity_timestamp(row, "time")
    return LegacyRow(
        source_table="metric_eval_results",
        source_pk=f"{tenant_id}:{eval_run_id}:{test_case_id}:{recorded_at}",
        payload={
            "type": "eval_result",
            "recordedAt": recorded_at,
            "tenantId": tenant_id,
            "evalRunId": eval_run_id,
            "testCaseId": test_case_id,
            "pass": optional_legacy_bool(row, "pass", default=False),
            "score": optional_legacy_float(row, "score", default=0.0),
            "latencyMs": optional_legacy_int(row, "latency_ms", default=0) or 0,
            "tokenUsage": optional_legacy_int(row, "token_usage", default=0) or 0,
            "cost": optional_legacy_decimal_text(row, "cost"),
            "assertionType": optional_legacy_identity_text(row, "assertion_type"),
            "failureClass": optional_legacy_identity_text(row, "failure_class"),
            "failureDetail": optional_legacy_identity_text(row, "failure_detail"),
            "tags": optional_legacy_text_list(row, "tags") or [],
        },
    )


def alert_rule_legacy_row(row: AlertRuleRow) -> LegacyRow:
    tenant_key = row.tenant_id or "platform"
    return LegacyRow(
        source_table="alert_rules",
        source_pk=f"{tenant_key}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "name": row.name,
            "description": row.description,
            "type": row.type,
            "severity": row.severity,
            "metric": row.metric,
            "threshold": row.threshold,
            "window_minutes": row.window_minutes,
            "enabled": row.enabled,
            "platform_only": row.platform_only,
            "created_at": isoformat(row.created_at),
        },
    )


def alert_instance_legacy_row(row: AlertInstanceRow) -> LegacyRow:
    return LegacyRow(
        source_table="alert_instances",
        source_pk=f"{row.rule_id}:{row.id}",
        payload={
            "id": row.id,
            "rule_id": row.rule_id,
            "tenant_id": row.tenant_id,
            "severity": row.severity,
            "status": row.status,
            "message": row.message,
            "metric_value": row.metric_value,
            "threshold": row.threshold,
            "fired_at": isoformat(row.fired_at),
            "resolved_at": optional_isoformat(row.resolved_at),
            "acknowledged_by": row.acknowledged_by,
        },
    )


def auth_user_legacy_row(row: AuthUser) -> LegacyRow:
    return LegacyRow(
        source_table="users",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "email": row.email,
            "name": row.name,
            "password_hash": row.password_hash,
            "role": row.role,
            "tenant_id": row.tenant_id,
            "groups": list(row.groups or []),
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def legacy_user_row(row: Mapping[str, Any], *, default_tenant_id: str) -> LegacyRow:
    user_id = required_legacy_identity_text(row, "id")
    tenant_id = optional_legacy_identity_text(row, "tenant_id") or default_tenant_id
    created_at = legacy_identity_timestamp(row, "created_at")
    return LegacyRow(
        source_table="users",
        source_pk=f"{tenant_id}:{user_id}",
        payload={
            "id": user_id,
            "email": required_legacy_identity_text(row, "email"),
            "name": required_legacy_identity_text(row, "name"),
            "password_hash": required_legacy_identity_text(row, "password_hash"),
            "role": optional_legacy_identity_text(row, "role") or "USER",
            "tenant_id": tenant_id,
            "created_at": created_at,
            "updated_at": optional_legacy_timestamp(row, "updated_at") or created_at,
        },
    )


def user_identity_legacy_row(row: UserIdentity) -> LegacyRow:
    return LegacyRow(
        source_table="user_identities",
        source_pk=f"{row.tenant_id}:{row.provider}:{row.external_subject}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "user_id": row.user_id,
            "provider": row.provider,
            "external_subject": row.external_subject,
            "metadata": dict(row.identity_metadata),
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def legacy_slack_user_identity_rows(
    row: Mapping[str, Any],
    *,
    tenant_id: str,
    user_id: str,
) -> list[LegacyRow]:
    slack_user_id = required_legacy_identity_text(row, "slack_user_id")
    email = required_legacy_identity_text(row, "email")
    display_name = optional_legacy_identity_text(row, "display_name")
    created_at = legacy_identity_timestamp(row, "created_at")
    updated_at = legacy_identity_timestamp(row, "updated_at")
    shared_metadata = {
        "display_name": display_name,
        "legacy_slack_user_id": slack_user_id,
    }
    rows = [
        legacy_external_identity_row(
            tenant_id=tenant_id,
            user_id=user_id,
            provider="slack",
            external_subject=slack_user_id,
            metadata={
                "email": email,
                "display_name": display_name,
                "legacy_slack_user_id": slack_user_id,
            },
            created_at=created_at,
            updated_at=updated_at,
        ),
        legacy_external_identity_row(
            tenant_id=tenant_id,
            user_id=user_id,
            provider="email",
            external_subject=email,
            metadata=shared_metadata,
            created_at=created_at,
            updated_at=updated_at,
        ),
    ]
    for provider, key in (("jira", "jira_account_id"), ("bitbucket", "bitbucket_uuid")):
        external_subject = optional_legacy_identity_text(row, key)
        if external_subject is None:
            continue
        rows.append(
            legacy_external_identity_row(
                tenant_id=tenant_id,
                user_id=user_id,
                provider=provider,
                external_subject=external_subject,
                metadata={"email": email, **shared_metadata},
                created_at=created_at,
                updated_at=updated_at,
            )
        )
    return rows


def legacy_external_identity_row(
    *,
    tenant_id: str,
    user_id: str,
    provider: str,
    external_subject: str,
    metadata: Mapping[str, Any],
    created_at: str,
    updated_at: str,
) -> LegacyRow:
    return LegacyRow(
        source_table="user_identities",
        source_pk=f"{tenant_id}:{provider}:{external_subject}",
        payload={
            "id": legacy_identity_id(tenant_id, provider, external_subject),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "provider": provider,
            "external_subject": external_subject,
            "metadata": {
                key: value
                for key, value in metadata.items()
                if isinstance(value, str) and value.strip()
            },
            "created_at": created_at,
            "updated_at": updated_at,
        },
    )


def legacy_identity_id(tenant_id: str, provider: str, external_subject: str) -> str:
    normalized_subject = re.sub(r"[^A-Za-z0-9]+", "_", external_subject).strip("_")
    normalized_subject = normalized_subject or "subject"
    return f"user_identity_{tenant_id}_{provider}_{normalized_subject}"


def legacy_metric_usage_id(
    *,
    tenant_id: str,
    run_id: str,
    occurred_at: str,
    provider: str,
    model: str,
    step_type: str,
) -> str:
    timestamp = occurred_at.split("+", maxsplit=1)[0].split(".", maxsplit=1)[0]
    timestamp = timestamp.replace(":", "").replace("-", "")
    raw = f"{tenant_id}_{run_id}_{timestamp}_{provider}_{model}_{step_type}"
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_")
    return f"usage_metric_{normalized or 'row'}"


def legacy_conversation_run_id(tenant_id: str, session_id: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", f"{tenant_id}_{session_id}").strip("_")
    return f"legacy_conv_{normalized or 'session'}"


def legacy_conversation_summary_run_id(tenant_id: str, session_id: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", f"{tenant_id}_{session_id}").strip("_")
    return f"legacy_conv_summary_{normalized or 'session'}"


def legacy_summary_facts(row: Mapping[str, Any]) -> list[Any]:
    value = row.get("facts_json")
    if value is None:
        return []
    if isinstance(value, list):
        return list(cast(list[Any], value))
    text = str(value).strip()
    if not text:
        return []
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError("facts_json must be a JSON array")
    return list(cast(list[Any], parsed))


def required_legacy_identity_text(row: Mapping[str, Any], key: str) -> str:
    value = optional_legacy_identity_text(row, key)
    if value is None:
        raise ValueError(f"{key} is required")
    return value


def optional_legacy_identity_text(row: Mapping[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def legacy_identity_timestamp(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if isinstance(value, datetime):
        return isoformat(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return isoformat(datetime.now())


def optional_legacy_timestamp(row: Mapping[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, datetime):
        return isoformat(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def optional_legacy_bool(row: Mapping[str, Any], key: str, *, default: bool) -> bool:
    value = row.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return bool(value)


def optional_legacy_int(
    row: Mapping[str, Any],
    key: str,
    *,
    default: int | None = None,
) -> int | None:
    value = row.get(key)
    if value is None:
        return default
    return int(value)


def optional_legacy_float(row: Mapping[str, Any], key: str, *, default: float) -> float:
    value = row.get(key)
    if value is None:
        return default
    return float(value)


def optional_legacy_decimal_text(row: Mapping[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    return decimal_str(Decimal(str(value)))


def legacy_price_per_1k_to_1m(row: Mapping[str, Any], key: str) -> Decimal:
    value = row.get(key)
    if value is None:
        return Decimal("0")
    return (Decimal(str(value)) * Decimal("1000")).quantize(Decimal("0.00000001"))


def optional_legacy_text_list(row: Mapping[str, Any], key: str) -> list[str] | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, list):
        raw_items = cast(list[Any], value)
        items = [str(item).strip() for item in raw_items]
    else:
        items = [item.strip() for item in str(value).split(",")]
    normalized = [item for item in items if item]
    return normalized or None


def optional_legacy_json_mapping(row: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = row.get(key)
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(cast(Mapping[str, Any], value))
    text = str(value).strip()
    if not text:
        return {}
    parsed = json.loads(text)
    if not isinstance(parsed, Mapping):
        raise ValueError(f"{key} must be a JSON object")
    return dict(cast(Mapping[str, Any], parsed))


def legacy_text_sequence(row: Mapping[str, Any], key: str) -> list[str]:
    value = row.get(key)
    if value is None:
        return []
    if isinstance(value, list | tuple | set | frozenset):
        raw_items = list(cast(Iterable[Any], value))
    else:
        text = str(value).strip()
        if not text:
            return []
        if text.startswith("["):
            parsed = json.loads(text)
            if not isinstance(parsed, list):
                raise ValueError(f"{key} must be a JSON array")
            raw_items = cast(list[Any], parsed)
        else:
            raw_items = [item.strip() for item in text.split(",")]
    normalized = [str(item).strip() for item in raw_items if str(item).strip()]
    return normalized


def legacy_text_sequence_mapping(
    row: Mapping[str, Any],
    key: str,
) -> dict[str, tuple[str, ...]]:
    raw = optional_legacy_json_mapping(row, key)
    normalized: dict[str, tuple[str, ...]] = {}
    for raw_key, raw_value in raw.items():
        channel = raw_key.strip().lower()
        if not channel:
            continue
        if isinstance(raw_value, list | tuple | set | frozenset):
            raw_values = cast(Iterable[Any], raw_value)
            values = [str(item).strip() for item in raw_values if str(item).strip()]
        else:
            values = [item.strip() for item in str(raw_value).split(",") if item.strip()]
        if values:
            normalized[channel] = tuple(sorted(set(values)))
    return dict(sorted(normalized.items()))


def legacy_datetime(row: Mapping[str, Any], key: str) -> datetime:
    value = row.get(key)
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value.strip())
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


def auth_token_revocation_legacy_row(row: AuthTokenRevocation) -> LegacyRow:
    return LegacyRow(
        source_table="auth_token_revocations",
        source_pk=row.token_id,
        payload={
            "token_id": row.token_id,
            "expires_at": isoformat(row.expires_at),
            "revoked_at": isoformat(row.revoked_at),
        },
    )


def input_guard_rule_legacy_row(row: InputGuardRule) -> LegacyRow:
    return LegacyRow(
        source_table="input_guard_rules",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "name": row.name,
            "pattern": row.pattern,
            "pattern_type": row.pattern_type,
            "action": row.action,
            "priority": row.priority,
            "category": row.category,
            "description": row.description,
            "enabled": row.enabled,
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def output_guard_rule_legacy_row(row: OutputGuardRule) -> LegacyRow:
    return LegacyRow(
        source_table="output_guard_rules",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "name": row.name,
            "pattern": row.pattern,
            "action": row.action,
            "replacement": row.replacement,
            "priority": row.priority,
            "enabled": row.enabled,
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def output_guard_rule_audit_legacy_row(row: OutputGuardRuleAudit) -> LegacyRow:
    return LegacyRow(
        source_table="output_guard_rule_audits",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "rule_id": row.rule_id,
            "action": row.action,
            "actor": row.actor,
            "detail": row.detail,
            "created_at": isoformat(row.created_at),
        },
    )


def admin_audit_legacy_row(row: AdminAudit) -> LegacyRow:
    return LegacyRow(
        source_table="admin_audits",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "category": row.category,
            "action": row.action,
            "actor": row.actor,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "detail": row.detail,
            "created_at": isoformat(row.created_at),
        },
    )


def tool_catalog_legacy_row(row: ToolCatalog) -> LegacyRow:
    return LegacyRow(
        source_table="tool_catalog",
        source_pk=f"{row.tenant_id}:{row.namespace}:{row.name}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "namespace": row.namespace,
            "name": row.name,
            "description": row.description,
            "risk_level": row.risk_level,
            "input_schema": dict(row.input_schema),
            "output_schema": dict(row.output_schema),
            "enabled": row.enabled,
            "requires_approval": row.requires_approval,
            "timeout_ms": row.timeout_ms,
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def pending_approval_legacy_row(row: PendingApproval) -> LegacyRow:
    return LegacyRow(
        source_table="pending_approvals",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "run_id": row.run_id,
            "tool_id": row.tool_id,
            "status": row.status,
            "requested_by": row.requested_by,
            "decided_by": row.decided_by,
            "request_payload": dict(row.request_payload),
            "decision_reason": row.decision_reason,
            "created_at": isoformat(row.created_at),
            "decided_at": optional_isoformat(row.decided_at),
        },
    )


def tool_invocation_legacy_row(row: ToolInvocation) -> LegacyRow:
    return LegacyRow(
        source_table="tool_invocations",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "run_id": row.run_id,
            "tool_id": row.tool_id,
            "approval_id": row.approval_id,
            "status": row.status,
            "idempotency_key": row.idempotency_key,
            "request_checksum": row.request_checksum,
            "result_checksum": row.result_checksum,
            "input_payload": dict(row.input_payload),
            "output_payload": dict(row.output_payload) if row.output_payload is not None else None,
            "error_payload": dict(row.error_payload) if row.error_payload is not None else None,
            "started_at": isoformat(row.started_at),
            "completed_at": optional_isoformat(row.completed_at),
        },
    )


def mcp_server_legacy_row(row: McpServer) -> LegacyRow:
    return LegacyRow(
        source_table="mcp_servers",
        source_pk=f"{row.tenant_id}:{row.name}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "name": row.name,
            "transport": row.transport,
            "status": row.status,
            "command": row.command,
            "args": list(row.args),
            "url": row.url,
            "auth_type": row.auth_type,
            "timeout_ms": row.timeout_ms,
            "protocol_version": row.protocol_version,
            "last_connection_error": row.last_connection_error,
            "reconnect_policy": dict(row.reconnect_policy),
            "tool_snapshot_hash": row.tool_snapshot_hash,
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def mcp_server_status_legacy_row(row: McpServerStatus) -> LegacyRow:
    return LegacyRow(
        source_table="mcp_server_status",
        source_pk=f"{row.tenant_id}:{row.server_id}",
        payload={
            "server_id": row.server_id,
            "tenant_id": row.tenant_id,
            "status": row.status,
            "negotiated_protocol_version": row.negotiated_protocol_version,
            "last_error": row.last_error,
            "reconnect_attempt": row.reconnect_attempt,
            "backoff_until": optional_isoformat(row.backoff_until),
            "checked_at": isoformat(row.checked_at),
        },
    )


def mcp_tool_snapshot_legacy_row(row: McpToolSnapshot) -> LegacyRow:
    return LegacyRow(
        source_table="mcp_tool_snapshots",
        source_pk=f"{row.tenant_id}:{row.server_id}:{row.tool_name}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "server_id": row.server_id,
            "qualified_name": row.qualified_name,
            "tool_name": row.tool_name,
            "description": row.description,
            "input_schema": dict(row.input_schema),
            "output_schema": dict(row.output_schema),
            "risk_level": row.risk_level,
            "enabled": row.enabled,
            "snapshot_hash": row.snapshot_hash,
            "created_at": isoformat(row.created_at),
        },
    )


def mcp_access_policy_legacy_row(row: McpAccessPolicy) -> LegacyRow:
    return LegacyRow(
        source_table="mcp_access_policies",
        source_pk=f"{row.tenant_id}:{row.graph_profile}:{row.server_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "server_id": row.server_id,
            "graph_profile": row.graph_profile,
            "allow_write": row.allow_write,
            "allowed_tools": list(row.allowed_tools),
            "created_at": isoformat(row.created_at),
        },
    )


def a2a_peer_agent_legacy_row(row: A2APeerAgent) -> LegacyRow:
    return LegacyRow(
        source_table="a2a_peer_agents",
        source_pk=f"{row.tenant_id}:{row.name}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "name": row.name,
            "endpoint_url": row.endpoint_url,
            "agent_card": dict(row.agent_card),
            "enabled": row.enabled,
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def a2a_agent_card_legacy_row(row: A2AAgentCard) -> LegacyRow:
    return LegacyRow(
        source_table="a2a_agent_cards",
        source_pk=f"{row.tenant_id}:{row.version}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "version": row.version,
            "protocol_version": row.protocol_version,
            "card": dict(row.card),
            "active": row.active,
            "created_at": isoformat(row.created_at),
        },
    )


def a2a_task_legacy_row(row: A2ATask) -> LegacyRow:
    return LegacyRow(
        source_table="a2a_tasks",
        source_pk=f"{row.tenant_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "peer_agent_id": row.peer_agent_id,
            "run_id": row.run_id,
            "thread_id": row.thread_id,
            "session_id": row.session_id,
            "context_id": row.context_id,
            "message_id": row.message_id,
            "status": row.status,
            "idempotency_key": row.idempotency_key,
            "input_payload": dict(row.input_payload),
            "output_payload": dict(row.output_payload) if row.output_payload is not None else None,
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        },
    )


def a2a_task_event_legacy_row(row: A2ATaskEvent) -> LegacyRow:
    return LegacyRow(
        source_table="a2a_task_events",
        source_pk=f"{row.tenant_id}:{row.task_id}:{row.sequence}:{row.id}",
        payload={
            "id": row.id,
            "task_id": row.task_id,
            "tenant_id": row.tenant_id,
            "sequence": row.sequence,
            "event_type": row.event_type,
            "payload": dict(row.payload),
            "created_at": isoformat(row.created_at),
        },
    )


def a2a_push_subscription_legacy_row(row: A2APushSubscription) -> LegacyRow:
    return LegacyRow(
        source_table="a2a_push_subscriptions",
        source_pk=f"{row.tenant_id}:{row.destination}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "destination": row.destination,
            "signing_key_ref": row.signing_key_ref,
            "enabled": row.enabled,
            "created_at": isoformat(row.created_at),
        },
    )


def a2a_access_policy_legacy_row(row: A2AAccessPolicy) -> LegacyRow:
    peer_key = row.peer_agent_id or "global"
    return LegacyRow(
        source_table="a2a_access_policies",
        source_pk=f"{row.tenant_id}:{peer_key}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "peer_agent_id": row.peer_agent_id,
            "allow_inbound": row.allow_inbound,
            "allow_outbound": row.allow_outbound,
            "allowed_skills": list(row.allowed_skills),
            "created_at": isoformat(row.created_at),
        },
    )


def rag_source_legacy_row(row: RagSource) -> LegacyRow:
    return LegacyRow(
        source_table="rag_sources",
        source_pk=f"{row.tenant_id}:{row.collection}:{row.source_uri}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "collection": row.collection,
            "source_uri": row.source_uri,
            "source_type": row.source_type,
            "checksum": row.checksum,
            "metadata": dict(row.source_metadata),
            "created_at": isoformat(row.created_at),
        },
    )


def rag_document_legacy_row(row: RagDocument) -> LegacyRow:
    return LegacyRow(
        source_table="rag_documents",
        source_pk=f"{row.tenant_id}:{row.source_id}:{row.version}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "source_id": row.source_id,
            "collection": row.collection,
            "title": row.title,
            "version": row.version,
            "acl": dict(row.acl),
            "metadata": dict(row.document_metadata),
            "created_at": isoformat(row.created_at),
        },
    )


def rag_chunk_legacy_row(row: RagChunk) -> LegacyRow:
    return LegacyRow(
        source_table="rag_chunks",
        source_pk=f"{row.tenant_id}:{row.document_id}:{row.chunk_index}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "document_id": row.document_id,
            "collection": row.collection,
            "chunk_index": row.chunk_index,
            "content": row.content,
            "content_hash": row.content_hash,
            "embedding": list(row.embedding) if row.embedding is not None else None,
            "metadata": dict(row.chunk_metadata),
            "created_at": isoformat(row.created_at),
        },
    )


def rag_ingestion_candidate_legacy_row(row: RagIngestionCandidateRow) -> LegacyRow:
    return LegacyRow(
        source_table="rag_ingestion_candidates",
        source_pk=row.id,
        payload={
            "id": row.id,
            "run_id": row.run_id,
            "user_id": row.user_id,
            "session_id": row.session_id,
            "channel": row.channel,
            "query": row.query,
            "response": row.response,
            "status": row.status,
            "captured_at": isoformat(row.captured_at),
            "reviewed_at": optional_isoformat(row.reviewed_at),
            "reviewed_by": row.reviewed_by,
            "review_comment": row.review_comment,
            "ingested_document_id": row.ingested_document_id,
        },
    )


def memory_namespace_legacy_row(row: MemoryNamespace) -> LegacyRow:
    return LegacyRow(
        source_table="memory_namespaces",
        source_pk=(
            f"{row.tenant_id}:{row.subject_type}:{row.subject_id}:"
            f"{row.memory_type}:{row.visibility}"
        ),
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "subject_type": row.subject_type,
            "subject_id": row.subject_id,
            "memory_type": row.memory_type,
            "visibility": row.visibility,
            "created_at": isoformat(row.created_at),
        },
    )


def memory_item_legacy_row(row: MemoryItem) -> LegacyRow:
    return LegacyRow(
        source_table="memory_items",
        source_pk=f"{row.tenant_id}:{row.namespace_id}:{row.id}",
        payload={
            "id": row.id,
            "namespace_id": row.namespace_id,
            "tenant_id": row.tenant_id,
            "status": row.status,
            "content": row.content,
            "source_id": row.source_id,
            "confidence": row.confidence,
            "valid_from": optional_isoformat(row.valid_from),
            "valid_until": optional_isoformat(row.valid_until),
            "metadata": dict(row.item_metadata),
            "created_at": isoformat(row.created_at),
        },
    )


def memory_embedding_legacy_row(row: MemoryEmbedding) -> LegacyRow:
    return LegacyRow(
        source_table="memory_embeddings",
        source_pk=f"{row.tenant_id}:{row.memory_id}",
        payload={
            "memory_id": row.memory_id,
            "tenant_id": row.tenant_id,
            "embedding": list(row.embedding),
            "embedding_model": row.embedding_model,
            "created_at": isoformat(row.created_at),
        },
    )


def memory_proposal_legacy_row(row: MemoryProposal) -> LegacyRow:
    return LegacyRow(
        source_table="memory_proposals",
        source_pk=f"{row.tenant_id}:{row.namespace_id}:{row.id}",
        payload={
            "id": row.id,
            "tenant_id": row.tenant_id,
            "namespace_id": row.namespace_id,
            "status": row.status,
            "proposed_content": row.proposed_content,
            "extraction_model": row.extraction_model,
            "extraction_prompt_version": row.extraction_prompt_version,
            "confidence": row.confidence,
            "source_payload": dict(row.source_payload),
            "decision_reason": row.decision_reason,
            "created_at": isoformat(row.created_at),
        },
    )


def isoformat(value: datetime) -> str:
    return value.isoformat()


def decimal_str(value: Decimal) -> str:
    return str(value)


def optional_isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
