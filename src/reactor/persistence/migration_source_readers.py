from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.migration.export import LegacyRow
from reactor.migration.source_readers import (
    a2a_access_policy_legacy_row,
    a2a_agent_card_legacy_row,
    a2a_peer_agent_legacy_row,
    a2a_push_subscription_legacy_row,
    a2a_task_event_legacy_row,
    a2a_task_legacy_row,
    admin_audit_legacy_row,
    agent_run_event_legacy_row,
    agent_run_legacy_row,
    agent_spec_legacy_row,
    alert_instance_legacy_row,
    alert_rule_legacy_row,
    auth_token_revocation_legacy_row,
    auth_user_legacy_row,
    dead_letter_job_legacy_row,
    eval_case_legacy_row,
    eval_result_legacy_row,
    faq_registration_legacy_row,
    feedback_legacy_row,
    idempotency_record_legacy_row,
    inbox_event_legacy_row,
    input_guard_metric_legacy_row,
    input_guard_rule_legacy_row,
    intent_definition_legacy_row,
    mcp_access_policy_legacy_row,
    mcp_server_legacy_row,
    mcp_server_status_legacy_row,
    mcp_tool_snapshot_legacy_row,
    memory_embedding_legacy_row,
    memory_item_legacy_row,
    memory_namespace_legacy_row,
    memory_proposal_legacy_row,
    model_pricing_legacy_row,
    outbox_event_legacy_row,
    output_guard_rule_audit_legacy_row,
    output_guard_rule_legacy_row,
    pending_approval_legacy_row,
    persona_legacy_row,
    proactive_channel_legacy_row,
    prompt_lab_experiment_legacy_row,
    prompt_lab_report_legacy_row,
    prompt_lab_trial_legacy_row,
    prompt_release_legacy_row,
    prompt_template_legacy_row,
    prompt_version_legacy_row,
    rag_chunk_legacy_row,
    rag_document_legacy_row,
    rag_ingestion_candidate_legacy_row,
    rag_source_legacy_row,
    run_queue_legacy_row,
    runtime_setting_legacy_row,
    scheduled_job_dead_letter_legacy_row,
    scheduled_job_execution_legacy_row,
    scheduled_job_legacy_row,
    slack_bot_legacy_row,
    tenant_legacy_row,
    tool_catalog_legacy_row,
    tool_invocation_legacy_row,
    usage_ledger_legacy_row,
    user_identity_legacy_row,
)
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


class AgentRunSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_agent_run_source_query())
            for row in rows:
                yield agent_run_legacy_row(row)


class AgentRunEventSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_agent_run_event_source_query())
            for row in rows:
                yield agent_run_event_legacy_row(row)


class RunQueueSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_run_queue_source_query())
            for row in rows:
                yield run_queue_legacy_row(row)


class DeadLetterJobSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_dead_letter_job_source_query())
            for row in rows:
                yield dead_letter_job_legacy_row(row)


class IdempotencyRecordSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_idempotency_record_source_query())
            for row in rows:
                yield idempotency_record_legacy_row(row)


class OutboxEventSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_outbox_event_source_query())
            for row in rows:
                yield outbox_event_legacy_row(row)


class InboxEventSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_inbox_event_source_query())
            for row in rows:
                yield inbox_event_legacy_row(row)


class RuntimeSettingsSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_runtime_settings_source_query())
            for row in rows:
                yield runtime_setting_legacy_row(row)


class PromptTemplateSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_prompt_template_source_query())
            for row in rows:
                yield prompt_template_legacy_row(row)


class PromptVersionSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_prompt_version_source_query())
            for row in rows:
                yield prompt_version_legacy_row(row)


class PromptReleaseSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_prompt_release_source_query())
            for row in rows:
                yield prompt_release_legacy_row(row)


class PersonaSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_persona_source_query())
            for row in rows:
                yield persona_legacy_row(row)


class AgentSpecSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_agent_spec_source_query())
            for row in rows:
                yield agent_spec_legacy_row(row)


class IntentDefinitionSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_intent_definition_source_query())
            for row in rows:
                yield intent_definition_legacy_row(row)


class PromptLabExperimentSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_prompt_lab_experiment_source_query())
            for row in rows:
                yield prompt_lab_experiment_legacy_row(row)


class PromptLabTrialSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_prompt_lab_trial_source_query())
            for row in rows:
                yield prompt_lab_trial_legacy_row(row)


class PromptLabReportSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_prompt_lab_report_source_query())
            for row in rows:
                yield prompt_lab_report_legacy_row(row)


class SlackBotSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_slack_bot_source_query())
            for row in rows:
                yield slack_bot_legacy_row(row)


class SlackProactiveChannelSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_slack_proactive_channel_source_query())
            for row in rows:
                yield proactive_channel_legacy_row(row)


class SlackFaqRegistrationSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_slack_faq_registration_source_query())
            for row in rows:
                yield faq_registration_legacy_row(row)


class FeedbackSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_feedback_source_query())
            for row in rows:
                yield feedback_legacy_row(row)


class EvalCaseSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_eval_case_source_query())
            for row in rows:
                yield eval_case_legacy_row(row)


class EvalResultSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_eval_result_source_query())
            for row in rows:
                yield eval_result_legacy_row(row)


class ScheduledJobSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_scheduled_job_source_query())
            for row in rows:
                yield scheduled_job_legacy_row(row)


class ScheduledJobExecutionSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_scheduled_job_execution_source_query())
            for row in rows:
                yield scheduled_job_execution_legacy_row(row)


class ScheduledJobDeadLetterSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_scheduled_job_dead_letter_source_query())
            for row in rows:
                yield scheduled_job_dead_letter_legacy_row(row)


class ModelPricingSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_model_pricing_source_query())
            for row in rows:
                yield model_pricing_legacy_row(row)


class UsageLedgerSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_usage_ledger_source_query())
            for row in rows:
                yield usage_ledger_legacy_row(row)


class TenantSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_tenant_source_query())
            for row in rows:
                yield tenant_legacy_row(row)


class AlertRuleSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_alert_rule_source_query())
            for row in rows:
                yield alert_rule_legacy_row(row)


class AlertInstanceSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_alert_instance_source_query())
            for row in rows:
                yield alert_instance_legacy_row(row)


class AuthUserSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_auth_user_source_query())
            for row in rows:
                yield auth_user_legacy_row(row)


class UserIdentitySourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_user_identity_source_query())
            for row in rows:
                yield user_identity_legacy_row(row)


class AuthTokenRevocationSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_auth_token_revocation_source_query())
            for row in rows:
                yield auth_token_revocation_legacy_row(row)


class InputGuardRuleSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_input_guard_rule_source_query())
            for row in rows:
                yield input_guard_rule_legacy_row(row)


class InputGuardMetricSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_input_guard_metric_source_query())
            for row in rows:
                yield input_guard_metric_legacy_row(row)


class OutputGuardRuleSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_output_guard_rule_source_query())
            for row in rows:
                yield output_guard_rule_legacy_row(row)


class OutputGuardRuleAuditSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_output_guard_rule_audit_source_query())
            for row in rows:
                yield output_guard_rule_audit_legacy_row(row)


class AdminAuditSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_admin_audit_source_query())
            for row in rows:
                yield admin_audit_legacy_row(row)


class ToolCatalogSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_tool_catalog_source_query())
            for row in rows:
                yield tool_catalog_legacy_row(row)


class PendingApprovalSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_pending_approval_source_query())
            for row in rows:
                yield pending_approval_legacy_row(row)


class ToolInvocationSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_tool_invocation_source_query())
            for row in rows:
                yield tool_invocation_legacy_row(row)


class McpServerSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_mcp_server_source_query())
            for row in rows:
                yield mcp_server_legacy_row(row)


class McpServerStatusSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_mcp_server_status_source_query())
            for row in rows:
                yield mcp_server_status_legacy_row(row)


class McpToolSnapshotSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_mcp_tool_snapshot_source_query())
            for row in rows:
                yield mcp_tool_snapshot_legacy_row(row)


class McpAccessPolicySourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_mcp_access_policy_source_query())
            for row in rows:
                yield mcp_access_policy_legacy_row(row)


class A2APeerAgentSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_a2a_peer_agent_source_query())
            for row in rows:
                yield a2a_peer_agent_legacy_row(row)


class A2AAgentCardSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_a2a_agent_card_source_query())
            for row in rows:
                yield a2a_agent_card_legacy_row(row)


class A2ATaskSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_a2a_task_source_query())
            for row in rows:
                yield a2a_task_legacy_row(row)


