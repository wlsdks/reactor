from __future__ import annotations

import json
from pathlib import Path

from pytest import CaptureFixture, MonkeyPatch

from reactor.release.readiness import build_replatform_readiness_report, main

LEDGER = "\n".join(
    [
        "| Area | Backup Scope | Current Python Status | Required Completion Gate |",
        "| --- | --- | --- | --- |",
        (
            "| Agent graph/runtime | runtime | ported | "
            "live provider/runtime smoke deferred to release-readiness verification |"
        ),
        "| RAG | rag | verified | full static/test gate |",
        (
            "| Slack/integrations | slack | ported | "
            "live Slack workspace smoke proof deferred to release-readiness verification |"
        ),
        (
            "| Data migration/cutover | optional legacy data tools only | verified | "
            "optional migration tooling retained; Python 2.0 starts with fresh data |"
        ),
    ]
)


def test_replatform_readiness_report_separates_local_and_release_gates() -> None:
    report = build_replatform_readiness_report(LEDGER)

    assert report["local_automation_ready"] is True
    assert report["release_ready"] is False
    assert report["status_counts"] == {"ported": 2, "verified": 2}
    assert report["deferred_gates"] == [
        {
            "area": "Agent graph/runtime",
            "code": "live_provider_runtime_smoke",
            "description": "live provider/runtime smoke deferred to release-readiness verification",
        },
        {
            "area": "Slack/integrations",
            "code": "live_slack_workspace_smoke",
            "description": (
                "live Slack workspace smoke proof deferred to release-readiness verification"
            ),
        },
    ]
    assert report["release_evidence_requirements"] == [
        {
            "code": "live_provider_runtime_smoke",
            "description": "Live LangChain/LangGraph provider runtime smoke.",
            "evidence_schema": {
                "status": "passed",
                "scope": "live",
                "evidence_uri": "reports/live-provider-runtime-smoke.json",
                "verified_at": "ISO-8601 timestamp",
            },
            "suggested_command": (
                "uv run reactor-live-provider-smoke "
                "--output reports/live-provider-runtime-smoke.json"
            ),
        },
        {
            "code": "live_provider_runtime_local_contract",
            "description": "Local LangChain/LangGraph provider runtime contract.",
            "evidence_schema": {
                "status": "passed",
                "scope": "live",
                "evidence_uri": "reports/live-provider-runtime-smoke.json",
                "verified_at": "ISO-8601 timestamp",
            },
            "suggested_command": (
                "uv run pytest tests/unit/test_langchain_agent.py tests/unit/test_run_service.py "
                "# plus reactor-live-provider-smoke"
            ),
        },
        {
            "code": "live_slack_workspace_smoke",
            "description": "Live Slack workspace command/event smoke.",
            "evidence_schema": {
                "status": "passed",
                "scope": "live",
                "evidence_uri": "reports/live-slack-workspace-smoke.json",
                "verified_at": "ISO-8601 timestamp",
            },
            "suggested_command": (
                "uv run reactor-live-slack-smoke --output reports/live-slack-workspace-smoke.json"
            ),
        },
        {
            "code": "live_slack_workspace_local_contract",
            "description": "Local Slack workspace gateway contract.",
            "evidence_schema": {
                "status": "passed",
                "scope": "live",
                "evidence_uri": "reports/live-slack-workspace-smoke.json",
                "verified_at": "ISO-8601 timestamp",
            },
            "suggested_command": (
                "uv run pytest tests/unit/test_slack_inbound.py tests/unit/test_slack_worker.py "
                "# plus reactor-live-slack-smoke"
            ),
        },
    ]


def test_replatform_readiness_report_adds_local_contract_requirements_for_live_gates() -> None:
    ledger = "\n".join(
        [
            "| Area | Backup Scope | Current Python Status | Required Completion Gate |",
            "| --- | --- | --- | --- |",
            (
                "| Agent graph/runtime | runtime | verified | "
                "live provider/runtime smoke deferred to release-readiness verification |"
            ),
            (
                "| A2A/multi-agent | a2a | verified | "
                "live peer-network interoperability smoke is deferred "
                "to release-readiness verification |"
            ),
            (
                "| Slack/integrations | slack | verified | "
                "live Slack workspace smoke proof deferred to release-readiness verification |"
            ),
            (
                "| Scheduler/background jobs | jobs | verified | "
                "live provider smoke proof deferred to release-readiness verification |"
            ),
            (
                "| Observability/cost/SLO | observability | verified | "
                "live backend/provider integration proof deferred "
                "to release-readiness verification |"
            ),
        ]
    )

    report = build_replatform_readiness_report(ledger)

    assert [requirement["code"] for requirement in report["release_evidence_requirements"]] == [
        "live_backend_provider_integration",
        "live_backend_provider_local_contract",
        "live_peer_network_interoperability_smoke",
        "live_peer_network_local_contract",
        "live_provider_runtime_smoke",
        "live_provider_runtime_local_contract",
        "live_provider_smoke",
        "live_provider_local_contract",
        "live_slack_workspace_smoke",
        "live_slack_workspace_local_contract",
    ]


