from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

from reactor.evals.scenario_matrix import (
    ScenarioMatrixReport,
    build_cases,
    evaluate_expectations,
    evaluate_quality_gates,
    load_scenario_document,
)

FIXTURE = Path("tests/fixtures/scenarios/minimal-matrix.json")


def test_build_cases_expands_matrix_and_renders_brace_styles() -> None:
    document = load_scenario_document(FIXTURE)

    cases = build_cases(
        document,
        runtime_vars={"run_id": "run-123"},
        include_tags=set(),
        exclude_tags=set(),
    )

    assert [case.id for case in cases] == [
        "matrix-tool-routing[tool_name=issue_search,channel=web]",
        "matrix-tool-routing[tool_name=issue_search,channel=chat]",
        "matrix-tool-routing[tool_name=knowledge_search,channel=web]",
        "matrix-tool-routing[tool_name=knowledge_search,channel=chat]",
    ]
    first_json = cast(dict[str, object], cases[0].request_json)
    second_json = cast(dict[str, object], cases[1].request_json)
    second_metadata = cast(dict[str, object], second_json["metadata"])
    assert first_json["message"] == "Use issue_search through web for run-123"
    assert second_metadata["sessionId"] == "run-123-issue_search-chat"
    assert cases[0].expect["toolsUsedAll"] == ["issue_search"]


def test_evaluate_expectations_ports_legacy_tools_content_and_json_checks() -> None:
    failures = evaluate_expectations(
        {
            "status": 200,
            "success": True,
            "toolsUsedAll": ["issue_search"],
            "toolsUsedNone": ["issue_create"],
            "toolsUsedMaxCount": 1,
            "contentContainsAny": ["Issue"],
            "contentNotRegex": ["(?i)secret"],
            "jsonExists": ["tokenUsage.inputTokens"],
            "jsonRegex": {"content": "Issue"},
        },
        status=200,
        body_text=json.dumps(
            {
                "success": True,
                "content": "Issue summary",
                "toolsUsed": ["issue_search"],
                "tokenUsage": {"inputTokens": 11},
            }
        ),
        body_json={
            "success": True,
            "content": "Issue summary",
            "toolsUsed": ["issue_search"],
            "tokenUsage": {"inputTokens": 11},
        },
    )

    assert failures == []


def test_quality_gates_fail_on_rate_and_tool_budget() -> None:
    report = ScenarioMatrixReport.from_results(
        scenario_file="fixture.json",
        base_url="http://testserver",
        tenant_id="default",
        run_id="run-123",
        strict=True,
        results=[
            {
                "id": "case-a",
                "status": "passed",
                "durationMs": 200,
                "observations": {"toolsUsedCount": 3},
            },
            {
                "id": "case-b",
                "status": "failed",
                "durationMs": 600,
                "observations": {"toolsUsedCount": 1},
            },
        ],
        rate_limited=0,
    )

    failures = evaluate_quality_gates(
        report,
        {"minPassRate": 1.0, "maxFailed": 0, "maxToolsUsedPerCase": 2},
    )

    assert failures == [
        "quality gate failed: minPassRate expected=1.0 actual=passRate=0.500",
        "quality gate failed: maxFailed expected=0 actual=failed=1",
        "quality gate failed: maxToolsUsedPerCase expected=2 actual=maxTools=3",
    ]


def test_cli_validate_only_writes_report_without_server(tmp_path: Path) -> None:
    report_file = tmp_path / "reactor-scenario-matrix-test-report.json"

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/dev/validate-scenario-matrix.py",
            "--scenario-file",
            str(FIXTURE),
            "--validate-only",
            "--report-file",
            str(report_file),
            "--seed",
            "7",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(report_file.read_text())
    assert payload["summary"]["total"] == 4
    assert payload["summary"]["skipped"] == 4
    assert payload["qualityGateFailures"] == []
