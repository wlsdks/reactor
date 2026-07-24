from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from reactor.mcp.security_policy import MCP_SECURITY_POLICY_SETTING_KEY
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
from reactor.persistence.migration_source_readers import (
    build_a2a_access_policy_source_query,
    build_a2a_agent_card_source_query,
    build_a2a_peer_agent_source_query,
    build_a2a_push_subscription_source_query,
    build_a2a_task_event_source_query,
    build_a2a_task_source_query,
    build_admin_audit_source_query,
    build_agent_run_event_source_query,
    build_agent_run_source_query,
    build_agent_spec_source_query,
    build_alert_instance_source_query,
    build_alert_rule_source_query,
    build_auth_token_revocation_source_query,
    build_auth_user_source_query,
    build_dead_letter_job_source_query,
    build_eval_case_source_query,
    build_eval_result_source_query,
    build_feedback_source_query,
    build_idempotency_record_source_query,
    build_inbox_event_source_query,
    build_input_guard_metric_source_query,
    build_input_guard_rule_source_query,
    build_intent_definition_source_query,
    build_mcp_access_policy_source_query,
    build_mcp_server_source_query,
    build_mcp_server_status_source_query,
    build_mcp_tool_snapshot_source_query,
    build_memory_embedding_source_query,
    build_memory_item_source_query,
    build_memory_namespace_source_query,
    build_memory_proposal_source_query,
    build_model_pricing_source_query,
    build_outbox_event_source_query,
    build_output_guard_rule_audit_source_query,
    build_output_guard_rule_source_query,
    build_pending_approval_source_query,
    build_persona_source_query,
    build_prompt_lab_experiment_source_query,
    build_prompt_lab_report_source_query,
    build_prompt_lab_trial_source_query,
    build_prompt_release_source_query,
    build_prompt_template_source_query,
    build_prompt_version_source_query,
    build_rag_chunk_source_query,
    build_rag_document_source_query,
    build_rag_ingestion_candidate_source_query,
    build_rag_source_source_query,
    build_run_queue_source_query,
    build_runtime_settings_source_query,
    build_scheduled_job_dead_letter_source_query,
    build_scheduled_job_execution_source_query,
    build_scheduled_job_source_query,
    build_slack_bot_source_query,
    build_slack_faq_registration_source_query,
    build_slack_proactive_channel_source_query,
    build_tenant_source_query,
    build_tool_catalog_source_query,
    build_tool_invocation_source_query,
    build_usage_ledger_source_query,
    build_user_identity_source_query,
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
from reactor.rag.ingestion_policy import RAG_INGESTION_POLICY_SETTING_KEY
from reactor.tools.policy import TOOL_POLICY_SETTING_KEY

BOT_TOKEN = "xoxb-secret"  # noqa: S105
APP_TOKEN = "xapp-secret"  # noqa: S105


def test_agent_run_source_query_orders_by_tenant_created_and_id() -> None:
    sql = str(build_agent_run_source_query().compile())

    assert "FROM agent_runs" in sql
    assert (
        "ORDER BY agent_runs.tenant_id ASC, agent_runs.created_at ASC, agent_runs.id ASC"
    ) in sql


def test_agent_run_legacy_row_preserves_full_payload() -> None:
    row = AgentRun(
        id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        thread_id="thread_1",
        checkpoint_ns="default",
        status="completed",
        input_text="hello",
        response_text="world",
        error_code=None,
        run_metadata={"model": "gpt-4.1", "usage": {"total_tokens": 42}},
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    assert agent_run_legacy_row(row) == LegacyRow(
        source_table="agent_runs",
        source_pk="tenant_1:run_1",
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


def test_agent_run_event_source_query_orders_by_run_sequence_and_id() -> None:
    sql = str(build_agent_run_event_source_query().compile())

    assert "FROM agent_run_events" in sql
    assert (
        "ORDER BY agent_run_events.tenant_id ASC, agent_run_events.run_id ASC, "
        "agent_run_events.sequence ASC, agent_run_events.id ASC"
    ) in sql


def test_agent_run_event_legacy_row_preserves_full_payload() -> None:
    row = AgentRunEvent(
        id=42,
        run_id="run_1",
        tenant_id="tenant_1",
        sequence=3,
        event_type="model.token",
        payload={"node": "model", "token": "hello", "trace_id": "trace_1"},
        created_at=datetime(2026, 6, 1, 0, 0, 3, tzinfo=UTC),
    )

    assert agent_run_event_legacy_row(row) == LegacyRow(
        source_table="agent_run_events",
        source_pk="tenant_1:run_1:3:42",
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


def test_legacy_conversation_message_rows_expand_to_synthetic_run_and_event() -> None:
    rows = legacy_conversation_message_rows(
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

    assert rows == [
        LegacyRow(
            source_table="agent_runs",
            source_pk="legacy_conversation:tenant_1:session_1",
            payload={
                "id": "legacy_conv_tenant_1_session_1",
                "tenant_id": "tenant_1",
                "user_id": "user_1",
                "thread_id": "session_1",
                "checkpoint_ns": "legacy-conversation",
                "status": "completed",
                "input_text": "Legacy conversation session session_1",
                "response_text": None,
                "error_code": None,
                "metadata": {
                    "source": "spring_conversation_messages",
                    "legacy_session_id": "session_1",
                },
                "created_at": "2026-01-01T12:00:00+00:00",
                "updated_at": "2026-01-01T12:00:00+00:00",
            },
        ),
        LegacyRow(
            source_table="agent_run_events",
            source_pk="legacy_conversation_message:tenant_1:session_1:7",
            payload={
                "id": None,
                "run_id": "legacy_conv_tenant_1_session_1",
                "tenant_id": "tenant_1",
                "sequence": 7,
                "event_type": "legacy.conversation.message",
                "payload": {
                    "role": "assistant",
                    "content": "The deployment summary is ready.",
                    "legacy_message_id": 7,
                    "legacy_session_id": "session_1",
                    "user_id": "user_1",
                    "timestamp_ms": 1_767_000_000_000,
                },
                "created_at": "2026-01-01T12:00:00+00:00",
            },
        ),
    ]


def test_legacy_conversation_summary_rows_expand_to_synthetic_summary_run_and_event() -> None:
    rows = legacy_conversation_summary_rows(
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

    assert rows == [
        LegacyRow(
            source_table="agent_runs",
            source_pk="legacy_conversation_summary:tenant_1:session_1",
            payload={
                "id": "legacy_conv_summary_tenant_1_session_1",
                "tenant_id": "tenant_1",
                "user_id": "anonymous",
                "thread_id": "session_1",
                "checkpoint_ns": "legacy-conversation-summary",
                "status": "completed",
                "input_text": "Legacy conversation summary session session_1",
                "response_text": "User asked about deployment status.",
                "error_code": None,
                "metadata": {
                    "source": "spring_conversation_summaries",
                    "legacy_session_id": "session_1",
                    "summarized_up_to": 7,
                },
                "created_at": "2026-01-01T12:00:00+00:00",
                "updated_at": "2026-01-01T12:05:00+00:00",
            },
        ),
        LegacyRow(
            source_table="agent_run_events",
            source_pk="legacy_conversation_summary:tenant_1:session_1:event",
            payload={
                "id": None,
                "run_id": "legacy_conv_summary_tenant_1_session_1",
                "tenant_id": "tenant_1",
                "sequence": 1,
                "event_type": "legacy.conversation.summary",
                "payload": {
                    "legacy_session_id": "session_1",
                    "narrative": "User asked about deployment status.",
                    "facts": [{"key": "service", "value": "api"}],
                    "summarized_up_to": 7,
                },
                "created_at": "2026-01-01T12:05:00+00:00",
            },
        ),
    ]


def test_run_queue_source_query_orders_by_tenant_status_available_priority_and_id() -> None:
    sql = str(build_run_queue_source_query().compile())

    assert "FROM run_queue" in sql
    assert (
        "ORDER BY run_queue.tenant_id ASC, run_queue.status ASC, "
        "run_queue.available_at ASC, run_queue.priority ASC, run_queue.id ASC"
    ) in sql


def test_run_queue_legacy_row_preserves_full_payload() -> None:
    row = RunQueue(
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

    assert run_queue_legacy_row(row) == LegacyRow(
        source_table="run_queue",
        source_pk="tenant_1:queue_1",
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


def test_dead_letter_job_source_query_orders_by_tenant_created_and_id() -> None:
    sql = str(build_dead_letter_job_source_query().compile())

    assert "FROM dead_letter_jobs" in sql
    assert (
        "ORDER BY dead_letter_jobs.tenant_id ASC, dead_letter_jobs.created_at ASC, "
        "dead_letter_jobs.id ASC"
    ) in sql


def test_dead_letter_job_legacy_row_preserves_full_payload() -> None:
    row = DeadLetterJob(
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

    assert dead_letter_job_legacy_row(row) == LegacyRow(
        source_table="dead_letter_jobs",
        source_pk="tenant_1:dead_1",
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


def test_idempotency_record_source_query_orders_by_tenant_scope_and_key() -> None:
    sql = str(build_idempotency_record_source_query().compile())

    assert "FROM idempotency_records" in sql
    assert (
        "ORDER BY idempotency_records.tenant_id ASC, idempotency_records.scope ASC, "
        "idempotency_records.key ASC"
    ) in sql


def test_idempotency_record_legacy_row_preserves_full_payload() -> None:
    row = IdempotencyRecord(
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

    assert idempotency_record_legacy_row(row) == LegacyRow(
        source_table="idempotency_records",
        source_pk="tenant_1:tool:tool:tenant_1:run_1:hash",
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


def test_outbox_event_source_query_orders_by_tenant_status_available_and_id() -> None:
    sql = str(build_outbox_event_source_query().compile())

    assert "FROM outbox_events" in sql
    assert (
        "ORDER BY outbox_events.tenant_id ASC, outbox_events.status ASC, "
        "outbox_events.available_at ASC, outbox_events.id ASC"
    ) in sql


def test_outbox_event_legacy_row_preserves_full_payload() -> None:
    row = OutboxEvent(
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

    assert outbox_event_legacy_row(row) == LegacyRow(
        source_table="outbox_events",
        source_pk="tenant_1:outbox_1",
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


def test_inbox_event_source_query_orders_by_tenant_source_received_and_id() -> None:
    sql = str(build_inbox_event_source_query().compile())

    assert "FROM inbox_events" in sql
    assert (
        "ORDER BY inbox_events.tenant_id ASC, inbox_events.source ASC, "
        "inbox_events.received_at ASC, inbox_events.id ASC"
    ) in sql


def test_inbox_event_legacy_row_preserves_full_payload() -> None:
    row = InboxEvent(
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

    assert inbox_event_legacy_row(row) == LegacyRow(
        source_table="inbox_events",
        source_pk="tenant_1:slack:Ev123",
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


def test_runtime_settings_source_query_orders_by_tenant_and_key() -> None:
    compiled = build_runtime_settings_source_query().compile()
    sql = str(compiled)

    assert "FROM runtime_settings" in sql
    assert "ORDER BY runtime_settings.tenant_id ASC, runtime_settings.key ASC" in sql


def test_runtime_setting_legacy_row_preserves_full_payload() -> None:
    row = RuntimeSetting(
        id="setting_1",
        tenant_id="tenant_1",
        key="feature.a2a.enabled",
        value="true",
        value_type="BOOLEAN",
        category="feature",
        description="A2A toggle",
        updated_by="admin_1",
        setting_metadata={"source": "legacy"},
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    legacy_row = runtime_setting_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="runtime_settings",
        source_pk="tenant_1:feature.a2a.enabled",
        payload={
            "tenant_id": "tenant_1",
            "key": "feature.a2a.enabled",
            "value": "true",
            "value_type": "BOOLEAN",
            "category": "feature",
            "description": "A2A toggle",
            "updated_by": "admin_1",
            "metadata": {"source": "legacy"},
            "created_at": "2026-06-01T00:00:00+00:00",
            "updated_at": "2026-06-02T00:00:00+00:00",
        },
    )


def test_legacy_tool_policy_row_maps_spring_singleton_to_runtime_setting() -> None:
    legacy_row = legacy_tool_policy_row(
        {
            "id": "default",
            "enabled": True,
            "write_tool_names": '["slack.post_message","jira.create_issue"]',
            "deny_write_channels": '["general","random"]',
            "allow_write_tool_names_in_deny_channels": '["jira.create_issue"]',
            "allow_write_tool_names_by_channel": '{"general":["slack.post_message"]}',
            "deny_write_message": "Writes require approval.",
            "created_at": datetime(2026, 6, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 6, 2, tzinfo=UTC),
        },
        tenant_id="tenant_1",
    )

    assert legacy_row.source_table == "runtime_settings"
    assert legacy_row.source_pk == f"tenant_1:{TOOL_POLICY_SETTING_KEY}"
    assert legacy_row.payload["tenant_id"] == "tenant_1"
    assert legacy_row.payload["key"] == TOOL_POLICY_SETTING_KEY
    assert legacy_row.payload["value_type"] == "JSON"
    assert legacy_row.payload["category"] == "tools"
    assert legacy_row.payload["updated_by"] == "migration"
    assert legacy_row.payload["metadata"] == {
        "source": "spring_tool_policy",
        "legacy_id": "default",
    }
    assert legacy_row.payload["value"] == (
        '{"allowWriteToolNamesByChannel":{"general":["slack.post_message"]},'
        '"allowWriteToolNamesInDenyChannels":["jira.create_issue"],'
        '"createdAt":"2026-06-01T00:00:00+00:00",'
        '"denyWriteChannels":["general","random"],'
        '"denyWriteMessage":"Writes require approval.",'
        '"enabled":true,'
        '"updatedAt":"2026-06-02T00:00:00+00:00",'
        '"writeToolNames":["jira.create_issue","slack.post_message"]}'
    )


def test_legacy_mcp_security_policy_row_maps_spring_singleton_to_global_setting() -> None:
    legacy_row = legacy_mcp_security_policy_row(
        {
            "id": "default",
            "allowed_server_names": '["github","slack"]',
            "max_tool_output_length": 120000,
            "created_at": datetime(2026, 6, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 6, 2, tzinfo=UTC),
        }
    )

    assert legacy_row == LegacyRow(
        source_table="runtime_settings",
        source_pk=f"global:{MCP_SECURITY_POLICY_SETTING_KEY}",
        payload={
            "tenant_id": "global",
            "key": MCP_SECURITY_POLICY_SETTING_KEY,
            "value": '{"allowedServerNames":["github","slack"],"maxToolOutputLength":120000}',
            "value_type": "JSON",
            "category": "mcp_security",
            "description": "Dynamic MCP server allowlist and tool output security policy.",
            "updated_by": "migration",
            "metadata": {
                "source": "spring_mcp_security_policy",
                "legacy_id": "default",
            },
            "created_at": "2026-06-01T00:00:00+00:00",
            "updated_at": "2026-06-02T00:00:00+00:00",
        },
    )


def test_legacy_rag_ingestion_policy_row_maps_spring_singleton_to_global_setting() -> None:
    legacy_row = legacy_rag_ingestion_policy_row(
        {
            "id": "default",
            "enabled": True,
            "require_review": False,
            "allowed_channels": '["help","engineering"]',
            "min_query_chars": 12,
            "min_response_chars": 40,
            "blocked_patterns": '["secret","password"]',
            "created_at": datetime(2026, 6, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 6, 2, tzinfo=UTC),
        }
    )

    assert legacy_row.source_table == "runtime_settings"
    assert legacy_row.source_pk == f"global:{RAG_INGESTION_POLICY_SETTING_KEY}"
    assert legacy_row.payload == {
        "tenant_id": "global",
        "key": RAG_INGESTION_POLICY_SETTING_KEY,
        "value": (
            '{"enabled": true, "requireReview": false, '
            '"allowedChannels": ["engineering", "help"], "minQueryChars": 12, '
            '"minResponseChars": 40, "blockedPatterns": ["password", "secret"], '
            '"createdAt": "2026-06-01T00:00:00+00:00", '
            '"updatedAt": "2026-06-02T00:00:00+00:00"}'
        ),
        "value_type": "JSON",
        "category": "rag",
        "description": "Dynamic RAG ingestion capture policy",
        "updated_by": "migration",
        "metadata": {
            "source": "spring_rag_ingestion_policy",
            "legacy_id": "default",
        },
        "created_at": "2026-06-01T00:00:00+00:00",
        "updated_at": "2026-06-02T00:00:00+00:00",
    }


def test_prompt_template_query_orders_by_tenant_name_and_id() -> None:
    sql = str(build_prompt_template_source_query().compile())

    assert "FROM prompt_templates" in sql
    assert (
        "ORDER BY prompt_templates.tenant_id ASC, prompt_templates.name ASC, "
        "prompt_templates.id ASC"
    ) in sql


def test_prompt_template_legacy_row_preserves_full_payload() -> None:
    row = PromptTemplate(
        id="prompt_template_1",
        tenant_id="tenant_1",
        name="support",
        graph_profile="rag",
        description="Support prompt",
        created_by="admin_1",
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    assert prompt_template_legacy_row(row) == LegacyRow(
        source_table="prompt_templates",
        source_pk="tenant_1:prompt_template_1",
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


def test_prompt_version_query_orders_by_template_version_and_id() -> None:
    sql = str(build_prompt_version_source_query().compile())

    assert "FROM prompt_versions" in sql
    assert (
        "ORDER BY prompt_versions.tenant_id ASC, prompt_versions.template_id ASC, "
        "prompt_versions.version ASC, prompt_versions.id ASC"
    ) in sql


def test_prompt_version_legacy_row_preserves_full_payload() -> None:
    row = PromptVersion(
        id="prompt_version_1",
        template_id="prompt_template_1",
        tenant_id="tenant_1",
        version="1",
        system_policy="Answer with citations.",
        developer_policy="Prefer RAG.",
        examples=["Q: hi"],
        prompt_metadata={"legacyStatus": "ACTIVE"},
        content_hash="sha256:abc",
        created_by="admin_1",
        created_at=datetime(2026, 6, 3, tzinfo=UTC),
    )

    assert prompt_version_legacy_row(row) == LegacyRow(
        source_table="prompt_versions",
        source_pk="tenant_1:prompt_template_1:prompt_version_1",
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


def test_prompt_release_query_orders_by_template_environment_and_id() -> None:
    sql = str(build_prompt_release_source_query().compile())

    assert "FROM prompt_releases" in sql
    assert (
        "ORDER BY prompt_releases.tenant_id ASC, prompt_releases.template_id ASC, "
        "prompt_releases.environment ASC, prompt_releases.id ASC"
    ) in sql


def test_prompt_release_legacy_row_preserves_full_payload() -> None:
    row = PromptRelease(
        id="prompt_release_1",
        tenant_id="tenant_1",
        template_id="prompt_template_1",
        version_id="prompt_version_1",
        environment="production",
        released_by="admin_1",
        released_at=datetime(2026, 6, 4, tzinfo=UTC),
        release_metadata={"ticket": "CUT-1"},
    )

    assert prompt_release_legacy_row(row) == LegacyRow(
        source_table="prompt_releases",
        source_pk="tenant_1:prompt_template_1:production",
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


def test_persona_query_orders_default_active_and_created() -> None:
    sql = str(build_persona_source_query().compile())

    assert "FROM personas" in sql
    assert (
        "ORDER BY personas.is_default DESC, personas.is_active DESC, "
        "personas.created_at ASC, personas.name ASC, personas.id ASC"
    ) in sql


def test_persona_legacy_row_preserves_full_payload() -> None:
    row = PersonaRow(
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

    assert persona_legacy_row(row) == LegacyRow(
        source_table="personas",
        source_pk="persona_1",
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


def test_agent_spec_query_orders_enabled_created_name_and_id() -> None:
    sql = str(build_agent_spec_source_query().compile())

    assert "FROM agent_specs" in sql
    assert (
        "ORDER BY agent_specs.enabled DESC, agent_specs.created_at ASC, "
        "agent_specs.name ASC, agent_specs.id ASC"
    ) in sql


def test_agent_spec_legacy_row_preserves_full_payload() -> None:
    row = AgentSpecRow(
        id="agent_spec_1",
        name="Support agent",
        description="Handles support requests",
        tool_names=["rag.search", "tickets.create"],
        keywords=["support", "ticket"],
        system_prompt="Resolve support cases.",
        mode="PLAN_EXECUTE",
        independent_execution=False,
        enabled=True,
        created_at=datetime(2026, 6, 5, tzinfo=UTC),
        updated_at=datetime(2026, 6, 6, tzinfo=UTC),
    )

    assert agent_spec_legacy_row(row) == LegacyRow(
        source_table="agent_specs",
        source_pk="agent_spec_1",
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


def test_intent_definition_query_orders_enabled_and_name() -> None:
    sql = str(build_intent_definition_source_query().compile())

    assert "FROM intent_definitions" in sql
    assert ("ORDER BY intent_definitions.enabled DESC, intent_definitions.name ASC") in sql


def test_intent_definition_legacy_row_preserves_full_payload() -> None:
    row = IntentDefinitionModel(
        name="support",
        description="Support request routing",
        examples=["I need help with billing"],
        keywords=["help", "billing"],
        profile="support",
        enabled=True,
        created_at=datetime(2026, 6, 5, tzinfo=UTC),
        updated_at=datetime(2026, 6, 6, tzinfo=UTC),
    )

    assert intent_definition_legacy_row(row) == LegacyRow(
        source_table="intent_definitions",
        source_pk="support",
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


def test_prompt_lab_experiment_query_orders_by_status_created_and_id() -> None:
    sql = str(build_prompt_lab_experiment_source_query().compile())

    assert "FROM prompt_lab_experiments" in sql
    assert (
        "ORDER BY prompt_lab_experiments.tenant_id ASC, "
        "prompt_lab_experiments.status ASC, prompt_lab_experiments.created_at ASC, "
        "prompt_lab_experiments.id ASC"
    ) in sql


def test_prompt_lab_experiment_legacy_row_preserves_full_payload() -> None:
    row = PromptLabExperiment(
        id="exp_1",
        tenant_id="tenant_1",
        name="Support prompt experiment",
        description="Measure support prompt variants",
        template_id="prompt_template_1",
        baseline_version_id="prompt_version_1",
        candidate_version_ids=["prompt_version_2"],
        test_queries=[
            {
                "query": "How do I reset MFA?",
                "expectedBehavior": "cite policy",
                "tags": ["mfa"],
            }
        ],
        evaluation_config={"rulesEnabled": True, "llmJudgeEnabled": False},
        model="openai:gpt-4.1-mini",
        judge_model=None,
        temperature=0.2,
        repetitions=2,
        auto_generated=True,
        status="COMPLETED",
        created_by="admin_1",
        created_at=datetime(2026, 6, 7, tzinfo=UTC),
        started_at=datetime(2026, 6, 7, 0, 1, tzinfo=UTC),
        completed_at=datetime(2026, 6, 7, 0, 2, tzinfo=UTC),
        error_message=None,
    )

    assert prompt_lab_experiment_legacy_row(row) == LegacyRow(
        source_table="prompt_lab_experiments",
        source_pk="tenant_1:exp_1",
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


def test_prompt_lab_trial_query_orders_by_experiment_executed_and_id() -> None:
    sql = str(build_prompt_lab_trial_source_query().compile())

    assert "FROM prompt_lab_trials" in sql
    assert (
        "ORDER BY prompt_lab_trials.tenant_id ASC, prompt_lab_trials.experiment_id ASC, "
        "prompt_lab_trials.executed_at ASC, prompt_lab_trials.id ASC"
    ) in sql


def test_prompt_lab_trial_legacy_row_preserves_full_payload() -> None:
    row = PromptLabTrial(
        id="trial_1",
        tenant_id="tenant_1",
        experiment_id="exp_1",
        prompt_version_id="prompt_version_2",
        prompt_version_number=2,
        test_query={"query": "How do I reset MFA?", "tags": ["mfa"]},
        repetition_index=1,
        response="Use the MFA reset policy.",
        success=True,
        error_message=None,
        tools_used=["rag.search"],
        token_usage={"promptTokens": 10, "completionTokens": 20, "totalTokens": 30},
        duration_ms=123,
        evaluations=[
            {
                "tier": "RULES",
                "passed": True,
                "score": 0.9,
                "reason": "Matched expected behavior.",
            }
        ],
        executed_at=datetime(2026, 6, 7, 0, 3, tzinfo=UTC),
    )

    assert prompt_lab_trial_legacy_row(row) == LegacyRow(
        source_table="prompt_lab_trials",
        source_pk="tenant_1:exp_1:trial_1",
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


def test_prompt_lab_report_query_orders_by_generated_and_experiment() -> None:
    sql = str(build_prompt_lab_report_source_query().compile())

    assert "FROM prompt_lab_reports" in sql
    assert (
        "ORDER BY prompt_lab_reports.tenant_id ASC, "
        "prompt_lab_reports.generated_at ASC, prompt_lab_reports.experiment_id ASC"
    ) in sql


def test_prompt_lab_report_legacy_row_preserves_full_payload() -> None:
    row = PromptLabReport(
        experiment_id="exp_1",
        tenant_id="tenant_1",
        experiment_name="Support prompt experiment",
        generated_at=datetime(2026, 6, 7, 0, 4, tzinfo=UTC),
        total_trials=1,
        version_summaries=[
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
        recommendation={
            "bestVersionId": "prompt_version_2",
            "bestVersionNumber": 2,
            "confidence": "HIGH",
            "reasoning": "Candidate passed all trials.",
            "improvements": ["Better grounding"],
            "warnings": [],
        },
    )

    assert prompt_lab_report_legacy_row(row) == LegacyRow(
        source_table="prompt_lab_reports",
        source_pk="tenant_1:exp_1",
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


def test_slack_bot_source_query_orders_by_tenant_name_and_id() -> None:
    compiled = build_slack_bot_source_query().compile()
    sql = str(compiled)

    assert "FROM slack_bot_instances" in sql
    assert (
        "ORDER BY slack_bot_instances.tenant_id ASC, "
        "slack_bot_instances.name ASC, slack_bot_instances.id ASC"
    ) in sql


def test_slack_bot_legacy_row_preserves_full_payload() -> None:
    row = SlackBotInstance(
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

    legacy_row = slack_bot_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="slack_bot_instances",
        source_pk="tenant_1:bot_1",
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


def test_legacy_slack_bot_instance_row_injects_tenant_for_old_spring_schema() -> None:
    legacy_row = legacy_slack_bot_instance_row(
        {
            "id": "bot_1",
            "name": "Support Bot",
            "bot_token": BOT_TOKEN,
            "app_token": APP_TOKEN,
            "persona_id": "support",
            "default_channel": "C123",
            "enabled": True,
            "created_at": datetime(2026, 6, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 6, 2, tzinfo=UTC),
        },
        tenant_id="tenant_1",
    )

    assert legacy_row == LegacyRow(
        source_table="slack_bot_instances",
        source_pk="tenant_1:bot_1",
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


def test_slack_proactive_channel_source_query_orders_by_tenant_and_channel() -> None:
    compiled = build_slack_proactive_channel_source_query().compile()
    sql = str(compiled)

    assert "FROM slack_proactive_channels" in sql
    assert (
        "ORDER BY slack_proactive_channels.tenant_id ASC, slack_proactive_channels.channel_id ASC"
    ) in sql


def test_proactive_channel_legacy_row_preserves_full_payload() -> None:
    row = SlackProactiveChannel(
        id="channel_row_1",
        tenant_id="tenant_1",
        channel_id="C123",
        channel_name="support",
        added_at=datetime(2026, 6, 1, tzinfo=UTC),
    )

    legacy_row = proactive_channel_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="slack_proactive_channels",
        source_pk="tenant_1:C123",
        payload={
            "tenant_id": "tenant_1",
            "channel_id": "C123",
            "channel_name": "support",
            "added_at": "2026-06-01T00:00:00+00:00",
        },
    )


def test_slack_faq_registration_source_query_orders_by_tenant_and_channel() -> None:
    compiled = build_slack_faq_registration_source_query().compile()
    sql = str(compiled)

    assert "FROM channel_faq_registrations" in sql
    assert (
        "ORDER BY channel_faq_registrations.tenant_id ASC, channel_faq_registrations.channel_id ASC"
    ) in sql


def test_faq_registration_legacy_row_preserves_full_payload() -> None:
    row = ChannelFaqRegistration(
        id="faq_reg_1",
        tenant_id="tenant_1",
        channel_id="C123",
        channel_name="support",
        enabled=True,
        auto_reply_mode="always",
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

    legacy_row = faq_registration_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="channel_faq_registrations",
        source_pk="tenant_1:C123",
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


def test_legacy_channel_faq_registration_row_injects_tenant_for_old_spring_schema() -> None:
    legacy_row = legacy_channel_faq_registration_row(
        {
            "channel_id": "C123",
            "channel_name": "support",
            "enabled": True,
            "auto_reply_mode": "always",
            "confidence_threshold": 0.82,
            "days_back": 45,
            "re_ingest_interval_hours": 12,
            "last_ingested_at": datetime(2026, 6, 3, tzinfo=UTC),
            "last_message_count": 120,
            "last_chunk_count": 44,
            "last_status": "OK",
            "last_error": None,
            "registered_by": "admin_1",
            "registered_at": datetime(2026, 6, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 6, 2, tzinfo=UTC),
        },
        tenant_id="tenant_1",
    )

    assert legacy_row == LegacyRow(
        source_table="channel_faq_registrations",
        source_pk="tenant_1:C123",
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
            "last_status": "OK",
            "last_error": None,
            "registered_by": "admin_1",
            "registered_at": "2026-06-01T00:00:00+00:00",
            "updated_at": "2026-06-02T00:00:00+00:00",
        },
    )


def test_feedback_source_query_orders_by_tenant_and_created() -> None:
    compiled = build_feedback_source_query().compile()
    sql = str(compiled)

    assert "FROM feedback" in sql
    assert "ORDER BY feedback.tenant_id ASC, feedback.created_at ASC, feedback.id ASC" in sql


def test_feedback_legacy_row_preserves_full_payload() -> None:
    row = FeedbackRecord(
        id="fb_1",
        tenant_id="tenant_1",
        query="How do I reset MFA?",
        response="Use the security portal.",
        rating="THUMBS_DOWN",
        source="slack_button",
        comment="Missing SSO path",
        session_id="session_1",
        run_id="run_1",
        user_id="user_1",
        review_status="done",
        review_tags=["sso", "docs"],
        reviewed_by="admin_1",
        reviewed_at=datetime(2026, 6, 3, tzinfo=UTC),
        review_note="Added to FAQ backlog",
        version=3,
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    legacy_row = feedback_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="feedback",
        source_pk="tenant_1:fb_1",
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


def test_legacy_feedback_row_injects_tenant_and_normalizes_text_lists() -> None:
    legacy_row = legacy_feedback_row(
        {
            "feedback_id": "fb_1",
            "query": "How do I reset MFA?",
            "response": "Use the security portal.",
            "rating": "THUMBS_DOWN",
            "timestamp": datetime(2026, 6, 1, tzinfo=UTC),
            "comment": "Missing SSO path",
            "session_id": "session_1",
            "run_id": "run_1",
            "user_id": "user_1",
            "intent": "support",
            "domain": "security",
            "model": "gpt-4.1",
            "prompt_version": 7,
            "tools_used": "rag.search, jira.lookup",
            "duration_ms": 1234,
            "tags": "mfa, sso",
        },
        tenant_id="tenant_1",
    )

    assert legacy_row == LegacyRow(
        source_table="feedback",
        source_pk="tenant_1:fb_1",
        payload={
            "feedback_id": "fb_1",
            "tenant_id": "tenant_1",
            "query": "How do I reset MFA?",
            "response": "Use the security portal.",
            "rating": "THUMBS_DOWN",
            "source": "legacy_feedback",
            "comment": "Missing SSO path",
            "session_id": "session_1",
            "run_id": "run_1",
            "user_id": "user_1",
            "intent": "support",
            "domain": "security",
            "model": "gpt-4.1",
            "prompt_version": 7,
            "tools_used": ["rag.search", "jira.lookup"],
            "duration_ms": 1234,
            "tags": ["mfa", "sso"],
            "review_status": "inbox",
            "review_tags": [],
            "reviewed_by": None,
            "reviewed_at": None,
            "review_note": None,
            "version": 1,
            "created_at": "2026-06-01T00:00:00+00:00",
            "updated_at": "2026-06-01T00:00:00+00:00",
        },
    )


def test_eval_case_source_query_orders_by_tenant_and_updated() -> None:
    compiled = build_eval_case_source_query().compile()
    sql = str(compiled)

    assert "FROM agent_eval_cases" in sql
    assert (
        "ORDER BY agent_eval_cases.tenant_id ASC, "
        "agent_eval_cases.updated_at ASC, agent_eval_cases.id ASC"
    ) in sql


def test_eval_case_legacy_row_preserves_full_payload() -> None:
    row = AgentEvalCase(
        id="case_1",
        tenant_id="tenant_1",
        name="MFA reset",
        user_input="How do I reset MFA?",
        expected_answer_contains=["security portal"],
        forbidden_answer_contains=["ask admin"],
        expected_tool_names=["search_docs"],
        forbidden_tool_names=["delete_user"],
        expected_exposed_tool_names=["search_docs"],
        forbidden_exposed_tool_names=["delete_user"],
        max_tool_exposure_count=3,
        agent_type="reactor",
        model="gpt-5",
        enabled=True,
        tags=["security", "faq"],
        min_score=0.8,
        source_run_id="run_1",
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    legacy_row = eval_case_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="agent_eval_cases",
        source_pk="tenant_1:case_1",
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


def test_eval_result_source_query_orders_by_tenant_case_and_evaluated() -> None:
    compiled = build_eval_result_source_query().compile()
    sql = str(compiled)

    assert "FROM agent_eval_results" in sql
    assert (
        "ORDER BY agent_eval_results.tenant_id ASC, "
        "agent_eval_results.case_id ASC, agent_eval_results.evaluated_at ASC, "
        "agent_eval_results.id ASC"
    ) in sql


def test_eval_result_legacy_row_preserves_full_payload() -> None:
    row = AgentEvalResult(
        id="result_1",
        tenant_id="tenant_1",
        case_id="case_1",
        run_id="run_1",
        tier="deterministic",
        passed=False,
        score=0.4,
        reasons=["missing expected phrase"],
        evaluated_at=datetime(2026, 6, 3, tzinfo=UTC),
    )

    legacy_row = eval_result_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="agent_eval_results",
        source_pk="tenant_1:result_1",
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


def test_scheduled_job_source_query_orders_by_tenant_and_created() -> None:
    compiled = build_scheduled_job_source_query().compile()
    sql = str(compiled)

    assert "FROM scheduled_jobs" in sql
    assert (
        "ORDER BY scheduled_jobs.tenant_id ASC, scheduled_jobs.created_at ASC, "
        "scheduled_jobs.id ASC"
    ) in sql


def test_scheduled_job_legacy_row_preserves_full_payload() -> None:
    row = ScheduledJob(
        id="job_1",
        tenant_id="tenant_1",
        name="Daily docs sync",
        description="Sync knowledge docs",
        cron_expression="0 9 * * *",
        timezone="Asia/Seoul",
        job_type="MCP_TOOL",
        mcp_server_name="docs",
        tool_name="sync_docs",
        tool_arguments={"space": "ENG"},
        agent_prompt=None,
        persona_id=None,
        agent_system_prompt=None,
        agent_model=None,
        agent_max_tool_calls=None,
        tags="docs,sync",
        slack_channel_id="C123",
        teams_webhook_url=None,
        retry_on_failure=True,
        max_retry_count=2,
        execution_timeout_ms=30000,
        enabled=True,
        last_run_at=datetime(2026, 6, 3, tzinfo=UTC),
        last_status="SUCCESS",
        last_result="ok",
        lease_owner="worker_1",
        lease_expires_at=datetime(2026, 6, 3, 1, tzinfo=UTC),
        fencing_token=7,
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    legacy_row = scheduled_job_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="scheduled_jobs",
        source_pk="tenant_1:job_1",
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
            "agent_prompt": None,
            "persona_id": None,
            "agent_system_prompt": None,
            "agent_model": None,
            "agent_max_tool_calls": None,
            "tags": ["docs", "sync"],
            "slack_channel_id": "C123",
            "teams_webhook_url": None,
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


def test_legacy_scheduled_job_row_injects_tenant_and_parses_tool_arguments() -> None:
    legacy_row = legacy_scheduled_job_row(
        {
            "id": "job_1",
            "name": "Daily docs sync",
            "description": "Sync knowledge docs",
            "cron_expression": "0 0 9 * * *",
            "timezone": "Asia/Seoul",
            "mcp_server_name": "docs",
            "tool_name": "sync_docs",
            "tool_arguments": '{"space":"ENG","limit":50}',
            "slack_channel_id": "C123",
            "retry_on_failure": True,
            "max_retry_count": 2,
            "execution_timeout_ms": 30000,
            "enabled": True,
            "last_run_at": datetime(2026, 6, 3, tzinfo=UTC),
            "last_status": "SUCCESS",
            "last_result": "ok",
            "created_at": datetime(2026, 6, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 6, 2, tzinfo=UTC),
        },
        tenant_id="tenant_1",
    )

    assert legacy_row == LegacyRow(
        source_table="scheduled_jobs",
        source_pk="tenant_1:job_1",
        payload={
            "id": "job_1",
            "tenant_id": "tenant_1",
            "name": "Daily docs sync",
            "description": "Sync knowledge docs",
            "cron_expression": "0 0 9 * * *",
            "timezone": "Asia/Seoul",
            "job_type": "MCP_TOOL",
            "mcp_server_name": "docs",
            "tool_name": "sync_docs",
            "tool_arguments": {"space": "ENG", "limit": 50},
            "agent_prompt": None,
            "persona_id": None,
            "agent_system_prompt": None,
            "agent_model": None,
            "agent_max_tool_calls": None,
            "tags": [],
            "slack_channel_id": "C123",
            "teams_webhook_url": None,
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


def test_scheduled_job_execution_source_query_orders_by_tenant_job_and_started() -> None:
    compiled = build_scheduled_job_execution_source_query().compile()
    sql = str(compiled)

    assert "FROM scheduled_job_executions" in sql
    assert (
        "ORDER BY scheduled_job_executions.tenant_id ASC, "
        "scheduled_job_executions.job_id ASC, scheduled_job_executions.started_at ASC, "
        "scheduled_job_executions.id ASC"
    ) in sql


def test_scheduled_job_execution_legacy_row_preserves_full_payload() -> None:
    row = ScheduledJobExecution(
        id="exec_1",
        tenant_id="tenant_1",
        job_id="job_1",
        job_name="Daily docs sync",
        job_type="MCP_TOOL",
        status="SUCCESS",
        result="ok",
        duration_ms=2500,
        dry_run=False,
        started_at=datetime(2026, 6, 3, tzinfo=UTC),
        completed_at=datetime(2026, 6, 3, 0, 0, 3, tzinfo=UTC),
    )

    legacy_row = scheduled_job_execution_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="scheduled_job_executions",
        source_pk="tenant_1:exec_1",
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


def test_legacy_scheduled_job_execution_row_injects_tenant_and_default_job_type() -> None:
    legacy_row = legacy_scheduled_job_execution_row(
        {
            "id": "exec_1",
            "job_id": "job_1",
            "job_name": "Daily docs sync",
            "status": "SUCCESS",
            "result": "ok",
            "duration_ms": 2500,
            "dry_run": False,
            "started_at": datetime(2026, 6, 3, tzinfo=UTC),
            "completed_at": datetime(2026, 6, 3, 0, 0, 3, tzinfo=UTC),
        },
        tenant_id="tenant_1",
    )

    assert legacy_row == LegacyRow(
        source_table="scheduled_job_executions",
        source_pk="tenant_1:exec_1",
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


def test_scheduled_job_dead_letter_source_query_orders_by_tenant_job_and_created() -> None:
    compiled = build_scheduled_job_dead_letter_source_query().compile()
    sql = str(compiled)

    assert "FROM scheduled_job_dead_letters" in sql
    assert (
        "ORDER BY scheduled_job_dead_letters.tenant_id ASC, "
        "scheduled_job_dead_letters.job_id ASC, scheduled_job_dead_letters.created_at ASC, "
        "scheduled_job_dead_letters.id ASC"
    ) in sql


def test_scheduled_job_dead_letter_legacy_row_preserves_full_payload() -> None:
    row = ScheduledJobDeadLetter(
        id="dead_1",
        tenant_id="tenant_1",
        job_id="job_1",
        job_name="Daily docs sync",
        job_type="MCP_TOOL",
        reason="timeout",
        result="Job failed: timeout",
        dry_run=True,
        created_at=datetime(2026, 6, 4, tzinfo=UTC),
    )

    legacy_row = scheduled_job_dead_letter_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="scheduled_job_dead_letters",
        source_pk="tenant_1:dead_1",
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


def test_model_pricing_source_query_orders_by_provider_model_and_effective_time() -> None:
    compiled = build_model_pricing_source_query().compile()
    sql = str(compiled)

    assert "FROM model_pricing" in sql
    assert (
        "ORDER BY model_pricing.provider ASC, model_pricing.model ASC, "
        "model_pricing.effective_from ASC, model_pricing.id ASC"
    ) in sql


def test_model_pricing_legacy_row_preserves_money_as_strings() -> None:
    row = ModelPricing(
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

    legacy_row = model_pricing_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="model_pricing",
        source_pk="openai:gpt-5-mini:pricing_1",
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


def test_legacy_v42_model_pricing_row_converts_per_1k_prices_to_per_1m() -> None:
    legacy_row = legacy_v42_model_pricing_row(
        {
            "id": "pricing_1",
            "provider": "openai",
            "model": "gpt-5-mini",
            "prompt_price_per_1k": Decimal("0.00125"),
            "completion_price_per_1k": Decimal("0.01000"),
            "cached_input_price_per_1k": Decimal("0.000125"),
            "reasoning_price_per_1k": Decimal("0.00200"),
            "batch_prompt_price_per_1k": Decimal("0.00050"),
            "batch_completion_price_per_1k": Decimal("0.00500"),
            "effective_from": datetime(2026, 6, 1, tzinfo=UTC),
            "effective_to": datetime(2026, 7, 1, tzinfo=UTC),
        }
    )

    assert legacy_row == LegacyRow(
        source_table="model_pricing",
        source_pk="openai:gpt-5-mini:pricing_1",
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


def test_usage_ledger_source_query_orders_by_tenant_run_and_occurred() -> None:
    compiled = build_usage_ledger_source_query().compile()
    sql = str(compiled)

    assert "FROM usage_ledger" in sql
    assert (
        "ORDER BY usage_ledger.tenant_id ASC, usage_ledger.run_id ASC, "
        "usage_ledger.occurred_at ASC, usage_ledger.id ASC"
    ) in sql


def test_usage_ledger_legacy_row_preserves_money_as_string() -> None:
    row = UsageLedger(
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

    legacy_row = usage_ledger_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="usage_ledger",
        source_pk="tenant_1:usage_1",
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


def test_legacy_metric_token_usage_row_maps_to_usage_ledger_payload() -> None:
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

    assert legacy_row == LegacyRow(
        source_table="usage_ledger",
        source_pk="tenant_1:usage_metric_tenant_1_run_1_20260601T133000_openai_gpt_5_mini_act",
        payload={
            "id": "usage_metric_tenant_1_run_1_20260601T133000_openai_gpt_5_mini_act",
            "tenant_id": "tenant_1",
            "run_id": "run_1",
            "provider": "openai",
            "model": "gpt-5-mini",
            "step_type": "act",
            "prompt_tokens": 100,
            "cached_tokens": 20,
            "completion_tokens": 30,
            "reasoning_tokens": 5,
            "total_tokens": 155,
            "estimated_cost_usd": "0.12345678",
            "occurred_at": "2026-06-01T13:30:00+00:00",
        },
    )


def test_legacy_metric_agent_execution_row_maps_to_compatibility_event_payload() -> None:
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

    assert legacy_row == LegacyRow(
        source_table="metric_agent_executions",
        source_pk="tenant_1:run_1:2026-06-01T12:00:00+00:00",
        payload={
            "type": "agent_execution",
            "recordedAt": "2026-06-01T12:00:00+00:00",
            "tenantId": "tenant_1",
            "runId": "run_1",
            "userId": "user_1",
            "sessionId": "session_1",
            "channel": "slack",
            "success": False,
            "errorCode": "TOOL_TIMEOUT",
            "errorClass": "timeout",
            "durationMs": 1200,
            "llmDurationMs": 700,
            "toolDurationMs": 300,
            "guardDurationMs": 100,
            "queueWaitMs": 50,
            "streaming": True,
            "toolCount": 2,
            "personaId": "persona_1",
            "promptTemplateId": "prompt_1",
            "intentCategory": "engineering",
            "guardRejected": True,
            "guardStage": "InjectionDetection",
            "guardCategory": "prompt_injection",
            "retryCount": 1,
            "fallbackUsed": True,
        },
    )


def test_legacy_metric_session_row_maps_to_compatibility_event_payload() -> None:
    legacy_row = legacy_metric_session_row(
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
    )

    assert legacy_row == LegacyRow(
        source_table="metric_sessions",
        source_pk="tenant_1:session_1:2026-06-01T13:00:00+00:00",
        payload={
            "type": "session",
            "recordedAt": "2026-06-01T13:00:00+00:00",
            "tenantId": "tenant_1",
            "sessionId": "session_1",
            "userId": "user_1",
            "channel": "slack",
            "turnCount": 3,
            "totalDurationMs": 5000,
            "totalTokens": 2000,
            "totalCostUsd": "0.01234567",
            "firstResponseLatencyMs": 850,
            "outcome": "resolved",
            "startedAt": "2026-06-01T12:00:00+00:00",
            "endedAt": "2026-06-01T12:05:00+00:00",
        },
    )


def test_legacy_metric_span_row_maps_to_compatibility_event_payload() -> None:
    legacy_row = legacy_metric_span_row(
        {
            "time": datetime(2026, 6, 1, 13, 30, tzinfo=UTC),
            "tenant_id": "tenant_1",
            "trace_id": "trace_1",
            "span_id": "span_1",
            "parent_span_id": "span_0",
            "run_id": "run_1",
            "operation_name": "graph.node",
            "service_name": "reactor",
            "duration_ms": 42,
            "success": False,
            "error_class": "timeout",
            "attributes": {"node": "tools"},
        }
    )

    assert legacy_row == LegacyRow(
        source_table="metric_spans",
        source_pk="tenant_1:trace_1:span_1",
        payload={
            "type": "span",
            "recordedAt": "2026-06-01T13:30:00+00:00",
            "tenantId": "tenant_1",
            "traceId": "trace_1",
            "spanId": "span_1",
            "parentSpanId": "span_0",
            "runId": "run_1",
            "operationName": "graph.node",
            "serviceName": "reactor",
            "durationMs": 42,
            "success": False,
            "errorClass": "timeout",
            "attributes": {"node": "tools"},
        },
    )


def test_legacy_metric_audit_trail_row_maps_to_compatibility_event_payload() -> None:
    legacy_row = legacy_metric_audit_trail_row(
        {
            "time": datetime(2026, 6, 1, 14, 0, tzinfo=UTC),
            "tenant_id": "tenant_1",
            "actor_id": "admin_1",
            "actor_email": "admin@example.com",
            "event_type": "TENANT_UPDATED",
            "resource_type": "tenant",
            "resource_id": "tenant_1",
            "detail": {"field": "quota"},
            "source_ip": "203.0.113.10",
        }
    )

    assert legacy_row == LegacyRow(
        source_table="metric_audit_trail",
        source_pk="tenant_1:TENANT_UPDATED:tenant_1:2026-06-01T14:00:00+00:00",
        payload={
            "type": "audit_trail",
            "recordedAt": "2026-06-01T14:00:00+00:00",
            "tenantId": "tenant_1",
            "actorId": "admin_1",
            "actorEmail": "admin@example.com",
            "eventType": "TENANT_UPDATED",
            "resourceType": "tenant",
            "resourceId": "tenant_1",
            "detail": {"field": "quota"},
            "sourceIp": "203.0.113.10",
        },
    )


def test_legacy_metric_quota_event_row_maps_to_compatibility_event_payload() -> None:
    legacy_row = legacy_metric_quota_event_row(
        {
            "time": datetime(2026, 6, 1, 14, 30, tzinfo=UTC),
            "tenant_id": "tenant_1",
            "action": "blocked",
            "current_usage": 110,
            "quota_limit": 100,
            "usage_percent": 110.0,
            "reason": "monthly request quota exceeded",
        }
    )

    assert legacy_row == LegacyRow(
        source_table="metric_quota_events",
        source_pk="tenant_1:blocked:2026-06-01T14:30:00+00:00",
        payload={
            "type": "quota_event",
            "recordedAt": "2026-06-01T14:30:00+00:00",
            "tenantId": "tenant_1",
            "action": "blocked",
            "currentUsage": 110,
            "quotaLimit": 100,
            "usagePercent": 110.0,
            "reason": "monthly request quota exceeded",
        },
    )


def test_legacy_metric_hitl_event_row_maps_to_compatibility_event_payload() -> None:
    legacy_row = legacy_metric_hitl_event_row(
        {
            "time": datetime(2026, 6, 1, 15, 0, tzinfo=UTC),
            "tenant_id": "tenant_1",
            "run_id": "run_1",
            "tool_name": "deploy",
            "approved": False,
            "wait_ms": 12000,
            "rejection_reason": "outside maintenance window",
        }
    )

    assert legacy_row == LegacyRow(
        source_table="metric_hitl_events",
        source_pk="tenant_1:run_1:deploy:2026-06-01T15:00:00+00:00",
        payload={
            "type": "hitl_event",
            "recordedAt": "2026-06-01T15:00:00+00:00",
            "tenantId": "tenant_1",
            "runId": "run_1",
            "toolName": "deploy",
            "approved": False,
            "waitMs": 12000,
            "rejectionReason": "outside maintenance window",
        },
    )


def test_legacy_metric_guard_event_row_preserves_guard_event_fields() -> None:
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

    assert legacy_row == LegacyRow(
        source_table="metric_guard_events",
        source_pk="tenant_1:user_1:InjectionDetection:2026-06-01T14:00:00+00:00",
        payload={
            "time": "2026-06-01T14:00:00+00:00",
            "tenant_id": "tenant_1",
            "user_id": "user_1",
            "channel": "slack",
            "stage": "InjectionDetection",
            "category": "prompt_injection",
            "reason_class": "jailbreak",
            "reason_detail": "ignore previous instructions",
            "is_output_guard": False,
            "action": "rejected",
        },
    )


def test_input_guard_metric_source_query_orders_by_time_and_id() -> None:
    sql = str(build_input_guard_metric_source_query().compile())

    assert "FROM metric_guard_events" in sql
    assert ("ORDER BY metric_guard_events.time ASC, metric_guard_events.id ASC") in sql


def test_input_guard_metric_legacy_row_preserves_guard_event_fields() -> None:
    row = MetricGuardEvent(
        id=7,
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

    assert input_guard_metric_legacy_row(row) == LegacyRow(
        source_table="metric_guard_events",
        source_pk="tenant_1:user_1:InjectionDetection:2026-06-01T14:00:00+00:00",
        payload={
            "time": "2026-06-01T14:00:00+00:00",
            "tenant_id": "tenant_1",
            "user_id": "user_1",
            "channel": "slack",
            "stage": "InjectionDetection",
            "category": "prompt_injection",
            "reason_class": "jailbreak",
            "reason_detail": "ignore previous instructions",
            "is_output_guard": False,
            "action": "rejected",
        },
    )


def test_legacy_metric_tool_call_row_maps_to_compatibility_event_payload() -> None:
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

    assert legacy_row == LegacyRow(
        source_table="metric_tool_calls",
        source_pk="tenant_1:run_1:2:jira_search",
        payload={
            "type": "tool_call",
            "recordedAt": "2026-06-01T12:30:00+00:00",
            "tenantId": "tenant_1",
            "runId": "run_1",
            "toolName": "jira_search",
            "toolSource": "mcp",
            "mcpServerName": "jira",
            "callIndex": 2,
            "success": False,
            "durationMs": 120,
            "errorClass": "timeout",
            "errorMessage": "tool timed out",
        },
    )


def test_legacy_mcp_health_metric_row_maps_to_compatibility_event_payload() -> None:
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

    assert legacy_row == LegacyRow(
        source_table="metric_mcp_health",
        source_pk="tenant_1:jira:2026-06-01T12:45:00+00:00",
        payload={
            "type": "mcp_health",
            "recordedAt": "2026-06-01T12:45:00+00:00",
            "tenantId": "tenant_1",
            "serverName": "jira",
            "status": "DISCONNECTED",
            "responseTimeMs": 250,
            "errorClass": "connect_timeout",
            "errorMessage": "server did not respond",
            "toolCount": 12,
        },
    )


def test_legacy_eval_result_metric_row_maps_to_compatibility_event_payload() -> None:
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

    assert legacy_row == LegacyRow(
        source_table="metric_eval_results",
        source_pk="tenant_1:eval_run_1:case_1:2026-06-01T13:00:00+00:00",
        payload={
            "type": "eval_result",
            "recordedAt": "2026-06-01T13:00:00+00:00",
            "tenantId": "tenant_1",
            "evalRunId": "eval_run_1",
            "testCaseId": "case_1",
            "pass": False,
            "score": 0.42,
            "latencyMs": 850,
            "tokenUsage": 1234,
            "cost": "0.01234567",
            "assertionType": "contains",
            "failureClass": "missing_phrase",
            "failureDetail": "expected phrase was missing",
            "tags": ["regression", "safety"],
        },
    )


def test_tenant_source_query_orders_by_created_time_and_id() -> None:
    compiled = build_tenant_source_query().compile()
    sql = str(compiled)

    assert "FROM tenants" in sql
    assert "ORDER BY tenants.created_at ASC, tenants.id ASC" in sql


def test_tenant_legacy_row_preserves_plan_quota_slo_and_metadata() -> None:
    row = Tenant(
        id="tenant_1",
        name="Acme",
        slug="acme",
        plan="BUSINESS",
        status="ACTIVE",
        max_requests_per_month=100_000,
        max_tokens_per_month=100_000_000,
        max_users=100,
        max_agents=50,
        max_mcp_servers=30,
        billing_cycle_start=5,
        billing_email="billing@example.com",
        slo_availability=0.999,
        slo_latency_p99_ms=5000,
        tenant_metadata={"tier": "paid"},
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    legacy_row = tenant_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="tenants",
        source_pk="tenant_1",
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


def test_legacy_slo_config_row_maps_to_tenant_slo_update() -> None:
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

    assert legacy_row == LegacyRow(
        source_table="tenant_slo_config",
        source_pk="tenant_1",
        payload={
            "tenant_id": "tenant_1",
            "slo_availability": 0.999,
            "slo_latency_p99_ms": 4500,
            "metadata": {
                "legacy_slo_config": {
                    "id": "slo_1",
                    "apdex_satisfied_ms": 1200,
                    "apdex_tolerating_ms": 5000,
                    "error_budget_window_days": 28,
                    "created_at": "2026-06-01T00:00:00+00:00",
                    "updated_at": "2026-06-02T00:00:00+00:00",
                }
            },
            "updated_at": "2026-06-02T00:00:00+00:00",
        },
    )


def test_alert_rule_source_query_orders_by_tenant_created_and_id() -> None:
    compiled = build_alert_rule_source_query().compile()
    sql = str(compiled)

    assert "FROM alert_rules" in sql
    assert (
        "ORDER BY alert_rules.tenant_id ASC NULLS FIRST, "
        "alert_rules.created_at ASC, alert_rules.id ASC"
    ) in sql


def test_alert_rule_legacy_row_preserves_full_payload() -> None:
    row = AlertRuleRow(
        id="rule_1",
        tenant_id="tenant_1",
        name="High error rate",
        description="API errors",
        type="STATIC_THRESHOLD",
        severity="CRITICAL",
        metric="error_rate",
        threshold=0.1,
        window_minutes=15,
        enabled=True,
        platform_only=False,
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
    )

    legacy_row = alert_rule_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="alert_rules",
        source_pk="tenant_1:rule_1",
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


def test_alert_instance_source_query_orders_by_rule_and_fired_time() -> None:
    compiled = build_alert_instance_source_query().compile()
    sql = str(compiled)

    assert "FROM alert_instances" in sql
    assert (
        "ORDER BY alert_instances.rule_id ASC, alert_instances.fired_at ASC, alert_instances.id ASC"
    ) in sql


def test_alert_instance_legacy_row_preserves_full_payload() -> None:
    row = AlertInstanceRow(
        id="alert_1",
        rule_id="rule_1",
        tenant_id="tenant_1",
        severity="CRITICAL",
        status="RESOLVED",
        message="error_rate exceeded threshold",
        metric_value=0.2,
        threshold=0.1,
        fired_at=datetime(2026, 6, 2, tzinfo=UTC),
        resolved_at=datetime(2026, 6, 3, tzinfo=UTC),
        acknowledged_by="admin_1",
    )

    legacy_row = alert_instance_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="alert_instances",
        source_pk="rule_1:alert_1",
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


def test_auth_user_source_query_orders_by_tenant_email_and_id() -> None:
    compiled = build_auth_user_source_query().compile()
    sql = str(compiled)

    assert "FROM users" in sql
    assert "ORDER BY users.tenant_id ASC, users.email ASC, users.id ASC" in sql


def test_auth_user_legacy_row_preserves_password_hash_and_role_payload() -> None:
    row = AuthUser(
        id="user_1",
        email="admin@example.com",
        name="Admin User",
        password_hash="$argon2id$v=19$hash",  # noqa: S106
        role="ADMIN",
        tenant_id="tenant_1",
        groups=["engineering", "finance"],
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    legacy_row = auth_user_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="users",
        source_pk="tenant_1:user_1",
        payload={
            "id": "user_1",
            "email": "admin@example.com",
            "name": "Admin User",
            "password_hash": "$argon2id$v=19$hash",
            "role": "ADMIN",
            "tenant_id": "tenant_1",
            "groups": ["engineering", "finance"],
            "created_at": "2026-06-01T00:00:00+00:00",
            "updated_at": "2026-06-02T00:00:00+00:00",
        },
    )


def test_legacy_user_row_defaults_missing_tenant_role_and_updated_at() -> None:
    legacy_row = legacy_user_row(
        {
            "id": "user_1",
            "email": "admin@example.com",
            "name": "Admin User",
            "password_hash": "$argon2id$v=19$hash",
            "created_at": datetime(2026, 6, 1, tzinfo=UTC),
        },
        default_tenant_id="tenant_1",
    )

    assert legacy_row == LegacyRow(
        source_table="users",
        source_pk="tenant_1:user_1",
        payload={
            "id": "user_1",
            "email": "admin@example.com",
            "name": "Admin User",
            "password_hash": "$argon2id$v=19$hash",
            "role": "USER",
            "tenant_id": "tenant_1",
            "created_at": "2026-06-01T00:00:00+00:00",
            "updated_at": "2026-06-01T00:00:00+00:00",
        },
    )


def test_user_identity_source_query_orders_by_tenant_provider_and_subject() -> None:
    compiled = build_user_identity_source_query().compile()
    sql = str(compiled)

    assert "FROM user_identities" in sql
    assert (
        "ORDER BY user_identities.tenant_id ASC, user_identities.provider ASC, "
        "user_identities.external_subject ASC, user_identities.id ASC"
    ) in sql


def test_user_identity_legacy_row_preserves_external_subject_payload() -> None:
    row = UserIdentity(
        id="identity_1",
        tenant_id="tenant_1",
        user_id="user_1",
        provider="jira",
        external_subject="acct-123",
        identity_metadata={"workspace": "ENG"},
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    legacy_row = user_identity_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="user_identities",
        source_pk="tenant_1:jira:acct-123",
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


def test_legacy_slack_user_identity_rows_expand_platform_columns_to_external_subjects() -> None:
    rows = legacy_slack_user_identity_rows(
        {
            "slack_user_id": "U123",
            "email": "employee@example.com",
            "display_name": "Employee One",
            "jira_account_id": "jira-account-123",
            "bitbucket_uuid": "{bitbucket-uuid}",
            "created_at": datetime(2026, 6, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 6, 2, tzinfo=UTC),
        },
        tenant_id="tenant_1",
        user_id="user_1",
    )

    assert rows == [
        LegacyRow(
            source_table="user_identities",
            source_pk="tenant_1:slack:U123",
            payload={
                "id": "user_identity_tenant_1_slack_U123",
                "tenant_id": "tenant_1",
                "user_id": "user_1",
                "provider": "slack",
                "external_subject": "U123",
                "metadata": {
                    "email": "employee@example.com",
                    "display_name": "Employee One",
                    "legacy_slack_user_id": "U123",
                },
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        ),
        LegacyRow(
            source_table="user_identities",
            source_pk="tenant_1:email:employee@example.com",
            payload={
                "id": "user_identity_tenant_1_email_employee_example_com",
                "tenant_id": "tenant_1",
                "user_id": "user_1",
                "provider": "email",
                "external_subject": "employee@example.com",
                "metadata": {
                    "display_name": "Employee One",
                    "legacy_slack_user_id": "U123",
                },
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        ),
        LegacyRow(
            source_table="user_identities",
            source_pk="tenant_1:jira:jira-account-123",
            payload={
                "id": "user_identity_tenant_1_jira_jira_account_123",
                "tenant_id": "tenant_1",
                "user_id": "user_1",
                "provider": "jira",
                "external_subject": "jira-account-123",
                "metadata": {
                    "email": "employee@example.com",
                    "display_name": "Employee One",
                    "legacy_slack_user_id": "U123",
                },
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        ),
        LegacyRow(
            source_table="user_identities",
            source_pk="tenant_1:bitbucket:{bitbucket-uuid}",
            payload={
                "id": "user_identity_tenant_1_bitbucket_bitbucket_uuid",
                "tenant_id": "tenant_1",
                "user_id": "user_1",
                "provider": "bitbucket",
                "external_subject": "{bitbucket-uuid}",
                "metadata": {
                    "email": "employee@example.com",
                    "display_name": "Employee One",
                    "legacy_slack_user_id": "U123",
                },
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-02T00:00:00+00:00",
            },
        ),
    ]


def test_auth_token_revocation_source_query_orders_by_expiry_and_token() -> None:
    compiled = build_auth_token_revocation_source_query().compile()
    sql = str(compiled)

    assert "FROM auth_token_revocations" in sql
    assert (
        "ORDER BY auth_token_revocations.expires_at ASC, auth_token_revocations.token_id ASC"
    ) in sql


def test_auth_token_revocation_legacy_row_preserves_full_payload() -> None:
    row = AuthTokenRevocation(
        token_id="jti_1",  # noqa: S106
        expires_at=datetime(2026, 6, 3, tzinfo=UTC),
        revoked_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    legacy_row = auth_token_revocation_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="auth_token_revocations",
        source_pk="jti_1",
        payload={
            "token_id": "jti_1",
            "expires_at": "2026-06-03T00:00:00+00:00",
            "revoked_at": "2026-06-02T00:00:00+00:00",
        },
    )


def test_input_guard_rule_source_query_orders_by_tenant_priority_and_created() -> None:
    compiled = build_input_guard_rule_source_query().compile()
    sql = str(compiled)

    assert "FROM input_guard_rules" in sql
    assert (
        "ORDER BY input_guard_rules.tenant_id ASC, input_guard_rules.priority DESC, "
        "input_guard_rules.created_at ASC, input_guard_rules.id ASC"
    ) in sql


def test_input_guard_rule_legacy_row_preserves_policy_payload() -> None:
    row = InputGuardRule(
        id="input_rule_1",
        tenant_id="tenant_1",
        name="Block jailbreak",
        pattern="ignore previous instructions",
        pattern_type="keyword",
        action="block",
        priority=900,
        category="prompt_injection",
        description="Legacy prompt injection rule",
        enabled=True,
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    legacy_row = input_guard_rule_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="input_guard_rules",
        source_pk="tenant_1:input_rule_1",
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


def test_output_guard_rule_source_query_orders_by_tenant_priority_and_created() -> None:
    compiled = build_output_guard_rule_source_query().compile()
    sql = str(compiled)

    assert "FROM output_guard_rules" in sql
    assert (
        "ORDER BY output_guard_rules.tenant_id ASC, output_guard_rules.priority ASC, "
        "output_guard_rules.created_at ASC, output_guard_rules.id ASC"
    ) in sql


def test_output_guard_rule_legacy_row_preserves_policy_payload() -> None:
    row = OutputGuardRule(
        id="output_rule_1",
        tenant_id="tenant_1",
        name="Mask API keys",
        pattern="sk-[A-Za-z0-9]+",
        action="MASK",
        replacement="[SECRET]",
        priority=10,
        enabled=True,
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    legacy_row = output_guard_rule_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="output_guard_rules",
        source_pk="tenant_1:output_rule_1",
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


def test_output_guard_rule_audit_source_query_orders_by_tenant_created_and_id() -> None:
    compiled = build_output_guard_rule_audit_source_query().compile()
    sql = str(compiled)

    assert "FROM output_guard_rule_audits" in sql
    assert (
        "ORDER BY output_guard_rule_audits.tenant_id ASC, "
        "output_guard_rule_audits.created_at ASC, output_guard_rule_audits.id ASC"
    ) in sql


def test_output_guard_rule_audit_legacy_row_preserves_full_payload() -> None:
    row = OutputGuardRuleAudit(
        id="audit_1",
        tenant_id="tenant_1",
        rule_id="output_rule_1",
        action="SIMULATE",
        actor="admin_1",
        detail="masked 2 values",
        created_at=datetime(2026, 6, 3, tzinfo=UTC),
    )

    legacy_row = output_guard_rule_audit_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="output_guard_rule_audits",
        source_pk="tenant_1:audit_1",
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


def test_admin_audit_source_query_orders_by_tenant_created_and_id() -> None:
    compiled = build_admin_audit_source_query().compile()
    sql = str(compiled)

    assert "FROM admin_audits" in sql
    assert (
        "ORDER BY admin_audits.tenant_id ASC, admin_audits.created_at ASC, admin_audits.id ASC"
    ) in sql


def test_admin_audit_legacy_row_preserves_full_payload() -> None:
    row = AdminAudit(
        id="audit_1",
        tenant_id="tenant_1",
        category="slack",
        action="ADD",
        actor="admin@example.com",
        resource_type="slack_channel",
        resource_id="C123",
        detail="added proactive channel",
        created_at=datetime(2026, 6, 4, tzinfo=UTC),
    )

    legacy_row = admin_audit_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="admin_audits",
        source_pk="tenant_1:audit_1",
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


def test_tool_catalog_source_query_orders_by_tenant_namespace_name_and_id() -> None:
    compiled = build_tool_catalog_source_query().compile()
    sql = str(compiled)

    assert "FROM tool_catalog" in sql
    assert (
        "ORDER BY tool_catalog.tenant_id ASC, tool_catalog.namespace ASC, "
        "tool_catalog.name ASC, tool_catalog.id ASC"
    ) in sql


def test_tool_catalog_legacy_row_preserves_full_payload() -> None:
    row = ToolCatalog(
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
        timeout_ms=15_000,
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    legacy_row = tool_catalog_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="tool_catalog",
        source_pk="tenant_1:builtin:send_webhook:tool_1",
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


def test_pending_approval_source_query_orders_by_tenant_created_and_id() -> None:
    compiled = build_pending_approval_source_query().compile()
    sql = str(compiled)

    assert "FROM pending_approvals" in sql
    assert (
        "ORDER BY pending_approvals.tenant_id ASC, pending_approvals.created_at ASC, "
        "pending_approvals.id ASC"
    ) in sql


def test_pending_approval_legacy_row_preserves_full_payload() -> None:
    row = PendingApproval(
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

    legacy_row = pending_approval_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="pending_approvals",
        source_pk="tenant_1:approval_1",
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


def test_tool_invocation_source_query_orders_by_tenant_run_started_and_id() -> None:
    compiled = build_tool_invocation_source_query().compile()
    sql = str(compiled)

    assert "FROM tool_invocations" in sql
    assert (
        "ORDER BY tool_invocations.tenant_id ASC, tool_invocations.run_id ASC, "
        "tool_invocations.started_at ASC, tool_invocations.id ASC"
    ) in sql


def test_tool_invocation_legacy_row_preserves_full_payload() -> None:
    row = ToolInvocation(
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

    legacy_row = tool_invocation_legacy_row(row)

    assert legacy_row == LegacyRow(
        source_table="tool_invocations",
        source_pk="tenant_1:invocation_1",
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


def test_mcp_server_source_query_orders_by_tenant_name_and_id() -> None:
    compiled = build_mcp_server_source_query().compile()
    sql = str(compiled)

    assert "FROM mcp_servers" in sql
    assert "ORDER BY mcp_servers.tenant_id ASC, mcp_servers.name ASC, mcp_servers.id ASC" in sql


def test_mcp_server_legacy_row_preserves_full_payload() -> None:
    row = McpServer(
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

    assert mcp_server_legacy_row(row) == LegacyRow(
        source_table="mcp_servers",
        source_pk="tenant_1:docs:mcp_1",
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


def test_mcp_server_status_source_query_orders_by_tenant_server_and_checked() -> None:
    compiled = build_mcp_server_status_source_query().compile()
    sql = str(compiled)

    assert "FROM mcp_server_status" in sql
    assert (
        "ORDER BY mcp_server_status.tenant_id ASC, mcp_server_status.server_id ASC, "
        "mcp_server_status.checked_at ASC"
    ) in sql


def test_mcp_server_status_legacy_row_preserves_full_payload() -> None:
    row = McpServerStatus(
        server_id="mcp_1",
        tenant_id="tenant_1",
        status="degraded",
        negotiated_protocol_version="2025-11-25",
        last_error="timeout",
        reconnect_attempt=2,
        backoff_until=datetime(2026, 6, 2, tzinfo=UTC),
        checked_at=datetime(2026, 6, 1, tzinfo=UTC),
    )

    assert mcp_server_status_legacy_row(row) == LegacyRow(
        source_table="mcp_server_status",
        source_pk="tenant_1:mcp_1",
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


def test_mcp_tool_snapshot_source_query_orders_by_tenant_server_tool_and_id() -> None:
    compiled = build_mcp_tool_snapshot_source_query().compile()
    sql = str(compiled)

    assert "FROM mcp_tool_snapshots" in sql
    assert (
        "ORDER BY mcp_tool_snapshots.tenant_id ASC, mcp_tool_snapshots.server_id ASC, "
        "mcp_tool_snapshots.tool_name ASC, mcp_tool_snapshots.id ASC"
    ) in sql


def test_mcp_tool_snapshot_legacy_row_preserves_full_payload() -> None:
    row = McpToolSnapshot(
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

    assert mcp_tool_snapshot_legacy_row(row) == LegacyRow(
        source_table="mcp_tool_snapshots",
        source_pk="tenant_1:mcp_1:search:snapshot_1",
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


def test_mcp_access_policy_source_query_orders_by_tenant_profile_server_and_id() -> None:
    compiled = build_mcp_access_policy_source_query().compile()
    sql = str(compiled)

    assert "FROM mcp_access_policies" in sql
    assert (
        "ORDER BY mcp_access_policies.tenant_id ASC, "
        "mcp_access_policies.graph_profile ASC, mcp_access_policies.server_id ASC, "
        "mcp_access_policies.id ASC"
    ) in sql


def test_mcp_access_policy_legacy_row_preserves_full_payload() -> None:
    row = McpAccessPolicy(
        id="policy_1",
        tenant_id="tenant_1",
        server_id="mcp_1",
        graph_profile="standard",
        allow_write=False,
        allowed_tools=["search"],
        created_at=datetime(2026, 6, 4, tzinfo=UTC),
    )

    assert mcp_access_policy_legacy_row(row) == LegacyRow(
        source_table="mcp_access_policies",
        source_pk="tenant_1:standard:mcp_1:policy_1",
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


def test_a2a_peer_agent_source_query_orders_by_tenant_name_and_id() -> None:
    sql = str(build_a2a_peer_agent_source_query().compile())

    assert "FROM a2a_peer_agents" in sql
    assert (
        "ORDER BY a2a_peer_agents.tenant_id ASC, a2a_peer_agents.name ASC, a2a_peer_agents.id ASC"
    ) in sql


def test_a2a_peer_agent_legacy_row_preserves_full_payload() -> None:
    row = A2APeerAgent(
        id="peer_1",
        tenant_id="tenant_1",
        name="planner",
        endpoint_url="https://a2a.example.com",
        agent_card={"name": "Planner"},
        enabled=True,
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    assert a2a_peer_agent_legacy_row(row) == LegacyRow(
        source_table="a2a_peer_agents",
        source_pk="tenant_1:planner:peer_1",
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


def test_a2a_agent_card_source_query_orders_by_tenant_version_and_id() -> None:
    sql = str(build_a2a_agent_card_source_query().compile())

    assert "FROM a2a_agent_cards" in sql
    assert (
        "ORDER BY a2a_agent_cards.tenant_id ASC, a2a_agent_cards.version ASC, "
        "a2a_agent_cards.id ASC"
    ) in sql


def test_a2a_agent_card_legacy_row_preserves_full_payload() -> None:
    row = A2AAgentCard(
        id="card_1",
        tenant_id="tenant_1",
        version="v1",
        protocol_version="1.0",
        card={"name": "Reactor"},
        active=True,
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
    )

    assert a2a_agent_card_legacy_row(row) == LegacyRow(
        source_table="a2a_agent_cards",
        source_pk="tenant_1:v1:card_1",
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


def test_a2a_task_source_query_orders_by_tenant_created_and_id() -> None:
    sql = str(build_a2a_task_source_query().compile())

    assert "FROM a2a_tasks" in sql
    assert "ORDER BY a2a_tasks.tenant_id ASC, a2a_tasks.created_at ASC, a2a_tasks.id ASC" in sql


def test_a2a_task_legacy_row_preserves_full_payload() -> None:
    row = A2ATask(
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

    assert a2a_task_legacy_row(row) == LegacyRow(
        source_table="a2a_tasks",
        source_pk="tenant_1:task_1",
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


def test_a2a_task_event_source_query_orders_by_tenant_task_sequence_and_id() -> None:
    sql = str(build_a2a_task_event_source_query().compile())

    assert "FROM a2a_task_events" in sql
    assert (
        "ORDER BY a2a_task_events.tenant_id ASC, a2a_task_events.task_id ASC, "
        "a2a_task_events.sequence ASC, a2a_task_events.id ASC"
    ) in sql


def test_a2a_task_event_legacy_row_preserves_full_payload() -> None:
    row = A2ATaskEvent(
        id="event_1",
        task_id="task_1",
        tenant_id="tenant_1",
        sequence=2,
        event_type="task.completed",
        payload={"status": "completed"},
        created_at=datetime(2026, 6, 5, tzinfo=UTC),
    )

    assert a2a_task_event_legacy_row(row) == LegacyRow(
        source_table="a2a_task_events",
        source_pk="tenant_1:task_1:2:event_1",
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


def test_a2a_push_subscription_source_query_orders_by_tenant_destination_and_id() -> None:
    sql = str(build_a2a_push_subscription_source_query().compile())

    assert "FROM a2a_push_subscriptions" in sql
    assert (
        "ORDER BY a2a_push_subscriptions.tenant_id ASC, "
        "a2a_push_subscriptions.destination ASC, a2a_push_subscriptions.id ASC"
    ) in sql


def test_a2a_push_subscription_legacy_row_preserves_full_payload() -> None:
    row = A2APushSubscription(
        id="push_1",
        tenant_id="tenant_1",
        destination="https://hooks.example.com/a2a",
        signing_key_ref="kms://a2a",
        enabled=True,
        created_at=datetime(2026, 6, 6, tzinfo=UTC),
    )

    assert a2a_push_subscription_legacy_row(row) == LegacyRow(
        source_table="a2a_push_subscriptions",
        source_pk="tenant_1:https://hooks.example.com/a2a:push_1",
        payload={
            "id": "push_1",
            "tenant_id": "tenant_1",
            "destination": "https://hooks.example.com/a2a",
            "signing_key_ref": "kms://a2a",
            "enabled": True,
            "created_at": "2026-06-06T00:00:00+00:00",
        },
    )


def test_a2a_access_policy_source_query_orders_by_tenant_peer_and_id() -> None:
    sql = str(build_a2a_access_policy_source_query().compile())

    assert "FROM a2a_access_policies" in sql
    assert (
        "ORDER BY a2a_access_policies.tenant_id ASC, "
        "a2a_access_policies.peer_agent_id ASC, a2a_access_policies.id ASC"
    ) in sql


def test_a2a_access_policy_legacy_row_preserves_full_payload() -> None:
    row = A2AAccessPolicy(
        id="policy_1",
        tenant_id="tenant_1",
        peer_agent_id="peer_1",
        allow_inbound=True,
        allow_outbound=False,
        allowed_skills=["plan"],
        created_at=datetime(2026, 6, 7, tzinfo=UTC),
    )

    assert a2a_access_policy_legacy_row(row) == LegacyRow(
        source_table="a2a_access_policies",
        source_pk="tenant_1:peer_1:policy_1",
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


def test_rag_source_query_orders_by_tenant_collection_and_uri() -> None:
    sql = str(build_rag_source_source_query().compile())

    assert "FROM rag_sources" in sql
    assert (
        "ORDER BY rag_sources.tenant_id ASC, rag_sources.collection ASC, rag_sources.source_uri ASC"
        in sql
    )


def test_rag_source_legacy_row_preserves_full_payload() -> None:
    row = RagSource(
        id="rag_src_1",
        tenant_id="tenant_1",
        collection="faq",
        source_uri="slack://C123/1700000000.000",
        source_type="slack-faq",
        checksum="sha256:source",
        source_metadata={"channel_id": "C123"},
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
    )

    assert rag_source_legacy_row(row) == LegacyRow(
        source_table="rag_sources",
        source_pk="tenant_1:faq:slack://C123/1700000000.000",
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


def test_rag_document_query_orders_by_tenant_collection_source_and_version() -> None:
    sql = str(build_rag_document_source_query().compile())

    assert "FROM rag_documents" in sql
    assert (
        "ORDER BY rag_documents.tenant_id ASC, rag_documents.collection ASC, "
        "rag_documents.source_id ASC, rag_documents.version ASC, rag_documents.id ASC"
    ) in sql


def test_rag_document_legacy_row_preserves_full_payload() -> None:
    row = RagDocument(
        id="rag_doc_1",
        tenant_id="tenant_1",
        source_id="rag_src_1",
        collection="faq",
        title="FAQ",
        version="v1",
        acl={"visibility": "tenant"},
        document_metadata={"lang": "ko"},
        created_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    assert rag_document_legacy_row(row) == LegacyRow(
        source_table="rag_documents",
        source_pk="tenant_1:rag_src_1:v1",
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


def test_rag_chunk_query_orders_by_tenant_collection_document_and_index() -> None:
    sql = str(build_rag_chunk_source_query().compile())

    assert "FROM rag_chunks" in sql
    assert (
        "ORDER BY rag_chunks.tenant_id ASC, rag_chunks.collection ASC, "
        "rag_chunks.document_id ASC, rag_chunks.chunk_index ASC, rag_chunks.id ASC"
    ) in sql


def test_rag_chunk_legacy_row_preserves_full_payload() -> None:
    row = RagChunk(
        id="rag_chk_1",
        tenant_id="tenant_1",
        document_id="rag_doc_1",
        collection="faq",
        chunk_index=0,
        content="hello",
        content_hash="sha256:chunk",
        embedding=[0.1, 0.2],
        chunk_metadata={"source_uri": "slack://C123"},
        created_at=datetime(2026, 6, 3, tzinfo=UTC),
    )

    assert rag_chunk_legacy_row(row) == LegacyRow(
        source_table="rag_chunks",
        source_pk="tenant_1:rag_doc_1:0",
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


def test_rag_ingestion_candidate_query_orders_by_status_captured_and_id() -> None:
    sql = str(build_rag_ingestion_candidate_source_query().compile())

    assert "FROM rag_ingestion_candidates" in sql
    assert (
        "ORDER BY rag_ingestion_candidates.status ASC, "
        "rag_ingestion_candidates.captured_at ASC, rag_ingestion_candidates.id ASC"
    ) in sql


def test_rag_ingestion_candidate_legacy_row_preserves_review_payload() -> None:
    row = RagIngestionCandidateRow(
        id="rag_candidate_1",
        run_id="run_1",
        user_id="user_1",
        session_id="session_1",
        channel="slack",
        query="How do I reset MFA?",
        response="Use the MFA reset workflow.",
        status="INGESTED",
        captured_at=datetime(2026, 6, 3, tzinfo=UTC),
        reviewed_at=datetime(2026, 6, 4, tzinfo=UTC),
        reviewed_by="admin_1",
        review_comment="Useful FAQ.",
        ingested_document_id="rag_doc_1",
    )

    assert rag_ingestion_candidate_legacy_row(row) == LegacyRow(
        source_table="rag_ingestion_candidates",
        source_pk="rag_candidate_1",
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


def test_memory_namespace_query_orders_by_identity() -> None:
    sql = str(build_memory_namespace_source_query().compile())

    assert "FROM memory_namespaces" in sql
    assert (
        "ORDER BY memory_namespaces.tenant_id ASC, memory_namespaces.subject_type ASC, "
        "memory_namespaces.subject_id ASC, memory_namespaces.memory_type ASC, "
        "memory_namespaces.visibility ASC, memory_namespaces.id ASC"
    ) in sql


def test_memory_namespace_legacy_row_preserves_full_payload() -> None:
    row = MemoryNamespace(
        id="memory_namespace_1",
        tenant_id="tenant_1",
        subject_type="user",
        subject_id="user_1",
        memory_type="semantic",
        visibility="user",
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
    )

    assert memory_namespace_legacy_row(row) == LegacyRow(
        source_table="memory_namespaces",
        source_pk="tenant_1:user:user_1:semantic:user",
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


def test_memory_item_query_orders_by_namespace_and_created_at() -> None:
    sql = str(build_memory_item_source_query().compile())

    assert "FROM memory_items" in sql
    assert (
        "ORDER BY memory_items.tenant_id ASC, memory_items.namespace_id ASC, "
        "memory_items.created_at ASC, memory_items.id ASC"
    ) in sql


def test_memory_item_legacy_row_preserves_full_payload() -> None:
    row = MemoryItem(
        id="memory_item_1",
        namespace_id="memory_namespace_1",
        tenant_id="tenant_1",
        status="active",
        content="prefers concise answers",
        source_id="run_1",
        confidence=0.91,
        valid_from=datetime(2026, 6, 1, tzinfo=UTC),
        valid_until=datetime(2026, 7, 1, tzinfo=UTC),
        item_metadata={"category": "preference"},
        created_at=datetime(2026, 6, 2, tzinfo=UTC),
    )

    assert memory_item_legacy_row(row) == LegacyRow(
        source_table="memory_items",
        source_pk="tenant_1:memory_namespace_1:memory_item_1",
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


def test_memory_embedding_query_orders_by_tenant_and_memory_id() -> None:
    sql = str(build_memory_embedding_source_query().compile())

    assert "FROM memory_embeddings" in sql
    assert "ORDER BY memory_embeddings.tenant_id ASC, memory_embeddings.memory_id ASC" in sql


def test_memory_embedding_legacy_row_preserves_full_payload() -> None:
    row = MemoryEmbedding(
        memory_id="memory_item_1",
        tenant_id="tenant_1",
        embedding=[0.3, 0.4],
        embedding_model="text-embedding-3-small",
        created_at=datetime(2026, 6, 3, tzinfo=UTC),
    )

    assert memory_embedding_legacy_row(row) == LegacyRow(
        source_table="memory_embeddings",
        source_pk="tenant_1:memory_item_1",
        payload={
            "memory_id": "memory_item_1",
            "tenant_id": "tenant_1",
            "embedding": [0.3, 0.4],
            "embedding_model": "text-embedding-3-small",
            "created_at": "2026-06-03T00:00:00+00:00",
        },
    )


def test_memory_proposal_query_orders_by_tenant_status_created_and_id() -> None:
    sql = str(build_memory_proposal_source_query().compile())

    assert "FROM memory_proposals" in sql
    assert (
        "ORDER BY memory_proposals.tenant_id ASC, memory_proposals.status ASC, "
        "memory_proposals.created_at ASC, memory_proposals.id ASC"
    ) in sql


def test_memory_proposal_legacy_row_preserves_full_payload() -> None:
    row = MemoryProposal(
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

    assert memory_proposal_legacy_row(row) == LegacyRow(
        source_table="memory_proposals",
        source_pk="tenant_1:memory_namespace_1:memory_proposal_1",
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
