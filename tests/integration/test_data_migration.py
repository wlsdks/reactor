from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.admin.tenants import TenantPlan, TenantQuota, TenantRecord, TenantStatus
from reactor.agents.specs import AgentSpecMode, AgentSpecRecord
from reactor.auth.models import TokenRevocationRecord, UserIdentityRecord, UserRecord
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
from reactor.migration.export import (
    LegacyRow,
    SkippedLegacyRow,
    export_legacy_rows_to_ndjson,
    read_legacy_rows,
)
from reactor.migration.import_ import ImportedRow, import_ndjson_records
from reactor.migration.parity import build_parity_report
from reactor.migration.report import generate_staging_parity_report
from reactor.migration.rollback import RollbackSnapshotRow, write_rollback_snapshot
from reactor.migration.source_readers import (
    legacy_channel_faq_registration_row,
    legacy_conversation_message_rows,
    legacy_conversation_summary_rows,
    legacy_eval_result_metric_row,
    legacy_feedback_row,
    legacy_mcp_health_metric_row,
    legacy_mcp_security_policy_row,
    legacy_metric_agent_execution_row,
    legacy_metric_audit_trail_row,
    legacy_metric_guard_event_row,
    legacy_metric_hitl_event_row,
    legacy_metric_quota_event_row,
    legacy_metric_session_row,
    legacy_metric_span_row,
    legacy_metric_token_usage_row,
    legacy_metric_tool_call_row,
    legacy_rag_ingestion_policy_row,
    legacy_scheduled_job_execution_row,
    legacy_scheduled_job_row,
    legacy_slack_bot_instance_row,
    legacy_slack_user_identity_rows,
    legacy_slo_config_row,
    legacy_tool_policy_row,
    legacy_user_row,
    legacy_v42_model_pricing_row,
)
from reactor.migration.targets import (
    A2AAccessPolicyTargetWriter,
    A2AAgentCardTargetWriter,
    A2APeerAgentTargetWriter,
    A2APushSubscriptionTargetWriter,
    A2ATaskEventTargetWriter,
    A2ATaskTargetWriter,
    AdminAuditTargetWriter,
    AgentRunEventTargetWriter,
    AgentRunTargetWriter,
    AgentSpecTargetWriter,
    AlertInstanceTargetWriter,
    AlertRuleTargetWriter,
    AuthTokenRevocationTargetWriter,
    AuthUserTargetWriter,
    DeadLetterJobTargetWriter,
    EvalCaseTargetWriter,
    EvalResultTargetWriter,
    FaqRegistrationTargetWriter,
    FeedbackTargetWriter,
    IdempotencyRecordTargetWriter,
    InboxEventTargetWriter,
    InputGuardMetricTargetWriter,
    InputGuardRuleTargetWriter,
    IntentDefinitionTargetWriter,
    McpAccessPolicyTargetWriter,
    McpServerStatusTargetWriter,
    McpServerTargetWriter,
    McpToolSnapshotTargetWriter,
    MemoryEmbeddingTargetWriter,
    MemoryItemTargetWriter,
    MemoryNamespaceTargetWriter,
    MemoryProposalTargetWriter,
    MetricAgentExecutionTargetWriter,
    MetricAuditTrailTargetWriter,
    MetricEvalResultTargetWriter,
    MetricHitlEventTargetWriter,
    MetricMcpHealthTargetWriter,
    MetricQuotaEventTargetWriter,
    MetricSessionTargetWriter,
    MetricSpanTargetWriter,
    MetricToolCallTargetWriter,
    MigrationTargetDispatcher,
    ModelPricingTargetWriter,
    OutboxEventTargetWriter,
    OutputGuardRuleAuditTargetWriter,
    OutputGuardRuleTargetWriter,
    PendingApprovalTargetWriter,
    PersonaTargetWriter,
    ProactiveChannelTargetWriter,
    PromptLabExperimentTargetWriter,
    PromptLabReportTargetWriter,
    PromptLabTrialTargetWriter,
    PromptReleaseTargetWriter,
    PromptTemplateTargetWriter,
    PromptVersionTargetWriter,
    RagChunkTargetWriter,
    RagDocumentTargetWriter,
    RagIngestionCandidateTargetWriter,
    RagSourceTargetWriter,
    RunQueueTargetWriter,
    RuntimeSettingsTargetWriter,
    ScheduledJobDeadLetterTargetWriter,
    ScheduledJobExecutionTargetWriter,
    ScheduledJobTargetWriter,
    SlackBotTargetWriter,
    TenantSloConfigTargetWriter,
    TenantTargetWriter,
    ToolCatalogTargetWriter,
    ToolInvocationTargetWriter,
    UnsupportedTargetTable,
    UsageLedgerTargetWriter,
    UserIdentityTargetWriter,
)
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
    EvaluationConfig,
    EvaluationResult,
    EvaluationTier,
    PromptLabExperimentRecord,
    PromptLabExperimentStatus,
    PromptLabReportRecord,
    PromptLabTrialRecord,
    Recommendation,
    RecommendationConfidence,
    TokenUsageSummary,
    VersionSummary,
)
from reactor.prompt_lab.models import (
    TestQuery as PromptLabTestQuery,
)
from reactor.prompts.personas import PersonaRecord
from reactor.rag.ingestion_candidates import (
    RagIngestionCandidate,
    RagIngestionCandidateStatus,
)
from reactor.runtime_settings.service import RuntimeSettingUpdate
from reactor.scheduler.service import (
    JobExecutionStatus,
    ScheduledJobDeadLetterRecord,
    ScheduledJobExecutionRecord,
    ScheduledJobRecord,
    ScheduledJobType,
)
from reactor.slack.faq import AutoReplyMode, ChannelFaqRegistration
from reactor.slack.feedback import Feedback, FeedbackRating
from reactor.slack.models import ProactiveChannelRecord, SlackBotInstanceRecord

FIXED_EXPORTED_AT = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
BOT_TOKEN = "xoxb-secret"  # noqa: S105
APP_TOKEN = "xapp-secret"  # noqa: S105


async def test_export_legacy_rows_to_ndjson_includes_checksum_and_skips() -> None:
    output = StringIO()

    summary = export_legacy_rows_to_ndjson(
        rows=[
            LegacyRow(
                source_table="slack_bot_instances",
                source_pk="bot_1",
                payload={"tenant_id": "tenant_1", "name": "Support", "enabled": True},
            ),
            SkippedLegacyRow(
                source_table="conversation_messages",
                source_pk="msg_bad",
                reason="unsupported legacy attachment",
            ),
        ],
        output=output,
        exported_at=FIXED_EXPORTED_AT,
    )

    lines = output.getvalue().splitlines()
    assert summary.exported == 1
    assert summary.skipped == 1
    assert len(lines) == 2
    assert lines[0] == (
        '{"checksum":"sha256:f176462251b8ea3ef1ee97a8ec6aefa6f0e555e45b46053bb56d33163e02'
        'f7ff","exported_at":"2026-06-27T12:00:00+00:00","payload":{"enabled":true,'
        '"name":"Support","tenant_id":"tenant_1"},"record_type":"row","source_pk":"bot_1",'
        '"source_table":"slack_bot_instances"}'
    )
    assert lines[1] == (
        '{"exported_at":"2026-06-27T12:00:00+00:00","reason":"unsupported legacy attachment",'
        '"record_type":"skipped","source_pk":"msg_bad","source_table":"conversation_messages"}'
    )


async def test_read_legacy_rows_flattens_source_readers_in_order() -> None:
    rows = [
        row
        async for row in read_legacy_rows(
            [
                StaticLegacySourceReader(
                    [
                        LegacyRow("runtime_settings", "tenant_1:a", {"key": "a"}),
                        SkippedLegacyRow("legacy_only", "old_1", "not retained"),
                    ]
                ),
                StaticLegacySourceReader(
                    [LegacyRow("slack_bot_instances", "tenant_1:bot_1", {"name": "Support"})]
                ),
            ]
        )
    ]

    assert rows == [
        LegacyRow("runtime_settings", "tenant_1:a", {"key": "a"}),
        SkippedLegacyRow("legacy_only", "old_1", "not retained"),
        LegacyRow("slack_bot_instances", "tenant_1:bot_1", {"name": "Support"}),
    ]


async def test_import_ndjson_records_is_idempotent_and_tracks_skips() -> None:
    sink = RecordingImportSink()
    ndjson = "\n".join(
        [
            (
                '{"checksum":"sha256:a","exported_at":"2026-06-27T12:00:00+00:00",'
                '"payload":{"name":"Support"},"record_type":"row","source_pk":"bot_1",'
                '"source_table":"slack_bot_instances"}'
            ),
            (
                '{"checksum":"sha256:a","exported_at":"2026-06-27T12:00:00+00:00",'
                '"payload":{"name":"Support"},"record_type":"row","source_pk":"bot_1",'
                '"source_table":"slack_bot_instances"}'
            ),
            (
                '{"exported_at":"2026-06-27T12:00:00+00:00","reason":"not retained",'
                '"record_type":"skipped","source_pk":"x","source_table":"old_table"}'
            ),
        ]
    )

    summary = await import_ndjson_records(StringIO(ndjson), sink=sink, batch_id="batch_1")

    assert summary.imported == 1
    assert summary.duplicates == 1
    assert summary.skipped == 1
    assert sink.rows == [
        ImportedRow(
            batch_id="batch_1",
            source_table="slack_bot_instances",
            source_pk="bot_1",
            checksum="sha256:a",
            payload={"name": "Support"},
        )
    ]


async def test_build_parity_report_compares_counts_checksums_and_samples() -> None:
    report = build_parity_report(
        exported=[
            LegacyRow("runtime_settings", "setting_1", {"key": "a"}),
            LegacyRow("runtime_settings", "setting_2", {"key": "b"}),
            LegacyRow("slack_bot_instances", "bot_1", {"name": "Support"}),
        ],
        imported=[
            ImportedRow(
                batch_id="batch_1",
                source_table="runtime_settings",
                source_pk="setting_1",
                checksum="sha256:bad",
                payload={"key": "a"},
            ),
            ImportedRow(
                batch_id="batch_1",
                source_table="slack_bot_instances",
                source_pk="bot_1",
                checksum="sha256:907de762b51597f5ff13061d9379770e35010f1403d7351cb68d65de2503ff77",
                payload={"name": "Support"},
            ),
        ],
        sample_size=2,
    )

    assert report.ok is False
    assert report.tables["runtime_settings"].exported_count == 2
    assert report.tables["runtime_settings"].imported_count == 1
    assert report.tables["runtime_settings"].missing_source_pks == ["setting_2"]
    assert report.tables["runtime_settings"].checksum_mismatches == ["setting_1"]
    assert report.tables["runtime_settings"].sample_source_pks == ["setting_1", "setting_2"]
    assert report.tables["slack_bot_instances"].ok is True


async def test_write_rollback_snapshot_records_current_rows_before_import() -> None:
    output = StringIO()

    summary = write_rollback_snapshot(
        rows=[
            RollbackSnapshotRow(
                target_table="runtime_settings",
                target_pk="setting_1",
                payload={"key": "a", "value": "old"},
            )
        ],
        output=output,
        batch_id="batch_1",
        captured_at=FIXED_EXPORTED_AT,
    )

    assert summary.snapshotted == 1
    assert output.getvalue().strip() == (
        '{"batch_id":"batch_1","captured_at":"2026-06-27T12:00:00+00:00",'
        '"checksum":"sha256:12e25dd57a08546740a7ea98c6145c5d5943d6cf2cf5e236a63e010cdd2d7754",'
        '"payload":{"key":"a","value":"old"},"record_type":"rollback_snapshot",'
        '"target_pk":"setting_1","target_table":"runtime_settings"}'
    )


async def test_runtime_settings_target_writer_maps_imported_rows_to_updates() -> None:
    store = RecordingRuntimeSettingsStore()
    writer = RuntimeSettingsTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="runtime_settings",
            source_pk="tenant_1:feature.a2a.enabled",
            checksum="sha256:a",
            payload={
                "tenant_id": "tenant_1",
                "key": "feature.a2a.enabled",
                "value": "true",
                "value_type": "BOOLEAN",
                "category": "feature",
                "description": "A2A toggle",
                "updated_by": "migration",
                "metadata": {"source": "legacy"},
            },
        )
    )

    assert store.updates == [
        RuntimeSettingUpdate(
            tenant_id="tenant_1",
            key="feature.a2a.enabled",
            value="true",
            value_type="BOOLEAN",
            category="feature",
            description="A2A toggle",
            updated_by="migration",
            metadata={"source": "legacy"},
        )
    ]


async def test_runtime_settings_target_writer_rejects_other_tables() -> None:
    writer = RuntimeSettingsTargetWriter(RecordingRuntimeSettingsStore())

    try:
        await writer.write(
            ImportedRow(
                batch_id="batch_1",
                source_table="slack_bot_instances",
                source_pk="bot_1",
                checksum="sha256:a",
                payload={"name": "Support"},
            )
        )
    except UnsupportedTargetTable as error:
        assert str(error) == "unsupported target table: slack_bot_instances"
    else:
        raise AssertionError("expected UnsupportedTargetTable")


async def test_legacy_runtime_policy_rows_import_to_runtime_settings() -> None:
    store = RecordingRuntimeSettingsStore()
    writer = RuntimeSettingsTargetWriter(store)
    legacy_rows = [
        legacy_tool_policy_row(
            {
                "id": "default",
                "enabled": True,
                "write_tool_names": '["slack.post_message"]',
                "deny_write_channels": '["general"]',
                "allow_write_tool_names_in_deny_channels": "[]",
                "allow_write_tool_names_by_channel": "{}",
                "deny_write_message": "Writes require approval.",
                "created_at": datetime(2026, 6, 1, tzinfo=UTC),
                "updated_at": datetime(2026, 6, 2, tzinfo=UTC),
            },
            tenant_id="tenant_1",
        ),
        legacy_mcp_security_policy_row(
            {
                "id": "default",
                "allowed_server_names": '["github"]',
                "max_tool_output_length": 120000,
                "created_at": datetime(2026, 6, 1, tzinfo=UTC),
                "updated_at": datetime(2026, 6, 2, tzinfo=UTC),
            }
        ),
        legacy_rag_ingestion_policy_row(
            {
                "id": "default",
                "enabled": True,
                "require_review": True,
                "allowed_channels": '["engineering"]',
                "min_query_chars": 10,
                "min_response_chars": 20,
                "blocked_patterns": '["password"]',
                "created_at": datetime(2026, 6, 1, tzinfo=UTC),
                "updated_at": datetime(2026, 6, 2, tzinfo=UTC),
            }
        ),
    ]

    for legacy_row in legacy_rows:
        await writer.write(
            ImportedRow(
                batch_id="batch_1",
                source_table=legacy_row.source_table,
                source_pk=legacy_row.source_pk,
                checksum="sha256:a",
                payload=legacy_row.payload,
            )
        )

    assert [(update.tenant_id, update.key, update.category) for update in store.updates] == [
        ("tenant_1", "tools.policy", "tools"),
        ("global", "mcp.security.policy", "mcp_security"),
        ("global", "rag.ingestion.policy", "rag"),
    ]
    assert all(update.value_type == "JSON" for update in store.updates)
    assert [update.metadata["source"] for update in store.updates] == [
        "spring_tool_policy",
        "spring_mcp_security_policy",
        "spring_rag_ingestion_policy",
    ]


