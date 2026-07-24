from __future__ import annotations

from collections.abc import Mapping, Sequence
from shlex import quote

REPLATFORM_READINESS_FILE = "reports/release/replatform-readiness.local.json"
RELEASE_SMOKE_PLAN_FILE = "reports/release/release-smoke-plan.local.json"
RELEASE_SMOKE_PREFLIGHT_FILE = "reports/release/release-smoke-preflight.local.json"
RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE = "reports/release/release-smoke-preflight.local.env"
RELEASE_SMOKE_RUN_FILE = "reports/release-smoke-run.json"
RELEASE_EVIDENCE_FILE = "reports/release-evidence.json"
RELEASE_READINESS_FILE = "reports/release-readiness.json"
HARDENING_SUITE_REPORT_FILE = "reports/hardening-suite.json"
LATEST_TAG_COMMAND = "git describe --tags --abbrev=0"
LATEST_TAG_SHELL_ARG = "$(git describe --tags --abbrev=0)"
RECOMMENDED_TAG_SOURCE = "release_readiness.tagRecommendation.recommendedTag"
LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF = [
    ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
]
LANGSMITH_SYNC_RECOMMENDED_ENV = ["LANGSMITH_ENDPOINT"]


def env_file_command(command: str) -> str:
    env_file_arg = f"--env-file {quote(RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE)}"
    if env_file_arg in command:
        return command
    return f"{command} {env_file_arg}"


def rag_ingestion_lifecycle_remediation_command() -> str:
    return f"uv run reactor-hardening-suite --report-file {HARDENING_SUITE_REPORT_FILE}"


def release_readiness_command_for_reports(
    *,
    required_reports: Sequence[str],
    report_files: Mapping[str, str],
    latest_tag_arg: str = LATEST_TAG_SHELL_ARG,
) -> str:
    for required_report in required_reports:
        if not report_files.get(required_report, "").strip():
            raise ValueError(
                f"missing report file for required readiness report: {required_report}"
            )
    required_args = " ".join(
        f"--required-readiness-report {quote(required_report)}"
        for required_report in required_reports
    )
    report_args = readiness_report_args_for_reports(
        required_reports=required_reports,
        report_files=report_files,
    )
    latest_tag_arg = latest_tag_arg.strip()
    latest_tag_option = f"--latest-tag {latest_tag_arg} " if latest_tag_arg else ""
    return (
        "uv run reactor-replatform-readiness "
        f"--output {REPLATFORM_READINESS_FILE} "
        "--allow-deferred-release-gates "
        "&& uv run reactor-release-smoke-plan "
        f"--readiness {REPLATFORM_READINESS_FILE} "
        f"--output {RELEASE_SMOKE_PLAN_FILE} "
        "&& uv run reactor-release-smoke-run "
        f"--plan {RELEASE_SMOKE_PLAN_FILE} "
        f"--preflight-file {RELEASE_SMOKE_PREFLIGHT_FILE} "
        f"--env-file {RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE} "
        f"--report-file {RELEASE_SMOKE_RUN_FILE} "
        f"--evidence-output {RELEASE_EVIDENCE_FILE} "
        "--verified-at $(date -u +%Y-%m-%dT%H:%M:%SZ) "
        f"{latest_tag_option}"
        f"--readiness-output {RELEASE_READINESS_FILE} "
        f"{required_args} "
        f"{report_args}"
    )


def readiness_report_args_for_reports(
    *,
    required_reports: Sequence[str],
    report_files: Mapping[str, str],
) -> str:
    for required_report in required_reports:
        if not report_files.get(required_report, "").strip():
            raise ValueError(
                f"missing report file for required readiness report: {required_report}"
            )
    return " ".join(
        f"--readiness-report {quote(required_report)}={quote(report_files[required_report])}"
        for required_report in required_reports
        if report_files.get(required_report)
    )


def release_readiness_command(*, required_report: str, report_file: str) -> str:
    return release_readiness_command_for_reports(
        required_reports=(required_report,),
        report_files={required_report: report_file},
    )


def langsmith_release_readiness_command(report_file: str) -> str:
    return release_readiness_command(
        required_report="langsmith_eval_sync",
        report_file=report_file,
    )
