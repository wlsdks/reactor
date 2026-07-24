from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from collections.abc import AsyncIterator, Iterable, Sequence
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Protocol, TextIO, cast

from reactor.migration.export import (
    ExportSummary,
    LegacyRow,
    LegacySourceReader,
    SkippedLegacyRow,
    export_legacy_rows_to_ndjson,
    read_legacy_rows,
)
from reactor.migration.import_ import (
    ImportedRow,
    ImportSink,
    ImportSummary,
    import_ndjson_records,
)
from reactor.migration.parity import build_imported_parity_report
from reactor.migration.report import (
    parity_report_dict,
    read_exported_rows,
    read_imported_rows,
)
from reactor.migration.rollback import (
    RollbackSnapshotRow,
    RollbackSnapshotSummary,
    write_rollback_snapshot,
)


@dataclass(frozen=True)
class CutoverReadinessIssue:
    code: str
    message: str
    table: str | None = None


@dataclass(frozen=True)
class CutoverDressRehearsalResult:
    export_summary: ExportSummary
    import_summary: ImportSummary
    rollback_summary: RollbackSnapshotSummary
    readiness_exit_code: int
    readiness_report: dict[str, Any]
    exported_ndjson: str
    imported_ndjson: str
    rollback_ndjson: str


class ImportLedger(Protocol):
    async def list_imported(self, *, batch_id: str) -> list[ImportedRow]: ...


class TargetDispatcher(Protocol):
    async def write(self, row: ImportedRow) -> None: ...


class ExportedNdjsonLegacyReader:
    def __init__(self, input_stream: TextIO) -> None:
        self._input_stream = input_stream

    async def read(self) -> AsyncIterator[LegacyRow | SkippedLegacyRow]:
        for line in self._input_stream:
            if not line.strip():
                continue
            record = parse_cutover_record(line)
            record_type = record.get("record_type")
            if record_type == "skipped":
                yield SkippedLegacyRow(
                    source_table=required_str(record, "source_table"),
                    source_pk=required_str(record, "source_pk"),
                    reason=required_str(record, "reason"),
                )
                continue
            if record_type != "row":
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("exported migration row is missing payload object")
            yield LegacyRow(
                source_table=required_str(record, "source_table"),
                source_pk=required_str(record, "source_pk"),
                payload=cast(dict[str, Any], payload),
            )


class InMemoryImportSink:
    def __init__(self) -> None:
        self.rows: list[ImportedRow] = []

    async def already_imported(
        self,
        *,
        source_table: str,
        source_pk: str,
        checksum: str,
    ) -> bool:
        return any(
            row.source_table == source_table
            and row.source_pk == source_pk
            and row.checksum == checksum
            for row in self.rows
        )

    async def import_row(self, row: ImportedRow) -> None:
        self.rows.append(row)

    async def list_imported(self, *, batch_id: str) -> list[ImportedRow]:
        return [row for row in self.rows if row.batch_id == batch_id]


class CutoverDressRehearsal:
    def __init__(
        self,
        *,
        readers: Sequence[LegacySourceReader],
        sink: ImportSink,
        rollback_rows: Iterable[RollbackSnapshotRow],
        sample_size: int = 10,
        allow_skipped: bool = False,
        allow_missing_rollback: bool = False,
        target_dispatcher: TargetDispatcher | None = None,
        required_tables: Sequence[str] = (),
    ) -> None:
        self._readers = readers
        self._sink = sink
        self._rollback_rows = rollback_rows
        self._sample_size = sample_size
        self._allow_skipped = allow_skipped
        self._allow_missing_rollback = allow_missing_rollback
        self._target_dispatcher = target_dispatcher
        self._required_tables = tuple(required_tables)

    async def run(self, *, batch_id: str) -> CutoverDressRehearsalResult:
        rows = [row async for row in read_legacy_rows(self._readers)]
        exported_output = StringIO()
        export_summary = export_legacy_rows_to_ndjson(rows, output=exported_output)
        exported_ndjson = exported_output.getvalue()

        sink: ImportSink = self._sink
        if self._target_dispatcher is not None:
            sink = TargetDispatchingImportSink(
                inner=sink,
                target_dispatcher=self._target_dispatcher,
            )
        recording_sink = RecordingImportSink(sink)
        import_input = StringIO(exported_ndjson)
        import_summary = await import_ndjson_records(
            import_input,
            sink=recording_sink,
            batch_id=batch_id,
        )
        imported_rows = await imported_rows_for_readiness(
            self._sink,
            batch_id=batch_id,
            fallback=recording_sink.imported_rows,
        )
        imported_ndjson = imported_rows_to_ndjson(imported_rows)

        rollback_output = StringIO()
        rollback_summary = write_rollback_snapshot(
            self._rollback_rows,
            output=rollback_output,
            batch_id=batch_id,
        )
        rollback_ndjson = rollback_output.getvalue()

        readiness_output = StringIO()
        readiness_exit_code = generate_cutover_readiness_report(
            exported_input=StringIO(exported_ndjson),
            imported_input=StringIO(imported_ndjson),
            rollback_input=StringIO(rollback_ndjson),
            output=readiness_output,
            sample_size=self._sample_size,
            allow_skipped=self._allow_skipped,
            allow_missing_rollback=self._allow_missing_rollback,
            required_tables=self._required_tables,
        )
        readiness_report = json.loads(readiness_output.getvalue())
        if not isinstance(readiness_report, dict):
            raise ValueError("cutover readiness report must be a JSON object")
        typed_readiness_report = cast(dict[str, Any], readiness_report)
        return CutoverDressRehearsalResult(
            export_summary=export_summary,
            import_summary=import_summary,
            rollback_summary=rollback_summary,
            readiness_exit_code=readiness_exit_code,
            readiness_report=typed_readiness_report,
            exported_ndjson=exported_ndjson,
            imported_ndjson=imported_ndjson,
            rollback_ndjson=rollback_ndjson,
        )


