from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202606270003"
down_revision: str | None = "202606270002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "metric_guard_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("channel", sa.String(length=64), nullable=True),
        sa.Column("stage", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column("reason_class", sa.String(length=128), nullable=True),
        sa.Column("reason_detail", sa.Text(), nullable=True),
        sa.Column("is_output_guard", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "action in ('allowed', 'rejected', 'error')",
            name="ck_metric_guard_events_action",
        ),
    )
    op.create_index(
        "ix_metric_guard_events_input_time",
        "metric_guard_events",
        ["is_output_guard", "time"],
    )
    op.create_index(
        "ix_metric_guard_events_tenant_time",
        "metric_guard_events",
        ["tenant_id", "time"],
    )
    op.create_index(
        "ix_metric_guard_events_stage_action",
        "metric_guard_events",
        ["stage", "action", "time"],
    )


def downgrade() -> None:
    op.drop_index("ix_metric_guard_events_stage_action", table_name="metric_guard_events")
    op.drop_index("ix_metric_guard_events_tenant_time", table_name="metric_guard_events")
    op.drop_index("ix_metric_guard_events_input_time", table_name="metric_guard_events")
    op.drop_table("metric_guard_events")
