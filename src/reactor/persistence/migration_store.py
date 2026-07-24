from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.kernel.ids import new_id
from reactor.migration.export import payload_checksum
from reactor.migration.import_ import ImportedRow
from reactor.migration.rollback import RollbackSnapshotRow
from reactor.persistence.models import MigrationImport, MigrationRollbackSnapshot


class SqlAlchemyMigrationImportStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def already_imported(
        self,
        *,
        source_table: str,
        source_pk: str,
        checksum: str,
    ) -> bool:
        async with self._session_factory() as session:
            result = await session.scalar(
                build_migration_import_exists(
                    source_table=source_table,
                    source_pk=source_pk,
                    checksum=checksum,
                )
            )
        return result is not None

    async def import_row(self, row: ImportedRow) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_migration_import_insert(row))

    async def list_imported(self, *, batch_id: str) -> list[ImportedRow]:
        async with self._session_factory() as session:
            rows = await session.scalars(build_migration_import_list(batch_id=batch_id))
            imported = list(rows)
        return [migration_import_row(row) for row in imported]


class SqlAlchemyRollbackSnapshotStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_snapshot(self, *, row: RollbackSnapshotRow, batch_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_rollback_snapshot_insert(row=row, batch_id=batch_id))


def build_migration_import_insert(row: ImportedRow) -> Any:
    return (
        insert(MigrationImport)
        .values(
            id=new_id("migration_import"),
            batch_id=row.batch_id,
            source_table=row.source_table,
            source_pk=row.source_pk,
            checksum=row.checksum,
            payload=row.payload,
        )
        .on_conflict_do_nothing(constraint="uq_migration_imports_source")
    )


def build_migration_import_exists(
    *,
    source_table: str,
    source_pk: str,
    checksum: str,
) -> Any:
    return select(MigrationImport.id).where(
        MigrationImport.source_table == source_table,
        MigrationImport.source_pk == source_pk,
        MigrationImport.checksum == checksum,
    )


def build_migration_import_list(*, batch_id: str) -> Any:
    return (
        select(MigrationImport)
        .where(MigrationImport.batch_id == batch_id)
        .order_by(MigrationImport.source_table.asc(), MigrationImport.source_pk.asc())
    )


def build_rollback_snapshot_insert(*, row: RollbackSnapshotRow, batch_id: str) -> Any:
    return (
        insert(MigrationRollbackSnapshot)
        .values(
            id=new_id("migration_rollback"),
            batch_id=batch_id,
            target_table=row.target_table,
            target_pk=row.target_pk,
            checksum=payload_checksum(row.payload),
            payload=row.payload,
        )
        .on_conflict_do_nothing(constraint="uq_migration_rollback_snapshots_target")
    )


def migration_import_row(row: MigrationImport) -> ImportedRow:
    return ImportedRow(
        batch_id=row.batch_id,
        source_table=row.source_table,
        source_pk=row.source_pk,
        checksum=row.checksum,
        payload=dict(row.payload),
    )