async def test_prompt_template_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingPromptMigrationStore()
    writer = PromptTemplateTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="prompt_templates",
            source_pk="tenant_1:prompt_template_1",
            checksum="sha256:a",
            payload={
                "id": "prompt_template_1",
                "tenant_id": "tenant_1",
                "name": "support",
                "graph_profile": "rag",
                "description": "Support prompt",
                "created_by": "admin_1",
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert store.templates == [
        PromptTemplateRecord(
            id="prompt_template_1",
            tenant_id="tenant_1",
            name="support",
            graph_profile="rag",
            description="Support prompt",
            created_by="admin_1",
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_prompt_version_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingPromptMigrationStore()
    writer = PromptVersionTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="prompt_versions",
            source_pk="tenant_1:prompt_template_1:prompt_version_1",
            checksum="sha256:a",
            payload={
                "id": "prompt_version_1",
                "template_id": "prompt_template_1",
                "tenant_id": "tenant_1",
                "version": "1",
                "system_policy": "Answer with citations.",
                "developer_policy": "Prefer RAG.",
                "examples": ["Q: hi"],
                "metadata": {"legacyStatus": "ACTIVE"},
                "content_hash": "sha256:abc",
                "created_by": "admin_1",
                "created_at": "2026-06-03T00:00:00+00:00",
            },
        )
    )

    assert store.versions == [
        PromptVersionRecord(
            id="prompt_version_1",
            template_id="prompt_template_1",
            tenant_id="tenant_1",
            version="1",
            system_policy="Answer with citations.",
            developer_policy="Prefer RAG.",
            examples=["Q: hi"],
            metadata={"legacyStatus": "ACTIVE"},
            content_hash="sha256:abc",
            created_by="admin_1",
            created_at=datetime(2026, 6, 3, tzinfo=UTC),
        )
    ]


async def test_prompt_release_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingPromptMigrationStore()
    writer = PromptReleaseTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="prompt_releases",
            source_pk="tenant_1:prompt_template_1:production",
            checksum="sha256:a",
            payload={
                "id": "prompt_release_1",
                "tenant_id": "tenant_1",
                "template_id": "prompt_template_1",
                "version_id": "prompt_version_1",
                "environment": "production",
                "released_by": "admin_1",
                "released_at": "2026-06-04T00:00:00+00:00",
                "metadata": {"ticket": "CUT-1"},
            },
        )
    )

    assert store.releases == [
        PromptReleaseRecord(
            id="prompt_release_1",
            tenant_id="tenant_1",
            template_id="prompt_template_1",
            version_id="prompt_version_1",
            environment="production",
            released_by="admin_1",
            released_at=datetime(2026, 6, 4, tzinfo=UTC),
            metadata={"ticket": "CUT-1"},
        )
    ]


async def test_persona_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingPersonaStore()
    writer = PersonaTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="personas",
            source_pk="persona_1",
            checksum="sha256:a",
            payload={
                "id": "persona_1",
                "name": "Support",
                "system_prompt": "Support users.",
                "is_default": True,
                "description": "Default support persona",
                "response_guideline": "Be concise.",
                "welcome_message": "Hi",
                "icon": "sparkles",
                "is_active": True,
                "prompt_template_id": "prompt_template_1",
                "created_at": "2026-06-05T00:00:00+00:00",
                "updated_at": "2026-06-06T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        PersonaRecord(
            id="persona_1",
            name="Support",
            system_prompt="Support users.",
            is_default=True,
            description="Default support persona",
            response_guideline="Be concise.",
            welcome_message="Hi",
            icon="sparkles",
            is_active=True,
            prompt_template_id="prompt_template_1",
            created_at=datetime(2026, 6, 5, tzinfo=UTC),
            updated_at=datetime(2026, 6, 6, tzinfo=UTC),
        )
    ]


async def test_agent_spec_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingAgentSpecStore()
    writer = AgentSpecTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="agent_specs",
            source_pk="agent_spec_1",
            checksum="sha256:a",
            payload={
                "id": "agent_spec_1",
                "name": "Support agent",
                "description": "Handles support requests",
                "tool_names": ["rag.search", "tickets.create"],
                "keywords": ["support", "ticket"],
                "system_prompt": "Resolve support cases.",
                "mode": "PLAN_EXECUTE",
                "independent_execution": False,
                "enabled": True,
                "created_at": "2026-06-05T00:00:00+00:00",
                "updated_at": "2026-06-06T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        AgentSpecRecord(
            id="agent_spec_1",
            name="Support agent",
            description="Handles support requests",
            tool_names=("rag.search", "tickets.create"),
            keywords=("support", "ticket"),
            system_prompt="Resolve support cases.",
            mode=AgentSpecMode.PLAN_EXECUTE,
            independent_execution=False,
            enabled=True,
            created_at=datetime(2026, 6, 5, tzinfo=UTC),
            updated_at=datetime(2026, 6, 6, tzinfo=UTC),
        )
    ]


async def test_intent_definition_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingIntentDefinitionStore()
    writer = IntentDefinitionTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="intent_definitions",
            source_pk="support",
            checksum="sha256:a",
            payload={
                "name": "support",
                "description": "Support request routing",
                "examples": ["I need help with billing"],
                "keywords": ["help", "billing"],
                "profile": "support",
                "enabled": True,
                "created_at": "2026-06-05T00:00:00+00:00",
                "updated_at": "2026-06-06T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        IntentDefinition(
            name="support",
            description="Support request routing",
            examples=("I need help with billing",),
            keywords=("help", "billing"),
            profile="support",
            enabled=True,
            created_at=datetime(2026, 6, 5, tzinfo=UTC),
            updated_at=datetime(2026, 6, 6, tzinfo=UTC),
        )
    ]


async def test_prompt_lab_experiment_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingPromptLabMigrationStore()
    writer = PromptLabExperimentTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="prompt_lab_experiments",
            source_pk="tenant_1:exp_1",
            checksum="sha256:a",
            payload={
                "id": "exp_1",
                "tenant_id": "tenant_1",
                "name": "Support prompt experiment",
                "description": "Measure support prompt variants",
                "template_id": "prompt_template_1",
                "baseline_version_id": "prompt_version_1",
                "candidate_version_ids": ["prompt_version_2"],
                "test_queries": [
                    {
                        "query": "How do I reset MFA?",
                        "expectedBehavior": "cite policy",
                        "tags": ["mfa"],
                    }
                ],
                "evaluation_config": {"rulesEnabled": True, "llmJudgeEnabled": False},
                "model": "openai:gpt-4.1-mini",
                "judge_model": None,
                "temperature": 0.2,
                "repetitions": 2,
                "auto_generated": True,
                "status": "COMPLETED",
                "created_by": "admin_1",
                "created_at": "2026-06-07T00:00:00+00:00",
                "started_at": "2026-06-07T00:01:00+00:00",
                "completed_at": "2026-06-07T00:02:00+00:00",
                "error_message": None,
            },
        )
    )

    assert store.experiments == [
        PromptLabExperimentRecord(
            id="exp_1",
            tenant_id="tenant_1",
            name="Support prompt experiment",
            description="Measure support prompt variants",
            template_id="prompt_template_1",
            baseline_version_id="prompt_version_1",
            candidate_version_ids=["prompt_version_2"],
            evaluation_config=EvaluationConfig(
                rules_enabled=True,
                llm_judge_enabled=False,
            ),
            test_queries=[
                PromptLabTestQuery(
                    query="How do I reset MFA?",
                    expected_behavior="cite policy",
                    tags=["mfa"],
                )
            ],
            model="openai:gpt-4.1-mini",
            judge_model=None,
            temperature=0.2,
            repetitions=2,
            auto_generated=True,
            status=PromptLabExperimentStatus.COMPLETED,
            created_by="admin_1",
            created_at=datetime(2026, 6, 7, tzinfo=UTC),
            started_at=datetime(2026, 6, 7, 0, 1, tzinfo=UTC),
            completed_at=datetime(2026, 6, 7, 0, 2, tzinfo=UTC),
            error_message=None,
        )
    ]
    assert store.experiments[0].evaluation_config.rules_enabled is True
    assert store.experiments[0].evaluation_config.llm_judge_enabled is False


async def test_prompt_lab_trial_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingPromptLabMigrationStore()
    writer = PromptLabTrialTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="prompt_lab_trials",
            source_pk="tenant_1:exp_1:trial_1",
            checksum="sha256:a",
            payload={
                "id": "trial_1",
                "tenant_id": "tenant_1",
                "experiment_id": "exp_1",
                "prompt_version_id": "prompt_version_2",
                "prompt_version_number": 2,
                "test_query": {"query": "How do I reset MFA?", "tags": ["mfa"]},
                "repetition_index": 1,
                "response": "Use the MFA reset policy.",
                "success": True,
                "error_message": None,
                "tools_used": ["rag.search"],
                "token_usage": {"promptTokens": 10, "completionTokens": 20, "totalTokens": 30},
                "duration_ms": 123,
                "evaluations": [
                    {
                        "tier": "RULES",
                        "passed": True,
                        "score": 0.9,
                        "reason": "Matched expected behavior.",
                    }
                ],
                "executed_at": "2026-06-07T00:03:00+00:00",
            },
        )
    )

    assert store.trials == [
        PromptLabTrialRecord(
            id="trial_1",
            tenant_id="tenant_1",
            experiment_id="exp_1",
            prompt_version_id="prompt_version_2",
            prompt_version_number=2,
            test_query=PromptLabTestQuery(query="How do I reset MFA?", tags=["mfa"]),
            repetition_index=1,
            response="Use the MFA reset policy.",
            success=True,
            error_message=None,
            tools_used=["rag.search"],
            token_usage=TokenUsageSummary(
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
            ),
            duration_ms=123,
            evaluations=[
                EvaluationResult(
                    tier=EvaluationTier.RULES,
                    passed=True,
                    score=0.9,
                    reason="Matched expected behavior.",
                    evaluator_name=None,
                )
            ],
            executed_at=datetime(2026, 6, 7, 0, 3, tzinfo=UTC),
        )
    ]


async def test_prompt_lab_report_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingPromptLabMigrationStore()
    writer = PromptLabReportTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="prompt_lab_reports",
            source_pk="tenant_1:exp_1",
            checksum="sha256:a",
            payload={
                "experiment_id": "exp_1",
                "tenant_id": "tenant_1",
                "experiment_name": "Support prompt experiment",
                "generated_at": "2026-06-07T00:04:00+00:00",
                "total_trials": 1,
                "version_summaries": [
                    {
                        "versionId": "prompt_version_2",
                        "versionNumber": 2,
                        "isBaseline": False,
                        "totalTrials": 1,
                        "passCount": 1,
                        "passRate": 1.0,
                        "avgScore": 0.9,
                        "avgDurationMs": 123.0,
                        "totalTokens": 30,
                        "tierBreakdown": {"RULES": {"passCount": 1, "failCount": 0}},
                        "toolUsageFrequency": {"rag.search": 1},
                        "errorRate": 0.0,
                    }
                ],
                "recommendation": {
                    "bestVersionId": "prompt_version_2",
                    "bestVersionNumber": 2,
                    "confidence": "HIGH",
                    "reasoning": "Candidate passed all trials.",
                    "improvements": ["Better grounding"],
                    "warnings": [],
                },
            },
        )
    )

    assert store.reports == [
        PromptLabReportRecord(
            experiment_id="exp_1",
            tenant_id="tenant_1",
            experiment_name="Support prompt experiment",
            generated_at=datetime(2026, 6, 7, 0, 4, tzinfo=UTC),
            total_trials=1,
            version_summaries=[
                VersionSummary(
                    version_id="prompt_version_2",
                    version_number=2,
                    is_baseline=False,
                    total_trials=1,
                    pass_count=1,
                    pass_rate=1.0,
                    avg_score=0.9,
                    avg_duration_ms=123.0,
                    total_tokens=30,
                    tier_breakdown={"RULES": {"passCount": 1, "failCount": 0}},
                    tool_usage_frequency={"rag.search": 1},
                    error_rate=0.0,
                )
            ],
            recommendation=Recommendation(
                best_version_id="prompt_version_2",
                best_version_number=2,
                confidence=RecommendationConfidence.HIGH,
                reasoning="Candidate passed all trials.",
                improvements=["Better grounding"],
                warnings=[],
            ),
        )
    ]


async def test_agent_run_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingRunMigrationStore()
    writer = AgentRunTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="agent_runs",
            source_pk="tenant_1:run_1",
            checksum="sha256:a",
            payload={
                "id": "run_1",
                "tenant_id": "tenant_1",
                "user_id": "user_1",
                "thread_id": "thread_1",
                "checkpoint_ns": "default",
                "status": "completed",
                "input_text": "hello",
                "response_text": "world",
                "error_code": None,
                "metadata": {"model": "gpt-4.1", "usage": {"total_tokens": 42}},
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert store.runs == [
        AgentRunMigrationRecord(
            id="run_1",
            tenant_id="tenant_1",
            user_id="user_1",
            thread_id="thread_1",
            checkpoint_ns="default",
            status="completed",
            input_text="hello",
            response_text="world",
            error_code=None,
            metadata={"model": "gpt-4.1", "usage": {"total_tokens": 42}},
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_agent_run_event_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingRunMigrationStore()
    writer = AgentRunEventTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="agent_run_events",
            source_pk="tenant_1:run_1:3:42",
            checksum="sha256:a",
            payload={
                "id": 42,
                "run_id": "run_1",
                "tenant_id": "tenant_1",
                "sequence": 3,
                "event_type": "model.token",
                "payload": {"node": "model", "token": "hello", "trace_id": "trace_1"},
                "created_at": "2026-06-01T00:00:03+00:00",
            },
        )
    )

    assert store.events == [
        AgentRunEventMigrationRecord(
            id=42,
            run_id="run_1",
            tenant_id="tenant_1",
            sequence=3,
            event_type="model.token",
            payload={"node": "model", "token": "hello", "trace_id": "trace_1"},
            created_at=datetime(2026, 6, 1, 0, 0, 3, tzinfo=UTC),
        )
    ]


async def test_run_queue_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingDurableMigrationStore()
    writer = RunQueueTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="run_queue",
            source_pk="tenant_1:queue_1",
            checksum="sha256:a",
            payload={
                "id": "queue_1",
                "run_id": "run_1",
                "tenant_id": "tenant_1",
                "status": "leased",
                "priority": 10,
                "attempt": 2,
                "max_attempts": 5,
                "available_at": "2026-06-01T00:01:00+00:00",
                "lease_owner": "worker_1",
                "lease_expires_at": "2026-06-01T00:06:00+00:00",
                "fencing_token": 7,
                "payload": {"mode": "async"},
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-01T00:02:00+00:00",
            },
        )
    )

    assert store.queues == [
        RunQueueMigrationRecord(
            id="queue_1",
            run_id="run_1",
            tenant_id="tenant_1",
            status="leased",
            priority=10,
            attempt=2,
            max_attempts=5,
            available_at=datetime(2026, 6, 1, 0, 1, tzinfo=UTC),
            lease_owner="worker_1",
            lease_expires_at=datetime(2026, 6, 1, 0, 6, tzinfo=UTC),
            fencing_token=7,
            payload={"mode": "async"},
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 1, 0, 2, tzinfo=UTC),
        )
    ]


