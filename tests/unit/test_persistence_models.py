from __future__ import annotations

from sqlalchemy import CheckConstraint

from reactor.persistence.models import Base


def test_checkpoint_tables_are_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"checkpoint_migrations"' in content
    assert '"checkpoints"' in content
    assert '"checkpoint_blobs"' in content
    assert '"checkpoint_writes"' in content


def test_durable_tables_are_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"run_queue"' in content
    assert '"dead_letter_jobs"' in content
    assert '"idempotency_records"' in content
    assert '"outbox_events"' in content
    assert '"inbox_events"' in content


def test_agent_run_tables_are_registered() -> None:
    assert "agent_runs" in Base.metadata.tables
    assert "agent_run_events" in Base.metadata.tables


def test_agent_run_status_constraint_allows_langgraph_interrupts() -> None:
    agent_runs = Base.metadata.tables["agent_runs"]
    constraint_sql = " ".join(
        str(constraint.sqltext)
        for constraint in agent_runs.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name == "ck_agent_runs_status"
    )

    assert "'interrupted'" in constraint_sql


def test_durable_execution_tables_are_registered() -> None:
    assert "run_queue" in Base.metadata.tables
    assert "dead_letter_jobs" in Base.metadata.tables
    assert "idempotency_records" in Base.metadata.tables
    assert "outbox_events" in Base.metadata.tables
    assert "inbox_events" in Base.metadata.tables


def test_tool_policy_tables_are_registered() -> None:
    assert "tool_catalog" in Base.metadata.tables
    assert "pending_approvals" in Base.metadata.tables
    assert "tool_invocations" in Base.metadata.tables


def test_output_guard_rule_tables_are_registered() -> None:
    assert "output_guard_rules" in Base.metadata.tables
    assert "output_guard_rule_audits" in Base.metadata.tables


def test_tool_tables_are_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"tool_catalog"' in content
    assert '"pending_approvals"' in content
    assert '"tool_invocations"' in content


def test_output_guard_rule_tables_are_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"output_guard_rules"' in content
    assert '"output_guard_rule_audits"' in content
    assert "ck_output_guard_rules_action" in content
    assert "ck_output_guard_rule_audits_action" in content


def test_mcp_tables_are_registered() -> None:
    assert "mcp_servers" in Base.metadata.tables
    assert "mcp_server_status" in Base.metadata.tables
    assert "mcp_tool_snapshots" in Base.metadata.tables
    assert "mcp_access_policies" in Base.metadata.tables


def test_mcp_tables_are_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"mcp_servers"' in content
    assert '"mcp_server_status"' in content
    assert '"mcp_tool_snapshots"' in content
    assert '"mcp_access_policies"' in content


def test_a2a_tables_are_registered() -> None:
    assert "a2a_peer_agents" in Base.metadata.tables
    assert "a2a_agent_cards" in Base.metadata.tables
    assert "a2a_tasks" in Base.metadata.tables
    assert "a2a_task_events" in Base.metadata.tables
    assert "a2a_push_subscriptions" in Base.metadata.tables
    assert "a2a_access_policies" in Base.metadata.tables


def test_a2a_tables_are_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"a2a_peer_agents"' in content
    assert '"a2a_agent_cards"' in content
    assert '"a2a_tasks"' in content
    assert '"a2a_task_events"' in content
    assert '"a2a_push_subscriptions"' in content
    assert '"a2a_access_policies"' in content


def test_rag_tables_are_registered() -> None:
    assert "rag_sources" in Base.metadata.tables
    assert "rag_documents" in Base.metadata.tables
    assert "rag_chunks" in Base.metadata.tables


def test_memory_tables_are_registered() -> None:
    assert "memory_namespaces" in Base.metadata.tables
    assert "memory_items" in Base.metadata.tables
    assert "memory_embeddings" in Base.metadata.tables
    assert "memory_proposals" in Base.metadata.tables


def test_runtime_settings_table_is_registered() -> None:
    assert "runtime_settings" in Base.metadata.tables


def test_prompt_tables_are_registered() -> None:
    assert "prompt_templates" in Base.metadata.tables
    assert "prompt_versions" in Base.metadata.tables
    assert "prompt_releases" in Base.metadata.tables


def test_prompt_tables_are_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"prompt_templates"' in content
    assert '"prompt_versions"' in content
    assert '"prompt_releases"' in content
    assert "uq_prompt_templates_name" in content
    assert "uq_prompt_versions_version" in content
    assert "uq_prompt_releases_environment" in content


def test_admin_audit_table_is_registered() -> None:
    assert "admin_audits" in Base.metadata.tables


def test_feedback_table_is_registered() -> None:
    assert "feedback" in Base.metadata.tables


def test_slack_tables_are_registered() -> None:
    assert "slack_bot_instances" in Base.metadata.tables
    assert "slack_proactive_channels" in Base.metadata.tables


def test_agent_eval_tables_are_registered() -> None:
    assert "agent_eval_cases" in Base.metadata.tables
    assert "agent_eval_results" in Base.metadata.tables


def test_scheduler_tables_are_registered() -> None:
    assert "scheduled_jobs" in Base.metadata.tables
    assert "scheduled_job_executions" in Base.metadata.tables
    assert "scheduled_job_dead_letters" in Base.metadata.tables


def test_scheduler_job_type_constraint_allows_prompt_lab_auto_optimize() -> None:
    scheduled_jobs = Base.metadata.tables["scheduled_jobs"]
    constraint_sql = " ".join(
        str(constraint.sqltext)
        for constraint in scheduled_jobs.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name == "ck_scheduled_jobs_type"
    )

    assert "PROMPT_LAB_AUTO_OPTIMIZE" in constraint_sql


