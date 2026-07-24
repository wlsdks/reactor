from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "202606280001"
down_revision: str | None = "202606270003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reactor_can_read_rag_acl(acl jsonb)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        AS $$
            SELECT
                acl ->> 'visibility' IN ('public', 'tenant')
                OR (
                    acl ->> 'visibility' = 'private'
                    AND (
                        (
                            jsonb_typeof(acl -> 'users') = 'array'
                            AND (acl -> 'users') ? current_setting('reactor.user_id', true)
                        )
                        OR (
                            jsonb_typeof(acl -> 'groups') = 'array'
                            AND EXISTS (
                                SELECT 1
                                FROM jsonb_array_elements_text(
                                    COALESCE(
                                        NULLIF(
                                            current_setting('reactor.user_groups', true),
                                            ''
                                        )::jsonb,
                                        '[]'::jsonb
                                    )
                                ) AS reactor_user_groups(group_id)
                                WHERE (acl -> 'groups') ? reactor_user_groups.group_id
                            )
                        )
                    )
                )
        $$;
        """
    )
    op.execute("ALTER TABLE rag_sources ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rag_documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rag_chunks ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY rag_sources_tenant_isolation
        ON rag_sources
        FOR SELECT
        USING (tenant_id = current_setting('reactor.tenant_id', true));
        """
    )
    op.execute(
        """
        CREATE POLICY rag_documents_tenant_acl_read
        ON rag_documents
        FOR SELECT
        USING (
            tenant_id = current_setting('reactor.tenant_id', true)
            AND reactor_can_read_rag_acl(acl)
        );
        """
    )
    op.execute(
        """
        CREATE POLICY rag_chunks_tenant_acl_read
        ON rag_chunks
        FOR SELECT
        USING (
            tenant_id = current_setting('reactor.tenant_id', true)
            AND EXISTS (
                SELECT 1
                FROM rag_documents
                WHERE rag_documents.id = rag_chunks.document_id
                  AND rag_documents.tenant_id = current_setting('reactor.tenant_id', true)
                  AND rag_documents.collection = rag_chunks.collection
                  AND reactor_can_read_rag_acl(rag_documents.acl)
            )
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS rag_chunks_tenant_acl_read ON rag_chunks")
    op.execute("DROP POLICY IF EXISTS rag_documents_tenant_acl_read ON rag_documents")
    op.execute("DROP POLICY IF EXISTS rag_sources_tenant_isolation ON rag_sources")
    op.execute("ALTER TABLE rag_chunks DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rag_documents DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rag_sources DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION IF EXISTS reactor_can_read_rag_acl(jsonb)")
