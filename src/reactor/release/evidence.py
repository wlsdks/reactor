from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from reactor.release.readiness import (
    RELEASE_EVIDENCE_REQUIREMENTS,
    current_git_commit,
    write_report,
)

GateResult = tuple[str, Path, str]
CompositeGateResult = tuple[str, tuple[Path, ...], str]
ReleaseEvidence = dict[str, dict[str, str]]
REQUIRED_GATE_SMOKE_CHECKS: dict[str, tuple[str, ...]] = {
    "live_slack_workspace_smoke": ("approval_block_contract",),
}
REQUIRED_GATE_SUPPORTING_REPORTS: frozenset[str] = frozenset(
    {
        "full_backup_db_api_dress_rehearsal",
        "full_backup_db_dress_rehearsal",
    }
)


def build_release_evidence(
    gate_results: Sequence[GateResult],
    *,
    verified_at: str,
    scope: str,
    git_commit: str | None = None,
) -> ReleaseEvidence:
    evidence: ReleaseEvidence = {}
    for gate_code, report_path, evidence_uri in gate_results:
        validate_gate_scope(gate_code=gate_code, scope=scope)
        report = read_json_object(report_path)
        failure = smoke_failure_for_gate(gate_code=gate_code, report=report)
        status = "passed" if failure is None else "failed"
        item = {
            "status": status,
            "scope": scope,
            "evidence_uri": evidence_uri,
            "verified_at": verified_at,
            **git_commit_field(git_commit),
        }
        if failure is not None:
            item["failure"] = failure
        evidence[gate_code] = item
    return evidence


def build_composite_release_evidence(
    gate_results: Sequence[CompositeGateResult],
    *,
    verified_at: str,
    scope: str,
    git_commit: str | None = None,
) -> ReleaseEvidence:
    evidence: ReleaseEvidence = {}
    for gate_code, report_paths, evidence_uri in gate_results:
        validate_gate_scope(gate_code=gate_code, scope=scope)
        reports = [read_json_object(path) for path in report_paths]
        failures = [
            failure
            for report in reports
            if (failure := smoke_failure_for_gate(gate_code=gate_code, report=report)) is not None
        ]
        status = "passed" if not failures else "failed"
        item = {
            "status": status,
            "scope": scope,
            "evidence_uri": evidence_uri,
            "verified_at": verified_at,
            **git_commit_field(git_commit),
        }
        if failures:
            item["failure"] = failures[0]
        evidence[gate_code] = item
    return evidence


def build_release_evidence_from_smoke_run(
    smoke_run_report: dict[str, Any],
    *,
    verified_at: str,
    git_commit: str | None = None,
) -> ReleaseEvidence:
    evidence: ReleaseEvidence = {}
    raw_steps = smoke_run_report.get("steps")
    if not isinstance(raw_steps, list):
        return evidence
    for raw_step in cast(list[object], raw_steps):
        if not isinstance(raw_step, dict):
            continue
        step = cast(dict[str, object], raw_step)
        if step.get("status") != "passed":
            continue
        if step.get("release_gate_closer") is not True:
            continue
        gate_code = string_field(step, "code")
        scope = string_field(step, "evidence_scope")
        evidence_uri = string_field(step, "evidence_uri")
        if gate_code not in RELEASE_EVIDENCE_REQUIREMENTS:
            continue
        validate_gate_scope(gate_code=gate_code, scope=scope)
        if not evidence_uri:
            continue
        if smoke_failure_for_gate(gate_code=gate_code, report=smoke_run_step_report(step)):
            continue
        if gate_code in REQUIRED_GATE_SUPPORTING_REPORTS and not supporting_reports_passed(step):
            continue
        evidence[gate_code] = {
            "status": "passed",
            "scope": scope,
            "evidence_uri": evidence_uri,
            "verified_at": verified_at,
            **git_commit_field(git_commit),
        }
    return dict(sorted(evidence.items()))


def git_commit_field(git_commit: str | None) -> dict[str, str]:
    clean = git_commit.strip() if git_commit else ""
    return {"git_commit": clean} if clean else {}


def merge_release_evidence(
    existing_items: Sequence[ReleaseEvidence],
    latest: ReleaseEvidence,
) -> ReleaseEvidence:
    merged: ReleaseEvidence = {}
    for existing in existing_items:
        merged.update(existing)
    merged.update(latest)
    return dict(sorted(merged.items()))


def smoke_status(report: dict[str, Any]) -> str:
    if report.get("ok") is True:
        return "passed"
    if report.get("status") == "passed":
        return "passed"
    return "failed"