def test_replatform_readiness_report_lists_ported_verification_backlog() -> None:
    report = build_replatform_readiness_report(LEDGER)

    assert report["verification_backlog"] == [
        {
            "area": "Agent graph/runtime",
            "status": "ported",
            "completion_gate": (
                "live provider/runtime smoke deferred to release-readiness verification"
            ),
        },
        {
            "area": "Slack/integrations",
            "status": "ported",
            "completion_gate": (
                "live Slack workspace smoke proof deferred to release-readiness verification"
            ),
        },
    ]


def test_replatform_readiness_report_accepts_release_evidence() -> None:
    report = build_replatform_readiness_report(
        LEDGER,
        evidence={
            "live_provider_runtime_smoke": {
                "status": "passed",
                "scope": "live",
                "evidence_uri": "reports/provider-runtime-smoke.json",
                "verified_at": "2026-06-28T00:00:00Z",
            },
            "live_slack_workspace_smoke": {
                "status": "passed",
                "scope": "live",
                "evidence_uri": "reports/slack-workspace-smoke.json",
                "verified_at": "2026-06-28T00:00:00Z",
            },
        },
    )

    assert report["release_ready"] is True
    assert report["deferred_gates"] == []
    assert report["satisfied_release_gates"] == [
        {
            "area": "Agent graph/runtime",
            "code": "live_provider_runtime_smoke",
            "scope": "live",
            "evidence_uri": "reports/provider-runtime-smoke.json",
            "verified_at": "2026-06-28T00:00:00Z",
        },
        {
            "area": "Slack/integrations",
            "code": "live_slack_workspace_smoke",
            "scope": "live",
            "evidence_uri": "reports/slack-workspace-smoke.json",
            "verified_at": "2026-06-28T00:00:00Z",
        },
    ]


def test_replatform_readiness_report_rejects_incomplete_release_evidence() -> None:
    report = build_replatform_readiness_report(
        LEDGER,
        evidence={
            "live_provider_runtime_smoke": {
                "status": "failed",
                "scope": "live",
                "evidence_uri": "reports/provider-runtime-smoke.json",
                "verified_at": "2026-06-28T00:00:00Z",
            },
        },
    )

    assert report["release_ready"] is False
    assert report["deferred_gates"][0]["code"] == "live_provider_runtime_smoke"
    assert report["deferred_gates"][0]["evidence_status"] == "failed"


def test_replatform_readiness_rejects_release_evidence_without_current_git_commit() -> None:
    report = build_replatform_readiness_report(
        LEDGER,
        evidence={
            "live_provider_runtime_smoke": {
                "status": "passed",
                "scope": "live",
                "evidence_uri": "reports/provider-runtime-smoke.json",
                "verified_at": "2026-06-28T00:00:00Z",
            },
            "live_slack_workspace_smoke": {
                "status": "passed",
                "scope": "live",
                "evidence_uri": "reports/slack-workspace-smoke.json",
                "verified_at": "2026-06-28T00:00:00Z",
                "git_commit": "abc123",
            },
        },
        current_git_commit="abc123",
    )

    assert report["release_ready"] is False
    assert report["deferred_gates"][0] == {
        "area": "Agent graph/runtime",
        "code": "live_provider_runtime_smoke",
        "description": "live provider/runtime smoke deferred to release-readiness verification",
        "evidence_status": "passed",
        "evidence_scope": "live",
        "evidence_revision_status": "missing",
    }


def test_replatform_readiness_rejects_release_evidence_from_other_git_commit() -> None:
    report = build_replatform_readiness_report(
        LEDGER,
        evidence={
            "live_provider_runtime_smoke": {
                "status": "passed",
                "scope": "live",
                "evidence_uri": "reports/provider-runtime-smoke.json",
                "verified_at": "2026-06-28T00:00:00Z",
                "git_commit": "old123",
            },
            "live_slack_workspace_smoke": {
                "status": "passed",
                "scope": "live",
                "evidence_uri": "reports/slack-workspace-smoke.json",
                "verified_at": "2026-06-28T00:00:00Z",
                "git_commit": "new456",
            },
        },
        current_git_commit="new456",
    )

    assert report["release_ready"] is False
    assert report["deferred_gates"][0] == {
        "area": "Agent graph/runtime",
        "code": "live_provider_runtime_smoke",
        "description": "live provider/runtime smoke deferred to release-readiness verification",
        "evidence_status": "passed",
        "evidence_scope": "live",
        "evidence_git_commit": "old123",
        "evidence_revision_status": "stale",
    }


