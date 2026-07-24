from __future__ import annotations

import json
from pathlib import Path

from pytest import MonkeyPatch

from reactor.release.evidence import (
    build_release_evidence,
    build_release_evidence_from_smoke_run,
    main,
    merge_release_evidence,
    parse_gate_result,
)


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


def test_build_release_evidence_marks_passing_smoke_report_passed(tmp_path: Path) -> None:
    report_path = tmp_path / "provider-smoke.json"
    report_path.write_text(
        json.dumps({"ok": True, "checks": {"chat": {"ok": True}}}),
        encoding="utf-8",
    )

    evidence = build_release_evidence(
        [
            (
                "live_provider_runtime_smoke",
                report_path,
                "reports/live-provider-runtime-smoke.json",
            )
        ],
        verified_at="2026-06-28T00:00:00Z",
        scope="live",
    )

    assert evidence == {
        "live_provider_runtime_smoke": {
            "status": "passed",
            "scope": "live",
            "evidence_uri": "reports/live-provider-runtime-smoke.json",
            "verified_at": "2026-06-28T00:00:00Z",
        }
    }


def test_build_release_evidence_records_git_commit_for_freshness(tmp_path: Path) -> None:
    report_path = tmp_path / "provider-smoke.json"
    report_path.write_text(json.dumps({"ok": True}), encoding="utf-8")

    evidence = build_release_evidence(
        [
            (
                "live_provider_runtime_smoke",
                report_path,
                "reports/live-provider-runtime-smoke.json",
            )
        ],
        verified_at="2026-06-28T00:00:00Z",
        scope="live",
        git_commit="abc123",
    )

    assert evidence["live_provider_runtime_smoke"]["git_commit"] == "abc123"


def test_build_release_evidence_preserves_failed_smoke_status(tmp_path: Path) -> None:
    report_path = tmp_path / "slack-smoke.json"
    report_path.write_text(
        json.dumps({"ok": False, "error": "invalid Slack signature"}),
        encoding="utf-8",
    )

    evidence = build_release_evidence(
        [("live_slack_workspace_smoke", report_path, "reports/live-slack-workspace-smoke.json")],
        verified_at="2026-06-28T00:00:00Z",
        scope="live",
    )

    assert evidence == {
        "live_slack_workspace_smoke": {
            "status": "failed",
            "scope": "live",
            "evidence_uri": "reports/live-slack-workspace-smoke.json",
            "verified_at": "2026-06-28T00:00:00Z",
            "failure": "invalid Slack signature",
        }
    }


def test_build_release_evidence_rejects_stale_slack_smoke_without_approval_block(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "slack-smoke.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "checks": {
                    "auth_test": {"status": "passed"},
                    "socket_mode": {"status": "passed"},
                    "thread_message": {"status": "passed"},
                },
            }
        ),
        encoding="utf-8",
    )

    evidence = build_release_evidence(
        [("live_slack_workspace_smoke", report_path, "reports/live-slack-workspace-smoke.json")],
        verified_at="2026-06-28T00:00:00Z",
        scope="live",
    )

    assert evidence == {
        "live_slack_workspace_smoke": {
            "status": "failed",
            "scope": "live",
            "evidence_uri": "reports/live-slack-workspace-smoke.json",
            "verified_at": "2026-06-28T00:00:00Z",
            "failure": "required smoke check approval_block_contract did not pass",
        }
    }


def test_build_release_evidence_accepts_current_slack_approval_block_contract(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "slack-smoke.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "checks": {
                    "auth_test": {"status": "passed"},
                    "socket_mode": {"status": "passed"},
                    "thread_message": {"status": "passed"},
                    "approval_block_contract": {"status": "passed"},
                },
            }
        ),
        encoding="utf-8",
    )

    evidence = build_release_evidence(
        [("live_slack_workspace_smoke", report_path, "reports/live-slack-workspace-smoke.json")],
        verified_at="2026-06-28T00:00:00Z",
        scope="live",
    )

    assert evidence == {
        "live_slack_workspace_smoke": {
            "status": "passed",
            "scope": "live",
            "evidence_uri": "reports/live-slack-workspace-smoke.json",
            "verified_at": "2026-06-28T00:00:00Z",
        }
    }