def smoke_failure(report: dict[str, Any]) -> str:
    error = report.get("error")
    if isinstance(error, str) and error.strip():
        return error
    status = report.get("status")
    if isinstance(status, str) and status.strip() and status != "passed":
        return status
    return "smoke report did not pass"


def smoke_failure_for_gate(*, gate_code: str, report: dict[str, Any]) -> str | None:
    if smoke_status(report) != "passed":
        return smoke_failure(report)
    for check_name in REQUIRED_GATE_SMOKE_CHECKS.get(gate_code, ()):
        if smoke_check_status(report, check_name) != "passed":
            return f"required smoke check {check_name} did not pass"
    return None


def smoke_check_status(report: dict[str, Any], check_name: str) -> str:
    checks = report.get("checks")
    if not isinstance(checks, dict):
        return ""
    typed_checks = cast(dict[str, object], checks)
    raw_check = typed_checks.get(check_name)
    if not isinstance(raw_check, dict):
        return ""
    typed_check = cast(dict[str, object], raw_check)
    status = typed_check.get("status")
    return status if isinstance(status, str) else ""


def smoke_run_step_report(step: dict[str, object]) -> dict[str, Any]:
    report: dict[str, Any] = {"status": step.get("status")}
    checks = step.get("checks")
    if isinstance(checks, dict):
        report["checks"] = cast(dict[str, object], checks)
    return report


def step_report_paths(step: dict[str, object]) -> tuple[str, ...]:
    raw_report_paths = step.get("report_paths")
    if not isinstance(raw_report_paths, list):
        return ()
    return tuple(
        value.strip()
        for value in cast(list[object], raw_report_paths)
        if isinstance(value, str) and value.strip()
    )


def supporting_reports_passed(step: dict[str, object]) -> bool:
    report_paths = step_report_paths(step)
    if not report_paths:
        return False
    try:
        reports = [read_json_object(Path(report_path)) for report_path in report_paths]
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return all(smoke_status(report) == "passed" for report in reports) and all(
        supporting_report_contract_passed(gate_code=string_field(step, "code"), report=report)
        for report in reports
    )


def supporting_report_contract_passed(*, gate_code: str, report: dict[str, Any]) -> bool:
    if gate_code == "full_backup_db_dress_rehearsal":
        return migration_persistence_contract_passed(report)
    if gate_code == "full_backup_db_api_dress_rehearsal":
        if "apiBoundary" in evidence_mapping(report):
            return True
        return migration_persistence_contract_passed(report)
    return True


def evidence_mapping(report: dict[str, Any]) -> dict[str, object]:
    evidence = report.get("evidence")
    return cast(dict[str, object], evidence) if isinstance(evidence, dict) else {}


def migration_persistence_contract_passed(report: dict[str, Any]) -> bool:
    persistence = report.get("migrationPersistence")
    if not isinstance(persistence, dict):
        return False
    typed_persistence = cast(dict[str, object], persistence)
    expected_text_fields = {
        "status": "verified",
        "orm": "SQLAlchemy",
        "migrations": "Alembic",
        "driver": "psycopg",
    }
    for field_name, expected_value in expected_text_fields.items():
        if typed_persistence.get(field_name) != expected_value:
            return False
    for field_name in (
        "retainedTableManifestRequired",
        "checksumParityRequired",
        "rollbackSnapshotsRequired",
        "idempotentImportLedger",
        "immutableMigrationHistory",
    ):
        if typed_persistence.get(field_name) is not True:
            return False
    return True


def first_smoke_failure(reports: Sequence[dict[str, Any]]) -> str:
    for report in reports:
        if smoke_status(report) != "passed":
            return smoke_failure(report)
    return "composite smoke report did not pass"


def parse_gate_result(value: str) -> GateResult:
    gate_code, report_path, evidence_uri = split_gate_result(value)
    if gate_code not in RELEASE_EVIDENCE_REQUIREMENTS:
        raise ValueError(f"unknown release gate code: {gate_code}")
    if not evidence_uri.strip():
        raise ValueError("gate result evidence_uri must not be blank")
    return gate_code, Path(report_path), evidence_uri


