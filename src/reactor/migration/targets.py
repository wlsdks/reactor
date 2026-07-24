from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from inspect import isawaitable
from typing import Any, Protocol, cast

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.admin.tenants import TenantPlan, TenantQuota, TenantRecord, TenantStatus
from reactor.agents.specs import AgentSpecMode, AgentSpecRecord
from reactor.auth.models import (
    TokenRevocationRecord,
    UserIdentityRecord,
    UserRecord,
    normalize_groups,
)
from reactor.auth.rbac import UserRole
from reactor.evals.models import AgentEvalCaseRecord, AgentEvalStoredResultRecord
from reactor.guards.intents import IntentDefinition
from reactor.guards.output_rules import (
    OutputGuardRuleAction,
    OutputGuardRuleAuditAction,
    OutputGuardRuleAuditRecord,
    OutputGuardRuleRecord,
)
from reactor.guards.rules import InputGuardRuleRecord, PatternType, RuleAction
from reactor.migration.import_ import ImportedRow
from reactor.observability.alerts import (
    AlertInstance,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    AlertType,
)
from reactor.observability.pricing import ModelPricing
from reactor.observability.usage_ledger import UsageLedgerRecord
from reactor.persistence.a2a_store import (
    A2AAccessPolicyRecord,
    A2AAgentCardRecord,
    A2APeerAgentRecord,
    A2APushSubscriptionRecord,
    A2ATaskEventRecord,
    A2ATaskMigrationRecord,
)
from reactor.persistence.approval_store import PendingApprovalRecord
from reactor.persistence.durable_store import (
    DeadLetterJobMigrationRecord,
    IdempotencyMigrationRecord,
    InboxEventMigrationRecord,
    OutboxEventMigrationRecord,
    RunQueueMigrationRecord,
)
from reactor.persistence.input_guard_stats_store import InputGuardMetricMigrationRecord
from reactor.persistence.mcp_store import (
    McpAccessPolicyRecord,
    McpServerMigrationRecord,
    McpServerStatusRecord,
    McpToolSnapshotRecord,
)
from reactor.persistence.memory_store import (
    MemoryEmbeddingRecord,
    MemoryItemMigrationRecord,
    MemoryNamespaceMigrationRecord,
    MemoryProposalMigrationRecord,
)
from reactor.persistence.prompt_lab_store import (
    evaluation_config_from_payload,
    evaluation_result_from_payload,
    recommendation_from_payload,
    test_query_from_payload,
    token_usage_from_payload,
    version_summary_from_payload,
)
from reactor.persistence.prompt_store import (
    PromptReleaseRecord,
    PromptTemplateRecord,
    PromptVersionRecord,
)
from reactor.persistence.rag_ingest_store import (
    RagChunkMigrationRecord,
    RagDocumentMigrationRecord,
    RagSourceMigrationRecord,
)
from reactor.persistence.run_store import AgentRunEventMigrationRecord, AgentRunMigrationRecord
from reactor.persistence.tool_invocation_store import ToolInvocationRecord
from reactor.persistence.tool_store import ToolCatalogRecord
from reactor.prompt_lab.models import (
    PromptLabExperimentRecord,
    PromptLabExperimentStatus,
    PromptLabReportRecord,
    PromptLabTrialRecord,
)
from reactor.prompts.personas import PersonaRecord
from reactor.rag.document_management import flatten_acl_metadata
from reactor.rag.ingestion_candidates import (
    RagIngestionCandidate,
    RagIngestionCandidateStatus,
)
from reactor.runtime_settings.service import (
    GLOBAL_TENANT_ID,
    RuntimeSettingType,
    RuntimeSettingUpdate,
)
from reactor.scheduler.service import (
    JobExecutionStatus,
    ScheduledJobDeadLetterRecord,
    ScheduledJobExecutionRecord,
    ScheduledJobRecord,
    ScheduledJobType,
)
from reactor.slack.faq import AutoReplyMode, ChannelFaqRegistration, IngestStatus
from reactor.slack.feedback import Feedback, FeedbackRating
from reactor.slack.models import ProactiveChannelRecord, SlackBotInstanceRecord


class UnsupportedTargetTable(ValueError):
    pass


class MigrationTargetWriter(Protocol):
    target_table: str

    async def write(self, row: ImportedRow) -> None: ...


class RuntimeSettingsStore(Protocol):
    async def set(self, update: RuntimeSettingUpdate) -> object: ...


class PromptMigrationStore(Protocol):
    async def save_template(self, record: PromptTemplateRecord) -> object: ...

    async def save_version(self, record: PromptVersionRecord) -> object: ...

    async def save_release(self, record: PromptReleaseRecord) -> object: ...


class PersonaStore(Protocol):
    async def save(self, record: PersonaRecord) -> object: ...


class AgentSpecStore(Protocol):
    async def save(self, record: AgentSpecRecord) -> object: ...


class IntentDefinitionStore(Protocol):
    async def save(self, intent: IntentDefinition) -> object: ...


class PromptLabMigrationStore(Protocol):
    async def save_experiment(self, record: PromptLabExperimentRecord) -> object: ...

    async def save_trial(self, record: PromptLabTrialRecord) -> object: ...

    async def save_report(self, record: PromptLabReportRecord) -> object: ...


class AgentRunMigrationStore(Protocol):
    async def save_run(self, record: AgentRunMigrationRecord) -> object: ...

    async def save_run_event(self, record: AgentRunEventMigrationRecord) -> object: ...


class DurableMigrationStore(Protocol):
    async def save_run_queue(self, record: RunQueueMigrationRecord) -> object: ...

    async def save_dead_letter_job(self, record: DeadLetterJobMigrationRecord) -> object: ...

    async def save_idempotency_record(self, record: IdempotencyMigrationRecord) -> object: ...

    async def save_outbox_event(self, record: OutboxEventMigrationRecord) -> object: ...

    async def save_inbox_event(self, record: InboxEventMigrationRecord) -> object: ...


class SlackBotStore(Protocol):
    async def save(self, record: SlackBotInstanceRecord) -> object: ...


class ProactiveChannelStore(Protocol):
    async def save(self, record: ProactiveChannelRecord) -> object: ...


class FaqRegistrationStore(Protocol):
    async def save(self, registration: ChannelFaqRegistration) -> object: ...


class FeedbackStore(Protocol):
    async def save(self, feedback: Feedback) -> object: ...


class EvalCaseStore(Protocol):
    async def save(self, record: AgentEvalCaseRecord) -> object: ...


class EvalResultStore(Protocol):
    async def save(self, record: AgentEvalStoredResultRecord) -> object: ...


class SchedulerStore(Protocol):
    async def save(self, job: ScheduledJobRecord) -> object: ...


class ScheduledJobExecutionStore(Protocol):
    async def save(self, execution: ScheduledJobExecutionRecord) -> object: ...


class ScheduledJobDeadLetterStore(Protocol):
    async def save(self, dead_letter: ScheduledJobDeadLetterRecord) -> object: ...


class ModelPricingStore(Protocol):
    async def save(self, pricing: ModelPricing) -> object: ...


class UsageLedgerStore(Protocol):
    async def record(self, record: UsageLedgerRecord) -> object: ...


class TenantStore(Protocol):
    async def find_by_id(self, tenant_id: str) -> TenantRecord | None: ...

    async def save(self, tenant: TenantRecord) -> object: ...


class AlertStore(Protocol):
    async def save_rule(self, rule: AlertRule) -> object: ...

    async def save_alert(self, alert: AlertInstance) -> object: ...


class UserStore(Protocol):
    async def save(self, user: UserRecord) -> object: ...


