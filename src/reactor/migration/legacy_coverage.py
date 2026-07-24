from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LegacyTableCoverage:
    legacy_table: str
    python_source_table: str
    python_target_tables: tuple[str, ...]
    note: str


SPRING_V6_1_RETAINED_TABLE_COVERAGE: tuple[LegacyTableCoverage, ...] = (
    LegacyTableCoverage(
        legacy_table="admin_audits",
        python_source_table="admin_audits",
        python_target_tables=("admin_audits",),
        note="retained operational audit rows",
    ),
    LegacyTableCoverage(
        legacy_table="alert_instances",
        python_source_table="alert_instances",
        python_target_tables=("alert_instances",),
        note="retained SLO alert instance history",
    ),
    LegacyTableCoverage(
        legacy_table="alert_rules",
        python_source_table="alert_rules",
        python_target_tables=("alert_rules",),
        note="retained SLO alert rule definitions",
    ),
    LegacyTableCoverage(
        legacy_table="auth_token_revocations",
        python_source_table="auth_token_revocations",
        python_target_tables=("auth_token_revocations",),
        note="retained revoked-token state",
    ),
    LegacyTableCoverage(
        legacy_table="conversation_messages",
        python_source_table="agent_run_events",
        python_target_tables=("agent_run_events",),
        note="Spring conversation messages become synthetic run events",
    ),
    LegacyTableCoverage(
        legacy_table="conversation_summaries",
        python_source_table="agent_run_events",
        python_target_tables=("agent_run_events",),
        note="Spring conversation summaries become synthetic run events",
    ),
    LegacyTableCoverage(
        legacy_table="experiment_reports",
        python_source_table="prompt_lab_reports",
        python_target_tables=("prompt_lab_reports",),
        note="Spring experiment reports become PromptLab reports",
    ),
    LegacyTableCoverage(
        legacy_table="experiments",
        python_source_table="prompt_lab_experiments",
        python_target_tables=("prompt_lab_experiments",),
        note="Spring experiments become PromptLab experiments",
    ),
    LegacyTableCoverage(
        legacy_table="feedback",
        python_source_table="feedback",
        python_target_tables=("feedback",),
        note="retained feedback and review metadata",
    ),
    LegacyTableCoverage(
        legacy_table="intent_definitions",
        python_source_table="intent_definitions",
        python_target_tables=("intent_definitions",),
        note="retained intent routing definitions",
    ),
    LegacyTableCoverage(
        legacy_table="mcp_security_policy",
        python_source_table="runtime_settings",
        python_target_tables=("runtime_settings",),
        note="Spring MCP policy becomes runtime settings",
    ),
    LegacyTableCoverage(
        legacy_table="mcp_servers",
        python_source_table="mcp_servers",
        python_target_tables=("mcp_servers",),
        note="retained MCP server registry rows",
    ),
    LegacyTableCoverage(
        legacy_table="metric_agent_executions",
        python_source_table="metric_agent_executions",
        python_target_tables=("metric_agent_executions",),
        note="retained compatibility metric events",
    ),
    LegacyTableCoverage(
        legacy_table="metric_audit_trail",
        python_source_table="metric_audit_trail",
        python_target_tables=("metric_audit_trail",),
        note="retained compatibility metric events",
    ),
    LegacyTableCoverage(
        legacy_table="metric_eval_results",
        python_source_table="metric_eval_results",
        python_target_tables=("metric_eval_results",),
        note="retained compatibility metric events",
    ),
    LegacyTableCoverage(
        legacy_table="metric_guard_events",
        python_source_table="metric_guard_events",
        python_target_tables=("metric_guard_events",),
        note="retained guard metric events",
    ),
    LegacyTableCoverage(
        legacy_table="metric_hitl_events",
        python_source_table="metric_hitl_events",
        python_target_tables=("metric_hitl_events",),
        note="retained compatibility metric events",
    ),
    LegacyTableCoverage(
        legacy_table="metric_mcp_health",
        python_source_table="metric_mcp_health",
        python_target_tables=("metric_mcp_health",),
        note="retained compatibility metric events",
    ),
    LegacyTableCoverage(
        legacy_table="metric_quota_events",
        python_source_table="metric_quota_events",
        python_target_tables=("metric_quota_events",),
        note="retained compatibility metric events",
    ),
    LegacyTableCoverage(
        legacy_table="metric_sessions",
        python_source_table="metric_sessions",
        python_target_tables=("metric_sessions",),
        note="retained compatibility metric events",
    ),
    LegacyTableCoverage(
        legacy_table="metric_spans",
        python_source_table="metric_spans",
        python_target_tables=("metric_spans",),
        note="retained compatibility metric events",
    ),
    LegacyTableCoverage(
        legacy_table="metric_token_usage",
        python_source_table="usage_ledger",
        python_target_tables=("usage_ledger",),
        note="Spring token usage metrics become usage-ledger records",
    ),
    LegacyTableCoverage(
        legacy_table="metric_tool_calls",
        python_source_table="metric_tool_calls",
        python_target_tables=("metric_tool_calls",),
        note="retained compatibility metric events",
    ),
    LegacyTableCoverage(
        legacy_table="model_pricing",
        python_source_table="model_pricing",
        python_target_tables=("model_pricing",),
        note="retained model pricing rows",
    ),
    LegacyTableCoverage(
        legacy_table="output_guard_rule_audits",
        python_source_table="output_guard_rule_audits",
        python_target_tables=("output_guard_rule_audits",),
        note="retained output guard audit rows",
    ),
    LegacyTableCoverage(
        legacy_table="output_guard_rules",
        python_source_table="output_guard_rules",
        python_target_tables=("output_guard_rules",),
        note="retained output guard policy rows",
    ),
    LegacyTableCoverage(
        legacy_table="pending_approvals",
        python_source_table="pending_approvals",
        python_target_tables=("pending_approvals",),
        note="retained approval state",
    ),
    LegacyTableCoverage(
        legacy_table="personas",
        python_source_table="personas",
        python_target_tables=("personas",),
        note="retained persona rows",
    ),
    LegacyTableCoverage(
        legacy_table="prompt_templates",
        python_source_table="prompt_templates",
        python_target_tables=("prompt_templates",),
        note="retained prompt templates",
    ),
    LegacyTableCoverage(
        legacy_table="prompt_versions",
        python_source_table="prompt_versions",
        python_target_tables=("prompt_versions",),
        note="retained prompt versions",
    ),
    LegacyTableCoverage(
        legacy_table="rag_ingestion_candidates",
        python_source_table="rag_ingestion_candidates",
        python_target_tables=("rag_ingestion_candidates",),
        note="retained RAG ingestion review queue",
    ),
    LegacyTableCoverage(
        legacy_table="rag_ingestion_policy",
        python_source_table="runtime_settings",
        python_target_tables=("runtime_settings",),
        note="Spring RAG ingestion policy becomes runtime settings",
    ),
    LegacyTableCoverage(
        legacy_table="scheduled_job_executions",
        python_source_table="scheduled_job_executions",
        python_target_tables=("scheduled_job_executions",),
        note="retained scheduler execution history",
    ),
    LegacyTableCoverage(
        legacy_table="scheduled_jobs",
        python_source_table="scheduled_jobs",
        python_target_tables=("scheduled_jobs",),
        note="retained scheduler definitions",
    ),
    LegacyTableCoverage(
        legacy_table="slo_config",
        python_source_table="tenant_slo_config",
        python_target_tables=("tenant_slo_config",),
        note="Spring SLO config becomes tenant SLO config",
    ),
    LegacyTableCoverage(
        legacy_table="tenants",
        python_source_table="tenants",
        python_target_tables=("tenants",),
        note="retained tenant records",
    ),
    LegacyTableCoverage(
        legacy_table="tool_policy",
        python_source_table="runtime_settings",
        python_target_tables=("runtime_settings",),
        note="Spring tool policy becomes runtime settings",
    ),
    LegacyTableCoverage(
        legacy_table="trials",
        python_source_table="prompt_lab_trials",
        python_target_tables=("prompt_lab_trials",),
        note="Spring experiment trials become PromptLab trials",
    ),
    LegacyTableCoverage(
        legacy_table="users",
        python_source_table="users",
        python_target_tables=("users",),
        note="retained auth users",
    ),
)
