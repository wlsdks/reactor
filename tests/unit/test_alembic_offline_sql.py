from __future__ import annotations

from io import StringIO

from alembic import command
from alembic.config import Config


def test_alembic_offline_upgrade_sql_renders_python_baseline() -> None:
    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)

    command.upgrade(config, "head", sql=True)

    sql = output.getvalue()
    assert "CREATE TABLE agent_runs" in sql
    assert "CREATE TABLE runtime_settings" in sql
    assert "CREATE TABLE rag_chunks" in sql
    assert "CREATE TABLE memory_embeddings" in sql
    assert "CREATE TABLE migration_imports" in sql
    assert "ALTER TABLE users ADD COLUMN groups JSON" in sql
    assert "PROMPT_LAB_AUTO_OPTIMIZE" in sql
    assert "ALTER TABLE outbox_events ADD COLUMN lease_owner VARCHAR(128)" in sql
    assert "CREATE INDEX ix_outbox_events_lease" in sql
    assert (
        "status in ('queued', 'running', 'interrupted', 'completed', 'failed', 'cancelled')" in sql
    )
    assert "CREATE TABLE IF NOT EXISTS store_migrations" in sql
    assert "CREATE TABLE IF NOT EXISTS store" in sql
    assert "INSERT INTO store_migrations (v) VALUES (0), (1), (2), (3)" in sql
    assert "ON CONFLICT (v) DO NOTHING" in sql
    assert "CREATE INDEX IF NOT EXISTS store_prefix_idx" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_store_expires_at" in sql
    assert "UPDATE alembic_version SET version_num='202607230002'" in sql


def test_alembic_offline_upgrade_sql_enables_rag_row_level_security() -> None:
    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)

    command.upgrade(config, "head", sql=True)

    sql = output.getvalue()
    assert "ALTER TABLE rag_sources ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE rag_documents ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE rag_chunks ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE rag_sources FORCE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE rag_documents FORCE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE rag_chunks FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY rag_sources_tenant_isolation" in sql
    assert "CREATE POLICY rag_documents_tenant_acl_read" in sql
    assert "CREATE POLICY rag_chunks_tenant_acl_read" in sql
    assert "CREATE POLICY rag_sources_tenant_insert" in sql
    assert "CREATE POLICY rag_documents_tenant_update" in sql
    assert "CREATE POLICY rag_chunks_tenant_delete" in sql
    assert "current_setting('reactor.tenant_id', true)" in sql
    assert "current_setting('reactor.user_id', true)" in sql
    assert "reactor.user_groups" in sql


def test_agent_run_interrupted_status_downgrade_normalizes_existing_rows() -> None:
    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)

    command.downgrade(config, "202607230001:202606280005", sql=True)

    sql = output.getvalue()
    assert "UPDATE agent_runs SET status = 'failed' WHERE status = 'interrupted'" in sql
    assert "status in ('queued', 'running', 'completed', 'failed', 'cancelled')" in sql
