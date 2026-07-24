from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from reactor.context.diagnostics import ALLOWED_MEMORY_STATUS_COUNT_LABELS
from reactor.release.backend_provider_smoke import LANGSMITH_KEY_ENV_NAMES
from reactor.release.env_values import is_placeholder_env_value
from reactor.release.evidence import (
    build_release_evidence_from_smoke_run,
    merge_release_evidence,
    read_release_evidence_file,
)
from reactor.release.provider_smoke import required_env_for_provider
from reactor.release.readiness import current_git_commit, write_report
from reactor.release.readiness_actions import rag_ingestion_lifecycle_remediation_command
from reactor.release.readiness_contracts import (
    feedback_review_queue_action,
    feedback_review_queue_export_action,
    feedback_review_queue_memory_lifecycle_action,
)
from reactor.release.readiness_evidence import (
    build_release_readiness_report_from_payloads,
    feedback_queue_bulk_review_action_summary,
    feedback_queue_candidate_action_summary,
    next_actions_summary,
    readiness_failure_summary,
    ready_local_contract_actions_from_preflight,
)
from reactor.release.slack_smoke import REQUIRED_SLACK_ENV

FULL_BACKUP_DRESS_ENV: tuple[str, ...] = (
    "REACTOR_FULL_BACKUP_EXPORTED_NDJSON",
    "REACTOR_FULL_BACKUP_ROLLBACK_NDJSON",
    "REACTOR_FULL_BACKUP_RETAINED_TABLE_MANIFEST",
    "REACTOR_FULL_BACKUP_DRESS_IMPORTED_OUTPUT",
    "REACTOR_FULL_BACKUP_DRESS_READINESS_OUTPUT",
    "REACTOR_FULL_BACKUP_DRESS_BATCH_ID",
)

DEFAULT_MODEL_PROVIDER = "openai"
RELEASE_SMOKE_PROVIDER_ENV = "REACTOR_RELEASE_SMOKE_PROVIDER"
RELEASE_SMOKE_MODEL_ENV = "REACTOR_RELEASE_SMOKE_MODEL"
RELEASE_SMOKE_TRACE_EXPORTER_ENV = "REACTOR_RELEASE_SMOKE_TRACE_EXPORTER"
DEFAULT_READINESS_REQUIRED_REPORTS = ("smoke_run", "release_evidence")
MEMORY_CONTRACT_AREAS = (
    "manager",
    "statuses",
    "consolidation",
    "review",
    "privacy",
    "dependencies",
)


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    duration_ms: int
    stdout: str
    stderr: str


CommandRunner = Callable[[list[str], int], CommandResult]


def build_release_smoke_plan(
    readiness_report: dict[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
    evidence_scopes: Sequence[str] = (),
) -> dict[str, object]:
    plan_environ = environ if environ is not None else os.environ
    all_steps = [
        smoke_plan_step(requirement, environ=plan_environ)
        for requirement in release_evidence_requirements(readiness_report)
    ]
    scope_filter = [scope.strip() for scope in evidence_scopes if scope.strip()]
    if scope_filter:
        scope_set = set(scope_filter)
        steps = [
            step
            for step in all_steps
            if isinstance(step.get("evidence_scope"), str)
            and cast(str, step["evidence_scope"]) in scope_set
        ]
        excluded_steps = [step for step in all_steps if step not in steps]
    else:
        steps = all_steps
        excluded_steps = []
    summary = {
        "total": len(steps),
        "automated": sum(1 for step in steps if step["mode"] == "automated"),
        "manual": sum(1 for step in steps if step["mode"] == "manual"),
    }
    plan: dict[str, object] = {"summary": summary, "steps": steps}
    if scope_filter:
        plan["evidenceScopeFilter"] = scope_filter
        plan["excludedSummary"] = {
            "total": len(excluded_steps),
            "automated": sum(1 for step in excluded_steps if step["mode"] == "automated"),
            "manual": sum(1 for step in excluded_steps if step["mode"] == "manual"),
        }
    if not steps:
        if readiness_report.get("release_ready") is True:
            plan["status"] = "passed"
            plan["reason"] = "release evidence requirements already satisfied"
        else:
            plan["status"] = "blocked"
            plan["remediationCommand"] = (
                "uv run reactor-replatform-readiness --output "
                "reports/release/replatform-readiness.local.json "
                "--allow-deferred-release-gates "
                "&& uv run reactor-release-smoke-plan "
                "--readiness reports/release/replatform-readiness.local.json "
                "--output reports/release/release-smoke-plan.local.json"
            )
            if scope_filter and all_steps:
                plan["failure"] = "release evidence requirements missing for evidence scope"
            else:
                plan["failure"] = "release evidence requirements missing"
            next_actions = readiness_next_actions(readiness_report)
            if next_actions:
                plan["nextActions"] = next_actions
    return plan


def release_evidence_requirements(readiness_report: dict[str, Any]) -> list[dict[str, Any]]:
    raw_requirements = readiness_report.get("release_evidence_requirements")
    if not isinstance(raw_requirements, list):
        return []
    requirements: list[dict[str, Any]] = []
    for raw_item in cast(list[object], raw_requirements):
        if isinstance(raw_item, dict):
            requirements.append(cast(dict[str, Any], raw_item))
    return requirements


def readiness_next_actions(readiness_report: Mapping[str, Any]) -> list[dict[str, object]]:
    raw_items = readiness_report.get("items")
    if not isinstance(raw_items, list):
        return []
    actions: list[dict[str, object]] = []
    for raw_item in cast(list[object], raw_items):
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, object], raw_item)
        source_report = item.get("name")
        raw_actions = item.get("nextActions")
        if not isinstance(raw_actions, list):
            continue
        for raw_action in cast(list[object], raw_actions):
            if not isinstance(raw_action, dict):
                continue
            action = dict(cast(dict[str, object], raw_action))
            if isinstance(source_report, str) and source_report:
                action.setdefault("sourceReport", source_report)
            actions.append(action)
    return actions


def smoke_plan_step(
    requirement: dict[str, Any],
    *,
    environ: Mapping[str, str],
) -> dict[str, object]:
    evidence_schema = requirement.get("evidence_schema")
    if not isinstance(evidence_schema, dict):
        evidence_schema = {}
    typed_evidence_schema = cast(dict[str, Any], evidence_schema)
    suggested_command = str(requirement.get("suggested_command", ""))
    command_text, manual_note = split_suggested_command(suggested_command)
    command = shlex.split(command_text)
    code = str(requirement.get("code", ""))
    configured_dress_commands = configured_full_backup_dress_commands(code, environ)
    if configured_dress_commands is not None:
        command = configured_dress_commands[0]
        manual_note = ""
    command = configured_provider_smoke_command(command, environ)
    mode = "automated" if is_automated_command(command, manual_note) else "manual"
    required_scope = str(typed_evidence_schema.get("scope", ""))
    release_gate_closer = is_release_gate_closer(
        command=command,
        mode=mode,
        required_scope=required_scope,
    )
    evidence_scope = required_scope if release_gate_closer else "local_contract"
    step: dict[str, object] = {
        "code": code,
        "description": str(requirement.get("description", "")),
        "scope": required_scope,
        "evidence_scope": evidence_scope,
        "release_gate_closer": release_gate_closer,
        "evidence_uri": str(typed_evidence_schema.get("evidence_uri", "")),
        "mode": mode,
        "command": command,
        "manual_note": manual_note,
    }
    required_env = required_env_for_step(code=code, command=command)
    if required_env:
        step["required_env"] = required_env
    prior_evidence = prior_evidence_metadata(requirement)
    if prior_evidence:
        step["prior_evidence"] = prior_evidence
    if configured_dress_commands is not None and len(configured_dress_commands) > 1:
        step["commands"] = configured_dress_commands
        report_paths = configured_full_backup_db_api_report_paths(environ)
        if report_paths:
            step["report_paths"] = report_paths
        api_smoke_output = configured_full_backup_db_api_smoke_output(environ)
        if api_smoke_output:
            step["readiness_reports"] = [
                {
                    "name": "dress_api_smoke",
                    "path": api_smoke_output,
                    "required": True,
                }
            ]
    return step


def split_suggested_command(value: str) -> tuple[str, str]:
    command_text, separator, note = value.partition("#")
    return command_text.strip(), normalize_manual_note(note) if separator else ""


def normalize_manual_note(value: str) -> str:
    note = value.strip()
    if note.startswith("plus "):
        return note.removeprefix("plus ").strip()
    return note


def is_automated_command(command: Sequence[str], manual_note: str) -> bool:
    if len(command) < 3:
        return False
    if command[:2] != ["uv", "run"]:
        return False
    if command[2] == "pytest":
        return "staging" in manual_note or "live" in manual_note
    if command[2] == "reactor-migration-dress-rehearsal":
        return "--help" not in command and not command_has_placeholder(command)
    if command[2] == "reactor-observability-smoke":
        return not command_has_placeholder(command)
    return command[2].startswith("reactor-live-") and not command_has_placeholder(command)


def is_release_gate_closer(
    *,
    command: Sequence[str],
    mode: str,
    required_scope: str,
) -> bool:
    if mode == "manual":
        return True
    return (
        mode == "automated"
        and len(command) >= 3
        and command[:2] == ["uv", "run"]
        and not command_has_placeholder(command)
        and (
            (required_scope == "live" and command[2].startswith("reactor-live-"))
            or (
                required_scope == "dress_rehearsal"
                and command[2] == "reactor-migration-dress-rehearsal"
                and "--help" not in command
            )
        )
    )


def command_has_placeholder(command: Sequence[str]) -> bool:
    return any("<" in value or ">" in value for value in command)


def required_env_for_step(*, code: str, command: Sequence[str]) -> dict[str, object]:
    command_name = command[2] if len(command) >= 3 else ""
    if code == "full_backup_db_dress_rehearsal":
        return {"variables": list(FULL_BACKUP_DRESS_ENV)}
    if code == "full_backup_db_api_dress_rehearsal":
        return {"variables": [*FULL_BACKUP_DRESS_ENV, "REACTOR_API_BASE_URL", "REACTOR_API_KEY"]}
    if command_name == "reactor-live-slack-smoke":
        return {"variables": list(REQUIRED_SLACK_ENV)}
    if command_name == "reactor-live-a2a-peer-smoke":
        return {"variables": ["REACTOR_A2A_BASE_URL", "REACTOR_A2A_API_KEY"]}
    if command_name == "reactor-live-backend-provider-smoke":
        required_env: dict[str, object] = {
            "variables": list(required_env_for_provider(command_provider(command))),
        }
        if command_trace_exporter(command) == "langsmith":
            required_env["any_of"] = [list(LANGSMITH_KEY_ENV_NAMES)]
            required_env["recommended"] = ["LANGSMITH_ENDPOINT"]
        return required_env
    if command_name == "reactor-observability-smoke":
        if command_trace_exporter(command) == "langsmith":
            return {
                "any_of": [list(LANGSMITH_KEY_ENV_NAMES)],
                "recommended": ["LANGSMITH_ENDPOINT"],
            }
        return {}
    if command_name == "reactor-live-provider-smoke":
        return {"variables": list(required_env_for_provider(command_provider(command)))}
    return {}


def command_provider(command: Sequence[str]) -> str:
    for index, value in enumerate(command):
        if value == "--provider" and index + 1 < len(command):
            return command[index + 1]
    return DEFAULT_MODEL_PROVIDER


def command_trace_exporter(command: Sequence[str]) -> str:
    for index, value in enumerate(command):
        if value == "--trace-exporter" and index + 1 < len(command):
            return command[index + 1].strip().lower().replace("-", "_")
    return "langsmith"


def configured_provider_smoke_command(
    command: list[str],
    environ: Mapping[str, str],
) -> list[str]:
    if len(command) < 3 or command[2] not in {
        "reactor-live-provider-smoke",
        "reactor-live-backend-provider-smoke",
    }:
        return command
    configured = list(command)
    provider = env_value(environ, RELEASE_SMOKE_PROVIDER_ENV)
    model = env_value(environ, RELEASE_SMOKE_MODEL_ENV)
    trace_exporter = env_value(environ, RELEASE_SMOKE_TRACE_EXPORTER_ENV)
    if provider:
        configured = command_with_option(configured, "--provider", provider)
    if model:
        configured = command_with_option(configured, "--model", model)
    if trace_exporter and configured[2] == "reactor-live-backend-provider-smoke":
        configured = command_with_option(configured, "--trace-exporter", trace_exporter)
    return configured


def command_with_option(command: list[str], option: str, value: str) -> list[str]:
    if option in command:
        index = command.index(option)
        if index + 1 < len(command):
            return [*command[: index + 1], value, *command[index + 2 :]]
    return [*command, option, value]


def configured_full_backup_dress_commands(
    code: str,
    environ: Mapping[str, str],
) -> list[list[str]] | None:
    if code not in {"full_backup_db_dress_rehearsal", "full_backup_db_api_dress_rehearsal"}:
        return None
    required = {
        "exported": env_value(environ, "REACTOR_FULL_BACKUP_EXPORTED_NDJSON"),
        "rollback": env_value(environ, "REACTOR_FULL_BACKUP_ROLLBACK_NDJSON"),
        "imported_output": env_value(environ, "REACTOR_FULL_BACKUP_DRESS_IMPORTED_OUTPUT"),
        "readiness_output": env_value(environ, "REACTOR_FULL_BACKUP_DRESS_READINESS_OUTPUT"),
        "batch_id": env_value(environ, "REACTOR_FULL_BACKUP_DRESS_BATCH_ID"),
    }
    manifest = env_value(environ, "REACTOR_FULL_BACKUP_RETAINED_TABLE_MANIFEST")
    if any(not value for value in required.values()) or not manifest:
        return None
    migration_command = [
        "uv",
        "run",
        "reactor-migration-dress-rehearsal",
        "--exported",
        required["exported"],
        "--rollback",
        required["rollback"],
        "--imported-output",
        required["imported_output"],
        "--readiness-output",
        required["readiness_output"],
        "--batch-id",
        required["batch_id"],
        "--required-table-file",
        manifest,
    ]
    if code == "full_backup_db_dress_rehearsal":
        return [migration_command]

    api_smoke_output = (
        env_value(
            environ,
            "REACTOR_FULL_BACKUP_API_SMOKE_OUTPUT",
        )
        or "reports/release/full-backup-db-api-smoke.json"
    )
    if not env_value(environ, "REACTOR_API_BASE_URL") or not env_value(environ, "REACTOR_API_KEY"):
        return None
    return [
        migration_command,
        [
            "uv",
            "run",
            "reactor-dress-api-smoke",
            "--output",
            api_smoke_output,
        ],
    ]


