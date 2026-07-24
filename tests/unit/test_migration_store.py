from __future__ import annotations

from reactor.migration.import_ import ImportedRow
from reactor.migration.rollback import RollbackSnapshotRow
from reactor.persistence.migration_store import (
    build_migration_import_exists,
    build_migration_import_insert,
    build_migration_import_list,
    build_rollback_snapshot_insert,
)


def test_migration_import_insert_uses_batch_table_pk_checksum_idempotency() -> None:
    statement = build_migration_import_insert(
        ImportedRow(
            batch_id="batch_1",
            source_table="runtime_settings",
            source_pk="setting_1",
            checksum="sha256:a",
            payload={"key": "a"},
        )
    )
    compiled = statement.compile()
    sql = str(compiled)

    assert "migration_imports" in sql
    assert "ON CONFLICT ON CONSTRAINT uq_migration_imports_source DO NOTHING" in sql
    assert compiled.params["batch_id"] == "batch_1"
    assert compiled.params["source_table"] == "runtime_settings"
    assert compiled.params["source_pk"] == "setting_1"
    assert compiled.params["checksum"] == "sha256:a"
    assert compiled.params["payload"] == {"key": "a"}


def test_migration_import_exists_filters_source_identity_and_checksum() -> None:
    compiled = build_migration_import_exists(
        source_table="runtime_settings",
        source_pk="setting_1",
        checksum="sha256:a",
    ).compile()
    sql = str(compiled)

    assert "migration_imports.source_table =" in sql
    assert "migration_imports.source_pk =" in sql
    assert "migration_imports.checksum =" in sql
    assert compiled.params["source_table_1"] == "runtime_settings"
    assert compiled.params["source_pk_1"] == "setting_1"
    assert compiled.params["checksum_1"] == "sha256:a"


def test_migration_import_list_scopes_batch() -> None:
    compiled = build_migration_import_list(batch_id="batch_1").compile()
    sql = str(compiled)

    assert "migration_imports.batch_id =" in sql
    assert "ORDER BY migration_imports.source_table ASC" in sql
    assert compiled.params["batch_id_1"] == "batch_1"


def test_rollback_snapshot_insert_uses_batch_table_pk_checksum_idempotency() -> None:
    statement = build_rollback_snapshot_insert(
        row=RollbackSnapshotRow(
            target_table="runtime_settings",
            target_pk="setting_1",
            payload={"key": "a", "value": "old"},
        ),
        batch_id="batch_1",
    )
    compiled = statement.compile()
    sql = str(compiled)

    assert "migration_rollback_snapshots" in sql
    assert "ON CONFLICT ON CONSTRAINT uq_migration_rollback_snapshots_target DO NOTHING" in sql
    assert compiled.params["batch_id"] == "batch_1"
    assert compiled.params["target_table"] == "runtime_settings"
    assert compiled.params["target_pk"] == "setting_1"
    assert compiled.params["payload"] == {"key": "a", "value": "old"}