class UserIdentityStore(Protocol):
    async def upsert(
        self,
        *,
        tenant_id: str,
        provider: str,
        external_subject: str,
        user_id: str,
        metadata: dict[str, Any] | None = None,
        identity_id: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> object: ...


class TokenRevocationMigrationStore(Protocol):
    async def save(self, revocation: TokenRevocationRecord) -> object: ...


class InputGuardRuleStore(Protocol):
    async def save(self, rule: InputGuardRuleRecord) -> object: ...


class InputGuardMetricStore(Protocol):
    async def save_metric(self, record: InputGuardMetricMigrationRecord) -> object: ...


class OutputGuardRuleStore(Protocol):
    async def save(self, rule: OutputGuardRuleRecord) -> object: ...


class OutputGuardRuleAuditStore(Protocol):
    async def save(self, audit: OutputGuardRuleAuditRecord) -> object: ...


class AdminAuditStore(Protocol):
    async def save(self, log: AdminAuditLog, *, tenant_id: str) -> object: ...


class ToolCatalogStore(Protocol):
    async def save(self, record: ToolCatalogRecord) -> object: ...


class PendingApprovalStore(Protocol):
    async def save(self, record: PendingApprovalRecord) -> object: ...


class ToolInvocationStore(Protocol):
    async def save(self, record: ToolInvocationRecord) -> object: ...


class McpMigrationStore(Protocol):
    async def save_server(self, record: McpServerMigrationRecord) -> object: ...

    async def save_server_status(self, record: McpServerStatusRecord) -> object: ...

    async def save_tool_snapshot(self, record: McpToolSnapshotRecord) -> object: ...

    async def save_access_policy(self, record: McpAccessPolicyRecord) -> object: ...


class A2AMigrationStore(Protocol):
    async def save_peer_agent(self, record: A2APeerAgentRecord) -> object: ...

    async def save_agent_card(self, record: A2AAgentCardRecord) -> object: ...

    async def save_task(self, record: A2ATaskMigrationRecord) -> object: ...

    async def save_task_event(self, record: A2ATaskEventRecord) -> object: ...

    async def save_push_subscription(self, record: A2APushSubscriptionRecord) -> object: ...

    async def save_access_policy(self, record: A2AAccessPolicyRecord) -> object: ...


class RagMigrationStore(Protocol):
    async def save_source(self, record: RagSourceMigrationRecord) -> object: ...

    async def save_document(self, record: RagDocumentMigrationRecord) -> object: ...

    async def save_chunk(self, record: RagChunkMigrationRecord) -> object: ...


class RagIngestionCandidateStore(Protocol):
    async def save(self, record: RagIngestionCandidate) -> object: ...


class MetricIngestionBuffer(Protocol):
    def publish(self, event: dict[str, object]) -> bool | Awaitable[bool]: ...


class MemoryMigrationStore(Protocol):
    async def save_namespace(self, record: MemoryNamespaceMigrationRecord) -> object: ...

    async def save_item(self, record: MemoryItemMigrationRecord) -> object: ...

    async def save_embedding(self, record: MemoryEmbeddingRecord) -> object: ...

    async def save_proposal_record(self, record: MemoryProposalMigrationRecord) -> object: ...


class MigrationTargetDispatcher:
    def __init__(self, writers: list[MigrationTargetWriter]) -> None:
        self._writers = {writer.target_table: writer for writer in writers}

    @property
    def target_tables(self) -> tuple[str, ...]:
        return tuple(sorted(self._writers))

    async def write(self, row: ImportedRow) -> None:
        writer = self._writers.get(row.source_table)
        if writer is None:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await writer.write(row)


class RuntimeSettingsTargetWriter:
    target_table = "runtime_settings"

    def __init__(self, store: RuntimeSettingsStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await self._store.set(runtime_setting_update_from_payload(row.payload))


class PromptTemplateTargetWriter:
    target_table = "prompt_templates"

    def __init__(self, store: PromptMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = prompt_template_from_payload(row.payload)
        record.validate()
        await self._store.save_template(record)


class PromptVersionTargetWriter:
    target_table = "prompt_versions"

    def __init__(self, store: PromptMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = prompt_version_from_payload(row.payload)
        record.validate()
        await self._store.save_version(record)


class PromptReleaseTargetWriter:
    target_table = "prompt_releases"

    def __init__(self, store: PromptMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = prompt_release_from_payload(row.payload)
        record.validate()
        await self._store.save_release(record)


class PersonaTargetWriter:
    target_table = "personas"

    def __init__(self, store: PersonaStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = persona_from_payload(row.payload)
        record.validate()
        await self._store.save(record)


class AgentSpecTargetWriter:
    target_table = "agent_specs"

    def __init__(self, store: AgentSpecStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = agent_spec_from_payload(row.payload)
        record.validate()
        await self._store.save(record)


class IntentDefinitionTargetWriter:
    target_table = "intent_definitions"

    def __init__(self, store: IntentDefinitionStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        intent = intent_definition_from_payload(row.payload)
        intent.validate()
        await self._store.save(intent)


class PromptLabExperimentTargetWriter:
    target_table = "prompt_lab_experiments"

    def __init__(self, store: PromptLabMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = prompt_lab_experiment_from_payload(row.payload)
        record.validate()
        await self._store.save_experiment(record)


class PromptLabTrialTargetWriter:
    target_table = "prompt_lab_trials"

    def __init__(self, store: PromptLabMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await self._store.save_trial(prompt_lab_trial_from_payload(row.payload))


class PromptLabReportTargetWriter:
    target_table = "prompt_lab_reports"

    def __init__(self, store: PromptLabMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await self._store.save_report(prompt_lab_report_from_payload(row.payload))


class AgentRunTargetWriter:
    target_table = "agent_runs"

    def __init__(self, store: AgentRunMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = agent_run_from_payload(row.payload)
        record.validate()
        await self._store.save_run(record)


class AgentRunEventTargetWriter:
    target_table = "agent_run_events"

    def __init__(self, store: AgentRunMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = agent_run_event_from_payload(row.payload)
        record.validate()
        await self._store.save_run_event(record)


class RunQueueTargetWriter:
    target_table = "run_queue"

    def __init__(self, store: DurableMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = run_queue_from_payload(row.payload)
        record.validate()
        await self._store.save_run_queue(record)


class DeadLetterJobTargetWriter:
    target_table = "dead_letter_jobs"

    def __init__(self, store: DurableMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = dead_letter_job_from_payload(row.payload)
        record.validate()
        await self._store.save_dead_letter_job(record)


class IdempotencyRecordTargetWriter:
    target_table = "idempotency_records"

    def __init__(self, store: DurableMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = idempotency_record_from_payload(row.payload)
        record.validate()
        await self._store.save_idempotency_record(record)


class OutboxEventTargetWriter:
    target_table = "outbox_events"

    def __init__(self, store: DurableMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = outbox_event_from_payload(row.payload)
        record.validate()
        await self._store.save_outbox_event(record)


class InboxEventTargetWriter:
    target_table = "inbox_events"

    def __init__(self, store: DurableMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = inbox_event_from_payload(row.payload)
        record.validate()
        await self._store.save_inbox_event(record)


class SlackBotTargetWriter:
    target_table = "slack_bot_instances"

    def __init__(self, store: SlackBotStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = slack_bot_record_from_payload(row.payload)
        record.validate()
        await self._store.save(record)


class ProactiveChannelTargetWriter:
    target_table = "slack_proactive_channels"

    def __init__(self, store: ProactiveChannelStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = proactive_channel_record_from_payload(row.payload)
        record.validate()
        await self._store.save(record)


class FaqRegistrationTargetWriter:
    target_table = "channel_faq_registrations"

    def __init__(self, store: FaqRegistrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        registration = faq_registration_from_payload(row.payload)
        registration.validate()
        await self._store.save(registration)


class FeedbackTargetWriter:
    target_table = "feedback"

    def __init__(self, store: FeedbackStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await self._store.save(feedback_from_payload(row.payload))


class EvalCaseTargetWriter:
    target_table = "agent_eval_cases"

    def __init__(self, store: EvalCaseStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = eval_case_from_payload(row.payload)
        record.validate()
        await self._store.save(record)


class EvalResultTargetWriter:
    target_table = "agent_eval_results"

    def __init__(self, store: EvalResultStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = eval_result_from_payload(row.payload)
        record.validate()
        await self._store.save(record)


class ScheduledJobTargetWriter:
    target_table = "scheduled_jobs"

    def __init__(self, store: SchedulerStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        job = scheduled_job_from_payload(row.payload)
        job.validate()
        await self._store.save(job)


class ScheduledJobExecutionTargetWriter:
    target_table = "scheduled_job_executions"

    def __init__(self, store: ScheduledJobExecutionStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await self._store.save(scheduled_job_execution_from_payload(row.payload))


class ScheduledJobDeadLetterTargetWriter:
    target_table = "scheduled_job_dead_letters"

    def __init__(self, store: ScheduledJobDeadLetterStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await self._store.save(scheduled_job_dead_letter_from_payload(row.payload))


class ModelPricingTargetWriter:
    target_table = "model_pricing"

    def __init__(self, store: ModelPricingStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        pricing = model_pricing_from_payload(row.payload)
        pricing.validate()
        await self._store.save(pricing)


class UsageLedgerTargetWriter:
    target_table = "usage_ledger"

    def __init__(self, store: UsageLedgerStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = usage_ledger_from_payload(row.payload)
        record.validate()
        await self._store.record(record)


class TenantTargetWriter:
    target_table = "tenants"

    def __init__(self, store: TenantStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await self._store.save(tenant_from_payload(row.payload))


class TenantSloConfigTargetWriter:
    target_table = "tenant_slo_config"

    def __init__(self, store: TenantStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        tenant_id = required_str(row.payload, "tenant_id")
        tenant = await self._store.find_by_id(tenant_id)
        if tenant is None:
            raise LookupError(f"tenant not found for SLO migration: {tenant_id}")
        metadata = dict(tenant.metadata)
        metadata.update(optional_mapping(row.payload, "metadata"))
        await self._store.save(
            replace(
                tenant,
                slo_availability=optional_float(row.payload, "slo_availability") or 0.995,
                slo_latency_p99_ms=optional_int(row.payload, "slo_latency_p99_ms") or 10000,
                metadata=metadata,
                updated_at=required_datetime(row.payload, "updated_at"),
            )
        )


class AlertRuleTargetWriter:
    target_table = "alert_rules"

    def __init__(self, store: AlertStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        rule = alert_rule_from_payload(row.payload)
        rule.validate()
        await self._store.save_rule(rule)


class AlertInstanceTargetWriter:
    target_table = "alert_instances"

    def __init__(self, store: AlertStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        alert = alert_instance_from_payload(row.payload)
        alert.validate()
        await self._store.save_alert(alert)


class AuthUserTargetWriter:
    target_table = "users"

    def __init__(self, store: UserStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        user = auth_user_from_payload(row.payload)
        user.validate()
        await self._store.save(user)


class UserIdentityTargetWriter:
    target_table = "user_identities"

    def __init__(self, store: UserIdentityStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        identity = user_identity_from_payload(row.payload)
        identity.validate()
        await self._store.upsert(
            tenant_id=identity.tenant_id,
            provider=identity.provider,
            external_subject=identity.external_subject,
            user_id=identity.user_id,
            metadata=identity.metadata,
            identity_id=identity.id,
            created_at=identity.created_at,
            updated_at=identity.updated_at,
        )


class AuthTokenRevocationTargetWriter:
    target_table = "auth_token_revocations"

    def __init__(self, store: TokenRevocationMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        revocation = auth_token_revocation_from_payload(row.payload)
        revocation.validate()
        await self._store.save(revocation)


class InputGuardRuleTargetWriter:
    target_table = "input_guard_rules"

    def __init__(self, store: InputGuardRuleStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        rule = input_guard_rule_from_payload(row.payload)
        rule.validate()
        await self._store.save(rule)


class InputGuardMetricTargetWriter:
    target_table = "metric_guard_events"

    def __init__(self, store: InputGuardMetricStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = input_guard_metric_from_payload(row.payload)
        record.validate()
        await self._store.save_metric(record)


class OutputGuardRuleTargetWriter:
    target_table = "output_guard_rules"

    def __init__(self, store: OutputGuardRuleStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        rule = output_guard_rule_from_payload(row.payload)
        rule.validate()
        await self._store.save(rule)


class OutputGuardRuleAuditTargetWriter:
    target_table = "output_guard_rule_audits"

    def __init__(self, store: OutputGuardRuleAuditStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await self._store.save(output_guard_rule_audit_from_payload(row.payload))


class AdminAuditTargetWriter:
    target_table = "admin_audits"

    def __init__(self, store: AdminAuditStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await self._store.save(
            admin_audit_from_payload(row.payload),
            tenant_id=required_str(row.payload, "tenant_id"),
        )


class ToolCatalogTargetWriter:
    target_table = "tool_catalog"

    def __init__(self, store: ToolCatalogStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = tool_catalog_from_payload(row.payload)
        record.validate()
        await self._store.save(record)


class PendingApprovalTargetWriter:
    target_table = "pending_approvals"

    def __init__(self, store: PendingApprovalStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = pending_approval_from_payload(row.payload)
        record.validate()
        await self._store.save(record)


class ToolInvocationTargetWriter:
    target_table = "tool_invocations"

    def __init__(self, store: ToolInvocationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = tool_invocation_from_payload(row.payload)
        record.validate()
        await self._store.save(record)


class McpServerTargetWriter:
    target_table = "mcp_servers"

    def __init__(self, store: McpMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = mcp_server_from_payload(row.payload)
        record.validate()
        await self._store.save_server(record)


class McpServerStatusTargetWriter:
    target_table = "mcp_server_status"

    def __init__(self, store: McpMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = mcp_server_status_from_payload(row.payload)
        record.validate()
        await self._store.save_server_status(record)


class McpToolSnapshotTargetWriter:
    target_table = "mcp_tool_snapshots"

    def __init__(self, store: McpMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = mcp_tool_snapshot_from_payload(row.payload)
        record.validate()
        await self._store.save_tool_snapshot(record)


class McpAccessPolicyTargetWriter:
    target_table = "mcp_access_policies"

    def __init__(self, store: McpMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = mcp_access_policy_from_payload(row.payload)
        record.validate()
        await self._store.save_access_policy(record)


class A2APeerAgentTargetWriter:
    target_table = "a2a_peer_agents"

    def __init__(self, store: A2AMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = a2a_peer_agent_from_payload(row.payload)
        record.validate()
        await self._store.save_peer_agent(record)


class A2AAgentCardTargetWriter:
    target_table = "a2a_agent_cards"

    def __init__(self, store: A2AMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = a2a_agent_card_from_payload(row.payload)
        record.validate()
        await self._store.save_agent_card(record)


class A2ATaskTargetWriter:
    target_table = "a2a_tasks"

    def __init__(self, store: A2AMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = a2a_task_from_payload(row.payload)
        record.validate()
        await self._store.save_task(record)


class A2ATaskEventTargetWriter:
    target_table = "a2a_task_events"

    def __init__(self, store: A2AMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = a2a_task_event_from_payload(row.payload)
        record.validate()
        await self._store.save_task_event(record)


class A2APushSubscriptionTargetWriter:
    target_table = "a2a_push_subscriptions"

    def __init__(self, store: A2AMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = a2a_push_subscription_from_payload(row.payload)
        record.validate()
        await self._store.save_push_subscription(record)


class A2AAccessPolicyTargetWriter:
    target_table = "a2a_access_policies"

    def __init__(self, store: A2AMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = a2a_access_policy_from_payload(row.payload)
        record.validate()
        await self._store.save_access_policy(record)


class RagSourceTargetWriter:
    target_table = "rag_sources"

    def __init__(self, store: RagMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = rag_source_from_payload(row.payload)
        record.validate()
        await self._store.save_source(record)


class RagDocumentTargetWriter:
    target_table = "rag_documents"

    def __init__(self, store: RagMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = rag_document_from_payload(row.payload)
        record.validate()
        await self._store.save_document(record)


class RagChunkTargetWriter:
    target_table = "rag_chunks"

    def __init__(self, store: RagMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = rag_chunk_from_payload(row.payload)
        record.validate()
        await self._store.save_chunk(record)


class RagIngestionCandidateTargetWriter:
    target_table = "rag_ingestion_candidates"

    def __init__(self, store: RagIngestionCandidateStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = rag_ingestion_candidate_from_payload(row.payload)
        record.validate()
        await self._store.save(record)


class MetricAgentExecutionTargetWriter:
    target_table = "metric_agent_executions"

    def __init__(self, buffer: MetricIngestionBuffer) -> None:
        self._buffer = buffer

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await publish_metric_event_or_raise(
            self._buffer,
            row,
            event_name="metric_agent_executions",
        )


class MetricSessionTargetWriter:
    target_table = "metric_sessions"

    def __init__(self, buffer: MetricIngestionBuffer) -> None:
        self._buffer = buffer

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await publish_metric_event_or_raise(self._buffer, row, event_name="metric_sessions")


class MetricSpanTargetWriter:
    target_table = "metric_spans"

    def __init__(self, buffer: MetricIngestionBuffer) -> None:
        self._buffer = buffer

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await publish_metric_event_or_raise(self._buffer, row, event_name="metric_spans")


class MetricAuditTrailTargetWriter:
    target_table = "metric_audit_trail"

    def __init__(self, buffer: MetricIngestionBuffer) -> None:
        self._buffer = buffer

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await publish_metric_event_or_raise(self._buffer, row, event_name="metric_audit_trail")


class MetricQuotaEventTargetWriter:
    target_table = "metric_quota_events"

    def __init__(self, buffer: MetricIngestionBuffer) -> None:
        self._buffer = buffer

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await publish_metric_event_or_raise(self._buffer, row, event_name="metric_quota_events")


class MetricHitlEventTargetWriter:
    target_table = "metric_hitl_events"

    def __init__(self, buffer: MetricIngestionBuffer) -> None:
        self._buffer = buffer

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await publish_metric_event_or_raise(self._buffer, row, event_name="metric_hitl_events")


class MetricToolCallTargetWriter:
    target_table = "metric_tool_calls"

    def __init__(self, buffer: MetricIngestionBuffer) -> None:
        self._buffer = buffer

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await publish_metric_event_or_raise(self._buffer, row, event_name="metric_tool_calls")


class MetricMcpHealthTargetWriter:
    target_table = "metric_mcp_health"

    def __init__(self, buffer: MetricIngestionBuffer) -> None:
        self._buffer = buffer

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await publish_metric_event_or_raise(self._buffer, row, event_name="metric_mcp_health")


class MetricEvalResultTargetWriter:
    target_table = "metric_eval_results"

    def __init__(self, buffer: MetricIngestionBuffer) -> None:
        self._buffer = buffer

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        await publish_metric_event_or_raise(self._buffer, row, event_name="metric_eval_results")


async def publish_metric_event_or_raise(
    buffer: MetricIngestionBuffer,
    row: ImportedRow,
    *,
    event_name: str,
) -> None:
    accepted = buffer.publish(dict(row.payload))
    if isawaitable(accepted):
        accepted = await accepted
    if not bool(accepted):
        raise RuntimeError(f"metric ingestion buffer rejected {event_name} event")


class MemoryNamespaceTargetWriter:
    target_table = "memory_namespaces"

    def __init__(self, store: MemoryMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = memory_namespace_from_payload(row.payload)
        record.validate()
        await self._store.save_namespace(record)


class MemoryItemTargetWriter:
    target_table = "memory_items"

    def __init__(self, store: MemoryMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = memory_item_from_payload(row.payload)
        record.validate()
        await self._store.save_item(record)


class MemoryEmbeddingTargetWriter:
    target_table = "memory_embeddings"

    def __init__(self, store: MemoryMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = memory_embedding_from_payload(row.payload)
        record.validate()
        await self._store.save_embedding(record)


class MemoryProposalTargetWriter:
    target_table = "memory_proposals"

    def __init__(self, store: MemoryMigrationStore) -> None:
        self._store = store

    async def write(self, row: ImportedRow) -> None:
        if row.source_table != self.target_table:
            raise UnsupportedTargetTable(f"unsupported target table: {row.source_table}")
        record = memory_proposal_from_payload(row.payload)
        record.validate()
        await self._store.save_proposal_record(record)


def runtime_setting_update_from_payload(payload: Mapping[str, Any]) -> RuntimeSettingUpdate:
    metadata = payload.get("metadata")
    return RuntimeSettingUpdate(
        tenant_id=optional_str(payload, "tenant_id") or GLOBAL_TENANT_ID,
        key=required_str(payload, "key"),
        value=required_str(payload, "value"),
        value_type=runtime_setting_type(optional_str(payload, "value_type") or "STRING"),
        category=optional_str(payload, "category") or "general",
        description=optional_str(payload, "description"),
        updated_by=optional_str(payload, "updated_by") or "migration",
        metadata=cast(Mapping[str, Any], metadata) if isinstance(metadata, Mapping) else {},
    )


def prompt_template_from_payload(payload: Mapping[str, Any]) -> PromptTemplateRecord:
    return PromptTemplateRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        name=required_str(payload, "name"),
        graph_profile=required_str(payload, "graph_profile"),
        description=optional_str(payload, "description"),
        created_by=required_str(payload, "created_by"),
        created_at=required_datetime(payload, "created_at"),
        updated_at=required_datetime(payload, "updated_at"),
    )


def prompt_version_from_payload(payload: Mapping[str, Any]) -> PromptVersionRecord:
    return PromptVersionRecord(
        id=required_str(payload, "id"),
        template_id=required_str(payload, "template_id"),
        tenant_id=required_str(payload, "tenant_id"),
        version=required_str(payload, "version"),
        system_policy=required_str(payload, "system_policy"),
        developer_policy=optional_str(payload, "developer_policy") or "",
        examples=optional_str_list(payload, "examples"),
        metadata=optional_mapping(payload, "metadata"),
        content_hash=required_str(payload, "content_hash"),
        created_by=required_str(payload, "created_by"),
        created_at=required_datetime(payload, "created_at"),
    )


def prompt_release_from_payload(payload: Mapping[str, Any]) -> PromptReleaseRecord:
    return PromptReleaseRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        template_id=required_str(payload, "template_id"),
        version_id=required_str(payload, "version_id"),
        environment=required_str(payload, "environment"),
        released_by=required_str(payload, "released_by"),
        released_at=required_datetime(payload, "released_at"),
        metadata=optional_mapping(payload, "metadata"),
    )


def persona_from_payload(payload: Mapping[str, Any]) -> PersonaRecord:
    return PersonaRecord(
        id=required_str(payload, "id"),
        name=required_str(payload, "name"),
        system_prompt=required_str(payload, "system_prompt"),
        is_default=optional_bool(payload, "is_default", default=False),
        description=optional_str(payload, "description"),
        response_guideline=optional_str(payload, "response_guideline"),
        welcome_message=optional_str(payload, "welcome_message"),
        icon=optional_str(payload, "icon"),
        is_active=optional_bool(payload, "is_active", default=True),
        prompt_template_id=optional_str(payload, "prompt_template_id"),
        created_at=required_datetime(payload, "created_at"),
        updated_at=required_datetime(payload, "updated_at"),
    )


def agent_spec_from_payload(payload: Mapping[str, Any]) -> AgentSpecRecord:
    return AgentSpecRecord(
        id=required_str(payload, "id"),
        name=required_str(payload, "name"),
        description=optional_str(payload, "description") or "",
        tool_names=tuple(optional_str_list(payload, "tool_names")),
        keywords=tuple(optional_str_list(payload, "keywords")),
        system_prompt=optional_str(payload, "system_prompt"),
        mode=agent_spec_mode(required_str(payload, "mode")),
        independent_execution=optional_bool(
            payload,
            "independent_execution",
            default=True,
        ),
        enabled=optional_bool(payload, "enabled", default=True),
        created_at=required_datetime(payload, "created_at"),
        updated_at=required_datetime(payload, "updated_at"),
    )


def intent_definition_from_payload(payload: Mapping[str, Any]) -> IntentDefinition:
    return IntentDefinition(
        name=required_str(payload, "name"),
        description=required_str(payload, "description"),
        examples=tuple(optional_str_list(payload, "examples")),
        keywords=tuple(optional_str_list(payload, "keywords")),
        profile=required_str(payload, "profile"),
        enabled=optional_bool(payload, "enabled", default=True),
        created_at=required_datetime(payload, "created_at"),
        updated_at=required_datetime(payload, "updated_at"),
    )


def prompt_lab_experiment_from_payload(payload: Mapping[str, Any]) -> PromptLabExperimentRecord:
    return PromptLabExperimentRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        name=required_str(payload, "name"),
        description=optional_str(payload, "description") or "",
        template_id=required_str(payload, "template_id"),
        baseline_version_id=required_str(payload, "baseline_version_id"),
        candidate_version_ids=optional_str_list(payload, "candidate_version_ids"),
        test_queries=[
            test_query_from_payload(item) for item in optional_mapping_list(payload, "test_queries")
        ],
        evaluation_config=evaluation_config_from_payload(
            optional_mapping(payload, "evaluation_config")
        ),
        model=optional_str(payload, "model"),
        judge_model=optional_str(payload, "judge_model"),
        temperature=optional_float(payload, "temperature") or 0.3,
        repetitions=required_int(payload, "repetitions"),
        auto_generated=optional_bool(payload, "auto_generated", default=False),
        status=prompt_lab_experiment_status(required_str(payload, "status")),
        created_by=required_str(payload, "created_by"),
        created_at=required_datetime(payload, "created_at"),
        started_at=optional_datetime(payload, "started_at"),
        completed_at=optional_datetime(payload, "completed_at"),
        error_message=optional_str(payload, "error_message"),
    )


def prompt_lab_trial_from_payload(payload: Mapping[str, Any]) -> PromptLabTrialRecord:
    return PromptLabTrialRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        experiment_id=required_str(payload, "experiment_id"),
        prompt_version_id=required_str(payload, "prompt_version_id"),
        prompt_version_number=required_int(payload, "prompt_version_number"),
        test_query=test_query_from_payload(required_mapping(payload, "test_query")),
        repetition_index=required_int(payload, "repetition_index"),
        response=optional_str(payload, "response"),
        success=optional_bool(payload, "success", default=False),
        error_message=optional_str(payload, "error_message"),
        tools_used=optional_str_list(payload, "tools_used"),
        token_usage=token_usage_from_payload(optional_mapping_or_none(payload, "token_usage")),
        duration_ms=required_int(payload, "duration_ms"),
        evaluations=[
            evaluation_result_from_payload(item)
            for item in optional_mapping_list(payload, "evaluations")
        ],
        executed_at=required_datetime(payload, "executed_at"),
    )


def prompt_lab_report_from_payload(payload: Mapping[str, Any]) -> PromptLabReportRecord:
    return PromptLabReportRecord(
        experiment_id=required_str(payload, "experiment_id"),
        tenant_id=required_str(payload, "tenant_id"),
        experiment_name=required_str(payload, "experiment_name"),
        generated_at=required_datetime(payload, "generated_at"),
        total_trials=required_int(payload, "total_trials"),
        version_summaries=[
            version_summary_from_payload(item)
            for item in optional_mapping_list(payload, "version_summaries")
        ],
        recommendation=recommendation_from_payload(required_mapping(payload, "recommendation")),
    )


def agent_run_from_payload(payload: Mapping[str, Any]) -> AgentRunMigrationRecord:
    return AgentRunMigrationRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        user_id=required_str(payload, "user_id"),
        thread_id=required_str(payload, "thread_id"),
        checkpoint_ns=required_str(payload, "checkpoint_ns"),
        status=required_str(payload, "status"),
        input_text=required_str(payload, "input_text"),
        response_text=optional_str(payload, "response_text"),
        error_code=optional_str(payload, "error_code"),
        metadata=optional_mapping(payload, "metadata"),
        created_at=required_datetime(payload, "created_at"),
        updated_at=required_datetime(payload, "updated_at"),
    )


def agent_run_event_from_payload(payload: Mapping[str, Any]) -> AgentRunEventMigrationRecord:
    return AgentRunEventMigrationRecord(
        id=optional_int(payload, "id"),
        run_id=required_str(payload, "run_id"),
        tenant_id=required_str(payload, "tenant_id"),
        sequence=required_int(payload, "sequence"),
        event_type=required_str(payload, "event_type"),
        payload=optional_mapping(payload, "payload"),
        created_at=required_datetime(payload, "created_at"),
    )


def run_queue_from_payload(payload: Mapping[str, Any]) -> RunQueueMigrationRecord:
    return RunQueueMigrationRecord(
        id=required_str(payload, "id"),
        run_id=required_str(payload, "run_id"),
        tenant_id=required_str(payload, "tenant_id"),
        status=required_str(payload, "status"),
        priority=required_int(payload, "priority"),
        attempt=required_int(payload, "attempt"),
        max_attempts=required_int(payload, "max_attempts"),
        available_at=required_datetime(payload, "available_at"),
        lease_owner=optional_str(payload, "lease_owner"),
        lease_expires_at=optional_datetime(payload, "lease_expires_at"),
        fencing_token=required_int(payload, "fencing_token"),
        payload=optional_mapping(payload, "payload"),
        created_at=required_datetime(payload, "created_at"),
        updated_at=required_datetime(payload, "updated_at"),
    )


def dead_letter_job_from_payload(payload: Mapping[str, Any]) -> DeadLetterJobMigrationRecord:
    return DeadLetterJobMigrationRecord(
        id=required_str(payload, "id"),
        queue_id=required_str(payload, "queue_id"),
        run_id=required_str(payload, "run_id"),
        tenant_id=required_str(payload, "tenant_id"),
        reason=required_str(payload, "reason"),
        last_checkpoint_id=optional_str(payload, "last_checkpoint_id"),
        trace_id=optional_str(payload, "trace_id"),
        payload=optional_mapping(payload, "payload"),
        created_at=required_datetime(payload, "created_at"),
    )


def idempotency_record_from_payload(payload: Mapping[str, Any]) -> IdempotencyMigrationRecord:
    return IdempotencyMigrationRecord(
        key=required_str(payload, "key"),
        tenant_id=required_str(payload, "tenant_id"),
        scope=required_str(payload, "scope"),
        request_checksum=required_str(payload, "request_checksum"),
        status=required_str(payload, "status"),
        response_payload=optional_mapping_or_none(payload, "response_payload"),
        locked_until=optional_datetime(payload, "locked_until"),
        created_at=required_datetime(payload, "created_at"),
        updated_at=required_datetime(payload, "updated_at"),
    )


def outbox_event_from_payload(payload: Mapping[str, Any]) -> OutboxEventMigrationRecord:
    return OutboxEventMigrationRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        run_id=optional_str(payload, "run_id"),
        destination=required_str(payload, "destination"),
        event_type=required_str(payload, "event_type"),
        idempotency_key=required_str(payload, "idempotency_key"),
        status=required_str(payload, "status"),
        attempt=required_int(payload, "attempt"),
        max_attempts=required_int(payload, "max_attempts"),
        available_at=required_datetime(payload, "available_at"),
        payload=optional_mapping(payload, "payload"),
        last_error=optional_str(payload, "last_error"),
        lease_owner=optional_str(payload, "lease_owner"),
        lease_expires_at=optional_datetime(payload, "lease_expires_at"),
        created_at=required_datetime(payload, "created_at"),
        updated_at=required_datetime(payload, "updated_at"),
    )


def inbox_event_from_payload(payload: Mapping[str, Any]) -> InboxEventMigrationRecord:
    return InboxEventMigrationRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        source=required_str(payload, "source"),
        source_event_id=required_str(payload, "source_event_id"),
        event_type=required_str(payload, "event_type"),
        status=required_str(payload, "status"),
        payload=optional_mapping(payload, "payload"),
        received_at=required_datetime(payload, "received_at"),
        processed_at=optional_datetime(payload, "processed_at"),
    )


def slack_bot_record_from_payload(payload: Mapping[str, Any]) -> SlackBotInstanceRecord:
    return SlackBotInstanceRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        name=required_str(payload, "name"),
        bot_token=required_str(payload, "bot_token"),
        app_token=required_str(payload, "app_token"),
        persona_id=required_str(payload, "persona_id"),
        default_channel=optional_str(payload, "default_channel"),
        enabled=optional_bool(payload, "enabled", default=True),
        created_at=optional_datetime(payload, "created_at") or datetime.now(UTC),
        updated_at=optional_datetime(payload, "updated_at") or datetime.now(UTC),
    )


def proactive_channel_record_from_payload(payload: Mapping[str, Any]) -> ProactiveChannelRecord:
    return ProactiveChannelRecord(
        tenant_id=required_str(payload, "tenant_id"),
        channel_id=required_str(payload, "channel_id"),
        channel_name=optional_str(payload, "channel_name"),
        added_at=optional_datetime(payload, "added_at") or datetime.now(UTC),
    )


def faq_registration_from_payload(payload: Mapping[str, Any]) -> ChannelFaqRegistration:
    return ChannelFaqRegistration(
        tenant_id=required_str(payload, "tenant_id"),
        channel_id=required_str(payload, "channel_id"),
        channel_name=optional_str(payload, "channel_name"),
        enabled=optional_bool(payload, "enabled", default=True),
        auto_reply_mode=auto_reply_mode(optional_str(payload, "auto_reply_mode") or "mention"),
        confidence_threshold=optional_float(payload, "confidence_threshold") or 0.75,
        days_back=optional_int(payload, "days_back") or 30,
        re_ingest_interval_hours=optional_int(payload, "re_ingest_interval_hours") or 24,
        last_ingested_at=optional_datetime(payload, "last_ingested_at"),
        last_message_count=optional_int(payload, "last_message_count"),
        last_chunk_count=optional_int(payload, "last_chunk_count"),
        last_status=optional_str(payload, "last_status") or IngestStatus.PENDING.value,
        last_error=optional_str(payload, "last_error"),
        registered_by=optional_str(payload, "registered_by"),
        registered_at=optional_datetime(payload, "registered_at") or datetime.now(UTC),
        updated_at=optional_datetime(payload, "updated_at") or datetime.now(UTC),
    )


def feedback_from_payload(payload: Mapping[str, Any]) -> Feedback:
    return Feedback(
        feedback_id=required_str(payload, "feedback_id"),
        tenant_id=required_str(payload, "tenant_id"),
        query=required_str(payload, "query"),
        response=required_str(payload, "response"),
        rating=feedback_rating(required_str(payload, "rating")),
        source=optional_str(payload, "source") or "slack_button",
        comment=optional_str(payload, "comment"),
        session_id=optional_str(payload, "session_id") or "",
        run_id=optional_str(payload, "run_id"),
        user_id=optional_str(payload, "user_id") or "",
        intent=optional_str(payload, "intent"),
        domain=optional_str(payload, "domain"),
        model=optional_str(payload, "model"),
        prompt_version=optional_int(payload, "prompt_version"),
        tools_used=optional_str_list(payload, "tools_used"),
        duration_ms=optional_int(payload, "duration_ms"),
        tags=optional_str_list(payload, "tags"),
        review_status=optional_str(payload, "review_status") or "inbox",
        review_tags=optional_str_list(payload, "review_tags"),
        reviewed_by=optional_str(payload, "reviewed_by"),
        reviewed_at=optional_datetime(payload, "reviewed_at"),
        review_note=optional_str(payload, "review_note"),
        version=optional_int(payload, "version") or 1,
        created_at=optional_datetime(payload, "created_at") or datetime.now(UTC),
        updated_at=optional_datetime(payload, "updated_at") or datetime.now(UTC),
    )


def eval_case_from_payload(payload: Mapping[str, Any]) -> AgentEvalCaseRecord:
    return AgentEvalCaseRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        name=required_str(payload, "name"),
        user_input=required_str(payload, "user_input"),
        expected_answer_contains=optional_str_tuple(payload, "expected_answer_contains"),
        forbidden_answer_contains=optional_str_tuple(payload, "forbidden_answer_contains"),
        expected_tool_names=optional_str_tuple(payload, "expected_tool_names"),
        forbidden_tool_names=optional_str_tuple(payload, "forbidden_tool_names"),
        expected_exposed_tool_names=optional_str_tuple(payload, "expected_exposed_tool_names"),
        forbidden_exposed_tool_names=optional_str_tuple(payload, "forbidden_exposed_tool_names"),
        max_tool_exposure_count=optional_int(payload, "max_tool_exposure_count"),
        agent_type=optional_str(payload, "agent_type"),
        model=optional_str(payload, "model"),
        enabled=optional_bool(payload, "enabled", default=True),
        tags=optional_str_tuple(payload, "tags"),
        min_score=optional_float(payload, "min_score") or 1.0,
        source_run_id=optional_str(payload, "source_run_id"),
        created_at=optional_datetime(payload, "created_at") or datetime.now(UTC),
        updated_at=optional_datetime(payload, "updated_at") or datetime.now(UTC),
    )


def eval_result_from_payload(payload: Mapping[str, Any]) -> AgentEvalStoredResultRecord:
    return AgentEvalStoredResultRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        case_id=required_str(payload, "case_id"),
        run_id=optional_str(payload, "run_id"),
        tier=optional_str(payload, "tier") or "deterministic",
        passed=optional_bool(payload, "passed", default=False),
        score=optional_float(payload, "score") or 0.0,
        reasons=optional_str_tuple(payload, "reasons"),
        evaluated_at=optional_datetime(payload, "evaluated_at") or datetime.now(UTC),
    )


def scheduled_job_from_payload(payload: Mapping[str, Any]) -> ScheduledJobRecord:
    return ScheduledJobRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        name=required_str(payload, "name"),
        description=optional_str(payload, "description"),
        cron_expression=required_str(payload, "cron_expression"),
        timezone=optional_str(payload, "timezone") or "Asia/Seoul",
        job_type=scheduled_job_type(optional_str(payload, "job_type") or "MCP_TOOL"),
        mcp_server_name=optional_str(payload, "mcp_server_name"),
        tool_name=optional_str(payload, "tool_name"),
        tool_arguments=optional_mapping(payload, "tool_arguments"),
        agent_prompt=optional_str(payload, "agent_prompt"),
        persona_id=optional_str(payload, "persona_id"),
        agent_system_prompt=optional_str(payload, "agent_system_prompt"),
        agent_model=optional_str(payload, "agent_model"),
        agent_max_tool_calls=optional_int(payload, "agent_max_tool_calls"),
        tags=frozenset(optional_str_list(payload, "tags")),
        slack_channel_id=optional_str(payload, "slack_channel_id"),
        teams_webhook_url=optional_str(payload, "teams_webhook_url"),
        retry_on_failure=optional_bool(payload, "retry_on_failure", default=False),
        max_retry_count=optional_int(payload, "max_retry_count") or 3,
        execution_timeout_ms=optional_int(payload, "execution_timeout_ms"),
        enabled=optional_bool(payload, "enabled", default=True),
        last_run_at=optional_datetime(payload, "last_run_at"),
        last_status=optional_execution_status(payload, "last_status"),
        last_result=optional_str(payload, "last_result"),
        created_at=optional_datetime(payload, "created_at") or datetime.now(UTC),
        updated_at=optional_datetime(payload, "updated_at") or datetime.now(UTC),
    )


def scheduled_job_execution_from_payload(
    payload: Mapping[str, Any],
) -> ScheduledJobExecutionRecord:
    return ScheduledJobExecutionRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        job_id=required_str(payload, "job_id"),
        job_name=required_str(payload, "job_name"),
        job_type=optional_job_type(payload, "job_type"),
        status=execution_status(required_str(payload, "status")),
        result=optional_str(payload, "result"),
        duration_ms=optional_int(payload, "duration_ms") or 0,
        dry_run=optional_bool(payload, "dry_run", default=False),
        started_at=optional_datetime(payload, "started_at") or datetime.now(UTC),
        completed_at=optional_datetime(payload, "completed_at"),
    )


def scheduled_job_dead_letter_from_payload(
    payload: Mapping[str, Any],
) -> ScheduledJobDeadLetterRecord:
    return ScheduledJobDeadLetterRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        job_id=required_str(payload, "job_id"),
        job_name=required_str(payload, "job_name"),
        job_type=optional_job_type(payload, "job_type"),
        reason=required_str(payload, "reason"),
        result=optional_str(payload, "result"),
        dry_run=optional_bool(payload, "dry_run", default=False),
        created_at=optional_datetime(payload, "created_at") or datetime.now(UTC),
    )


def model_pricing_from_payload(payload: Mapping[str, Any]) -> ModelPricing:
    return ModelPricing(
        id=required_str(payload, "id"),
        provider=required_str(payload, "provider"),
        model=required_str(payload, "model"),
        prompt_price_per_1m=required_decimal(payload, "prompt_price_per_1m"),
        completion_price_per_1m=required_decimal(payload, "completion_price_per_1m"),
        cached_input_price_per_1m=required_decimal(payload, "cached_input_price_per_1m"),
        reasoning_price_per_1m=required_decimal(payload, "reasoning_price_per_1m"),
        batch_prompt_price_per_1m=required_decimal(payload, "batch_prompt_price_per_1m"),
        batch_completion_price_per_1m=required_decimal(payload, "batch_completion_price_per_1m"),
        effective_from=required_datetime(payload, "effective_from"),
        effective_to=optional_datetime(payload, "effective_to"),
    )


def usage_ledger_from_payload(payload: Mapping[str, Any]) -> UsageLedgerRecord:
    return UsageLedgerRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        run_id=required_str(payload, "run_id"),
        provider=required_str(payload, "provider"),
        model=required_str(payload, "model"),
        step_type=required_str(payload, "step_type"),
        prompt_tokens=optional_int(payload, "prompt_tokens") or 0,
        cached_tokens=optional_int(payload, "cached_tokens") or 0,
        completion_tokens=optional_int(payload, "completion_tokens") or 0,
        reasoning_tokens=optional_int(payload, "reasoning_tokens") or 0,
        total_tokens=optional_int(payload, "total_tokens") or 0,
        estimated_cost_usd=required_decimal(payload, "estimated_cost_usd"),
        occurred_at=required_datetime(payload, "occurred_at"),
    )


def tenant_from_payload(payload: Mapping[str, Any]) -> TenantRecord:
    return TenantRecord(
        id=required_str(payload, "id"),
        name=required_str(payload, "name"),
        slug=required_str(payload, "slug"),
        plan=TenantPlan(required_str(payload, "plan")),
        status=TenantStatus(required_str(payload, "status")),
        quota=TenantQuota(
            max_requests_per_month=optional_int(payload, "max_requests_per_month") or 1000,
            max_tokens_per_month=optional_int(payload, "max_tokens_per_month") or 1000000,
            max_users=optional_int(payload, "max_users") or 5,
            max_agents=optional_int(payload, "max_agents") or 3,
            max_mcp_servers=optional_int(payload, "max_mcp_servers") or 5,
        ),
        billing_cycle_start=optional_int(payload, "billing_cycle_start") or 1,
        billing_email=optional_str(payload, "billing_email"),
        slo_availability=optional_float(payload, "slo_availability") or 0.995,
        slo_latency_p99_ms=optional_int(payload, "slo_latency_p99_ms") or 10000,
        metadata=optional_mapping(payload, "metadata"),
        created_at=required_datetime(payload, "created_at"),
        updated_at=required_datetime(payload, "updated_at"),
    )


def alert_rule_from_payload(payload: Mapping[str, Any]) -> AlertRule:
    return AlertRule(
        id=required_str(payload, "id"),
        tenant_id=optional_str(payload, "tenant_id"),
        name=required_str(payload, "name"),
        description=optional_str(payload, "description") or "",
        type=alert_type(required_str(payload, "type")),
        severity=alert_severity(required_str(payload, "severity")),
        metric=required_str(payload, "metric"),
        threshold=optional_float(payload, "threshold") or 0.0,
        window_minutes=optional_int(payload, "window_minutes") or 15,
        enabled=optional_bool(payload, "enabled", default=True),
        platform_only=optional_bool(payload, "platform_only", default=False),
        created_at=required_datetime(payload, "created_at"),
    )


def alert_instance_from_payload(payload: Mapping[str, Any]) -> AlertInstance:
    return AlertInstance(
        id=required_str(payload, "id"),
        rule_id=required_str(payload, "rule_id"),
        tenant_id=optional_str(payload, "tenant_id"),
        severity=alert_severity(required_str(payload, "severity")),
        status=alert_status(required_str(payload, "status")),
        message=required_str(payload, "message"),
        metric_value=optional_float(payload, "metric_value") or 0.0,
        threshold=optional_float(payload, "threshold") or 0.0,
        fired_at=required_datetime(payload, "fired_at"),
        resolved_at=optional_datetime(payload, "resolved_at"),
        acknowledged_by=optional_str(payload, "acknowledged_by"),
    )


def auth_user_from_payload(payload: Mapping[str, Any]) -> UserRecord:
    return UserRecord(
        id=required_str(payload, "id"),
        email=required_str(payload, "email"),
        name=required_str(payload, "name"),
        password_hash=required_str(payload, "password_hash"),
        role=user_role(required_str(payload, "role")),
        tenant_id=required_str(payload, "tenant_id"),
        groups=normalize_groups(payload.get("groups")),
        created_at=required_datetime(payload, "created_at"),
    )


def user_identity_from_payload(payload: Mapping[str, Any]) -> UserIdentityRecord:
    return UserIdentityRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        user_id=required_str(payload, "user_id"),
        provider=required_str(payload, "provider"),
        external_subject=required_str(payload, "external_subject"),
        metadata=optional_mapping(payload, "metadata"),
        created_at=required_datetime(payload, "created_at"),
        updated_at=required_datetime(payload, "updated_at"),
    )


def auth_token_revocation_from_payload(payload: Mapping[str, Any]) -> TokenRevocationRecord:
    return TokenRevocationRecord(
        token_id=required_str(payload, "token_id"),
        expires_at=required_datetime(payload, "expires_at"),
        revoked_at=required_datetime(payload, "revoked_at"),
    )


def input_guard_rule_from_payload(payload: Mapping[str, Any]) -> InputGuardRuleRecord:
    return InputGuardRuleRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        name=required_str(payload, "name"),
        pattern=required_str(payload, "pattern"),
        pattern_type=pattern_type(required_str(payload, "pattern_type")),
        action=rule_action(required_str(payload, "action")),
        priority=optional_int(payload, "priority") or 100,
        category=optional_str(payload, "category") or "custom",
        description=optional_str(payload, "description"),
        enabled=optional_bool(payload, "enabled", default=True),
        created_at=required_datetime(payload, "created_at"),
        updated_at=required_datetime(payload, "updated_at"),
    )


def input_guard_metric_from_payload(payload: Mapping[str, Any]) -> InputGuardMetricMigrationRecord:
    return InputGuardMetricMigrationRecord(
        time=required_datetime(payload, "time"),
        tenant_id=optional_str(payload, "tenant_id"),
        user_id=optional_str(payload, "user_id"),
        channel=optional_str(payload, "channel") or "api",
        stage=required_str(payload, "stage"),
        category=optional_str(payload, "category"),
        reason_class=optional_str(payload, "reason_class"),
        reason_detail=optional_str(payload, "reason_detail"),
        is_output_guard=optional_bool(payload, "is_output_guard", default=False),
        action=optional_str(payload, "action") or "rejected",
    )


def output_guard_rule_from_payload(payload: Mapping[str, Any]) -> OutputGuardRuleRecord:
    return OutputGuardRuleRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        name=required_str(payload, "name"),
        pattern=required_str(payload, "pattern"),
        action=output_guard_rule_action(required_str(payload, "action")),
        replacement=optional_str(payload, "replacement") or "[REDACTED]",
        priority=optional_int(payload, "priority") or 100,
        enabled=optional_bool(payload, "enabled", default=True),
        created_at=required_datetime(payload, "created_at"),
        updated_at=required_datetime(payload, "updated_at"),
    )


def output_guard_rule_audit_from_payload(
    payload: Mapping[str, Any],
) -> OutputGuardRuleAuditRecord:
    return OutputGuardRuleAuditRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        rule_id=optional_str(payload, "rule_id"),
        action=output_guard_rule_audit_action(required_str(payload, "action")),
        actor=required_str(payload, "actor"),
        detail=optional_str(payload, "detail"),
        created_at=required_datetime(payload, "created_at"),
    )


def admin_audit_from_payload(payload: Mapping[str, Any]) -> AdminAuditLog:
    return AdminAuditLog(
        id=required_str(payload, "id"),
        category=required_str(payload, "category"),
        action=admin_audit_action(required_str(payload, "action")),
        actor=required_str(payload, "actor"),
        resource_type=optional_str(payload, "resource_type"),
        resource_id=optional_str(payload, "resource_id"),
        detail=optional_str(payload, "detail"),
        created_at=required_datetime(payload, "created_at"),
    )


def tool_catalog_from_payload(payload: Mapping[str, Any]) -> ToolCatalogRecord:
    return ToolCatalogRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        namespace=required_str(payload, "namespace"),
        name=required_str(payload, "name"),
        description=required_str(payload, "description"),
        risk_level=required_str(payload, "risk_level"),
        input_schema=optional_mapping(payload, "input_schema"),
        output_schema=optional_mapping(payload, "output_schema"),
        enabled=optional_bool(payload, "enabled", default=True),
        requires_approval=optional_bool(payload, "requires_approval", default=False),
        timeout_ms=optional_int(payload, "timeout_ms") or 15_000,
        created_at=required_datetime(payload, "created_at"),
        updated_at=required_datetime(payload, "updated_at"),
    )


def pending_approval_from_payload(payload: Mapping[str, Any]) -> PendingApprovalRecord:
    return PendingApprovalRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        run_id=required_str(payload, "run_id"),
        tool_id=required_str(payload, "tool_id"),
        status=required_str(payload, "status"),
        requested_by=required_str(payload, "requested_by"),
        decided_by=optional_str(payload, "decided_by"),
        request_payload=optional_mapping(payload, "request_payload"),
        decision_reason=optional_str(payload, "decision_reason"),
        created_at=required_datetime(payload, "created_at"),
        decided_at=optional_datetime(payload, "decided_at"),
    )


def tool_invocation_from_payload(payload: Mapping[str, Any]) -> ToolInvocationRecord:
    return ToolInvocationRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        run_id=required_str(payload, "run_id"),
        tool_id=required_str(payload, "tool_id"),
        approval_id=optional_str(payload, "approval_id"),
        status=required_str(payload, "status"),
        idempotency_key=required_str(payload, "idempotency_key"),
        request_checksum=required_str(payload, "request_checksum"),
        result_checksum=optional_str(payload, "result_checksum"),
        input_payload=optional_mapping(payload, "input_payload"),
        output_payload=optional_mapping_or_none(payload, "output_payload"),
        error_payload=optional_mapping_or_none(payload, "error_payload"),
        started_at=required_datetime(payload, "started_at"),
        completed_at=optional_datetime(payload, "completed_at"),
    )


def mcp_server_from_payload(payload: Mapping[str, Any]) -> McpServerMigrationRecord:
    return McpServerMigrationRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        name=required_str(payload, "name"),
        transport=required_str(payload, "transport"),
        status=required_str(payload, "status"),
        command=optional_str(payload, "command"),
        args=optional_str_list(payload, "args"),
        url=optional_str(payload, "url"),
        auth_type=optional_str(payload, "auth_type") or "none",
        timeout_ms=optional_int(payload, "timeout_ms") or 15_000,
        protocol_version=optional_str(payload, "protocol_version"),
        last_connection_error=optional_str(payload, "last_connection_error"),
        reconnect_policy=optional_mapping(payload, "reconnect_policy"),
        tool_snapshot_hash=optional_str(payload, "tool_snapshot_hash"),
        created_at=required_datetime(payload, "created_at"),
        updated_at=required_datetime(payload, "updated_at"),
    )


def mcp_server_status_from_payload(payload: Mapping[str, Any]) -> McpServerStatusRecord:
    return McpServerStatusRecord(
        server_id=required_str(payload, "server_id"),
        tenant_id=required_str(payload, "tenant_id"),
        status=required_str(payload, "status"),
        negotiated_protocol_version=optional_str(payload, "negotiated_protocol_version"),
        last_error=optional_str(payload, "last_error"),
        reconnect_attempt=optional_int(payload, "reconnect_attempt") or 0,
        backoff_until=optional_datetime(payload, "backoff_until"),
        checked_at=required_datetime(payload, "checked_at"),
    )


def mcp_tool_snapshot_from_payload(payload: Mapping[str, Any]) -> McpToolSnapshotRecord:
    return McpToolSnapshotRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        server_id=required_str(payload, "server_id"),
        qualified_name=required_str(payload, "qualified_name"),
        tool_name=required_str(payload, "tool_name"),
        description=required_str(payload, "description"),
        input_schema=optional_mapping(payload, "input_schema"),
        output_schema=optional_mapping(payload, "output_schema"),
        risk_level=required_str(payload, "risk_level"),
        enabled=optional_bool(payload, "enabled", default=True),
        snapshot_hash=required_str(payload, "snapshot_hash"),
        created_at=required_datetime(payload, "created_at"),
    )


def mcp_access_policy_from_payload(payload: Mapping[str, Any]) -> McpAccessPolicyRecord:
    return McpAccessPolicyRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        server_id=required_str(payload, "server_id"),
        graph_profile=required_str(payload, "graph_profile"),
        allow_write=optional_bool(payload, "allow_write", default=False),
        allowed_tools=optional_str_list(payload, "allowed_tools"),
        created_at=required_datetime(payload, "created_at"),
    )


def a2a_peer_agent_from_payload(payload: Mapping[str, Any]) -> A2APeerAgentRecord:
    return A2APeerAgentRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        name=required_str(payload, "name"),
        endpoint_url=required_str(payload, "endpoint_url"),
        agent_card=optional_mapping(payload, "agent_card"),
        enabled=optional_bool(payload, "enabled", default=True),
        created_at=required_datetime(payload, "created_at"),
        updated_at=required_datetime(payload, "updated_at"),
    )


def a2a_agent_card_from_payload(payload: Mapping[str, Any]) -> A2AAgentCardRecord:
    return A2AAgentCardRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        version=required_str(payload, "version"),
        protocol_version=required_str(payload, "protocol_version"),
        card=optional_mapping(payload, "card"),
        active=optional_bool(payload, "active", default=True),
        created_at=required_datetime(payload, "created_at"),
    )


def a2a_task_from_payload(payload: Mapping[str, Any]) -> A2ATaskMigrationRecord:
    return A2ATaskMigrationRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        peer_agent_id=optional_str(payload, "peer_agent_id"),
        run_id=required_str(payload, "run_id"),
        thread_id=required_str(payload, "thread_id"),
        session_id=required_str(payload, "session_id"),
        context_id=required_str(payload, "context_id"),
        message_id=required_str(payload, "message_id"),
        status=required_str(payload, "status"),
        idempotency_key=required_str(payload, "idempotency_key"),
        input_payload=optional_mapping(payload, "input_payload"),
        output_payload=optional_mapping_or_none(payload, "output_payload"),
        created_at=required_datetime(payload, "created_at"),
        updated_at=required_datetime(payload, "updated_at"),
    )


def a2a_task_event_from_payload(payload: Mapping[str, Any]) -> A2ATaskEventRecord:
    return A2ATaskEventRecord(
        id=required_str(payload, "id"),
        task_id=required_str(payload, "task_id"),
        tenant_id=required_str(payload, "tenant_id"),
        sequence=optional_int(payload, "sequence") or 0,
        event_type=required_str(payload, "event_type"),
        payload=optional_mapping(payload, "payload"),
        created_at=required_datetime(payload, "created_at"),
    )


def a2a_push_subscription_from_payload(
    payload: Mapping[str, Any],
) -> A2APushSubscriptionRecord:
    return A2APushSubscriptionRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        destination=required_str(payload, "destination"),
        signing_key_ref=optional_str(payload, "signing_key_ref"),
        enabled=optional_bool(payload, "enabled", default=True),
        created_at=required_datetime(payload, "created_at"),
    )


def a2a_access_policy_from_payload(payload: Mapping[str, Any]) -> A2AAccessPolicyRecord:
    return A2AAccessPolicyRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        peer_agent_id=optional_str(payload, "peer_agent_id"),
        allow_inbound=optional_bool(payload, "allow_inbound", default=True),
        allow_outbound=optional_bool(payload, "allow_outbound", default=False),
        allowed_skills=optional_str_list(payload, "allowed_skills"),
        created_at=required_datetime(payload, "created_at"),
    )


def rag_source_from_payload(payload: Mapping[str, Any]) -> RagSourceMigrationRecord:
    return RagSourceMigrationRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        collection=required_str(payload, "collection"),
        source_uri=required_str(payload, "source_uri"),
        source_type=required_str(payload, "source_type"),
        checksum=required_str(payload, "checksum"),
        metadata=optional_mapping(payload, "metadata"),
        created_at=required_datetime(payload, "created_at"),
    )


def rag_document_from_payload(payload: Mapping[str, Any]) -> RagDocumentMigrationRecord:
    return RagDocumentMigrationRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        source_id=required_str(payload, "source_id"),
        collection=required_str(payload, "collection"),
        title=required_str(payload, "title"),
        version=required_str(payload, "version"),
        acl=optional_mapping(payload, "acl"),
        metadata=optional_mapping(payload, "metadata"),
        created_at=required_datetime(payload, "created_at"),
    )


def rag_chunk_from_payload(payload: Mapping[str, Any]) -> RagChunkMigrationRecord:
    metadata = normalize_rag_chunk_metadata(optional_mapping(payload, "metadata"))
    return RagChunkMigrationRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        document_id=required_str(payload, "document_id"),
        collection=required_str(payload, "collection"),
        chunk_index=required_int(payload, "chunk_index"),
        content=required_str(payload, "content"),
        content_hash=required_str(payload, "content_hash"),
        embedding=optional_float_list_or_none(payload, "embedding"),
        metadata=metadata,
        created_at=required_datetime(payload, "created_at"),
    )


def normalize_rag_chunk_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    acl = metadata.get("acl")
    if isinstance(acl, Mapping):
        metadata = dict(metadata)
        acl_values = cast(Mapping[Any, Any], acl)
        acl_metadata: dict[str, Any] = {str(key): value for key, value in acl_values.items()}
        metadata.update(flatten_acl_metadata(acl_metadata))
    return metadata


def rag_ingestion_candidate_from_payload(
    payload: Mapping[str, Any],
) -> RagIngestionCandidate:
    return RagIngestionCandidate(
        id=required_str(payload, "id"),
        run_id=required_str(payload, "run_id"),
        user_id=required_str(payload, "user_id"),
        session_id=optional_str(payload, "session_id"),
        channel=optional_str(payload, "channel"),
        query=required_str(payload, "query"),
        response=required_str(payload, "response"),
        status=rag_ingestion_candidate_status(required_str(payload, "status")),
        captured_at=required_datetime(payload, "captured_at"),
        reviewed_at=optional_datetime(payload, "reviewed_at"),
        reviewed_by=optional_str(payload, "reviewed_by"),
        review_comment=optional_str(payload, "review_comment"),
        ingested_document_id=optional_str(payload, "ingested_document_id"),
    )


def memory_namespace_from_payload(payload: Mapping[str, Any]) -> MemoryNamespaceMigrationRecord:
    return MemoryNamespaceMigrationRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        subject_type=required_str(payload, "subject_type"),
        subject_id=required_str(payload, "subject_id"),
        memory_type=required_str(payload, "memory_type"),
        visibility=required_str(payload, "visibility"),
        created_at=required_datetime(payload, "created_at"),
    )


def memory_item_from_payload(payload: Mapping[str, Any]) -> MemoryItemMigrationRecord:
    return MemoryItemMigrationRecord(
        id=required_str(payload, "id"),
        namespace_id=required_str(payload, "namespace_id"),
        tenant_id=required_str(payload, "tenant_id"),
        status=required_str(payload, "status"),
        content=required_str(payload, "content"),
        source_id=optional_str(payload, "source_id"),
        confidence=optional_float(payload, "confidence") or 0.0,
        valid_from=optional_datetime(payload, "valid_from"),
        valid_until=optional_datetime(payload, "valid_until"),
        metadata=optional_mapping(payload, "metadata"),
        created_at=required_datetime(payload, "created_at"),
    )


def memory_embedding_from_payload(payload: Mapping[str, Any]) -> MemoryEmbeddingRecord:
    return MemoryEmbeddingRecord(
        memory_id=required_str(payload, "memory_id"),
        tenant_id=required_str(payload, "tenant_id"),
        embedding=required_float_list(payload, "embedding"),
        embedding_model=required_str(payload, "embedding_model"),
        created_at=required_datetime(payload, "created_at"),
    )


def memory_proposal_from_payload(payload: Mapping[str, Any]) -> MemoryProposalMigrationRecord:
    return MemoryProposalMigrationRecord(
        id=required_str(payload, "id"),
        tenant_id=required_str(payload, "tenant_id"),
        namespace_id=required_str(payload, "namespace_id"),
        status=required_str(payload, "status"),
        proposed_content=required_str(payload, "proposed_content"),
        extraction_model=required_str(payload, "extraction_model"),
        extraction_prompt_version=required_str(payload, "extraction_prompt_version"),
        confidence=optional_float(payload, "confidence") or 0.0,
        source_payload=optional_mapping(payload, "source_payload"),
        decision_reason=optional_str(payload, "decision_reason"),
        created_at=required_datetime(payload, "created_at"),
    )


def runtime_setting_type(value: str) -> RuntimeSettingType:
    if value in {"STRING", "BOOLEAN", "INT", "DOUBLE", "JSON"}:
        return cast(RuntimeSettingType, value)
    raise ValueError(f"unsupported runtime setting type: {value}")


def auto_reply_mode(value: str) -> AutoReplyMode:
    try:
        return AutoReplyMode(value)
    except ValueError as error:
        raise ValueError(f"unsupported auto reply mode: {value}") from error


def feedback_rating(value: str) -> FeedbackRating:
    try:
        return FeedbackRating(value)
    except ValueError as error:
        raise ValueError(f"unsupported feedback rating: {value}") from error


def scheduled_job_type(value: str) -> ScheduledJobType:
    try:
        return ScheduledJobType(value)
    except ValueError as error:
        raise ValueError(f"unsupported scheduled job type: {value}") from error


def execution_status(value: str) -> JobExecutionStatus:
    try:
        return JobExecutionStatus(value)
    except ValueError as error:
        raise ValueError(f"unsupported execution status: {value}") from error


def alert_type(value: str) -> AlertType:
    try:
        return AlertType(value)
    except ValueError as error:
        raise ValueError(f"unsupported alert type: {value}") from error


def alert_severity(value: str) -> AlertSeverity:
    try:
        return AlertSeverity(value)
    except ValueError as error:
        raise ValueError(f"unsupported alert severity: {value}") from error


def alert_status(value: str) -> AlertStatus:
    try:
        return AlertStatus(value)
    except ValueError as error:
        raise ValueError(f"unsupported alert status: {value}") from error


def user_role(value: str) -> UserRole:
    try:
        return UserRole(value)
    except ValueError as error:
        raise ValueError(f"unsupported user role: {value}") from error


def pattern_type(value: str) -> PatternType:
    try:
        return PatternType(value)
    except ValueError as error:
        raise ValueError(f"unsupported input guard pattern type: {value}") from error


def rule_action(value: str) -> RuleAction:
    try:
        return RuleAction(value)
    except ValueError as error:
        raise ValueError(f"unsupported input guard action: {value}") from error


def output_guard_rule_action(value: str) -> OutputGuardRuleAction:
    try:
        return OutputGuardRuleAction(value)
    except ValueError as error:
        raise ValueError(f"unsupported output guard action: {value}") from error


def output_guard_rule_audit_action(value: str) -> OutputGuardRuleAuditAction:
    try:
        return OutputGuardRuleAuditAction(value)
    except ValueError as error:
        raise ValueError(f"unsupported output guard audit action: {value}") from error


def prompt_lab_experiment_status(value: str) -> PromptLabExperimentStatus:
    try:
        return PromptLabExperimentStatus(value)
    except ValueError as error:
        raise ValueError(f"unsupported prompt lab experiment status: {value}") from error


def agent_spec_mode(value: str) -> AgentSpecMode:
    try:
        return AgentSpecMode(value)
    except ValueError as error:
        raise ValueError(f"unsupported agent spec mode: {value}") from error


def rag_ingestion_candidate_status(value: str) -> RagIngestionCandidateStatus:
    try:
        return RagIngestionCandidateStatus(value)
    except ValueError as error:
        raise ValueError(f"unsupported rag ingestion candidate status: {value}") from error


def admin_audit_action(value: str) -> AdminAuditAction:
    try:
        return AdminAuditAction(value)
    except ValueError as error:
        raise ValueError(f"unsupported admin audit action: {value}") from error


def required_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError(f"runtime setting payload is missing {key}")


def required_decimal(payload: Mapping[str, Any], key: str) -> Decimal:
    value = payload.get(key)
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float | str) and not isinstance(value, bool):
        return Decimal(str(value))
    raise ValueError(f"payload is missing decimal {key}")


def required_datetime(payload: Mapping[str, Any], key: str) -> datetime:
    value = optional_datetime(payload, key)
    if value is None:
        raise ValueError(f"payload is missing datetime {key}")
    return value


def required_mapping(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if isinstance(value, Mapping):
        return dict(cast(Mapping[str, Any], value))
    raise ValueError(f"payload is missing object {key}")


def required_int(payload: Mapping[str, Any], key: str) -> int:
    value = optional_int(payload, key)
    if value is None:
        raise ValueError(f"payload is missing int {key}")
    return value


def required_float_list(payload: Mapping[str, Any], key: str) -> list[float]:
    value = optional_float_list_or_none(payload, key)
    if value is None:
        raise ValueError(f"payload is missing float list {key}")
    return value


def optional_str(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


def optional_str_list(payload: Mapping[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, str):
            items.append(item)
    return items


def optional_str_tuple(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    return tuple(optional_str_list(payload, key))


def optional_float_list_or_none(payload: Mapping[str, Any], key: str) -> list[float] | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    items: list[float] = []
    for item in cast(list[object], value):
        if isinstance(item, int | float) and not isinstance(item, bool):
            items.append(float(item))
    return items


def optional_mapping(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if isinstance(value, Mapping):
        return dict(cast(Mapping[str, Any], value))
    return {}


def optional_mapping_or_none(payload: Mapping[str, Any], key: str) -> dict[str, Any] | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(cast(Mapping[str, Any], value))
    return None


def optional_mapping_list(payload: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for item in cast(list[object], value):
        if isinstance(item, Mapping):
            items.append(dict(cast(Mapping[str, Any], item)))
    return items


def optional_job_type(payload: Mapping[str, Any], key: str) -> ScheduledJobType | None:
    value = optional_str(payload, key)
    if value is None:
        return None
    return scheduled_job_type(value)


def optional_execution_status(payload: Mapping[str, Any], key: str) -> JobExecutionStatus | None:
    value = optional_str(payload, key)
    if value is None:
        return None
    return execution_status(value)


def optional_bool(payload: Mapping[str, Any], key: str, *, default: bool) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    return default


def optional_int(payload: Mapping[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def optional_float(payload: Mapping[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def optional_datetime(payload: Mapping[str, Any], key: str) -> datetime | None:
    value = payload.get(key)
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        return datetime.fromisoformat(value)
    return None
