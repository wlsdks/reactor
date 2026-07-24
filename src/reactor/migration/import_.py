from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol, TextIO, cast


@dataclass(frozen=True)
class ImportedRow:
    batch_id: str
    source_table: str
    source_pk: str
    checksum: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ImportSummary:
    imported: int
    duplicates: int
    skipped: int


class ImportSink(Protocol):
    async def already_imported(
        self,
        *,
        source_table: str,
        source_pk: str,
        checksum: str,
    ) -> bool: ...

    async def import_row(self, row: ImportedRow) -> None: ...


async def import_ndjson_records(
    input_stream: TextIO,
    *,
    sink: ImportSink,
    batch_id: str,
) -> ImportSummary:
    imported = 0
    duplicates = 0
    skipped = 0
    for line in input_stream:
        if not line.strip():
            continue
        record = parse_record(line)
        record_type = record.get("record_type")
        if record_type == "skipped":
            skipped += 1
            continue
        if record_type != "row":
            skipped += 1
            continue
        row = imported_row(record, batch_id=batch_id)
        if await sink.already_imported(
            source_table=row.source_table,
            source_pk=row.source_pk,
            checksum=row.checksum,
        ):
            duplicates += 1
            continue
        await sink.import_row(row)
        imported += 1
    return ImportSummary(imported=imported, duplicates=duplicates, skipped=skipped)


def parse_record(line: str) -> dict[str, Any]:
    parsed = json.loads(line)
    if not isinstance(parsed, dict):
        raise ValueError("migration NDJSON record must be an object")
    return cast(dict[str, Any], parsed)


def imported_row(record: dict[str, Any], *, batch_id: str) -> ImportedRow:
    payload = record.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("migration row record is missing payload object")
    return ImportedRow(
        batch_id=batch_id,
        source_table=required_str(record, "source_table"),
        source_pk=required_str(record, "source_pk"),
        checksum=required_str(record, "checksum"),
        payload=cast(dict[str, Any], payload),
    )


def required_str(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError(f"migration record is missing {key}")
