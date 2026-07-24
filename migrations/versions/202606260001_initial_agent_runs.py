from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "202606260001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "checkpoint_migrations",
        sa.Column("v", sa.Integer(), primary_key=True),
    )
    op.bulk_insert(
        sa.table("checkpoint_migrations", sa.column("v", sa.Integer())),
        [{"v": version} for version in range(10)],
    )
    op.create_table(
        "checkpoints",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), nullable=False, server_default=""),
        sa.Column("checkpoint_id", sa.Text(), nullable=False),
        sa.Column("parent_checkpoint_id", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("checkpoint", postgresql.JSONB(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "checkpoint_id"),
    )
    op.create_index("checkpoints_thread_id_idx", "checkpoints", ["thread_id"])
    op.create_table(
        "checkpoint_blobs",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), nullable=False, server_default=""),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("blob", postgresql.BYTEA(), nullable=True),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "channel", "version"),
    )
    op.create_index("checkpoint_blobs_thread_id_idx", "checkpoint_blobs", ["thread_id"])
    op.create_table(
        "checkpoint_writes",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("checkpoint_ns", sa.Text(), nullable=False, server_default=""),
        sa.Column("checkpoint_id", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("task_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("blob", postgresql.BYTEA(), nullable=False),
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx"),
    )
    op.create_index("checkpoint_writes_thread_id_idx", "checkpoint_writes", ["thread_id"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("thread_id", sa.String(length=128), nullable=False),
        sa.Column("checkpoint_ns", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status in ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_agent_runs_status",
        ),
    )
    op.create_index("ix_agent_runs_tenant_created", "agent_runs", ["tenant_id", "created_at"])
    op.create_index("ix_agent_runs_thread", "agent_runs", ["thread_id", "checkpoint_ns"])

    op.create_table(
        "agent_run_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_agent_run_events_sequence"),
    )
    op.create_index("ix_agent_run_events_run", "agent_run_events", ["run_id", "sequence"])
    op.create_index(
        "ix_agent_run_events_tenant_created", "agent_run_events", ["tenant_id", "created_at"]
    )

    op.create_table(
        "run_queue",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status in ('queued', 'leased', 'completed', 'retryable_failed', "
            "'dead_lettered', 'cancelled')",
            name="ck_run_queue_status",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_run_queue_claim", "run_queue", ["tenant_id", "status", "available_at", "priority"]
    )
    op.create_index("ix_run_queue_lease", "run_queue", ["lease_expires_at", "fencing_token"])

    op.create_table(
        "dead_letter_jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("queue_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=128), nullable=False),
        sa.Column("last_checkpoint_id", sa.String(length=128), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column(
            "payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["queue_id"], ["run_queue.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_dead_letter_jobs_tenant_created", "dead_letter_jobs", ["tenant_id", "created_at"]
    )

    op.create_table(
        "idempotency_records",
        sa.Column("key", sa.String(length=256), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("request_checksum", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("response_payload", postgresql.JSONB(), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status in ('started', 'completed', 'failed', 'expired')",
            name="ck_idempotency_records_status",
        ),
    )
    op.create_index(
        "ix_idempotency_records_tenant_scope", "idempotency_records", ["tenant_id", "scope"]
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("destination", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status in ('pending', 'dispatching', 'dispatched', "
            "'retryable_failed', 'dead_lettered')",
            name="ck_outbox_events_status",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_outbox_events_idempotency"),
    )
    op.create_index(
        "ix_outbox_events_claim", "outbox_events", ["tenant_id", "status", "available_at"]
    )

    op.create_table(
        "inbox_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("source_event_id", sa.String(length=256), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('received', 'processing', 'processed', 'ignored', 'failed')",
            name="ck_inbox_events_status",
        ),
        sa.UniqueConstraint(
            "tenant_id", "source", "source_event_id", name="uq_inbox_events_source_event"
        ),
    )
    op.create_index(
        "ix_inbox_events_tenant_status", "inbox_events", ["tenant_id", "status", "received_at"]
    )

    op.create_table(
        "tool_catalog",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("namespace", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("input_schema", postgresql.JSONB(), nullable=False),
        sa.Column("output_schema", postgresql.JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "requires_approval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("timeout_ms", sa.Integer(), nullable=False, server_default="15000"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "risk_level in ('read', 'write', 'external_side_effect', 'destructive')",
            name="ck_tool_catalog_risk_level",
        ),
        sa.UniqueConstraint("tenant_id", "namespace", "name", name="uq_tool_catalog_name"),
    )
    op.create_index("ix_tool_catalog_tenant_enabled", "tool_catalog", ["tenant_id", "enabled"])

    op.create_table(
        "pending_approvals",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("tool_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column(
            "request_payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('pending', 'approved', 'rejected', 'expired', 'cancelled')",
            name="ck_pending_approvals_status",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tool_id"], ["tool_catalog.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_pending_approvals_tenant_status",
        "pending_approvals",
        ["tenant_id", "status", "created_at"],
    )

    op.create_table(
        "tool_invocations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("tool_id", sa.String(length=64), nullable=False),
        sa.Column("approval_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("request_checksum", sa.String(length=128), nullable=False),
        sa.Column("result_checksum", sa.String(length=128), nullable=True),
        sa.Column(
            "input_payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("output_payload", postgresql.JSONB(), nullable=True),
        sa.Column("error_payload", postgresql.JSONB(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('started', 'succeeded', 'failed', 'requires_reconciliation', 'cancelled')",
            name="ck_tool_invocations_status",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tool_id"], ["tool_catalog.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approval_id"], ["pending_approvals.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_tool_invocations_idempotency"),
    )
    op.create_index("ix_tool_invocations_run", "tool_invocations", ["run_id", "started_at"])

    op.create_table(
        "input_guard_rules",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("pattern_type", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="custom"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "pattern_type in ('regex', 'keyword')",
            name="ck_input_guard_rules_pattern",
        ),
        sa.CheckConstraint(
            "action in ('block', 'warn', 'flag')",
            name="ck_input_guard_rules_action",
        ),
    )
    op.create_index(
        "ix_input_guard_rules_tenant_enabled",
        "input_guard_rules",
        ["tenant_id", "enabled", "priority"],
    )

    op.create_table(
        "intent_definitions",
        sa.Column("name", sa.String(length=128), primary_key=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("examples", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("keywords", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("profile", sa.String(length=128), nullable=False, server_default="default"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_intent_definitions_enabled",
        "intent_definitions",
        ["enabled", "name"],
    )

    op.create_table(
        "agent_specs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("tool_names", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("keywords", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="REACT"),
        sa.Column(
            "independent_execution",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "mode in ('REACT', 'STANDARD', 'PLAN_EXECUTE')",
            name="ck_agent_specs_mode",
        ),
        sa.UniqueConstraint("name", name="uq_agent_specs_name"),
    )
    op.create_index(
        "ix_agent_specs_enabled",
        "agent_specs",
        ["enabled", "created_at"],
    )

    op.create_table(
        "personas",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("response_guideline", sa.Text(), nullable=True),
        sa.Column("welcome_message", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("prompt_template_id", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_personas_active_created",
        "personas",
        ["is_active", "created_at"],
    )
    op.create_index(
        "idx_personas_single_default",
        "personas",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default IS TRUE"),
    )

    op.create_table(
        "output_guard_rules",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column(
            "replacement",
            sa.String(length=256),
            nullable=False,
            server_default="[REDACTED]",
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "action in ('MASK', 'REJECT')",
            name="ck_output_guard_rules_action",
        ),
    )
    op.create_index(
        "ix_output_guard_rules_tenant_enabled",
        "output_guard_rules",
        ["tenant_id", "enabled", "priority", "created_at"],
    )

    op.create_table(
        "output_guard_rule_audits",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "action in ('CREATE', 'UPDATE', 'DELETE', 'SIMULATE')",
            name="ck_output_guard_rule_audits_action",
        ),
    )
    op.create_index(
        "ix_output_guard_rule_audits_tenant_created",
        "output_guard_rule_audits",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_output_guard_rule_audits_rule_id",
        "output_guard_rule_audits",
        ["rule_id"],
    )

    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("transport", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("command", sa.Text(), nullable=True),
        sa.Column(
            "args", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("auth_type", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("timeout_ms", sa.Integer(), nullable=False, server_default="15000"),
        sa.Column("protocol_version", sa.String(length=32), nullable=True),
        sa.Column("last_connection_error", sa.Text(), nullable=True),
        sa.Column(
            "reconnect_policy",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("tool_snapshot_hash", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "transport in ('stdio', 'streamable_http')",
            name="ck_mcp_servers_transport",
        ),
        sa.CheckConstraint(
            "status in ('registered', 'healthy', 'degraded', 'disabled')",
            name="ck_mcp_servers_status",
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_mcp_servers_name"),
    )
    op.create_index("ix_mcp_servers_tenant_status", "mcp_servers", ["tenant_id", "status"])

    op.create_table(
        "mcp_server_status",
        sa.Column("server_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("negotiated_protocol_version", sa.String(length=32), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("reconnect_attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("backoff_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "checked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "mcp_tool_snapshots",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("server_id", sa.String(length=64), nullable=False),
        sa.Column("qualified_name", sa.String(length=257), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "input_schema",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "output_schema",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("snapshot_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "risk_level in ('read', 'write', 'external_side_effect', 'destructive')",
            name="ck_mcp_tool_snapshots_risk_level",
        ),
        sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("server_id", "tool_name", name="uq_mcp_tool_snapshots_tool"),
    )
    op.create_index(
        "ix_mcp_tool_snapshots_tenant_enabled",
        "mcp_tool_snapshots",
        ["tenant_id", "enabled"],
    )

    op.create_table(
        "mcp_access_policies",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("server_id", sa.String(length=64), nullable=False),
        sa.Column("graph_profile", sa.String(length=128), nullable=False),
        sa.Column("allow_write", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "allowed_tools",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "server_id", "graph_profile", name="uq_mcp_access_policy"),
    )
    op.create_index(
        "ix_mcp_access_policies_tenant",
        "mcp_access_policies",
        ["tenant_id", "graph_profile"],
    )

    op.create_table(
        "a2a_peer_agents",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("endpoint_url", sa.Text(), nullable=False),
        sa.Column(
            "agent_card",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_a2a_peer_agents_name"),
    )
    op.create_index(
        "ix_a2a_peer_agents_tenant_enabled",
        "a2a_peer_agents",
        ["tenant_id", "enabled"],
    )

    op.create_table(
        "a2a_agent_cards",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("protocol_version", sa.String(length=16), nullable=False),
        sa.Column(
            "card",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "version", name="uq_a2a_agent_cards_version"),
    )
    op.create_index(
        "ix_a2a_agent_cards_tenant_active",
        "a2a_agent_cards",
        ["tenant_id", "active"],
    )

    op.create_table(
        "a2a_tasks",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("peer_agent_id", sa.String(length=64), nullable=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("thread_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("context_id", sa.String(length=128), nullable=False),
        sa.Column("message_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column(
            "input_payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("output_payload", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status in ('submitted', 'working', 'input_required', 'completed', "
            "'failed', 'cancelled')",
            name="ck_a2a_tasks_status",
        ),
        sa.ForeignKeyConstraint(["peer_agent_id"], ["a2a_peer_agents.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_a2a_tasks_idempotency"),
    )
    op.create_index(
        "ix_a2a_tasks_tenant_status",
        "a2a_tasks",
        ["tenant_id", "status", "created_at"],
    )
    op.create_index("ix_a2a_tasks_run", "a2a_tasks", ["run_id"])

    op.create_table(
        "a2a_task_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["task_id"], ["a2a_tasks.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("task_id", "sequence", name="uq_a2a_task_events_sequence"),
    )
    op.create_index("ix_a2a_task_events_task", "a2a_task_events", ["task_id", "sequence"])
    op.create_index(
        "ix_a2a_task_events_tenant_created",
        "a2a_task_events",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "a2a_push_subscriptions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("destination", sa.String(length=256), nullable=False),
        sa.Column("signing_key_ref", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "tenant_id", "destination", name="uq_a2a_push_subscriptions_destination"
        ),
    )
    op.create_index(
        "ix_a2a_push_subscriptions_tenant_enabled",
        "a2a_push_subscriptions",
        ["tenant_id", "enabled"],
    )

    op.create_table(
        "a2a_access_policies",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("peer_agent_id", sa.String(length=64), nullable=True),
        sa.Column("allow_inbound", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("allow_outbound", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "allowed_skills",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["peer_agent_id"], ["a2a_peer_agents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "peer_agent_id", name="uq_a2a_access_policy"),
    )
    op.create_index("ix_a2a_access_policies_tenant", "a2a_access_policies", ["tenant_id"])

    op.create_table(
        "rag_sources",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("collection", sa.String(length=128), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "source_uri", name="uq_rag_sources_uri"),
    )
    op.create_index("ix_rag_sources_tenant", "rag_sources", ["tenant_id", "collection"])

    op.create_table(
        "rag_documents",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("collection", sa.String(length=128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("acl", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["source_id"], ["rag_sources.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "source_id", "version", name="uq_rag_documents_version"),
    )
    op.create_index(
        "ix_rag_documents_tenant_collection",
        "rag_documents",
        ["tenant_id", "collection"],
    )

    op.create_table(
        "rag_chunks",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("collection", sa.String(length=128), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["document_id"], ["rag_documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_rag_chunks_document_index"),
    )
    op.create_index(
        "ix_rag_chunks_tenant_collection",
        "rag_chunks",
        ["tenant_id", "collection"],
    )

    op.create_table(
        "rag_ingestion_candidates",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=120), nullable=False),
        sa.Column("user_id", sa.String(length=120), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("channel", sa.String(length=120), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(length=120), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("ingested_document_id", sa.String(length=120), nullable=True),
        sa.CheckConstraint(
            "status in ('PENDING', 'REJECTED', 'INGESTED')",
            name="ck_rag_ingestion_candidates_status",
        ),
        sa.UniqueConstraint("run_id", name="uq_rag_ingestion_candidates_run"),
    )
    op.create_index(
        "idx_rag_ingestion_candidates_status_captured_at",
        "rag_ingestion_candidates",
        ["status", "captured_at"],
    )
    op.create_index(
        "idx_rag_ingestion_candidates_channel",
        "rag_ingestion_candidates",
        ["channel"],
    )

    op.create_table(
        "memory_namespaces",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("subject_type", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("memory_type", sa.String(length=64), nullable=False),
        sa.Column("visibility", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "subject_type",
            "subject_id",
            "memory_type",
            "visibility",
            name="uq_memory_namespaces_identity",
        ),
    )
    op.create_index(
        "ix_memory_namespaces_tenant",
        "memory_namespaces",
        ["tenant_id", "subject_type", "subject_id"],
    )

    op.create_table(
        "memory_items",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("namespace_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status in ('active', 'superseded', 'tombstoned')",
            name="ck_memory_items_status",
        ),
        sa.ForeignKeyConstraint(["namespace_id"], ["memory_namespaces.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_memory_items_namespace_status",
        "memory_items",
        ["namespace_id", "status"],
    )

    op.create_table(
        "memory_embeddings",
        sa.Column("memory_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["memory_id"], ["memory_items.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_memory_embeddings_tenant", "memory_embeddings", ["tenant_id"])

    op.create_table(
        "memory_proposals",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("namespace_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("proposed_content", sa.Text(), nullable=False),
        sa.Column("extraction_model", sa.String(length=128), nullable=False),
        sa.Column("extraction_prompt_version", sa.String(length=128), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "source_payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status in ('proposed', 'approved', 'rejected', 'expired')",
            name="ck_memory_proposals_status",
        ),
        sa.ForeignKeyConstraint(["namespace_id"], ["memory_namespaces.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_memory_proposals_tenant_status",
        "memory_proposals",
        ["tenant_id", "status"],
    )

    op.create_table(
        "runtime_settings",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("key", sa.String(length=256), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False, server_default="STRING"),
        sa.Column("category", sa.String(length=128), nullable=False, server_default="general"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(length=128), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "key", name="uq_runtime_settings_key"),
    )
    op.create_index(
        "ix_runtime_settings_tenant_category",
        "runtime_settings",
        ["tenant_id", "category"],
    )

    op.create_table(
        "admin_audits",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=256), nullable=False),
        sa.Column("resource_type", sa.String(length=128), nullable=True),
        sa.Column("resource_id", sa.String(length=256), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_admin_audits_tenant_created",
        "admin_audits",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_admin_audits_category_action",
        "admin_audits",
        ["tenant_id", "category", "action", "created_at"],
    )

    op.create_table(
        "feedback",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("rating", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="slack_button"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("run_id", sa.String(length=128), nullable=True),
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("review_status", sa.String(length=32), nullable=False, server_default="inbox"),
        sa.Column("review_tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("reviewed_by", sa.String(length=128), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "rating in ('THUMBS_UP', 'THUMBS_DOWN')",
            name="ck_feedback_rating",
        ),
        sa.CheckConstraint(
            "review_status in ('inbox', 'done')",
            name="ck_feedback_review_status",
        ),
    )
    op.create_index("ix_feedback_tenant_created", "feedback", ["tenant_id", "created_at"])
    op.create_index("ix_feedback_tenant_rating", "feedback", ["tenant_id", "rating", "created_at"])
    op.create_index(
        "ix_feedback_review_status",
        "feedback",
        ["tenant_id", "review_status", "created_at"],
    )

    op.create_table(
        "slack_bot_instances",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("bot_token", sa.Text(), nullable=False),
        sa.Column("app_token", sa.Text(), nullable=False),
        sa.Column("persona_id", sa.String(length=128), nullable=False),
        sa.Column("default_channel", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_slack_bot_instances_name"),
    )
    op.create_index(
        "ix_slack_bot_instances_tenant_enabled",
        "slack_bot_instances",
        ["tenant_id", "enabled", "created_at"],
    )
    op.create_table(
        "slack_proactive_channels",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("channel_id", sa.String(length=50), nullable=False),
        sa.Column("channel_name", sa.String(length=200), nullable=True),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "channel_id", name="uq_slack_proactive_channels_id"),
    )
    op.create_index(
        "ix_slack_proactive_channels_tenant_added",
        "slack_proactive_channels",
        ["tenant_id", "added_at"],
    )
    op.create_table(
        "channel_faq_registrations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("channel_id", sa.String(length=64), nullable=False),
        sa.Column("channel_name", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "auto_reply_mode",
            sa.String(length=16),
            nullable=False,
            server_default="mention",
        ),
        sa.Column(
            "confidence_threshold",
            sa.Float(),
            nullable=False,
            server_default="0.75",
        ),
        sa.Column("days_back", sa.Integer(), nullable=False, server_default="30"),
        sa.Column(
            "re_ingest_interval_hours",
            sa.Integer(),
            nullable=False,
            server_default="24",
        ),
        sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_count", sa.Integer(), nullable=True),
        sa.Column("last_chunk_count", sa.Integer(), nullable=True),
        sa.Column("last_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("registered_by", sa.String(length=128), nullable=True),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "confidence_threshold >= 0 and confidence_threshold <= 1",
            name="ck_channel_faq_registrations_threshold",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "channel_id",
            name="uq_channel_faq_registrations_tenant_channel",
        ),
    )
    op.create_index(
        "ix_channel_faq_registrations_due",
        "channel_faq_registrations",
        ["tenant_id", "enabled", "last_ingested_at", "channel_id"],
    )

    op.create_table(
        "agent_eval_cases",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("user_input", sa.Text(), nullable=False),
        sa.Column(
            "expected_answer_contains",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "forbidden_answer_contains",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "expected_tool_names",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "forbidden_tool_names",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "expected_exposed_tool_names",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "forbidden_exposed_tool_names",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("max_tool_exposure_count", sa.Integer(), nullable=True),
        sa.Column("agent_type", sa.String(length=255), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "tags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("min_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("source_run_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "min_score >= 0 and min_score <= 1",
            name="ck_agent_eval_cases_score",
        ),
    )
    op.create_index(
        "ix_agent_eval_cases_tenant_enabled",
        "agent_eval_cases",
        ["tenant_id", "enabled", "updated_at"],
    )
    op.create_index(
        "ix_agent_eval_cases_source_run",
        "agent_eval_cases",
        ["tenant_id", "source_run_id"],
    )

    op.create_table(
        "agent_eval_results",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=True),
        sa.Column("tier", sa.String(length=64), nullable=False, server_default="deterministic"),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "reasons",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "score >= 0 and score <= 1",
            name="ck_agent_eval_results_score",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["agent_eval_cases.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_agent_eval_results_case",
        "agent_eval_results",
        ["tenant_id", "case_id", "evaluated_at"],
    )
    op.create_index(
        "ix_agent_eval_results_tier",
        "agent_eval_results",
        ["tenant_id", "tier", "evaluated_at"],
    )

    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cron_expression", sa.String(length=128), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Asia/Seoul"),
        sa.Column("job_type", sa.String(length=32), nullable=False, server_default="MCP_TOOL"),
        sa.Column("mcp_server_name", sa.String(length=128), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=True),
        sa.Column(
            "tool_arguments",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("agent_prompt", sa.Text(), nullable=True),
        sa.Column("persona_id", sa.String(length=128), nullable=True),
        sa.Column("agent_system_prompt", sa.Text(), nullable=True),
        sa.Column("agent_model", sa.String(length=128), nullable=True),
        sa.Column("agent_max_tool_calls", sa.Integer(), nullable=True),
        sa.Column("tags", sa.String(length=1000), nullable=True),
        sa.Column("slack_channel_id", sa.String(length=128), nullable=True),
        sa.Column("teams_webhook_url", sa.String(length=500), nullable=True),
        sa.Column("retry_on_failure", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_retry_count", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("execution_timeout_ms", sa.BigInteger(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=32), nullable=True),
        sa.Column("last_result", sa.Text(), nullable=True),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "job_type in ('MCP_TOOL', 'AGENT', 'PROMPT_LAB_AUTO_OPTIMIZE')",
            name="ck_scheduled_jobs_type",
        ),
        sa.CheckConstraint(
            "last_status is null or last_status in ('SUCCESS', 'FAILED', 'RUNNING', 'SKIPPED')",
            name="ck_scheduled_jobs_last_status",
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_scheduled_jobs_name"),
    )
    op.create_index(
        "ix_scheduled_jobs_tenant_enabled",
        "scheduled_jobs",
        ["tenant_id", "enabled", "created_at"],
    )
    op.create_index(
        "ix_scheduled_jobs_lease",
        "scheduled_jobs",
        ["tenant_id", "lease_expires_at", "fencing_token"],
    )

    op.create_table(
        "scheduled_job_executions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("job_name", sa.String(length=200), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('SUCCESS', 'FAILED', 'RUNNING', 'SKIPPED')",
            name="ck_scheduled_job_executions_status",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["scheduled_jobs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_scheduled_job_executions_job",
        "scheduled_job_executions",
        ["tenant_id", "job_id", "started_at"],
    )
    op.create_index(
        "ix_scheduled_job_executions_recent",
        "scheduled_job_executions",
        ["tenant_id", "started_at"],
    )

    op.create_table(
        "scheduled_job_dead_letters",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("job_name", sa.String(length=200), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["job_id"], ["scheduled_jobs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_scheduled_job_dead_letters_job",
        "scheduled_job_dead_letters",
        ["tenant_id", "job_id", "created_at"],
    )
    op.create_index(
        "ix_scheduled_job_dead_letters_recent",
        "scheduled_job_dead_letters",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("plan", sa.String(length=20), nullable=False, server_default="FREE"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("max_requests_per_month", sa.BigInteger(), nullable=False, server_default="1000"),
        sa.Column(
            "max_tokens_per_month", sa.BigInteger(), nullable=False, server_default="1000000"
        ),
        sa.Column("max_users", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("max_agents", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("max_mcp_servers", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("billing_cycle_start", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("billing_email", sa.String(length=255), nullable=True),
        sa.Column("slo_availability", sa.Float(), nullable=False, server_default="0.995"),
        sa.Column("slo_latency_p99_ms", sa.BigInteger(), nullable=False, server_default="10000"),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "plan in ('FREE', 'STARTER', 'BUSINESS', 'ENTERPRISE')",
            name="ck_tenants_plan",
        ),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'SUSPENDED', 'DEACTIVATED')",
            name="ck_tenants_status",
        ),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"])
    op.create_index("ix_tenants_status", "tenants", ["status"])

    op.create_table(
        "model_pricing",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column(
            "prompt_price_per_1m",
            sa.Numeric(18, 8),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "completion_price_per_1m",
            sa.Numeric(18, 8),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "cached_input_price_per_1m",
            sa.Numeric(18, 8),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "reasoning_price_per_1m",
            sa.Numeric(18, 8),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "batch_prompt_price_per_1m",
            sa.Numeric(18, 8),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "batch_completion_price_per_1m",
            sa.Numeric(18, 8),
            nullable=False,
            server_default="0",
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_model_pricing_effective",
        "model_pricing",
        ["provider", "model", "effective_from"],
    )

    op.create_table(
        "usage_ledger",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("step_type", sa.String(length=64), nullable=False),
        sa.Column("prompt_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cached_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reasoning_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(18, 8),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_usage_ledger_tenant_occurred",
        "usage_ledger",
        ["tenant_id", "occurred_at"],
    )
    op.create_index(
        "ix_usage_ledger_tenant_run",
        "usage_ledger",
        ["tenant_id", "run_id"],
    )

    op.create_table(
        "alert_rules",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("metric", sa.String(length=128), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False, server_default="0"),
        sa.Column("window_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("platform_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "type in ('STATIC_THRESHOLD', 'BASELINE_ANOMALY', 'ERROR_BUDGET_BURN_RATE')",
            name="ck_alert_rules_type",
        ),
        sa.CheckConstraint(
            "severity in ('INFO', 'WARNING', 'CRITICAL')",
            name="ck_alert_rules_severity",
        ),
    )
    op.create_index(
        "ix_alert_rules_tenant_enabled",
        "alert_rules",
        ["tenant_id", "enabled", "created_at"],
    )

    op.create_table(
        "alert_instances",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("threshold", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "fired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "severity in ('INFO', 'WARNING', 'CRITICAL')",
            name="ck_alert_instances_severity",
        ),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'ACKNOWLEDGED', 'RESOLVED')",
            name="ck_alert_instances_status",
        ),
        sa.ForeignKeyConstraint(["rule_id"], ["alert_rules.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_alert_instances_status", "alert_instances", ["status", "fired_at"])
    op.create_index(
        "ix_alert_instances_rule_status",
        "alert_instances",
        ["rule_id", "status"],
    )
    op.create_index(
        "ix_alert_instances_tenant_status",
        "alert_instances",
        ["tenant_id", "status", "fired_at"],
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False, server_default="default"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "user_identities",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("external_subject", sa.String(length=256), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            "external_subject",
            name="uq_user_identities_external_subject",
        ),
    )
    op.create_index(
        "ix_user_identities_user",
        "user_identities",
        ["tenant_id", "user_id"],
    )

    op.create_table(
        "auth_token_revocations",
        sa.Column("token_id", sa.String(length=256), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "revoked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("graph_profile", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_prompt_templates_name"),
    )
    op.create_index(
        "ix_prompt_templates_tenant_graph",
        "prompt_templates",
        ["tenant_id", "graph_profile"],
    )

    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("template_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("system_policy", sa.Text(), nullable=False),
        sa.Column("developer_policy", sa.Text(), nullable=False, server_default=""),
        sa.Column("examples", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["template_id"], ["prompt_templates.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("template_id", "version", name="uq_prompt_versions_version"),
    )
    op.create_index(
        "ix_prompt_versions_tenant_created",
        "prompt_versions",
        ["tenant_id", "created_at"],
    )
    op.create_index("ix_prompt_versions_content_hash", "prompt_versions", ["content_hash"])

    op.create_table(
        "prompt_releases",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("template_id", sa.String(length=64), nullable=False),
        sa.Column("version_id", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("released_by", sa.String(length=128), nullable=False),
        sa.Column(
            "released_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.ForeignKeyConstraint(["template_id"], ["prompt_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["prompt_versions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id",
            "template_id",
            "environment",
            name="uq_prompt_releases_environment",
        ),
    )
    op.create_index(
        "ix_prompt_releases_tenant_environment",
        "prompt_releases",
        ["tenant_id", "environment"],
    )

    op.create_table(
        "migration_imports",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("batch_id", sa.String(length=128), nullable=False),
        sa.Column("source_table", sa.String(length=128), nullable=False),
        sa.Column("source_pk", sa.String(length=256), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "batch_id",
            "source_table",
            "source_pk",
            "checksum",
            name="uq_migration_imports_source",
        ),
    )
    op.create_index(
        "ix_migration_imports_batch_table",
        "migration_imports",
        ["batch_id", "source_table", "source_pk"],
    )

    op.create_table(
        "migration_rollback_snapshots",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("batch_id", sa.String(length=128), nullable=False),
        sa.Column("target_table", sa.String(length=128), nullable=False),
        sa.Column("target_pk", sa.String(length=256), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "batch_id",
            "target_table",
            "target_pk",
            "checksum",
            name="uq_migration_rollback_snapshots_target",
        ),
    )
    op.create_index(
        "ix_migration_rollback_snapshots_batch_table",
        "migration_rollback_snapshots",
        ["batch_id", "target_table", "target_pk"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_migration_rollback_snapshots_batch_table",
        table_name="migration_rollback_snapshots",
    )
    op.drop_table("migration_rollback_snapshots")
    op.drop_index("ix_migration_imports_batch_table", table_name="migration_imports")
    op.drop_table("migration_imports")
    op.drop_index(
        "ix_prompt_releases_tenant_environment",
        table_name="prompt_releases",
    )
    op.drop_table("prompt_releases")
    op.drop_index("ix_prompt_versions_content_hash", table_name="prompt_versions")
    op.drop_index("ix_prompt_versions_tenant_created", table_name="prompt_versions")
    op.drop_table("prompt_versions")
    op.drop_index("ix_prompt_templates_tenant_graph", table_name="prompt_templates")
    op.drop_table("prompt_templates")
    op.drop_table("auth_token_revocations")
    op.drop_index("ix_user_identities_user", table_name="user_identities")
    op.drop_table("user_identities")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_usage_ledger_tenant_run", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_tenant_occurred", table_name="usage_ledger")
    op.drop_table("usage_ledger")
    op.drop_index("ix_model_pricing_effective", table_name="model_pricing")
    op.drop_table("model_pricing")
    op.drop_index("ix_tenants_status", table_name="tenants")
    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")
    op.drop_index("ix_alert_instances_tenant_status", table_name="alert_instances")
    op.drop_index("ix_alert_instances_rule_status", table_name="alert_instances")
    op.drop_index("ix_alert_instances_status", table_name="alert_instances")
    op.drop_table("alert_instances")
    op.drop_index("ix_alert_rules_tenant_enabled", table_name="alert_rules")
    op.drop_table("alert_rules")
    op.drop_index(
        "ix_scheduled_job_dead_letters_recent",
        table_name="scheduled_job_dead_letters",
    )
    op.drop_index(
        "ix_scheduled_job_dead_letters_job",
        table_name="scheduled_job_dead_letters",
    )
    op.drop_table("scheduled_job_dead_letters")
    op.drop_index(
        "ix_scheduled_job_executions_recent",
        table_name="scheduled_job_executions",
    )
    op.drop_index("ix_scheduled_job_executions_job", table_name="scheduled_job_executions")
    op.drop_table("scheduled_job_executions")
    op.drop_index("ix_scheduled_jobs_lease", table_name="scheduled_jobs")
    op.drop_index("ix_scheduled_jobs_tenant_enabled", table_name="scheduled_jobs")
    op.drop_table("scheduled_jobs")
    op.drop_index("ix_agent_eval_results_tier", table_name="agent_eval_results")
    op.drop_index("ix_agent_eval_results_case", table_name="agent_eval_results")
    op.drop_table("agent_eval_results")
    op.drop_index("ix_agent_eval_cases_source_run", table_name="agent_eval_cases")
    op.drop_index("ix_agent_eval_cases_tenant_enabled", table_name="agent_eval_cases")
    op.drop_table("agent_eval_cases")
    op.drop_index(
        "ix_channel_faq_registrations_due",
        table_name="channel_faq_registrations",
    )
    op.drop_table("channel_faq_registrations")
    op.drop_index(
        "ix_slack_proactive_channels_tenant_added",
        table_name="slack_proactive_channels",
    )
    op.drop_table("slack_proactive_channels")
    op.drop_index(
        "ix_slack_bot_instances_tenant_enabled",
        table_name="slack_bot_instances",
    )
    op.drop_table("slack_bot_instances")
    op.drop_index("ix_feedback_review_status", table_name="feedback")
    op.drop_index("ix_feedback_tenant_rating", table_name="feedback")
    op.drop_index("ix_feedback_tenant_created", table_name="feedback")
    op.drop_table("feedback")
    op.drop_index("ix_admin_audits_category_action", table_name="admin_audits")
    op.drop_index("ix_admin_audits_tenant_created", table_name="admin_audits")
    op.drop_table("admin_audits")
    op.drop_index("ix_runtime_settings_tenant_category", table_name="runtime_settings")
    op.drop_table("runtime_settings")
    op.drop_index("ix_memory_proposals_tenant_status", table_name="memory_proposals")
    op.drop_table("memory_proposals")
    op.drop_index("ix_memory_embeddings_tenant", table_name="memory_embeddings")
    op.drop_table("memory_embeddings")
    op.drop_index("ix_memory_items_namespace_status", table_name="memory_items")
    op.drop_table("memory_items")
    op.drop_index("ix_memory_namespaces_tenant", table_name="memory_namespaces")
    op.drop_table("memory_namespaces")
    op.drop_index(
        "idx_rag_ingestion_candidates_channel",
        table_name="rag_ingestion_candidates",
    )
    op.drop_index(
        "idx_rag_ingestion_candidates_status_captured_at",
        table_name="rag_ingestion_candidates",
    )
    op.drop_table("rag_ingestion_candidates")
    op.drop_index("ix_rag_chunks_tenant_collection", table_name="rag_chunks")
    op.drop_table("rag_chunks")
    op.drop_index("ix_rag_documents_tenant_collection", table_name="rag_documents")
    op.drop_table("rag_documents")
    op.drop_index("ix_rag_sources_tenant", table_name="rag_sources")
    op.drop_table("rag_sources")
    op.drop_index("ix_a2a_access_policies_tenant", table_name="a2a_access_policies")
    op.drop_table("a2a_access_policies")
    op.drop_index("ix_a2a_push_subscriptions_tenant_enabled", table_name="a2a_push_subscriptions")
    op.drop_table("a2a_push_subscriptions")
    op.drop_index("ix_a2a_task_events_tenant_created", table_name="a2a_task_events")
    op.drop_index("ix_a2a_task_events_task", table_name="a2a_task_events")
    op.drop_table("a2a_task_events")
    op.drop_index("ix_a2a_tasks_run", table_name="a2a_tasks")
    op.drop_index("ix_a2a_tasks_tenant_status", table_name="a2a_tasks")
    op.drop_table("a2a_tasks")
    op.drop_index("ix_a2a_agent_cards_tenant_active", table_name="a2a_agent_cards")
    op.drop_table("a2a_agent_cards")
    op.drop_index("ix_a2a_peer_agents_tenant_enabled", table_name="a2a_peer_agents")
    op.drop_table("a2a_peer_agents")
    op.drop_index("ix_mcp_access_policies_tenant", table_name="mcp_access_policies")
    op.drop_table("mcp_access_policies")
    op.drop_index("ix_mcp_tool_snapshots_tenant_enabled", table_name="mcp_tool_snapshots")
    op.drop_table("mcp_tool_snapshots")
    op.drop_table("mcp_server_status")
    op.drop_index("ix_mcp_servers_tenant_status", table_name="mcp_servers")
    op.drop_table("mcp_servers")
    op.drop_index("ix_output_guard_rule_audits_rule_id", table_name="output_guard_rule_audits")
    op.drop_index(
        "ix_output_guard_rule_audits_tenant_created",
        table_name="output_guard_rule_audits",
    )
    op.drop_table("output_guard_rule_audits")
    op.drop_index("ix_output_guard_rules_tenant_enabled", table_name="output_guard_rules")
    op.drop_table("output_guard_rules")
    op.drop_index("ix_agent_specs_enabled", table_name="agent_specs")
    op.drop_table("agent_specs")
    op.drop_index("idx_personas_single_default", table_name="personas")
    op.drop_index("ix_personas_active_created", table_name="personas")
    op.drop_table("personas")
    op.drop_index("ix_intent_definitions_enabled", table_name="intent_definitions")
    op.drop_table("intent_definitions")
    op.drop_index("ix_input_guard_rules_tenant_enabled", table_name="input_guard_rules")
    op.drop_table("input_guard_rules")
    op.drop_index("ix_tool_invocations_run", table_name="tool_invocations")
    op.drop_table("tool_invocations")
    op.drop_index("ix_pending_approvals_tenant_status", table_name="pending_approvals")
    op.drop_table("pending_approvals")
    op.drop_index("ix_tool_catalog_tenant_enabled", table_name="tool_catalog")
    op.drop_table("tool_catalog")
    op.drop_index("ix_inbox_events_tenant_status", table_name="inbox_events")
    op.drop_table("inbox_events")
    op.drop_index("ix_outbox_events_claim", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index("ix_idempotency_records_tenant_scope", table_name="idempotency_records")
    op.drop_table("idempotency_records")
    op.drop_index("ix_dead_letter_jobs_tenant_created", table_name="dead_letter_jobs")
    op.drop_table("dead_letter_jobs")
    op.drop_index("ix_run_queue_lease", table_name="run_queue")
    op.drop_index("ix_run_queue_claim", table_name="run_queue")
    op.drop_table("run_queue")
    op.drop_index("ix_agent_run_events_tenant_created", table_name="agent_run_events")
    op.drop_index("ix_agent_run_events_run", table_name="agent_run_events")
    op.drop_table("agent_run_events")
    op.drop_index("ix_agent_runs_thread", table_name="agent_runs")
    op.drop_index("ix_agent_runs_tenant_created", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("checkpoint_writes_thread_id_idx", table_name="checkpoint_writes")
    op.drop_table("checkpoint_writes")
    op.drop_index("checkpoint_blobs_thread_id_idx", table_name="checkpoint_blobs")
    op.drop_table("checkpoint_blobs")
    op.drop_index("checkpoints_thread_id_idx", table_name="checkpoints")
    op.drop_table("checkpoints")
    op.drop_table("checkpoint_migrations")