def test_release_evidence_cli_writes_evidence_file(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    report_path = tmp_path / "provider-smoke.json"
    output_path = tmp_path / "reports" / "release" / "release-evidence.json"
    report_path.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    monkeypatch.setattr("reactor.release.evidence.current_git_commit", lambda: "abc123")

    exit_code = main(
        [
            "--verified-at",
            "2026-06-28T00:00:00Z",
            "--scope",
            "live",
            "--gate-result",
            f"live_provider_runtime_smoke={report_path}=reports/live-provider-runtime-smoke.json",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "live_provider_runtime_smoke": {
            "status": "passed",
            "scope": "live",
            "evidence_uri": "reports/live-provider-runtime-smoke.json",
            "verified_at": "2026-06-28T00:00:00Z",
            "git_commit": "abc123",
        }
    }


def test_merge_release_evidence_preserves_existing_and_overrides_newer_gate() -> None:
    existing = {
        "live_provider_runtime_smoke": {
            "status": "failed",
            "scope": "live",
            "evidence_uri": "reports/old-provider-smoke.json",
            "verified_at": "2026-06-27T00:00:00Z",
            "failure": "old failure",
        },
        "live_slack_workspace_smoke": {
            "status": "passed",
            "scope": "live",
            "evidence_uri": "reports/slack-smoke.json",
            "verified_at": "2026-06-27T00:00:00Z",
        },
    }
    latest = {
        "live_provider_runtime_smoke": {
            "status": "passed",
            "scope": "live",
            "evidence_uri": "reports/new-provider-smoke.json",
            "verified_at": "2026-06-28T00:00:00Z",
        }
    }

    assert merge_release_evidence([existing], latest) == {
        "live_provider_runtime_smoke": {
            "status": "passed",
            "scope": "live",
            "evidence_uri": "reports/new-provider-smoke.json",
            "verified_at": "2026-06-28T00:00:00Z",
        },
        "live_slack_workspace_smoke": {
            "status": "passed",
            "scope": "live",
            "evidence_uri": "reports/slack-smoke.json",
            "verified_at": "2026-06-27T00:00:00Z",
        },
    }


def test_release_evidence_cli_merges_existing_evidence_file(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    existing_path = tmp_path / "existing-evidence.json"
    report_path = tmp_path / "dress-rehearsal-smoke.json"
    output_path = tmp_path / "release-evidence.json"
    existing_path.write_text(
        json.dumps(
            {
                "live_provider_runtime_smoke": {
                    "status": "passed",
                    "scope": "live",
                    "evidence_uri": "reports/provider-smoke.json",
                    "verified_at": "2026-06-27T00:00:00Z",
                }
            }
        ),
        encoding="utf-8",
    )
    report_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
    monkeypatch.setattr("reactor.release.evidence.current_git_commit", lambda: "abc123")

    exit_code = main(
        [
            "--input",
            str(existing_path),
            "--verified-at",
            "2026-06-28T00:00:00Z",
            "--scope",
            "dress_rehearsal",
            "--gate-result",
            (
                "full_backup_db_dress_rehearsal="
                f"{report_path}=reports/full-backup-db-dress-rehearsal.json"
            ),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "full_backup_db_dress_rehearsal": {
            "status": "passed",
            "scope": "dress_rehearsal",
            "evidence_uri": "reports/full-backup-db-dress-rehearsal.json",
            "verified_at": "2026-06-28T00:00:00Z",
            "git_commit": "abc123",
        },
        "live_provider_runtime_smoke": {
            "status": "passed",
            "scope": "live",
            "evidence_uri": "reports/provider-smoke.json",
            "verified_at": "2026-06-27T00:00:00Z",
        },
    }


def test_build_release_evidence_from_smoke_run_uses_only_passed_gate_closers() -> None:
    evidence = build_release_evidence_from_smoke_run(
        {
            "steps": [
                {
                    "code": "live_provider_runtime_smoke",
                    "status": "passed",
                    "evidence_scope": "live",
                    "release_gate_closer": True,
                    "evidence_uri": "reports/live-provider-runtime-smoke.json",
                },
                {
                    "code": "live_provider_smoke",
                    "status": "failed",
                    "evidence_scope": "live",
                    "release_gate_closer": True,
                    "evidence_uri": "reports/live-provider-smoke.json",
                    "stderr": "missing key",
                },
                {
                    "code": "live_slack_workspace_smoke",
                    "status": "passed",
                    "evidence_scope": "local_contract",
                    "release_gate_closer": False,
                    "evidence_uri": "reports/live-slack-workspace-smoke.json",
                },
                {
                    "code": "full_backup_db_dress_rehearsal",
                    "status": "skipped",
                    "evidence_scope": "dress_rehearsal",
                    "release_gate_closer": True,
                    "evidence_uri": "reports/full-backup-db-dress-rehearsal.json",
                },
            ]
        },
        verified_at="2026-06-28T00:00:00Z",
        git_commit="abc123",
    )

    assert evidence == {
        "live_provider_runtime_smoke": {
            "status": "passed",
            "scope": "live",
            "evidence_uri": "reports/live-provider-runtime-smoke.json",
            "verified_at": "2026-06-28T00:00:00Z",
            "git_commit": "abc123",
        }
    }


def test_release_evidence_cli_can_build_from_smoke_run_report(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    smoke_run_path = tmp_path / "smoke-run.json"
    output_path = tmp_path / "release-evidence.json"
    smoke_run_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "code": "live_slack_workspace_smoke",
                        "status": "passed",
                        "checks": {
                            "approval_block_contract": {
                                "status": "passed",
                            }
                        },
                        "evidence_scope": "live",
                        "release_gate_closer": True,
                        "evidence_uri": "reports/live-slack-workspace-smoke.json",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("reactor.release.evidence.current_git_commit", lambda: "abc123")

    exit_code = main(
        [
            "--verified-at",
            "2026-06-28T00:00:00Z",
            "--smoke-run",
            str(smoke_run_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "live_slack_workspace_smoke": {
            "status": "passed",
            "scope": "live",
            "evidence_uri": "reports/live-slack-workspace-smoke.json",
            "verified_at": "2026-06-28T00:00:00Z",
            "git_commit": "abc123",
        }
    }


def test_build_release_evidence_from_smoke_run_rejects_stale_slack_step() -> None:
    evidence = build_release_evidence_from_smoke_run(
        {
            "steps": [
                {
                    "code": "live_slack_workspace_smoke",
                    "status": "passed",
                    "evidence_scope": "live",
                    "release_gate_closer": True,
                    "evidence_uri": "reports/live-slack-workspace-smoke.json",
                }
            ]
        },
        verified_at="2026-06-28T00:00:00Z",
    )

    assert evidence == {}


def test_build_release_evidence_from_smoke_run_rejects_dress_rehearsal_without_reports() -> None:
    evidence = build_release_evidence_from_smoke_run(
        {
            "steps": [
                {
                    "code": "full_backup_db_dress_rehearsal",
                    "status": "passed",
                    "evidence_scope": "dress_rehearsal",
                    "release_gate_closer": True,
                    "evidence_uri": "reports/full-backup-db-dress-rehearsal.json",
                }
            ]
        },
        verified_at="2026-06-28T00:00:00Z",
    )

    assert evidence == {}


def test_build_release_evidence_from_smoke_run_rejects_failed_dress_rehearsal_report(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "dress-readiness.json"
    report_path.write_text(
        json.dumps({"ok": False, "error": "checksum mismatch"}),
        encoding="utf-8",
    )

    evidence = build_release_evidence_from_smoke_run(
        {
            "steps": [
                {
                    "code": "full_backup_db_dress_rehearsal",
                    "status": "passed",
                    "evidence_scope": "dress_rehearsal",
                    "release_gate_closer": True,
                    "evidence_uri": "reports/full-backup-db-dress-rehearsal.json",
                    "report_paths": [str(report_path)],
                }
            ]
        },
        verified_at="2026-06-28T00:00:00Z",
    )

    assert evidence == {}


def test_build_release_evidence_from_smoke_run_accepts_passed_dress_rehearsal_report(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "dress-readiness.json"
    report_path.write_text(
        json.dumps({"ok": True, "migrationPersistence": migration_persistence_evidence()}),
        encoding="utf-8",
    )

    evidence = build_release_evidence_from_smoke_run(
        {
            "steps": [
                {
                    "code": "full_backup_db_dress_rehearsal",
                    "status": "passed",
                    "evidence_scope": "dress_rehearsal",
                    "release_gate_closer": True,
                    "evidence_uri": "reports/full-backup-db-dress-rehearsal.json",
                    "report_paths": [str(report_path)],
                }
            ]
        },
        verified_at="2026-06-28T00:00:00Z",
    )

    assert evidence == {
        "full_backup_db_dress_rehearsal": {
            "status": "passed",
            "scope": "dress_rehearsal",
            "evidence_uri": "reports/full-backup-db-dress-rehearsal.json",
            "verified_at": "2026-06-28T00:00:00Z",
        }
    }


def test_build_release_evidence_rejects_dress_rehearsal_without_migration_persistence(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "dress-readiness.json"
    report_path.write_text(json.dumps({"ok": True}), encoding="utf-8")

    evidence = build_release_evidence_from_smoke_run(
        {
            "steps": [
                {
                    "code": "full_backup_db_dress_rehearsal",
                    "status": "passed",
                    "evidence_scope": "dress_rehearsal",
                    "release_gate_closer": True,
                    "evidence_uri": "reports/full-backup-db-dress-rehearsal.json",
                    "report_paths": [str(report_path)],
                }
            ]
        },
        verified_at="2026-06-28T00:00:00Z",
    )

    assert evidence == {}


def test_release_evidence_cli_requires_all_composite_gate_reports_to_pass(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    readiness_path = tmp_path / "dress-rehearsal-readiness.json"
    api_smoke_path = tmp_path / "api-smoke.json"
    output_path = tmp_path / "release-evidence.json"
    readiness_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
    api_smoke_path.write_text(json.dumps({"ok": False, "error": "api failed"}), encoding="utf-8")
    monkeypatch.setattr("reactor.release.evidence.current_git_commit", lambda: "abc123")

    exit_code = main(
        [
            "--verified-at",
            "2026-06-28T00:00:00Z",
            "--scope",
            "dress_rehearsal",
            "--composite-gate-result",
            (
                "full_backup_db_api_dress_rehearsal="
                f"{readiness_path},{api_smoke_path}=reports/full-backup-db-api-dress-rehearsal.json"
            ),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "full_backup_db_api_dress_rehearsal": {
            "status": "failed",
            "scope": "dress_rehearsal",
            "evidence_uri": "reports/full-backup-db-api-dress-rehearsal.json",
            "verified_at": "2026-06-28T00:00:00Z",
            "git_commit": "abc123",
            "failure": "api failed",
        }
    }


def test_release_evidence_cli_marks_composite_gate_passed_when_all_reports_pass(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    readiness_path = tmp_path / "dress-rehearsal-readiness.json"
    api_smoke_path = tmp_path / "api-smoke.json"
    output_path = tmp_path / "release-evidence.json"
    readiness_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
    api_smoke_path.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    monkeypatch.setattr("reactor.release.evidence.current_git_commit", lambda: "abc123")

    exit_code = main(
        [
            "--verified-at",
            "2026-06-28T00:00:00Z",
            "--scope",
            "dress_rehearsal",
            "--composite-gate-result",
            (
                "full_backup_db_api_dress_rehearsal="
                f"{readiness_path},{api_smoke_path}=reports/full-backup-db-api-dress-rehearsal.json"
            ),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "full_backup_db_api_dress_rehearsal": {
            "status": "passed",
            "scope": "dress_rehearsal",
            "evidence_uri": "reports/full-backup-db-api-dress-rehearsal.json",
            "verified_at": "2026-06-28T00:00:00Z",
            "git_commit": "abc123",
        }
    }


def test_parse_gate_result_rejects_unknown_release_gate(tmp_path: Path) -> None:
    report_path = tmp_path / "unknown.json"
    report_path.write_text("{}", encoding="utf-8")

    try:
        parse_gate_result(f"unknown_gate={report_path}=reports/unknown.json")
    except ValueError as error:
        assert str(error) == "unknown release gate code: unknown_gate"
    else:
        raise AssertionError("expected parse_gate_result to reject an unknown gate")
