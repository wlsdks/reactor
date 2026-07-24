from __future__ import annotations

import pytest

from reactor.release.readiness_actions import (
    env_file_command,
    release_readiness_command_for_reports,
)


def test_release_readiness_command_threads_latest_git_tag_into_smoke_run() -> None:
    command = release_readiness_command_for_reports(
        required_reports=("hardening_suite", "langsmith_eval_sync"),
        report_files={
            "hardening_suite": "reports/hardening-suite.json",
            "langsmith_eval_sync": "artifacts/langsmith/rag-candidate.json",
        },
    )

    assert "--latest-tag $(git describe --tags --abbrev=0)" in command
    assert "--readiness-output reports/release-readiness.json" in command
    assert command.index("--latest-tag") < command.index("--readiness-output")


def test_release_readiness_command_uses_env_file_without_overwriting_template() -> None:
    command = release_readiness_command_for_reports(
        required_reports=("langsmith_eval_sync",),
        report_files={"langsmith_eval_sync": "reports/langsmith-eval-sync.json"},
    )

    assert "--env-file reports/release/release-smoke-preflight.local.env" in command
    assert "--preflight-env-template" not in command


def test_env_file_command_does_not_duplicate_existing_env_file() -> None:
    command = release_readiness_command_for_reports(
        required_reports=("langsmith_eval_sync",),
        report_files={"langsmith_eval_sync": "reports/langsmith-eval-sync.json"},
    )

    env_command = env_file_command(command)

    assert env_command.count("--env-file reports/release/release-smoke-preflight.local.env") == 1


def test_release_readiness_command_requires_files_for_required_reports() -> None:
    with pytest.raises(
        ValueError,
        match="missing report file for required readiness report: langsmith_eval_sync",
    ):
        release_readiness_command_for_reports(
            required_reports=("hardening_suite", "langsmith_eval_sync"),
            report_files={"hardening_suite": "reports/hardening-suite.json"},
        )


def test_release_readiness_command_rejects_blank_required_report_file() -> None:
    with pytest.raises(
        ValueError,
        match="missing report file for required readiness report: langsmith_eval_sync",
    ):
        release_readiness_command_for_reports(
            required_reports=("langsmith_eval_sync",),
            report_files={"langsmith_eval_sync": "   "},
        )