def env_value(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "").strip()
    return "" if is_placeholder_env_value(value) else value


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        values[key.strip()] = value.strip()
    return values


def merged_environ(env_file_values: Sequence[str]) -> dict[str, str]:
    merged = dict(os.environ)
    for value in env_file_values:
        env_path = Path(value)
        merged.update(read_env_file(env_path))
    return merged


def redaction_values_from_env_files(env_file_values: Sequence[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for value in env_file_values:
        env_path = Path(value)
        for raw_env_value in read_env_file(env_path).values():
            env_value_from_file = raw_env_value.strip()
            if len(env_value_from_file) < 6 or env_value_from_file in seen:
                continue
            values.append(env_value_from_file)
            seen.add(env_value_from_file)
    return values


def env_file_unreadable_report(
    *,
    env_file: str,
    plan_file: str,
    preflight_file: str = "reports/release-smoke-preflight.json",
    readiness_output: str = "",
) -> dict[str, object]:
    env_file = env_file.strip()
    remediation_command = (
        f"uv run reactor-release-smoke-run --plan {plan_file} "
        f"--preflight-file {preflight_file} "
        f"--preflight-env-template {env_file}.example "
        "--preflight-only"
    )
    if readiness_output.strip():
        remediation_command = f"{remediation_command} --readiness-output {readiness_output.strip()}"
    return {
        "ok": False,
        "status": "blocked",
        "scope": "release_smoke_env_file",
        "failure": "release smoke env file unreadable",
        "envFile": env_file,
        "remediationCommand": remediation_command,
    }


def configured_full_backup_db_api_report_paths(environ: Mapping[str, str]) -> list[str]:
    readiness_output = env_value(environ, "REACTOR_FULL_BACKUP_DRESS_READINESS_OUTPUT")
    api_smoke_output = configured_full_backup_db_api_smoke_output(environ)
    return [value for value in [readiness_output, api_smoke_output] if value]


def configured_full_backup_db_api_smoke_output(environ: Mapping[str, str]) -> str:
    return (
        env_value(environ, "REACTOR_FULL_BACKUP_API_SMOKE_OUTPUT")
        or "reports/release/full-backup-db-api-smoke.json"
    )


def read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("release smoke plan input must be a JSON object")
    return cast(dict[str, Any], payload)


def ensure_parent_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json_report_file(path: Path, report: Mapping[str, object]) -> None:
    ensure_parent_directory(path)
    with path.open("w", encoding="utf-8") as output:
        write_report(cast(dict[str, Any], report), output)


def run_release_smoke_plan(
    plan: dict[str, object],
    *,
    report_file: Path,
    command_runner: CommandRunner | None = None,
    redaction_values: Sequence[str] = (),
    preflight_report: dict[str, object] | None = None,
) -> dict[str, object]:
    runner = command_runner or run_command
    blocked_preflight_steps = preflight_steps_by_code(preflight_report)
    step_reports: list[dict[str, object]] = []
    for step in smoke_plan_steps(plan):
        if step["mode"] != "automated":
            step_reports.append(skipped_manual_step_report(step))
            continue
        blocked_preflight = blocked_preflight_steps.get(str(step.get("code", "")))
        if blocked_preflight is not None:
            step_reports.append(blocked_preflight_step_report(step, blocked_preflight))
            continue
        result = run_automated_step(step, runner)
        step_reports.append(automated_step_report(step, result, redaction_values=redaction_values))
    summary = {
        "total": len(step_reports),
        "passed": sum(1 for step in step_reports if step["status"] == "passed"),
        "failed": sum(1 for step in step_reports if step["status"] == "failed"),
        "skipped": sum(1 for step in step_reports if step["status"] == "skipped"),
    }
    plan_blocked = plan.get("status") == "blocked" and not step_reports
    blocked_count = sum(1 for step in step_reports if step["status"] == "blocked") + (
        1 if plan_blocked else 0
    )
    if blocked_count:
        summary["blocked"] = blocked_count
    report: dict[str, object] = {
        "ok": summary["total"] > 0 and summary["failed"] == 0 and blocked_count == 0,
        "summary": summary,
        "steps": step_reports,
    }
    if summary["total"] == 0:
        if plan.get("status") == "passed":
            report["ok"] = True
            report["status"] = "passed"
            reason = plan.get("reason")
            if isinstance(reason, str) and reason.strip():
                report["reason"] = reason.strip()
        else:
            if plan_blocked:
                report["status"] = "blocked"
                failure = plan.get("failure")
                if isinstance(failure, str) and failure.strip():
                    report["failure"] = failure.strip()
                remediation = plan.get("remediationCommand")
                if isinstance(remediation, str) and remediation.strip():
                    report["remediationCommand"] = remediation.strip()
                next_actions = plan.get("nextActions")
                if isinstance(next_actions, list) and next_actions:
                    report["nextActions"] = cast(list[object], next_actions)
            else:
                report["status"] = "skipped"
                report["failure"] = "no automated release smoke steps configured"
    write_json_report_file(report_file, report)
    return report


def run_release_smoke_preflight(
    plan: dict[str, object],
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    env = environ if environ is not None else os.environ
    step_reports = [preflight_step_report(step, env) for step in smoke_plan_steps(plan)]
    plan_blocked = plan.get("status") == "blocked" and not step_reports
    summary = {
        "total": len(step_reports),
        "ready": sum(1 for step in step_reports if step["status"] == "ready"),
        "blocked": sum(1 for step in step_reports if step["status"] == "blocked")
        + (1 if plan_blocked else 0),
        "optional_missing": sum(
            len(cast(list[object], step.get("optional_missing", []))) for step in step_reports
        ),
    }
    report: dict[str, object] = {
        "ok": summary["blocked"] == 0,
        "summary": summary,
        "steps": step_reports,
    }
    if plan_blocked:
        report["status"] = "blocked"
        failure = plan.get("failure")
        if isinstance(failure, str) and failure.strip():
            report["failure"] = failure.strip()
        remediation = plan.get("remediationCommand")
        if isinstance(remediation, str) and remediation.strip():
            report["remediationCommand"] = remediation.strip()
        next_actions = plan.get("nextActions")
        if isinstance(next_actions, list) and next_actions:
            report["nextActions"] = cast(list[object], next_actions)
    return report


def preflight_steps_by_code(
    preflight_report: dict[str, object] | None,
) -> dict[str, dict[str, object]]:
    if preflight_report is None:
        return {}
    return {
        str(step.get("code", "")): step
        for step in preflight_steps(preflight_report)
        if step.get("status") == "blocked" and str(step.get("code", "")).strip()
    }


def release_smoke_preflight_failure_summary(report: dict[str, object]) -> str:
    summary = report.get("summary")
    summary_mapping = cast(dict[str, object], summary) if isinstance(summary, dict) else {}
    lines = [
        "release_smoke_preflight "
        f"ok={str(report.get('ok') is True).lower()} "
        f"blocked={summary_mapping.get('blocked', 0)} "
        f"ready={summary_mapping.get('ready', 0)} "
        f"optional_missing={summary_mapping.get('optional_missing', 0)}"
    ]
    for step in preflight_steps(report):
        if step.get("status") != "blocked":
            continue
        code = step.get("code") or "unknown"
        suffix = ""
        missing_env = sorted(string_list_value(step.get("missing")))
        if missing_env:
            suffix = f"{suffix} missingEnv={','.join(missing_env)}"
        missing_any_of = preflight_missing_any_of_summary(step.get("missing_any_of"))
        if missing_any_of:
            suffix = f"{suffix} missingAnyOf={missing_any_of}"
        lines.append(f"- blockedStep={code}{suffix}")
    for step in preflight_steps(report):
        if step.get("status") != "ready" or step.get("evidence_scope") != "local_contract":
            continue
        code = str(step.get("code") or "unknown").strip() or "unknown"
        command = step.get("command")
        suffix = ""
        if isinstance(command, list):
            command_parts = string_list_value(cast(list[object], command))
            if command_parts:
                suffix = f" command={summary_quoted_value(shlex.join(command_parts))}"
        lines.append(f"- readyLocalContract={code}{suffix}")
    failure = report.get("failure")
    if isinstance(failure, str) and failure.strip():
        lines.append(f"- failure={summary_quoted_value(failure.strip())}")
    env_file = report.get("envFile")
    if isinstance(env_file, str) and env_file.strip():
        lines.append(f"- envFile={summary_quoted_value(env_file.strip())}")
    remediation = report.get("remediationCommand")
    if isinstance(remediation, str) and remediation.strip():
        lines.append(f"- remediationCommand={summary_quoted_value(remediation.strip())}")
    next_actions = next_actions_summary(cast(Mapping[object, object], report))
    if next_actions:
        lines.append(f"- {next_actions}")
    return "\n".join(lines)


def preflight_missing_any_of_summary(value: object) -> str:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return ""
    groups: list[str] = []
    for group in cast(Sequence[object], value):
        items = string_list_value(group)
        if items:
            groups.append("|".join(items))
    return ",".join(groups)


def build_preflight_env_template(preflight_report: dict[str, object]) -> str:
    required = sorted(unique_preflight_values(preflight_report, "missing"))
    any_of = sorted(unique_preflight_group_values(preflight_report, "missing_any_of"))
    any_of_group_lines = preflight_any_of_group_template_lines(preflight_report)
    recommended = sorted(unique_preflight_values(preflight_report, "recommended_env"))
    optional = sorted(unique_preflight_values(preflight_report, "optional_missing"))
    sections: list[tuple[str, list[str]]] = []
    if required:
        sections.append(("Required", required))
    if any_of:
        sections.append(("Required alternatives: set at least one value in each group", any_of))
    if recommended:
        sections.append(("Recommended", recommended))
    if optional:
        sections.append(("Optional", optional))
    lines: list[str] = []
    for index, (title, values) in enumerate(sections):
        if index:
            lines.append("")
        lines.append(f"# {title}")
        if title.startswith("Required alternatives"):
            lines.extend(any_of_group_lines)
        lines.extend(f"{value}=" for value in values)
    blocked_gate_lines = blocked_gate_template_lines(preflight_report)
    if blocked_gate_lines:
        if lines:
            lines.append("")
        lines.append("# Blocked gates")
        lines.extend(blocked_gate_lines)
    prior_evidence_lines = prior_evidence_template_lines(preflight_report)
    if prior_evidence_lines:
        if lines:
            lines.append("")
        lines.append("# Prior release evidence")
        lines.extend(prior_evidence_lines)
    if lines:
        lines.append("")
    return "\n".join(lines)


def preflight_any_of_group_template_lines(preflight_report: dict[str, object]) -> list[str]:
    group_codes: dict[str, list[str]] = {}
    for step in preflight_steps(preflight_report):
        code = str(step.get("code", "")).strip()
        raw_groups = step.get("missing_any_of")
        if not isinstance(raw_groups, list):
            continue
        for raw_group in cast(list[object], raw_groups):
            if not isinstance(raw_group, list):
                continue
            values = [
                value.strip()
                for value in cast(list[object], raw_group)
                if isinstance(value, str) and value.strip()
            ]
            if not values:
                continue
            group = "|".join(values)
            codes = group_codes.setdefault(group, [])
            if code and code not in codes:
                codes.append(code)
    lines: list[str] = []
    for group_index, (group, codes) in enumerate(group_codes.items(), start=1):
        code_suffix = f" ({','.join(codes)})" if codes else ""
        lines.append(f"# any-of group {group_index}{code_suffix}: {group}")
    return lines


def blocked_gate_template_lines(preflight_report: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for step in preflight_steps(preflight_report):
        if step.get("status") != "blocked":
            continue
        code = str(step.get("code", "")).strip()
        if not code:
            continue
        parts: list[str] = []
        missing = sorted(string_list_value(step.get("missing")))
        if missing:
            parts.append(f"missing={','.join(missing)}")
        missing_any_of = preflight_missing_any_of_summary(step.get("missing_any_of"))
        if missing_any_of:
            parts.append(f"missingAnyOf={missing_any_of}")
        placeholder_env = sorted(string_list_value(step.get("placeholder_env")))
        if placeholder_env:
            parts.append(f"placeholder={','.join(placeholder_env)}")
        if parts:
            lines.append(f"# {code}: {' '.join(parts)}")
    return lines


def prior_evidence_template_lines(preflight_report: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for step in preflight_steps(preflight_report):
        code = str(step.get("code", "")).strip()
        prior_evidence = step.get("prior_evidence")
        if not code or not isinstance(prior_evidence, dict):
            continue
        evidence = cast(dict[object, object], prior_evidence)
        fields: list[str] = []
        for output_name, source_name in (
            ("status", "status"),
            ("scope", "scope"),
            ("revision", "revision_status"),
            ("git_commit", "git_commit"),
        ):
            value = evidence.get(source_name)
            if isinstance(value, str) and value.strip():
                fields.append(f"{output_name}={value.strip()}")
        if fields:
            lines.append(f"# {code}: {' '.join(fields)}")
    return lines


def unique_preflight_values(preflight_report: dict[str, object], key: str) -> set[str]:
    values: set[str] = set()
    for step in preflight_steps(preflight_report):
        raw_values = step.get(key)
        if key == "recommended_env" and not isinstance(raw_values, list):
            required_env = step.get("required_env")
            if isinstance(required_env, dict):
                raw_values = cast(dict[object, object], required_env).get("recommended")
        if not isinstance(raw_values, list):
            continue
        values.update(value for value in cast(list[object], raw_values) if isinstance(value, str))
    return values


def unique_preflight_group_values(preflight_report: dict[str, object], key: str) -> set[str]:
    values: set[str] = set()
    for step in preflight_steps(preflight_report):
        raw_groups = step.get(key)
        if not isinstance(raw_groups, list):
            continue
        for raw_group in cast(list[object], raw_groups):
            if isinstance(raw_group, list):
                values.update(
                    value for value in cast(list[object], raw_group) if isinstance(value, str)
                )
    return values


def unique_preflight_groups(preflight_report: dict[str, object], key: str) -> set[str]:
    groups: set[str] = set()
    for step in preflight_steps(preflight_report):
        raw_groups = step.get(key)
        if not isinstance(raw_groups, list):
            continue
        for raw_group in cast(list[object], raw_groups):
            if not isinstance(raw_group, list):
                continue
            group = sorted(
                value.strip()
                for value in cast(list[object], raw_group)
                if isinstance(value, str) and value.strip()
            )
            if group:
                groups.add("|".join(group))
    return groups


def preflight_steps(preflight_report: dict[str, object]) -> list[dict[str, object]]:
    raw_steps = preflight_report.get("steps")
    if not isinstance(raw_steps, list):
        return []
    steps: list[dict[str, object]] = []
    for raw_step in cast(list[object], raw_steps):
        if isinstance(raw_step, dict):
            steps.append(cast(dict[str, object], raw_step))
    return steps


def preflight_step_report(step: dict[str, object], environ: Mapping[str, str]) -> dict[str, object]:
    requirement = step_required_env(step)
    missing = missing_env_values(requirement.get("variables", []), environ)
    missing_any_of = missing_any_of_groups(requirement.get("any_of", []), environ)
    optional_missing = missing_env_values(requirement.get("optional", []), environ)
    placeholder_env = placeholder_env_values(requirement, environ)
    recommended_env = [
        value
        for value in cast(list[object], requirement.get("recommended", []))
        if isinstance(value, str) and value.strip()
    ]
    report: dict[str, object] = {
        "code": str(step.get("code", "")),
        "mode": str(step.get("mode", "")),
        "status": "blocked" if missing or missing_any_of else "ready",
        "missing": missing,
        "missing_any_of": missing_any_of,
        "optional_missing": optional_missing,
    }
    if placeholder_env:
        report["placeholder_env"] = placeholder_env
    if recommended_env:
        report["recommended_env"] = recommended_env
    command = step.get("command")
    if isinstance(command, list):
        report["command"] = [
            value for value in cast(list[object], command) if isinstance(value, str)
        ]
    evidence_uri = step.get("evidence_uri")
    if isinstance(evidence_uri, str) and evidence_uri.strip():
        report["evidence_uri"] = evidence_uri.strip()
    evidence_scope = step.get("evidence_scope")
    if isinstance(evidence_scope, str) and evidence_scope.strip():
        report["evidence_scope"] = evidence_scope.strip()
    prior_evidence = step.get("prior_evidence")
    if isinstance(prior_evidence, dict):
        report["prior_evidence"] = cast(dict[str, object], prior_evidence)
    return report


def prior_evidence_metadata(requirement: dict[str, Any]) -> dict[str, str]:
    field_map = {
        "evidence_status": "status",
        "evidence_scope": "scope",
        "evidence_revision_status": "revision_status",
        "evidence_git_commit": "git_commit",
    }
    metadata = {
        output_key: value.strip()
        for source_key, output_key in field_map.items()
        if isinstance((value := requirement.get(source_key)), str) and value.strip()
    }
    return metadata


def step_required_env(step: dict[str, object]) -> dict[str, object]:
    raw_required_env = step.get("required_env")
    if isinstance(raw_required_env, dict):
        return cast(dict[str, object], raw_required_env)
    return {}


def missing_env_values(raw_values: object, environ: Mapping[str, str]) -> list[str]:
    values: list[object] = cast(list[object], raw_values) if isinstance(raw_values, list) else []
    return [value for value in values if isinstance(value, str) and not env_value(environ, value)]


def missing_any_of_groups(raw_groups: object, environ: Mapping[str, str]) -> list[list[str]]:
    groups: list[object] = cast(list[object], raw_groups) if isinstance(raw_groups, list) else []
    missing_groups: list[list[str]] = []
    for raw_group in groups:
        if not isinstance(raw_group, list):
            continue
        group = [value for value in cast(list[object], raw_group) if isinstance(value, str)]
        if group and not any(env_value(environ, value) for value in group):
            missing_groups.append(group)
    return missing_groups


def placeholder_env_values(
    requirement: Mapping[str, object], environ: Mapping[str, str]
) -> list[str]:
    values: set[str] = set()
    for key in ("variables", "optional"):
        raw_values = requirement.get(key)
        if isinstance(raw_values, list):
            values.update(
                value for value in cast(list[object], raw_values) if isinstance(value, str)
            )
    raw_groups = requirement.get("any_of")
    if isinstance(raw_groups, list):
        for raw_group in cast(list[object], raw_groups):
            if isinstance(raw_group, list):
                values.update(
                    value for value in cast(list[object], raw_group) if isinstance(value, str)
                )
    return sorted(value for value in values if is_placeholder_env_value(environ.get(value, "")))


def smoke_plan_steps(plan: dict[str, object]) -> list[dict[str, object]]:
    raw_steps = plan.get("steps")
    if not isinstance(raw_steps, list):
        return []
    steps: list[dict[str, object]] = []
    for raw_step in cast(list[object], raw_steps):
        if isinstance(raw_step, dict):
            steps.append(cast(dict[str, object], raw_step))
    return steps


def run_automated_step(step: dict[str, object], runner: CommandRunner) -> CommandResult:
    results: list[CommandResult] = []
    for command in step_commands(step):
        result = runner(command, 120)
        results.append(result)
        if result.exit_code != 0:
            break
    combined = combine_command_results(results)
    if combined.exit_code != 0:
        return combined
    report_validation = validate_supporting_reports(step)
    if report_validation is None:
        return combined
    return CommandResult(
        exit_code=1,
        duration_ms=combined.duration_ms,
        stdout=combined.stdout,
        stderr=join_output([combined.stderr, report_validation]),
    )


def step_commands(step: dict[str, object]) -> list[list[str]]:
    raw_commands = step.get("commands")
    if isinstance(raw_commands, list):
        commands: list[list[str]] = []
        for raw_command in cast(list[object], raw_commands):
            if not isinstance(raw_command, list):
                continue
            raw_parts = cast(list[object], raw_command)
            if all(isinstance(part, str) for part in raw_parts):
                commands.append(cast(list[str], raw_command))
        if commands:
            return commands
    return [cast(list[str], step["command"])]


def combine_command_results(results: list[CommandResult]) -> CommandResult:
    if not results:
        return CommandResult(exit_code=1, duration_ms=0, stdout="", stderr="no command executed")
    failed = next((result for result in results if result.exit_code != 0), None)
    return CommandResult(
        exit_code=failed.exit_code if failed is not None else 0,
        duration_ms=sum(result.duration_ms for result in results),
        stdout="\n".join(result.stdout for result in results if result.stdout),
        stderr="\n".join(result.stderr for result in results if result.stderr),
    )


def validate_supporting_reports(step: dict[str, object]) -> str | None:
    for report_path in step_report_paths(step):
        try:
            report = read_json_object(Path(report_path))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            return f"supporting report failed: {report_path}: {error}"
        if not report_passed(report):
            return f"supporting report failed: {report_path}: {report_failure(report)}"
    return None


def step_report_paths(step: dict[str, object]) -> list[str]:
    raw_report_paths = step.get("report_paths")
    if not isinstance(raw_report_paths, list):
        return []
    return [
        value
        for value in cast(list[object], raw_report_paths)
        if isinstance(value, str) and value.strip()
    ]


def report_passed(report: dict[str, Any]) -> bool:
    return report.get("ok") is True or report.get("status") == "passed"


def report_failure(report: dict[str, Any]) -> str:
    error = report.get("error")
    if isinstance(error, str) and error.strip():
        return error
    status = report.get("status")
    item_failure = report_item_failure(report)
    if item_failure:
        return (
            f"{status}: {item_failure}"
            if isinstance(status, str) and status.strip()
            else item_failure
        )
    if isinstance(status, str) and status.strip():
        return status
    return "supporting report did not pass"


def report_item_failure(report: dict[str, Any]) -> str:
    items = report.get("items")
    if not isinstance(items, list):
        return ""
    for item in cast(list[object], items):
        if not isinstance(item, dict):
            continue
        item_mapping = cast(dict[str, object], item)
        if item_mapping.get("status") == "passed":
            continue
        raw_name = item_mapping.get("name")
        raw_failure = item_mapping.get("failure")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        failure = raw_failure.strip() if isinstance(raw_failure, str) else ""
        details = report_item_feedback_details(
            item_mapping,
            tag_recommendation=report.get("tagRecommendation"),
        )
        if name and failure:
            return f"{name}: {failure}{details}"
        if name:
            return f"{name}{details}"
        if failure:
            return f"{failure}{details}"
    return ""


def report_item_feedback_details(
    item: dict[str, object],
    *,
    tag_recommendation: object = None,
) -> str:
    feedback_promotion = item.get("feedbackPromotion")
    details: list[str] = []
    tag_recommendation_detail = tag_recommendation_details(tag_recommendation)
    tag_recommendation_appended = False
    dataset_name = item_string_summary(item, "datasetName")
    if dataset_name:
        details.append(f"datasetName={dataset_name}")
    source_suite = item_string_summary(item, "sourceSuite")
    if source_suite:
        details.append(f"sourceSuite={source_suite}")
    live_sync_command = item_string_summary(item, "liveSyncCommand")
    if live_sync_command:
        details.append(f"liveSyncCommand={summary_quoted_value(live_sync_command)}")
    readiness_command = item_string_summary(item, "readinessCommand")
    if readiness_command:
        details.append(f"readinessCommand={summary_quoted_value(readiness_command)}")
    product_boundary_readiness_command = item_string_summary(
        item,
        "productBoundaryReadinessCommand",
    )
    if product_boundary_readiness_command:
        details.append(
            "productBoundaryReadinessCommand="
            f"{summary_quoted_value(product_boundary_readiness_command)}"
        )
    required_readiness_reports = string_list_summary(item.get("requiredReadinessReports"))
    if required_readiness_reports:
        details.append(f"requiredReadinessReports={required_readiness_reports}")
    readiness_report_arg = item_string_summary(item, "readinessReportArg")
    if readiness_report_arg:
        details.append(f"readinessReportArg={summary_quoted_value(readiness_report_arg)}")
    required_env_any_of = required_env_any_of_summary(item.get("requiredEnvAnyOf"))
    if required_env_any_of:
        details.append(required_env_any_of)
    recommended_env = string_list_summary(item.get("recommendedEnv"))
    if recommended_env:
        details.append(f"recommendedEnv={recommended_env}")
    readiness_reports = equals_string_mapping_summary(item.get("readinessReports"))
    if readiness_reports:
        details.append(f"readinessReports={readiness_reports}")
    api_boundary = item.get("apiBoundary")
    if isinstance(api_boundary, dict):
        api_boundary_mapping = cast(dict[str, object], api_boundary)
        api_schemas = string_list_summary(api_boundary_mapping.get("nextActionSchemas"))
        if api_schemas:
            details.append(f"apiNextActionSchemas={api_schemas}")
        api_fields = string_list_summary(api_boundary_mapping.get("nextActionSchemaFields"))
        if api_fields:
            details.append(f"apiNextActionFields={api_fields}")
        run_fields = string_list_summary(
            api_boundary_mapping.get("runOperatorNextActionSchemaFields")
        )
        if run_fields:
            details.append(f"apiRunOperatorNextActionFields={run_fields}")
    next_actions = next_actions_summary(cast(Mapping[object, object], item))
    if next_actions:
        details.append(next_actions)
    if isinstance(feedback_promotion, dict):
        feedback_mapping = cast(dict[str, object], feedback_promotion)
        review_ids = feedback_mapping.get("feedbackReviewIds")
        if isinstance(review_ids, list):
            ids = ",".join(
                review_id.strip()
                for review_id in cast(list[object], review_ids)
                if isinstance(review_id, str) and review_id.strip()
            )
            if ids:
                details.append(f"feedbackReviewIds={ids}")
        rating_summary = feedback_mapping_counts_summary(
            feedback_mapping.get("feedbackRatingCounts")
        )
        if rating_summary:
            details.append(f"feedbackRatings={rating_summary}")
        source_summary = feedback_mapping_counts_summary(
            feedback_mapping.get("feedbackSourceCounts")
        )
        if source_summary:
            details.append(f"feedbackSources={source_summary}")
        workflow_summary = feedback_mapping_counts_summary(
            feedback_mapping.get("workflowTagCounts")
        )
        if workflow_summary:
            details.append(f"feedbackWorkflows={workflow_summary}")
        if tag_recommendation_detail:
            details.append(f"tagRecommendation={summary_quoted_value(tag_recommendation_detail)}")
            tag_recommendation_appended = True
        source_run_count = string_list_count_summary(item.get("sourceRunIds"))
        if source_run_count:
            details.append(f"sourceRunIds={source_run_count}")
        case_source_run_count = string_mapping_count_summary(item.get("caseSourceRunIds"))
        if case_source_run_count:
            details.append(f"caseSourceRunMappings={case_source_run_count}")
        review_action = feedback_mapping.get("reviewAction")
        if isinstance(review_action, str) and review_action.strip():
            details.append(f"reviewAction={summary_quoted_value(review_action.strip())}")
        review_actions = feedback_review_actions_summary(feedback_mapping.get("reviewActions"))
        if review_actions:
            details.append(f"reviewActions={summary_quoted_value(review_actions)}")
        bulk_review_action = feedback_mapping.get("bulkReviewAction")
        if isinstance(bulk_review_action, str) and bulk_review_action.strip():
            details.append(
                f"feedbackBulkReviewAction={summary_quoted_value(bulk_review_action.strip())}"
            )
    if tag_recommendation_detail and not tag_recommendation_appended:
        details.append(f"tagRecommendation={summary_quoted_value(tag_recommendation_detail)}")
    feedback_queue = item.get("feedbackReviewQueue")
    if isinstance(feedback_queue, dict):
        queue_mapping = cast(dict[str, object], feedback_queue)
        queue_case_count = string_list_count_summary(queue_mapping.get("caseIds"))
        if queue_case_count:
            details.append(f"feedbackQueueCases={queue_case_count}")
        queue_rating_summary = feedback_mapping_counts_summary(
            queue_mapping.get("feedbackRatingCounts")
        )
        if queue_rating_summary:
            details.append(f"feedbackQueueRatings={queue_rating_summary}")
        queue_source_summary = feedback_mapping_counts_summary(
            queue_mapping.get("feedbackSourceCounts")
        )
        if queue_source_summary:
            details.append(f"feedbackQueueSources={queue_source_summary}")
        queue_workflow_summary = feedback_mapping_counts_summary(
            queue_mapping.get("workflowTagCounts")
        )
        if queue_workflow_summary:
            details.append(f"feedbackQueueWorkflows={queue_workflow_summary}")
        queue_expected_citation_summary = feedback_mapping_counts_summary(
            queue_mapping.get("expectedCitationCounts")
        )
        if queue_expected_citation_summary:
            details.append(f"feedbackQueueExpectedCitations={queue_expected_citation_summary}")
        queue_case_ids = string_list_value(queue_mapping.get("caseIds"))
        queue_review_action: object = feedback_review_queue_action(
            feedback_rating_counts=queue_mapping.get("feedbackRatingCounts"),
            feedback_source_counts=queue_mapping.get("feedbackSourceCounts"),
            workflow_tag_counts=queue_mapping.get("workflowTagCounts"),
            case_ids=queue_case_ids,
            case_count=len(queue_case_ids),
        ) or queue_mapping.get("reviewAction")
        if isinstance(queue_review_action, str) and queue_review_action.strip():
            details.append(
                f"feedbackQueueReviewAction={summary_quoted_value(queue_review_action.strip())}"
            )
        queue_export_action: object = feedback_review_queue_export_action(
            feedback_rating_counts=queue_mapping.get("feedbackRatingCounts"),
            feedback_source_counts=queue_mapping.get("feedbackSourceCounts"),
            workflow_tag_counts=queue_mapping.get("workflowTagCounts"),
            case_ids=queue_case_ids,
            case_count=len(queue_case_ids),
        ) or queue_mapping.get("exportAction")
        if isinstance(queue_export_action, str) and queue_export_action.strip():
            details.append(
                f"feedbackQueueExportAction={summary_quoted_value(queue_export_action.strip())}"
            )
        queue_candidate_action = queue_mapping.get("candidateReviewAction")
        if not isinstance(queue_candidate_action, str) or not queue_candidate_action.strip():
            queue_candidate_action = feedback_queue_candidate_action_summary(
                cast(Mapping[object, object], item)
            )
        if queue_candidate_action.strip():
            details.append(
                f"feedbackQueueCandidateAction="
                f"{summary_quoted_value(queue_candidate_action.strip())}"
            )
        queue_bulk_review_action = queue_mapping.get("bulkReviewAction")
        if not isinstance(queue_bulk_review_action, str) or not queue_bulk_review_action.strip():
            queue_bulk_review_action = feedback_queue_bulk_review_action_summary(
                cast(Mapping[object, object], item)
            )
        if queue_bulk_review_action.strip():
            details.append(
                f"feedbackQueueBulkReviewAction="
                f"{summary_quoted_value(queue_bulk_review_action.strip())}"
            )
        queue_memory_action = queue_mapping.get("memoryLifecycleAction")
        if not isinstance(queue_memory_action, str) or not queue_memory_action.strip():
            queue_memory_action = feedback_review_queue_memory_lifecycle_action(
                queue_mapping.get("workflowTagCounts")
            )
        if queue_memory_action.strip():
            details.append(
                f"feedbackQueueMemoryAction={summary_quoted_value(queue_memory_action.strip())}"
            )
    product_boundary_details = product_boundary_summary(item)
    details.extend(product_boundary_details)
    release_gate = item.get("releaseGate")
    if isinstance(release_gate, dict):
        release_gate_mapping = cast(dict[str, object], release_gate)
        gate_status = release_gate_mapping.get("status")
        if isinstance(gate_status, str) and gate_status.strip():
            details.append(f"releaseGate={gate_status.strip()}")
        gate_reason = release_gate_mapping.get("reason")
        if isinstance(gate_reason, str) and gate_reason.strip():
            details.append(f"gateReason={gate_reason.strip()}")
        remediation = release_gate_mapping.get("remediation")
        if isinstance(remediation, list):
            remediation_items = [
                item.strip()
                for item in cast(list[object], remediation)
                if isinstance(item, str) and item.strip()
            ]
            if remediation_items:
                details.append(f"releaseNext={remediation_items[0]}")
                details.append(f"releasePlan={','.join(remediation_items)}")
        remediation_command = release_gate_mapping.get("remediationCommand")
        if isinstance(remediation_command, str) and remediation_command.strip():
            details.append(
                f"releaseGateRemediationCommand={summary_quoted_value(remediation_command.strip())}"
            )
    memory_lifecycle = item.get("memoryMaintenanceLifecycle")
    if isinstance(memory_lifecycle, dict):
        lifecycle_mapping = cast(dict[str, object], memory_lifecycle)
        review_surface = lifecycle_mapping.get("reviewSurface")
        if isinstance(review_surface, dict):
            review_surface_mapping = cast(dict[str, object], review_surface)
            lifecycle_action = review_surface_mapping.get("lifecycleGateAction")
            if isinstance(lifecycle_action, str) and lifecycle_action.strip():
                memory_status_counts = memory_status_counts_summary(item)
                if memory_status_counts:
                    details.append(f"memoryStatusCounts={memory_status_counts}")
                skipped_memory_status_counts = skipped_memory_status_counts_summary(item)
                if skipped_memory_status_counts:
                    details.append(f"skippedMemoryStatusCounts={skipped_memory_status_counts}")
                memory_admission_policy = memory_admission_policy_summary(item)
                if memory_admission_policy:
                    details.append(
                        f"memoryAdmissionPolicy={summary_quoted_value(memory_admission_policy)}"
                    )
                details.append(f"memoryContractAreas={','.join(MEMORY_CONTRACT_AREAS)}")
                details.append(f"memoryLifecycleAction='{lifecycle_action.strip()}'")
                proposal_actions = memory_proposal_next_actions_summary(lifecycle_mapping)
                if proposal_actions:
                    details.append(
                        f"memoryProposalNextActions={summary_quoted_value(proposal_actions)}"
                    )
                memory_sensors = memory_verification_sensors_summary(lifecycle_mapping)
                if memory_sensors:
                    details.append(
                        f"memoryVerificationSensors={summary_quoted_value(memory_sensors)}"
                    )
                memory_contracts = verification_sensor_contracts_summary(lifecycle_mapping)
                if memory_contracts:
                    details.append(
                        f"memoryReadinessContracts={summary_quoted_value(memory_contracts)}"
                    )
                memory_artifacts = verification_sensor_artifact_outputs_summary(lifecycle_mapping)
                if memory_artifacts:
                    details.append(
                        f"memoryArtifactOutputs={summary_quoted_value(memory_artifacts)}"
                    )
                memory_covers = verification_sensor_covers_summary(lifecycle_mapping)
                if memory_covers:
                    details.append(
                        f"memoryVerificationCovers={summary_quoted_value(memory_covers)}"
                    )
        dependency_warning_details = memory_dependency_warning_summary(lifecycle_mapping)
        details.extend(dependency_warning_details)
    rag_lifecycle = item.get("ragIngestionLifecycle")
    if isinstance(rag_lifecycle, dict):
        rag_sensors = verification_sensors_summary(cast(dict[str, object], rag_lifecycle))
        if rag_sensors:
            details.append(f"ragVerificationSensors={summary_quoted_value(rag_sensors)}")
    streaming_contract = item.get("streamingEventContract")
    if isinstance(streaming_contract, dict):
        stream_terminal_details = stream_terminal_next_actions_summary(
            cast(dict[str, object], streaming_contract)
        )
        details.extend(stream_terminal_details)
    context_findings = context_diagnostic_findings_summary(item)
    if context_findings:
        details.append(f"contextFindings={context_findings}")
    invalid_memory_status_labels = invalid_memory_status_labels_summary(item)
    if invalid_memory_status_labels:
        details.append(f"invalidMemoryStatusLabels={invalid_memory_status_labels}")
    citation_workflow_case_ids = context_diagnostics_string_list_summary(
        item,
        "citationWorkflowEvalCaseIds",
    )
    if citation_workflow_case_ids:
        details.append(f"citationWorkflowEvalCaseIds={citation_workflow_case_ids}")
    citation_workflow_tags = context_diagnostics_string_list_summary(
        item,
        "citationWorkflowTags",
    )
    if citation_workflow_tags:
        details.append(f"citationWorkflowTags={citation_workflow_tags}")
    return f" {' '.join(details)}" if details else ""


def feedback_review_actions_summary(value: object) -> str:
    if not isinstance(value, list):
        return ""
    actions = [
        action.strip()
        for action in cast(list[object], value)
        if isinstance(action, str) and action.strip()
    ]
    return "; ".join(actions)


def memory_verification_sensors_summary(memory_lifecycle: Mapping[str, object]) -> str:
    return verification_sensors_summary(memory_lifecycle)


def memory_proposal_next_actions_summary(memory_lifecycle: Mapping[str, object]) -> str:
    review_surface = memory_lifecycle.get("reviewSurface")
    if not isinstance(review_surface, Mapping):
        return ""
    action_ids = cast(Mapping[object, object], review_surface).get("proposalNextActionIds")
    if not isinstance(action_ids, Sequence) or isinstance(action_ids, str | bytes | bytearray):
        return ""
    names = [
        action_id.strip()
        for action_id in cast(Sequence[object], action_ids)
        if isinstance(action_id, str) and action_id.strip()
    ]
    return "; ".join(names)


def verification_sensors_summary(lifecycle: Mapping[str, object]) -> str:
    sensors = lifecycle.get("verificationSensors")
    if not isinstance(sensors, Mapping):
        return ""
    focused_tests = cast(Mapping[object, object], sensors).get("focusedTests")
    if not isinstance(focused_tests, Sequence) or isinstance(
        focused_tests, str | bytes | bytearray
    ):
        return ""
    commands = [
        command.strip()
        for command in cast(Sequence[object], focused_tests)
        if isinstance(command, str) and command.strip()
    ]
    return "; ".join(commands)


def verification_sensor_covers_summary(lifecycle: Mapping[str, object]) -> str:
    sensors = lifecycle.get("verificationSensors")
    if not isinstance(sensors, Mapping):
        return ""
    covers = cast(Mapping[object, object], sensors).get("covers")
    if not isinstance(covers, Sequence) or isinstance(covers, str | bytes | bytearray):
        return ""
    names = [
        name.strip()
        for name in cast(Sequence[object], covers)
        if isinstance(name, str) and name.strip()
    ]
    return "; ".join(names)


def verification_sensor_contracts_summary(lifecycle: Mapping[str, object]) -> str:
    sensors = lifecycle.get("verificationSensors")
    if not isinstance(sensors, Mapping):
        return ""
    contracts = cast(Mapping[object, object], sensors).get("releaseReadinessContracts")
    if not isinstance(contracts, Sequence) or isinstance(contracts, str | bytes | bytearray):
        return ""
    names = [
        name.strip()
        for name in cast(Sequence[object], contracts)
        if isinstance(name, str) and name.strip()
    ]
    return "; ".join(names)


def verification_sensor_artifact_outputs_summary(lifecycle: Mapping[str, object]) -> str:
    sensors = lifecycle.get("verificationSensors")
    if not isinstance(sensors, Mapping):
        return ""
    artifacts = cast(Mapping[object, object], sensors).get("artifactOutputs")
    if not isinstance(artifacts, Sequence) or isinstance(artifacts, str | bytes | bytearray):
        return ""
    names = [
        name.strip()
        for name in cast(Sequence[object], artifacts)
        if isinstance(name, str) and name.strip()
    ]
    return "; ".join(names)


def stream_terminal_next_actions_summary(contract: Mapping[str, object]) -> list[str]:
    terminal_actions = contract.get("terminalNextActions")
    if not isinstance(terminal_actions, dict):
        return ["streamTerminalNextActions=missing"]
    terminal_mapping = cast(dict[str, object], terminal_actions)
    details: list[str] = []
    if terminal_mapping.get("includedInCompletedPayload") is not True:
        details.append("streamTerminalNextActions=missing_from_completed_payload")
    action_ids = string_list_value(terminal_mapping.get("actionIds"))
    if action_ids:
        details.append(f"streamTerminalActionIds={','.join(action_ids)}")
    commands = string_list_value(terminal_mapping.get("commands"))
    if commands:
        details.append(f"streamTerminalCommands={summary_quoted_value('; '.join(commands))}")
    identity_fields = string_list_value(terminal_mapping.get("identityFields"))
    if identity_fields:
        details.append(f"streamTerminalIdentityFields={','.join(identity_fields)}")
    return details


def memory_dependency_warning_summary(lifecycle: Mapping[str, object]) -> list[str]:
    dependency_warnings = lifecycle.get("dependencyWarnings")
    if not isinstance(dependency_warnings, dict):
        return []
    warning_mapping = cast(dict[str, object], dependency_warnings)
    details: list[str] = []
    findings = warning_mapping.get("findings")
    if isinstance(findings, list):
        finding_count = sum(1 for item in cast(list[object], findings) if isinstance(item, dict))
        if finding_count > 0:
            details.append(f"memoryDependencyWarnings={finding_count}")
    checked_packages = string_list_value(warning_mapping.get("checkedPackages"))
    if checked_packages:
        details.append(f"memoryDependencyPackages={','.join(sorted(checked_packages))}")
    direct_pins = string_mapping_summary(warning_mapping.get("directPins"))
    if direct_pins:
        details.append(f"memoryDependencyDirectPins={direct_pins}")
    pin_source = item_string_summary(warning_mapping, "pinSource")
    if pin_source:
        details.append(f"memoryDependencyPinSource={pin_source}")
    review_command = item_string_summary(warning_mapping, "reviewCommand")
    if review_command:
        details.append(f"memoryDependencyReviewCommand={summary_quoted_value(review_command)}")
    remediation_command = item_string_summary(warning_mapping, "remediationCommand")
    if remediation_command:
        details.append(
            f"memoryDependencyRemediationCommand={summary_quoted_value(remediation_command)}"
        )
    return details


def summary_quoted_value(value: str) -> str:
    if "'" in value:
        return json.dumps(value)
    return f"'{value}'"


def item_string_summary(item: Mapping[str, object], field_name: str) -> str:
    value = item.get(field_name)
    return value.strip() if isinstance(value, str) else ""


def tag_recommendation_details(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    recommendation = cast(dict[object, object], value)
    details = [
        f"status={recommendation.get('status') or 'unknown'}",
        f"eligible={bool_detail(recommendation.get('eligible'))}",
        f"recommendedVersionBump={recommendation.get('recommendedVersionBump') or 'unknown'}",
        f"recommendedTagPattern={recommendation.get('recommendedTagPattern') or 'unknown'}",
        f"minorEligible={bool_detail(recommendation.get('minorEligible'))}",
    ]
    latest_tag = recommendation.get("latestTag")
    if isinstance(latest_tag, str) and latest_tag.strip():
        details.append(f"latestTag={latest_tag.strip()}")
    recommended_tag = recommendation.get("recommendedTag")
    if isinstance(recommended_tag, str) and recommended_tag.strip():
        details.append(f"recommendedTag={recommended_tag.strip()}")
    tag_selection_reason = recommendation.get("tagSelectionReason")
    if isinstance(tag_selection_reason, str) and tag_selection_reason.strip():
        details.append(f"tagSelectionReason={summary_quoted_value(tag_selection_reason.strip())}")
    blocking_reports = string_list_summary(recommendation.get("blockingReports"))
    if blocking_reports:
        details.append(f"blockingReports={blocking_reports}")
    root_blocking_reports = string_list_summary(recommendation.get("rootBlockingReports"))
    if root_blocking_reports:
        details.append(f"rootBlockingReports={root_blocking_reports}")
    downstream_blocked_reports = string_list_summary(recommendation.get("downstreamBlockedReports"))
    if downstream_blocked_reports:
        details.append(f"downstreamBlockedReports={downstream_blocked_reports}")
    minor_boundary_reports = string_list_summary(recommendation.get("minorBoundaryReports"))
    if minor_boundary_reports:
        details.append(f"minorBoundaryReports={minor_boundary_reports}")
    passed_reports = string_list_summary(recommendation.get("passedReports"))
    if passed_reports:
        details.append(f"passedReports={passed_reports}")
    warning_reports = string_list_summary(recommendation.get("warningReports"))
    if warning_reports:
        details.append(f"warningReports={warning_reports}")
    warning_review_required = recommendation.get("warningReviewRequired")
    if warning_review_required is not None:
        details.append(f"warningReviewRequired={bool_detail(warning_review_required)}")
    minor_blocked_reason = recommendation.get("minorBlockedReason")
    if isinstance(minor_blocked_reason, str) and minor_blocked_reason.strip():
        details.append(f"minorBlockedReason={summary_quoted_value(minor_blocked_reason.strip())}")
    minor_blocked_reports = string_list_summary(recommendation.get("minorBlockedReports"))
    if minor_blocked_reports:
        details.append(f"minorBlockedReports={minor_blocked_reports}")
    minor_boundary_missing = string_list_summary(recommendation.get("minorBoundaryMissingEvidence"))
    if minor_boundary_missing:
        details.append(f"minorBoundaryMissing={minor_boundary_missing}")
    minor_boundary_remediation_command = recommendation.get("minorBoundaryRemediationCommand")
    if (
        isinstance(minor_boundary_remediation_command, str)
        and minor_boundary_remediation_command.strip()
    ):
        minor_boundary_remediation_command = normalize_rag_candidate_eval_apply_action(
            minor_boundary_remediation_command.strip()
        )
        details.append(
            "minorBoundaryRemediationCommand="
            f"{summary_quoted_value(minor_boundary_remediation_command)}"
        )
    next_action = recommendation.get("nextAction")
    if isinstance(next_action, str) and next_action.strip():
        details.append(f"nextAction={json.dumps(next_action.strip())}")
    next_action_id = recommendation.get("nextActionId")
    if isinstance(next_action_id, str) and next_action_id.strip():
        details.append(f"nextActionId={next_action_id.strip()}")
    for field_name in ("readyNextActionIds", "blockedNextActionIds"):
        action_ids = string_list_summary(recommendation.get(field_name))
        if action_ids:
            details.append(f"{field_name}={action_ids}")
    next_action_states = action_state_mapping_summary(recommendation.get("nextActionStates"))
    if next_action_states:
        details.append(f"nextActionStates={next_action_states}")
    next_action_command = recommendation.get("nextActionCommand")
    if isinstance(next_action_command, str) and next_action_command.strip():
        details.append(f"nextActionCommand={summary_quoted_value(next_action_command.strip())}")
    next_action_env_file_command = recommendation.get("nextActionEnvFileCommand")
    if isinstance(next_action_env_file_command, str) and next_action_env_file_command.strip():
        details.append(
            f"nextActionEnvFileCommand={summary_quoted_value(next_action_env_file_command.strip())}"
        )
    release_readiness_command = recommendation.get("releaseReadinessCommand")
    if isinstance(release_readiness_command, str) and release_readiness_command.strip():
        details.append(
            f"releaseReadinessCommand={summary_quoted_value(release_readiness_command.strip())}"
        )
    preflight_file = recommendation.get("preflightFile")
    if isinstance(preflight_file, str) and preflight_file.strip():
        details.append(f"preflightFile={summary_quoted_value(preflight_file.strip())}")
    preflight_env_template = recommendation.get("preflightEnvTemplate")
    if isinstance(preflight_env_template, str) and preflight_env_template.strip():
        details.append(
            f"preflightEnvTemplate={summary_quoted_value(preflight_env_template.strip())}"
        )
    remediation_command = recommendation.get("remediationCommand")
    if isinstance(remediation_command, str) and remediation_command.strip():
        details.append(f"remediationCommand={summary_quoted_value(remediation_command.strip())}")
    readiness_report_arg = recommendation.get("readinessReportArg")
    if isinstance(readiness_report_arg, str) and readiness_report_arg.strip():
        details.append(f"readinessReportArg={summary_quoted_value(readiness_report_arg.strip())}")
    required_readiness_reports = string_list_summary(recommendation.get("requiredReadinessReports"))
    if required_readiness_reports:
        details.append(f"requiredReadinessReports={required_readiness_reports}")
    readiness_reports = equals_string_mapping_summary(recommendation.get("readinessReports"))
    if readiness_reports:
        details.append(f"readinessReports={readiness_reports}")
    required_env_any_of = required_env_any_of_summary(recommendation.get("requiredEnvAnyOf"))
    if required_env_any_of:
        details.append(required_env_any_of)
    missing_env = string_list_summary(recommendation.get("missingEnv"))
    if missing_env:
        details.append(f"missingEnv={missing_env}")
    missing_env_any_of = string_list_summary(recommendation.get("missingEnvAnyOf"))
    if missing_env_any_of:
        details.append(f"missingEnvAnyOf={missing_env_any_of}")
    recommended_env = string_list_summary(recommendation.get("recommendedEnv"))
    if recommended_env:
        details.append(f"recommendedEnv={recommended_env}")
    blocking_env_action_id = recommendation.get("blockingEnvActionId")
    if isinstance(blocking_env_action_id, str) and blocking_env_action_id.strip():
        details.append(f"blockingEnvActionId={blocking_env_action_id.strip()}")
    blocking_required_env_any_of = required_env_any_of_summary(
        recommendation.get("blockingRequiredEnvAnyOf")
    )
    if blocking_required_env_any_of:
        details.append(
            blocking_required_env_any_of.replace(
                "requiredEnvAnyOf",
                "blockingRequiredEnvAnyOf",
            )
        )
    blocking_missing_env_any_of = string_list_summary(recommendation.get("blockingMissingEnvAnyOf"))
    if blocking_missing_env_any_of:
        details.append(f"blockingMissingEnvAnyOf={blocking_missing_env_any_of}")
    blocking_recommended_env = string_list_summary(recommendation.get("blockingRecommendedEnv"))
    if blocking_recommended_env:
        details.append(f"blockingRecommendedEnv={blocking_recommended_env}")
    for identity_key in ("feedbackId", "evalCaseId", "sourceRunId", "candidateTag"):
        identity_value = recommendation.get(identity_key)
        if isinstance(identity_value, str) and identity_value.strip():
            details.append(f"{identity_key}={summary_quoted_value(identity_value.strip())}")
    for tag_key in ("feedbackTags", "workflowTags"):
        tag_values = string_list_summary(recommendation.get(tag_key))
        if tag_values:
            details.append(f"{tag_key}={tag_values}")
    details.extend(blocking_next_actions_details(recommendation.get("blockingNextActions")))
    return " ".join(details)


def blocking_next_actions_details(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    details: list[str] = []
    reports: list[str] = []
    actions = cast(list[object], value)
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_mapping = cast(dict[object, object], action)
        report = action_mapping.get("report")
        if not isinstance(report, str) or not report.strip():
            continue
        report_name = report.strip()
        reports.append(report_name)
        for field_name in (
            "nextAction",
            "nextActionId",
            "nextActionCommand",
            "nextActionEnvFileCommand",
            "preflightEnvFileCommand",
            "releaseSmokeEnvFileCommand",
            "remediationCommand",
            "requiredReviewNote",
        ):
            field_value = action_mapping.get(field_name)
            if not isinstance(field_value, str) or not field_value.strip():
                continue
            rendered = (
                field_value.strip()
                if field_name == "nextActionId"
                else summary_quoted_value(field_value.strip())
            )
            details.append(f"blockingNextAction.{report_name}.{field_name}={rendered}")
        for field_name in (
            "missingEnv",
            "missingEnvAnyOf",
            "recommendedEnv",
            "readyNextActionIds",
            "blockedNextActionIds",
        ):
            summary = string_list_summary(action_mapping.get(field_name))
            if summary:
                details.append(f"blockingNextAction.{report_name}.{field_name}={summary}")
        next_action_states = action_state_mapping_summary(action_mapping.get("nextActionStates"))
        if next_action_states:
            details.append(
                f"blockingNextAction.{report_name}.nextActionStates={next_action_states}"
            )
        required_env_any_of = required_env_any_of_summary(action_mapping.get("requiredEnvAnyOf"))
        if required_env_any_of:
            details.append(
                required_env_any_of.replace(
                    "requiredEnvAnyOf",
                    f"blockingNextAction.{report_name}.requiredEnvAnyOf",
                )
            )
    if not reports:
        return []
    return [f"blockingNextActions={','.join(reports)}", *details]


def action_state_mapping_summary(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    parts = [
        f"{action_id.strip()}={state.strip()}"
        for action_id, state in cast(dict[object, object], value).items()
        if isinstance(action_id, str)
        and action_id.strip()
        and isinstance(state, str)
        and state.strip()
    ]
    return ",".join(parts)


def product_boundary_summary(item: dict[str, object]) -> list[str]:
    value = item.get("productCapabilityBoundary")
    if not isinstance(value, dict):
        return []
    boundary = cast(dict[object, object], value)
    details: list[str] = []
    capability = boundary.get("capability")
    if isinstance(capability, str) and capability.strip():
        details.append(f"productCapability={capability.strip()}")
    minor_eligible = boundary.get("minorEligible")
    if isinstance(minor_eligible, bool):
        details.append(f"productBoundaryMinorEligible={bool_detail(minor_eligible)}")
    evidence = string_list_summary(boundary.get("evidence"))
    if evidence:
        details.append(f"productBoundaryEvidence={evidence}")
    resolved_evidence = string_list_summary(item.get("productBoundaryResolvedEvidence"))
    if resolved_evidence:
        details.append(f"productBoundaryResolved={resolved_evidence}")
    resolved_by = item.get("productBoundaryResolvedByReports")
    if isinstance(resolved_by, dict):
        resolved_by_mapping = cast(Mapping[object, object], resolved_by)
        for evidence_name, report_name in sorted(resolved_by_mapping.items()):
            if not isinstance(evidence_name, str) or not evidence_name.strip():
                continue
            if not isinstance(report_name, str) or not report_name.strip():
                continue
            details.append(
                f"productBoundaryResolvedBy.{evidence_name.strip()}={report_name.strip()}"
            )
    missing_evidence = string_list_summary(boundary.get("missingEvidence"))
    if missing_evidence:
        details.append(f"productBoundaryMissing={missing_evidence}")
        missing_items = {entry.strip() for entry in missing_evidence.split(",") if entry.strip()}
        resolved_items = {entry.strip() for entry in resolved_evidence.split(",") if entry.strip()}
        if (
            "rag_ingestion_lifecycle" in missing_items
            and "rag_ingestion_lifecycle" not in resolved_items
        ):
            details.append(
                "productBoundaryRemediationAction="
                f"{summary_quoted_value(rag_ingestion_lifecycle_remediation_command())}"
            )
        if any(
            missing_item == "eval_promotion_apply_coverage"
            or missing_item.startswith("eval_promotion_apply_coverage.")
            or missing_item.startswith("context_manifest_diagnostics.citationWorkflow")
            for missing_item in missing_items
        ):
            eval_apply_action = item.get("ragCandidateEvalApplyAction")
            if isinstance(eval_apply_action, str) and eval_apply_action.strip():
                eval_apply_action = normalize_rag_candidate_eval_apply_action(
                    eval_apply_action.strip()
                )
                details.append(
                    f"productBoundaryRemediationAction={summary_quoted_value(eval_apply_action)}"
                )
        if any(
            missing_item.startswith("feedback_promotion.") and missing_item not in resolved_items
            for missing_item in missing_items
        ):
            feedback_review_action = product_boundary_feedback_review_action(item)
            if feedback_review_action:
                details.append(
                    "productBoundaryFeedbackReviewAction="
                    f"{summary_quoted_value(feedback_review_action)}"
                )
    return details


def normalize_rag_candidate_eval_apply_action(command: str) -> str:
    if (
        "reactor-runs promote-eval" not in command
        or "rag-ingestion-candidate" not in command
        or "--apply-dry-run" not in command
    ):
        return command
    try:
        tokens = shlex.split(command)
    except ValueError:
        return command
    return shlex.join(part for part in tokens if part != "--apply-dry-run")


def product_boundary_feedback_review_action(item: dict[str, object]) -> str:
    for key in ("feedbackReviewQueue", "feedbackPromotion"):
        value = item.get(key)
        if not isinstance(value, dict):
            continue
        action = cast(dict[object, object], value).get("bulkReviewAction")
        if isinstance(action, str) and action.strip():
            return action.strip()
    return ""


def bool_detail(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return "unknown"


def string_list_summary(value: object) -> str:
    if not isinstance(value, list):
        return ""
    values = [
        item.strip() for item in cast(list[object], value) if isinstance(item, str) and item.strip()
    ]
    return ",".join(values)


def feedback_mapping_counts_summary(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    pairs = [
        (key.strip(), count)
        for key, count in cast(dict[object, object], value).items()
        if isinstance(key, str)
        and key.strip()
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count > 0
    ]
    return ",".join(f"{key}={count}" for key, count in sorted(pairs))


def string_list_count_summary(value: object) -> str:
    if not isinstance(value, list):
        return ""
    count = sum(1 for item in cast(list[object], value) if isinstance(item, str) and item.strip())
    return str(count) if count > 0 else ""


def string_list_value(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        item.strip() for item in cast(list[object], value) if isinstance(item, str) and item.strip()
    ]


def required_env_any_of_summary(value: object) -> str:
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for index, group in enumerate(cast(list[object], value)):
        env_names = string_list_value(group)
        if env_names:
            parts.append(f"requiredEnvAnyOf.{index}={'|'.join(env_names)}")
    return " ".join(parts)


def string_mapping_count_summary(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    count = sum(
        1
        for key, item in cast(dict[object, object], value).items()
        if isinstance(key, str) and key.strip() and isinstance(item, str) and item.strip()
    )
    return str(count) if count > 0 else ""


def string_mapping_summary(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    pairs = [
        (key.strip(), item.strip())
        for key, item in cast(dict[object, object], value).items()
        if isinstance(key, str) and key.strip() and isinstance(item, str) and item.strip()
    ]
    return ",".join(f"{key}{item}" for key, item in sorted(pairs))


def equals_string_mapping_summary(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    pairs = [
        (key.strip(), item.strip())
        for key, item in cast(dict[object, object], value).items()
        if isinstance(key, str) and key.strip() and isinstance(item, str) and item.strip()
    ]
    return ",".join(f"{key}={item}" for key, item in sorted(pairs))


def memory_status_counts_summary(item: dict[str, object]) -> str:
    diagnostics = item.get("contextManifestDiagnostics")
    if not isinstance(diagnostics, dict):
        return ""
    diagnostics_mapping = cast(dict[object, object], diagnostics)
    counts = diagnostics_mapping.get("memoryStatusCounts")
    return memory_diagnostic_counts_summary(counts)


def skipped_memory_status_counts_summary(item: dict[str, object]) -> str:
    diagnostics = item.get("contextManifestDiagnostics")
    if not isinstance(diagnostics, dict):
        return ""
    diagnostics_mapping = cast(dict[object, object], diagnostics)
    counts = diagnostics_mapping.get("skippedMemoryStatusCounts")
    return memory_diagnostic_counts_summary(counts)


def memory_admission_policy_summary(item: dict[str, object]) -> str:
    diagnostics = item.get("contextManifestDiagnostics")
    if not isinstance(diagnostics, dict):
        return ""
    diagnostics_mapping = cast(dict[object, object], diagnostics)
    policy = diagnostics_mapping.get("memoryAdmissionPolicy")
    if not isinstance(policy, dict):
        return ""
    policy_mapping = cast(dict[object, object], policy)
    fields = (
        "activeOnly",
        "missingStatusExcluded",
        "supersededExcluded",
        "tombstonedExcluded",
    )
    parts: list[str] = []
    for field in fields:
        value = policy_mapping.get(field)
        if isinstance(value, bool):
            parts.append(f"{field}={str(value).lower()}")
    return "; ".join(parts)


def invalid_memory_status_labels_summary(item: dict[str, object]) -> str:
    diagnostics = item.get("contextManifestDiagnostics")
    if not isinstance(diagnostics, dict):
        return ""
    labels: set[str] = set()
    diagnostics_mapping = cast(dict[object, object], diagnostics)
    for field_name in ("memoryStatusCounts", "skippedMemoryStatusCounts"):
        counts = diagnostics_mapping.get(field_name)
        if not isinstance(counts, dict):
            continue
        for label in cast(dict[object, object], counts):
            if isinstance(label, str) and label.strip():
                clean_label = label.strip()
                if clean_label not in ALLOWED_MEMORY_STATUS_COUNT_LABELS:
                    labels.add(clean_label)
    return ",".join(sorted(labels))


def memory_diagnostic_counts_summary(counts: object) -> str:
    if not isinstance(counts, dict):
        return ""
    pairs = [
        (key.strip(), count)
        for key, count in cast(dict[object, object], counts).items()
        if isinstance(key, str)
        and key.strip()
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count >= 0
    ]
    return ",".join(f"{key}={count}" for key, count in sorted(pairs))


def context_diagnostic_findings_summary(item: dict[str, object]) -> str:
    diagnostics = item.get("contextManifestDiagnostics")
    if not isinstance(diagnostics, dict):
        return ""
    diagnostics_mapping = cast(dict[object, object], diagnostics)
    findings = diagnostics_mapping.get("findings")
    if not isinstance(findings, list):
        return ""
    codes: list[str] = []
    for finding in cast(list[object], findings):
        if not isinstance(finding, dict):
            continue
        finding_mapping = cast(dict[object, object], finding)
        code = finding_mapping.get("code")
        if isinstance(code, str) and code.strip():
            codes.append(code.strip())
    return ",".join(dict.fromkeys(codes))


def context_diagnostics_string_list_summary(item: dict[str, object], field_name: str) -> str:
    diagnostics = item.get("contextManifestDiagnostics")
    if not isinstance(diagnostics, dict):
        return ""
    diagnostics_mapping = cast(dict[object, object], diagnostics)
    values = diagnostics_mapping.get(field_name)
    if not isinstance(values, list):
        return ""
    return ",".join(
        dict.fromkeys(
            value.strip()
            for value in cast(list[object], values)
            if isinstance(value, str) and value.strip()
        )
    )


def join_output(parts: Sequence[str]) -> str:
    return "\n".join(part for part in parts if part)


def automated_step_report(
    step: dict[str, object],
    result: CommandResult,
    *,
    redaction_values: Sequence[str] = (),
) -> dict[str, object]:
    return {
        **step_report_base(step),
        "status": "passed" if result.exit_code == 0 else "failed",
        "exit_code": result.exit_code,
        "duration_ms": result.duration_ms,
        "stdout": redact_output(result.stdout, redaction_values),
        "stderr": redact_output(result.stderr, redaction_values),
    }


def redact_output(value: str, redaction_values: Sequence[str]) -> str:
    redacted = value
    for redaction_value in redaction_values:
        if len(redaction_value) >= 6:
            redacted = redacted.replace(redaction_value, "[redacted]")
    return redacted


def skipped_manual_step_report(step: dict[str, object]) -> dict[str, object]:
    return {
        **step_report_base(step),
        "status": "skipped",
        "exit_code": 0,
        "duration_ms": 0,
        "stdout": "",
        "stderr": "manual release evidence required",
    }


def blocked_preflight_step_report(
    step: dict[str, object],
    preflight_step: dict[str, object],
) -> dict[str, object]:
    raw_missing_any_of = preflight_step.get("missing_any_of", [])
    missing_any_of = (
        [
            group
            for group in (
                string_list_value(raw_group) for raw_group in cast(list[object], raw_missing_any_of)
            )
            if group
        ]
        if isinstance(raw_missing_any_of, list)
        else []
    )
    report = {
        **step_report_base(step),
        "status": "blocked",
        "exit_code": 0,
        "duration_ms": 0,
        "stdout": "",
        "stderr": "required environment is missing",
        "failure": "release smoke run blocked by missing environment",
        "missing": string_list_value(preflight_step.get("missing")),
        "missing_any_of": missing_any_of,
        "optional_missing": string_list_value(preflight_step.get("optional_missing")),
    }
    placeholder_env = string_list_value(preflight_step.get("placeholder_env"))
    if placeholder_env:
        report["placeholder_env"] = placeholder_env
    prior_evidence = preflight_step.get("prior_evidence")
    if isinstance(prior_evidence, dict):
        report["prior_evidence"] = cast(dict[str, object], prior_evidence)
    return report


def step_report_base(step: dict[str, object]) -> dict[str, object]:
    report: dict[str, object] = {
        "code": str(step.get("code", "")),
        "mode": str(step.get("mode", "")),
        "evidence_scope": str(step.get("evidence_scope", "")),
        "release_gate_closer": bool(step.get("release_gate_closer", False)),
        "evidence_uri": str(step.get("evidence_uri", "")),
    }
    report_paths = step_report_paths(step)
    if report_paths:
        report["report_paths"] = report_paths
    required_env = step.get("required_env")
    if isinstance(required_env, dict):
        report["required_env"] = cast(dict[str, object], required_env)
    return report


def run_command(
    command: list[str],
    timeout_seconds: int,
    *,
    environ: Mapping[str, str] | None = None,
) -> CommandResult:
    started = time.monotonic()
    completed = subprocess.run(  # noqa: S603
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        env=dict(environ) if environ is not None else None,
    )
    return CommandResult(
        exit_code=completed.returncode,
        duration_ms=int((time.monotonic() - started) * 1000),
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def parse_plan_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a Reactor release smoke execution plan from readiness JSON."
    )
    parser.add_argument("--readiness", required=True, help="Path to readiness JSON")
    parser.add_argument("--output", required=True, help="Path to write smoke plan JSON")
    parser.add_argument(
        "--evidence-scope",
        action="append",
        default=[],
        help=(
            "Only include plan steps with this evidence_scope, for example local_contract. "
            "May be provided more than once."
        ),
    )
    return parser.parse_args(argv)


def parse_run_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run automated Reactor release smoke plan steps.")
    parser.add_argument("--plan", required=True, help="Path to release smoke plan JSON")
    parser.add_argument(
        "--env-file",
        action="append",
        default=[],
        help="Optional .env file values used for preflight checks",
    )
    parser.add_argument("--report-file", default="", help="Path to write smoke run report JSON")
    parser.add_argument(
        "--preflight-file",
        default="",
        help="Optional path to write required-env preflight JSON before running",
    )
    parser.add_argument(
        "--preflight-env-template",
        default="",
        help="Optional path to write a .env template from missing preflight variables",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Write --preflight-file and skip smoke command execution",
    )
    parser.add_argument(
        "--evidence-input",
        action="append",
        default=[],
        help="Existing release evidence JSON file to merge before --evidence-output",
    )
    parser.add_argument(
        "--evidence-output",
        default="",
        help="Optional path to write release evidence from passed gate-closing steps",
    )
    parser.add_argument(
        "--verified-at",
        default="",
        help="ISO-8601 timestamp for --evidence-output",
    )
    parser.add_argument(
        "--readiness-output",
        default="",
        help="Optional path to write aggregated release readiness evidence JSON.",
    )
    parser.add_argument(
        "--readiness-report",
        action="append",
        default=[],
        help="Additional readiness report as name=path to include in --readiness-output.",
    )
    parser.add_argument(
        "--required-readiness-report",
        action="append",
        default=[],
        help="Report name required in --readiness-output.",
    )
    parser.add_argument(
        "--latest-tag",
        default="",
        help="Latest stable version tag, used by --readiness-output tagRecommendation.",
    )
    parser.add_argument(
        "--expected-commit",
        default="",
        help="Expected HEAD SHA for readiness provenance; defaults to the current git commit.",
    )
    parser.add_argument(
        "--max-readiness-input-age-seconds",
        type=int,
        default=21_600,
        help="Fail readiness when an input report is older than this many seconds.",
    )
    parser.add_argument(
        "--skip-release-evidence-readiness",
        action="store_true",
        help=(
            "Omit the release_evidence readiness item for local handoffs that only aggregate "
            "smoke_run plus explicit --readiness-report inputs."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_plan_args(argv)
    readiness_report = read_json_object(Path(str(args.readiness)))
    plan = build_release_smoke_plan(
        readiness_report,
        evidence_scopes=cast(list[str], args.evidence_scope),
    )
    write_json_report_file(Path(str(args.output)), plan)
    return 0


def run_main(argv: Sequence[str] | None = None) -> int:
    args = parse_run_args(argv)
    plan = read_json_object(Path(str(args.plan)))
    env_file_values = cast(list[str], args.env_file)
    explicit_preflight_env_template = str(args.preflight_env_template).strip()
    preflight_env_file = next((value.strip() for value in env_file_values if value.strip()), "")
    effective_preflight_env_template = preflight_env_file or explicit_preflight_env_template
    preflight_env_template_refresh_path = (
        explicit_preflight_env_template
        if preflight_env_file and explicit_preflight_env_template
        else ""
    )
    preflight_env_template_is_env_file = bool(preflight_env_file)
    try:
        preflight_environ = merged_environ(env_file_values)
        redaction_values = redaction_values_from_env_files(env_file_values)
    except OSError:
        report = env_file_unreadable_report(
            env_file=next((value.strip() for value in env_file_values if value.strip()), ""),
            plan_file=str(args.plan),
            preflight_file=(
                str(args.preflight_file).strip() or "reports/release-smoke-preflight.json"
            ),
            readiness_output=str(args.readiness_output),
        )
        output_path = str(args.report_file).strip() or str(args.preflight_file).strip()
        if output_path:
            write_json_report_file(Path(output_path), report)
        readiness_output = str(args.readiness_output).strip()
        if readiness_output:
            readiness_commit = str(args.expected_commit).strip() or current_git_commit()
            readiness_report = build_release_readiness_report_from_payloads(
                [("preflight", report, output_path or "release_smoke_env_file")],
                required_reports=["preflight", *cast(list[str], args.required_readiness_report)],
                latest_tag=str(args.latest_tag),
                expected_commit=readiness_commit,
                current_commit_sha=readiness_commit,
                max_input_age_seconds=max(1, int(args.max_readiness_input_age_seconds)),
            )
            write_json_report_file(Path(readiness_output), readiness_report)
        print(release_smoke_preflight_failure_summary(report), file=sys.stderr)
        return 1
    preflight_file = str(args.preflight_file).strip()
    preflight_report: dict[str, object] | None = None
    if preflight_file:
        preflight_report = run_release_smoke_preflight(plan, environ=preflight_environ)
        annotate_preflight_report_handoff(
            preflight_report,
            plan_file=str(args.plan),
            preflight_file=preflight_file,
            preflight_env_template=effective_preflight_env_template,
            evidence_output=str(args.evidence_output),
            readiness_output=str(args.readiness_output),
            readiness_reports=cast(list[str], args.readiness_report),
            required_readiness_reports=cast(list[str], args.required_readiness_report),
            latest_tag=str(args.latest_tag),
            skip_release_evidence_readiness=bool(args.skip_release_evidence_readiness),
            preflight_env_template_is_env_file=preflight_env_template_is_env_file,
            preflight_env_template_refresh_path=preflight_env_template_refresh_path,
        )
        write_json_report_file(Path(preflight_file), preflight_report)
        preflight_env_template = str(args.preflight_env_template).strip()
        if preflight_env_template:
            preflight_env_template_path = Path(preflight_env_template)
            ensure_parent_directory(preflight_env_template_path)
            preflight_env_template_path.write_text(
                build_preflight_env_template(preflight_report),
                encoding="utf-8",
            )
        if bool(args.preflight_only):
            readiness_output = str(args.readiness_output).strip()
            readiness_ok = True
            if readiness_output:
                readiness_report_values = cast(list[str], args.readiness_report)
                readiness_config_error: ValueError | None = None
                try:
                    extra_report_specs = extra_readiness_report_specs(readiness_report_values)
                except ValueError as error:
                    readiness_config_error = error
                    extra_report_specs = []
                try:
                    plan_report_specs = plan_readiness_report_specs(plan)
                except ValueError as error:
                    if readiness_config_error is None:
                        readiness_config_error = error
                    plan_report_specs = []
                extra_reports = extra_readiness_reports_from_specs(extra_report_specs)
                plan_reports = plan_readiness_reports_from_specs(plan_report_specs)
                required_readiness_reports = [
                    "preflight",
                    *cast(list[str], args.required_readiness_report),
                    *(name for name, _, required in plan_report_specs if required),
                    *(name for name, _ in extra_report_specs),
                    *(("readiness_report_config",) if readiness_config_error else ()),
                ]
                readiness_payloads: list[tuple[str, dict[str, Any], str]] = [
                    (
                        "preflight",
                        preflight_readiness_report(
                            preflight_report,
                            preflight_file,
                            plan_file=str(args.plan),
                            preflight_env_template=effective_preflight_env_template,
                            readiness_output=readiness_output,
                            readiness_reports=readiness_report_values,
                            required_readiness_reports=cast(
                                list[str], args.required_readiness_report
                            ),
                            latest_tag=str(args.latest_tag),
                            skip_release_evidence_readiness=bool(
                                args.skip_release_evidence_readiness
                            ),
                            preflight_env_template_is_env_file=preflight_env_template_is_env_file,
                            preflight_env_template_refresh_path=preflight_env_template_refresh_path,
                        ),
                        preflight_file,
                    )
                ]
                readiness_payloads.extend(extra_reports)
                readiness_payloads.extend(
                    (name, report, artifact) for name, report, artifact, _ in plan_reports
                )
                if readiness_config_error:
                    readiness_payloads.append(
                        (
                            "readiness_report_config",
                            invalid_readiness_report_config_report(
                                artifact=str(args.plan),
                                error=readiness_config_error,
                            ),
                            str(args.plan),
                        )
                    )
                readiness_commit = str(args.expected_commit).strip() or current_git_commit()
                readiness_report = build_release_readiness_report_from_payloads(
                    readiness_payloads,
                    required_reports=required_readiness_reports,
                    latest_tag=str(args.latest_tag),
                    expected_commit=readiness_commit,
                    current_commit_sha=readiness_commit,
                    max_input_age_seconds=max(1, int(args.max_readiness_input_age_seconds)),
                )
                write_json_report_file(Path(readiness_output), readiness_report)
                readiness_ok = readiness_report.get("ok") is True
                if not readiness_ok:
                    print(readiness_failure_summary(readiness_report), file=sys.stderr)
            elif preflight_report.get("ok") is not True:
                print(release_smoke_preflight_failure_summary(preflight_report), file=sys.stderr)
            return 0 if preflight_report["ok"] and readiness_ok else 1
    report_file = str(args.report_file).strip()
    if not report_file:
        raise ValueError("--report-file is required unless --preflight-only is used")
    if preflight_report is None and env_file_values:
        preflight_report = run_release_smoke_preflight(plan, environ=preflight_environ)
    command_runner = command_runner_with_environ(preflight_environ) if env_file_values else None
    report = run_release_smoke_plan(
        plan,
        report_file=Path(str(args.report_file)),
        command_runner=command_runner,
        redaction_values=redaction_values,
        preflight_report=preflight_report,
    )
    evidence_output = str(args.evidence_output).strip()
    evidence: dict[str, dict[str, str]] = {}
    if evidence_output:
        verified_at = str(args.verified_at).strip()
        if not verified_at:
            raise ValueError("--verified-at is required when --evidence-output is used")
        evidence_input_values = cast(list[str], args.evidence_input)
        evidence = merge_release_evidence(
            [read_release_evidence_file(Path(value)) for value in evidence_input_values],
            build_release_evidence_from_smoke_run(
                report,
                verified_at=verified_at,
                git_commit=current_git_commit(),
            ),
        )
        write_json_report_file(Path(evidence_output), evidence)
    readiness_output = str(args.readiness_output).strip()
    readiness_ok = True
    if readiness_output:
        readiness_report_values = cast(list[str], args.readiness_report)
        readiness_config_error: ValueError | None = None
        try:
            extra_report_specs = extra_readiness_report_specs(readiness_report_values)
        except ValueError as error:
            readiness_config_error = error
            extra_report_specs = []
        try:
            plan_report_specs = plan_readiness_report_specs(plan)
        except ValueError as error:
            if readiness_config_error is None:
                readiness_config_error = error
            plan_report_specs = []
        extra_reports = extra_readiness_reports_from_specs(extra_report_specs)
        plan_reports = plan_readiness_reports_from_specs(plan_report_specs)
        skip_release_evidence = bool(args.skip_release_evidence_readiness)
        required_readiness_reports = [
            *(("smoke_run",) if skip_release_evidence else DEFAULT_READINESS_REQUIRED_REPORTS),
            *cast(list[str], args.required_readiness_report),
            *(name for name, _, required in plan_report_specs if required),
            *(name for name, _ in extra_report_specs),
            *(("readiness_report_config",) if readiness_config_error else ()),
        ]
        readiness_payloads: list[tuple[str, dict[str, Any], str]] = [
            (
                "smoke_run",
                smoke_run_readiness_report(
                    report,
                    report_file,
                    plan_file=str(args.plan),
                    preflight_file=preflight_file or "reports/release-smoke-preflight.json",
                    preflight_env_template=(
                        effective_preflight_env_template
                        or "reports/release-smoke-preflight.env.example"
                    ),
                    report_file=report_file,
                    evidence_output=evidence_output,
                    readiness_output=readiness_output,
                    readiness_reports=readiness_report_values,
                    required_readiness_reports=cast(list[str], args.required_readiness_report),
                    latest_tag=str(args.latest_tag),
                    skip_release_evidence_readiness=skip_release_evidence,
                    preflight_env_template_is_env_file=preflight_env_template_is_env_file,
                    preflight_env_template_refresh_path=preflight_env_template_refresh_path,
                ),
                report_file,
            ),
        ]
        if not skip_release_evidence:
            readiness_payloads.append(
                (
                    "release_evidence",
                    release_evidence_readiness_report(
                        evidence,
                        evidence_output,
                        plan_file=str(args.plan),
                        report_file=report_file,
                    ),
                    evidence_output or "release-evidence",
                )
            )
        readiness_payloads.extend(extra_reports)
        readiness_payloads.extend(
            (name, report, artifact) for name, report, artifact, _ in plan_reports
        )
        if readiness_config_error:
            readiness_payloads.append(
                (
                    "readiness_report_config",
                    invalid_readiness_report_config_report(
                        artifact=str(args.plan),
                        error=readiness_config_error,
                    ),
                    str(args.plan),
                )
            )
        readiness_commit = str(args.expected_commit).strip() or current_git_commit()
        readiness_report = build_release_readiness_report_from_payloads(
            readiness_payloads,
            required_reports=required_readiness_reports,
            latest_tag=str(args.latest_tag),
            expected_commit=readiness_commit,
            current_commit_sha=readiness_commit,
            max_input_age_seconds=max(1, int(args.max_readiness_input_age_seconds)),
        )
        write_json_report_file(Path(readiness_output), readiness_report)
        readiness_ok = readiness_report.get("ok") is True
        if not readiness_ok:
            print(readiness_failure_summary(readiness_report), file=sys.stderr)
    return 0 if report["ok"] and readiness_ok else 1


def extra_readiness_reports(values: Sequence[str]) -> list[tuple[str, dict[str, Any], str]]:
    return extra_readiness_reports_from_specs(extra_readiness_report_specs(values))


def extra_readiness_report_specs(values: Sequence[str]) -> list[tuple[str, Path]]:
    specs: list[tuple[str, Path]] = []
    seen_names: set[str] = set()
    for value in values:
        name, separator, path_value = value.partition("=")
        if not separator or not name.strip() or not path_value.strip():
            raise ValueError("--readiness-report must use name=path")
        normalized_name = name.strip()
        if normalized_name in seen_names:
            raise ValueError(f"duplicate --readiness-report name: {normalized_name}")
        seen_names.add(normalized_name)
        specs.append((normalized_name, Path(path_value.strip())))
    return specs


def extra_readiness_reports_from_specs(
    specs: Sequence[tuple[str, Path]],
) -> list[tuple[str, dict[str, Any], str]]:
    reports: list[tuple[str, dict[str, Any], str]] = []
    for normalized_name, path in specs:
        if not path.exists():
            continue
        try:
            report = read_json_object(path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            report = unreadable_readiness_report(path=path, error=error)
        reports.append((normalized_name, report, str(path)))
    return reports


def unreadable_readiness_report(*, path: Path, error: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "failed",
        "scope": "readiness_report_input",
        "error": f"readiness report unreadable: {error}",
        "evidence": {
            "artifact": str(path),
            "owner": "reactor.release",
            "mode": "readiness_report_input",
        },
    }


def invalid_readiness_report_config_report(*, artifact: str, error: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "failed",
        "scope": "readiness_report_input",
        "error": f"invalid readiness report configuration: {error}",
        "evidence": {
            "artifact": artifact,
            "owner": "reactor.release",
            "mode": "readiness_report_input",
        },
    }


def plan_readiness_reports(
    plan: Mapping[str, object],
) -> list[tuple[str, dict[str, Any], str, bool]]:
    return plan_readiness_reports_from_specs(plan_readiness_report_specs(plan))


def plan_readiness_report_specs(
    plan: Mapping[str, object],
) -> list[tuple[str, Path, bool]]:
    specs: list[tuple[str, Path, bool]] = []
    seen_names: set[str] = set()
    for step in smoke_plan_steps(dict(plan)):
        raw_reports = step.get("readiness_reports")
        if not isinstance(raw_reports, list):
            continue
        for raw_report in cast(list[object], raw_reports):
            if not isinstance(raw_report, dict):
                continue
            report_mapping = cast(dict[object, object], raw_report)
            name = report_mapping.get("name")
            path_value = report_mapping.get("path")
            if not isinstance(name, str) or not name.strip():
                continue
            if not isinstance(path_value, str) or not path_value.strip():
                continue
            normalized_name = name.strip()
            if normalized_name in seen_names:
                raise ValueError(f"duplicate plan readiness report name: {normalized_name}")
            seen_names.add(normalized_name)
            specs.append(
                (normalized_name, Path(path_value.strip()), report_mapping.get("required") is True)
            )
    return specs


def plan_readiness_reports_from_specs(
    specs: Sequence[tuple[str, Path, bool]],
) -> list[tuple[str, dict[str, Any], str, bool]]:
    reports: list[tuple[str, dict[str, Any], str, bool]] = []
    for normalized_name, path, required in specs:
        if not path.exists():
            continue
        try:
            report = read_json_object(path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            report = unreadable_readiness_report(path=path, error=error)
        reports.append((normalized_name, report, str(path), required))
    return reports


def smoke_run_readiness_report(
    report: dict[str, object],
    artifact: str,
    *,
    plan_file: str = "reports/release-smoke-plan.json",
    preflight_file: str = "reports/release-smoke-preflight.json",
    preflight_env_template: str = "reports/release-smoke-preflight.env.example",
    report_file: str = "reports/release-smoke-run.json",
    evidence_output: str = "",
    readiness_output: str = "reports/release-readiness.json",
    readiness_reports: Sequence[str] = (),
    required_readiness_reports: Sequence[str] = (),
    latest_tag: str = "",
    skip_release_evidence_readiness: bool = False,
    preflight_env_template_is_env_file: bool = False,
    preflight_env_template_refresh_path: str = "",
) -> dict[str, Any]:
    ok = report.get("ok") is True
    report_status = report.get("status")
    status = (
        "passed"
        if ok
        else "skipped"
        if report_status == "skipped"
        else "blocked"
        if report_status == "blocked" or report_summary_count(report, "blocked")
        else "failed"
    )
    evidence: dict[str, object] = {
        "artifact": artifact,
        "owner": "reactor.release",
        "mode": "release_smoke_run",
        "smokeRunSummary": report.get("summary"),
        "smokeRunMissingEnv": sorted(unique_preflight_values(report, "missing")),
        "smokeRunMissingAnyOf": sorted(unique_preflight_groups(report, "missing_any_of")),
    }
    blocked_gates = preflight_blocked_gate_metadata(report)
    recommended_env = sorted(
        unique_preflight_values(report, "recommended_env")
        or unique_preflight_values({"steps": blocked_gates}, "recommended_env")
    )
    evidence["smokeRunRecommendedEnv"] = recommended_env
    if blocked_gates:
        evidence["smokeRunBlockedGates"] = blocked_gates
        evidence.update(
            blocked_env_remediation_fields(
                plan_file=plan_file,
                preflight_file=preflight_file,
                preflight_env_template=preflight_env_template,
                report_file=report_file,
                evidence_output=evidence_output,
                readiness_output=readiness_output,
                readiness_reports=readiness_reports,
                required_readiness_reports=required_readiness_reports,
                latest_tag=latest_tag,
                skip_release_evidence_readiness=skip_release_evidence_readiness,
                preflight_env_template_is_env_file=preflight_env_template_is_env_file,
                preflight_env_template_refresh_path=preflight_env_template_refresh_path,
            )
        )
    next_actions = report.get("nextActions")
    if isinstance(next_actions, list) and next_actions:
        evidence["nextActions"] = cast(list[object], next_actions)
    readiness_report = {
        "ok": ok,
        "status": status,
        "scope": "release_smoke_run",
        "evidence": evidence,
    }
    failure = report.get("failure")
    if isinstance(failure, str) and failure.strip():
        readiness_report["error"] = failure.strip()
    elif status == "blocked":
        readiness_report["error"] = "release smoke run blocked by missing environment"
    return readiness_report


def preflight_readiness_report(
    report: dict[str, object],
    artifact: str,
    *,
    plan_file: str = "reports/release-smoke-plan.json",
    preflight_env_template: str = "reports/release-smoke-preflight.env.example",
    readiness_output: str = "reports/release-readiness.json",
    readiness_reports: Sequence[str] = (),
    required_readiness_reports: Sequence[str] = (),
    latest_tag: str = "",
    skip_release_evidence_readiness: bool = False,
    preflight_env_template_is_env_file: bool = False,
    preflight_env_template_refresh_path: str = "",
) -> dict[str, Any]:
    plan_file = plan_file or "reports/release-smoke-plan.json"
    preflight_env_template = preflight_env_template or "reports/release-smoke-preflight.env.example"
    readiness_output = readiness_output or "reports/release-readiness.json"
    ok = report.get("ok") is True
    status = "passed" if ok else "blocked" if report_summary_count(report, "blocked") else "failed"
    evidence: dict[str, object] = {
        "artifact": artifact,
        "owner": "reactor.release",
        "mode": "release_smoke_preflight",
        "preflightSummary": report.get("summary"),
        "preflightMissingEnv": sorted(unique_preflight_values(report, "missing")),
        "preflightMissingAnyOf": sorted(unique_preflight_groups(report, "missing_any_of")),
    }
    blocked_gates = preflight_blocked_gate_metadata(report)
    recommended_env = sorted(
        unique_preflight_values(report, "recommended_env")
        or unique_preflight_values({"steps": blocked_gates}, "recommended_env")
    )
    if recommended_env:
        evidence["preflightRecommendedEnv"] = recommended_env
    ready_local_contract_actions = ready_local_contract_actions_from_preflight(report)
    if ready_local_contract_actions:
        evidence["readyLocalContractActions"] = ready_local_contract_actions
    if blocked_gates:
        evidence["preflightBlockedGates"] = blocked_gates
        evidence.update(
            blocked_env_remediation_fields(
                plan_file=plan_file,
                preflight_file=artifact,
                preflight_env_template=preflight_env_template,
                readiness_output=readiness_output,
                readiness_reports=readiness_reports,
                required_readiness_reports=required_readiness_reports,
                latest_tag=latest_tag,
                skip_release_evidence_readiness=skip_release_evidence_readiness,
                preflight_env_template_is_env_file=preflight_env_template_is_env_file,
                preflight_env_template_refresh_path=preflight_env_template_refresh_path,
            )
        )
    remediation = report.get("remediationCommand")
    if isinstance(remediation, str) and remediation.strip():
        evidence["remediationCommand"] = remediation.strip()
    next_actions = report.get("nextActions")
    if isinstance(next_actions, list) and next_actions:
        evidence["nextActions"] = cast(list[object], next_actions)
    readiness_report = {
        "ok": ok,
        "status": status,
        "scope": "release_smoke_preflight",
        "evidence": evidence,
    }
    if status == "blocked":
        failure = report.get("failure")
        if isinstance(failure, str) and failure.strip():
            readiness_report["error"] = failure.strip()
        else:
            readiness_report["error"] = "release smoke preflight blocked by missing environment"
    return readiness_report


def annotate_preflight_report_handoff(
    report: dict[str, object],
    *,
    plan_file: str = "reports/release-smoke-plan.json",
    preflight_file: str = "reports/release-smoke-preflight.json",
    preflight_env_template: str = "reports/release-smoke-preflight.env.example",
    evidence_output: str = "",
    readiness_output: str = "reports/release-readiness.json",
    readiness_reports: Sequence[str] = (),
    required_readiness_reports: Sequence[str] = (),
    latest_tag: str = "",
    skip_release_evidence_readiness: bool = False,
    preflight_env_template_is_env_file: bool = False,
    preflight_env_template_refresh_path: str = "",
) -> None:
    ok = report.get("ok") is True
    status = "passed" if ok else "blocked" if report_summary_count(report, "blocked") else "failed"
    report["status"] = status
    report["scope"] = "release_smoke_preflight"
    existing_failure = report.get("failure")
    has_failure = isinstance(existing_failure, str) and bool(existing_failure.strip())
    if status == "blocked" and not has_failure:
        report["failure"] = "release smoke preflight blocked by missing environment"
    preflight_env_template = (
        preflight_env_template.strip() or "reports/release-smoke-preflight.env.example"
    )
    report["preflightEnvTemplate"] = preflight_env_template
    if preflight_blocked_gate_metadata(report):
        remediation_fields = blocked_env_remediation_fields(
            plan_file=plan_file,
            preflight_file=preflight_file,
            preflight_env_template=preflight_env_template,
            evidence_output=evidence_output,
            readiness_output=(readiness_output.strip() or "reports/release-readiness.json"),
            readiness_reports=readiness_reports,
            required_readiness_reports=required_readiness_reports,
            latest_tag=latest_tag,
            skip_release_evidence_readiness=skip_release_evidence_readiness,
            preflight_env_template_is_env_file=preflight_env_template_is_env_file,
            preflight_env_template_refresh_path=preflight_env_template_refresh_path,
        )
        report.update(remediation_fields)
        report.update(blocked_env_next_action_fields(report, remediation_fields))


def blocked_env_remediation_fields(
    *,
    plan_file: str = "reports/release-smoke-plan.json",
    preflight_file: str = "reports/release-smoke-preflight.json",
    preflight_env_template: str = "reports/release-smoke-preflight.env.example",
    report_file: str = "reports/release-smoke-run.json",
    evidence_output: str = "",
    readiness_output: str = "reports/release-readiness.json",
    readiness_reports: Sequence[str] = (),
    required_readiness_reports: Sequence[str] = (),
    latest_tag: str = "",
    skip_release_evidence_readiness: bool = False,
    preflight_env_template_is_env_file: bool = False,
    preflight_env_template_refresh_path: str = "",
) -> dict[str, str]:
    preflight_env_template_is_env_file = (
        preflight_env_template_is_env_file
        or preflight_env_template.endswith(".env")
        or preflight_env_template.endswith(".local.env")
    )
    readiness_report_args = " ".join(
        f"--readiness-report {report.strip()}" for report in readiness_reports if report.strip()
    )
    required_report_args = " ".join(
        f"--required-readiness-report {report.strip()}"
        for report in required_readiness_reports
        if report.strip()
    )
    latest_tag_arg = f"--latest-tag {latest_tag.strip()}" if latest_tag.strip() else ""
    skip_release_evidence_arg = (
        "--skip-release-evidence-readiness" if skip_release_evidence_readiness else ""
    )
    extra_args = " ".join(
        arg
        for arg in (
            readiness_report_args,
            required_report_args,
            latest_tag_arg,
            skip_release_evidence_arg,
        )
        if arg
    )
    preflight_env_file_command = (
        f"uv run reactor-release-smoke-run --plan {plan_file} "
        f"--env-file {preflight_env_template} "
        f"--preflight-file {preflight_file} "
        f"--preflight-only --readiness-output {readiness_output}"
        f"{f' {extra_args}' if extra_args else ''}"
    )
    release_smoke_evidence_arg = (
        f"--evidence-output {evidence_output} "
        if evidence_output.strip() and not skip_release_evidence_readiness
        else ""
    )
    release_smoke_env_file_command = (
        f"uv run reactor-release-smoke-run --plan {plan_file} "
        f"--env-file {preflight_env_template} "
        f"--preflight-file {preflight_file} "
        f"--report-file {report_file} "
        "--verified-at $(date -u +%Y-%m-%dT%H:%M:%SZ) "
        f"{release_smoke_evidence_arg}"
        f"--readiness-output {readiness_output}"
        f"{f' {extra_args}' if extra_args else ''}"
    )
    remediation_command = (
        preflight_env_file_command
        if preflight_env_template_is_env_file
        else (
            f"uv run reactor-release-smoke-run --plan {plan_file} "
            f"--preflight-file {preflight_file} "
            f"--preflight-env-template {preflight_env_template} "
            f"--preflight-only --readiness-output {readiness_output}"
            f"{f' {extra_args}' if extra_args else ''}"
        )
    )
    fields = {
        "remediationCommand": remediation_command,
        "preflightEnvTemplate": preflight_env_template,
        "preflightEnvFileCommand": preflight_env_file_command,
        "releaseSmokeEnvFileCommand": release_smoke_env_file_command,
    }
    if preflight_env_template_is_env_file:
        refresh_path = (
            preflight_env_template_refresh_path.strip() or f"{preflight_env_template}.example"
        )
        fields["preflightEnvTemplateRefreshPath"] = refresh_path
        fields["preflightEnvTemplateRefreshCommand"] = (
            f"uv run reactor-release-smoke-run --plan {plan_file} "
            f"--preflight-file {preflight_file} "
            f"--preflight-env-template {refresh_path} "
            f"--preflight-only --readiness-output {readiness_output}"
            f"{f' {extra_args}' if extra_args else ''}"
        )
    return fields


def blocked_env_next_action_fields(
    report: dict[str, object], remediation_fields: Mapping[str, str]
) -> dict[str, object]:
    action_id = "set-release-smoke-preflight-env"
    command = remediation_fields.get("preflightEnvFileCommand", "").strip()
    if not command:
        command = remediation_fields.get("remediationCommand", "").strip()
    if not command:
        return {}
    action: dict[str, object] = {
        "id": action_id,
        "command": command,
        "label": "Set release smoke preflight environment before tagging",
    }
    for field in (
        "remediationCommand",
        "preflightEnvTemplate",
        "preflightEnvFileCommand",
        "releaseSmokeEnvFileCommand",
        "preflightEnvTemplateRefreshPath",
        "preflightEnvTemplateRefreshCommand",
    ):
        value = remediation_fields.get(field)
        if isinstance(value, str) and value.strip():
            action[field] = value.strip()
    missing_env = sorted(unique_preflight_values(report, "missing"))
    if missing_env:
        action["missingEnv"] = missing_env
    missing_env_any_of = sorted(unique_preflight_groups(report, "missing_any_of"))
    if missing_env_any_of:
        action["missingEnvAnyOf"] = missing_env_any_of
    recommended_env = sorted(unique_preflight_values(report, "recommended_env"))
    if recommended_env:
        action["recommendedEnv"] = recommended_env
    required_env_any_of = blocked_required_env_any_of(report)
    if required_env_any_of:
        action["requiredEnvAnyOf"] = required_env_any_of
    return {
        "nextActions": [action],
        "readyNextActionIds": [action_id],
        "nextActionStates": {action_id: "ready"},
    }


def blocked_required_env_any_of(report: dict[str, object]) -> list[list[str]]:
    groups: set[tuple[str, ...]] = set()
    for gate in preflight_blocked_gate_metadata(report):
        for group in cast(list[object], gate.get("missing_any_of", [])):
            values = tuple(string_list_value(group))
            if values:
                groups.add(values)
    for group in cast(list[object], report.get("required_env_any_of", [])):
        values = tuple(string_list_value(group))
        if values:
            groups.add(values)
    return [list(group) for group in sorted(groups)]


def report_summary_count(report: dict[str, object], field: str) -> int:
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return 0
    value = cast(dict[str, object], summary).get(field)
    return value if isinstance(value, int) else 0


def preflight_blocked_gate_metadata(report: dict[str, object]) -> list[dict[str, object]]:
    blocked: list[dict[str, object]] = []
    for step in preflight_steps(report):
        if step.get("status") != "blocked":
            continue
        gate: dict[str, object] = {"code": str(step.get("code", ""))}
        command = step.get("command")
        if isinstance(command, list):
            gate["command"] = [
                value for value in cast(list[object], command) if isinstance(value, str)
            ]
        for field in ("evidence_uri", "evidence_scope"):
            value = step.get(field)
            if isinstance(value, str) and value.strip():
                gate[field] = value.strip()
        gate["missing"] = sorted(string_list_value(step.get("missing")))
        gate["missing_any_of"] = [
            string_list_value(group)
            for group in cast(list[object], step.get("missing_any_of", []))
            if string_list_value(group)
        ]
        recommended_env = sorted(string_list_value(step.get("recommended_env")))
        if recommended_env:
            gate["recommended_env"] = recommended_env
        blocked.append(gate)
    return blocked


def release_evidence_readiness_report(
    evidence: dict[str, dict[str, str]],
    artifact: str,
    *,
    plan_file: str = "reports/release-smoke-plan.json",
    report_file: str = "reports/release-smoke-run.json",
) -> dict[str, Any]:
    artifact = artifact or "reports/release-evidence.json"
    ok = bool(evidence) and all(item.get("status") == "passed" for item in evidence.values())
    status = "passed" if ok else "failed" if evidence else "skipped"
    report: dict[str, Any] = {
        "ok": ok,
        "status": status,
        "scope": "release_evidence",
        "evidence": {
            "artifact": artifact,
            "owner": "reactor.release",
            "mode": "release_evidence",
            "releaseEvidence": release_evidence_summary(evidence),
        },
    }
    if not evidence:
        report["error"] = "release evidence missing"
        report["evidence"]["remediationCommand"] = (
            f"uv run reactor-release-smoke-run --plan {plan_file} "
            f"--report-file {report_file} --verified-at <ISO-8601> "
            f"--evidence-output {artifact}"
        )
        report["evidence"]["readinessReportArg"] = f"--readiness-report release_evidence={artifact}"
    elif not ok:
        report["error"] = release_evidence_failure(evidence)
    return report


def release_evidence_summary(evidence: dict[str, dict[str, str]]) -> dict[str, object]:
    gate_codes = sorted(evidence)
    scopes: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for item in evidence.values():
        scope = item.get("scope", "").strip()
        if scope:
            scopes[scope] = scopes.get(scope, 0) + 1
        status = item.get("status", "").strip()
        if status:
            status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "gateCount": len(gate_codes),
        "gateCodes": gate_codes,
        "scopes": dict(sorted(scopes.items())),
        "statusCounts": dict(sorted(status_counts.items())),
    }


def release_evidence_failure(evidence: dict[str, dict[str, str]]) -> str:
    for gate_code, item in evidence.items():
        if item.get("status") == "passed":
            continue
        failure = item.get("failure", "").strip()
        suffix = f": {failure}" if failure else ""
        return f"release evidence gate failed: {gate_code}{suffix}"
    return "release evidence gate failed"


def command_runner_with_environ(environ: Mapping[str, str]) -> CommandRunner:
    def runner(command: list[str], timeout_seconds: int) -> CommandResult:
        return run_command(command, timeout_seconds, environ=environ)

    return runner