class A2ATaskEventSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_a2a_task_event_source_query())
            for row in rows:
                yield a2a_task_event_legacy_row(row)


class A2APushSubscriptionSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_a2a_push_subscription_source_query())
            for row in rows:
                yield a2a_push_subscription_legacy_row(row)


class A2AAccessPolicySourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_a2a_access_policy_source_query())
            for row in rows:
                yield a2a_access_policy_legacy_row(row)


class RagSourceSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_rag_source_source_query())
            for row in rows:
                yield rag_source_legacy_row(row)


class RagDocumentSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_rag_document_source_query())
            for row in rows:
                yield rag_document_legacy_row(row)


class RagChunkSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_rag_chunk_source_query())
            for row in rows:
                yield rag_chunk_legacy_row(row)


class RagIngestionCandidateSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_rag_ingestion_candidate_source_query())
            for row in rows:
                yield rag_ingestion_candidate_legacy_row(row)


class MemoryNamespaceSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_memory_namespace_source_query())
            for row in rows:
                yield memory_namespace_legacy_row(row)


class MemoryItemSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_memory_item_source_query())
            for row in rows:
                yield memory_item_legacy_row(row)


class MemoryEmbeddingSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_memory_embedding_source_query())
            for row in rows:
                yield memory_embedding_legacy_row(row)


class MemoryProposalSourceReader:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read(self) -> AsyncIterator[LegacyRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_memory_proposal_source_query())
            for row in rows:
                yield memory_proposal_legacy_row(row)


def build_runtime_settings_source_query() -> Any:
    return select(RuntimeSetting).order_by(
        RuntimeSetting.tenant_id.asc(),
        RuntimeSetting.key.asc(),
    )


def build_prompt_template_source_query() -> Any:
    return select(PromptTemplate).order_by(
        PromptTemplate.tenant_id.asc(),
        PromptTemplate.name.asc(),
        PromptTemplate.id.asc(),
    )


def build_prompt_version_source_query() -> Any:
    return select(PromptVersion).order_by(
        PromptVersion.tenant_id.asc(),
        PromptVersion.template_id.asc(),
        PromptVersion.version.asc(),
        PromptVersion.id.asc(),
    )


def build_prompt_release_source_query() -> Any:
    return select(PromptRelease).order_by(
        PromptRelease.tenant_id.asc(),
        PromptRelease.template_id.asc(),
        PromptRelease.environment.asc(),
        PromptRelease.id.asc(),
    )


def build_persona_source_query() -> Any:
    return select(PersonaRow).order_by(
        PersonaRow.is_default.desc(),
        PersonaRow.is_active.desc(),
        PersonaRow.created_at.asc(),
        PersonaRow.name.asc(),
        PersonaRow.id.asc(),
    )


def build_agent_spec_source_query() -> Any:
    return select(AgentSpecRow).order_by(
        AgentSpecRow.enabled.desc(),
        AgentSpecRow.created_at.asc(),
        AgentSpecRow.name.asc(),
        AgentSpecRow.id.asc(),
    )


def build_intent_definition_source_query() -> Any:
    return select(IntentDefinitionModel).order_by(
        IntentDefinitionModel.enabled.desc(),
        IntentDefinitionModel.name.asc(),
    )


def build_prompt_lab_experiment_source_query() -> Any:
    return select(PromptLabExperiment).order_by(
        PromptLabExperiment.tenant_id.asc(),
        PromptLabExperiment.status.asc(),
        PromptLabExperiment.created_at.asc(),
        PromptLabExperiment.id.asc(),
    )


def build_prompt_lab_trial_source_query() -> Any:
    return select(PromptLabTrial).order_by(
        PromptLabTrial.tenant_id.asc(),
        PromptLabTrial.experiment_id.asc(),
        PromptLabTrial.executed_at.asc(),
        PromptLabTrial.id.asc(),
    )


def build_prompt_lab_report_source_query() -> Any:
    return select(PromptLabReport).order_by(
        PromptLabReport.tenant_id.asc(),
        PromptLabReport.generated_at.asc(),
        PromptLabReport.experiment_id.asc(),
    )


def build_agent_run_source_query() -> Any:
    return select(AgentRun).order_by(
        AgentRun.tenant_id.asc(),
        AgentRun.created_at.asc(),
        AgentRun.id.asc(),
    )