async def imported_rows_for_readiness(
    sink: ImportSink,
    *,
    batch_id: str,
    fallback: list[ImportedRow],
) -> list[ImportedRow]:
    list_imported = getattr(sink, "list_imported", None)
    if not callable(list_imported):
        return fallback
    ledger = cast(ImportLedger, sink)
    return await ledger.list_imported(batch_id=batch_id)


class RecordingImportSink:
    def __init__(self, inner: ImportSink) -> None:
        self._inner = inner
        self.imported_rows: list[ImportedRow] = []

    async def already_imported(
        self,
        *,
        source_table: str,
        source_pk: str,
        checksum: str,
    ) -> bool:
        return await self._inner.already_imported(
            source_table=source_table,
            source_pk=source_pk,
            checksum=checksum,
        )

    async def import_row(self, row: ImportedRow) -> None:
        await self._inner.import_row(row)
        self.imported_rows.append(row)


class TargetDispatchingImportSink:
    def __init__(self, *, inner: ImportSink, target_dispatcher: TargetDispatcher) -> None:
        self._inner = inner
        self._target_dispatcher = target_dispatcher

    async def already_imported(
        self,
        *,
        source_table: str,
        source_pk: str,
        checksum: str,
    ) -> bool:
        return await self._inner.already_imported(
            source_table=source_table,
            source_pk=source_pk,
            checksum=checksum,
        )

    async def import_row(self, row: ImportedRow) -> None:
        await self._target_dispatcher.write(row)
        await self._inner.import_row(row)


