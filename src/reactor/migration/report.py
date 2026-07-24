from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO, cast

from reactor.migration.import_ import ImportedRow, parse_record
from reactor.migration.parity import ParityReport, build_imported_parity_report


def generate_staging_parity_report(
    *,
    exported_input: TextIO,
    imported_input: TextIO,
    output: TextIO,
    sample_size: int = 10,
) -> int:
    report = build_imported_parity_report(
        exported=read_exported_rows(exported_input),
        imported=read_imported_rows(imported_input),
        sample_size=sample_size,
    )
    output.write(json.dumps(parity_report_dict(report), sort_keys=True, separators=(",", ":")))
    output.write("\n")
    return 0 if report.ok else 1


def read_exported_rows(input_stream: TextIO) -> list[ImportedRow]:
    rows: list[ImportedRow] = []
    for line in input_stream:
        if not line.strip():
            continue
        record = parse_record(line)
        if record.get("record_type") != "row":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("exported row record is missing payload object")
        typed_payload = cast(dict[str, Any], payload)
        rows.append(
            ImportedRow(
                batch_id=optional_str(record, "batch_id") or "exported",
                source_table=required_str(record, "source_table"),
                source_pk=required_str(record, "source_pk"),
                checksum=required_str(record, "checksum"),
                payload=typed_payload,
            )
        )
    return rows


def read_imported_rows(input_stream: TextIO) -> list[ImportedRow]:
    rows: list[ImportedRow] = []
    for line in input_stream:
        if not line.strip():
            continue
        record = parse_record(line)
        if record.get("record_type") != "row":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("imported row record is missing payload object")
        typed_payload = cast(dict[str, Any], payload)
        rows.append(
            ImportedRow(
                batch_id=optional_str(record, "batch_id") or "staging",
                source_table=required_str(record, "source_table"),
                source_pk=required_str(record, "source_pk"),
                checksum=required_str(record, "checksum"),
                payload=typed_payload,
            )
        )
    return rows


def parity_report_dict(report: ParityReport) -> dict[str, Any]:
    return {
        "ok": report.ok,
        "tables": {
            table_name: {
                "ok": table_report.ok,
                "exported_count": table_report.exported_count,
                "imported_count": table_report.imported_count,
                "missing_source_pks": table_report.missing_source_pks,
                "extra_source_pks": table_report.extra_source_pks,
                "checksum_mismatches": table_report.checksum_mismatches,
                "sample_source_pks": table_report.sample_source_pks,
            }
            for table_name, table_report in sorted(report.tables.items())
        },
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Reactor migration staging parity report."
    )
    parser.add_argument("--exported", required=True, help="Path to exported NDJSON file")
    parser.add_argument("--imported", required=True, help="Path to imported NDJSON file")
    parser.add_argument("--output", required=True, help="Path to write JSON parity report")
    parser.add_argument("--sample-size", type=int, default=10)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    with (
        Path(args.exported).open(encoding="utf-8") as exported,
        Path(args.imported).open(encoding="utf-8") as imported,
        Path(args.output).open("w", encoding="utf-8") as output,
    ):
        return generate_staging_parity_report(
            exported_input=exported,
            imported_input=imported,
            output=output,
            sample_size=args.sample_size,
        )


def required_str(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError(f"parity report record is missing {key}")


def optional_str(record: dict[str, Any], key: str) -> str | None:
    value = record.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None