async def test_dead_letter_job_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingDurableMigrationStore()
    writer = DeadLetterJobTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="dead_letter_jobs",
            source_pk="tenant_1:dead_1",
            checksum="sha256:a",
            payload={
                "id": "dead_1",
                "queue_id": "queue_1",
                "run_id": "run_1",
                "tenant_id": "tenant_1",
                "reason": "max_attempts_exhausted",
                "last_checkpoint_id": "checkpoint_1",
                "trace_id": "trace_1",
                "payload": {"error": "timeout"},
                "created_at": "2026-06-01T00:10:00+00:00",
            },
        )
    )

    assert store.dead_letters == [
        DeadLetterJobMigrationRecord(
            id="dead_1",
            queue_id="queue_1",
            run_id="run_1",
            tenant_id="tenant_1",
            reason="max_attempts_exhausted",
            last_checkpoint_id="checkpoint_1",
            trace_id="trace_1",
            payload={"error": "timeout"},
            created_at=datetime(2026, 6, 1, 0, 10, tzinfo=UTC),
        )
    ]


async def test_idempotency_record_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingDurableMigrationStore()
    writer = IdempotencyRecordTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="idempotency_records",
            source_pk="tenant_1:tool:tool:tenant_1:run_1:hash",
            checksum="sha256:a",
            payload={
                "key": "tool:tenant_1:run_1:hash",
                "tenant_id": "tenant_1",
                "scope": "tool",
                "request_checksum": "sha256:req",
                "status": "completed",
                "response_payload": {"ok": True},
                "locked_until": "2026-06-01T00:05:00+00:00",
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-01T00:01:00+00:00",
            },
        )
    )

    assert store.idempotency_records == [
        IdempotencyMigrationRecord(
            key="tool:tenant_1:run_1:hash",
            tenant_id="tenant_1",
            scope="tool",
            request_checksum="sha256:req",
            status="completed",
            response_payload={"ok": True},
            locked_until=datetime(2026, 6, 1, 0, 5, tzinfo=UTC),
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 1, 0, 1, tzinfo=UTC),
        )
    ]


async def test_outbox_event_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingDurableMigrationStore()
    writer = OutboxEventTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="outbox_events",
            source_pk="tenant_1:outbox_1",
            checksum="sha256:a",
            payload={
                "id": "outbox_1",
                "tenant_id": "tenant_1",
                "run_id": "run_1",
                "destination": "slack",
                "event_type": "slack.message",
                "idempotency_key": "slack:msg_1",
                "status": "retryable_failed",
                "attempt": 2,
                "max_attempts": 5,
                "available_at": "2026-06-01T00:03:00+00:00",
                "payload": {"channel": "C123"},
                "last_error": "rate limited",
                "lease_owner": "worker_1",
                "lease_expires_at": "2026-06-01T00:04:00+00:00",
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-01T00:02:00+00:00",
            },
        )
    )

    assert store.outbox_events == [
        OutboxEventMigrationRecord(
            id="outbox_1",
            tenant_id="tenant_1",
            run_id="run_1",
            destination="slack",
            event_type="slack.message",
            idempotency_key="slack:msg_1",
            status="retryable_failed",
            attempt=2,
            max_attempts=5,
            available_at=datetime(2026, 6, 1, 0, 3, tzinfo=UTC),
            payload={"channel": "C123"},
            last_error="rate limited",
            lease_owner="worker_1",
            lease_expires_at=datetime(2026, 6, 1, 0, 4, tzinfo=UTC),
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 1, 0, 2, tzinfo=UTC),
        )
    ]


async def test_inbox_event_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingDurableMigrationStore()
    writer = InboxEventTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="inbox_events",
            source_pk="tenant_1:slack:Ev123",
            checksum="sha256:a",
            payload={
                "id": "inbox_1",
                "tenant_id": "tenant_1",
                "source": "slack",
                "source_event_id": "Ev123",
                "event_type": "message",
                "status": "processed",
                "payload": {"event": {"type": "message"}},
                "received_at": "2026-06-01T00:04:00+00:00",
                "processed_at": "2026-06-01T00:05:00+00:00",
            },
        )
    )

    assert store.inbox_events == [
        InboxEventMigrationRecord(
            id="inbox_1",
            tenant_id="tenant_1",
            source="slack",
            source_event_id="Ev123",
            event_type="message",
            status="processed",
            payload={"event": {"type": "message"}},
            received_at=datetime(2026, 6, 1, 0, 4, tzinfo=UTC),
            processed_at=datetime(2026, 6, 1, 0, 5, tzinfo=UTC),
        )
    ]


async def test_migration_target_dispatcher_routes_rows_by_source_table() -> None:
    runtime_settings = RecordingRuntimeSettingsStore()
    slack_bots = RecordingSlackBotStore()
    tenants = RecordingTenantStore(
        [
            TenantRecord(
                id="tenant_1",
                name="Acme",
                slug="acme",
                plan=TenantPlan.BUSINESS,
                status=TenantStatus.ACTIVE,
                metadata={"tier": "paid"},
                created_at=datetime(2026, 6, 1, tzinfo=UTC),
                updated_at=datetime(2026, 6, 1, tzinfo=UTC),
            )
        ]
    )
    dispatcher = MigrationTargetDispatcher(
        [
            RuntimeSettingsTargetWriter(runtime_settings),
            SlackBotTargetWriter(slack_bots),
            TenantSloConfigTargetWriter(tenants),
        ]
    )

    assert dispatcher.target_tables == (
        "runtime_settings",
        "slack_bot_instances",
        "tenant_slo_config",
    )

    await dispatcher.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="runtime_settings",
            source_pk="tenant_1:feature.a2a.enabled",
            checksum="sha256:a",
            payload={
                "tenant_id": "tenant_1",
                "key": "feature.a2a.enabled",
                "value": "true",
            },
        )
    )
    await dispatcher.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="slack_bot_instances",
            source_pk="tenant_1:bot_1",
            checksum="sha256:b",
            payload={
                "id": "bot_1",
                "tenant_id": "tenant_1",
                "name": "Support Bot",
                "bot_token": BOT_TOKEN,
                "app_token": APP_TOKEN,
                "persona_id": "support",
            },
        )
    )
    await dispatcher.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="tenant_slo_config",
            source_pk="tenant_1",
            checksum="sha256:c",
            payload={
                "tenant_id": "tenant_1",
                "slo_availability": 0.999,
                "slo_latency_p99_ms": 4500,
                "metadata": {"legacy_slo_config": {"error_budget_window_days": 28}},
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert [update.key for update in runtime_settings.updates] == ["feature.a2a.enabled"]
    assert [record.id for record in slack_bots.records] == ["bot_1"]
    assert tenants.records[-1].slo_availability == 0.999
    assert tenants.records[-1].metadata["legacy_slo_config"] == {"error_budget_window_days": 28}


async def test_legacy_conversation_message_rows_import_to_synthetic_run_events() -> None:
    store = RecordingRunMigrationStore()
    dispatcher = MigrationTargetDispatcher(
        [
            AgentRunTargetWriter(store),
            AgentRunEventTargetWriter(store),
        ]
    )
    legacy_rows = legacy_conversation_message_rows(
        {
            "id": 7,
            "session_id": "session_1",
            "user_id": "user_1",
            "role": "assistant",
            "content": "The deployment summary is ready.",
            "timestamp": 1_767_000_000_000,
            "created_at": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        },
        tenant_id="tenant_1",
    )

    for legacy_row in legacy_rows:
        await dispatcher.write(
            ImportedRow(
                batch_id="batch_1",
                source_table=legacy_row.source_table,
                source_pk=legacy_row.source_pk,
                checksum="sha256:a",
                payload=legacy_row.payload,
            )
        )

    assert store.runs == [
        AgentRunMigrationRecord(
            id="legacy_conv_tenant_1_session_1",
            tenant_id="tenant_1",
            user_id="user_1",
            thread_id="session_1",
            checkpoint_ns="legacy-conversation",
            status="completed",
            input_text="Legacy conversation session session_1",
            response_text=None,
            error_code=None,
            metadata={
                "source": "spring_conversation_messages",
                "legacy_session_id": "session_1",
            },
            created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        )
    ]
    assert store.events == [
        AgentRunEventMigrationRecord(
            id=None,
            run_id="legacy_conv_tenant_1_session_1",
            tenant_id="tenant_1",
            sequence=7,
            event_type="legacy.conversation.message",
            payload={
                "role": "assistant",
                "content": "The deployment summary is ready.",
                "legacy_message_id": 7,
                "legacy_session_id": "session_1",
                "user_id": "user_1",
                "timestamp_ms": 1_767_000_000_000,
            },
            created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        )
    ]


async def test_legacy_conversation_summary_rows_import_to_synthetic_run_events() -> None:
    store = RecordingRunMigrationStore()
    dispatcher = MigrationTargetDispatcher(
        [
            AgentRunTargetWriter(store),
            AgentRunEventTargetWriter(store),
        ]
    )
    legacy_rows = legacy_conversation_summary_rows(
        {
            "session_id": "session_1",
            "narrative": "User asked about deployment status.",
            "facts_json": '[{"key":"service","value":"api"}]',
            "summarized_up_to": 7,
            "created_at": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            "updated_at": datetime(2026, 1, 1, 12, 5, tzinfo=UTC),
        },
        tenant_id="tenant_1",
    )

    for legacy_row in legacy_rows:
        await dispatcher.write(
            ImportedRow(
                batch_id="batch_1",
                source_table=legacy_row.source_table,
                source_pk=legacy_row.source_pk,
                checksum="sha256:a",
                payload=legacy_row.payload,
            )
        )

    assert store.runs[0].id == "legacy_conv_summary_tenant_1_session_1"
    assert store.runs[0].response_text == "User asked about deployment status."
    assert store.events == [
        AgentRunEventMigrationRecord(
            id=None,
            run_id="legacy_conv_summary_tenant_1_session_1",
            tenant_id="tenant_1",
            sequence=1,
            event_type="legacy.conversation.summary",
            payload={
                "legacy_session_id": "session_1",
                "narrative": "User asked about deployment status.",
                "facts": [{"key": "service", "value": "api"}],
                "summarized_up_to": 7,
            },
            created_at=datetime(2026, 1, 1, 12, 5, tzinfo=UTC),
        )
    ]


async def test_migration_target_dispatcher_rejects_unregistered_tables() -> None:
    dispatcher = MigrationTargetDispatcher(
        [RuntimeSettingsTargetWriter(RecordingRuntimeSettingsStore())]
    )

    try:
        await dispatcher.write(
            ImportedRow(
                batch_id="batch_1",
                source_table="unknown_table",
                source_pk="x",
                checksum="sha256:a",
                payload={},
            )
        )
    except UnsupportedTargetTable as error:
        assert str(error) == "unsupported target table: unknown_table"
    else:
        raise AssertionError("expected UnsupportedTargetTable")


async def test_slack_bot_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingSlackBotStore()
    writer = SlackBotTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="slack_bot_instances",
            source_pk="tenant_1:bot_1",
            checksum="sha256:a",
            payload={
                "id": "bot_1",
                "tenant_id": "tenant_1",
                "name": "Support Bot",
                "bot_token": BOT_TOKEN,
                "app_token": APP_TOKEN,
                "persona_id": "support",
                "default_channel": "C123",
                "enabled": True,
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        SlackBotInstanceRecord(
            id="bot_1",
            tenant_id="tenant_1",
            name="Support Bot",
            bot_token=BOT_TOKEN,
            app_token=APP_TOKEN,
            persona_id="support",
            default_channel="C123",
            enabled=True,
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_legacy_slack_bot_instance_row_imports_with_default_tenant() -> None:
    store = RecordingSlackBotStore()
    writer = SlackBotTargetWriter(store)
    legacy_row = legacy_slack_bot_instance_row(
        {
            "id": "bot_1",
            "name": "Support Bot",
            "bot_token": BOT_TOKEN,
            "app_token": APP_TOKEN,
            "persona_id": "support",
            "default_channel": "C123",
            "enabled": True,
            "created_at": "2026-06-01T00:00:00+00:00",
            "updated_at": "2026-06-02T00:00:00+00:00",
        },
        tenant_id="tenant_1",
    )

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table=legacy_row.source_table,
            source_pk=legacy_row.source_pk,
            checksum="sha256:a",
            payload=legacy_row.payload,
        )
    )

    assert [(record.tenant_id, record.id, record.name) for record in store.records] == [
        ("tenant_1", "bot_1", "Support Bot")
    ]


async def test_proactive_channel_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingProactiveChannelStore()
    writer = ProactiveChannelTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="slack_proactive_channels",
            source_pk="tenant_1:C123",
            checksum="sha256:a",
            payload={
                "tenant_id": "tenant_1",
                "channel_id": "C123",
                "channel_name": "support",
                "added_at": "2026-06-01T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        ProactiveChannelRecord(
            tenant_id="tenant_1",
            channel_id="C123",
            channel_name="support",
            added_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
    ]


async def test_faq_registration_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingFaqRegistrationStore()
    writer = FaqRegistrationTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="channel_faq_registrations",
            source_pk="tenant_1:C123",
            checksum="sha256:a",
            payload={
                "tenant_id": "tenant_1",
                "channel_id": "C123",
                "channel_name": "support",
                "enabled": True,
                "auto_reply_mode": "always",
                "confidence_threshold": 0.82,
                "days_back": 45,
                "re_ingest_interval_hours": 12,
                "last_ingested_at": "2026-06-03T00:00:00+00:00",
                "last_message_count": 120,
                "last_chunk_count": 44,
                "last_status": "ok",
                "last_error": None,
                "registered_by": "admin_1",
                "registered_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        ChannelFaqRegistration(
            tenant_id="tenant_1",
            channel_id="C123",
            channel_name="support",
            enabled=True,
            auto_reply_mode=AutoReplyMode.ALWAYS,
            confidence_threshold=0.82,
            days_back=45,
            re_ingest_interval_hours=12,
            last_ingested_at=datetime(2026, 6, 3, tzinfo=UTC),
            last_message_count=120,
            last_chunk_count=44,
            last_status="ok",
            last_error=None,
            registered_by="admin_1",
            registered_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_legacy_channel_faq_registration_row_imports_with_default_tenant() -> None:
    store = RecordingFaqRegistrationStore()
    writer = FaqRegistrationTargetWriter(store)
    legacy_row = legacy_channel_faq_registration_row(
        {
            "channel_id": "C123",
            "channel_name": "support",
            "enabled": True,
            "auto_reply_mode": "always",
            "confidence_threshold": 0.82,
            "days_back": 45,
            "re_ingest_interval_hours": 12,
            "last_ingested_at": "2026-06-03T00:00:00+00:00",
            "last_message_count": 120,
            "last_chunk_count": 44,
            "last_status": "OK",
            "last_error": None,
            "registered_by": "admin_1",
            "registered_at": "2026-06-01T00:00:00+00:00",
            "updated_at": "2026-06-02T00:00:00+00:00",
        },
        tenant_id="tenant_1",
    )

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table=legacy_row.source_table,
            source_pk=legacy_row.source_pk,
            checksum="sha256:a",
            payload=legacy_row.payload,
        )
    )

    assert [
        (record.tenant_id, record.channel_id, record.auto_reply_mode.value)
        for record in store.records
    ] == [("tenant_1", "C123", "always")]