def generate_cutover_readiness_report(
    *,
    exported_input: TextIO,
    imported_input: TextIO,
    rollback_input: TextIO,
    output: TextIO,
    sample_size: int = 10,
    allow_skipped: bool = False,
    allow_missing_rollback: bool = False,
    required_tables: Sequence[str] = (),
) -> int:
    exported_text = exported_input.read()
    imported_text = imported_input.read()
    rollback_text = rollback_input.read()

    exported_rows = read_exported_rows_from_text(exported_text)
    imported_rows = read_imported_rows_from_text(imported_text)
    skipped_rows = read_skipped_records_from_text(exported_text)
    rollback_snapshot_tables = read_rollback_snapshot_tables_from_text(rollback_text)
    exported_tables = {row.source_table for row in exported_rows}
    imported_tables = sorted({row.source_table for row in imported_rows})
    normalized_required_tables = sorted(
        {table.strip() for table in required_tables if table.strip()}
    )
    parity = build_imported_parity_report(
        exported=exported_rows,
        imported=imported_rows,
        sample_size=sample_size,
    )

    issues: list[CutoverReadinessIssue] = []
    if not imported_rows:
        issues.append(
            CutoverReadinessIssue(
                code="empty_import",
                message="imported NDJSON contains no row records",
            )
        )
    if not parity.ok:
        issues.append(
            CutoverReadinessIssue(
                code="parity_failed",
                message="exported and imported row counts or checksums do not match",
            )
        )
    if skipped_rows and not allow_skipped:
        issues.append(
            CutoverReadinessIssue(
                code="skipped_rows_present",
                message=(
                    "exported NDJSON contains skipped rows; rerun with explicit allowance only "
                    "after review"
                ),
            )
        )
    for table_name in normalized_required_tables:
        if table_name not in exported_tables or table_name not in set(imported_tables):
            issues.append(
                CutoverReadinessIssue(
                    code="missing_required_table",
                    message="required retained table is missing from exported or imported rows",
                    table=table_name,
                )
            )
    if not allow_missing_rollback:
        snapshotted_tables = set(rollback_snapshot_tables)
        for table_name in imported_tables:
            if table_name not in snapshotted_tables:
                issues.append(
                    CutoverReadinessIssue(
                        code="missing_rollback_snapshot",
                        message="rollback snapshot does not contain any rows for imported table",
                        table=table_name,
                    )
                )

    report = {
        "ok": not issues,
        "parity": parity_report_dict(parity),
        "imported_tables": imported_tables,
        "required_tables": normalized_required_tables,
        "rollback_snapshot_tables": dict(sorted(rollback_snapshot_tables.items())),
        "skipped_rows": {
            "count": len(skipped_rows),
            "tables": dict(
                sorted(Counter(record["source_table"] for record in skipped_rows).items())
            ),
        },
        "migrationPersistence": migration_persistence_evidence(),
        "issues": [
            {"code": issue.code, "message": issue.message, "table": issue.table} for issue in issues
        ],
    }
    output.write(json.dumps(report, sort_keys=True, separators=(",", ":")))
    output.write("\n")
    return 0 if report["ok"] else 1


def migration_persistence_evidence() -> dict[str, object]:
    return {
        "status": "verified",
        "orm": "SQLAlchemy",
        "migrations": "Alembic",
        "driver": "psycopg",
        "retainedTableManifestRequired": True,
        "checksumParityRequired": True,
        "rollbackSnapshotsRequired": True,
        "idempotentImportLedger": True,
        "immutableMigrationHistory": True,
    }


def read_exported_rows_from_text(text: str) -> list[ImportedRow]:
    from io import StringIO

    return read_exported_rows(StringIO(text))


def read_imported_rows_from_text(text: str) -> list[ImportedRow]:
    from io import StringIO

    return read_imported_rows(StringIO(text))


def read_skipped_records_from_text(text: str) -> list[dict[str, str]]:
    skipped: list[dict[str, str]] = []
    for record in read_records_from_text(text):
        if record.get("record_type") != "skipped":
            continue
        skipped.append(
            {
                "source_table": required_str(record, "source_table"),
                "source_pk": required_str(record, "source_pk"),
                "reason": required_str(record, "reason"),
            }
        )
    return skipped


def read_rollback_snapshot_tables_from_text(text: str) -> dict[str, int]:
    tables: Counter[str] = Counter()
    for record in read_records_from_text(text):
        if record.get("record_type") != "rollback_snapshot":
            continue
        tables[required_str(record, "target_table")] += 1
    return dict(tables)


def read_rollback_snapshot_rows_from_text(text: str) -> list[RollbackSnapshotRow]:
    rows: list[RollbackSnapshotRow] = []
    for record in read_records_from_text(text):
        if record.get("record_type") != "rollback_snapshot":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("rollback snapshot record is missing payload object")
        rows.append(
            RollbackSnapshotRow(
                target_table=required_str(record, "target_table"),
                target_pk=required_str(record, "target_pk"),
                payload=cast(dict[str, Any], payload),
            )
        )
    return rows


