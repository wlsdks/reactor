from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "202606280002"
down_revision: str | None = "202606280001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("rag_sources", "rag_documents", "rag_chunks"):
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE POLICY rag_sources_tenant_insert
        ON rag_sources
        FOR INSERT
        WITH CHECK (tenant_id = current_setting('reactor.tenant_id', true));
        """
    )
    op.execute(
        """
        CREATE POLICY rag_sources_tenant_update
        ON rag_sources
        FOR UPDATE
        USING (tenant_id = current_setting('reactor.tenant_id', true))
        WITH CHECK (tenant_id = current_setting('reactor.tenant_id', true));
        """
    )
    op.execute(
        """
        CREATE POLICY rag_sources_tenant_delete
        ON rag_sources
        FOR DELETE
        USING (tenant_id = current_setting('reactor.tenant_id', true));
        """
    )
    op.execute(
        """
        CREATE POLICY rag_documents_tenant_insert
        ON rag_documents
        FOR INSERT
        WITH CHECK (tenant_id = current_setting('reactor.tenant_id', true));
        """
    )
    op.execute(
        """
        CREATE POLICY rag_documents_tenant_update
        ON rag_documents
        FOR UPDATE
        USING (tenant_id = current_setting('reactor.tenant_id', true))
        WITH CHECK (tenant_id = current_setting('reactor.tenant_id', true));
        """
    )
    op.execute(
        """
        CREATE POLICY rag_documents_tenant_delete
        ON rag_documents
        FOR DELETE
        USING (tenant_id = current_setting('reactor.tenant_id', true));
        """
    )
    op.execute(
        """
        CREATE POLICY rag_chunks_tenant_insert
        ON rag_chunks
        FOR INSERT
        WITH CHECK (tenant_id = current_setting('reactor.tenant_id', true));
        """
    )
    op.execute(
        """
        CREATE POLICY rag_chunks_tenant_update
        ON rag_chunks
        FOR UPDATE
        USING (tenant_id = current_setting('reactor.tenant_id', true))
        WITH CHECK (tenant_id = current_setting('reactor.tenant_id', true));
        """
    )
    op.execute(
        """
        CREATE POLICY rag_chunks_tenant_delete
        ON rag_chunks
        FOR DELETE
        USING (tenant_id = current_setting('reactor.tenant_id', true));
        """
    )


def downgrade() -> None:
    for table, policies in {
        "rag_chunks": (
            "rag_chunks_tenant_delete",
            "rag_chunks_tenant_update",
            "rag_chunks_tenant_insert",
        ),
        "rag_documents": (
            "rag_documents_tenant_delete",
            "rag_documents_tenant_update",
            "rag_documents_tenant_insert",
        ),
        "rag_sources": (
            "rag_sources_tenant_delete",
            "rag_sources_tenant_update",
            "rag_sources_tenant_insert",
        ),
    }.items():
        for policy in policies:
            op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