async def test_feedback_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingFeedbackStore()
    writer = FeedbackTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="feedback",
            source_pk="tenant_1:fb_1",
            checksum="sha256:a",
            payload={
                "feedback_id": "fb_1",
                "tenant_id": "tenant_1",
                "query": "How do I reset MFA?",
                "response": "Use the security portal.",
                "rating": "THUMBS_DOWN",
                "source": "slack_button",
                "comment": "Missing SSO path",
                "session_id": "session_1",
                "run_id": "run_1",
                "user_id": "user_1",
                "intent": "support",
                "domain": "security",
                "model": "gpt-4.1",
                "prompt_version": 7,
                "tools_used": ["rag.search"],
                "duration_ms": 1234,
                "tags": ["security", "faq"],
                "review_status": "done",
                "review_tags": ["sso", "docs"],
                "reviewed_by": "admin_1",
                "reviewed_at": "2026-06-03T00:00:00+00:00",
                "review_note": "Added to FAQ backlog",
                "version": 3,
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        Feedback(
            feedback_id="fb_1",
            tenant_id="tenant_1",
            query="How do I reset MFA?",
            response="Use the security portal.",
            rating=FeedbackRating.THUMBS_DOWN,
            source="slack_button",
            comment="Missing SSO path",
            session_id="session_1",
            run_id="run_1",
            user_id="user_1",
            intent="support",
            domain="security",
            model="gpt-4.1",
            prompt_version=7,
            tools_used=["rag.search"],
            duration_ms=1234,
            tags=["security", "faq"],
            review_status="done",
            review_tags=["sso", "docs"],
            reviewed_by="admin_1",
            reviewed_at=datetime(2026, 6, 3, tzinfo=UTC),
            review_note="Added to FAQ backlog",
            version=3,
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_legacy_feedback_row_imports_with_default_tenant_and_text_lists() -> None:
    store = RecordingFeedbackStore()
    writer = FeedbackTargetWriter(store)
    legacy_row = legacy_feedback_row(
        {
            "feedback_id": "fb_1",
            "query": "How do I reset MFA?",
            "response": "Use the security portal.",
            "rating": "THUMBS_DOWN",
            "timestamp": "2026-06-01T00:00:00+00:00",
            "comment": "Missing SSO path",
            "session_id": "session_1",
            "run_id": "run_1",
            "user_id": "user_1",
            "tools_used": "rag.search, jira.lookup",
            "tags": "mfa, sso",
        },
        tenant_id="tenant_1",
    )

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table=legacy_row.source_table,
            source_pk=legacy_row.source_pk,
            checksum="sha256:a",
            payload=legacy_row.payload,
        )
    )

    assert [
        (record.tenant_id, record.feedback_id, record.tools_used, record.tags)
        for record in store.records
    ] == [
        (
            "tenant_1",
            "fb_1",
            ["rag.search", "jira.lookup"],
            ["mfa", "sso"],
        )
    ]


async def test_eval_case_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingEvalCaseStore()
    writer = EvalCaseTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="agent_eval_cases",
            source_pk="tenant_1:case_1",
            checksum="sha256:a",
            payload={
                "id": "case_1",
                "tenant_id": "tenant_1",
                "name": "MFA reset",
                "user_input": "How do I reset MFA?",
                "expected_answer_contains": ["security portal"],
                "forbidden_answer_contains": ["ask admin"],
                "expected_tool_names": ["search_docs"],
                "forbidden_tool_names": ["delete_user"],
                "expected_exposed_tool_names": ["search_docs"],
                "forbidden_exposed_tool_names": ["delete_user"],
                "max_tool_exposure_count": 3,
                "agent_type": "reactor",
                "model": "gpt-5",
                "enabled": True,
                "tags": ["security", "faq"],
                "min_score": 0.8,
                "source_run_id": "run_1",
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        AgentEvalCaseRecord(
            id="case_1",
            tenant_id="tenant_1",
            name="MFA reset",
            user_input="How do I reset MFA?",
            expected_answer_contains=("security portal",),
            forbidden_answer_contains=("ask admin",),
            expected_tool_names=("search_docs",),
            forbidden_tool_names=("delete_user",),
            expected_exposed_tool_names=("search_docs",),
            forbidden_exposed_tool_names=("delete_user",),
            max_tool_exposure_count=3,
            agent_type="reactor",
            model="gpt-5",
            enabled=True,
            tags=("security", "faq"),
            min_score=0.8,
            source_run_id="run_1",
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_eval_result_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingEvalResultStore()
    writer = EvalResultTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="agent_eval_results",
            source_pk="tenant_1:result_1",
            checksum="sha256:a",
            payload={
                "id": "result_1",
                "tenant_id": "tenant_1",
                "case_id": "case_1",
                "run_id": "run_1",
                "tier": "deterministic",
                "passed": False,
                "score": 0.4,
                "reasons": ["missing expected phrase"],
                "evaluated_at": "2026-06-03T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        AgentEvalStoredResultRecord(
            id="result_1",
            tenant_id="tenant_1",
            case_id="case_1",
            run_id="run_1",
            tier="deterministic",
            passed=False,
            score=0.4,
            reasons=("missing expected phrase",),
            evaluated_at=datetime(2026, 6, 3, tzinfo=UTC),
        )
    ]


async def test_scheduled_job_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingSchedulerStore()
    writer = ScheduledJobTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="scheduled_jobs",
            source_pk="tenant_1:job_1",
            checksum="sha256:a",
            payload={
                "id": "job_1",
                "tenant_id": "tenant_1",
                "name": "Daily docs sync",
                "description": "Sync knowledge docs",
                "cron_expression": "0 9 * * *",
                "timezone": "Asia/Seoul",
                "job_type": "MCP_TOOL",
                "mcp_server_name": "docs",
                "tool_name": "sync_docs",
                "tool_arguments": {"space": "ENG"},
                "tags": ["docs", "sync"],
                "slack_channel_id": "C123",
                "retry_on_failure": True,
                "max_retry_count": 2,
                "execution_timeout_ms": 30000,
                "enabled": True,
                "last_run_at": "2026-06-03T00:00:00+00:00",
                "last_status": "SUCCESS",
                "last_result": "ok",
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        ScheduledJobRecord(
            id="job_1",
            tenant_id="tenant_1",
            name="Daily docs sync",
            description="Sync knowledge docs",
            cron_expression="0 9 * * *",
            timezone="Asia/Seoul",
            job_type=ScheduledJobType.MCP_TOOL,
            mcp_server_name="docs",
            tool_name="sync_docs",
            tool_arguments={"space": "ENG"},
            tags=frozenset({"docs", "sync"}),
            slack_channel_id="C123",
            retry_on_failure=True,
            max_retry_count=2,
            execution_timeout_ms=30000,
            enabled=True,
            last_run_at=datetime(2026, 6, 3, tzinfo=UTC),
            last_status=JobExecutionStatus.SUCCESS,
            last_result="ok",
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_legacy_scheduled_job_row_imports_as_mcp_tool_job() -> None:
    store = RecordingSchedulerStore()
    writer = ScheduledJobTargetWriter(store)
    legacy_row = legacy_scheduled_job_row(
        {
            "id": "job_1",
            "name": "Daily docs sync",
            "description": "Sync knowledge docs",
            "cron_expression": "0 0 9 * * *",
            "timezone": "Asia/Seoul",
            "mcp_server_name": "docs",
            "tool_name": "sync_docs",
            "tool_arguments": '{"space":"ENG"}',
            "retry_on_failure": True,
            "max_retry_count": 2,
            "execution_timeout_ms": 30000,
            "created_at": "2026-06-01T00:00:00+00:00",
            "updated_at": "2026-06-02T00:00:00+00:00",
        },
        tenant_id="tenant_1",
    )

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table=legacy_row.source_table,
            source_pk=legacy_row.source_pk,
            checksum="sha256:a",
            payload=legacy_row.payload,
        )
    )

    assert store.records == [
        ScheduledJobRecord(
            id="job_1",
            tenant_id="tenant_1",
            name="Daily docs sync",
            description="Sync knowledge docs",
            cron_expression="0 0 9 * * *",
            timezone="Asia/Seoul",
            job_type=ScheduledJobType.MCP_TOOL,
            mcp_server_name="docs",
            tool_name="sync_docs",
            tool_arguments={"space": "ENG"},
            retry_on_failure=True,
            max_retry_count=2,
            execution_timeout_ms=30000,
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_scheduled_job_execution_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingScheduledJobExecutionStore()
    writer = ScheduledJobExecutionTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="scheduled_job_executions",
            source_pk="tenant_1:exec_1",
            checksum="sha256:a",
            payload={
                "id": "exec_1",
                "tenant_id": "tenant_1",
                "job_id": "job_1",
                "job_name": "Daily docs sync",
                "job_type": "MCP_TOOL",
                "status": "SUCCESS",
                "result": "ok",
                "duration_ms": 2500,
                "dry_run": False,
                "started_at": "2026-06-03T00:00:00+00:00",
                "completed_at": "2026-06-03T00:00:03+00:00",
            },
        )
    )

    assert store.records == [
        ScheduledJobExecutionRecord(
            id="exec_1",
            tenant_id="tenant_1",
            job_id="job_1",
            job_name="Daily docs sync",
            job_type=ScheduledJobType.MCP_TOOL,
            status=JobExecutionStatus.SUCCESS,
            result="ok",
            duration_ms=2500,
            dry_run=False,
            started_at=datetime(2026, 6, 3, tzinfo=UTC),
            completed_at=datetime(2026, 6, 3, 0, 0, 3, tzinfo=UTC),
        )
    ]


async def test_legacy_scheduled_job_execution_row_imports_with_default_job_type() -> None:
    store = RecordingScheduledJobExecutionStore()
    writer = ScheduledJobExecutionTargetWriter(store)
    legacy_row = legacy_scheduled_job_execution_row(
        {
            "id": "exec_1",
            "job_id": "job_1",
            "job_name": "Daily docs sync",
            "status": "SUCCESS",
            "result": "ok",
            "duration_ms": 2500,
            "dry_run": False,
            "started_at": "2026-06-03T00:00:00+00:00",
            "completed_at": "2026-06-03T00:00:03+00:00",
        },
        tenant_id="tenant_1",
    )

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table=legacy_row.source_table,
            source_pk=legacy_row.source_pk,
            checksum="sha256:a",
            payload=legacy_row.payload,
        )
    )

    assert store.records == [
        ScheduledJobExecutionRecord(
            id="exec_1",
            tenant_id="tenant_1",
            job_id="job_1",
            job_name="Daily docs sync",
            job_type=ScheduledJobType.MCP_TOOL,
            status=JobExecutionStatus.SUCCESS,
            result="ok",
            duration_ms=2500,
            dry_run=False,
            started_at=datetime(2026, 6, 3, tzinfo=UTC),
            completed_at=datetime(2026, 6, 3, 0, 0, 3, tzinfo=UTC),
        )
    ]


async def test_scheduled_job_dead_letter_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingScheduledJobDeadLetterStore()
    writer = ScheduledJobDeadLetterTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="scheduled_job_dead_letters",
            source_pk="tenant_1:dead_1",
            checksum="sha256:a",
            payload={
                "id": "dead_1",
                "tenant_id": "tenant_1",
                "job_id": "job_1",
                "job_name": "Daily docs sync",
                "job_type": "MCP_TOOL",
                "reason": "timeout",
                "result": "Job failed: timeout",
                "dry_run": True,
                "created_at": "2026-06-04T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        ScheduledJobDeadLetterRecord(
            id="dead_1",
            tenant_id="tenant_1",
            job_id="job_1",
            job_name="Daily docs sync",
            job_type=ScheduledJobType.MCP_TOOL,
            reason="timeout",
            result="Job failed: timeout",
            dry_run=True,
            created_at=datetime(2026, 6, 4, tzinfo=UTC),
        )
    ]


async def test_model_pricing_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingModelPricingStore()
    writer = ModelPricingTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="model_pricing",
            source_pk="openai:gpt-5-mini:pricing_1",
            checksum="sha256:a",
            payload={
                "id": "pricing_1",
                "provider": "openai",
                "model": "gpt-5-mini",
                "prompt_price_per_1m": "1.25000000",
                "completion_price_per_1m": "10.00000000",
                "cached_input_price_per_1m": "0.12500000",
                "reasoning_price_per_1m": "2.00000000",
                "batch_prompt_price_per_1m": "0.50000000",
                "batch_completion_price_per_1m": "5.00000000",
                "effective_from": "2026-06-01T00:00:00+00:00",
                "effective_to": "2026-07-01T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        ModelPricing(
            id="pricing_1",
            provider="openai",
            model="gpt-5-mini",
            prompt_price_per_1m=Decimal("1.25000000"),
            completion_price_per_1m=Decimal("10.00000000"),
            cached_input_price_per_1m=Decimal("0.12500000"),
            reasoning_price_per_1m=Decimal("2.00000000"),
            batch_prompt_price_per_1m=Decimal("0.50000000"),
            batch_completion_price_per_1m=Decimal("5.00000000"),
            effective_from=datetime(2026, 6, 1, tzinfo=UTC),
            effective_to=datetime(2026, 7, 1, tzinfo=UTC),
        )
    ]


async def test_legacy_v42_model_pricing_row_imports_with_per_1m_prices() -> None:
    store = RecordingModelPricingStore()
    writer = ModelPricingTargetWriter(store)
    legacy_row = legacy_v42_model_pricing_row(
        {
            "id": "pricing_1",
            "provider": "openai",
            "model": "gpt-5-mini",
            "prompt_price_per_1k": "0.00125",
            "completion_price_per_1k": "0.01000",
            "cached_input_price_per_1k": "0.000125",
            "reasoning_price_per_1k": "0.00200",
            "batch_prompt_price_per_1k": "0.00050",
            "batch_completion_price_per_1k": "0.00500",
            "effective_from": "2026-06-01T00:00:00+00:00",
            "effective_to": "2026-07-01T00:00:00+00:00",
        }
    )

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table=legacy_row.source_table,
            source_pk=legacy_row.source_pk,
            checksum="sha256:a",
            payload=legacy_row.payload,
        )
    )

    assert store.records == [
        ModelPricing(
            id="pricing_1",
            provider="openai",
            model="gpt-5-mini",
            prompt_price_per_1m=Decimal("1.25000000"),
            completion_price_per_1m=Decimal("10.00000000"),
            cached_input_price_per_1m=Decimal("0.12500000"),
            reasoning_price_per_1m=Decimal("2.00000000"),
            batch_prompt_price_per_1m=Decimal("0.50000000"),
            batch_completion_price_per_1m=Decimal("5.00000000"),
            effective_from=datetime(2026, 6, 1, tzinfo=UTC),
            effective_to=datetime(2026, 7, 1, tzinfo=UTC),
        )
    ]


