from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TextIO

from reactor.migration.export import canonical_json, payload_checksum


@dataclass(frozen=True)
class RollbackSnapshotRow:
    target_table: str
    target_pk: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class RollbackSnapshotSummary:
    snapshotted: int


def write_rollback_snapshot(
    rows: Iterable[RollbackSnapshotRow],
    *,
    output: TextIO,
    batch_id: str,
    captured_at: datetime | None = None,
) -> RollbackSnapshotSummary:
    timestamp = (captured_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    snapshotted = 0
    for row in rows:
        output.write(
            canonical_json(
                {
                    "record_type": "rollback_snapshot",
                    "batch_id": batch_id,
                    "target_table": row.target_table,
                    "target_pk": row.target_pk,
                    "payload": row.payload,
                    "checksum": payload_checksum(row.payload),
                    "captured_at": timestamp,
                }
            )
        )
        output.write("\n")
        snapshotted += 1
    return RollbackSnapshotSummary(snapshotted=snapshotted)
