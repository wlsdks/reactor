from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO, cast

LOCAL_READY_STATUSES = {"ported", "verified"}
INCOMPLETE_STATUSES = {"not_started", "foundation", "in_progress"}

DEFERRED_GATE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("live provider/runtime smoke", "live_provider_runtime_smoke"),
    ("live peer-network interoperability smoke", "live_peer_network_interoperability_smoke"),
    ("live slack workspace smoke", "live_slack_workspace_smoke"),
    ("live provider smoke", "live_provider_smoke"),
    ("live backend/provider integration proof", "live_backend_provider_integration"),
)

RELEASE_EVIDENCE_REQUIREMENTS: dict[str, dict[str, str]] = {
    "full_backup_db_api_dress_rehearsal": {
        "description": "Full backup database and API migration dress rehearsal.",
        "evidence_uri": "reports/full-backup-db-api-dress-rehearsal.json",
        "scope": "dress_rehearsal",
        "suggested_command": (
            "uv run reactor-migration-dress-rehearsal --help "
            "# then run against the full backup source/target files and API smoke"
        ),
    },
    "full_backup_db_dress_rehearsal": {
        "description": "Full backup database migration dress rehearsal.",
        "evidence_uri": "reports/full-backup-db-dress-rehearsal.json",
        "scope": "dress_rehearsal",
        "suggested_command": (
            "uv run reactor-migration-dress-rehearsal --help "
            "# then run against the full backup source/target files"
        ),
    },
    "live_backend_provider_integration": {
        "description": "Live backend/provider observability integration proof.",
        "evidence_uri": "reports/live-backend-provider-integration.json",
        "scope": "live",
        "suggested_command": (
            "uv run reactor-live-backend-provider-smoke "
            "--output reports/live-backend-provider-integration.json"
        ),
    },
    "live_backend_provider_local_contract": {
        "description": "Local backend/provider observability contract.",
        "evidence_uri": "reports/live-backend-provider-integration.json",
        "scope": "live",
        "suggested_command": (
            "uv run pytest tests/unit/test_tracing.py tests/unit/test_provider_routing.py "
            "# plus reactor-live-backend-provider-smoke"
        ),
    },
    "live_peer_network_interoperability_smoke": {
        "description": "Live A2A peer-network interoperability smoke.",
        "evidence_uri": "reports/live-peer-network-interoperability-smoke.json",
        "scope": "live",
        "suggested_command": (
            "uv run reactor-live-a2a-peer-smoke "
            "--output reports/live-peer-network-interoperability-smoke.json"
        ),
    },
    "live_peer_network_local_contract": {
        "description": "Local A2A peer-network interoperability contract.",
        "evidence_uri": "reports/live-peer-network-interoperability-smoke.json",
        "scope": "live",
        "suggested_command": (
            "uv run pytest tests/unit/test_a2a_server.py tests/unit/test_a2a_tasks.py "
            "# plus reactor-live-a2a-peer-smoke"
        ),
    },
    "live_provider_runtime_smoke": {
        "description": "Live LangChain/LangGraph provider runtime smoke.",
        "evidence_uri": "reports/live-provider-runtime-smoke.json",
        "scope": "live",
        "suggested_command": (
            "uv run reactor-live-provider-smoke --output reports/live-provider-runtime-smoke.json"
        ),
    },
    "live_provider_runtime_local_contract": {
        "description": "Local LangChain/LangGraph provider runtime contract.",
        "evidence_uri": "reports/live-provider-runtime-smoke.json",
        "scope": "live",
        "suggested_command": (
            "uv run pytest tests/unit/test_langchain_agent.py tests/unit/test_run_service.py "
            "# plus reactor-live-provider-smoke"
        ),
    },
    "live_provider_smoke": {
        "description": "Live provider smoke for scheduled/background agent work.",
        "evidence_uri": "reports/live-provider-smoke.json",
        "scope": "live",
        "suggested_command": (
            "uv run reactor-live-provider-smoke --output reports/live-provider-smoke.json"
        ),
    },
    "live_provider_local_contract": {
        "description": "Local scheduled/background provider contract.",
        "evidence_uri": "reports/live-provider-smoke.json",
        "scope": "live",
        "suggested_command": (
            "uv run pytest tests/unit/test_scheduler_worker.py "
            "tests/unit/test_prompt_lab_service.py "
            "# plus reactor-live-provider-smoke"
        ),
    },
    "live_slack_workspace_smoke": {
        "description": "Live Slack workspace command/event smoke.",
        "evidence_uri": "reports/live-slack-workspace-smoke.json",
        "scope": "live",
        "suggested_command": (
            "uv run reactor-live-slack-smoke --output reports/live-slack-workspace-smoke.json"
        ),
    },
    "live_slack_workspace_local_contract": {
        "description": "Local Slack workspace gateway contract.",
        "evidence_uri": "reports/live-slack-workspace-smoke.json",
        "scope": "live",
        "suggested_command": (
            "uv run pytest tests/unit/test_slack_inbound.py tests/unit/test_slack_worker.py "
            "# plus reactor-live-slack-smoke"
        ),
    },
}

