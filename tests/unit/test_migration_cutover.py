from __future__ import annotations

import json
from collections.abc import AsyncIterator
from io import StringIO
from pathlib import Path

from reactor.migration.cutover import (
    CutoverDressRehearsal,
    dress_rehearsal_main,
    generate_cutover_readiness_report,
    read_required_table_manifest,
)
from reactor.migration.export import LegacyRow, payload_checksum
from reactor.migration.import_ import ImportedRow
from reactor.migration.rollback import RollbackSnapshotRow


async def test_cutover_dress_rehearsal_exports_imports_snapshots_and_reports_readiness() -> None:
    rehearsal = CutoverDressRehearsal(
        readers=[
            StaticLegacyReader(
                [
                    LegacyRow(
                        source_table="runtime_settings",
                        source_pk="setting_1",
                        payload={"key": "agent.timeout", "value": "30"},
                    )
                ]
            )
        ],
        sink=RecordingImportSink(),
        rollback_rows=[
            RollbackSnapshotRow(
                target_table="runtime_settings",
                target_pk="setting_1",
                payload={"key": "agent.timeout", "value": "15"},
            )
        ],
    )

    result = await rehearsal.run(batch_id="batch_1")

    assert result.export_summary.exported == 1
    assert result.import_summary.imported == 1
    assert result.rollback_summary.snapshotted == 1
    assert result.readiness_exit_code == 0
    assert result.readiness_report["ok"] is True
    assert result.readiness_report["imported_tables"] == ["runtime_settings"]
    assert result.exported_ndjson.count('"record_type":"row"') == 1
    assert result.imported_ndjson.count('"record_type":"row"') == 1
    assert result.rollback_ndjson.count('"record_type":"rollback_snapshot"') == 1


async def test_cutover_dress_rehearsal_fails_when_rollback_snapshot_is_missing() -> None:
    rehearsal = CutoverDressRehearsal(
        readers=[
            StaticLegacyReader(
                [
                    LegacyRow(
                        source_table="runtime_settings",
                        source_pk="setting_1",
                        payload={"key": "agent.timeout", "value": "30"},
                    )
                ]
            )
        ],
        sink=RecordingImportSink(),
        rollback_rows=[],
    )

    result = await rehearsal.run(batch_id="batch_1")

    assert result.readiness_exit_code == 1
    assert result.readiness_report["ok"] is False
    assert result.readiness_report["issues"] == [
        {
            "code": "missing_rollback_snapshot",
            "message": "rollback snapshot does not contain any rows for imported table",
            "table": "runtime_settings",
        }
    ]


async def test_cutover_dress_rehearsal_uses_existing_import_ledger_for_idempotent_rerun() -> None:
    existing = ImportedRow(
        batch_id="batch_1",
        source_table="runtime_settings",
        source_pk="setting_1",
        checksum=payload_checksum({"key": "agent.timeout", "value": "30"}),
        payload={"key": "agent.timeout", "value": "30"},
    )
    rehearsal = CutoverDressRehearsal(
        readers=[
            StaticLegacyReader(
                [
                    LegacyRow(
                        source_table="runtime_settings",
                        source_pk="setting_1",
                        payload={"key": "agent.timeout", "value": "30"},
                    )
                ]
            )
        ],
        sink=LedgerBackedImportSink([existing]),
        rollback_rows=[
            RollbackSnapshotRow(
                target_table="runtime_settings",
                target_pk="setting_1",
                payload={"key": "agent.timeout", "value": "15"},
            )
        ],
    )

    result = await rehearsal.run(batch_id="batch_1")

    assert result.import_summary.imported == 0
    assert result.import_summary.duplicates == 1
    assert result.readiness_exit_code == 0
    assert result.readiness_report["ok"] is True


async def test_cutover_dress_rehearsal_applies_rows_to_target_dispatcher_before_ledger() -> None:
    sink = RecordingImportSink()
    dispatcher = RecordingTargetDispatcher()
    rehearsal = CutoverDressRehearsal(
        readers=[
            StaticLegacyReader(
                [
                    LegacyRow(
                        source_table="runtime_settings",
                        source_pk="setting_1",
                        payload={"key": "agent.timeout", "value": "30"},
                    )
                ]
            )
        ],
        sink=sink,
        rollback_rows=[
            RollbackSnapshotRow(
                target_table="runtime_settings",
                target_pk="setting_1",
                payload={"key": "agent.timeout", "value": "15"},
            )
        ],
        target_dispatcher=dispatcher,
    )

    result = await rehearsal.run(batch_id="batch_1")

    assert result.readiness_exit_code == 0
    assert [row.source_pk for row in dispatcher.rows] == ["setting_1"]
    assert [row.source_pk for row in sink.rows] == ["setting_1"]