def parse_composite_gate_result(value: str) -> CompositeGateResult:
    gate_code, report_paths, evidence_uri = split_gate_result(value)
    if gate_code not in RELEASE_EVIDENCE_REQUIREMENTS:
        raise ValueError(f"unknown release gate code: {gate_code}")
    paths = tuple(Path(report_path.strip()) for report_path in report_paths.split(","))
    if not paths or any(not str(path).strip() for path in paths):
        raise ValueError("composite gate result report paths must not be blank")
    if not evidence_uri.strip():
        raise ValueError("composite gate result evidence_uri must not be blank")
    return gate_code, paths, evidence_uri


def validate_gate_scope(*, gate_code: str, scope: str) -> None:
    required_scope = RELEASE_EVIDENCE_REQUIREMENTS[gate_code]["scope"]
    if scope != required_scope:
        raise ValueError(f"{gate_code} requires evidence scope {required_scope}")


def split_gate_result(value: str) -> tuple[str, str, str]:
    parts = value.split("=", 2)
    if len(parts) != 3:
        raise ValueError("gate result must use gate_code=smoke_report_path=evidence_uri")
    gate_code, report_path, evidence_uri = (part.strip() for part in parts)
    if not gate_code or not report_path:
        raise ValueError("gate result gate_code and smoke_report_path must not be blank")
    return gate_code, report_path, evidence_uri


def read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"smoke report must contain a JSON object: {path}")
    return cast(dict[str, Any], payload)


def read_release_evidence_file(path: Path) -> ReleaseEvidence:
    payload = read_json_object(path)
    evidence: ReleaseEvidence = {}
    for gate_code, raw_item in payload.items():
        if not isinstance(raw_item, dict):
            raise ValueError(f"release evidence item must be an object: {gate_code}")
        item = cast(dict[str, object], raw_item)
        evidence[gate_code] = {key: value for key, value in item.items() if isinstance(value, str)}
    return evidence


def string_field(value: dict[str, object], key: str) -> str:
    raw_value = value.get(key)
    return raw_value.strip() if isinstance(raw_value, str) else ""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Reactor release evidence JSON from smoke report files."
    )
    parser.add_argument(
        "--gate-result",
        action="append",
        default=[],
        help="Repeatable gate_code=smoke_report_path=evidence_uri entry",
    )
    parser.add_argument(
        "--composite-gate-result",
        action="append",
        default=[],
        help=(
            "Repeatable gate_code=smoke_report_path[,smoke_report_path...]=evidence_uri "
            "entry. All reports must pass for the gate to pass."
        ),
    )
    parser.add_argument(
        "--smoke-run",
        action="append",
        default=[],
        help="Release smoke run report JSON to convert passed gate-closing steps into evidence",
    )
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="Existing release evidence JSON file to merge before new gate results",
    )
    parser.add_argument(
        "--scope",
        choices=sorted({item["scope"] for item in RELEASE_EVIDENCE_REQUIREMENTS.values()}),
        default=None,
        help="Evidence scope. Must match each selected release gate.",
    )
    parser.add_argument("--verified-at", required=True, help="ISO-8601 verification timestamp")
    parser.add_argument("--output", required=True, help="Path to write release evidence JSON")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    gate_result_values = cast(list[str], args.gate_result)
    composite_gate_result_values = cast(list[str], args.composite_gate_result)
    smoke_run_values = cast(list[str], args.smoke_run)
    input_values = cast(list[str], args.input)
    git_commit = current_git_commit()
    latest_items: list[ReleaseEvidence] = []
    if gate_result_values:
        if args.scope is None:
            raise ValueError("--scope is required when --gate-result is used")
        latest_items.append(
            build_release_evidence(
                [parse_gate_result(value) for value in gate_result_values],
                verified_at=str(args.verified_at),
                scope=str(args.scope),
                git_commit=git_commit,
            )
        )
    if composite_gate_result_values:
        if args.scope is None:
            raise ValueError("--scope is required when --composite-gate-result is used")
        latest_items.append(
            build_composite_release_evidence(
                [parse_composite_gate_result(value) for value in composite_gate_result_values],
                verified_at=str(args.verified_at),
                scope=str(args.scope),
                git_commit=git_commit,
            )
        )
    latest_items.extend(
        build_release_evidence_from_smoke_run(
            read_json_object(Path(value)),
            verified_at=str(args.verified_at),
            git_commit=git_commit,
        )
        for value in smoke_run_values
    )
    if not latest_items:
        raise ValueError("at least one --gate-result or --smoke-run is required")
    latest = merge_release_evidence(latest_items, {})
    evidence = merge_release_evidence(
        [read_release_evidence_file(Path(value)) for value in input_values],
        latest,
    )
    output_path = Path(str(args.output))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output:
        write_report(evidence, output)
    return 0