LOCAL_CONTRACT_REQUIREMENTS_BY_GATE: dict[str, tuple[str, ...]] = {
    "live_backend_provider_integration": ("live_backend_provider_local_contract",),
    "live_peer_network_interoperability_smoke": ("live_peer_network_local_contract",),
    "live_provider_runtime_smoke": ("live_provider_runtime_local_contract",),
    "live_provider_smoke": ("live_provider_local_contract",),
    "live_slack_workspace_smoke": ("live_slack_workspace_local_contract",),
}


def build_replatform_readiness_report(
    ledger_text: str,
    *,
    evidence: dict[str, Any] | None = None,
    current_git_commit: str | None = None,
) -> dict[str, Any]:
    rows = list(parse_ledger_feature_rows(ledger_text))
    status_counts = Counter(row["status"] for row in rows)
    blocking_areas = [
        {"area": row["area"], "status": row["status"]}
        for row in rows
        if row["status"] in INCOMPLETE_STATUSES
    ]
    deferred_gates: list[dict[str, str]] = []
    satisfied_release_gates: list[dict[str, str]] = []
    seen_release_gate_codes: set[str] = set()
    for row in rows:
        for gate in deferred_gates_for_area(
            area=row["area"],
            completion_gate=row["completion_gate"],
        ):
            if gate["code"] in seen_release_gate_codes:
                continue
            seen_release_gate_codes.add(gate["code"])
            release_evidence = release_evidence_for_gate(
                evidence or {},
                gate["code"],
                current_git_commit=current_git_commit,
            )
            if release_evidence is None:
                deferred_gates.append(
                    gate_with_evidence_status(
                        gate,
                        evidence or {},
                        current_git_commit=current_git_commit,
                    )
                )
                continue
            satisfied_release_gates.append(
                {
                    "area": gate["area"],
                    "code": gate["code"],
                    "scope": release_evidence["scope"],
                    "evidence_uri": release_evidence["evidence_uri"],
                    "verified_at": release_evidence["verified_at"],
                    **git_commit_field(release_evidence),
                }
            )
    local_automation_ready = not blocking_areas and all(
        row["status"] in LOCAL_READY_STATUSES for row in rows
    )
    return {
        "local_automation_ready": local_automation_ready,
        "release_ready": local_automation_ready and not deferred_gates,
        "status_counts": dict(sorted(status_counts.items())),
        "blocking_areas": blocking_areas,
        "verification_backlog": verification_backlog(rows),
        "deferred_gates": deferred_gates,
        "release_evidence_requirements": release_evidence_requirements(deferred_gates),
        "satisfied_release_gates": satisfied_release_gates,
    }


def parse_ledger_feature_rows(ledger_text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in ledger_text.splitlines():
        if not line.startswith("| "):
            continue
        if line.startswith("| Area") or line.startswith("| ---"):
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) < 4:
            continue
        status = parts[2]
        if status not in LOCAL_READY_STATUSES | INCOMPLETE_STATUSES:
            continue
        rows.append(
            {
                "area": parts[0],
                "status": status,
                "completion_gate": parts[3],
            }
        )
    return rows


def verification_backlog(rows: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "area": row["area"],
            "status": row["status"],
            "completion_gate": row["completion_gate"],
        }
        for row in rows
        if row["status"] == "ported"
    ]


def deferred_gates_for_area(*, area: str, completion_gate: str) -> list[dict[str, str]]:
    normalized = completion_gate.lower()
    gates: list[dict[str, str]] = []
    seen_codes: set[str] = set()
    for pattern, code in DEFERRED_GATE_PATTERNS:
        if pattern not in normalized or code in seen_codes:
            continue
        seen_codes.add(code)
        gates.append(
            {
                "area": area,
                "code": code,
                "description": sentence_containing(completion_gate, pattern),
            }
        )
    return gates


