from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "202607230001"
down_revision: str | None = "202606280005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "ck_agent_runs_status"
INTERRUPTED_STATUS_CONSTRAINT = (
    "status in ('queued', 'running', 'interrupted', 'completed', 'failed', 'cancelled')"
)
LEGACY_STATUS_CONSTRAINT = "status in ('queued', 'running', 'completed', 'failed', 'cancelled')"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "agent_runs", type_="check")
    op.create_check_constraint(
        CONSTRAINT_NAME,
        "agent_runs",
        INTERRUPTED_STATUS_CONSTRAINT,
    )


def downgrade() -> None:
    op.execute("UPDATE agent_runs SET status = 'failed' WHERE status = 'interrupted'")
    op.drop_constraint(CONSTRAINT_NAME, "agent_runs", type_="check")
    op.create_check_constraint(
        CONSTRAINT_NAME,
        "agent_runs",
        LEGACY_STATUS_CONSTRAINT,
    )