def test_auth_tables_are_registered() -> None:
    assert "users" in Base.metadata.tables
    assert "user_identities" in Base.metadata.tables
    assert "auth_token_revocations" in Base.metadata.tables
    assert "groups" in Base.metadata.tables["users"].columns


def test_alert_tables_are_registered() -> None:
    assert "alert_rules" in Base.metadata.tables
    assert "alert_instances" in Base.metadata.tables


def test_migration_tables_are_registered() -> None:
    assert "migration_imports" in Base.metadata.tables
    assert "migration_rollback_snapshots" in Base.metadata.tables


def test_migration_tables_are_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"migration_imports"' in content
    assert '"migration_rollback_snapshots"' in content
    assert "uq_migration_imports_source" in content
    assert "uq_migration_rollback_snapshots_target" in content


def test_runtime_settings_table_is_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"runtime_settings"' in content
    assert "uq_runtime_settings_key" in content
    assert "ix_runtime_settings_tenant_category" in content


def test_admin_audit_table_is_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"admin_audits"' in content
    assert "ix_admin_audits_tenant_created" in content
    assert "ix_admin_audits_category_action" in content


def test_slack_tables_are_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"slack_bot_instances"' in content
    assert '"slack_proactive_channels"' in content
    assert "uq_slack_bot_instances_name" in content
    assert "uq_slack_proactive_channels_id" in content
    assert "ix_slack_bot_instances_tenant_enabled" in content
    assert "ix_slack_proactive_channels_tenant_added" in content


def test_agent_eval_tables_are_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"agent_eval_cases"' in content
    assert '"agent_eval_results"' in content
    assert "ck_agent_eval_cases_score" in content
    assert "ck_agent_eval_results_score" in content
    assert "ix_agent_eval_cases_tenant_enabled" in content
    assert "ix_agent_eval_results_case" in content


def test_scheduler_tables_are_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"scheduled_jobs"' in content
    assert '"scheduled_job_executions"' in content
    assert '"scheduled_job_dead_letters"' in content
    assert '"lease_owner"' in content
    assert '"lease_expires_at"' in content
    assert '"fencing_token"' in content
    assert "ck_scheduled_jobs_type" in content
    assert "PROMPT_LAB_AUTO_OPTIMIZE" in content
    assert "ck_scheduled_job_executions_status" in content
    assert "uq_scheduled_jobs_name" in content
    assert "ix_scheduled_jobs_lease" in content
    assert "ix_scheduled_job_dead_letters_job" in content


def test_auth_tables_are_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"users"' in content
    assert '"user_identities"' in content
    assert '"auth_token_revocations"' in content
    assert "uq_users_email" in content
    assert "ix_users_role" in content
    assert "uq_user_identities_external_subject" in content
    assert "ix_user_identities_user" in content


def test_usage_ledger_tables_are_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"model_pricing"' in content
    assert '"usage_ledger"' in content
    assert '"prompt_price_per_1m"' in content
    assert '"estimated_cost_usd"' in content
    assert "ix_model_pricing_effective" in content
    assert "ix_usage_ledger_tenant_occurred" in content
    assert "ix_usage_ledger_tenant_run" in content


def test_alert_tables_are_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"alert_rules"' in content
    assert '"alert_instances"' in content
    assert "ck_alert_rules_type" in content
    assert "ck_alert_instances_status" in content
    assert "ix_alert_rules_tenant_enabled" in content
    assert "ix_alert_instances_status" in content


def test_rag_and_memory_tables_use_pgvector_in_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"rag_chunks"' in content
    assert '"memory_embeddings"' in content
    assert "Vector(1536)" in content


def test_run_queue_references_agent_runs() -> None:
    foreign_keys = Base.metadata.tables["run_queue"].foreign_keys

    targets = {foreign_key.target_fullname for foreign_key in foreign_keys}
    assert "agent_runs.id" in targets


def test_agent_runs_schema_contains_checkpoint_identity() -> None:
    columns = Base.metadata.tables["agent_runs"].columns

    assert "thread_id" in columns
    assert "checkpoint_ns" in columns
    assert "metadata" in columns


def test_agent_run_events_sequence_is_unique_per_run() -> None:
    constraints = Base.metadata.tables["agent_run_events"].constraints

    names = {constraint.name for constraint in constraints}
    assert "uq_agent_run_events_sequence" in names


def test_outbox_idempotency_is_unique_per_tenant() -> None:
    constraints = Base.metadata.tables["outbox_events"].constraints

    names = {constraint.name for constraint in constraints}
    assert "uq_outbox_events_idempotency" in names


def test_tool_catalog_name_is_unique_per_tenant_namespace() -> None:
    constraints = Base.metadata.tables["tool_catalog"].constraints

    names = {constraint.name for constraint in constraints}
    assert "uq_tool_catalog_name" in names


def test_mcp_server_name_is_unique_per_tenant() -> None:
    constraints = Base.metadata.tables["mcp_servers"].constraints

    names = {constraint.name for constraint in constraints}
    assert "uq_mcp_servers_name" in names


def test_a2a_task_idempotency_is_unique_per_tenant() -> None:
    constraints = Base.metadata.tables["a2a_tasks"].constraints

    names = {constraint.name for constraint in constraints}
    assert "uq_a2a_tasks_idempotency" in names


def test_a2a_task_events_sequence_is_unique_per_task() -> None:
    constraints = Base.metadata.tables["a2a_task_events"].constraints

    names = {constraint.name for constraint in constraints}
    assert "uq_a2a_task_events_sequence" in names
