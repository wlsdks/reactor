from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202606270002"
down_revision: str | None = "202606270001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("feedback", sa.Column("intent", sa.String(length=120), nullable=True))
    op.add_column("feedback", sa.Column("domain", sa.String(length=120), nullable=True))
    op.add_column("feedback", sa.Column("model", sa.String(length=120), nullable=True))
    op.add_column("feedback", sa.Column("prompt_version", sa.Integer(), nullable=True))
    op.add_column("feedback", sa.Column("tools_used", sa.JSON(), nullable=True))
    op.add_column("feedback", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("feedback", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column("feedback", sa.Column("template_id", sa.String(length=120), nullable=True))
    op.create_index(
        "ix_feedback_tenant_template_rating",
        "feedback",
        ["tenant_id", "template_id", "rating", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_tenant_template_rating", table_name="feedback")
    op.drop_column("feedback", "template_id")
    op.drop_column("feedback", "tags")
    op.drop_column("feedback", "duration_ms")
    op.drop_column("feedback", "tools_used")
    op.drop_column("feedback", "prompt_version")
    op.drop_column("feedback", "model")
    op.drop_column("feedback", "domain")
    op.drop_column("feedback", "intent")