def build_agent_run_event_source_query() -> Any:
    return select(AgentRunEvent).order_by(
        AgentRunEvent.tenant_id.asc(),
        AgentRunEvent.run_id.asc(),
        AgentRunEvent.sequence.asc(),
        AgentRunEvent.id.asc(),
    )


def build_run_queue_source_query() -> Any:
    return select(RunQueue).order_by(
        RunQueue.tenant_id.asc(),
        RunQueue.status.asc(),
        RunQueue.available_at.asc(),
        RunQueue.priority.asc(),
        RunQueue.id.asc(),
    )


def build_dead_letter_job_source_query() -> Any:
    return select(DeadLetterJob).order_by(
        DeadLetterJob.tenant_id.asc(),
        DeadLetterJob.created_at.asc(),
        DeadLetterJob.id.asc(),
    )


def build_idempotency_record_source_query() -> Any:
    return select(IdempotencyRecord).order_by(
        IdempotencyRecord.tenant_id.asc(),
        IdempotencyRecord.scope.asc(),
        IdempotencyRecord.key.asc(),
    )


def build_outbox_event_source_query() -> Any:
    return select(OutboxEvent).order_by(
        OutboxEvent.tenant_id.asc(),
        OutboxEvent.status.asc(),
        OutboxEvent.available_at.asc(),
        OutboxEvent.id.asc(),
    )


def build_inbox_event_source_query() -> Any:
    return select(InboxEvent).order_by(
        InboxEvent.tenant_id.asc(),
        InboxEvent.source.asc(),
        InboxEvent.received_at.asc(),
        InboxEvent.id.asc(),
    )


def build_slack_bot_source_query() -> Any:
    return select(SlackBotInstance).order_by(
        SlackBotInstance.tenant_id.asc(),
        SlackBotInstance.name.asc(),
        SlackBotInstance.id.asc(),
    )


def build_slack_proactive_channel_source_query() -> Any:
    return select(SlackProactiveChannel).order_by(
        SlackProactiveChannel.tenant_id.asc(),
        SlackProactiveChannel.channel_id.asc(),
    )


def build_slack_faq_registration_source_query() -> Any:
    return select(ChannelFaqRegistration).order_by(
        ChannelFaqRegistration.tenant_id.asc(),
        ChannelFaqRegistration.channel_id.asc(),
    )


def build_feedback_source_query() -> Any:
    return select(FeedbackRecord).order_by(
        FeedbackRecord.tenant_id.asc(),
        FeedbackRecord.created_at.asc(),
        FeedbackRecord.id.asc(),
    )


def build_eval_case_source_query() -> Any:
    return select(AgentEvalCase).order_by(
        AgentEvalCase.tenant_id.asc(),
        AgentEvalCase.updated_at.asc(),
        AgentEvalCase.id.asc(),
    )


def build_eval_result_source_query() -> Any:
    return select(AgentEvalResult).order_by(
        AgentEvalResult.tenant_id.asc(),
        AgentEvalResult.case_id.asc(),
        AgentEvalResult.evaluated_at.asc(),
        AgentEvalResult.id.asc(),
    )


def build_scheduled_job_source_query() -> Any:
    return select(ScheduledJob).order_by(
        ScheduledJob.tenant_id.asc(),
        ScheduledJob.created_at.asc(),
        ScheduledJob.id.asc(),
    )


def build_scheduled_job_execution_source_query() -> Any:
    return select(ScheduledJobExecution).order_by(
        ScheduledJobExecution.tenant_id.asc(),
        ScheduledJobExecution.job_id.asc(),
        ScheduledJobExecution.started_at.asc(),
        ScheduledJobExecution.id.asc(),
    )


def build_scheduled_job_dead_letter_source_query() -> Any:
    return select(ScheduledJobDeadLetter).order_by(
        ScheduledJobDeadLetter.tenant_id.asc(),
        ScheduledJobDeadLetter.job_id.asc(),
        ScheduledJobDeadLetter.created_at.asc(),
        ScheduledJobDeadLetter.id.asc(),
    )


def build_model_pricing_source_query() -> Any:
    return select(ModelPricing).order_by(
        ModelPricing.provider.asc(),
        ModelPricing.model.asc(),
        ModelPricing.effective_from.asc(),
        ModelPricing.id.asc(),
    )