async def test_usage_ledger_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingUsageLedgerStore()
    writer = UsageLedgerTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="usage_ledger",
            source_pk="tenant_1:usage_1",
            checksum="sha256:a",
            payload={
                "id": "usage_1",
                "tenant_id": "tenant_1",
                "run_id": "run_1",
                "provider": "openai",
                "model": "gpt-5-mini",
                "step_type": "model",
                "prompt_tokens": 100,
                "cached_tokens": 20,
                "completion_tokens": 30,
                "reasoning_tokens": 5,
                "total_tokens": 135,
                "estimated_cost_usd": "0.12345678",
                "occurred_at": "2026-06-03T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        UsageLedgerRecord(
            id="usage_1",
            tenant_id="tenant_1",
            run_id="run_1",
            provider="openai",
            model="gpt-5-mini",
            step_type="model",
            prompt_tokens=100,
            cached_tokens=20,
            completion_tokens=30,
            reasoning_tokens=5,
            total_tokens=135,
            estimated_cost_usd=Decimal("0.12345678"),
            occurred_at=datetime(2026, 6, 3, tzinfo=UTC),
        )
    ]


async def test_legacy_metric_token_usage_row_imports_to_usage_ledger_store() -> None:
    store = RecordingUsageLedgerStore()
    writer = UsageLedgerTargetWriter(store)
    legacy_row = legacy_metric_token_usage_row(
        {
            "time": datetime(2026, 6, 1, 13, 30, tzinfo=UTC),
            "tenant_id": "tenant_1",
            "run_id": "run_1",
            "provider": "openai",
            "model": "gpt-5-mini",
            "step_type": "act",
            "prompt_tokens": 100,
            "prompt_cached_tokens": 20,
            "completion_tokens": 30,
            "reasoning_tokens": 5,
            "total_tokens": 155,
            "estimated_cost_usd": Decimal("0.12345678"),
        }
    )

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table=legacy_row.source_table,
            source_pk=legacy_row.source_pk,
            checksum="sha256:a",
            payload=legacy_row.payload,
        )
    )

    assert store.records == [
        UsageLedgerRecord(
            id="usage_metric_tenant_1_run_1_20260601T133000_openai_gpt_5_mini_act",
            tenant_id="tenant_1",
            run_id="run_1",
            provider="openai",
            model="gpt-5-mini",
            step_type="act",
            prompt_tokens=100,
            cached_tokens=20,
            completion_tokens=30,
            reasoning_tokens=5,
            total_tokens=155,
            estimated_cost_usd=Decimal("0.12345678"),
            occurred_at=datetime(2026, 6, 1, 13, 30, tzinfo=UTC),
        )
    ]


async def test_tenant_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingTenantStore()
    writer = TenantTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="tenants",
            source_pk="tenant_1",
            checksum="sha256:a",
            payload={
                "id": "tenant_1",
                "name": "Acme",
                "slug": "acme",
                "plan": "BUSINESS",
                "status": "ACTIVE",
                "max_requests_per_month": 100_000,
                "max_tokens_per_month": 100_000_000,
                "max_users": 100,
                "max_agents": 50,
                "max_mcp_servers": 30,
                "billing_cycle_start": 5,
                "billing_email": "billing@example.com",
                "slo_availability": 0.999,
                "slo_latency_p99_ms": 5000,
                "metadata": {"tier": "paid"},
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        TenantRecord(
            id="tenant_1",
            name="Acme",
            slug="acme",
            plan=TenantPlan.BUSINESS,
            status=TenantStatus.ACTIVE,
            quota=TenantQuota(
                max_requests_per_month=100_000,
                max_tokens_per_month=100_000_000,
                max_users=100,
                max_agents=50,
                max_mcp_servers=30,
            ),
            billing_cycle_start=5,
            billing_email="billing@example.com",
            slo_availability=0.999,
            slo_latency_p99_ms=5000,
            metadata={"tier": "paid"},
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_legacy_slo_config_row_updates_existing_tenant_slo_metadata() -> None:
    existing = TenantRecord(
        id="tenant_1",
        name="Acme",
        slug="acme",
        plan=TenantPlan.BUSINESS,
        status=TenantStatus.ACTIVE,
        quota=TenantQuota(max_requests_per_month=100_000),
        billing_email="billing@example.com",
        metadata={"tier": "paid"},
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        updated_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    store = RecordingTenantStore([existing])
    writer = TenantSloConfigTargetWriter(store)
    legacy_row = legacy_slo_config_row(
        {
            "id": "slo_1",
            "tenant_id": "tenant_1",
            "availability_target": 0.999,
            "latency_p99_target_ms": 4500,
            "apdex_satisfied_ms": 1200,
            "apdex_tolerating_ms": 5000,
            "error_budget_window_days": 28,
            "created_at": datetime(2026, 6, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 6, 2, tzinfo=UTC),
        }
    )

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table=legacy_row.source_table,
            source_pk=legacy_row.source_pk,
            checksum="sha256:a",
            payload=legacy_row.payload,
        )
    )

    updated = store.records[-1]
    assert updated.name == "Acme"
    assert updated.slug == "acme"
    assert updated.plan == TenantPlan.BUSINESS
    assert updated.quota.max_requests_per_month == 100_000
    assert updated.slo_availability == 0.999
    assert updated.slo_latency_p99_ms == 4500
    assert updated.metadata == {
        "tier": "paid",
        "legacy_slo_config": {
            "id": "slo_1",
            "apdex_satisfied_ms": 1200,
            "apdex_tolerating_ms": 5000,
            "error_budget_window_days": 28,
            "created_at": "2026-06-01T00:00:00+00:00",
            "updated_at": "2026-06-02T00:00:00+00:00",
        },
    }
    assert updated.updated_at == datetime(2026, 6, 2, tzinfo=UTC)


async def test_alert_rule_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingAlertStore()
    writer = AlertRuleTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="alert_rules",
            source_pk="tenant_1:rule_1",
            checksum="sha256:a",
            payload={
                "id": "rule_1",
                "tenant_id": "tenant_1",
                "name": "High error rate",
                "description": "API errors",
                "type": "STATIC_THRESHOLD",
                "severity": "CRITICAL",
                "metric": "error_rate",
                "threshold": 0.1,
                "window_minutes": 15,
                "enabled": True,
                "platform_only": False,
                "created_at": "2026-06-01T00:00:00+00:00",
            },
        )
    )

    assert store.rules == [
        AlertRule(
            id="rule_1",
            tenant_id="tenant_1",
            name="High error rate",
            description="API errors",
            type=AlertType.STATIC_THRESHOLD,
            severity=AlertSeverity.CRITICAL,
            metric="error_rate",
            threshold=0.1,
            window_minutes=15,
            enabled=True,
            platform_only=False,
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
    ]


async def test_alert_instance_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingAlertStore()
    writer = AlertInstanceTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="alert_instances",
            source_pk="rule_1:alert_1",
            checksum="sha256:a",
            payload={
                "id": "alert_1",
                "rule_id": "rule_1",
                "tenant_id": "tenant_1",
                "severity": "CRITICAL",
                "status": "RESOLVED",
                "message": "error_rate exceeded threshold",
                "metric_value": 0.2,
                "threshold": 0.1,
                "fired_at": "2026-06-02T00:00:00+00:00",
                "resolved_at": "2026-06-03T00:00:00+00:00",
                "acknowledged_by": "admin_1",
            },
        )
    )

    assert store.alerts == [
        AlertInstance(
            id="alert_1",
            rule_id="rule_1",
            tenant_id="tenant_1",
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.RESOLVED,
            message="error_rate exceeded threshold",
            metric_value=0.2,
            threshold=0.1,
            fired_at=datetime(2026, 6, 2, tzinfo=UTC),
            resolved_at=datetime(2026, 6, 3, tzinfo=UTC),
            acknowledged_by="admin_1",
        )
    ]


async def test_auth_user_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingUserStore()
    writer = AuthUserTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="users",
            source_pk="tenant_1:user_1",
            checksum="sha256:a",
            payload={
                "id": "user_1",
                "email": "admin@example.com",
                "name": "Admin User",
                "password_hash": "$argon2id$v=19$hash",
                "role": "ADMIN",
                "tenant_id": "tenant_1",
                "groups": ["engineering", "finance"],
                "created_at": "2026-06-01T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        UserRecord(
            id="user_1",
            email="admin@example.com",
            name="Admin User",
            password_hash="$argon2id$v=19$hash",  # noqa: S106
            role=UserRole.ADMIN,
            tenant_id="tenant_1",
            groups=("engineering", "finance"),
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
    ]


