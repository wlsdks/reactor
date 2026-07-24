from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202606270001"
down_revision: str | None = "202606260001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompt_lab_experiments",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("template_id", sa.String(length=64), nullable=False),
        sa.Column("baseline_version_id", sa.String(length=64), nullable=False),
        sa.Column("candidate_version_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("test_queries", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evaluation_config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("judge_model", sa.String(length=128), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.3"),
        sa.Column("repetitions", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("auto_generated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status in ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_prompt_lab_experiments_status",
        ),
    )
    op.create_index(
        "ix_prompt_lab_experiments_tenant_status",
        "prompt_lab_experiments",
        ["tenant_id", "status", "created_at"],
    )
    op.create_index(
        "ix_prompt_lab_experiments_template",
        "prompt_lab_experiments",
        ["tenant_id", "template_id"],
    )

    op.create_table(
        "prompt_lab_trials",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("experiment_id", sa.String(length=64), nullable=False),
        sa.Column("prompt_version_id", sa.String(length=64), nullable=False),
        sa.Column("prompt_version_number", sa.Integer(), nullable=False),
        sa.Column("test_query", sa.JSON(), nullable=False),
        sa.Column("repetition_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("tools_used", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("token_usage", sa.JSON(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evaluations", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "executed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["prompt_lab_experiments.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_prompt_lab_trials_experiment",
        "prompt_lab_trials",
        ["tenant_id", "experiment_id", "executed_at"],
    )

    op.create_table(
        "prompt_lab_reports",
        sa.Column("experiment_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("experiment_name", sa.String(length=200), nullable=False),
        sa.Column(
            "generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("total_trials", sa.Integer(), nullable=False),
        sa.Column("version_summaries", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("recommendation", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["prompt_lab_experiments.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_prompt_lab_reports_tenant_generated",
        "prompt_lab_reports",
        ["tenant_id", "generated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_prompt_lab_reports_tenant_generated", table_name="prompt_lab_reports")
    op.drop_table("prompt_lab_reports")
    op.drop_index("ix_prompt_lab_trials_experiment", table_name="prompt_lab_trials")
    op.drop_table("prompt_lab_trials")
    op.drop_index("ix_prompt_lab_experiments_template", table_name="prompt_lab_experiments")
    op.drop_index("ix_prompt_lab_experiments_tenant_status", table_name="prompt_lab_experiments")
    op.drop_table("prompt_lab_experiments")
