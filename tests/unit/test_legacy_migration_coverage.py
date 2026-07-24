from __future__ import annotations

import re
from pathlib import Path

from reactor.migration.legacy_coverage import SPRING_V6_1_RETAINED_TABLE_COVERAGE


def test_spring_v6_1_retained_tables_have_python_source_and_target_coverage() -> None:
    source_reader_tables = _source_reader_tables()
    target_writer_tables = _target_writer_tables()

    missing_source_readers = sorted(
        coverage.python_source_table
        for coverage in SPRING_V6_1_RETAINED_TABLE_COVERAGE
        if coverage.python_source_table not in source_reader_tables
    )
    missing_target_writers = sorted(
        target_table
        for coverage in SPRING_V6_1_RETAINED_TABLE_COVERAGE
        for target_table in coverage.python_target_tables
        if target_table not in target_writer_tables
    )

    assert missing_source_readers == []
    assert missing_target_writers == []


def test_spring_v6_1_retained_table_manifest_has_no_ambiguous_source_rows() -> None:
    legacy_tables = [coverage.legacy_table for coverage in SPRING_V6_1_RETAINED_TABLE_COVERAGE]

    assert legacy_tables == sorted(set(legacy_tables))
    assert all(coverage.python_target_tables for coverage in SPRING_V6_1_RETAINED_TABLE_COVERAGE)


def test_full_backup_retained_table_manifest_matches_python_migration_coverage() -> None:
    manifest_tables = _retained_table_manifest_tables()
    coverage_tables = {
        target_table
        for coverage in SPRING_V6_1_RETAINED_TABLE_COVERAGE
        for target_table in coverage.python_target_tables
    }
    target_writer_tables = _target_writer_tables()

    assert manifest_tables == sorted(target_writer_tables)
    assert coverage_tables.issubset(set(manifest_tables))


def _source_reader_tables() -> set[str]:
    source = Path("src/reactor/migration/source_readers.py").read_text(encoding="utf-8")
    return set(re.findall(r'source_table="([^"]+)"', source))


def _target_writer_tables() -> set[str]:
    source = Path("src/reactor/migration/targets.py").read_text(encoding="utf-8")
    return set(re.findall(r'target_table = "([^"]+)"', source))


def _retained_table_manifest_tables() -> list[str]:
    return [
        line.strip()
        for line in Path("docs/migration/retained-table-manifest.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.startswith("#")
    ]