def test_replatform_readiness_report_rejects_wrong_evidence_scope() -> None:
    report = build_replatform_readiness_report(
        LEDGER,
        evidence={
            "live_provider_runtime_smoke": {
                "status": "passed",
                "scope": "local",
                "evidence_uri": "reports/provider-runtime-smoke.json",
                "verified_at": "2026-06-28T00:00:00Z",
            },
            "live_slack_workspace_smoke": {
                "status": "passed",
                "scope": "live",
                "evidence_uri": "reports/slack-workspace-smoke.json",
                "verified_at": "2026-06-28T00:00:00Z",
            },
        },
    )

    assert report["release_ready"] is False
    assert report["deferred_gates"] == [
        {
            "area": "Agent graph/runtime",
            "code": "live_provider_runtime_smoke",
            "description": "live provider/runtime smoke deferred to release-readiness verification",
            "evidence_status": "passed",
            "evidence_scope": "local",
        }
    ]


def test_replatform_readiness_report_deduplicates_repeated_release_gate_codes() -> None:
    duplicate_ledger = "\n".join(
        [
            "| Area | Backup Scope | Current Python Status | Required Completion Gate |",
            "| --- | --- | --- | --- |",
            (
                "| Agent graph/runtime | runtime | ported | "
                "live provider/runtime smoke deferred to release-readiness verification |"
            ),
            (
                "| Guards/hooks/output filters | guards | ported | "
                "live provider/runtime smoke deferred to release-readiness verification |"
            ),
            (
                "| Eval/quality/hardening | eval | ported | "
                "live provider proof deferred to release-readiness verification |"
            ),
            (
                "| Data migration/cutover | optional legacy data tools only | verified | "
                "optional migration tooling retained; Python 2.0 starts with fresh data |"
            ),
        ]
    )

    report = build_replatform_readiness_report(duplicate_ledger)

    assert [gate["code"] for gate in report["deferred_gates"]] == [
        "live_provider_runtime_smoke",
    ]
    assert [requirement["code"] for requirement in report["release_evidence_requirements"]] == [
        "live_provider_runtime_smoke",
        "live_provider_runtime_local_contract",
    ]


def test_replatform_readiness_report_fails_local_gate_when_area_is_unported() -> None:
    report = build_replatform_readiness_report(
        LEDGER.replace("| RAG | rag | verified |", "| RAG | rag | in_progress |")
    )

    assert report["local_automation_ready"] is False
    assert report["release_ready"] is False
    assert report["blocking_areas"] == [{"area": "RAG", "status": "in_progress"}]


def test_replatform_readiness_cli_writes_json_report(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.md"
    output_path = tmp_path / "reports" / "release" / "readiness.json"
    ledger_path.write_text(LEDGER, encoding="utf-8")

    exit_code = main(["--ledger", str(ledger_path), "--output", str(output_path)])

    assert exit_code == 1
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["local_automation_ready"] is True
    assert report["release_ready"] is False


def test_replatform_readiness_cli_summarizes_deferred_gates_on_stderr(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    ledger_path = tmp_path / "ledger.md"
    output_path = tmp_path / "readiness.json"
    ledger_path.write_text(LEDGER, encoding="utf-8")

    exit_code = main(["--ledger", str(ledger_path), "--output", str(output_path)])

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "replatform_readiness release_ready=false local_automation_ready=true" in stderr
    assert "deferredGate=live_provider_runtime_smoke" in stderr
    assert "area='Agent graph/runtime'" in stderr
    assert (
        "suggestedCommand='uv run reactor-live-provider-smoke "
        "--output reports/live-provider-runtime-smoke.json'"
    ) in stderr


def test_replatform_readiness_cli_can_accept_deferred_release_gates(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.md"
    output_path = tmp_path / "readiness.json"
    ledger_path.write_text(LEDGER, encoding="utf-8")

    exit_code = main(
        [
            "--ledger",
            str(ledger_path),
            "--output",
            str(output_path),
            "--allow-deferred-release-gates",
        ]
    )

    assert exit_code == 0


def test_replatform_readiness_cli_uses_release_evidence(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    ledger_path = tmp_path / "ledger.md"
    evidence_path = tmp_path / "evidence.json"
    output_path = tmp_path / "readiness.json"
    ledger_path.write_text(LEDGER, encoding="utf-8")
    monkeypatch.setattr("reactor.release.readiness.current_git_commit", lambda: "abc123")
    evidence_path.write_text(
        json.dumps(
            {
                "live_provider_runtime_smoke": {
                    "status": "passed",
                    "scope": "live",
                    "evidence_uri": "reports/provider-runtime-smoke.json",
                    "verified_at": "2026-06-28T00:00:00Z",
                    "git_commit": "abc123",
                },
                "live_slack_workspace_smoke": {
                    "status": "passed",
                    "scope": "live",
                    "evidence_uri": "reports/slack-workspace-smoke.json",
                    "verified_at": "2026-06-28T00:00:00Z",
                    "git_commit": "abc123",
                },
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--ledger",
            str(ledger_path),
            "--evidence",
            str(evidence_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["release_ready"] is True