async def test_legacy_user_row_imports_with_default_tenant_role_and_created_at() -> None:
    store = RecordingUserStore()
    writer = AuthUserTargetWriter(store)
    legacy_row = legacy_user_row(
        {
            "id": "user_1",
            "email": "admin@example.com",
            "name": "Admin User",
            "password_hash": "$argon2id$v=19$hash",
            "created_at": "2026-06-01T00:00:00+00:00",
        },
        default_tenant_id="tenant_1",
    )

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table=legacy_row.source_table,
            source_pk=legacy_row.source_pk,
            checksum="sha256:a",
            payload=legacy_row.payload,
        )
    )

    assert store.records == [
        UserRecord(
            id="user_1",
            email="admin@example.com",
            name="Admin User",
            password_hash="$argon2id$v=19$hash",  # noqa: S106
            role=UserRole.USER,
            tenant_id="tenant_1",
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
    ]


async def test_user_identity_target_writer_maps_external_subject_to_user() -> None:
    store = RecordingUserIdentityStore()
    writer = UserIdentityTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="user_identities",
            source_pk="tenant_1:jira:acct-123",
            checksum="sha256:a",
            payload={
                "id": "identity_1",
                "tenant_id": "tenant_1",
                "user_id": "user_1",
                "provider": "jira",
                "external_subject": "acct-123",
                "metadata": {"workspace": "ENG"},
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        UserIdentityRecord(
            id="identity_1",
            tenant_id="tenant_1",
            user_id="user_1",
            provider="jira",
            external_subject="acct-123",
            metadata={"workspace": "ENG"},
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_legacy_slack_identity_rows_import_as_generalized_external_subjects() -> None:
    store = RecordingUserIdentityStore()
    writer = UserIdentityTargetWriter(store)
    rows = legacy_slack_user_identity_rows(
        {
            "slack_user_id": "U123",
            "email": "employee@example.com",
            "display_name": "Employee One",
            "jira_account_id": "jira-account-123",
            "bitbucket_uuid": None,
            "created_at": "2026-06-01T00:00:00+00:00",
            "updated_at": "2026-06-02T00:00:00+00:00",
        },
        tenant_id="tenant_1",
        user_id="user_1",
    )

    for index, legacy_row in enumerate(rows, start=1):
        await writer.write(
            ImportedRow(
                batch_id="batch_1",
                source_table=legacy_row.source_table,
                source_pk=legacy_row.source_pk,
                checksum=f"sha256:{index}",
                payload=legacy_row.payload,
            )
        )

    assert [(record.provider, record.external_subject) for record in store.records] == [
        ("slack", "U123"),
        ("email", "employee@example.com"),
        ("jira", "jira-account-123"),
    ]
    assert store.records[0].metadata == {
        "email": "employee@example.com",
        "display_name": "Employee One",
        "legacy_slack_user_id": "U123",
    }


async def test_auth_token_revocation_target_writer_preserves_revoked_at() -> None:
    store = RecordingTokenRevocationMigrationStore()
    writer = AuthTokenRevocationTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="auth_token_revocations",
            source_pk="jti_1",
            checksum="sha256:a",
            payload={
                "token_id": "jti_1",
                "expires_at": "2026-06-03T00:00:00+00:00",
                "revoked_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        TokenRevocationRecord(
            token_id="jti_1",  # noqa: S106
            expires_at=datetime(2026, 6, 3, tzinfo=UTC),
            revoked_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_input_guard_rule_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingInputGuardRuleStore()
    writer = InputGuardRuleTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="input_guard_rules",
            source_pk="tenant_1:input_rule_1",
            checksum="sha256:a",
            payload={
                "id": "input_rule_1",
                "tenant_id": "tenant_1",
                "name": "Block jailbreak",
                "pattern": "ignore previous instructions",
                "pattern_type": "keyword",
                "action": "block",
                "priority": 900,
                "category": "prompt_injection",
                "description": "Legacy prompt injection rule",
                "enabled": True,
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        InputGuardRuleRecord(
            id="input_rule_1",
            tenant_id="tenant_1",
            name="Block jailbreak",
            pattern="ignore previous instructions",
            pattern_type=PatternType.KEYWORD,
            action=RuleAction.BLOCK,
            priority=900,
            category="prompt_injection",
            description="Legacy prompt injection rule",
            enabled=True,
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_legacy_metric_guard_event_row_imports_to_guard_metric_store() -> None:
    store = RecordingInputGuardMetricStore()
    writer = InputGuardMetricTargetWriter(store)
    legacy_row = legacy_metric_guard_event_row(
        {
            "time": datetime(2026, 6, 1, 14, 0, tzinfo=UTC),
            "tenant_id": "tenant_1",
            "user_id": "user_1",
            "channel": "slack",
            "stage": "InjectionDetection",
            "category": "prompt_injection",
            "reason_class": "jailbreak",
            "reason_detail": "ignore previous instructions",
            "is_output_guard": False,
            "action": "rejected",
        }
    )

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table=legacy_row.source_table,
            source_pk=legacy_row.source_pk,
            checksum="sha256:a",
            payload=legacy_row.payload,
        )
    )

    assert store.records == [
        InputGuardMetricMigrationRecord(
            time=datetime(2026, 6, 1, 14, 0, tzinfo=UTC),
            tenant_id="tenant_1",
            user_id="user_1",
            channel="slack",
            stage="InjectionDetection",
            category="prompt_injection",
            reason_class="jailbreak",
            reason_detail="ignore previous instructions",
            is_output_guard=False,
            action="rejected",
        )
    ]


async def test_output_guard_rule_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingOutputGuardRuleStore()
    writer = OutputGuardRuleTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="output_guard_rules",
            source_pk="tenant_1:output_rule_1",
            checksum="sha256:a",
            payload={
                "id": "output_rule_1",
                "tenant_id": "tenant_1",
                "name": "Mask API keys",
                "pattern": "sk-[A-Za-z0-9]+",
                "action": "MASK",
                "replacement": "[SECRET]",
                "priority": 10,
                "enabled": True,
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        OutputGuardRuleRecord(
            id="output_rule_1",
            tenant_id="tenant_1",
            name="Mask API keys",
            pattern="sk-[A-Za-z0-9]+",
            action=OutputGuardRuleAction.MASK,
            replacement="[SECRET]",
            priority=10,
            enabled=True,
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_output_guard_rule_audit_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingOutputGuardRuleAuditStore()
    writer = OutputGuardRuleAuditTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="output_guard_rule_audits",
            source_pk="tenant_1:audit_1",
            checksum="sha256:a",
            payload={
                "id": "audit_1",
                "tenant_id": "tenant_1",
                "rule_id": "output_rule_1",
                "action": "SIMULATE",
                "actor": "admin_1",
                "detail": "masked 2 values",
                "created_at": "2026-06-03T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        OutputGuardRuleAuditRecord(
            id="audit_1",
            tenant_id="tenant_1",
            rule_id="output_rule_1",
            action=OutputGuardRuleAuditAction.SIMULATE,
            actor="admin_1",
            detail="masked 2 values",
            created_at=datetime(2026, 6, 3, tzinfo=UTC),
        )
    ]


async def test_admin_audit_target_writer_maps_imported_rows_to_records_with_tenant() -> None:
    store = RecordingAdminAuditStore()
    writer = AdminAuditTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="admin_audits",
            source_pk="tenant_1:audit_1",
            checksum="sha256:a",
            payload={
                "id": "audit_1",
                "tenant_id": "tenant_1",
                "category": "slack",
                "action": "ADD",
                "actor": "admin@example.com",
                "resource_type": "slack_channel",
                "resource_id": "C123",
                "detail": "added proactive channel",
                "created_at": "2026-06-04T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        (
            "tenant_1",
            AdminAuditLog(
                id="audit_1",
                category="slack",
                action=AdminAuditAction.ADD,
                actor="admin@example.com",
                resource_type="slack_channel",
                resource_id="C123",
                detail="added proactive channel",
                created_at=datetime(2026, 6, 4, tzinfo=UTC),
            ),
        )
    ]


async def test_tool_catalog_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingToolCatalogStore()
    writer = ToolCatalogTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="tool_catalog",
            source_pk="tenant_1:builtin:send_webhook:tool_1",
            checksum="sha256:a",
            payload={
                "id": "tool_1",
                "tenant_id": "tenant_1",
                "namespace": "builtin",
                "name": "send_webhook",
                "description": "Send a signed webhook.",
                "risk_level": "external_side_effect",
                "input_schema": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
                "output_schema": {"type": "object"},
                "enabled": True,
                "requires_approval": True,
                "timeout_ms": 15000,
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        ToolCatalogRecord(
            id="tool_1",
            tenant_id="tenant_1",
            namespace="builtin",
            name="send_webhook",
            description="Send a signed webhook.",
            risk_level="external_side_effect",
            input_schema={
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
            output_schema={"type": "object"},
            enabled=True,
            requires_approval=True,
            timeout_ms=15000,
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_pending_approval_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingPendingApprovalStore()
    writer = PendingApprovalTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="pending_approvals",
            source_pk="tenant_1:approval_1",
            checksum="sha256:a",
            payload={
                "id": "approval_1",
                "tenant_id": "tenant_1",
                "run_id": "run_1",
                "tool_id": "tool_1",
                "status": "approved",
                "requested_by": "user_1",
                "decided_by": "admin_1",
                "request_payload": {"args": {"url": "https://example.com"}},
                "decision_reason": "approved for incident response",
                "created_at": "2026-06-03T00:00:00+00:00",
                "decided_at": "2026-06-04T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        PendingApprovalRecord(
            id="approval_1",
            tenant_id="tenant_1",
            run_id="run_1",
            tool_id="tool_1",
            status="approved",
            requested_by="user_1",
            decided_by="admin_1",
            request_payload={"args": {"url": "https://example.com"}},
            decision_reason="approved for incident response",
            created_at=datetime(2026, 6, 3, tzinfo=UTC),
            decided_at=datetime(2026, 6, 4, tzinfo=UTC),
        )
    ]


async def test_tool_invocation_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingToolInvocationStore()
    writer = ToolInvocationTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="tool_invocations",
            source_pk="tenant_1:invocation_1",
            checksum="sha256:a",
            payload={
                "id": "invocation_1",
                "tenant_id": "tenant_1",
                "run_id": "run_1",
                "tool_id": "tool_1",
                "approval_id": "approval_1",
                "status": "succeeded",
                "idempotency_key": "tool:tenant_1:run_1:builtin:send_webhook:abc",
                "request_checksum": "sha256:req",
                "result_checksum": "sha256:result",
                "input_payload": {"url": "https://example.com"},
                "output_payload": {"status": 200},
                "error_payload": None,
                "started_at": "2026-06-05T00:00:00+00:00",
                "completed_at": "2026-06-06T00:00:00+00:00",
            },
        )
    )

    assert store.records == [
        ToolInvocationRecord(
            id="invocation_1",
            tenant_id="tenant_1",
            run_id="run_1",
            tool_id="tool_1",
            approval_id="approval_1",
            status="succeeded",
            idempotency_key="tool:tenant_1:run_1:builtin:send_webhook:abc",
            request_checksum="sha256:req",
            result_checksum="sha256:result",
            input_payload={"url": "https://example.com"},
            output_payload={"status": 200},
            error_payload=None,
            started_at=datetime(2026, 6, 5, tzinfo=UTC),
            completed_at=datetime(2026, 6, 6, tzinfo=UTC),
        )
    ]


async def test_mcp_server_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingMcpStore()
    writer = McpServerTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="mcp_servers",
            source_pk="tenant_1:docs:mcp_1",
            checksum="sha256:a",
            payload={
                "id": "mcp_1",
                "tenant_id": "tenant_1",
                "name": "docs",
                "transport": "streamable_http",
                "status": "healthy",
                "command": None,
                "args": [],
                "url": "https://mcp.example.com",
                "auth_type": "oauth2",
                "timeout_ms": 20000,
                "protocol_version": "2025-11-25",
                "last_connection_error": None,
                "reconnect_policy": {"max_attempts": 3},
                "tool_snapshot_hash": "sha256:tools",
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert store.servers == [
        McpServerMigrationRecord(
            id="mcp_1",
            tenant_id="tenant_1",
            name="docs",
            transport="streamable_http",
            status="healthy",
            command=None,
            args=[],
            url="https://mcp.example.com",
            auth_type="oauth2",
            timeout_ms=20000,
            protocol_version="2025-11-25",
            last_connection_error=None,
            reconnect_policy={"max_attempts": 3},
            tool_snapshot_hash="sha256:tools",
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_mcp_server_status_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingMcpStore()
    writer = McpServerStatusTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="mcp_server_status",
            source_pk="tenant_1:mcp_1",
            checksum="sha256:a",
            payload={
                "server_id": "mcp_1",
                "tenant_id": "tenant_1",
                "status": "degraded",
                "negotiated_protocol_version": "2025-11-25",
                "last_error": "timeout",
                "reconnect_attempt": 2,
                "backoff_until": "2026-06-02T00:00:00+00:00",
                "checked_at": "2026-06-01T00:00:00+00:00",
            },
        )
    )

    assert store.statuses == [
        McpServerStatusRecord(
            server_id="mcp_1",
            tenant_id="tenant_1",
            status="degraded",
            negotiated_protocol_version="2025-11-25",
            last_error="timeout",
            reconnect_attempt=2,
            backoff_until=datetime(2026, 6, 2, tzinfo=UTC),
            checked_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
    ]


async def test_mcp_tool_snapshot_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingMcpStore()
    writer = McpToolSnapshotTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="mcp_tool_snapshots",
            source_pk="tenant_1:mcp_1:search:snapshot_1",
            checksum="sha256:a",
            payload={
                "id": "snapshot_1",
                "tenant_id": "tenant_1",
                "server_id": "mcp_1",
                "qualified_name": "docs:search",
                "tool_name": "search",
                "description": "Search docs",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "risk_level": "read",
                "enabled": True,
                "snapshot_hash": "sha256:tool",
                "created_at": "2026-06-03T00:00:00+00:00",
            },
        )
    )

    assert store.tool_snapshots == [
        McpToolSnapshotRecord(
            id="snapshot_1",
            tenant_id="tenant_1",
            server_id="mcp_1",
            qualified_name="docs:search",
            tool_name="search",
            description="Search docs",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            risk_level="read",
            enabled=True,
            snapshot_hash="sha256:tool",
            created_at=datetime(2026, 6, 3, tzinfo=UTC),
        )
    ]


async def test_mcp_access_policy_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingMcpStore()
    writer = McpAccessPolicyTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="mcp_access_policies",
            source_pk="tenant_1:standard:mcp_1:policy_1",
            checksum="sha256:a",
            payload={
                "id": "policy_1",
                "tenant_id": "tenant_1",
                "server_id": "mcp_1",
                "graph_profile": "standard",
                "allow_write": False,
                "allowed_tools": ["search"],
                "created_at": "2026-06-04T00:00:00+00:00",
            },
        )
    )

    assert store.access_policies == [
        McpAccessPolicyRecord(
            id="policy_1",
            tenant_id="tenant_1",
            server_id="mcp_1",
            graph_profile="standard",
            allow_write=False,
            allowed_tools=["search"],
            created_at=datetime(2026, 6, 4, tzinfo=UTC),
        )
    ]


async def test_a2a_peer_agent_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingA2AStore()
    writer = A2APeerAgentTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="a2a_peer_agents",
            source_pk="tenant_1:planner:peer_1",
            checksum="sha256:a",
            payload={
                "id": "peer_1",
                "tenant_id": "tenant_1",
                "name": "planner",
                "endpoint_url": "https://a2a.example.com",
                "agent_card": {"name": "Planner"},
                "enabled": True,
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert store.peers == [
        A2APeerAgentRecord(
            id="peer_1",
            tenant_id="tenant_1",
            name="planner",
            endpoint_url="https://a2a.example.com",
            agent_card={"name": "Planner"},
            enabled=True,
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_a2a_agent_card_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingA2AStore()
    writer = A2AAgentCardTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="a2a_agent_cards",
            source_pk="tenant_1:v1:card_1",
            checksum="sha256:a",
            payload={
                "id": "card_1",
                "tenant_id": "tenant_1",
                "version": "v1",
                "protocol_version": "1.0",
                "card": {"name": "Reactor"},
                "active": True,
                "created_at": "2026-06-01T00:00:00+00:00",
            },
        )
    )

    assert store.agent_cards == [
        A2AAgentCardRecord(
            id="card_1",
            tenant_id="tenant_1",
            version="v1",
            protocol_version="1.0",
            card={"name": "Reactor"},
            active=True,
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
    ]


async def test_a2a_task_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingA2AStore()
    writer = A2ATaskTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="a2a_tasks",
            source_pk="tenant_1:task_1",
            checksum="sha256:a",
            payload={
                "id": "task_1",
                "tenant_id": "tenant_1",
                "peer_agent_id": "peer_1",
                "run_id": "run_1",
                "thread_id": "thread_1",
                "session_id": "session_1",
                "context_id": "ctx_1",
                "message_id": "msg_1",
                "status": "completed",
                "idempotency_key": "a2a:tenant_1:ctx_1:msg_1",
                "input_payload": {"input": "plan"},
                "output_payload": {"answer": "done"},
                "created_at": "2026-06-03T00:00:00+00:00",
                "updated_at": "2026-06-04T00:00:00+00:00",
            },
        )
    )

    assert store.tasks == [
        A2ATaskMigrationRecord(
            id="task_1",
            tenant_id="tenant_1",
            peer_agent_id="peer_1",
            run_id="run_1",
            thread_id="thread_1",
            session_id="session_1",
            context_id="ctx_1",
            message_id="msg_1",
            status="completed",
            idempotency_key="a2a:tenant_1:ctx_1:msg_1",
            input_payload={"input": "plan"},
            output_payload={"answer": "done"},
            created_at=datetime(2026, 6, 3, tzinfo=UTC),
            updated_at=datetime(2026, 6, 4, tzinfo=UTC),
        )
    ]


async def test_a2a_task_event_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingA2AStore()
    writer = A2ATaskEventTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="a2a_task_events",
            source_pk="tenant_1:task_1:2:event_1",
            checksum="sha256:a",
            payload={
                "id": "event_1",
                "task_id": "task_1",
                "tenant_id": "tenant_1",
                "sequence": 2,
                "event_type": "task.completed",
                "payload": {"status": "completed"},
                "created_at": "2026-06-05T00:00:00+00:00",
            },
        )
    )

    assert store.events == [
        A2ATaskEventRecord(
            id="event_1",
            task_id="task_1",
            tenant_id="tenant_1",
            sequence=2,
            event_type="task.completed",
            payload={"status": "completed"},
            created_at=datetime(2026, 6, 5, tzinfo=UTC),
        )
    ]


async def test_a2a_push_subscription_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingA2AStore()
    writer = A2APushSubscriptionTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="a2a_push_subscriptions",
            source_pk="tenant_1:https://hooks.example.com/a2a:push_1",
            checksum="sha256:a",
            payload={
                "id": "push_1",
                "tenant_id": "tenant_1",
                "destination": "https://hooks.example.com/a2a",
                "signing_key_ref": "kms://a2a",
                "enabled": True,
                "created_at": "2026-06-06T00:00:00+00:00",
            },
        )
    )

    assert store.push_subscriptions == [
        A2APushSubscriptionRecord(
            id="push_1",
            tenant_id="tenant_1",
            destination="https://hooks.example.com/a2a",
            signing_key_ref="kms://a2a",
            enabled=True,
            created_at=datetime(2026, 6, 6, tzinfo=UTC),
        )
    ]


async def test_a2a_access_policy_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingA2AStore()
    writer = A2AAccessPolicyTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="a2a_access_policies",
            source_pk="tenant_1:peer_1:policy_1",
            checksum="sha256:a",
            payload={
                "id": "policy_1",
                "tenant_id": "tenant_1",
                "peer_agent_id": "peer_1",
                "allow_inbound": True,
                "allow_outbound": False,
                "allowed_skills": ["plan"],
                "created_at": "2026-06-07T00:00:00+00:00",
            },
        )
    )

    assert store.access_policies == [
        A2AAccessPolicyRecord(
            id="policy_1",
            tenant_id="tenant_1",
            peer_agent_id="peer_1",
            allow_inbound=True,
            allow_outbound=False,
            allowed_skills=["plan"],
            created_at=datetime(2026, 6, 7, tzinfo=UTC),
        )
    ]


async def test_rag_source_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingRagStore()
    writer = RagSourceTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="rag_sources",
            source_pk="tenant_1:faq:slack://C123/1700000000.000",
            checksum="sha256:a",
            payload={
                "id": "rag_src_1",
                "tenant_id": "tenant_1",
                "collection": "faq",
                "source_uri": "slack://C123/1700000000.000",
                "source_type": "slack-faq",
                "checksum": "sha256:source",
                "metadata": {"channel_id": "C123"},
                "created_at": "2026-06-01T00:00:00+00:00",
            },
        )
    )

    assert store.sources == [
        RagSourceMigrationRecord(
            id="rag_src_1",
            tenant_id="tenant_1",
            collection="faq",
            source_uri="slack://C123/1700000000.000",
            source_type="slack-faq",
            checksum="sha256:source",
            metadata={"channel_id": "C123"},
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
    ]


async def test_legacy_metric_tool_call_row_imports_to_metric_ingestion_buffer() -> None:
    buffer = RecordingMetricIngestionBuffer()
    writer = MetricToolCallTargetWriter(buffer)
    legacy_row = legacy_metric_tool_call_row(
        {
            "time": datetime(2026, 6, 1, 12, 30, tzinfo=UTC),
            "tenant_id": "tenant_1",
            "run_id": "run_1",
            "tool_name": "jira_search",
            "tool_source": "mcp",
            "mcp_server_name": "jira",
            "call_index": 2,
            "success": False,
            "duration_ms": 120,
            "error_class": "timeout",
            "error_message": "tool timed out",
        }
    )

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table=legacy_row.source_table,
            source_pk=legacy_row.source_pk,
            checksum="sha256:a",
            payload=legacy_row.payload,
        )
    )

    assert buffer.events == [legacy_row.payload]