def gate_with_evidence_status(
    gate: dict[str, str],
    evidence: dict[str, Any],
    *,
    current_git_commit: str | None = None,
) -> dict[str, str]:
    raw = evidence.get(gate["code"])
    if not isinstance(raw, dict):
        return gate
    typed_raw = cast(dict[str, object], raw)
    status = typed_raw.get("status")
    if not isinstance(status, str) or not status.strip():
        return gate
    evidence_gate = {**gate, "evidence_status": status}
    scope = typed_raw.get("scope")
    if isinstance(scope, str) and scope.strip():
        evidence_gate["evidence_scope"] = scope
    git_commit = typed_raw.get("git_commit")
    if isinstance(git_commit, str) and git_commit.strip():
        evidence_gate["evidence_git_commit"] = git_commit.strip()
    clean_current_git_commit = current_git_commit.strip() if current_git_commit else ""
    if clean_current_git_commit and status == "passed":
        if not isinstance(git_commit, str) or not git_commit.strip():
            evidence_gate["evidence_revision_status"] = "missing"
        elif git_commit.strip() != clean_current_git_commit:
            evidence_gate["evidence_revision_status"] = "stale"
    return evidence_gate


def release_evidence_for_gate(
    evidence: dict[str, Any],
    gate_code: str,
    *,
    current_git_commit: str | None = None,
) -> dict[str, str] | None:
    raw = evidence.get(gate_code)
    if not isinstance(raw, dict):
        return None
    typed_raw = cast(dict[str, object], raw)
    status = typed_raw.get("status")
    scope = typed_raw.get("scope")
    evidence_uri = typed_raw.get("evidence_uri")
    verified_at = typed_raw.get("verified_at")
    git_commit = typed_raw.get("git_commit")
    if status != "passed":
        return None
    required_scope = RELEASE_EVIDENCE_REQUIREMENTS.get(gate_code, {}).get("scope")
    if not isinstance(scope, str) or scope != required_scope:
        return None
    if not isinstance(evidence_uri, str) or not evidence_uri.strip():
        return None
    if not isinstance(verified_at, str) or not verified_at.strip():
        return None
    clean_current_git_commit = current_git_commit.strip() if current_git_commit else ""
    if clean_current_git_commit:
        if not isinstance(git_commit, str) or not git_commit.strip():
            return None
        if git_commit.strip() != clean_current_git_commit:
            return None
    result = {
        "scope": scope,
        "evidence_uri": evidence_uri,
        "verified_at": verified_at,
    }
    if isinstance(git_commit, str) and git_commit.strip():
        result["git_commit"] = git_commit.strip()
    return result


def git_commit_field(release_evidence: dict[str, str]) -> dict[str, str]:
    git_commit = release_evidence.get("git_commit")
    return {"git_commit": git_commit} if git_commit else {}


def release_evidence_requirements(gates: Sequence[dict[str, str]]) -> list[dict[str, object]]:
    requirements: list[dict[str, object]] = []
    gates_by_code = {gate["code"]: gate for gate in gates}
    for code in sorted(gates_by_code):
        requirements.extend(release_evidence_requirements_for_gate(gates_by_code[code]))
    return requirements


def release_evidence_requirements_for_gate(gate: dict[str, str]) -> list[dict[str, object]]:
    codes = [gate["code"], *LOCAL_CONTRACT_REQUIREMENTS_BY_GATE.get(gate["code"], ())]
    requirements: list[dict[str, object]] = []
    for code in codes:
        requirement = RELEASE_EVIDENCE_REQUIREMENTS.get(code)
        if requirement is None:
            continue
        item: dict[str, object] = {
            "code": code,
            "description": requirement["description"],
            "evidence_schema": {
                "status": "passed",
                "scope": requirement["scope"],
                "evidence_uri": requirement["evidence_uri"],
                "verified_at": "ISO-8601 timestamp",
            },
            "suggested_command": requirement["suggested_command"],
        }
        item.update(release_evidence_status_fields(gate))
        requirements.append(item)
    return requirements


def release_evidence_status_fields(gate: dict[str, str]) -> dict[str, str]:
    field_map = {
        "evidence_status": "evidence_status",
        "evidence_scope": "evidence_scope",
        "evidence_git_commit": "evidence_git_commit",
        "evidence_revision_status": "evidence_revision_status",
    }
    return {
        output_key: value
        for source_key, output_key in field_map.items()
        if (value := gate.get(source_key))
    }


