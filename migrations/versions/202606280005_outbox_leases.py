from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202606280005"
down_revision: str | None = "202606280004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("outbox_events", sa.Column("lease_owner", sa.String(length=128), nullable=True))
    op.add_column(
        "outbox_events",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_outbox_events_lease",
        "outbox_events",
        ["tenant_id", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_lease", table_name="outbox_events")
    op.drop_column("outbox_events", "lease_expires_at")
    op.drop_column("outbox_events", "lease_owner")
