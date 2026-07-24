from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "202606280004"
down_revision: str | None = "202606280003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_scheduled_jobs_type", "scheduled_jobs", type_="check")
    op.create_check_constraint(
        "ck_scheduled_jobs_type",
        "scheduled_jobs",
        "job_type in ('MCP_TOOL', 'AGENT', 'PROMPT_LAB_AUTO_OPTIMIZE')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_scheduled_jobs_type", "scheduled_jobs", type_="check")
    op.create_check_constraint(
        "ck_scheduled_jobs_type",
        "scheduled_jobs",
        "job_type in ('MCP_TOOL', 'AGENT')",
    )
