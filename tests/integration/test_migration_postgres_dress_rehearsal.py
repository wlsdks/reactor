from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from docker.errors import DockerException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from reactor.core.container import AppContainer
from reactor.core.settings import get_settings
from reactor.migration.cutover import CutoverDressRehearsal
from reactor.migration.export import LegacyRow
from reactor.migration.rollback import RollbackSnapshotRow
from reactor.persistence.migration_store import (
    SqlAlchemyMigrationImportStore,
    SqlAlchemyRollbackSnapshotStore,
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
    MigrationImport,
    MigrationRollbackSnapshot,
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
    Tenant,
    ToolCatalog,
    ToolInvocation,
    UsageLedger,
    UserIdentity,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("REACTOR_TEST_POSTGRES") != "1",
    reason="set REACTOR_TEST_POSTGRES=1 to run Docker-backed migration dress rehearsal tests",
)


async def test_migration_dress_rehearsal_uses_postgres_import_ledger_and_snapshots() -> None:
    try:
        container = cast(Any, postgres_container())
    except DockerException as exc:
        pytest.skip(f"Docker daemon is unavailable for migration dress rehearsal test: {exc}")
    with container as postgres:
        sync_url = str(postgres.get_connection_url()).replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
        )
        migrate_postgres(sync_url)
        engine = create_async_engine(sync_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        import_store = SqlAlchemyMigrationImportStore(session_factory)
        rollback_store = SqlAlchemyRollbackSnapshotStore(session_factory)
        rollback_rows = [
            RollbackSnapshotRow(
                target_table="tenants",
                target_pk="tenant_1",
                payload={"id": "tenant_1", "name": "Legacy Tenant"},
            ),
            RollbackSnapshotRow(
                target_table="tenant_slo_config",
                target_pk="tenant_1",
                payload={"tenant_id": "tenant_1", "slo_availability": 0.995},
            ),
            RollbackSnapshotRow(
                target_table="runtime_settings",
                target_pk="tenant_1:agent.timeout",
                payload={"key": "agent.timeout", "value": "15"},
            ),
            RollbackSnapshotRow(
                target_table="slack_bot_instances",
                target_pk="tenant_1:bot_1",
                payload={"id": "bot_1", "name": "Old Support Bot"},
            ),
            RollbackSnapshotRow(
                target_table="rag_sources",
                target_pk="tenant_1:docs:https://docs.example/reactor",
                payload={"id": "rag_source_1", "checksum": "old"},
            ),
            RollbackSnapshotRow(
                target_table="rag_documents",
                target_pk="tenant_1:rag_source_1:v1",
                payload={"id": "rag_doc_1", "title": "Old Reactor Guide"},
            ),
            RollbackSnapshotRow(
                target_table="rag_chunks",
                target_pk="tenant_1:rag_doc_1:0",
                payload={"id": "rag_chunk_1", "content_hash": "old"},
            ),
            RollbackSnapshotRow(
                target_table="rag_ingestion_candidates",
                target_pk="rag_candidate_1",
                payload={"id": "rag_candidate_1", "status": "PENDING"},
            ),
            RollbackSnapshotRow(
                target_table="memory_namespaces",
                target_pk="tenant_1:user:user_1:semantic:user",
                payload={"id": "memory_namespace_1"},
            ),
            RollbackSnapshotRow(
                target_table="memory_items",
                target_pk="tenant_1:memory_namespace_1:memory_item_1",
                payload={"id": "memory_item_1", "status": "active"},
            ),
            RollbackSnapshotRow(
                target_table="memory_embeddings",
                target_pk="tenant_1:memory_item_1",
                payload={"memory_id": "memory_item_1", "embedding_model": "old"},
            ),
            RollbackSnapshotRow(
                target_table="memory_proposals",
                target_pk="tenant_1:memory_namespace_1:memory_proposal_1",
                payload={"id": "memory_proposal_1", "status": "proposed"},
            ),
            RollbackSnapshotRow(
                target_table="mcp_servers",
                target_pk="tenant_1:docs:mcp_1",
                payload={"id": "mcp_1", "status": "registered"},
            ),
            RollbackSnapshotRow(
                target_table="mcp_server_status",
                target_pk="tenant_1:mcp_1",
                payload={"server_id": "mcp_1", "status": "healthy"},
            ),
            RollbackSnapshotRow(
                target_table="mcp_tool_snapshots",
                target_pk="tenant_1:mcp_1:search:snapshot_1",
                payload={"id": "snapshot_1", "snapshot_hash": "old"},
            ),
            RollbackSnapshotRow(
                target_table="mcp_access_policies",
                target_pk="tenant_1:standard:mcp_1:policy_1",
                payload={"id": "policy_1", "allow_write": True},
            ),
            RollbackSnapshotRow(
                target_table="a2a_peer_agents",
                target_pk="tenant_1:planner:peer_1",
                payload={"id": "peer_1", "enabled": False},
            ),
            RollbackSnapshotRow(
                target_table="a2a_agent_cards",
                target_pk="tenant_1:v1:card_1",
                payload={"id": "card_1", "active": False},
            ),
            RollbackSnapshotRow(
                target_table="a2a_tasks",
                target_pk="tenant_1:task_1",
                payload={"id": "task_1", "status": "working"},
            ),
            RollbackSnapshotRow(
                target_table="a2a_task_events",
                target_pk="tenant_1:task_1:2:event_1",
                payload={"id": "event_1", "event_type": "task.working"},
            ),
            RollbackSnapshotRow(
                target_table="a2a_push_subscriptions",
                target_pk="tenant_1:https://hooks.example.com/a2a:push_1",
                payload={"id": "push_1", "enabled": False},
            ),
            RollbackSnapshotRow(
                target_table="a2a_access_policies",
                target_pk="tenant_1:peer_1:policy_1",
                payload={"id": "a2a_policy_1", "allow_outbound": True},
            ),
            RollbackSnapshotRow(
                target_table="prompt_templates",
                target_pk="tenant_1:prompt_template_1",
                payload={"id": "prompt_template_1", "name": "old-support"},
            ),
            RollbackSnapshotRow(
                target_table="prompt_versions",
                target_pk="tenant_1:prompt_template_1:prompt_version_1",
                payload={"id": "prompt_version_1", "content_hash": "old"},
            ),
            RollbackSnapshotRow(
                target_table="prompt_releases",
                target_pk="tenant_1:prompt_template_1:production",
                payload={"id": "prompt_release_1", "environment": "production"},
            ),
            RollbackSnapshotRow(
                target_table="prompt_lab_experiments",
                target_pk="tenant_1:exp_1",
                payload={"id": "exp_1", "status": "PENDING"},
            ),
            RollbackSnapshotRow(
                target_table="prompt_lab_trials",
                target_pk="tenant_1:exp_1:trial_1",
                payload={"id": "trial_1", "success": False},
            ),
            RollbackSnapshotRow(
                target_table="prompt_lab_reports",
                target_pk="tenant_1:exp_1",
                payload={"experiment_id": "exp_1", "total_trials": 0},
            ),
            RollbackSnapshotRow(
                target_table="personas",
                target_pk="persona_1",
                payload={"id": "persona_1", "name": "Old Support"},
            ),
            RollbackSnapshotRow(
                target_table="agent_specs",
                target_pk="agent_spec_1",
                payload={"id": "agent_spec_1", "name": "Old agent"},
            ),
            RollbackSnapshotRow(
                target_table="intent_definitions",
                target_pk="support",
                payload={"name": "support", "enabled": False},
            ),
            RollbackSnapshotRow(
                target_table="agent_runs",
                target_pk="tenant_1:run_1",
                payload={"id": "run_1", "status": "running"},
            ),
            RollbackSnapshotRow(
                target_table="agent_run_events",
                target_pk="tenant_1:run_1:3:42",
                payload={"id": 42, "event_type": "run.started"},
            ),
            RollbackSnapshotRow(
                target_table="run_queue",
                target_pk="tenant_1:queue_1",
                payload={"id": "queue_1", "status": "queued"},
            ),
            RollbackSnapshotRow(
                target_table="dead_letter_jobs",
                target_pk="tenant_1:dead_1",
                payload={"id": "dead_1", "reason": "old"},
            ),
            RollbackSnapshotRow(
                target_table="idempotency_records",
                target_pk="tenant_1:tool:tool:tenant_1:run_1:hash",
                payload={"key": "tool:tenant_1:run_1:hash", "status": "started"},
            ),
            RollbackSnapshotRow(
                target_table="outbox_events",
                target_pk="tenant_1:outbox_1",
                payload={"id": "outbox_1", "status": "pending"},
            ),
            RollbackSnapshotRow(
                target_table="inbox_events",
                target_pk="tenant_1:slack:Ev123",
                payload={"id": "inbox_1", "status": "received"},
            ),
            RollbackSnapshotRow(
                target_table="tool_catalog",
                target_pk="tenant_1:builtin:send_webhook:tool_1",
                payload={"id": "tool_1", "enabled": False},
            ),
            RollbackSnapshotRow(
                target_table="pending_approvals",
                target_pk="tenant_1:approval_1",
                payload={"id": "approval_1", "status": "pending"},
            ),
            RollbackSnapshotRow(
                target_table="tool_invocations",
                target_pk="tenant_1:invocation_1",
                payload={"id": "invocation_1", "status": "started"},
            ),
            RollbackSnapshotRow(
                target_table="feedback",
                target_pk="tenant_1:fb_1",
                payload={"feedback_id": "fb_1", "review_status": "inbox"},
            ),
            RollbackSnapshotRow(
                target_table="agent_eval_cases",
                target_pk="tenant_1:case_1",
                payload={"id": "case_1", "enabled": False},
            ),
            RollbackSnapshotRow(
                target_table="agent_eval_results",
                target_pk="tenant_1:result_1",
                payload={"id": "result_1", "passed": True},
            ),
            RollbackSnapshotRow(
                target_table="scheduled_jobs",
                target_pk="tenant_1:job_1",
                payload={"id": "job_1", "enabled": False},
            ),
            RollbackSnapshotRow(
                target_table="scheduled_job_executions",
                target_pk="tenant_1:exec_1",
                payload={"id": "exec_1", "status": "FAILED"},
            ),
            RollbackSnapshotRow(
                target_table="scheduled_job_dead_letters",
                target_pk="tenant_1:scheduled_dead_1",
                payload={"id": "scheduled_dead_1", "reason": "old"},
            ),
            RollbackSnapshotRow(
                target_table="model_pricing",
                target_pk="openai:gpt-5-mini:pricing_1",
                payload={"id": "pricing_1", "model": "old"},
            ),
            RollbackSnapshotRow(
                target_table="metric_agent_executions",
                target_pk="tenant_1:run_1:2026-06-01T12:00:00+00:00",
                payload={"run_id": "run_1", "success": True},
            ),
            RollbackSnapshotRow(
                target_table="metric_sessions",
                target_pk="tenant_1:session_1:2026-06-01T13:00:00+00:00",
                payload={"session_id": "session_1", "outcome": "old"},
            ),
            RollbackSnapshotRow(
                target_table="metric_spans",
                target_pk="tenant_1:trace_1:span_1",
                payload={"span_id": "span_1", "success": False},
            ),
            RollbackSnapshotRow(
                target_table="metric_audit_trail",
                target_pk="tenant_1:TENANT_UPDATED:tenant_1:2026-06-01T14:00:00+00:00",
                payload={"resource_id": "tenant_1", "detail": {"old": True}},
            ),
            RollbackSnapshotRow(
                target_table="metric_quota_events",
                target_pk="tenant_1:blocked:2026-06-01T14:30:00+00:00",
                payload={"action": "blocked", "current_usage": 100},
            ),
            RollbackSnapshotRow(
                target_table="metric_hitl_events",
                target_pk="tenant_1:run_1:deploy:2026-06-01T15:00:00+00:00",
                payload={"tool_name": "deploy", "approved": True},
            ),
            RollbackSnapshotRow(
                target_table="metric_tool_calls",
                target_pk="tenant_1:run_1:jira_search:2",
                payload={"tool_name": "jira_search", "success": True},
            ),
            RollbackSnapshotRow(
                target_table="metric_mcp_health",
                target_pk="tenant_1:jira:2026-06-01T12:45:00+00:00",
                payload={"server_name": "jira", "status": "CONNECTED"},
            ),
            RollbackSnapshotRow(
                target_table="metric_eval_results",
                target_pk="tenant_1:eval_run_1:case_1",
                payload={"eval_run_id": "eval_run_1", "pass": True},
            ),
            RollbackSnapshotRow(
                target_table="usage_ledger",
                target_pk="tenant_1:usage_1",
                payload={"id": "usage_1", "total_tokens": 0},
            ),
            RollbackSnapshotRow(
                target_table="alert_rules",
                target_pk="tenant_1:rule_1",
                payload={"id": "rule_1", "enabled": False},
            ),
            RollbackSnapshotRow(
                target_table="alert_instances",
                target_pk="rule_1:alert_1",
                payload={"id": "alert_1", "status": "ACTIVE"},
            ),
            RollbackSnapshotRow(
                target_table="users",
                target_pk="tenant_1:user_1",
                payload={"id": "user_1", "email": "old-admin@example.com"},
            ),
            RollbackSnapshotRow(
                target_table="user_identities",
                target_pk="tenant_1:jira:acct-123",
                payload={"id": "identity_1", "external_subject": "old-acct"},
            ),
            RollbackSnapshotRow(
                target_table="auth_token_revocations",
                target_pk="jti_1",
                payload={"token_id": "jti_1"},
            ),
            RollbackSnapshotRow(
                target_table="input_guard_rules",
                target_pk="tenant_1:input_rule_1",
                payload={"id": "input_rule_1", "enabled": False},
            ),
            RollbackSnapshotRow(
                target_table="output_guard_rules",
                target_pk="tenant_1:output_rule_1",
                payload={"id": "output_rule_1", "enabled": False},
            ),
            RollbackSnapshotRow(
                target_table="output_guard_rule_audits",
                target_pk="tenant_1:output_audit_1",
                payload={"id": "output_audit_1", "action": "CREATE"},
            ),
            RollbackSnapshotRow(
                target_table="admin_audits",
                target_pk="tenant_1:admin_audit_1",
                payload={"id": "admin_audit_1", "category": "old"},
            ),
        ]
        legacy_rows = [
            LegacyRow(
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
            ),
            LegacyRow(
                source_table="tenant_slo_config",
                source_pk="tenant_1",
                payload={
                    "tenant_id": "tenant_1",
                    "slo_availability": 0.9995,
                    "slo_latency_p99_ms": 4500,
                    "metadata": {"legacy_slo_config": {"error_budget_window_days": 28}},
                    "updated_at": "2026-06-04T00:00:00+00:00",
                },
            ),
            LegacyRow(
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
                },
            ),
            LegacyRow(
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
            ),
            LegacyRow(
                source_table="auth_token_revocations",
                source_pk="jti_1",
                payload={
                    "token_id": "jti_1",
                    "expires_at": "2026-06-03T00:00:00+00:00",
                    "revoked_at": "2026-06-02T00:00:00+00:00",
                },
            ),
            LegacyRow(
                source_table="runtime_settings",
                source_pk="tenant_1:agent.timeout",
                payload={
                    "tenant_id": "tenant_1",
                    "key": "agent.timeout",
                    "value": "30",
                    "value_type": "INT",
                    "category": "agent",
                    "description": "Agent timeout seconds",
                    "updated_by": "migration",
                    "metadata": {"source": "legacy"},
                },
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
                source_table="output_guard_rule_audits",
                source_pk="tenant_1:output_audit_1",
                payload={
                    "id": "output_audit_1",
                    "tenant_id": "tenant_1",
                    "rule_id": "output_rule_1",
                    "action": "SIMULATE",
                    "actor": "admin_1",
                    "detail": "masked 2 values",
                    "created_at": "2026-06-03T00:00:00+00:00",
                },
            ),
            LegacyRow(
                source_table="admin_audits",
                source_pk="tenant_1:admin_audit_1",
                payload={
                    "id": "admin_audit_1",
                    "tenant_id": "tenant_1",
                    "category": "slack",
                    "action": "ADD",
                    "actor": "admin@example.com",
                    "resource_type": "slack_channel",
                    "resource_id": "C123",
                    "detail": "added proactive channel",
                    "created_at": "2026-06-04T00:00:00+00:00",
                },
            ),
            LegacyRow(
                source_table="slack_bot_instances",
                source_pk="tenant_1:bot_1",
                payload={
                    "id": "bot_1",
                    "tenant_id": "tenant_1",
                    "name": "Support Bot",
                    "bot_token": "xoxb-test-token",
                    "app_token": "xapp-test-token",
                    "persona_id": "support",
                    "default_channel": "C123",
                    "enabled": True,
                    "created_at": "2026-06-01T00:00:00+00:00",
                    "updated_at": "2026-06-02T00:00:00+00:00",
                },
            ),
            LegacyRow(
                source_table="rag_sources",
                source_pk="tenant_1:docs:https://docs.example/reactor",
                payload={
                    "id": "rag_source_1",
                    "tenant_id": "tenant_1",
                    "collection": "docs",
                    "source_uri": "https://docs.example/reactor",
                    "source_type": "docs",
                    "checksum": "checksum_rag_source_1",
                    "metadata": {"kind": "manual"},
                    "created_at": "2026-06-01T00:00:00+00:00",
                },
            ),
            LegacyRow(
                source_table="rag_documents",
                source_pk="tenant_1:rag_source_1:v1",
                payload={
                    "id": "rag_doc_1",
                    "tenant_id": "tenant_1",
                    "source_id": "rag_source_1",
                    "collection": "docs",
                    "title": "Reactor RAG Guide",
                    "version": "v1",
                    "acl": {"visibility": "private", "groups": ["engineering"]},
                    "metadata": {"section": "runtime"},
                    "created_at": "2026-06-01T00:00:00+00:00",
                },
            ),
            LegacyRow(
                source_table="rag_chunks",
                source_pk="tenant_1:rag_doc_1:0",
                payload={
                    "id": "rag_chunk_1",
                    "tenant_id": "tenant_1",
                    "document_id": "rag_doc_1",
                    "collection": "docs",
                    "chunk_index": 0,
                    "content": "LangGraph orchestrates Reactor RAG with Postgres.",
                    "content_hash": "hash_rag_chunk_1",
                    "embedding": [1.0, *([0.0] * 1535)],
                    "metadata": {
                        "source_uri": "https://docs.example/reactor",
                        "acl_hash": "acl_rag_doc_1",
                    },
                    "created_at": "2026-06-01T00:00:00+00:00",
                },
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
                    "metadata": {"category": "preference", "key": "answer_style"},
                    "created_at": "2026-06-02T00:00:00+00:00",
                },
            ),
            LegacyRow(
                source_table="memory_embeddings",
                source_pk="tenant_1:memory_item_1",
                payload={
                    "memory_id": "memory_item_1",
                    "tenant_id": "tenant_1",
                    "embedding": [0.5, *([0.0] * 1535)],
                    "embedding_model": "text-embedding-3-small",
                    "created_at": "2026-06-03T00:00:00+00:00",
                },
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
                source_table="a2a_access_policies",
                source_pk="tenant_1:peer_1:policy_1",
                payload={
                    "id": "a2a_policy_1",
                    "tenant_id": "tenant_1",
                    "peer_agent_id": "peer_1",
                    "allow_inbound": True,
                    "allow_outbound": False,
                    "allowed_skills": ["plan"],
                    "created_at": "2026-06-07T00:00:00+00:00",
                },
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
                    "token_usage": {
                        "promptTokens": 10,
                        "completionTokens": 20,
                        "totalTokens": 30,
                    },
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
                source_table="scheduled_job_dead_letters",
                source_pk="tenant_1:scheduled_dead_1",
                payload={
                    "id": "scheduled_dead_1",
                    "tenant_id": "tenant_1",
                    "job_id": "job_1",
                    "job_name": "Daily docs sync",
                    "job_type": "MCP_TOOL",
                    "reason": "timeout",
                    "result": "Job failed: timeout",
                    "dry_run": True,
                    "created_at": "2026-06-04T00:00:00+00:00",
                },
            ),
            LegacyRow(
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
            ),
            LegacyRow(
                source_table="metric_agent_executions",
                source_pk="tenant_1:run_1:2026-06-01T12:00:00+00:00",
                payload={
                    "time": "2026-06-01T12:00:00+00:00",
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
                    "prompt_template_id": "prompt_template_1",
                    "intent_category": "engineering",
                    "guard_rejected": True,
                    "guard_stage": "InjectionDetection",
                    "guard_category": "prompt_injection",
                    "retry_count": 1,
                    "fallback_used": True,
                },
            ),
            LegacyRow(
                source_table="metric_sessions",
                source_pk="tenant_1:session_1:2026-06-01T13:00:00+00:00",
                payload={
                    "time": "2026-06-01T13:00:00+00:00",
                    "tenant_id": "tenant_1",
                    "session_id": "session_1",
                    "user_id": "user_1",
                    "channel": "slack",
                    "turn_count": 3,
                    "total_duration_ms": 5000,
                    "total_tokens": 2000,
                    "total_cost_usd": "0.01234567",
                    "first_response_latency_ms": 850,
                    "outcome": "resolved",
                    "started_at": "2026-06-01T12:00:00+00:00",
                    "ended_at": "2026-06-01T12:05:00+00:00",
                },
            ),
            LegacyRow(
                source_table="metric_spans",
                source_pk="tenant_1:trace_1:span_1",
                payload={
                    "time": "2026-06-01T13:30:00+00:00",
                    "tenant_id": "tenant_1",
                    "trace_id": "trace_1",
                    "span_id": "span_1",
                    "operation_name": "graph.node",
                    "service_name": "reactor",
                    "duration_ms": 42,
                    "success": True,
                    "attributes": {"node": "tools"},
                },
            ),
            LegacyRow(
                source_table="metric_audit_trail",
                source_pk="tenant_1:TENANT_UPDATED:tenant_1:2026-06-01T14:00:00+00:00",
                payload={
                    "time": "2026-06-01T14:00:00+00:00",
                    "tenant_id": "tenant_1",
                    "event_type": "TENANT_UPDATED",
                    "resource_id": "tenant_1",
                    "detail": {"field": "quota"},
                },
            ),
            LegacyRow(
                source_table="metric_quota_events",
                source_pk="tenant_1:blocked:2026-06-01T14:30:00+00:00",
                payload={
                    "time": "2026-06-01T14:30:00+00:00",
                    "tenant_id": "tenant_1",
                    "action": "blocked",
                    "current_usage": 110,
                    "quota_limit": 100,
                    "usage_percent": 110.0,
                },
            ),
            LegacyRow(
                source_table="metric_hitl_events",
                source_pk="tenant_1:run_1:deploy:2026-06-01T15:00:00+00:00",
                payload={
                    "time": "2026-06-01T15:00:00+00:00",
                    "tenant_id": "tenant_1",
                    "run_id": "run_1",
                    "tool_name": "deploy",
                    "approved": False,
                    "wait_ms": 12000,
                },
            ),
            LegacyRow(
                source_table="metric_tool_calls",
                source_pk="tenant_1:run_1:jira_search:2",
                payload={
                    "time": "2026-06-01T12:30:00+00:00",
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
                },
            ),
            LegacyRow(
                source_table="metric_mcp_health",
                source_pk="tenant_1:jira:2026-06-01T12:45:00+00:00",
                payload={
                    "time": "2026-06-01T12:45:00+00:00",
                    "tenant_id": "tenant_1",
                    "server_name": "jira",
                    "status": "DISCONNECTED",
                    "response_time_ms": 250,
                    "error_class": "connect_timeout",
                    "error_message": "server did not respond",
                    "tool_count": 12,
                },
            ),
            LegacyRow(
                source_table="metric_eval_results",
                source_pk="tenant_1:eval_run_1:case_1",
                payload={
                    "time": "2026-06-01T13:00:00+00:00",
                    "tenant_id": "tenant_1",
                    "eval_run_id": "eval_run_1",
                    "test_case_id": "case_1",
                    "pass": False,
                    "score": 0.42,
                    "latency_ms": 850,
                    "token_usage": 1234,
                    "cost": "0.01234567",
                    "assertion_type": "contains",
                    "failure_class": "missing_phrase",
                    "failure_detail": "expected phrase was missing",
                    "tags": "regression, safety",
                },
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
            LegacyRow(
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
            ),
        ]

        try:
            for rollback_row in rollback_rows:
                await rollback_store.save_snapshot(row=rollback_row, batch_id="batch_1")
            app_container = AppContainer(
                settings=get_settings(),
                engine=engine,
                session_factory=session_factory,
                graph=None,
                checkpointer=None,
            )
            target_dispatcher = app_container.migration_target_dispatcher()
            assert target_dispatcher is not None
            first = await CutoverDressRehearsal(
                readers=[StaticLegacyReader(legacy_rows)],
                sink=import_store,
                rollback_rows=rollback_rows,
                target_dispatcher=target_dispatcher,
            ).run(batch_id="batch_1")
            second = await CutoverDressRehearsal(
                readers=[StaticLegacyReader(legacy_rows)],
                sink=import_store,
                rollback_rows=rollback_rows,
                target_dispatcher=target_dispatcher,
            ).run(batch_id="batch_1")

            async with session_factory() as session:
                imports = list(await session.scalars(select(MigrationImport)))
                snapshots = list(await session.scalars(select(MigrationRollbackSnapshot)))
                runtime_settings = list(await session.scalars(select(RuntimeSetting)))
                tenants = list(await session.scalars(select(Tenant)))
                slack_bots = list(await session.scalars(select(SlackBotInstance)))
                rag_sources = list(await session.scalars(select(RagSource)))
                rag_documents = list(await session.scalars(select(RagDocument)))
                rag_chunks = list(await session.scalars(select(RagChunk)))
                rag_ingestion_candidates = list(
                    await session.scalars(select(RagIngestionCandidateRow))
                )
                memory_namespaces = list(await session.scalars(select(MemoryNamespace)))
                memory_items = list(await session.scalars(select(MemoryItem)))
                memory_embeddings = list(await session.scalars(select(MemoryEmbedding)))
                memory_proposals = list(await session.scalars(select(MemoryProposal)))
                mcp_servers = list(await session.scalars(select(McpServer)))
                mcp_statuses = list(await session.scalars(select(McpServerStatus)))
                mcp_tool_snapshots = list(await session.scalars(select(McpToolSnapshot)))
                mcp_access_policies = list(await session.scalars(select(McpAccessPolicy)))
                a2a_peer_agents = list(await session.scalars(select(A2APeerAgent)))
                a2a_agent_cards = list(await session.scalars(select(A2AAgentCard)))
                a2a_tasks = list(await session.scalars(select(A2ATask)))
                a2a_task_events = list(await session.scalars(select(A2ATaskEvent)))
                a2a_push_subscriptions = list(await session.scalars(select(A2APushSubscription)))
                a2a_access_policies = list(await session.scalars(select(A2AAccessPolicy)))
                prompt_templates = list(await session.scalars(select(PromptTemplate)))
                prompt_versions = list(await session.scalars(select(PromptVersion)))
                prompt_releases = list(await session.scalars(select(PromptRelease)))
                prompt_lab_experiments = list(await session.scalars(select(PromptLabExperiment)))
                prompt_lab_trials = list(await session.scalars(select(PromptLabTrial)))
                prompt_lab_reports = list(await session.scalars(select(PromptLabReport)))
                personas = list(await session.scalars(select(PersonaRow)))
                agent_specs = list(await session.scalars(select(AgentSpecRow)))
                intent_definitions = list(await session.scalars(select(IntentDefinitionModel)))
                agent_runs = list(await session.scalars(select(AgentRun)))
                agent_run_events = list(await session.scalars(select(AgentRunEvent)))
                run_queue_rows = list(await session.scalars(select(RunQueue)))
                dead_letter_jobs = list(await session.scalars(select(DeadLetterJob)))
                idempotency_records = list(await session.scalars(select(IdempotencyRecord)))
                outbox_events = list(await session.scalars(select(OutboxEvent)))
                inbox_events = list(await session.scalars(select(InboxEvent)))
                users = list(await session.scalars(select(AuthUser)))
                user_identities = list(await session.scalars(select(UserIdentity)))
                token_revocations = list(await session.scalars(select(AuthTokenRevocation)))
                input_guard_rules = list(await session.scalars(select(InputGuardRule)))
                output_guard_rules = list(await session.scalars(select(OutputGuardRule)))
                output_guard_audits = list(await session.scalars(select(OutputGuardRuleAudit)))
                admin_audits = list(await session.scalars(select(AdminAudit)))
                tool_catalog = list(await session.scalars(select(ToolCatalog)))
                pending_approvals = list(await session.scalars(select(PendingApproval)))
                tool_invocations = list(await session.scalars(select(ToolInvocation)))
                feedback_rows = list(await session.scalars(select(FeedbackRecord)))
                eval_cases = list(await session.scalars(select(AgentEvalCase)))
                eval_results = list(await session.scalars(select(AgentEvalResult)))
                scheduled_jobs = list(await session.scalars(select(ScheduledJob)))
                scheduled_executions = list(await session.scalars(select(ScheduledJobExecution)))
                scheduled_dead_letters = list(await session.scalars(select(ScheduledJobDeadLetter)))
                model_pricing = list(await session.scalars(select(ModelPricing)))
                usage_ledger = list(await session.scalars(select(UsageLedger)))
                alert_rules = list(await session.scalars(select(AlertRuleRow)))
                alert_instances = list(await session.scalars(select(AlertInstanceRow)))

            assert first.readiness_exit_code == 0
            assert first.readiness_report["ok"] is True
            assert first.import_summary.imported == 67
            assert second.readiness_exit_code == 0
            assert second.readiness_report["ok"] is True
            assert second.import_summary.imported == 0
            assert second.import_summary.duplicates == 67
            assert sorted((row.source_table, row.source_pk, row.batch_id) for row in imports) == [
                ("a2a_access_policies", "tenant_1:peer_1:policy_1", "batch_1"),
                ("a2a_agent_cards", "tenant_1:v1:card_1", "batch_1"),
                ("a2a_peer_agents", "tenant_1:planner:peer_1", "batch_1"),
                (
                    "a2a_push_subscriptions",
                    "tenant_1:https://hooks.example.com/a2a:push_1",
                    "batch_1",
                ),
                ("a2a_task_events", "tenant_1:task_1:2:event_1", "batch_1"),
                ("a2a_tasks", "tenant_1:task_1", "batch_1"),
                ("admin_audits", "tenant_1:admin_audit_1", "batch_1"),
                ("agent_eval_cases", "tenant_1:case_1", "batch_1"),
                ("agent_eval_results", "tenant_1:result_1", "batch_1"),
                ("agent_run_events", "tenant_1:run_1:3:42", "batch_1"),
                ("agent_runs", "tenant_1:run_1", "batch_1"),
                ("agent_specs", "agent_spec_1", "batch_1"),
                ("alert_instances", "rule_1:alert_1", "batch_1"),
                ("alert_rules", "tenant_1:rule_1", "batch_1"),
                ("auth_token_revocations", "jti_1", "batch_1"),
                ("dead_letter_jobs", "tenant_1:dead_1", "batch_1"),
                ("feedback", "tenant_1:fb_1", "batch_1"),
                (
                    "idempotency_records",
                    "tenant_1:tool:tool:tenant_1:run_1:hash",
                    "batch_1",
                ),
                ("inbox_events", "tenant_1:slack:Ev123", "batch_1"),
                ("input_guard_rules", "tenant_1:input_rule_1", "batch_1"),
                ("intent_definitions", "support", "batch_1"),
                (
                    "mcp_access_policies",
                    "tenant_1:standard:mcp_1:policy_1",
                    "batch_1",
                ),
                (
                    "mcp_server_status",
                    "tenant_1:mcp_1",
                    "batch_1",
                ),
                (
                    "mcp_servers",
                    "tenant_1:docs:mcp_1",
                    "batch_1",
                ),
                (
                    "mcp_tool_snapshots",
                    "tenant_1:mcp_1:search:snapshot_1",
                    "batch_1",
                ),
                (
                    "memory_embeddings",
                    "tenant_1:memory_item_1",
                    "batch_1",
                ),
                (
                    "memory_items",
                    "tenant_1:memory_namespace_1:memory_item_1",
                    "batch_1",
                ),
                (
                    "memory_namespaces",
                    "tenant_1:user:user_1:semantic:user",
                    "batch_1",
                ),
                (
                    "memory_proposals",
                    "tenant_1:memory_namespace_1:memory_proposal_1",
                    "batch_1",
                ),
                (
                    "metric_agent_executions",
                    "tenant_1:run_1:2026-06-01T12:00:00+00:00",
                    "batch_1",
                ),
                (
                    "metric_audit_trail",
                    "tenant_1:TENANT_UPDATED:tenant_1:2026-06-01T14:00:00+00:00",
                    "batch_1",
                ),
                ("metric_eval_results", "tenant_1:eval_run_1:case_1", "batch_1"),
                (
                    "metric_hitl_events",
                    "tenant_1:run_1:deploy:2026-06-01T15:00:00+00:00",
                    "batch_1",
                ),
                ("metric_mcp_health", "tenant_1:jira:2026-06-01T12:45:00+00:00", "batch_1"),
                ("metric_quota_events", "tenant_1:blocked:2026-06-01T14:30:00+00:00", "batch_1"),
                ("metric_sessions", "tenant_1:session_1:2026-06-01T13:00:00+00:00", "batch_1"),
                ("metric_spans", "tenant_1:trace_1:span_1", "batch_1"),
                ("metric_tool_calls", "tenant_1:run_1:jira_search:2", "batch_1"),
                ("model_pricing", "openai:gpt-5-mini:pricing_1", "batch_1"),
                ("outbox_events", "tenant_1:outbox_1", "batch_1"),
                ("output_guard_rule_audits", "tenant_1:output_audit_1", "batch_1"),
                ("output_guard_rules", "tenant_1:output_rule_1", "batch_1"),
                ("pending_approvals", "tenant_1:approval_1", "batch_1"),
                ("personas", "persona_1", "batch_1"),
                ("prompt_lab_experiments", "tenant_1:exp_1", "batch_1"),
                ("prompt_lab_reports", "tenant_1:exp_1", "batch_1"),
                ("prompt_lab_trials", "tenant_1:exp_1:trial_1", "batch_1"),
                ("prompt_releases", "tenant_1:prompt_template_1:production", "batch_1"),
                (
                    "prompt_templates",
                    "tenant_1:prompt_template_1",
                    "batch_1",
                ),
                (
                    "prompt_versions",
                    "tenant_1:prompt_template_1:prompt_version_1",
                    "batch_1",
                ),
                ("rag_chunks", "tenant_1:rag_doc_1:0", "batch_1"),
                ("rag_documents", "tenant_1:rag_source_1:v1", "batch_1"),
                ("rag_ingestion_candidates", "rag_candidate_1", "batch_1"),
                ("rag_sources", "tenant_1:docs:https://docs.example/reactor", "batch_1"),
                ("run_queue", "tenant_1:queue_1", "batch_1"),
                ("runtime_settings", "tenant_1:agent.timeout", "batch_1"),
                ("scheduled_job_dead_letters", "tenant_1:scheduled_dead_1", "batch_1"),
                ("scheduled_job_executions", "tenant_1:exec_1", "batch_1"),
                ("scheduled_jobs", "tenant_1:job_1", "batch_1"),
                ("slack_bot_instances", "tenant_1:bot_1", "batch_1"),
                ("tenant_slo_config", "tenant_1", "batch_1"),
                ("tenants", "tenant_1", "batch_1"),
                ("tool_catalog", "tenant_1:builtin:send_webhook:tool_1", "batch_1"),
                ("tool_invocations", "tenant_1:invocation_1", "batch_1"),
                ("usage_ledger", "tenant_1:usage_1", "batch_1"),
                ("user_identities", "tenant_1:jira:acct-123", "batch_1"),
                ("users", "tenant_1:user_1", "batch_1"),
            ]
            assert sorted((row.target_table, row.target_pk, row.batch_id) for row in snapshots) == [
                ("a2a_access_policies", "tenant_1:peer_1:policy_1", "batch_1"),
                ("a2a_agent_cards", "tenant_1:v1:card_1", "batch_1"),
                ("a2a_peer_agents", "tenant_1:planner:peer_1", "batch_1"),
                (
                    "a2a_push_subscriptions",
                    "tenant_1:https://hooks.example.com/a2a:push_1",
                    "batch_1",
                ),
                ("a2a_task_events", "tenant_1:task_1:2:event_1", "batch_1"),
                ("a2a_tasks", "tenant_1:task_1", "batch_1"),
                ("admin_audits", "tenant_1:admin_audit_1", "batch_1"),
                ("agent_eval_cases", "tenant_1:case_1", "batch_1"),
                ("agent_eval_results", "tenant_1:result_1", "batch_1"),
                ("agent_run_events", "tenant_1:run_1:3:42", "batch_1"),
                ("agent_runs", "tenant_1:run_1", "batch_1"),
                ("agent_specs", "agent_spec_1", "batch_1"),
                ("alert_instances", "rule_1:alert_1", "batch_1"),
                ("alert_rules", "tenant_1:rule_1", "batch_1"),
                ("auth_token_revocations", "jti_1", "batch_1"),
                ("dead_letter_jobs", "tenant_1:dead_1", "batch_1"),
                ("feedback", "tenant_1:fb_1", "batch_1"),
                (
                    "idempotency_records",
                    "tenant_1:tool:tool:tenant_1:run_1:hash",
                    "batch_1",
                ),
                ("inbox_events", "tenant_1:slack:Ev123", "batch_1"),
                ("input_guard_rules", "tenant_1:input_rule_1", "batch_1"),
                ("intent_definitions", "support", "batch_1"),
                (
                    "mcp_access_policies",
                    "tenant_1:standard:mcp_1:policy_1",
                    "batch_1",
                ),
                (
                    "mcp_server_status",
                    "tenant_1:mcp_1",
                    "batch_1",
                ),
                (
                    "mcp_servers",
                    "tenant_1:docs:mcp_1",
                    "batch_1",
                ),
                (
                    "mcp_tool_snapshots",
                    "tenant_1:mcp_1:search:snapshot_1",
                    "batch_1",
                ),
                (
                    "memory_embeddings",
                    "tenant_1:memory_item_1",
                    "batch_1",
                ),
                (
                    "memory_items",
                    "tenant_1:memory_namespace_1:memory_item_1",
                    "batch_1",
                ),
                (
                    "memory_namespaces",
                    "tenant_1:user:user_1:semantic:user",
                    "batch_1",
                ),
                (
                    "memory_proposals",
                    "tenant_1:memory_namespace_1:memory_proposal_1",
                    "batch_1",
                ),
                (
                    "metric_agent_executions",
                    "tenant_1:run_1:2026-06-01T12:00:00+00:00",
                    "batch_1",
                ),
                (
                    "metric_audit_trail",
                    "tenant_1:TENANT_UPDATED:tenant_1:2026-06-01T14:00:00+00:00",
                    "batch_1",
                ),
                ("metric_eval_results", "tenant_1:eval_run_1:case_1", "batch_1"),
                (
                    "metric_hitl_events",
                    "tenant_1:run_1:deploy:2026-06-01T15:00:00+00:00",
                    "batch_1",
                ),
                ("metric_mcp_health", "tenant_1:jira:2026-06-01T12:45:00+00:00", "batch_1"),
                ("metric_quota_events", "tenant_1:blocked:2026-06-01T14:30:00+00:00", "batch_1"),
                ("metric_sessions", "tenant_1:session_1:2026-06-01T13:00:00+00:00", "batch_1"),
                ("metric_spans", "tenant_1:trace_1:span_1", "batch_1"),
                ("metric_tool_calls", "tenant_1:run_1:jira_search:2", "batch_1"),
                ("model_pricing", "openai:gpt-5-mini:pricing_1", "batch_1"),
                ("outbox_events", "tenant_1:outbox_1", "batch_1"),
                ("output_guard_rule_audits", "tenant_1:output_audit_1", "batch_1"),
                ("output_guard_rules", "tenant_1:output_rule_1", "batch_1"),
                ("pending_approvals", "tenant_1:approval_1", "batch_1"),
                ("personas", "persona_1", "batch_1"),
                ("prompt_lab_experiments", "tenant_1:exp_1", "batch_1"),
                ("prompt_lab_reports", "tenant_1:exp_1", "batch_1"),
                ("prompt_lab_trials", "tenant_1:exp_1:trial_1", "batch_1"),
                ("prompt_releases", "tenant_1:prompt_template_1:production", "batch_1"),
                (
                    "prompt_templates",
                    "tenant_1:prompt_template_1",
                    "batch_1",
                ),
                (
                    "prompt_versions",
                    "tenant_1:prompt_template_1:prompt_version_1",
                    "batch_1",
                ),
                ("rag_chunks", "tenant_1:rag_doc_1:0", "batch_1"),
                ("rag_documents", "tenant_1:rag_source_1:v1", "batch_1"),
                ("rag_ingestion_candidates", "rag_candidate_1", "batch_1"),
                ("rag_sources", "tenant_1:docs:https://docs.example/reactor", "batch_1"),
                ("run_queue", "tenant_1:queue_1", "batch_1"),
                ("runtime_settings", "tenant_1:agent.timeout", "batch_1"),
                ("scheduled_job_dead_letters", "tenant_1:scheduled_dead_1", "batch_1"),
                ("scheduled_job_executions", "tenant_1:exec_1", "batch_1"),
                ("scheduled_jobs", "tenant_1:job_1", "batch_1"),
                ("slack_bot_instances", "tenant_1:bot_1", "batch_1"),
                ("tenant_slo_config", "tenant_1", "batch_1"),
                ("tenants", "tenant_1", "batch_1"),
                ("tool_catalog", "tenant_1:builtin:send_webhook:tool_1", "batch_1"),
                ("tool_invocations", "tenant_1:invocation_1", "batch_1"),
                ("usage_ledger", "tenant_1:usage_1", "batch_1"),
                ("user_identities", "tenant_1:jira:acct-123", "batch_1"),
                ("users", "tenant_1:user_1", "batch_1"),
            ]
            assert [
                (row.tenant_id, row.key, row.value, row.value_type, row.category)
                for row in runtime_settings
            ] == [("tenant_1", "agent.timeout", "30", "INT", "agent")]
            assert [
                (
                    row.id,
                    row.name,
                    row.slug,
                    row.plan,
                    row.status,
                    row.slo_availability,
                    row.slo_latency_p99_ms,
                    row.tenant_metadata,
                )
                for row in tenants
            ] == [
                (
                    "tenant_1",
                    "Acme",
                    "acme",
                    "BUSINESS",
                    "ACTIVE",
                    0.9995,
                    4500,
                    {
                        "tier": "paid",
                        "legacy_slo_config": {"error_budget_window_days": 28},
                    },
                )
            ]
            assert app_container.metric_ingestion_buffer().events == [
                {
                    "time": "2026-06-01T12:00:00+00:00",
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
                    "prompt_template_id": "prompt_template_1",
                    "intent_category": "engineering",
                    "guard_rejected": True,
                    "guard_stage": "InjectionDetection",
                    "guard_category": "prompt_injection",
                    "retry_count": 1,
                    "fallback_used": True,
                },
                {
                    "time": "2026-06-01T13:00:00+00:00",
                    "tenant_id": "tenant_1",
                    "session_id": "session_1",
                    "user_id": "user_1",
                    "channel": "slack",
                    "turn_count": 3,
                    "total_duration_ms": 5000,
                    "total_tokens": 2000,
                    "total_cost_usd": "0.01234567",
                    "first_response_latency_ms": 850,
                    "outcome": "resolved",
                    "started_at": "2026-06-01T12:00:00+00:00",
                    "ended_at": "2026-06-01T12:05:00+00:00",
                },
                {
                    "time": "2026-06-01T13:30:00+00:00",
                    "tenant_id": "tenant_1",
                    "trace_id": "trace_1",
                    "span_id": "span_1",
                    "operation_name": "graph.node",
                    "service_name": "reactor",
                    "duration_ms": 42,
                    "success": True,
                    "attributes": {"node": "tools"},
                },
                {
                    "time": "2026-06-01T14:00:00+00:00",
                    "tenant_id": "tenant_1",
                    "event_type": "TENANT_UPDATED",
                    "resource_id": "tenant_1",
                    "detail": {"field": "quota"},
                },
                {
                    "time": "2026-06-01T14:30:00+00:00",
                    "tenant_id": "tenant_1",
                    "action": "blocked",
                    "current_usage": 110,
                    "quota_limit": 100,
                    "usage_percent": 110.0,
                },
                {
                    "time": "2026-06-01T15:00:00+00:00",
                    "tenant_id": "tenant_1",
                    "run_id": "run_1",
                    "tool_name": "deploy",
                    "approved": False,
                    "wait_ms": 12000,
                },
                {
                    "time": "2026-06-01T12:30:00+00:00",
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
                },
                {
                    "time": "2026-06-01T12:45:00+00:00",
                    "tenant_id": "tenant_1",
                    "server_name": "jira",
                    "status": "DISCONNECTED",
                    "response_time_ms": 250,
                    "error_class": "connect_timeout",
                    "error_message": "server did not respond",
                    "tool_count": 12,
                },
                {
                    "time": "2026-06-01T13:00:00+00:00",
                    "tenant_id": "tenant_1",
                    "eval_run_id": "eval_run_1",
                    "test_case_id": "case_1",
                    "pass": False,
                    "score": 0.42,
                    "latency_ms": 850,
                    "token_usage": 1234,
                    "cost": "0.01234567",
                    "assertion_type": "contains",
                    "failure_class": "missing_phrase",
                    "failure_detail": "expected phrase was missing",
                    "tags": "regression, safety",
                },
            ]
            assert [
                (
                    row.id,
                    row.email,
                    row.name,
                    row.password_hash,
                    row.role,
                    row.tenant_id,
                    row.groups,
                )
                for row in users
            ] == [
                (
                    "user_1",
                    "admin@example.com",
                    "Admin User",
                    "$argon2id$v=19$hash",  # noqa: S106
                    "ADMIN",
                    "tenant_1",
                    ["engineering", "finance"],
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.user_id,
                    row.provider,
                    row.external_subject,
                    row.identity_metadata,
                )
                for row in user_identities
            ] == [("identity_1", "tenant_1", "user_1", "jira", "acct-123", {"workspace": "ENG"})]
            assert [(row.token_id,) for row in token_revocations] == [("jti_1",)]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.name,
                    row.pattern,
                    row.pattern_type,
                    row.action,
                    row.priority,
                    row.category,
                    row.description,
                    row.enabled,
                )
                for row in input_guard_rules
            ] == [
                (
                    "input_rule_1",
                    "tenant_1",
                    "Block jailbreak",
                    "ignore previous instructions",
                    "keyword",
                    "block",
                    900,
                    "prompt_injection",
                    "Legacy prompt injection rule",
                    True,
                )
            ]
            assert [
                (
                    row.id,
                    row.provider,
                    row.model,
                    str(row.prompt_price_per_1m),
                    str(row.completion_price_per_1m),
                    str(row.cached_input_price_per_1m),
                    str(row.reasoning_price_per_1m),
                    str(row.batch_prompt_price_per_1m),
                    str(row.batch_completion_price_per_1m),
                )
                for row in model_pricing
            ] == [
                (
                    "pricing_1",
                    "openai",
                    "gpt-5-mini",
                    "1.25000000",
                    "10.00000000",
                    "0.12500000",
                    "2.00000000",
                    "0.50000000",
                    "5.00000000",
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.run_id,
                    row.provider,
                    row.model,
                    row.step_type,
                    row.prompt_tokens,
                    row.cached_tokens,
                    row.completion_tokens,
                    row.reasoning_tokens,
                    row.total_tokens,
                    str(row.estimated_cost_usd),
                )
                for row in usage_ledger
            ] == [
                (
                    "usage_1",
                    "tenant_1",
                    "run_1",
                    "openai",
                    "gpt-5-mini",
                    "model",
                    100,
                    20,
                    30,
                    5,
                    135,
                    "0.12345678",
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.name,
                    row.type,
                    row.severity,
                    row.metric,
                    row.threshold,
                    row.window_minutes,
                    row.enabled,
                    row.platform_only,
                )
                for row in alert_rules
            ] == [
                (
                    "rule_1",
                    "tenant_1",
                    "High error rate",
                    "STATIC_THRESHOLD",
                    "CRITICAL",
                    "error_rate",
                    0.1,
                    15,
                    True,
                    False,
                )
            ]
            assert [
                (
                    row.id,
                    row.rule_id,
                    row.tenant_id,
                    row.severity,
                    row.status,
                    row.message,
                    row.metric_value,
                    row.threshold,
                    row.acknowledged_by,
                )
                for row in alert_instances
            ] == [
                (
                    "alert_1",
                    "rule_1",
                    "tenant_1",
                    "CRITICAL",
                    "RESOLVED",
                    "error_rate exceeded threshold",
                    0.2,
                    0.1,
                    "admin_1",
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.name,
                    row.pattern,
                    row.action,
                    row.replacement,
                    row.priority,
                    row.enabled,
                )
                for row in output_guard_rules
            ] == [
                (
                    "output_rule_1",
                    "tenant_1",
                    "Mask API keys",
                    "sk-[A-Za-z0-9]+",
                    "MASK",
                    "[SECRET]",
                    10,
                    True,
                )
            ]
            assert [
                (row.id, row.tenant_id, row.rule_id, row.action, row.actor, row.detail)
                for row in output_guard_audits
            ] == [
                (
                    "output_audit_1",
                    "tenant_1",
                    "output_rule_1",
                    "SIMULATE",
                    "admin_1",
                    "masked 2 values",
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.category,
                    row.action,
                    row.actor,
                    row.resource_type,
                    row.resource_id,
                    row.detail,
                )
                for row in admin_audits
            ] == [
                (
                    "admin_audit_1",
                    "tenant_1",
                    "slack",
                    "ADD",
                    "admin@example.com",
                    "slack_channel",
                    "C123",
                    "added proactive channel",
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.namespace,
                    row.name,
                    row.description,
                    row.risk_level,
                    row.input_schema,
                    row.output_schema,
                    row.enabled,
                    row.requires_approval,
                    row.timeout_ms,
                )
                for row in tool_catalog
            ] == [
                (
                    "tool_1",
                    "tenant_1",
                    "builtin",
                    "send_webhook",
                    "Send a signed webhook.",
                    "external_side_effect",
                    {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                    },
                    {"type": "object"},
                    True,
                    True,
                    15000,
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.run_id,
                    row.tool_id,
                    row.status,
                    row.requested_by,
                    row.decided_by,
                    row.request_payload,
                    row.decision_reason,
                )
                for row in pending_approvals
            ] == [
                (
                    "approval_1",
                    "tenant_1",
                    "run_1",
                    "tool_1",
                    "approved",
                    "user_1",
                    "admin_1",
                    {"args": {"url": "https://example.com"}},
                    "approved for incident response",
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.run_id,
                    row.tool_id,
                    row.approval_id,
                    row.status,
                    row.idempotency_key,
                    row.request_checksum,
                    row.result_checksum,
                    row.input_payload,
                    row.output_payload,
                    row.error_payload,
                )
                for row in tool_invocations
            ] == [
                (
                    "invocation_1",
                    "tenant_1",
                    "run_1",
                    "tool_1",
                    "approval_1",
                    "succeeded",
                    "tool:tenant_1:run_1:builtin:send_webhook:abc",
                    "sha256:req",
                    "sha256:result",
                    {"url": "https://example.com"},
                    {"status": 200},
                    None,
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.rating,
                    row.source,
                    row.run_id,
                    row.user_id,
                    row.intent,
                    row.domain,
                    row.model,
                    row.prompt_version,
                    row.tools_used,
                    row.tags,
                    row.review_status,
                    row.review_tags,
                    row.reviewed_by,
                    row.review_note,
                    row.version,
                )
                for row in feedback_rows
            ] == [
                (
                    "fb_1",
                    "tenant_1",
                    "THUMBS_DOWN",
                    "slack_button",
                    "run_1",
                    "user_1",
                    "support",
                    "security",
                    "gpt-4.1",
                    7,
                    ["rag.search"],
                    ["security", "faq"],
                    "done",
                    ["sso", "docs"],
                    "admin_1",
                    "Added to FAQ backlog",
                    3,
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.name,
                    row.expected_answer_contains,
                    row.forbidden_answer_contains,
                    row.expected_tool_names,
                    row.forbidden_tool_names,
                    row.expected_exposed_tool_names,
                    row.forbidden_exposed_tool_names,
                    row.max_tool_exposure_count,
                    row.agent_type,
                    row.model,
                    row.enabled,
                    row.tags,
                    row.min_score,
                    row.source_run_id,
                )
                for row in eval_cases
            ] == [
                (
                    "case_1",
                    "tenant_1",
                    "MFA reset",
                    ["security portal"],
                    ["ask admin"],
                    ["search_docs"],
                    ["delete_user"],
                    ["search_docs"],
                    ["delete_user"],
                    3,
                    "reactor",
                    "gpt-5",
                    True,
                    ["security", "faq"],
                    0.8,
                    "run_1",
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.case_id,
                    row.run_id,
                    row.tier,
                    row.passed,
                    row.score,
                    row.reasons,
                )
                for row in eval_results
            ] == [
                (
                    "result_1",
                    "tenant_1",
                    "case_1",
                    "run_1",
                    "deterministic",
                    False,
                    0.4,
                    ["missing expected phrase"],
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.name,
                    row.cron_expression,
                    row.timezone,
                    row.job_type,
                    row.mcp_server_name,
                    row.tool_name,
                    row.tool_arguments,
                    row.slack_channel_id,
                    row.retry_on_failure,
                    row.max_retry_count,
                    row.execution_timeout_ms,
                    row.enabled,
                    row.last_status,
                    row.last_result,
                )
                for row in scheduled_jobs
            ] == [
                (
                    "job_1",
                    "tenant_1",
                    "Daily docs sync",
                    "0 9 * * *",
                    "Asia/Seoul",
                    "MCP_TOOL",
                    "docs",
                    "sync_docs",
                    {"space": "ENG"},
                    "C123",
                    True,
                    2,
                    30000,
                    True,
                    "SUCCESS",
                    "ok",
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.job_id,
                    row.job_name,
                    row.job_type,
                    row.status,
                    row.result,
                    row.duration_ms,
                    row.dry_run,
                )
                for row in scheduled_executions
            ] == [
                (
                    "exec_1",
                    "tenant_1",
                    "job_1",
                    "Daily docs sync",
                    "MCP_TOOL",
                    "SUCCESS",
                    "ok",
                    2500,
                    False,
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.job_id,
                    row.job_name,
                    row.job_type,
                    row.reason,
                    row.result,
                    row.dry_run,
                )
                for row in scheduled_dead_letters
            ] == [
                (
                    "scheduled_dead_1",
                    "tenant_1",
                    "job_1",
                    "Daily docs sync",
                    "MCP_TOOL",
                    "timeout",
                    "Job failed: timeout",
                    True,
                )
            ]
            assert [(row.id, row.tenant_id, row.name, row.enabled) for row in slack_bots] == [
                ("bot_1", "tenant_1", "Support Bot", True)
            ]
            assert [
                (row.id, row.tenant_id, row.collection, row.source_uri, row.checksum)
                for row in rag_sources
            ] == [
                (
                    "rag_source_1",
                    "tenant_1",
                    "docs",
                    "https://docs.example/reactor",
                    "checksum_rag_source_1",
                )
            ]
            assert [(row.id, row.source_id, row.title, row.acl) for row in rag_documents] == [
                (
                    "rag_doc_1",
                    "rag_source_1",
                    "Reactor RAG Guide",
                    {"visibility": "private", "groups": ["engineering"]},
                )
            ]
            assert [
                (row.id, row.document_id, row.content_hash, row.chunk_metadata)
                for row in rag_chunks
            ] == [
                (
                    "rag_chunk_1",
                    "rag_doc_1",
                    "hash_rag_chunk_1",
                    {
                        "source_uri": "https://docs.example/reactor",
                        "acl_hash": "acl_rag_doc_1",
                    },
                )
            ]
            assert [
                (
                    row.id,
                    row.run_id,
                    row.user_id,
                    row.session_id,
                    row.channel,
                    row.query,
                    row.response,
                    row.status,
                    row.reviewed_by,
                    row.review_comment,
                    row.ingested_document_id,
                )
                for row in rag_ingestion_candidates
            ] == [
                (
                    "rag_candidate_1",
                    "run_1",
                    "user_1",
                    "session_1",
                    "slack",
                    "How do I reset MFA?",
                    "Use the MFA reset workflow.",
                    "INGESTED",
                    "admin_1",
                    "Useful FAQ.",
                    "rag_doc_1",
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.subject_type,
                    row.subject_id,
                    row.memory_type,
                    row.visibility,
                )
                for row in memory_namespaces
            ] == [
                (
                    "memory_namespace_1",
                    "tenant_1",
                    "user",
                    "user_1",
                    "semantic",
                    "user",
                )
            ]
            assert [
                (
                    row.id,
                    row.namespace_id,
                    row.tenant_id,
                    row.status,
                    row.content,
                    row.source_id,
                    row.confidence,
                    row.item_metadata,
                )
                for row in memory_items
            ] == [
                (
                    "memory_item_1",
                    "memory_namespace_1",
                    "tenant_1",
                    "active",
                    "prefers concise answers",
                    "run_1",
                    0.91,
                    {"category": "preference", "key": "answer_style"},
                )
            ]
            assert [
                (row.memory_id, row.tenant_id, list(row.embedding)[:2], row.embedding_model)
                for row in memory_embeddings
            ] == [
                (
                    "memory_item_1",
                    "tenant_1",
                    [0.5, 0.0],
                    "text-embedding-3-small",
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.namespace_id,
                    row.status,
                    row.proposed_content,
                    row.extraction_model,
                    row.extraction_prompt_version,
                    row.confidence,
                    row.source_payload,
                    row.decision_reason,
                )
                for row in memory_proposals
            ] == [
                (
                    "memory_proposal_1",
                    "tenant_1",
                    "memory_namespace_1",
                    "proposed",
                    "likes structured specs",
                    "gpt-4.1",
                    "v2",
                    0.88,
                    {"run_id": "run_1"},
                    None,
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.name,
                    row.transport,
                    row.status,
                    row.url,
                    row.auth_type,
                    row.timeout_ms,
                    row.protocol_version,
                    row.reconnect_policy,
                    row.tool_snapshot_hash,
                )
                for row in mcp_servers
            ] == [
                (
                    "mcp_1",
                    "tenant_1",
                    "docs",
                    "streamable_http",
                    "healthy",
                    "https://mcp.example.com",
                    "oauth2",
                    20000,
                    "2025-11-25",
                    {"max_attempts": 3},
                    "sha256:tools",
                )
            ]
            assert [
                (
                    row.server_id,
                    row.tenant_id,
                    row.status,
                    row.negotiated_protocol_version,
                    row.last_error,
                    row.reconnect_attempt,
                )
                for row in mcp_statuses
            ] == [("mcp_1", "tenant_1", "degraded", "2025-11-25", "timeout", 2)]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.server_id,
                    row.qualified_name,
                    row.tool_name,
                    row.input_schema,
                    row.output_schema,
                    row.risk_level,
                    row.enabled,
                    row.snapshot_hash,
                )
                for row in mcp_tool_snapshots
            ] == [
                (
                    "snapshot_1",
                    "tenant_1",
                    "mcp_1",
                    "docs:search",
                    "search",
                    {"type": "object"},
                    {"type": "object"},
                    "read",
                    True,
                    "sha256:tool",
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.server_id,
                    row.graph_profile,
                    row.allow_write,
                    row.allowed_tools,
                )
                for row in mcp_access_policies
            ] == [("policy_1", "tenant_1", "mcp_1", "standard", False, ["search"])]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.name,
                    row.endpoint_url,
                    row.agent_card,
                    row.enabled,
                )
                for row in a2a_peer_agents
            ] == [
                (
                    "peer_1",
                    "tenant_1",
                    "planner",
                    "https://a2a.example.com",
                    {"name": "Planner"},
                    True,
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.version,
                    row.protocol_version,
                    row.card,
                    row.active,
                )
                for row in a2a_agent_cards
            ] == [("card_1", "tenant_1", "v1", "1.0", {"name": "Reactor"}, True)]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.peer_agent_id,
                    row.run_id,
                    row.thread_id,
                    row.session_id,
                    row.context_id,
                    row.message_id,
                    row.status,
                    row.idempotency_key,
                    row.input_payload,
                    row.output_payload,
                )
                for row in a2a_tasks
            ] == [
                (
                    "task_1",
                    "tenant_1",
                    "peer_1",
                    "run_1",
                    "thread_1",
                    "session_1",
                    "ctx_1",
                    "msg_1",
                    "completed",
                    "a2a:tenant_1:ctx_1:msg_1",
                    {"input": "plan"},
                    {"answer": "done"},
                )
            ]
            assert [
                (
                    row.id,
                    row.task_id,
                    row.tenant_id,
                    row.sequence,
                    row.event_type,
                    row.payload,
                )
                for row in a2a_task_events
            ] == [("event_1", "task_1", "tenant_1", 2, "task.completed", {"status": "completed"})]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.destination,
                    row.signing_key_ref,
                    row.enabled,
                )
                for row in a2a_push_subscriptions
            ] == [("push_1", "tenant_1", "https://hooks.example.com/a2a", "kms://a2a", True)]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.peer_agent_id,
                    row.allow_inbound,
                    row.allow_outbound,
                    row.allowed_skills,
                )
                for row in a2a_access_policies
            ] == [("a2a_policy_1", "tenant_1", "peer_1", True, False, ["plan"])]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.name,
                    row.graph_profile,
                    row.description,
                    row.created_by,
                )
                for row in prompt_templates
            ] == [("prompt_template_1", "tenant_1", "support", "rag", "Support prompt", "admin_1")]
            assert [
                (
                    row.id,
                    row.template_id,
                    row.tenant_id,
                    row.version,
                    row.system_policy,
                    row.developer_policy,
                    row.examples,
                    row.prompt_metadata,
                    row.content_hash,
                    row.created_by,
                )
                for row in prompt_versions
            ] == [
                (
                    "prompt_version_1",
                    "prompt_template_1",
                    "tenant_1",
                    "1",
                    "Answer with citations.",
                    "Prefer RAG.",
                    ["Q: hi"],
                    {"legacyStatus": "ACTIVE"},
                    "sha256:abc",
                    "admin_1",
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.template_id,
                    row.version_id,
                    row.environment,
                    row.released_by,
                    row.release_metadata,
                )
                for row in prompt_releases
            ] == [
                (
                    "prompt_release_1",
                    "tenant_1",
                    "prompt_template_1",
                    "prompt_version_1",
                    "production",
                    "admin_1",
                    {"ticket": "CUT-1"},
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.name,
                    row.template_id,
                    row.baseline_version_id,
                    row.candidate_version_ids,
                    row.test_queries,
                    row.evaluation_config,
                    row.model,
                    row.status,
                    row.created_by,
                )
                for row in prompt_lab_experiments
            ] == [
                (
                    "exp_1",
                    "tenant_1",
                    "Support prompt experiment",
                    "prompt_template_1",
                    "prompt_version_1",
                    ["prompt_version_2"],
                    [
                        {
                            "query": "How do I reset MFA?",
                            "intent": None,
                            "domain": None,
                            "expectedBehavior": "cite policy",
                            "tags": ["mfa"],
                        }
                    ],
                    {
                        "structuralEnabled": True,
                        "rulesEnabled": True,
                        "llmJudgeEnabled": False,
                        "llmJudgeBudgetTokens": 100000,
                        "customRubric": None,
                    },
                    "openai:gpt-4.1-mini",
                    "COMPLETED",
                    "admin_1",
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.experiment_id,
                    row.prompt_version_id,
                    row.prompt_version_number,
                    row.test_query,
                    row.repetition_index,
                    row.response,
                    row.success,
                    row.tools_used,
                    row.token_usage,
                    row.duration_ms,
                    row.evaluations,
                )
                for row in prompt_lab_trials
            ] == [
                (
                    "trial_1",
                    "tenant_1",
                    "exp_1",
                    "prompt_version_2",
                    2,
                    {
                        "query": "How do I reset MFA?",
                        "intent": None,
                        "domain": None,
                        "expectedBehavior": None,
                        "tags": ["mfa"],
                    },
                    1,
                    "Use the MFA reset policy.",
                    True,
                    ["rag.search"],
                    {"promptTokens": 10, "completionTokens": 20, "totalTokens": 30},
                    123,
                    [
                        {
                            "tier": "RULES",
                            "passed": True,
                            "score": 0.9,
                            "reason": "Matched expected behavior.",
                            "evaluatorName": "RULES",
                        }
                    ],
                )
            ]
            assert [
                (
                    row.experiment_id,
                    row.tenant_id,
                    row.experiment_name,
                    row.total_trials,
                    row.version_summaries,
                    row.recommendation,
                )
                for row in prompt_lab_reports
            ] == [
                (
                    "exp_1",
                    "tenant_1",
                    "Support prompt experiment",
                    1,
                    [
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
                    {
                        "bestVersionId": "prompt_version_2",
                        "bestVersionNumber": 2,
                        "confidence": "HIGH",
                        "reasoning": "Candidate passed all trials.",
                        "improvements": ["Better grounding"],
                        "warnings": [],
                    },
                )
            ]
            assert [
                (
                    row.id,
                    row.name,
                    row.system_prompt,
                    row.is_default,
                    row.description,
                    row.response_guideline,
                    row.welcome_message,
                    row.icon,
                    row.is_active,
                    row.prompt_template_id,
                )
                for row in personas
            ] == [
                (
                    "persona_1",
                    "Support",
                    "Support users.",
                    True,
                    "Default support persona",
                    "Be concise.",
                    "Hi",
                    "sparkles",
                    True,
                    "prompt_template_1",
                )
            ]
            assert [
                (
                    row.id,
                    row.name,
                    row.description,
                    row.tool_names,
                    row.keywords,
                    row.system_prompt,
                    row.mode,
                    row.independent_execution,
                    row.enabled,
                )
                for row in agent_specs
            ] == [
                (
                    "agent_spec_1",
                    "Support agent",
                    "Handles support requests",
                    ["rag.search", "tickets.create"],
                    ["support", "ticket"],
                    "Resolve support cases.",
                    "PLAN_EXECUTE",
                    False,
                    True,
                )
            ]
            assert [
                (
                    row.name,
                    row.description,
                    row.examples,
                    row.keywords,
                    row.profile,
                    row.enabled,
                )
                for row in intent_definitions
            ] == [
                (
                    "support",
                    "Support request routing",
                    ["I need help with billing"],
                    ["help", "billing"],
                    "support",
                    True,
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.user_id,
                    row.thread_id,
                    row.checkpoint_ns,
                    row.status,
                    row.input_text,
                    row.response_text,
                    row.error_code,
                    row.run_metadata,
                )
                for row in agent_runs
            ] == [
                (
                    "run_1",
                    "tenant_1",
                    "user_1",
                    "thread_1",
                    "default",
                    "completed",
                    "hello",
                    "world",
                    None,
                    {"model": "gpt-4.1", "usage": {"total_tokens": 42}},
                )
            ]
            assert [
                (row.id, row.run_id, row.tenant_id, row.sequence, row.event_type, row.payload)
                for row in agent_run_events
            ] == [
                (
                    42,
                    "run_1",
                    "tenant_1",
                    3,
                    "model.token",
                    {"node": "model", "token": "hello", "trace_id": "trace_1"},
                )
            ]
            assert [
                (
                    row.id,
                    row.run_id,
                    row.tenant_id,
                    row.status,
                    row.priority,
                    row.attempt,
                    row.max_attempts,
                    row.lease_owner,
                    row.fencing_token,
                    row.payload,
                )
                for row in run_queue_rows
            ] == [
                (
                    "queue_1",
                    "run_1",
                    "tenant_1",
                    "leased",
                    10,
                    2,
                    5,
                    "worker_1",
                    7,
                    {"mode": "async"},
                )
            ]
            assert [
                (
                    row.id,
                    row.queue_id,
                    row.run_id,
                    row.tenant_id,
                    row.reason,
                    row.last_checkpoint_id,
                    row.trace_id,
                    row.payload,
                )
                for row in dead_letter_jobs
            ] == [
                (
                    "dead_1",
                    "queue_1",
                    "run_1",
                    "tenant_1",
                    "max_attempts_exhausted",
                    "checkpoint_1",
                    "trace_1",
                    {"error": "timeout"},
                )
            ]
            assert [
                (
                    row.key,
                    row.tenant_id,
                    row.scope,
                    row.request_checksum,
                    row.status,
                    row.response_payload,
                )
                for row in idempotency_records
            ] == [
                (
                    "tool:tenant_1:run_1:hash",
                    "tenant_1",
                    "tool",
                    "sha256:req",
                    "completed",
                    {"ok": True},
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.run_id,
                    row.destination,
                    row.event_type,
                    row.idempotency_key,
                    row.status,
                    row.attempt,
                    row.max_attempts,
                    row.payload,
                    row.last_error,
                    row.lease_owner,
                    row.lease_expires_at,
                )
                for row in outbox_events
            ] == [
                (
                    "outbox_1",
                    "tenant_1",
                    "run_1",
                    "slack",
                    "slack.message",
                    "slack:msg_1",
                    "retryable_failed",
                    2,
                    5,
                    {"channel": "C123"},
                    "rate limited",
                    "worker_1",
                    datetime(2026, 6, 1, 0, 4, tzinfo=UTC),
                )
            ]
            assert [
                (
                    row.id,
                    row.tenant_id,
                    row.source,
                    row.source_event_id,
                    row.event_type,
                    row.status,
                    row.payload,
                )
                for row in inbox_events
            ] == [
                (
                    "inbox_1",
                    "tenant_1",
                    "slack",
                    "Ev123",
                    "message",
                    "processed",
                    {"event": {"type": "message"}},
                )
            ]
        finally:
            await engine.dispose()


class StaticLegacyReader:
    def __init__(self, rows: list[LegacyRow]) -> None:
        self._rows = rows

    async def read(self):
        for row in self._rows:
            yield row


def postgres_container() -> PostgresContainer:
    return PostgresContainer(
        image="pgvector/pgvector:0.8.3-pg18-trixie",
        username="reactor",
        password="reactor",  # noqa: S106 - ephemeral Docker test credential
        dbname="reactor",
    )


def migrate_postgres(sync_url: str) -> None:
    previous_url = os.environ.get("REACTOR_DATABASE_URL")
    os.environ["REACTOR_DATABASE_URL"] = sync_url
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        if previous_url is None:
            os.environ.pop("REACTOR_DATABASE_URL", None)
        else:
            os.environ["REACTOR_DATABASE_URL"] = previous_url
        get_settings.cache_clear()
