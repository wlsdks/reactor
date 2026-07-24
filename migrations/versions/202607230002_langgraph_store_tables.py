from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607230002"
down_revision: str | None = "202607230001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS store_migrations (
                v INTEGER PRIMARY KEY
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS store (
                prefix TEXT NOT NULL,
                key TEXT NOT NULL,
                value JSONB NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP WITH TIME ZONE,
                ttl_minutes INTEGER,
                PRIMARY KEY (prefix, key)
            )
            """
        )
    )
    op.execute(sa.text("ALTER TABLE store ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ"))
    op.execute(sa.text("ALTER TABLE store ADD COLUMN IF NOT EXISTS ttl_minutes INTEGER"))
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS store_prefix_idx "
            "ON store USING btree (prefix text_pattern_ops)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_store_expires_at "
            "ON store (expires_at) WHERE expires_at IS NOT NULL"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO store_migrations (v) VALUES (0), (1), (2), (3) ON CONFLICT (v) DO NOTHING"
        )
    )


def downgrade() -> None:
    op.drop_index("idx_store_expires_at", table_name="store")
    op.drop_index("store_prefix_idx", table_name="store")
    op.drop_table("store")
    op.drop_table("store_migrations")