def sentence_containing(text: str, pattern: str) -> str:
    lower_pattern = pattern.lower()
    for sentence in split_sentences(text):
        if lower_pattern in sentence.lower():
            return sentence
    return text.strip()


def split_sentences(text: str) -> list[str]:
    return [part.strip(" .;") for part in text.replace("; ", ". ").split(". ") if part.strip(" .;")]


def write_report(report: dict[str, Any], output: TextIO) -> None:
    output.write(json.dumps(report, sort_keys=True, separators=(",", ":")))
    output.write("\n")


def replatform_readiness_failure_summary(report: dict[str, Any]) -> str:
    lines = [
        "replatform_readiness "
        f"release_ready={str(bool(report.get('release_ready'))).lower()} "
        f"local_automation_ready={str(bool(report.get('local_automation_ready'))).lower()}"
    ]
    blocking_areas = report.get("blocking_areas")
    if isinstance(blocking_areas, Sequence) and not isinstance(
        blocking_areas, str | bytes | bytearray
    ):
        for area in cast(Sequence[object], blocking_areas):
            if not isinstance(area, dict):
                continue
            area_mapping = cast(dict[str, object], area)
            lines.append(
                "- blockingArea="
                f"{area_mapping.get('area') or 'unknown'} "
                f"status={area_mapping.get('status') or 'unknown'}"
            )
    deferred_gates = report.get("deferred_gates")
    if isinstance(deferred_gates, Sequence) and not isinstance(
        deferred_gates, str | bytes | bytearray
    ):
        for gate in cast(Sequence[object], deferred_gates):
            if not isinstance(gate, dict):
                continue
            gate_mapping = cast(dict[str, object], gate)
            code = gate_mapping.get("code")
            requirement = RELEASE_EVIDENCE_REQUIREMENTS.get(code) if isinstance(code, str) else None
            suggested_command = requirement.get("suggested_command") if requirement else None
            suffix = (
                f" suggestedCommand={summary_quoted_value(suggested_command)}"
                if isinstance(suggested_command, str) and suggested_command.strip()
                else ""
            )
            evidence_status = gate_mapping.get("evidence_status")
            if isinstance(evidence_status, str) and evidence_status.strip():
                suffix = f"{suffix} evidenceStatus={evidence_status.strip()}"
            evidence_revision_status = gate_mapping.get("evidence_revision_status")
            if isinstance(evidence_revision_status, str) and evidence_revision_status.strip():
                suffix = f"{suffix} evidenceRevision={evidence_revision_status.strip()}"
            lines.append(
                f"- deferredGate={code or 'unknown'} "
                f"area={summary_quoted_value(str(gate_mapping.get('area') or 'unknown'))}"
                f"{suffix}"
            )
    return "\n".join(lines)


def summary_quoted_value(value: str) -> str:
    if "'" in value:
        return json.dumps(value)
    return f"'{value}'"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report Reactor Python/LangGraph replatform release readiness."
    )
    parser.add_argument(
        "--ledger",
        default="docs/migration/full-replatform-parity-ledger.md",
        help="Path to the replatform parity ledger",
    )
    parser.add_argument("--output", required=True, help="Path to write JSON readiness report")
    parser.add_argument(
        "--evidence",
        default=None,
        help="Optional JSON file with release evidence keyed by deferred gate code",
    )
    parser.add_argument(
        "--allow-deferred-release-gates",
        action="store_true",
        help="Exit 0 when local automation is ready even if live release gates remain deferred",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    ledger_text = Path(str(args.ledger)).read_text(encoding="utf-8")
    evidence = read_release_evidence(str(args.evidence) if args.evidence is not None else None)
    report = build_replatform_readiness_report(
        ledger_text,
        evidence=evidence,
        current_git_commit=current_git_commit(),
    )
    output_path = Path(str(args.output))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output:
        write_report(report, output)
    if report["release_ready"]:
        return 0
    if args.allow_deferred_release_gates and report["local_automation_ready"]:
        return 0
    print(replatform_readiness_failure_summary(report), file=sys.stderr)
    return 1


def read_release_evidence(path: str | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("release evidence file must contain a JSON object")
    return cast(dict[str, Any], payload)


def current_git_commit() -> str:
    git = shutil.which("git")
    if git is None:
        return ""
    try:
        result = subprocess.run(  # noqa: S603
            [git, "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip()
