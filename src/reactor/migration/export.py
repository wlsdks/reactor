from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, TextIO


@dataclass(frozen=True)
class LegacyRow:
    source_table: str
    source_pk: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class SkippedLegacyRow:
    source_table: str
    source_pk: str
    reason: str


@dataclass(frozen=True)
class ExportSummary:
    exported: int
    skipped: int


class LegacySourceReader(Protocol):
    def read(self) -> AsyncIterator[LegacyRow | SkippedLegacyRow]: ...


@dataclass(frozen=True)
class ExportedRecord:
    record_type: Literal["row"]
    source_table: str
    source_pk: str
    payload: dict[str, Any]
    checksum: str
    exported_at: str


@dataclass(frozen=True)
class SkippedRecord:
    record_type: Literal["skipped"]
    source_table: str
    source_pk: str
    reason: str
    exported_at: str


async def read_legacy_rows(
    readers: Iterable[LegacySourceReader],
) -> AsyncIterator[LegacyRow | SkippedLegacyRow]:
    for reader in readers:
        async for row in reader.read():
            yield row


def export_legacy_rows_to_ndjson(
    rows: Iterable[LegacyRow | SkippedLegacyRow],
    *,
    output: TextIO,
    exported_at: datetime | None = None,
) -> ExportSummary:
    exported = 0
    skipped = 0
    timestamp = (exported_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    for row in rows:
        if isinstance(row, SkippedLegacyRow):
            output.write(canonical_json(skipped_record(row, exported_at=timestamp)))
            output.write("\n")
            skipped += 1
            continue
        output.write(canonical_json(exported_record(row, exported_at=timestamp)))
        output.write("\n")
        exported += 1
    return ExportSummary(exported=exported, skipped=skipped)


def exported_record(row: LegacyRow, *, exported_at: str) -> dict[str, Any]:
    return {
        "record_type": "row",
        "source_table": row.source_table,
        "source_pk": row.source_pk,
        "payload": row.payload,
        "checksum": payload_checksum(row.payload),
        "exported_at": exported_at,
    }


def skipped_record(row: SkippedLegacyRow, *, exported_at: str) -> dict[str, str]:
    return {
        "record_type": "skipped",
        "source_table": row.source_table,
        "source_pk": row.source_pk,
        "reason": row.reason,
        "exported_at": exported_at,
    }


def payload_checksum(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json(payload).encode()).hexdigest()
    return f"sha256:{digest}"


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