def build_usage_ledger_source_query() -> Any:
    return select(UsageLedger).order_by(
        UsageLedger.tenant_id.asc(),
        UsageLedger.run_id.asc(),
        UsageLedger.occurred_at.asc(),
        UsageLedger.id.asc(),
    )


def build_tenant_source_query() -> Any:
    return select(Tenant).order_by(Tenant.created_at.asc(), Tenant.id.asc())


def build_alert_rule_source_query() -> Any:
    return select(AlertRuleRow).order_by(
        AlertRuleRow.tenant_id.asc().nulls_first(),
        AlertRuleRow.created_at.asc(),
        AlertRuleRow.id.asc(),
    )


def build_alert_instance_source_query() -> Any:
    return select(AlertInstanceRow).order_by(
        AlertInstanceRow.rule_id.asc(),
        AlertInstanceRow.fired_at.asc(),
        AlertInstanceRow.id.asc(),
    )


def build_auth_user_source_query() -> Any:
    return select(AuthUser).order_by(
        AuthUser.tenant_id.asc(),
        AuthUser.email.asc(),
        AuthUser.id.asc(),
    )


def build_user_identity_source_query() -> Any:
    return select(UserIdentity).order_by(
        UserIdentity.tenant_id.asc(),
        UserIdentity.provider.asc(),
        UserIdentity.external_subject.asc(),
        UserIdentity.id.asc(),
    )


def build_auth_token_revocation_source_query() -> Any:
    return select(AuthTokenRevocation).order_by(
        AuthTokenRevocation.expires_at.asc(),
        AuthTokenRevocation.token_id.asc(),
    )


def build_input_guard_rule_source_query() -> Any:
    return select(InputGuardRule).order_by(
        InputGuardRule.tenant_id.asc(),
        InputGuardRule.priority.desc(),
        InputGuardRule.created_at.asc(),
        InputGuardRule.id.asc(),
    )


def build_input_guard_metric_source_query() -> Any:
    return select(MetricGuardEvent).order_by(
        MetricGuardEvent.time.asc(),
        MetricGuardEvent.id.asc(),
    )


def build_output_guard_rule_source_query() -> Any:
    return select(OutputGuardRule).order_by(
        OutputGuardRule.tenant_id.asc(),
        OutputGuardRule.priority.asc(),
        OutputGuardRule.created_at.asc(),
        OutputGuardRule.id.asc(),
    )


def build_output_guard_rule_audit_source_query() -> Any:
    return select(OutputGuardRuleAudit).order_by(
        OutputGuardRuleAudit.tenant_id.asc(),
        OutputGuardRuleAudit.created_at.asc(),
        OutputGuardRuleAudit.id.asc(),
    )


def build_admin_audit_source_query() -> Any:
    return select(AdminAudit).order_by(
        AdminAudit.tenant_id.asc(),
        AdminAudit.created_at.asc(),
        AdminAudit.id.asc(),
    )


def build_tool_catalog_source_query() -> Any:
    return select(ToolCatalog).order_by(
        ToolCatalog.tenant_id.asc(),
        ToolCatalog.namespace.asc(),
        ToolCatalog.name.asc(),
        ToolCatalog.id.asc(),
    )


def build_pending_approval_source_query() -> Any:
    return select(PendingApproval).order_by(
        PendingApproval.tenant_id.asc(),
        PendingApproval.created_at.asc(),
        PendingApproval.id.asc(),
    )


def build_tool_invocation_source_query() -> Any:
    return select(ToolInvocation).order_by(
        ToolInvocation.tenant_id.asc(),
        ToolInvocation.run_id.asc(),
        ToolInvocation.started_at.asc(),
        ToolInvocation.id.asc(),
    )


def build_mcp_server_source_query() -> Any:
    return select(McpServer).order_by(
        McpServer.tenant_id.asc(),
        McpServer.name.asc(),
        McpServer.id.asc(),
    )


def build_mcp_server_status_source_query() -> Any:
    return select(McpServerStatus).order_by(
        McpServerStatus.tenant_id.asc(),
        McpServerStatus.server_id.asc(),
        McpServerStatus.checked_at.asc(),
    )


