from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from reactor.migration.export import LegacyRow, payload_checksum
from reactor.migration.import_ import ImportedRow


@dataclass(frozen=True)
class TableParityReport:
    exported_count: int
    imported_count: int
    missing_source_pks: list[str]
    extra_source_pks: list[str]
    checksum_mismatches: list[str]
    sample_source_pks: list[str]

    @property
    def ok(self) -> bool:
        return (
            self.exported_count == self.imported_count
            and not self.missing_source_pks
            and not self.extra_source_pks
            and not self.checksum_mismatches
        )


@dataclass(frozen=True)
class ParityReport:
    tables: dict[str, TableParityReport]

    @property
    def ok(self) -> bool:
        return all(report.ok for report in self.tables.values())


def build_parity_report(
    *,
    exported: list[LegacyRow],
    imported: list[ImportedRow],
    sample_size: int = 10,
) -> ParityReport:
    return build_parity_report_from_checksums(
        exported_checksums=group_exported(exported),
        imported_checksums=group_imported(imported),
        sample_size=sample_size,
    )


def build_parity_report_from_checksums(
    *,
    exported_checksums: dict[str, dict[str, str]],
    imported_checksums: dict[str, dict[str, str]],
    sample_size: int = 10,
) -> ParityReport:
    table_names = sorted(set(exported_checksums) | set(imported_checksums))
    tables = {
        table_name: compare_table(
            exported_checksums.get(table_name, {}),
            imported_checksums.get(table_name, {}),
            sample_size=sample_size,
        )
        for table_name in table_names
    }
    return ParityReport(tables=tables)


def build_imported_parity_report(
    *,
    exported: list[ImportedRow],
    imported: list[ImportedRow],
    sample_size: int = 10,
) -> ParityReport:
    exported_by_table = group_imported(exported)
    imported_by_table = group_imported(imported)
    return build_parity_report_from_checksums(
        exported_checksums=exported_by_table,
        imported_checksums=imported_by_table,
        sample_size=sample_size,
    )


def group_exported(rows: list[LegacyRow]) -> dict[str, dict[str, str]]:
    grouped: dict[str, dict[str, str]] = defaultdict(dict)
    for row in rows:
        grouped[row.source_table][row.source_pk] = payload_checksum(row.payload)
    return dict(grouped)


def group_imported(rows: list[ImportedRow]) -> dict[str, dict[str, str]]:
    grouped: dict[str, dict[str, str]] = defaultdict(dict)
    for row in rows:
        grouped[row.source_table][row.source_pk] = row.checksum
    return dict(grouped)


def compare_table(
    exported: dict[str, str],
    imported: dict[str, str],
    *,
    sample_size: int,
) -> TableParityReport:
    exported_pks = set(exported)
    imported_pks = set(imported)
    common_pks = exported_pks & imported_pks
    checksum_mismatches = [
        source_pk for source_pk in sorted(common_pks) if exported[source_pk] != imported[source_pk]
    ]
    return TableParityReport(
        exported_count=len(exported),
        imported_count=len(imported),
        missing_source_pks=sorted(exported_pks - imported_pks),
        extra_source_pks=sorted(imported_pks - exported_pks),
        checksum_mismatches=checksum_mismatches,
        sample_source_pks=sorted(exported_pks)[: max(0, sample_size)],
    )