async def test_cutover_dress_rehearsal_does_not_mark_target_failure_imported() -> None:
    sink = RecordingImportSink()
    dispatcher = FailingTargetDispatcher()
    rehearsal = CutoverDressRehearsal(
        readers=[
            StaticLegacyReader(
                [
                    LegacyRow(
                        source_table="runtime_settings",
                        source_pk="setting_1",
                        payload={"key": "agent.timeout", "value": "30"},
                    )
                ]
            )
        ],
        sink=sink,
        rollback_rows=[
            RollbackSnapshotRow(
                target_table="runtime_settings",
                target_pk="setting_1",
                payload={"key": "agent.timeout", "value": "15"},
            )
        ],
        target_dispatcher=dispatcher,
    )

    try:
        await rehearsal.run(batch_id="batch_1")
    except RuntimeError as exc:
        assert str(exc) == "target write failed"
    else:
        raise AssertionError("target dispatcher failure should stop the rehearsal")

    assert sink.rows == []


def test_dress_rehearsal_cli_writes_imported_ledger_and_readiness_report(
    tmp_path: Path,
) -> None:
    exported = tmp_path / "exported.ndjson"
    rollback = tmp_path / "rollback.ndjson"
    imported = tmp_path / "reports" / "migration" / "imported.ndjson"
    readiness = tmp_path / "reports" / "migration" / "readiness.json"
    exported.write_text(
        (
            '{"checksum":"sha256:a","payload":{"name":"Support"},"record_type":"row",'
            '"source_pk":"bot_1","source_table":"slack_bot_instances"}\n'
        ),
        encoding="utf-8",
    )
    rollback.write_text(
        (
            '{"checksum":"sha256:old","payload":{"name":"Old"},'
            '"record_type":"rollback_snapshot","target_pk":"bot_1",'
            '"target_table":"slack_bot_instances"}\n'
        ),
        encoding="utf-8",
    )

    exit_code = dress_rehearsal_main(
        [
            "--exported",
            str(exported),
            "--rollback",
            str(rollback),
            "--imported-output",
            str(imported),
            "--readiness-output",
            str(readiness),
            "--batch-id",
            "batch_1",
        ]
    )

    assert exit_code == 0
    assert '"record_type":"row"' in imported.read_text(encoding="utf-8")
    readiness_report = json.loads(readiness.read_text(encoding="utf-8"))
    assert readiness_report["ok"] is True
    assert readiness_report["imported_tables"] == ["slack_bot_instances"]
    assert readiness_report["migrationPersistence"] == {
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


def test_dress_rehearsal_cli_fails_when_required_table_is_missing(tmp_path: Path) -> None:
    exported = tmp_path / "exported.ndjson"
    rollback = tmp_path / "rollback.ndjson"
    imported = tmp_path / "imported.ndjson"
    readiness = tmp_path / "readiness.json"
    exported.write_text(
        (
            '{"checksum":"sha256:a","payload":{"name":"Support"},"record_type":"row",'
            '"source_pk":"bot_1","source_table":"slack_bot_instances"}\n'
        ),
        encoding="utf-8",
    )
    rollback.write_text(
        (
            '{"checksum":"sha256:old","payload":{"name":"Old"},'
            '"record_type":"rollback_snapshot","target_pk":"bot_1",'
            '"target_table":"slack_bot_instances"}\n'
        ),
        encoding="utf-8",
    )

    exit_code = dress_rehearsal_main(
        [
            "--exported",
            str(exported),
            "--rollback",
            str(rollback),
            "--imported-output",
            str(imported),
            "--readiness-output",
            str(readiness),
            "--batch-id",
            "batch_1",
            "--required-table",
            "slack_bot_instances",
            "--required-table",
            "agent_runs",
        ]
    )

    readiness_report = json.loads(readiness.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert readiness_report["issues"] == [
        {
            "code": "missing_required_table",
            "message": "required retained table is missing from exported or imported rows",
            "table": "agent_runs",
        }
    ]


def test_dress_rehearsal_cli_loads_required_tables_from_manifest_file(tmp_path: Path) -> None:
    exported = tmp_path / "exported.ndjson"
    rollback = tmp_path / "rollback.ndjson"
    imported = tmp_path / "imported.ndjson"
    readiness = tmp_path / "readiness.json"
    required_tables = tmp_path / "required-tables.txt"
    exported.write_text(
        (
            '{"checksum":"sha256:a","payload":{"name":"Support"},"record_type":"row",'
            '"source_pk":"bot_1","source_table":"slack_bot_instances"}\n'
        ),
        encoding="utf-8",
    )
    rollback.write_text(
        (
            '{"checksum":"sha256:old","payload":{"name":"Old"},'
            '"record_type":"rollback_snapshot","target_pk":"bot_1",'
            '"target_table":"slack_bot_instances"}\n'
        ),
        encoding="utf-8",
    )
    required_tables.write_text("slack_bot_instances\nagent_runs\n", encoding="utf-8")

    exit_code = dress_rehearsal_main(
        [
            "--exported",
            str(exported),
            "--rollback",
            str(rollback),
            "--imported-output",
            str(imported),
            "--readiness-output",
            str(readiness),
            "--batch-id",
            "batch_1",
            "--required-table-file",
            str(required_tables),
        ]
    )

    readiness_report = json.loads(readiness.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert readiness_report["required_tables"] == ["agent_runs", "slack_bot_instances"]
    assert readiness_report["issues"] == [
        {
            "code": "missing_required_table",
            "message": "required retained table is missing from exported or imported rows",
            "table": "agent_runs",
        }
    ]


def test_cutover_readiness_fails_when_parity_report_fails() -> None:
    output = StringIO()

    exit_code = generate_cutover_readiness_report(
        exported_input=StringIO(
            "\n".join(
                [
                    (
                        '{"checksum":"sha256:expected","payload":{"name":"Support"},'
                        '"record_type":"row","source_pk":"bot_1",'
                        '"source_table":"slack_bot_instances"}'
                    )
                ]
            )
        ),
        imported_input=StringIO(""),
        rollback_input=StringIO(
            '{"checksum":"sha256:old","payload":{"name":"Old"},"record_type":"rollback_snapshot",'
            '"target_pk":"bot_1","target_table":"slack_bot_instances"}\n'
        ),
        output=output,
    )

    report = json.loads(output.getvalue())
    assert exit_code == 1
    assert report["ok"] is False
    assert report["parity"]["ok"] is False
    assert report["issues"] == [
        {
            "code": "empty_import",
            "message": "imported NDJSON contains no row records",
            "table": None,
        },
        {
            "code": "parity_failed",
            "message": "exported and imported row counts or checksums do not match",
            "table": None,
        },
    ]


def test_cutover_readiness_fails_on_skipped_rows_by_default() -> None:
    output = StringIO()

    exit_code = generate_cutover_readiness_report(
        exported_input=StringIO(
            "\n".join(
                [
                    (
                        '{"checksum":"sha256:a","payload":{"name":"Support"},'
                        '"record_type":"row","source_pk":"bot_1",'
                        '"source_table":"slack_bot_instances"}'
                    ),
                    (
                        '{"reason":"legacy attachment","record_type":"skipped",'
                        '"source_pk":"msg_1","source_table":"conversation_messages"}'
                    ),
                ]
            )
        ),
        imported_input=StringIO(
            '{"checksum":"sha256:a","payload":{"name":"Support"},"record_type":"row",'
            '"source_pk":"bot_1","source_table":"slack_bot_instances"}\n'
        ),
        rollback_input=StringIO(
            '{"checksum":"sha256:old","payload":{"name":"Old"},"record_type":"rollback_snapshot",'
            '"target_pk":"bot_1","target_table":"slack_bot_instances"}\n'
        ),
        output=output,
    )

    report = json.loads(output.getvalue())
    assert exit_code == 1
    assert report["skipped_rows"]["count"] == 1
    assert report["issues"] == [
        {
            "code": "skipped_rows_present",
            "message": (
                "exported NDJSON contains skipped rows; rerun with explicit allowance only "
                "after review"
            ),
            "table": None,
        }
    ]


def test_cutover_readiness_fails_when_rollback_snapshot_table_is_missing() -> None:
    output = StringIO()

    exit_code = generate_cutover_readiness_report(
        exported_input=StringIO(
            '{"checksum":"sha256:a","payload":{"name":"Support"},"record_type":"row",'
            '"source_pk":"bot_1","source_table":"slack_bot_instances"}\n'
        ),
        imported_input=StringIO(
            '{"checksum":"sha256:a","payload":{"name":"Support"},"record_type":"row",'
            '"source_pk":"bot_1","source_table":"slack_bot_instances"}\n'
        ),
        rollback_input=StringIO(""),
        output=output,
    )

    report = json.loads(output.getvalue())
    assert exit_code == 1
    assert report["issues"] == [
        {
            "code": "missing_rollback_snapshot",
            "message": "rollback snapshot does not contain any rows for imported table",
            "table": "slack_bot_instances",
        }
    ]


def test_cutover_readiness_fails_when_required_retained_table_is_missing() -> None:
    output = StringIO()

    exit_code = generate_cutover_readiness_report(
        exported_input=StringIO(
            '{"checksum":"sha256:a","payload":{"name":"Support"},"record_type":"row",'
            '"source_pk":"bot_1","source_table":"slack_bot_instances"}\n'
        ),
        imported_input=StringIO(
            '{"checksum":"sha256:a","payload":{"name":"Support"},"record_type":"row",'
            '"source_pk":"bot_1","source_table":"slack_bot_instances"}\n'
        ),
        rollback_input=StringIO(
            '{"checksum":"sha256:old","payload":{"name":"Old"},"record_type":"rollback_snapshot",'
            '"target_pk":"bot_1","target_table":"slack_bot_instances"}\n'
        ),
        output=output,
        required_tables=("slack_bot_instances", "agent_runs"),
    )

    report = json.loads(output.getvalue())
    assert exit_code == 1
    assert report["required_tables"] == ["agent_runs", "slack_bot_instances"]
    assert report["issues"] == [
        {
            "code": "missing_required_table",
            "message": "required retained table is missing from exported or imported rows",
            "table": "agent_runs",
        }
    ]


def test_cutover_readiness_passes_when_parity_and_rollback_are_complete() -> None:
    output = StringIO()

    exit_code = generate_cutover_readiness_report(
        exported_input=StringIO(
            '{"checksum":"sha256:a","payload":{"name":"Support"},"record_type":"row",'
            '"source_pk":"bot_1","source_table":"slack_bot_instances"}\n'
        ),
        imported_input=StringIO(
            '{"checksum":"sha256:a","payload":{"name":"Support"},"record_type":"row",'
            '"source_pk":"bot_1","source_table":"slack_bot_instances"}\n'
        ),
        rollback_input=StringIO(
            '{"checksum":"sha256:old","payload":{"name":"Old"},"record_type":"rollback_snapshot",'
            '"target_pk":"bot_1","target_table":"slack_bot_instances"}\n'
        ),
        output=output,
    )

    report = json.loads(output.getvalue())
    assert exit_code == 0
    assert report["ok"] is True
    assert report["imported_tables"] == ["slack_bot_instances"]
    assert report["rollback_snapshot_tables"] == {"slack_bot_instances": 1}
    assert report["issues"] == []


def test_cutover_readiness_cli_fails_when_required_table_is_missing(tmp_path: Path) -> None:
    exported = tmp_path / "exported.ndjson"
    imported = tmp_path / "imported.ndjson"
    rollback = tmp_path / "rollback.ndjson"
    readiness = tmp_path / "readiness.json"
    exported.write_text(
        (
            '{"checksum":"sha256:a","payload":{"name":"Support"},"record_type":"row",'
            '"source_pk":"bot_1","source_table":"slack_bot_instances"}\n'
        ),
        encoding="utf-8",
    )
    imported.write_text(exported.read_text(encoding="utf-8"), encoding="utf-8")
    rollback.write_text(
        (
            '{"checksum":"sha256:old","payload":{"name":"Old"},'
            '"record_type":"rollback_snapshot","target_pk":"bot_1",'
            '"target_table":"slack_bot_instances"}\n'
        ),
        encoding="utf-8",
    )

    from reactor.migration.cutover import main

    exit_code = main(
        [
            "--exported",
            str(exported),
            "--imported",
            str(imported),
            "--rollback",
            str(rollback),
            "--output",
            str(readiness),
            "--required-table",
            "slack_bot_instances",
            "--required-table",
            "agent_runs",
        ]
    )

    report = json.loads(readiness.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["issues"][0]["code"] == "missing_required_table"
    assert report["issues"][0]["table"] == "agent_runs"


def test_cutover_readiness_cli_loads_required_tables_from_manifest_file(
    tmp_path: Path,
) -> None:
    exported = tmp_path / "exported.ndjson"
    imported = tmp_path / "imported.ndjson"
    rollback = tmp_path / "rollback.ndjson"
    required_tables = tmp_path / "required-tables.txt"
    readiness = tmp_path / "readiness.json"
    exported.write_text(
        (
            '{"checksum":"sha256:a","payload":{"name":"Support"},"record_type":"row",'
            '"source_pk":"bot_1","source_table":"slack_bot_instances"}\n'
        ),
        encoding="utf-8",
    )
    imported.write_text(exported.read_text(encoding="utf-8"), encoding="utf-8")
    rollback.write_text(
        (
            '{"checksum":"sha256:old","payload":{"name":"Old"},'
            '"record_type":"rollback_snapshot","target_pk":"bot_1",'
            '"target_table":"slack_bot_instances"}\n'
        ),
        encoding="utf-8",
    )
    required_tables.write_text(
        "# retained migration tables\nslack_bot_instances\n\nagent_runs\n",
        encoding="utf-8",
    )

    from reactor.migration.cutover import main

    exit_code = main(
        [
            "--exported",
            str(exported),
            "--imported",
            str(imported),
            "--rollback",
            str(rollback),
            "--output",
            str(readiness),
            "--required-table-file",
            str(required_tables),
        ]
    )

    report = json.loads(readiness.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["required_tables"] == ["agent_runs", "slack_bot_instances"]
    assert report["issues"][0]["code"] == "missing_required_table"
    assert report["issues"][0]["table"] == "agent_runs"


def test_retained_table_manifest_contains_core_cutover_tables() -> None:
    tables = set(read_required_table_manifest(Path("docs/migration/retained-table-manifest.txt")))

    assert {
        "agent_runs",
        "agent_run_events",
        "runtime_settings",
        "slack_bot_instances",
        "mcp_servers",
        "a2a_tasks",
        "rag_chunks",
        "memory_items",
        "usage_ledger",
    } <= tables


def test_cutover_readiness_can_explicitly_allow_skipped_and_missing_rollback() -> None:
    output = StringIO()

    exit_code = generate_cutover_readiness_report(
        exported_input=StringIO(
            "\n".join(
                [
                    (
                        '{"checksum":"sha256:a","payload":{"name":"Support"},'
                        '"record_type":"row","source_pk":"bot_1",'
                        '"source_table":"slack_bot_instances"}'
                    ),
                    (
                        '{"reason":"not retained","record_type":"skipped",'
                        '"source_pk":"old_1","source_table":"legacy_only"}'
                    ),
                ]
            )
        ),
        imported_input=StringIO(
            '{"checksum":"sha256:a","payload":{"name":"Support"},"record_type":"row",'
            '"source_pk":"bot_1","source_table":"slack_bot_instances"}\n'
        ),
        rollback_input=StringIO(""),
        output=output,
        allow_skipped=True,
        allow_missing_rollback=True,
    )

    report = json.loads(output.getvalue())
    assert exit_code == 0
    assert report["ok"] is True
    assert report["skipped_rows"]["count"] == 1


class StaticLegacyReader:
    def __init__(self, rows: list[LegacyRow]) -> None:
        self._rows = rows

    async def read(self) -> AsyncIterator[LegacyRow]:
        for row in self._rows:
            yield row


class RecordingImportSink:
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


class LedgerBackedImportSink(RecordingImportSink):
    def __init__(self, rows: list[ImportedRow]) -> None:
        super().__init__()
        self.rows = rows.copy()

    async def list_imported(self, *, batch_id: str) -> list[ImportedRow]:
        return [row for row in self.rows if row.batch_id == batch_id]


class RecordingTargetDispatcher:
    def __init__(self) -> None:
        self.rows: list[ImportedRow] = []

    async def write(self, row: ImportedRow) -> None:
        self.rows.append(row)


class FailingTargetDispatcher:
    async def write(self, row: ImportedRow) -> None:
        del row
        raise RuntimeError("target write failed")