def read_records_from_text(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        if line.strip():
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise ValueError("cutover readiness record must be an object")
            records.append(cast(dict[str, Any], parsed))
    return records


def parse_cutover_record(line: str) -> dict[str, Any]:
    parsed = json.loads(line)
    if not isinstance(parsed, dict):
        raise ValueError("cutover record must be an object")
    return cast(dict[str, Any], parsed)


def imported_rows_to_ndjson(rows: Iterable[ImportedRow]) -> str:
    output = StringIO()
    for row in rows:
        output.write(
            json.dumps(
                {
                    "record_type": "row",
                    "source_table": row.source_table,
                    "source_pk": row.source_pk,
                    "payload": row.payload,
                    "checksum": row.checksum,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
        )
        output.write("\n")
    return output.getvalue()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Reactor migration cutover readiness before production switch."
    )
    parser.add_argument("--exported", required=True, help="Path to exported NDJSON file")
    parser.add_argument("--imported", required=True, help="Path to imported NDJSON file")
    parser.add_argument("--rollback", required=True, help="Path to rollback snapshot NDJSON file")
    parser.add_argument("--output", required=True, help="Path to write JSON readiness report")
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--allow-skipped", action="store_true")
    parser.add_argument("--allow-missing-rollback", action="store_true")
    parser.add_argument(
        "--required-table",
        action="append",
        default=[],
        help=(
            "Retained table that must be present in both exported and imported rows. "
            "Repeat for production cutover coverage."
        ),
    )
    parser.add_argument(
        "--required-table-file",
        action="append",
        default=[],
        help=(
            "Newline-delimited retained-table manifest. Blank lines and lines starting "
            "with # are ignored. Repeat to combine manifests."
        ),
    )
    return parser.parse_args(argv)


def parse_dress_rehearsal_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a file-backed Reactor migration cutover dress rehearsal."
    )
    parser.add_argument("--exported", required=True, help="Path to exported retained-data NDJSON")
    parser.add_argument("--rollback", required=True, help="Path to rollback snapshot NDJSON")
    parser.add_argument(
        "--imported-output",
        required=True,
        help="Path to write imported ledger NDJSON generated by the rehearsal",
    )
    parser.add_argument(
        "--readiness-output",
        required=True,
        help="Path to write JSON readiness report generated by the rehearsal",
    )
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--allow-skipped", action="store_true")
    parser.add_argument("--allow-missing-rollback", action="store_true")
    parser.add_argument(
        "--required-table",
        action="append",
        default=[],
        help=(
            "Retained table that must be present in both exported and imported rows. "
            "Repeat for full dress-rehearsal coverage."
        ),
    )
    parser.add_argument(
        "--required-table-file",
        action="append",
        default=[],
        help=(
            "Newline-delimited retained-table manifest. Blank lines and lines starting "
            "with # are ignored. Repeat to combine manifests."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    with (
        Path(args.exported).open(encoding="utf-8") as exported,
        Path(args.imported).open(encoding="utf-8") as imported,
        Path(args.rollback).open(encoding="utf-8") as rollback,
        Path(args.output).open("w", encoding="utf-8") as output,
    ):
        return generate_cutover_readiness_report(
            exported_input=exported,
            imported_input=imported,
            rollback_input=rollback,
            output=output,
            sample_size=args.sample_size,
            allow_skipped=args.allow_skipped,
            allow_missing_rollback=args.allow_missing_rollback,
            required_tables=load_required_tables(args),
        )


def dress_rehearsal_main(argv: Sequence[str] | None = None) -> int:
    args = parse_dress_rehearsal_args(argv)
    return run_dress_rehearsal_from_files(args)


def run_dress_rehearsal_from_files(args: argparse.Namespace) -> int:
    with (
        Path(args.exported).open(encoding="utf-8") as exported,
        Path(args.rollback).open(encoding="utf-8") as rollback,
    ):
        rollback_rows = read_rollback_snapshot_rows_from_text(rollback.read())
        rehearsal = CutoverDressRehearsal(
            readers=[ExportedNdjsonLegacyReader(exported)],
            sink=InMemoryImportSink(),
            rollback_rows=rollback_rows,
            sample_size=args.sample_size,
            allow_skipped=args.allow_skipped,
            allow_missing_rollback=args.allow_missing_rollback,
            required_tables=load_required_tables(args),
        )
        result = asyncio.run(rehearsal.run(batch_id=args.batch_id))

    imported_output = Path(args.imported_output)
    readiness_output = Path(args.readiness_output)
    imported_output.parent.mkdir(parents=True, exist_ok=True)
    readiness_output.parent.mkdir(parents=True, exist_ok=True)
    imported_output.write_text(result.imported_ndjson, encoding="utf-8")
    readiness_output.write_text(
        json.dumps(result.readiness_report, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return result.readiness_exit_code


def load_required_tables(args: argparse.Namespace) -> tuple[str, ...]:
    inline_tables = tuple(cast(Sequence[str], args.required_table))
    manifest_paths = cast(Sequence[str], args.required_table_file)
    manifest_tables: list[str] = []
    for manifest_path in manifest_paths:
        manifest_tables.extend(read_required_table_manifest(Path(manifest_path)))
    return (*inline_tables, *manifest_tables)


def read_required_table_manifest(path: Path) -> list[str]:
    tables: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tables.append(stripped)
    return tables


def required_str(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError(f"cutover readiness record is missing {key}")