async def test_legacy_metric_agent_execution_row_imports_to_metric_ingestion_buffer() -> None:
    buffer = RecordingMetricIngestionBuffer()
    writer = MetricAgentExecutionTargetWriter(buffer)
    legacy_row = legacy_metric_agent_execution_row(
        {
            "time": datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            "tenant_id": "tenant_1",
            "run_id": "run_1",
            "user_id": "user_1",
            "session_id": "session_1",
            "channel": "slack",
            "success": False,
            "error_code": "TOOL_TIMEOUT",
            "error_class": "timeout",
            "duration_ms": 1200,
            "llm_duration_ms": 700,
            "tool_duration_ms": 300,
            "guard_duration_ms": 100,
            "queue_wait_ms": 50,
            "is_streaming": True,
            "tool_count": 2,
            "persona_id": "persona_1",
            "prompt_template_id": "prompt_1",
            "intent_category": "engineering",
            "guard_rejected": True,
            "guard_stage": "InjectionDetection",
            "guard_category": "prompt_injection",
            "retry_count": 1,
            "fallback_used": True,
        }
    )

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table=legacy_row.source_table,
            source_pk=legacy_row.source_pk,
            checksum="sha256:a",
            payload=legacy_row.payload,
        )
    )

    assert buffer.events == [legacy_row.payload]


async def test_remaining_legacy_admin_metric_rows_import_to_metric_ingestion_buffer() -> None:
    cases = [
        (
            MetricSessionTargetWriter,
            legacy_metric_session_row(
                {
                    "time": datetime(2026, 6, 1, 13, 0, tzinfo=UTC),
                    "tenant_id": "tenant_1",
                    "session_id": "session_1",
                    "user_id": "user_1",
                    "channel": "slack",
                    "turn_count": 3,
                    "total_duration_ms": 5000,
                    "total_tokens": 2000,
                    "total_cost_usd": Decimal("0.01234567"),
                    "first_response_latency_ms": 850,
                    "outcome": "resolved",
                    "started_at": datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
                    "ended_at": datetime(2026, 6, 1, 12, 5, tzinfo=UTC),
                }
            ),
        ),
        (
            MetricSpanTargetWriter,
            legacy_metric_span_row(
                {
                    "time": datetime(2026, 6, 1, 13, 30, tzinfo=UTC),
                    "tenant_id": "tenant_1",
                    "trace_id": "trace_1",
                    "span_id": "span_1",
                    "operation_name": "graph.node",
                    "service_name": "reactor",
                    "duration_ms": 42,
                    "success": True,
                    "attributes": {"node": "tools"},
                }
            ),
        ),
        (
            MetricAuditTrailTargetWriter,
            legacy_metric_audit_trail_row(
                {
                    "time": datetime(2026, 6, 1, 14, 0, tzinfo=UTC),
                    "tenant_id": "tenant_1",
                    "event_type": "TENANT_UPDATED",
                    "resource_id": "tenant_1",
                    "detail": {"field": "quota"},
                }
            ),
        ),
        (
            MetricQuotaEventTargetWriter,
            legacy_metric_quota_event_row(
                {
                    "time": datetime(2026, 6, 1, 14, 30, tzinfo=UTC),
                    "tenant_id": "tenant_1",
                    "action": "blocked",
                    "current_usage": 110,
                    "quota_limit": 100,
                    "usage_percent": 110.0,
                }
            ),
        ),
        (
            MetricHitlEventTargetWriter,
            legacy_metric_hitl_event_row(
                {
                    "time": datetime(2026, 6, 1, 15, 0, tzinfo=UTC),
                    "tenant_id": "tenant_1",
                    "run_id": "run_1",
                    "tool_name": "deploy",
                    "approved": False,
                    "wait_ms": 12000,
                }
            ),
        ),
    ]

    for writer_type, legacy_row in cases:
        buffer = RecordingMetricIngestionBuffer()
        writer = writer_type(buffer)

        await writer.write(
            ImportedRow(
                batch_id="batch_1",
                source_table=legacy_row.source_table,
                source_pk=legacy_row.source_pk,
                checksum="sha256:a",
                payload=legacy_row.payload,
            )
        )

        assert buffer.events == [legacy_row.payload]


async def test_legacy_mcp_health_metric_row_imports_to_metric_ingestion_buffer() -> None:
    buffer = RecordingMetricIngestionBuffer()
    writer = MetricMcpHealthTargetWriter(buffer)
    legacy_row = legacy_mcp_health_metric_row(
        {
            "time": datetime(2026, 6, 1, 12, 45, tzinfo=UTC),
            "tenant_id": "tenant_1",
            "server_name": "jira",
            "status": "DISCONNECTED",
            "response_time_ms": 250,
            "error_class": "connect_timeout",
            "error_message": "server did not respond",
            "tool_count": 12,
        }
    )

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table=legacy_row.source_table,
            source_pk=legacy_row.source_pk,
            checksum="sha256:a",
            payload=legacy_row.payload,
        )
    )

    assert buffer.events == [legacy_row.payload]


async def test_legacy_eval_result_metric_row_imports_to_metric_ingestion_buffer() -> None:
    buffer = RecordingMetricIngestionBuffer()
    writer = MetricEvalResultTargetWriter(buffer)
    legacy_row = legacy_eval_result_metric_row(
        {
            "time": datetime(2026, 6, 1, 13, 0, tzinfo=UTC),
            "tenant_id": "tenant_1",
            "eval_run_id": "eval_run_1",
            "test_case_id": "case_1",
            "pass": False,
            "score": 0.42,
            "latency_ms": 850,
            "token_usage": 1234,
            "cost": Decimal("0.01234567"),
            "assertion_type": "contains",
            "failure_class": "missing_phrase",
            "failure_detail": "expected phrase was missing",
            "tags": "regression, safety",
        }
    )

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table=legacy_row.source_table,
            source_pk=legacy_row.source_pk,
            checksum="sha256:a",
            payload=legacy_row.payload,
        )
    )

    assert buffer.events == [legacy_row.payload]


async def test_rag_document_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingRagStore()
    writer = RagDocumentTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="rag_documents",
            source_pk="tenant_1:rag_src_1:v1",
            checksum="sha256:a",
            payload={
                "id": "rag_doc_1",
                "tenant_id": "tenant_1",
                "source_id": "rag_src_1",
                "collection": "faq",
                "title": "FAQ",
                "version": "v1",
                "acl": {"visibility": "tenant"},
                "metadata": {"lang": "ko"},
                "created_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert store.documents == [
        RagDocumentMigrationRecord(
            id="rag_doc_1",
            tenant_id="tenant_1",
            source_id="rag_src_1",
            collection="faq",
            title="FAQ",
            version="v1",
            acl={"visibility": "tenant"},
            metadata={"lang": "ko"},
            created_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_rag_chunk_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingRagStore()
    writer = RagChunkTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="rag_chunks",
            source_pk="tenant_1:rag_doc_1:0",
            checksum="sha256:a",
            payload={
                "id": "rag_chk_1",
                "tenant_id": "tenant_1",
                "document_id": "rag_doc_1",
                "collection": "faq",
                "chunk_index": 0,
                "content": "hello",
                "content_hash": "sha256:chunk",
                "embedding": [0.1, 0.2],
                "metadata": {"source_uri": "slack://C123"},
                "created_at": "2026-06-03T00:00:00+00:00",
            },
        )
    )

    assert store.chunks == [
        RagChunkMigrationRecord(
            id="rag_chk_1",
            tenant_id="tenant_1",
            document_id="rag_doc_1",
            collection="faq",
            chunk_index=0,
            content="hello",
            content_hash="sha256:chunk",
            embedding=[0.1, 0.2],
            metadata={"source_uri": "slack://C123"},
            created_at=datetime(2026, 6, 3, tzinfo=UTC),
        )
    ]


async def test_rag_chunk_target_writer_normalizes_legacy_acl_for_authorized_vector_search() -> None:
    store = RecordingRagStore()
    writer = RagChunkTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="rag_chunks",
            source_pk="tenant_1:rag_doc_1:0",
            checksum="sha256:a",
            payload={
                "id": "rag_chk_1",
                "tenant_id": "tenant_1",
                "document_id": "rag_doc_1",
                "collection": "faq",
                "chunk_index": 0,
                "content": "Executive salary bands",
                "content_hash": "sha256:chunk",
                "embedding": [0.1, 0.2],
                "metadata": {
                    "source_uri": "s3://docs/executive-salary.md",
                    "acl": {"visibility": "private", "groups": ["executive"]},
                },
                "created_at": "2026-06-03T00:00:00+00:00",
            },
        )
    )

    assert store.chunks[0].metadata == {
        "source_uri": "s3://docs/executive-salary.md",
        "acl": {"visibility": "private", "groups": ["executive"]},
        "acl_visibility": "private",
        "acl_users": [],
        "acl_groups": ["executive"],
        "acl_group_180b988a36f655a375c5eadb524e0364aa1acd22c07568c1789235ae54a5514a": "1",
    }


async def test_rag_ingestion_candidate_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingRagIngestionCandidateStore()
    writer = RagIngestionCandidateTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="rag_ingestion_candidates",
            source_pk="rag_candidate_1",
            checksum="sha256:a",
            payload={
                "id": "rag_candidate_1",
                "run_id": "run_1",
                "user_id": "user_1",
                "session_id": "session_1",
                "channel": "slack",
                "query": "How do I reset MFA?",
                "response": "Use the MFA reset workflow.",
                "status": "INGESTED",
                "captured_at": "2026-06-03T00:00:00+00:00",
                "reviewed_at": "2026-06-04T00:00:00+00:00",
                "reviewed_by": "admin_1",
                "review_comment": "Useful FAQ.",
                "ingested_document_id": "rag_doc_1",
            },
        )
    )

    assert store.records == [
        RagIngestionCandidate(
            id="rag_candidate_1",
            run_id="run_1",
            user_id="user_1",
            session_id="session_1",
            channel="slack",
            query="How do I reset MFA?",
            response="Use the MFA reset workflow.",
            status=RagIngestionCandidateStatus.INGESTED,
            captured_at=datetime(2026, 6, 3, tzinfo=UTC),
            reviewed_at=datetime(2026, 6, 4, tzinfo=UTC),
            reviewed_by="admin_1",
            review_comment="Useful FAQ.",
            ingested_document_id="rag_doc_1",
        )
    ]


async def test_memory_namespace_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingMemoryMigrationStore()
    writer = MemoryNamespaceTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="memory_namespaces",
            source_pk="tenant_1:user:user_1:semantic:user",
            checksum="sha256:a",
            payload={
                "id": "memory_namespace_1",
                "tenant_id": "tenant_1",
                "subject_type": "user",
                "subject_id": "user_1",
                "memory_type": "semantic",
                "visibility": "user",
                "created_at": "2026-06-01T00:00:00+00:00",
            },
        )
    )

    assert store.namespaces == [
        MemoryNamespaceMigrationRecord(
            id="memory_namespace_1",
            tenant_id="tenant_1",
            subject_type="user",
            subject_id="user_1",
            memory_type="semantic",
            visibility="user",
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
    ]


async def test_memory_item_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingMemoryMigrationStore()
    writer = MemoryItemTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="memory_items",
            source_pk="tenant_1:memory_namespace_1:memory_item_1",
            checksum="sha256:a",
            payload={
                "id": "memory_item_1",
                "namespace_id": "memory_namespace_1",
                "tenant_id": "tenant_1",
                "status": "active",
                "content": "prefers concise answers",
                "source_id": "run_1",
                "confidence": 0.91,
                "valid_from": "2026-06-01T00:00:00+00:00",
                "valid_until": "2026-07-01T00:00:00+00:00",
                "metadata": {"category": "preference"},
                "created_at": "2026-06-02T00:00:00+00:00",
            },
        )
    )

    assert store.items == [
        MemoryItemMigrationRecord(
            id="memory_item_1",
            namespace_id="memory_namespace_1",
            tenant_id="tenant_1",
            status="active",
            content="prefers concise answers",
            source_id="run_1",
            confidence=0.91,
            valid_from=datetime(2026, 6, 1, tzinfo=UTC),
            valid_until=datetime(2026, 7, 1, tzinfo=UTC),
            metadata={"category": "preference"},
            created_at=datetime(2026, 6, 2, tzinfo=UTC),
        )
    ]


async def test_memory_embedding_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingMemoryMigrationStore()
    writer = MemoryEmbeddingTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="memory_embeddings",
            source_pk="tenant_1:memory_item_1",
            checksum="sha256:a",
            payload={
                "memory_id": "memory_item_1",
                "tenant_id": "tenant_1",
                "embedding": [0.3, 0.4],
                "embedding_model": "text-embedding-3-small",
                "created_at": "2026-06-03T00:00:00+00:00",
            },
        )
    )

    assert store.embeddings == [
        MemoryEmbeddingRecord(
            memory_id="memory_item_1",
            tenant_id="tenant_1",
            embedding=[0.3, 0.4],
            embedding_model="text-embedding-3-small",
            created_at=datetime(2026, 6, 3, tzinfo=UTC),
        )
    ]


async def test_memory_proposal_target_writer_maps_imported_rows_to_records() -> None:
    store = RecordingMemoryMigrationStore()
    writer = MemoryProposalTargetWriter(store)

    await writer.write(
        ImportedRow(
            batch_id="batch_1",
            source_table="memory_proposals",
            source_pk="tenant_1:memory_namespace_1:memory_proposal_1",
            checksum="sha256:a",
            payload={
                "id": "memory_proposal_1",
                "tenant_id": "tenant_1",
                "namespace_id": "memory_namespace_1",
                "status": "proposed",
                "proposed_content": "likes structured specs",
                "extraction_model": "gpt-4.1",
                "extraction_prompt_version": "v2",
                "confidence": 0.88,
                "source_payload": {"run_id": "run_1"},
                "decision_reason": None,
                "created_at": "2026-06-04T00:00:00+00:00",
            },
        )
    )

    assert store.proposals == [
        MemoryProposalMigrationRecord(
            id="memory_proposal_1",
            tenant_id="tenant_1",
            namespace_id="memory_namespace_1",
            status="proposed",
            proposed_content="likes structured specs",
            extraction_model="gpt-4.1",
            extraction_prompt_version="v2",
            confidence=0.88,
            source_payload={"run_id": "run_1"},
            decision_reason=None,
            created_at=datetime(2026, 6, 4, tzinfo=UTC),
        )
    ]