def build_mcp_tool_snapshot_source_query() -> Any:
    return select(McpToolSnapshot).order_by(
        McpToolSnapshot.tenant_id.asc(),
        McpToolSnapshot.server_id.asc(),
        McpToolSnapshot.tool_name.asc(),
        McpToolSnapshot.id.asc(),
    )


def build_mcp_access_policy_source_query() -> Any:
    return select(McpAccessPolicy).order_by(
        McpAccessPolicy.tenant_id.asc(),
        McpAccessPolicy.graph_profile.asc(),
        McpAccessPolicy.server_id.asc(),
        McpAccessPolicy.id.asc(),
    )


def build_a2a_peer_agent_source_query() -> Any:
    return select(A2APeerAgent).order_by(
        A2APeerAgent.tenant_id.asc(),
        A2APeerAgent.name.asc(),
        A2APeerAgent.id.asc(),
    )


def build_a2a_agent_card_source_query() -> Any:
    return select(A2AAgentCard).order_by(
        A2AAgentCard.tenant_id.asc(),
        A2AAgentCard.version.asc(),
        A2AAgentCard.id.asc(),
    )


def build_a2a_task_source_query() -> Any:
    return select(A2ATask).order_by(
        A2ATask.tenant_id.asc(),
        A2ATask.created_at.asc(),
        A2ATask.id.asc(),
    )


def build_a2a_task_event_source_query() -> Any:
    return select(A2ATaskEvent).order_by(
        A2ATaskEvent.tenant_id.asc(),
        A2ATaskEvent.task_id.asc(),
        A2ATaskEvent.sequence.asc(),
        A2ATaskEvent.id.asc(),
    )


def build_a2a_push_subscription_source_query() -> Any:
    return select(A2APushSubscription).order_by(
        A2APushSubscription.tenant_id.asc(),
        A2APushSubscription.destination.asc(),
        A2APushSubscription.id.asc(),
    )


def build_a2a_access_policy_source_query() -> Any:
    return select(A2AAccessPolicy).order_by(
        A2AAccessPolicy.tenant_id.asc(),
        A2AAccessPolicy.peer_agent_id.asc(),
        A2AAccessPolicy.id.asc(),
    )


def build_rag_source_source_query() -> Any:
    return select(RagSource).order_by(
        RagSource.tenant_id.asc(),
        RagSource.collection.asc(),
        RagSource.source_uri.asc(),
    )


def build_rag_document_source_query() -> Any:
    return select(RagDocument).order_by(
        RagDocument.tenant_id.asc(),
        RagDocument.collection.asc(),
        RagDocument.source_id.asc(),
        RagDocument.version.asc(),
        RagDocument.id.asc(),
    )


def build_rag_chunk_source_query() -> Any:
    return select(RagChunk).order_by(
        RagChunk.tenant_id.asc(),
        RagChunk.collection.asc(),
        RagChunk.document_id.asc(),
        RagChunk.chunk_index.asc(),
        RagChunk.id.asc(),
    )


def build_rag_ingestion_candidate_source_query() -> Any:
    return select(RagIngestionCandidateRow).order_by(
        RagIngestionCandidateRow.status.asc(),
        RagIngestionCandidateRow.captured_at.asc(),
        RagIngestionCandidateRow.id.asc(),
    )


def build_memory_namespace_source_query() -> Any:
    return select(MemoryNamespace).order_by(
        MemoryNamespace.tenant_id.asc(),
        MemoryNamespace.subject_type.asc(),
        MemoryNamespace.subject_id.asc(),
        MemoryNamespace.memory_type.asc(),
        MemoryNamespace.visibility.asc(),
        MemoryNamespace.id.asc(),
    )


def build_memory_item_source_query() -> Any:
    return select(MemoryItem).order_by(
        MemoryItem.tenant_id.asc(),
        MemoryItem.namespace_id.asc(),
        MemoryItem.created_at.asc(),
        MemoryItem.id.asc(),
    )


def build_memory_embedding_source_query() -> Any:
    return select(MemoryEmbedding).order_by(
        MemoryEmbedding.tenant_id.asc(),
        MemoryEmbedding.memory_id.asc(),
    )


def build_memory_proposal_source_query() -> Any:
    return select(MemoryProposal).order_by(
        MemoryProposal.tenant_id.asc(),
        MemoryProposal.status.asc(),
        MemoryProposal.created_at.asc(),
        MemoryProposal.id.asc(),
    )
