from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('queued', 'running', 'interrupted', 'completed', 'failed', 'cancelled')",
            name="ck_agent_runs_status",
        ),
        Index("ix_agent_runs_tenant_created", "tenant_id", "created_at"),
        Index("ix_agent_runs_thread", "thread_id", "checkpoint_ns"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False)
    checkpoint_ns: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    run_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    events: Mapped[list[AgentRunEvent]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class AgentRunEvent(Base):
    __tablename__ = "agent_run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_agent_run_events_sequence"),
        Index("ix_agent_run_events_run", "run_id", "sequence"),
        Index("ix_agent_run_events_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    run: Mapped[AgentRun] = relationship(back_populates="events")


class RunQueue(Base):
    __tablename__ = "run_queue"
    __table_args__ = (
        CheckConstraint(
            "status in ('queued', 'leased', 'completed', 'retryable_failed', "
            "'dead_lettered', 'cancelled')",
            name="ck_run_queue_status",
        ),
        Index("ix_run_queue_claim", "tenant_id", "status", "available_at", "priority"),
        Index("ix_run_queue_lease", "lease_expires_at", "fencing_token"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class DeadLetterJob(Base):
    __tablename__ = "dead_letter_jobs"
    __table_args__ = (Index("ix_dead_letter_jobs_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    queue_id: Mapped[str] = mapped_column(ForeignKey("run_queue.id", ondelete="CASCADE"))
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    last_checkpoint_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        CheckConstraint(
            "status in ('started', 'completed', 'failed', 'expired')",
            name="ck_idempotency_records_status",
        ),
        Index("ix_idempotency_records_tenant_scope", "tenant_id", "scope"),
    )

    key: Mapped[str] = mapped_column(String(256), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'dispatching', 'dispatched', "
            "'retryable_failed', 'dead_lettered')",
            name="ck_outbox_events_status",
        ),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_outbox_events_idempotency"),
        Index("ix_outbox_events_claim", "tenant_id", "status", "available_at"),
        Index("ix_outbox_events_lease", "tenant_id", "lease_expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"))
    destination: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class InboxEvent(Base):
    __tablename__ = "inbox_events"
    __table_args__ = (
        CheckConstraint(
            "status in ('received', 'processing', 'processed', 'ignored', 'failed')",
            name="ck_inbox_events_status",
        ),
        UniqueConstraint(
            "tenant_id", "source", "source_event_id", name="uq_inbox_events_source_event"
        ),
        Index("ix_inbox_events_tenant_status", "tenant_id", "status", "received_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(256), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ToolCatalog(Base):
    __tablename__ = "tool_catalog"
    __table_args__ = (
        CheckConstraint(
            "risk_level in ('read', 'write', 'external_side_effect', 'destructive')",
            name="ck_tool_catalog_risk_level",
        ),
        UniqueConstraint("tenant_id", "namespace", "name", name="uq_tool_catalog_name"),
        Index("ix_tool_catalog_tenant_enabled", "tenant_id", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=15000)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PendingApproval(Base):
    __tablename__ = "pending_approvals"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'approved', 'rejected', 'expired', 'cancelled')",
            name="ck_pending_approvals_status",
        ),
        Index("ix_pending_approvals_tenant_status", "tenant_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    tool_id: Mapped[str] = mapped_column(ForeignKey("tool_catalog.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ToolInvocation(Base):
    __tablename__ = "tool_invocations"
    __table_args__ = (
        CheckConstraint(
            "status in ('started', 'succeeded', 'failed', 'requires_reconciliation', 'cancelled')",
            name="ck_tool_invocations_status",
        ),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_tool_invocations_idempotency"),
        Index("ix_tool_invocations_run", "run_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    tool_id: Mapped[str] = mapped_column(ForeignKey("tool_catalog.id", ondelete="CASCADE"))
    approval_id: Mapped[str | None] = mapped_column(
        ForeignKey("pending_approvals.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    request_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    result_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InputGuardRule(Base):
    __tablename__ = "input_guard_rules"
    __table_args__ = (
        CheckConstraint(
            "pattern_type in ('regex', 'keyword')", name="ck_input_guard_rules_pattern"
        ),
        CheckConstraint("action in ('block', 'warn', 'flag')", name="ck_input_guard_rules_action"),
        Index("ix_input_guard_rules_tenant_enabled", "tenant_id", "enabled", "priority"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    pattern_type: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="custom")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class IntentDefinitionModel(Base):
    __tablename__ = "intent_definitions"
    __table_args__ = (Index("ix_intent_definitions_enabled", "enabled", "name"),)

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    examples: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    profile: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AgentSpecRow(Base):
    __tablename__ = "agent_specs"
    __table_args__ = (
        CheckConstraint(
            "mode in ('REACT', 'STANDARD', 'PLAN_EXECUTE')",
            name="ck_agent_specs_mode",
        ),
        UniqueConstraint("name", name="uq_agent_specs_name"),
        Index("ix_agent_specs_enabled", "enabled", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_names: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="REACT")
    independent_execution: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PersonaRow(Base):
    __tablename__ = "personas"
    __table_args__ = (Index("ix_personas_active_created", "is_active", "created_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_guideline: Mapped[str | None] = mapped_column(Text, nullable=True)
    welcome_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    prompt_template_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


Index(
    "idx_personas_single_default",
    PersonaRow.is_default,
    unique=True,
    postgresql_where=PersonaRow.is_default.is_(True),
)


class OutputGuardRule(Base):
    __tablename__ = "output_guard_rules"
    __table_args__ = (
        CheckConstraint("action in ('MASK', 'REJECT')", name="ck_output_guard_rules_action"),
        Index(
            "ix_output_guard_rules_tenant_enabled",
            "tenant_id",
            "enabled",
            "priority",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    replacement: Mapped[str] = mapped_column(String(256), nullable=False, default="[REDACTED]")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class OutputGuardRuleAudit(Base):
    __tablename__ = "output_guard_rule_audits"
    __table_args__ = (
        CheckConstraint(
            "action in ('CREATE', 'UPDATE', 'DELETE', 'SIMULATE')",
            name="ck_output_guard_rule_audits_action",
        ),
        Index("ix_output_guard_rule_audits_tenant_created", "tenant_id", "created_at"),
        Index("ix_output_guard_rule_audits_rule_id", "rule_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_prompt_templates_name"),
        Index("ix_prompt_templates_tenant_graph", "tenant_id", "graph_profile"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    graph_profile: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_prompt_versions_version"),
        Index("ix_prompt_versions_tenant_created", "tenant_id", "created_at"),
        Index("ix_prompt_versions_content_hash", "content_hash"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    template_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    system_policy: Mapped[str] = mapped_column(Text, nullable=False)
    developer_policy: Mapped[str] = mapped_column(Text, nullable=False, default="")
    examples: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    prompt_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PromptRelease(Base):
    __tablename__ = "prompt_releases"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "template_id",
            "environment",
            name="uq_prompt_releases_environment",
        ),
        Index("ix_prompt_releases_tenant_environment", "tenant_id", "environment"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    template_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="CASCADE"), nullable=False
    )
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    released_by: Mapped[str] = mapped_column(String(128), nullable=False)
    released_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    release_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )


class PromptLabExperiment(Base):
    __tablename__ = "prompt_lab_experiments"
    __table_args__ = (
        CheckConstraint(
            "status in ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_prompt_lab_experiments_status",
        ),
        Index("ix_prompt_lab_experiments_tenant_status", "tenant_id", "status", "created_at"),
        Index("ix_prompt_lab_experiments_template", "tenant_id", "template_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_version_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    test_queries: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    evaluation_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    judge_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    auto_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class PromptLabTrial(Base):
    __tablename__ = "prompt_lab_trials"
    __table_args__ = (
        Index("ix_prompt_lab_trials_experiment", "tenant_id", "experiment_id", "executed_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    experiment_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_lab_experiments.id", ondelete="CASCADE"), nullable=False
    )
    prompt_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    test_query: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    repetition_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    tools_used: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PromptLabReport(Base):
    __tablename__ = "prompt_lab_reports"
    __table_args__ = (Index("ix_prompt_lab_reports_tenant_generated", "tenant_id", "generated_at"),)

    experiment_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_lab_experiments.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    experiment_name: Mapped[str] = mapped_column(String(200), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    total_trials: Mapped[int] = mapped_column(Integer, nullable=False)
    version_summaries: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    recommendation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class McpServer(Base):
    __tablename__ = "mcp_servers"
    __table_args__ = (
        CheckConstraint(
            "transport in ('stdio', 'streamable_http')",
            name="ck_mcp_servers_transport",
        ),
        CheckConstraint(
            "status in ('registered', 'healthy', 'degraded', 'disabled')",
            name="ck_mcp_servers_status",
        ),
        UniqueConstraint("tenant_id", "name", name="uq_mcp_servers_name"),
        Index("ix_mcp_servers_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    transport: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    command: Mapped[str | None] = mapped_column(Text, nullable=True)
    args: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=15000)
    protocol_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_connection_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    reconnect_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    tool_snapshot_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class McpServerStatus(Base):
    __tablename__ = "mcp_server_status"

    server_id: Mapped[str] = mapped_column(
        ForeignKey("mcp_servers.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    negotiated_protocol_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    reconnect_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    backoff_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class McpToolSnapshot(Base):
    __tablename__ = "mcp_tool_snapshots"
    __table_args__ = (
        CheckConstraint(
            "risk_level in ('read', 'write', 'external_side_effect', 'destructive')",
            name="ck_mcp_tool_snapshots_risk_level",
        ),
        UniqueConstraint("server_id", "tool_name", name="uq_mcp_tool_snapshots_tool"),
        Index("ix_mcp_tool_snapshots_tenant_enabled", "tenant_id", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    server_id: Mapped[str] = mapped_column(ForeignKey("mcp_servers.id", ondelete="CASCADE"))
    qualified_name: Mapped[str] = mapped_column(String(257), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    snapshot_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class McpAccessPolicy(Base):
    __tablename__ = "mcp_access_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "server_id", "graph_profile", name="uq_mcp_access_policy"),
        Index("ix_mcp_access_policies_tenant", "tenant_id", "graph_profile"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    server_id: Mapped[str] = mapped_column(ForeignKey("mcp_servers.id", ondelete="CASCADE"))
    graph_profile: Mapped[str] = mapped_column(String(128), nullable=False)
    allow_write: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allowed_tools: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class A2APeerAgent(Base):
    __tablename__ = "a2a_peer_agents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_a2a_peer_agents_name"),
        Index("ix_a2a_peer_agents_tenant_enabled", "tenant_id", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(Text, nullable=False)
    agent_card: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class A2AAgentCard(Base):
    __tablename__ = "a2a_agent_cards"
    __table_args__ = (
        UniqueConstraint("tenant_id", "version", name="uq_a2a_agent_cards_version"),
        Index("ix_a2a_agent_cards_tenant_active", "tenant_id", "active"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    protocol_version: Mapped[str] = mapped_column(String(16), nullable=False)
    card: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class A2ATask(Base):
    __tablename__ = "a2a_tasks"
    __table_args__ = (
        CheckConstraint(
            "status in ('submitted', 'working', 'input_required', 'completed', "
            "'failed', 'cancelled')",
            name="ck_a2a_tasks_status",
        ),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_a2a_tasks_idempotency"),
        Index("ix_a2a_tasks_tenant_status", "tenant_id", "status", "created_at"),
        Index("ix_a2a_tasks_run", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    peer_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("a2a_peer_agents.id", ondelete="SET NULL"), nullable=True
    )
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    context_id: Mapped[str] = mapped_column(String(128), nullable=False)
    message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class A2ATaskEvent(Base):
    __tablename__ = "a2a_task_events"
    __table_args__ = (
        UniqueConstraint("task_id", "sequence", name="uq_a2a_task_events_sequence"),
        Index("ix_a2a_task_events_task", "task_id", "sequence"),
        Index("ix_a2a_task_events_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("a2a_tasks.id", ondelete="CASCADE"))
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class A2APushSubscription(Base):
    __tablename__ = "a2a_push_subscriptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "destination", name="uq_a2a_push_subscriptions_destination"),
        Index("ix_a2a_push_subscriptions_tenant_enabled", "tenant_id", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    destination: Mapped[str] = mapped_column(String(256), nullable=False)
    signing_key_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class A2AAccessPolicy(Base):
    __tablename__ = "a2a_access_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "peer_agent_id", name="uq_a2a_access_policy"),
        Index("ix_a2a_access_policies_tenant", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    peer_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("a2a_peer_agents.id", ondelete="CASCADE"), nullable=True
    )
    allow_inbound: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_outbound: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allowed_skills: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class RagSource(Base):
    __tablename__ = "rag_sources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_uri", name="uq_rag_sources_uri"),
        Index("ix_rag_sources_tenant", "tenant_id", "collection"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    collection: Mapped[str] = mapped_column(String(128), nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class RagDocument(Base):
    __tablename__ = "rag_documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_id", "version", name="uq_rag_documents_version"),
        Index("ix_rag_documents_tenant_collection", "tenant_id", "collection"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("rag_sources.id", ondelete="CASCADE"))
    collection: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    acl: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    document_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class RagChunk(Base):
    __tablename__ = "rag_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_rag_chunks_document_index"),
        Index("ix_rag_chunks_tenant_collection", "tenant_id", "collection"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    document_id: Mapped[str] = mapped_column(ForeignKey("rag_documents.id", ondelete="CASCADE"))
    collection: Mapped[str] = mapped_column(String(128), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class RagIngestionCandidateRow(Base):
    __tablename__ = "rag_ingestion_candidates"
    __table_args__ = (
        CheckConstraint(
            "status in ('PENDING', 'REJECTED', 'INGESTED')",
            name="ck_rag_ingestion_candidates_status",
        ),
        UniqueConstraint("run_id", name="uq_rag_ingestion_candidates_run"),
        Index(
            "idx_rag_ingestion_candidates_status_captured_at",
            "status",
            "captured_at",
        ),
        Index("idx_rag_ingestion_candidates_channel", "channel"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(120), nullable=False)
    user_id: Mapped[str] = mapped_column(String(120), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(120), nullable=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_document_id: Mapped[str | None] = mapped_column(String(120), nullable=True)


class MemoryNamespace(Base):
    __tablename__ = "memory_namespaces"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "subject_type",
            "subject_id",
            "memory_type",
            "visibility",
            name="uq_memory_namespaces_identity",
        ),
        Index("ix_memory_namespaces_tenant", "tenant_id", "subject_type", "subject_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    memory_type: Mapped[str] = mapped_column(String(64), nullable=False)
    visibility: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class MemoryItem(Base):
    __tablename__ = "memory_items"
    __table_args__ = (
        CheckConstraint(
            "status in ('active', 'superseded', 'tombstoned')",
            name="ck_memory_items_status",
        ),
        Index("ix_memory_items_namespace_status", "namespace_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    namespace_id: Mapped[str] = mapped_column(
        ForeignKey("memory_namespaces.id", ondelete="CASCADE")
    )
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    item_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class MemoryEmbedding(Base):
    __tablename__ = "memory_embeddings"
    __table_args__ = (Index("ix_memory_embeddings_tenant", "tenant_id"),)

    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class MemoryProposal(Base):
    __tablename__ = "memory_proposals"
    __table_args__ = (
        CheckConstraint(
            "status in ('proposed', 'approved', 'rejected', 'expired')",
            name="ck_memory_proposals_status",
        ),
        Index("ix_memory_proposals_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    namespace_id: Mapped[str] = mapped_column(
        ForeignKey("memory_namespaces.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    proposed_content: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_model: Mapped[str] = mapped_column(String(128), nullable=False)
    extraction_prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class RuntimeSetting(Base):
    __tablename__ = "runtime_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_runtime_settings_key"),
        Index("ix_runtime_settings_tenant_category", "tenant_id", "category"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    key: Mapped[str] = mapped_column(String(256), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column("type", String(32), nullable=False, default="STRING")
    category: Mapped[str] = mapped_column(String(128), nullable=False, default="general")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    setting_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AdminAudit(Base):
    __tablename__ = "admin_audits"
    __table_args__ = (
        Index("ix_admin_audits_tenant_created", "tenant_id", "created_at"),
        Index("ix_admin_audits_category_action", "tenant_id", "category", "action", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(256), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class FeedbackRecord(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(
            "rating in ('THUMBS_UP', 'THUMBS_DOWN')",
            name="ck_feedback_rating",
        ),
        CheckConstraint(
            "review_status in ('inbox', 'done')",
            name="ck_feedback_review_status",
        ),
        Index("ix_feedback_tenant_created", "tenant_id", "created_at"),
        Index("ix_feedback_tenant_rating", "tenant_id", "rating", "created_at"),
        Index("ix_feedback_review_status", "tenant_id", "review_status", "created_at"),
        Index(
            "ix_feedback_tenant_template_rating",
            "tenant_id",
            "template_id",
            "rating",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="slack_button")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    intent: Mapped[str | None] = mapped_column(String(120), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tools_used: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    template_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="inbox")
    review_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SlackBotInstance(Base):
    __tablename__ = "slack_bot_instances"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_slack_bot_instances_name"),
        Index("ix_slack_bot_instances_tenant_enabled", "tenant_id", "enabled", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    bot_token: Mapped[str] = mapped_column(Text, nullable=False)
    app_token: Mapped[str] = mapped_column(Text, nullable=False)
    persona_id: Mapped[str] = mapped_column(String(128), nullable=False)
    default_channel: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SlackProactiveChannel(Base):
    __tablename__ = "slack_proactive_channels"
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel_id", name="uq_slack_proactive_channels_id"),
        Index("ix_slack_proactive_channels_tenant_added", "tenant_id", "added_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ChannelFaqRegistration(Base):
    __tablename__ = "channel_faq_registrations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "channel_id",
            name="uq_channel_faq_registrations_tenant_channel",
        ),
        CheckConstraint(
            "confidence_threshold >= 0 and confidence_threshold <= 1",
            name="ck_channel_faq_registrations_threshold",
        ),
        Index(
            "ix_channel_faq_registrations_due",
            "tenant_id",
            "enabled",
            "last_ingested_at",
            "channel_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_reply_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="mention")
    confidence_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.75)
    days_back: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    re_ingest_interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    last_ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_message_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    registered_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AgentEvalCase(Base):
    __tablename__ = "agent_eval_cases"
    __table_args__ = (
        CheckConstraint("min_score >= 0 and min_score <= 1", name="ck_agent_eval_cases_score"),
        Index("ix_agent_eval_cases_tenant_enabled", "tenant_id", "enabled", "updated_at"),
        Index("ix_agent_eval_cases_source_run", "tenant_id", "source_run_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    user_input: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer_contains: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    forbidden_answer_contains: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    expected_tool_names: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    forbidden_tool_names: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    expected_exposed_tool_names: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    forbidden_exposed_tool_names: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    max_tool_exposure_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    min_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AgentEvalResult(Base):
    __tablename__ = "agent_eval_results"
    __table_args__ = (
        CheckConstraint("score >= 0 and score <= 1", name="ck_agent_eval_results_score"),
        Index("ix_agent_eval_results_case", "tenant_id", "case_id", "evaluated_at"),
        Index("ix_agent_eval_results_tier", "tenant_id", "tier", "evaluated_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("agent_eval_cases.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tier: Mapped[str] = mapped_column(String(64), nullable=False, default="deterministic")
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type in ('MCP_TOOL', 'AGENT', 'PROMPT_LAB_AUTO_OPTIMIZE')",
            name="ck_scheduled_jobs_type",
        ),
        CheckConstraint(
            "last_status is null or last_status in ('SUCCESS', 'FAILED', 'RUNNING', 'SKIPPED')",
            name="ck_scheduled_jobs_last_status",
        ),
        UniqueConstraint("tenant_id", "name", name="uq_scheduled_jobs_name"),
        Index("ix_scheduled_jobs_tenant_enabled", "tenant_id", "enabled", "created_at"),
        Index("ix_scheduled_jobs_lease", "tenant_id", "lease_expires_at", "fencing_token"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cron_expression: Mapped[str] = mapped_column(String(128), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Seoul")
    job_type: Mapped[str] = mapped_column(String(32), nullable=False, default="MCP_TOOL")
    mcp_server_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_arguments: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    agent_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    persona_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent_system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent_max_tool_calls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    slack_channel_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    teams_webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retry_on_failure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    execution_timeout_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ScheduledJobExecution(Base):
    __tablename__ = "scheduled_job_executions"
    __table_args__ = (
        CheckConstraint(
            "status in ('SUCCESS', 'FAILED', 'RUNNING', 'SKIPPED')",
            name="ck_scheduled_job_executions_status",
        ),
        Index("ix_scheduled_job_executions_job", "tenant_id", "job_id", "started_at"),
        Index("ix_scheduled_job_executions_recent", "tenant_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("scheduled_jobs.id", ondelete="CASCADE"), nullable=False
    )
    job_name: Mapped[str] = mapped_column(String(200), nullable=False)
    job_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScheduledJobDeadLetter(Base):
    __tablename__ = "scheduled_job_dead_letters"
    __table_args__ = (
        Index("ix_scheduled_job_dead_letters_job", "tenant_id", "job_id", "created_at"),
        Index("ix_scheduled_job_dead_letters_recent", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("scheduled_jobs.id", ondelete="CASCADE"), nullable=False
    )
    job_name: Mapped[str] = mapped_column(String(200), nullable=False)
    job_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ModelPricing(Base):
    __tablename__ = "model_pricing"
    __table_args__ = (Index("ix_model_pricing_effective", "provider", "model", "effective_from"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_price_per_1m: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False, default=0)
    completion_price_per_1m: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=0
    )
    cached_input_price_per_1m: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=0
    )
    reasoning_price_per_1m: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=0
    )
    batch_prompt_price_per_1m: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=0
    )
    batch_completion_price_per_1m: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=0
    )
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(
            "plan in ('FREE', 'STARTER', 'BUSINESS', 'ENTERPRISE')",
            name="ck_tenants_plan",
        ),
        CheckConstraint(
            "status in ('ACTIVE', 'SUSPENDED', 'DEACTIVATED')",
            name="ck_tenants_status",
        ),
        UniqueConstraint("slug", name="uq_tenants_slug"),
        Index("ix_tenants_slug", "slug"),
        Index("ix_tenants_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    plan: Mapped[str] = mapped_column(String(20), nullable=False, default="FREE")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    max_requests_per_month: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1000)
    max_tokens_per_month: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1000000)
    max_users: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    max_agents: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_mcp_servers: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    billing_cycle_start: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    billing_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    slo_availability: Mapped[float] = mapped_column(Float, nullable=False, default=0.995)
    slo_latency_p99_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=10000)
    tenant_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class UsageLedger(Base):
    __tablename__ = "usage_ledger"
    __table_args__ = (
        Index("ix_usage_ledger_tenant_occurred", "tenant_id", "occurred_at"),
        Index("ix_usage_ledger_tenant_run", "tenant_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    step_type: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cached_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False, default=0)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class MetricGuardEvent(Base):
    __tablename__ = "metric_guard_events"
    __table_args__ = (
        CheckConstraint(
            "action in ('allowed', 'rejected', 'error')",
            name="ck_metric_guard_events_action",
        ),
        Index("ix_metric_guard_events_input_time", "is_output_guard", "time"),
        Index("ix_metric_guard_events_tenant_time", "tenant_id", "time"),
        Index("ix_metric_guard_events_stage_action", "stage", "action", "time"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason_class: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_output_guard: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)


class AlertRuleRow(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        CheckConstraint(
            "type in ('STATIC_THRESHOLD', 'BASELINE_ANOMALY', 'ERROR_BUDGET_BURN_RATE')",
            name="ck_alert_rules_type",
        ),
        CheckConstraint(
            "severity in ('INFO', 'WARNING', 'CRITICAL')",
            name="ck_alert_rules_severity",
        ),
        Index("ix_alert_rules_tenant_enabled", "tenant_id", "enabled", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    metric: Mapped[str] = mapped_column(String(128), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    window_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    platform_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class AlertInstanceRow(Base):
    __tablename__ = "alert_instances"
    __table_args__ = (
        CheckConstraint(
            "severity in ('INFO', 'WARNING', 'CRITICAL')",
            name="ck_alert_instances_severity",
        ),
        CheckConstraint(
            "status in ('ACTIVE', 'ACKNOWLEDGED', 'RESOLVED')",
            name="ck_alert_instances_status",
        ),
        Index("ix_alert_instances_status", "status", "fired_at"),
        Index("ix_alert_instances_rule_status", "rule_id", "status"),
        Index("ix_alert_instances_tenant_status", "tenant_id", "status", "fired_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey("alert_rules.id", ondelete="CASCADE"))
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(128), nullable=True)


class AuthUser(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_role", "role"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    groups: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "external_subject",
            name="uq_user_identities_external_subject",
        ),
        Index("ix_user_identities_user", "tenant_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    external_subject: Mapped[str] = mapped_column(String(256), nullable=False)
    identity_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AuthTokenRevocation(Base):
    __tablename__ = "auth_token_revocations"

    token_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class MigrationImport(Base):
    __tablename__ = "migration_imports"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "source_table",
            "source_pk",
            "checksum",
            name="uq_migration_imports_source",
        ),
        Index("ix_migration_imports_batch_table", "batch_id", "source_table", "source_pk"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_table: Mapped[str] = mapped_column(String(128), nullable=False)
    source_pk: Mapped[str] = mapped_column(String(256), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class MigrationRollbackSnapshot(Base):
    __tablename__ = "migration_rollback_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "target_table",
            "target_pk",
            "checksum",
            name="uq_migration_rollback_snapshots_target",
        ),
        Index(
            "ix_migration_rollback_snapshots_batch_table",
            "batch_id",
            "target_table",
            "target_pk",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_table: Mapped[str] = mapped_column(String(128), nullable=False)
    target_pk: Mapped[str] = mapped_column(String(256), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