async def test_generate_staging_parity_report_writes_json_summary() -> None:
    exported = StringIO(
        "\n".join(
            [
                (
                    '{"checksum":"sha256:bad","exported_at":"2026-06-27T12:00:00+00:00",'
                    '"payload":{"key":"a"},"record_type":"row","source_pk":"setting_1",'
                    '"source_table":"runtime_settings"}'
                ),
                (
                    '{"checksum":"sha256:skip","exported_at":"2026-06-27T12:00:00+00:00",'
                    '"reason":"not retained","record_type":"skipped","source_pk":"old",'
                    '"source_table":"legacy_only"}'
                ),
            ]
        )
    )
    imported = StringIO(
        '{"checksum":"sha256:bad","payload":{"key":"a"},"record_type":"row",'
        '"source_pk":"setting_1","source_table":"runtime_settings"}'
    )
    output = StringIO()

    exit_code = generate_staging_parity_report(
        exported_input=exported,
        imported_input=imported,
        output=output,
        sample_size=5,
    )

    assert exit_code == 0
    assert output.getvalue().strip() == (
        '{"ok":true,"tables":{"runtime_settings":{"checksum_mismatches":[],'
        '"exported_count":1,"extra_source_pks":[],"imported_count":1,'
        '"missing_source_pks":[],"ok":true,"sample_source_pks":["setting_1"]}}}'
    )


class RecordingImportSink:
    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()
        self.rows: list[ImportedRow] = []

    async def already_imported(self, *, source_table: str, source_pk: str, checksum: str) -> bool:
        del checksum
        return (source_table, source_pk) in self._seen

    async def import_row(self, row: ImportedRow) -> None:
        self._seen.add((row.source_table, row.source_pk))
        self.rows.append(row)


class StaticLegacySourceReader:
    def __init__(self, rows: list[LegacyRow | SkippedLegacyRow]) -> None:
        self._rows = rows

    async def read(self):
        for row in self._rows:
            yield row


class RecordingRuntimeSettingsStore:
    def __init__(self) -> None:
        self.updates: list[RuntimeSettingUpdate] = []

    async def set(self, update: RuntimeSettingUpdate):
        self.updates.append(update)
        return update


class RecordingPromptMigrationStore:
    def __init__(self) -> None:
        self.templates: list[PromptTemplateRecord] = []
        self.versions: list[PromptVersionRecord] = []
        self.releases: list[PromptReleaseRecord] = []

    async def save_template(self, record: PromptTemplateRecord) -> object:
        self.templates.append(record)
        return record

    async def save_version(self, record: PromptVersionRecord) -> object:
        self.versions.append(record)
        return record

    async def save_release(self, record: PromptReleaseRecord) -> object:
        self.releases.append(record)
        return record


class RecordingPersonaStore:
    def __init__(self) -> None:
        self.records: list[PersonaRecord] = []

    async def save(self, record: PersonaRecord) -> object:
        self.records.append(record)
        return record


class RecordingAgentSpecStore:
    def __init__(self) -> None:
        self.records: list[AgentSpecRecord] = []

    async def save(self, record: AgentSpecRecord) -> object:
        self.records.append(record)
        return record


class RecordingIntentDefinitionStore:
    def __init__(self) -> None:
        self.records: list[IntentDefinition] = []

    async def save(self, intent: IntentDefinition) -> object:
        self.records.append(intent)
        return intent


class RecordingPromptLabMigrationStore:
    def __init__(self) -> None:
        self.experiments: list[PromptLabExperimentRecord] = []
        self.trials: list[PromptLabTrialRecord] = []
        self.reports: list[PromptLabReportRecord] = []

    async def save_experiment(self, record: PromptLabExperimentRecord) -> object:
        self.experiments.append(record)
        return record

    async def save_trial(self, record: PromptLabTrialRecord) -> object:
        self.trials.append(record)
        return record

    async def save_report(self, record: PromptLabReportRecord) -> object:
        self.reports.append(record)
        return record


class RecordingRunMigrationStore:
    def __init__(self) -> None:
        self.runs: list[AgentRunMigrationRecord] = []
        self.events: list[AgentRunEventMigrationRecord] = []

    async def save_run(self, record: AgentRunMigrationRecord) -> object:
        self.runs.append(record)
        return record

    async def save_run_event(self, record: AgentRunEventMigrationRecord) -> object:
        self.events.append(record)
        return record


class RecordingDurableMigrationStore:
    def __init__(self) -> None:
        self.queues: list[RunQueueMigrationRecord] = []
        self.dead_letters: list[DeadLetterJobMigrationRecord] = []
        self.idempotency_records: list[IdempotencyMigrationRecord] = []
        self.outbox_events: list[OutboxEventMigrationRecord] = []
        self.inbox_events: list[InboxEventMigrationRecord] = []

    async def save_run_queue(self, record: RunQueueMigrationRecord) -> object:
        self.queues.append(record)
        return record

    async def save_dead_letter_job(self, record: DeadLetterJobMigrationRecord) -> object:
        self.dead_letters.append(record)
        return record

    async def save_idempotency_record(self, record: IdempotencyMigrationRecord) -> object:
        self.idempotency_records.append(record)
        return record

    async def save_outbox_event(self, record: OutboxEventMigrationRecord) -> object:
        self.outbox_events.append(record)
        return record

    async def save_inbox_event(self, record: InboxEventMigrationRecord) -> object:
        self.inbox_events.append(record)
        return record


class RecordingSlackBotStore:
    def __init__(self) -> None:
        self.records: list[SlackBotInstanceRecord] = []

    async def save(self, record: SlackBotInstanceRecord) -> object:
        self.records.append(record)
        return record


class RecordingProactiveChannelStore:
    def __init__(self) -> None:
        self.records: list[ProactiveChannelRecord] = []

    async def save(self, record: ProactiveChannelRecord) -> object:
        self.records.append(record)
        return record


class RecordingFaqRegistrationStore:
    def __init__(self) -> None:
        self.records: list[ChannelFaqRegistration] = []

    async def save(self, registration: ChannelFaqRegistration) -> object:
        self.records.append(registration)
        return registration


class RecordingFeedbackStore:
    def __init__(self) -> None:
        self.records: list[Feedback] = []

    async def save(self, feedback: Feedback) -> object:
        self.records.append(feedback)
        return feedback


class RecordingEvalCaseStore:
    def __init__(self) -> None:
        self.records: list[AgentEvalCaseRecord] = []

    async def save(self, record: AgentEvalCaseRecord) -> object:
        self.records.append(record)
        return record


class RecordingEvalResultStore:
    def __init__(self) -> None:
        self.records: list[AgentEvalStoredResultRecord] = []

    async def save(self, record: AgentEvalStoredResultRecord) -> object:
        self.records.append(record)
        return record


class RecordingSchedulerStore:
    def __init__(self) -> None:
        self.records: list[ScheduledJobRecord] = []

    async def save(self, job: ScheduledJobRecord) -> object:
        self.records.append(job)
        return job


class RecordingScheduledJobExecutionStore:
    def __init__(self) -> None:
        self.records: list[ScheduledJobExecutionRecord] = []

    async def save(self, execution: ScheduledJobExecutionRecord) -> object:
        self.records.append(execution)
        return execution


class RecordingScheduledJobDeadLetterStore:
    def __init__(self) -> None:
        self.records: list[ScheduledJobDeadLetterRecord] = []

    async def save(self, dead_letter: ScheduledJobDeadLetterRecord) -> object:
        self.records.append(dead_letter)
        return dead_letter


class RecordingModelPricingStore:
    def __init__(self) -> None:
        self.records: list[ModelPricing] = []

    async def save(self, pricing: ModelPricing) -> object:
        self.records.append(pricing)
        return pricing


class RecordingUsageLedgerStore:
    def __init__(self) -> None:
        self.records: list[UsageLedgerRecord] = []

    async def record(self, record: UsageLedgerRecord) -> object:
        self.records.append(record)
        return record


class RecordingTenantStore:
    def __init__(self, records: list[TenantRecord] | None = None) -> None:
        self.records: list[TenantRecord] = list(records or [])

    async def find_by_id(self, tenant_id: str) -> TenantRecord | None:
        for tenant in reversed(self.records):
            if tenant.id == tenant_id:
                return tenant
        return None

    async def save(self, tenant: TenantRecord) -> object:
        self.records.append(tenant)
        return tenant


class RecordingAlertStore:
    def __init__(self) -> None:
        self.rules: list[AlertRule] = []
        self.alerts: list[AlertInstance] = []

    async def save_rule(self, rule: AlertRule) -> object:
        self.rules.append(rule)
        return rule

    async def save_alert(self, alert: AlertInstance) -> object:
        self.alerts.append(alert)
        return alert


class RecordingUserStore:
    def __init__(self) -> None:
        self.records: list[UserRecord] = []

    async def save(self, user: UserRecord) -> object:
        self.records.append(user)
        return user


class RecordingUserIdentityStore:
    def __init__(self) -> None:
        self.records: list[UserIdentityRecord] = []

    async def upsert(
        self,
        *,
        tenant_id: str,
        provider: str,
        external_subject: str,
        user_id: str,
        metadata: dict[str, object] | None = None,
        identity_id: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> object:
        record = UserIdentityRecord(
            id=identity_id or "identity_generated",
            tenant_id=tenant_id,
            user_id=user_id,
            provider=provider,
            external_subject=external_subject,
            metadata=dict(metadata or {}),
            created_at=created_at or datetime(2026, 6, 1, tzinfo=UTC),
            updated_at=updated_at or datetime(2026, 6, 2, tzinfo=UTC),
        )
        self.records.append(record)
        return record


class RecordingTokenRevocationMigrationStore:
    def __init__(self) -> None:
        self.records: list[TokenRevocationRecord] = []

    async def save(self, revocation: TokenRevocationRecord) -> object:
        self.records.append(revocation)
        return revocation


class RecordingInputGuardRuleStore:
    def __init__(self) -> None:
        self.records: list[InputGuardRuleRecord] = []

    async def save(self, rule: InputGuardRuleRecord) -> object:
        self.records.append(rule)
        return rule


class RecordingInputGuardMetricStore:
    def __init__(self) -> None:
        self.records: list[InputGuardMetricMigrationRecord] = []

    async def save_metric(self, record: InputGuardMetricMigrationRecord) -> object:
        self.records.append(record)
        return record


class RecordingOutputGuardRuleStore:
    def __init__(self) -> None:
        self.records: list[OutputGuardRuleRecord] = []

    async def save(self, rule: OutputGuardRuleRecord) -> object:
        self.records.append(rule)
        return rule


class RecordingOutputGuardRuleAuditStore:
    def __init__(self) -> None:
        self.records: list[OutputGuardRuleAuditRecord] = []

    async def save(self, audit: OutputGuardRuleAuditRecord) -> object:
        self.records.append(audit)
        return audit


class RecordingAdminAuditStore:
    def __init__(self) -> None:
        self.records: list[tuple[str, AdminAuditLog]] = []

    async def save(self, log: AdminAuditLog, *, tenant_id: str) -> object:
        self.records.append((tenant_id, log))
        return log


class RecordingToolCatalogStore:
    def __init__(self) -> None:
        self.records: list[ToolCatalogRecord] = []

    async def save(self, record: ToolCatalogRecord) -> object:
        self.records.append(record)
        return record


class RecordingPendingApprovalStore:
    def __init__(self) -> None:
        self.records: list[PendingApprovalRecord] = []

    async def save(self, record: PendingApprovalRecord) -> object:
        self.records.append(record)
        return record


class RecordingToolInvocationStore:
    def __init__(self) -> None:
        self.records: list[ToolInvocationRecord] = []

    async def save(self, record: ToolInvocationRecord) -> object:
        self.records.append(record)
        return record


class RecordingMcpStore:
    def __init__(self) -> None:
        self.servers: list[McpServerMigrationRecord] = []
        self.statuses: list[McpServerStatusRecord] = []
        self.tool_snapshots: list[McpToolSnapshotRecord] = []
        self.access_policies: list[McpAccessPolicyRecord] = []

    async def save_server(self, record: McpServerMigrationRecord) -> object:
        self.servers.append(record)
        return record

    async def save_server_status(self, record: McpServerStatusRecord) -> object:
        self.statuses.append(record)
        return record

    async def save_tool_snapshot(self, record: McpToolSnapshotRecord) -> object:
        self.tool_snapshots.append(record)
        return record

    async def save_access_policy(self, record: McpAccessPolicyRecord) -> object:
        self.access_policies.append(record)
        return record


class RecordingA2AStore:
    def __init__(self) -> None:
        self.peers: list[A2APeerAgentRecord] = []
        self.agent_cards: list[A2AAgentCardRecord] = []
        self.tasks: list[A2ATaskMigrationRecord] = []
        self.events: list[A2ATaskEventRecord] = []
        self.push_subscriptions: list[A2APushSubscriptionRecord] = []
        self.access_policies: list[A2AAccessPolicyRecord] = []

    async def save_peer_agent(self, record: A2APeerAgentRecord) -> object:
        self.peers.append(record)
        return record

    async def save_agent_card(self, record: A2AAgentCardRecord) -> object:
        self.agent_cards.append(record)
        return record

    async def save_task(self, record: A2ATaskMigrationRecord) -> object:
        self.tasks.append(record)
        return record

    async def save_task_event(self, record: A2ATaskEventRecord) -> object:
        self.events.append(record)
        return record

    async def save_push_subscription(self, record: A2APushSubscriptionRecord) -> object:
        self.push_subscriptions.append(record)
        return record

    async def save_access_policy(self, record: A2AAccessPolicyRecord) -> object:
        self.access_policies.append(record)
        return record


class RecordingRagStore:
    def __init__(self) -> None:
        self.sources: list[RagSourceMigrationRecord] = []
        self.documents: list[RagDocumentMigrationRecord] = []
        self.chunks: list[RagChunkMigrationRecord] = []

    async def save_source(self, record: RagSourceMigrationRecord) -> object:
        self.sources.append(record)
        return record

    async def save_document(self, record: RagDocumentMigrationRecord) -> object:
        self.documents.append(record)
        return record

    async def save_chunk(self, record: RagChunkMigrationRecord) -> object:
        self.chunks.append(record)
        return record


class RecordingRagIngestionCandidateStore:
    def __init__(self) -> None:
        self.records: list[RagIngestionCandidate] = []

    async def save(self, record: RagIngestionCandidate) -> object:
        self.records.append(record)
        return record


class RecordingMetricIngestionBuffer:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def publish(self, event: dict[str, object]) -> bool:
        self.events.append(event)
        return True


class RecordingMemoryMigrationStore:
    def __init__(self) -> None:
        self.namespaces: list[MemoryNamespaceMigrationRecord] = []
        self.items: list[MemoryItemMigrationRecord] = []
        self.embeddings: list[MemoryEmbeddingRecord] = []
        self.proposals: list[MemoryProposalMigrationRecord] = []

    async def save_namespace(self, record: MemoryNamespaceMigrationRecord) -> object:
        self.namespaces.append(record)
        return record

    async def save_item(self, record: MemoryItemMigrationRecord) -> object:
        self.items.append(record)
        return record

    async def save_embedding(self, record: MemoryEmbeddingRecord) -> object:
        self.embeddings.append(record)
        return record

    async def save_proposal_record(self, record: MemoryProposalMigrationRecord) -> object:
        self.proposals.append(record)
        return record
