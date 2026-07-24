from __future__ import annotations

import json
from collections.abc import Sequence
from io import StringIO
from pathlib import Path
from typing import cast

from reactor.cli.runs import (
    RunCliHttpResult,
    completed_run_next_actions,
    diagnose_next_action_rows,
    diagnose_next_action_summary,
    format_eval_case_table,
    format_fork_table,
    format_run_result_table,
    langsmith_feedback_review_action,
    langsmith_next_action_rows,
    promoted_eval_run_fixture,
    run_cli,
    running_run_next_actions,
)
from reactor.memory.lifecycle_actions import MEMORY_LIFECYCLE_GATE_ACTION
from reactor.release.readiness_actions import release_readiness_command_for_reports


def run_1_operator_next_actions() -> list[dict[str, str]]:
    return [
        {
            "id": "diagnose-run",
            "command": "reactor-runs diagnose run_1 --output table",
        },
        {
            "id": "inspect-state-history",
            "command": "reactor-admin state-history run_1 --output table",
        },
        {
            "id": "replay-stream",
            "command": "reactor-runs replay run_1 --output table",
        },
    ]


def test_run_result_table_shows_next_action_source_run_ids() -> None:
    output = format_run_result_table(
        {
            "runId": "run_1",
            "status": "completed",
            "nextActions": [
                {
                    "id": "fork-checkpoint",
                    "command": "reactor-runs fork run_1 --output table",
                    "sourceRunId": "run_1",
                    "checkpointNs": "reactor",
                    "checkpointId": "checkpoint_1",
                }
            ],
        }
    )

    assert "forkAction.sourceRunId" in output
    assert "run_1\n" in output


class FakeRunsProbe:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
        self.calls.append({"method": "GET", "path": path, "headers": headers})
        if path == "/v1/runs/run_1":
            return RunCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "run_id": "run_1",
                    "status": "completed",
                    "response_text": "answer",
                },
            )
        if path == "/v1/runs/run_1/stream-events":
            return RunCliHttpResult(
                ok=True,
                status_code=200,
                body=[{"sequence": 1, "event_type": "message", "payload": {"text": "answer"}}],
            )
        if path == "/v1/runs/run_1/tool-invocations?limit=100":
            return RunCliHttpResult(
                ok=True,
                status_code=200,
                body=[
                    {
                        "id": "tool_ok",
                        "runId": "run_1",
                        "toolId": "Rag:hybrid_search",
                        "status": "succeeded",
                        "success": True,
                    }
                ],
            )
        if path == "/v1/runs/run_1/tool-invocations?limit=25&status=failed":
            return RunCliHttpResult(
                ok=True,
                status_code=200,
                body=[
                    {
                        "id": "tool_1",
                        "runId": "run_1",
                        "toolId": "Webhook:send",
                        "status": "failed",
                        "success": False,
                        "input": {"url": "https://example.com"},
                        "output": None,
                        "error": {"message": "approval required"},
                    }
                ],
            )
        if path == "/v1/runs/run_failed":
            return RunCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "run_id": "run_failed",
                    "status": "failed",
                    "input_text": "Investigate provider outage",
                    "response_text": "Provider failed safely.",
                    "metadata": {
                        "agentType": "standard",
                        "model": "test-model",
                        "toolNames": ["Provider:call"],
                        "exposedToolNames": ["Provider:call"],
                        "errors": ["provider_timeout"],
                    },
                },
            )
        if path == "/v1/runs/run_failed/tool-invocations?limit=100":
            return RunCliHttpResult(
                ok=True,
                status_code=200,
                body=[
                    {
                        "id": "tool_failed",
                        "runId": "run_failed",
                        "toolId": "Provider:call",
                        "status": "failed",
                        "success": False,
                        "error": {"message": "provider_timeout"},
                    }
                ],
            )
        return RunCliHttpResult(ok=False, status_code=404, error="not found")

    def post_json(
        self,
        path: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> RunCliHttpResult:
        self.calls.append(
            {
                "method": "POST",
                "path": path,
                "headers": headers,
                "payload": payload,
            }
        )
        if path == "/v1/runs/preflight":
            return RunCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "status": "ready",
                    "runtime": "langchain_agent",
                    "threadId": "thread_1",
                    "checkpointNs": "reactor",
                    "model": {"provider": "openai", "name": "gpt-5-mini"},
                    "middlewareChain": {
                        "count": 2,
                        "middleware": ["ModelCallLimitMiddleware", "PIIMiddleware"],
                    },
                    "toolProfileBudget": {
                        "activeToolCount": 2,
                        "configuredToolCount": 4,
                    },
                    "structuredOutput": {
                        "strategy": "json_object_schema",
                        "status": "applied",
                    },
                },
            )
        if path == "/v1/runs/run_1/cancel":
            return RunCliHttpResult(
                ok=True,
                status_code=200,
                body={"run_id": "run_1", "status": "cancelled", "response": "Run cancelled."},
            )
        if path == "/v1/runs/run_1/resume":
            return RunCliHttpResult(
                ok=True,
                status_code=200,
                body={"run_id": "run_1", "status": "completed", "response": "resumed answer"},
            )
        if path == "/v1/runs/run_1/fork":
            return RunCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "run_id": "run_fork",
                    "source_run_id": "run_1",
                    "thread_id": "thread_fork",
                    "checkpoint_ns": "fork_ns",
                    "status": "completed",
                    "response": "forked answer",
                    "provenance": {"source": "checkpoint_fork"},
                },
            )
        if path == "/v1/admin/agent-eval/cases/promote":
            tags = ["regression", "promoted-from-failed-run"]
            payload_tags = payload.get("tags")
            if isinstance(payload_tags, list):
                tags.extend(str(tag) for tag in cast(Sequence[object], payload_tags))
            case_id = str(payload.get("id") or "case_failed_provider")
            expected_answer = payload.get("expectedAnswerContains")
            expected_answers = (
                [str(item) for item in cast(Sequence[object], expected_answer)]
                if isinstance(expected_answer, list)
                else ["provider outage"]
            )
            return RunCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "id": case_id,
                    "name": "Provider timeout regression",
                    "userInput": "Investigate provider outage",
                    "expectedAnswerContains": expected_answers,
                    "forbiddenAnswerContains": [],
                    "expectedToolNames": [],
                    "forbiddenToolNames": [],
                    "expectedExposedToolNames": [],
                    "forbiddenExposedToolNames": [],
                    "maxToolExposureCount": None,
                    "agentType": "standard",
                    "model": "test-model",
                    "enabled": True,
                    "tags": tags,
                    "minScore": 1.0,
                    "sourceRunId": "run_failed",
                    "assertionCount": 2,
                    "createdAt": "2026-07-01T00:00:00Z",
                    "updatedAt": "2026-07-01T00:00:00Z",
                },
            )
        return RunCliHttpResult(
            ok=True,
            status_code=200,
            body={
                "run_id": "run_1",
                "status": "completed",
                "response": "answer",
                "nextActions": run_1_operator_next_actions(),
            },
        )


def test_runs_cli_diagnose_next_actions_render_executable_timestamps() -> None:
    actions = [
        {
            "id": "refresh-readiness",
            "command": (
                "uv run reactor-release-smoke-run --verified-at VERIFY_TIMESTAMP --output table"
            ),
        }
    ]

    assert diagnose_next_action_summary(actions) == (
        "uv run reactor-release-smoke-run --verified-at "
        "$(date -u +%Y-%m-%dT%H:%M:%SZ) --output table"
    )
    assert diagnose_next_action_rows(actions) == [
        (
            "nextAction.refresh-readiness",
            "true",
            "-",
            (
                "uv run reactor-release-smoke-run --verified-at "
                "$(date -u +%Y-%m-%dT%H:%M:%SZ) --output table"
            ),
        )
    ]


def test_runs_cli_next_actions_quote_shell_arguments() -> None:
    completed_actions = completed_run_next_actions(
        "run needs quoting",
        {
            "status": "completed",
            "checkpointNs": "tenant checkpoint",
            "lastCheckpointId": "checkpoint needs quoting",
        },
        [{"sequence": 1, "event_type": "run.stream.token"}],
    )
    running_actions = running_run_next_actions(
        "run needs quoting",
        {"status": "running"},
        [
            {
                "event_type": "run.stream.approval",
                "payload": {
                    "approval_status": "pending",
                    "approval_id": "approval needs quoting",
                },
            }
        ],
    )

    assert completed_actions[0]["command"] == (
        "reactor-runs replay 'run needs quoting' --output table"
    )
    assert completed_actions[1]["command"] == (
        "reactor-runs fork 'run needs quoting' --checkpoint-ns 'tenant checkpoint' "
        "--checkpoint-id 'checkpoint needs quoting' --output table"
    )
    assert completed_actions[2]["command"] == (
        "reactor-admin state-history 'run needs quoting' --output table"
    )
    assert running_actions[0]["command"] == (
        "reactor-runs replay 'run needs quoting' --output table"
    )
    assert running_actions[1]["command"] == (
        "reactor-runs resume 'run needs quoting' --approval-id 'approval needs quoting' "
        "--output table"
    )
    assert running_actions[2]["command"] == (
        "reactor-runs resume 'run needs quoting' --approval-id 'approval needs quoting' "
        "--reject --reason 'operator rejected approval' --output table"
    )


def test_run_result_table_quotes_run_operator_actions() -> None:
    table = format_run_result_table(
        {
            "run_id": "run needs quoting",
            "status": "completed",
            "approval_id": "approval_1",
            "response": "done",
        }
    )

    assert "run_id              run needs quoting\n" in table
    assert "diagnoseAction      reactor-runs diagnose 'run needs quoting' --output table\n" in table
    assert (
        "stateHistoryAction  reactor-admin state-history 'run needs quoting' --output table\n"
    ) in table
    assert "replayAction        reactor-runs replay 'run needs quoting' --output table\n" in table


def test_run_result_table_surfaces_cancel_next_action() -> None:
    table = format_run_result_table(
        {
            "run_id": "run_1",
            "status": "started",
            "nextActions": [
                {
                    "id": "cancel-run",
                    "label": "Cancel the run",
                    "command": (
                        "reactor-runs cancel run_1 "
                        "--reason 'operator requested cancellation' --output table"
                    ),
                }
            ],
        }
    )

    assert (
        "cancelAction  reactor-runs cancel run_1 "
        "--reason 'operator requested cancellation' --output table\n"
    ) in table


def test_run_result_table_surfaces_fork_checkpoint_metadata() -> None:
    table = format_run_result_table(
        {
            "run_id": "run_1",
            "status": "completed",
            "nextActions": [
                {
                    "id": "fork-checkpoint",
                    "label": "Fork from checkpoint",
                    "threadId": "thread_1",
                    "checkpointNs": "reactor",
                    "checkpointId": "checkpoint_7",
                    "command": (
                        "reactor-runs fork run_1 --checkpoint-ns reactor "
                        "--checkpoint-id checkpoint_7 --output table"
                    ),
                }
            ],
        }
    )

    assert "forkAction.threadId      thread_1\n" in table
    assert "forkAction.checkpointNs  reactor\n" in table
    assert "forkAction.checkpointId  checkpoint_7\n" in table


def test_run_result_table_surfaces_unknown_next_action_by_id() -> None:
    table = format_run_result_table(
        {
            "run_id": "run_1",
            "status": "failed",
            "nextActions": [
                {
                    "id": "inspect-provider-fallback",
                    "label": "Inspect provider fallback",
                    "command": "reactor-runs providers run_1 --output table",
                }
            ],
        }
    )

    assert (
        "nextAction.inspect-provider-fallback  reactor-runs providers run_1 --output table\n"
        in table
    )


def test_run_result_table_surfaces_approval_next_action_metadata() -> None:
    table = format_run_result_table(
        {
            "run_id": "run_waiting",
            "status": "waiting_for_approval",
            "nextActions": [
                {
                    "id": "resume-approval",
                    "label": "Approve this pending LangGraph approval",
                    "sourceRunId": "run_waiting",
                    "threadId": "thread_1",
                    "approvalId": "approval_1",
                    "command": (
                        "reactor-runs resume run_waiting --approval-id approval_1 --output table"
                    ),
                }
            ],
        }
    )

    assert "nextAction.resume-approval.approvalId" in table
    assert "approval_1" in table


def test_fork_table_quotes_run_operator_actions() -> None:
    table = format_fork_table({"run_id": "fork needs quoting", "status": "completed"})

    assert "run_id              fork needs quoting\n" in table
    assert (
        "nextAction          reactor-runs diagnose 'fork needs quoting' --output table\n" in table
    )
    assert (
        "stateHistoryAction  reactor-admin state-history 'fork needs quoting' --output table\n"
    ) in table
    assert "replayAction        reactor-runs replay 'fork needs quoting' --output table\n" in table


def test_fork_table_preserves_api_next_action_metadata() -> None:
    table = format_fork_table(
        {
            "runId": "run_fork",
            "sourceRunId": "run_source",
            "threadId": "thread_fork",
            "checkpointNs": "reactor",
            "status": "started",
            "nextActions": [
                {
                    "id": "cancel-run",
                    "sourceRunId": "run_fork",
                    "threadId": "thread_fork",
                    "checkpointNs": "reactor",
                    "command": (
                        "reactor-runs cancel run_fork "
                        "--reason 'operator requested cancellation' --output table"
                    ),
                }
            ],
        }
    )

    assert "cancelAction.checkpointNs" in table
    assert "reactor" in table


def test_runs_cli_creates_run_with_tenant_headers_and_json_output() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "user_1",
            "create",
            "--message",
            "hello",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=stderr,
        environ={},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == {
        "run_id": "run_1",
        "status": "completed",
        "response": "answer",
        "nextActions": run_1_operator_next_actions(),
    }
    assert stderr.getvalue() == ""
    assert probe.calls == [
        {
            "method": "POST",
            "path": "/v1/runs",
            "headers": {
                "Content-Type": "application/json",
                "X-Reactor-Tenant-Id": "tenant_1",
                "X-Reactor-User-Id": "user_1",
            },
            "payload": {"message": "hello"},
        }
    ]


def test_runs_cli_create_can_render_operator_table_output() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "user_1",
            "create",
            "--message",
            "hello",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "FIELD               VALUE\n"
        "run_id              run_1\n"
        "status              completed\n"
        "response            answer\n"
        "nextAction          reactor-runs diagnose run_1 --output table\n"
        "stateHistoryAction  reactor-admin state-history run_1 --output table\n"
        "replayAction        reactor-runs replay run_1 --output table\n"
    )
    assert probe.calls[-1]["path"] == "/v1/runs"


def test_runs_cli_create_preflight_first_can_render_operator_table_output() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "create",
            "--message",
            "start after policy check",
            "--preflight-first",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "FIELD               VALUE\n"
        "preflight.status    ready\n"
        "preflight.runtime   langchain_agent\n"
        "preflight.threadId  thread_1\n"
        "preflight.model     openai/gpt-5-mini\n"
        "run.run_id          run_1\n"
        "run.status          completed\n"
        "nextAction          reactor-runs diagnose run_1 --output table\n"
        "stateHistoryAction  reactor-admin state-history run_1 --output table\n"
        "replayAction        reactor-runs replay run_1 --output table\n"
    )
    assert [call["path"] for call in probe.calls[-2:]] == ["/v1/runs/preflight", "/v1/runs"]


def test_runs_cli_create_posts_operational_context_to_run_api() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "create",
            "--message",
            "resume this thread",
            "--thread-id",
            "thread_cli",
            "--checkpoint-ns",
            "cli_ns",
            "--metadata-json",
            '{"runtime":"langchain_agent","graphProfile":"default"}',
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue())["run_id"] == "run_1"
    assert probe.calls[-1] == {
        "method": "POST",
        "path": "/v1/runs",
        "headers": {
            "Content-Type": "application/json",
            "X-Reactor-Tenant-Id": "tenant_1",
            "X-Reactor-User-Id": "operator_1",
        },
        "payload": {
            "message": "resume this thread",
            "threadId": "thread_cli",
            "checkpointNs": "cli_ns",
            "metadata": {
                "runtime": "langchain_agent",
                "graphProfile": "default",
            },
        },
    }


def test_runs_cli_create_can_preflight_before_starting_run() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "create",
            "--message",
            "start after policy check",
            "--thread-id",
            "thread_cli",
            "--checkpoint-ns",
            "cli_ns",
            "--metadata-json",
            '{"runtime":"langchain_agent","toolProfileBudget":{"maxTools":3}}',
            "--preflight-first",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == {
        "preflight": {
            "status": "ready",
            "runtime": "langchain_agent",
            "threadId": "thread_1",
            "checkpointNs": "reactor",
            "model": {"provider": "openai", "name": "gpt-5-mini"},
            "middlewareChain": {
                "count": 2,
                "middleware": ["ModelCallLimitMiddleware", "PIIMiddleware"],
            },
            "toolProfileBudget": {
                "activeToolCount": 2,
                "configuredToolCount": 4,
            },
            "structuredOutput": {
                "strategy": "json_object_schema",
                "status": "applied",
            },
        },
        "run": {
            "run_id": "run_1",
            "status": "completed",
            "response": "answer",
            "nextActions": run_1_operator_next_actions(),
        },
    }
    shared_payload = {
        "message": "start after policy check",
        "threadId": "thread_cli",
        "checkpointNs": "cli_ns",
        "metadata": {
            "runtime": "langchain_agent",
            "toolProfileBudget": {"maxTools": 3},
        },
    }
    assert probe.calls[-2:] == [
        {
            "method": "POST",
            "path": "/v1/runs/preflight",
            "headers": {
                "Content-Type": "application/json",
                "X-Reactor-Tenant-Id": "tenant_1",
                "X-Reactor-User-Id": "operator_1",
            },
            "payload": shared_payload,
        },
        {
            "method": "POST",
            "path": "/v1/runs",
            "headers": {
                "Content-Type": "application/json",
                "X-Reactor-Tenant-Id": "tenant_1",
                "X-Reactor-User-Id": "operator_1",
            },
            "payload": shared_payload,
        },
    ]


def test_runs_cli_create_can_attach_post_create_diagnostics() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "create",
            "--message",
            "answer then show me what happened",
            "--diagnose-after-create",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == {
        "run": {
            "run_id": "run_1",
            "status": "completed",
            "response": "answer",
            "nextActions": run_1_operator_next_actions(),
        },
        "diagnostics": {
            "runId": "run_1",
            "status": {
                "ok": True,
                "statusCode": 200,
                "body": {
                    "run_id": "run_1",
                    "status": "completed",
                },
            },
            "streamEvents": {
                "ok": True,
                "statusCode": 200,
                "body": [{"sequence": 1, "event_type": "message"}],
            },
            "toolInvocations": {
                "ok": True,
                "statusCode": 200,
                "body": [
                    {
                        "id": "tool_ok",
                        "runId": "run_1",
                        "toolId": "Rag:hybrid_search",
                        "status": "succeeded",
                        "success": True,
                    }
                ],
            },
        },
    }
    assert [call["path"] for call in probe.calls] == [
        "/v1/runs",
        "/v1/runs/run_1",
        "/v1/runs/run_1/stream-events",
        "/v1/runs/run_1/tool-invocations?limit=100",
    ]
    assert "payload" not in stdout.getvalue()
    assert "response_text" not in stdout.getvalue()


def test_runs_cli_create_with_post_create_diagnostics_can_render_table_output() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "create",
            "--message",
            "answer then summarize what happened",
            "--diagnose-after-create",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "FIELD               VALUE\n"
        "run.run_id          run_1\n"
        "run.status          completed\n"
        "diagnostics.status  completed\n"
        "diagnostics.events  1\n"
        "diagnostics.tools   1\n"
        "diagnostics.failed  0\n"
        "nextAction          reactor-runs diagnose run_1 --output table\n"
        "stateHistoryAction  reactor-admin state-history run_1 --output table\n"
        "replayAction        reactor-runs replay run_1 --output table\n"
    )


def test_runs_cli_create_with_post_create_diagnostics_table_shows_approval_next_action() -> None:
    class PendingApprovalCreateProbe(FakeRunsProbe):
        def post_json(
            self,
            path: str,
            headers: dict[str, str],
            payload: dict[str, object],
        ) -> RunCliHttpResult:
            if path == "/v1/runs":
                self.calls.append(
                    {
                        "method": "POST",
                        "path": path,
                        "headers": headers,
                        "payload": payload,
                    }
                )
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_waiting",
                        "status": "running",
                        "threadId": "thread_waiting",
                    },
                )
            return super().post_json(path, headers, payload)

        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_waiting":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_waiting",
                        "status": "running",
                        "threadId": "thread_waiting",
                    },
                )
            if path == "/v1/runs/run_waiting/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "sequence": 2,
                            "event_type": "run.stream.approval",
                            "payload": {
                                "approval_status": "pending",
                                "approval_id": "approval_1",
                            },
                        }
                    ],
                )
            if path == "/v1/runs/run_waiting/tool-invocations?limit=100":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(ok=True, status_code=200, body=[])
            return super().get_json(path, headers)

    probe = PendingApprovalCreateProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "create",
            "--message",
            "send the webhook",
            "--diagnose-after-create",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    output = stdout.getvalue()
    assert "diagnostics.nextAction" in output
    assert (
        "reactor-runs replay run_waiting --output table; reactor-runs resume run_waiting "
        "--approval-id approval_1 --output table; reactor-runs resume run_waiting "
        "--approval-id approval_1 --reject --reason 'operator rejected approval' --output table; "
        "reactor-runs cancel run_waiting "
        "--reason 'operator requested cancellation' --output table"
    ) in output
    assert (
        "diagnostics.nextActionIds  replay-stream,resume-approval,reject-approval,cancel-run\n"
        in (output)
    )
    assert "diagnostics.sourceRunIds   run_waiting\n" in output
    assert "diagnostics.approvalIds    approval_1\n" in output


def test_runs_cli_create_preflight_first_blocks_rejected_run() -> None:
    class RejectedPreflightProbe(FakeRunsProbe):
        def post_json(
            self,
            path: str,
            headers: dict[str, str],
            payload: dict[str, object],
        ) -> RunCliHttpResult:
            self.calls.append(
                {
                    "method": "POST",
                    "path": path,
                    "headers": headers,
                    "payload": payload,
                }
            )
            if path == "/v1/runs/preflight":
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={"status": "rejected", "reason": "unsupported_runtime"},
                )
            raise AssertionError("create should not run after rejected preflight")

    probe = RejectedPreflightProbe()
    stderr = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "create",
            "--message",
            "do not start this",
            "--metadata-json",
            '{"runtime":"unknown"}',
            "--preflight-first",
        ],
        http_probe=probe,
        stdout=StringIO(),
        stderr=stderr,
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 1
    assert "unsupported_runtime" in stderr.getvalue()
    assert [call["path"] for call in probe.calls] == ["/v1/runs/preflight"]


def test_runs_cli_preflight_posts_policy_probe_without_creating_run() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "user_1",
            "preflight",
            "--message",
            "should I run this?",
            "--thread-id",
            "thread_1",
            "--checkpoint-ns",
            "reactor",
            "--metadata-json",
            '{"runtime":"langchain_agent","toolProfileBudget":{"maxTools":3}}',
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue())["status"] == "ready"
    assert probe.calls[-1] == {
        "method": "POST",
        "path": "/v1/runs/preflight",
        "headers": {
            "Content-Type": "application/json",
            "X-Reactor-Tenant-Id": "tenant_1",
            "X-Reactor-User-Id": "user_1",
        },
        "payload": {
            "message": "should I run this?",
            "threadId": "thread_1",
            "checkpointNs": "reactor",
            "metadata": {
                "runtime": "langchain_agent",
                "toolProfileBudget": {"maxTools": 3},
            },
        },
    }


def test_runs_cli_preflight_can_render_operator_table_output() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "user_1",
            "preflight",
            "--message",
            "should I run this?",
            "--metadata-json",
            '{"runtime":"langchain_agent"}',
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    rows = dict(line.split(maxsplit=1) for line in stdout.getvalue().splitlines()[1:])
    assert rows["status"] == "ready"
    assert rows["runtime"] == "langchain_agent"
    assert rows["threadId"] == "thread_1"
    assert rows["checkpointNs"] == "reactor"
    assert rows["model"] == "openai/gpt-5-mini"
    assert rows["middlewareCount"] == "2"
    assert rows["middlewareChain"] == "ModelCallLimitMiddleware, PIIMiddleware"
    assert rows["activeTools"] == "2/4"
    assert rows["structuredOutput"] == "json_object_schema"
    assert rows["structuredStatus"] == "applied"
    assert probe.calls[-1]["path"] == "/v1/runs/preflight"


def test_runs_cli_status_and_replay_use_existing_run_api() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    status_exit = run_cli(
        ["--base-url", "http://reactor.local", "status", "run_1"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )
    replay_out = StringIO()
    replay_exit = run_cli(
        ["--base-url", "http://reactor.local", "replay", "run_1"],
        http_probe=probe,
        stdout=replay_out,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert status_exit == 0
    assert json.loads(stdout.getvalue())["status"] == "completed"
    assert replay_exit == 0
    replay_payload = json.loads(replay_out.getvalue())
    assert replay_payload == [{"sequence": 1, "event_type": "message"}]
    assert [call["path"] for call in probe.calls] == [
        "/v1/runs/run_1",
        "/v1/runs/run_1/stream-events",
    ]


def test_runs_cli_status_json_omits_raw_payload_fields() -> None:
    class StatusPayloadProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_1",
                        "status": "completed",
                        "threadId": "thread_1",
                        "checkpointNs": "reactor",
                        "lastCheckpointId": "checkpoint_1",
                        "input_text": "private user request",
                        "response_text": "private model answer",
                        "metadata": {
                            "model_provider": "openai",
                            "selected_model": "gpt-5-mini",
                            "raw_user_input": "private metadata prompt",
                            "tool_input": {"url": "https://private.example"},
                            "payload": {"response": "private metadata payload"},
                            "tokenUsage": {
                                "inputTokens": 120,
                                "outputTokens": 35,
                                "totalTokens": 155,
                                "cachedTokens": 40,
                                "reasoningTokens": 7,
                            },
                        },
                    },
                )
            return super().get_json(path, headers)

    probe = StatusPayloadProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "status", "run_1"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == {
        "run_id": "run_1",
        "status": "completed",
        "threadId": "thread_1",
        "checkpointNs": "reactor",
        "lastCheckpointId": "checkpoint_1",
        "metadata": {
            "model_provider": "openai",
            "selected_model": "gpt-5-mini",
            "tokenUsage": {
                "inputTokens": 120,
                "outputTokens": 35,
                "totalTokens": 155,
                "cachedTokens": 40,
                "reasoningTokens": 7,
            },
        },
    }
    assert "private user request" not in stdout.getvalue()
    assert "private model answer" not in stdout.getvalue()
    assert "private metadata prompt" not in stdout.getvalue()
    assert "https://private.example" not in stdout.getvalue()
    assert "private metadata payload" not in stdout.getvalue()


def test_runs_cli_status_can_render_operator_table_output() -> None:
    class StatusMetadataProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_1",
                        "status": "completed",
                        "threadId": "thread_1",
                        "checkpointNs": "reactor",
                        "lastCheckpointId": "checkpoint_1",
                        "response_text": "answer",
                        "nextActions": [
                            {
                                "id": "diagnose-run",
                                "label": "Diagnose with server policy",
                                "command": "reactor-runs diagnose run_1 --output json",
                            },
                            {
                                "id": "inspect-state-history",
                                "label": "Inspect state with server policy",
                                "command": (
                                    "reactor-admin state-history run_1 --limit 5 --output table"
                                ),
                            },
                            {
                                "id": "replay-stream",
                                "label": "Replay with server policy",
                                "command": (
                                    "reactor-runs replay run_1 --after-sequence 10 --output table"
                                ),
                            },
                        ],
                    },
                )
            return super().get_json(path, headers)

    probe = StatusMetadataProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "status", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "FIELD               VALUE\n"
        "run_id              run_1\n"
        "status              completed\n"
        "thread_id           thread_1\n"
        "checkpoint_ns       reactor\n"
        "last_checkpoint_id  checkpoint_1\n"
        "response_text       answer\n"
        "nextAction          reactor-runs diagnose run_1 --output json\n"
        "stateHistoryAction  reactor-admin state-history run_1 --limit 5 --output table\n"
        "replayAction        reactor-runs replay run_1 --after-sequence 10 --output table\n"
    )
    assert probe.calls[-1]["path"] == "/v1/runs/run_1"


def test_runs_cli_status_table_shows_checkpoint_runtime_provenance() -> None:
    class StatusCheckpointProvenanceProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_1",
                        "status": "completed",
                        "threadId": "thread_1",
                        "checkpointNs": "reactor",
                        "lastCheckpointId": "checkpoint_1",
                        "metadata": {
                            "checkpointProvenance": {
                                "store": "AsyncPostgresSaver",
                                "graphStoreRuntime": {
                                    "durableStore": "AsyncPostgresStore",
                                    "localStore": "InMemoryStore",
                                },
                            }
                        },
                    },
                )
            return super().get_json(path, headers)

    probe = StatusCheckpointProvenanceProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "status", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    lines = stdout.getvalue().splitlines()
    assert "checkpoint_store     AsyncPostgresSaver" in lines
    assert "graph_durable_store  AsyncPostgresStore" in lines
    assert "graph_local_store    InMemoryStore" in lines


def test_runs_cli_status_table_shows_langchain_middleware_policy() -> None:
    class StatusMiddlewareProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_1",
                        "status": "completed",
                        "metadata": {
                            "langchainMiddlewarePolicy": {
                                "status": "applied",
                                "source": "tenant_runtime_setting",
                                "policy": {
                                    "modelCallRunLimit": 3,
                                    "toolCallRunLimit": 2,
                                    "modelRetryMaxRetries": 1,
                                    "toolRetryMaxRetries": 2,
                                },
                            },
                            "langchainMiddlewareChain": {
                                "status": "applied",
                                "count": 2,
                                "middleware": ["ModelCallLimitMiddleware", "PIIMiddleware"],
                                "piiRuleCount": 1,
                                "hitlToolCount": 2,
                                "fallbackModelCount": 1,
                            },
                        },
                        "response_text": "answer",
                    },
                )
            return super().get_json(path, headers)

    probe = StatusMiddlewareProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "status", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "FIELD                        VALUE\n"
        "run_id                       run_1\n"
        "status                       completed\n"
        "langchain_middleware_status  applied\n"
        "langchain_middleware_source  tenant_runtime_setting\n"
        "langchain_model_limit        3\n"
        "langchain_tool_limit         2\n"
        "langchain_model_retries      1\n"
        "langchain_tool_retries       2\n"
        "langchain_middleware_chain   ModelCallLimitMiddleware, PIIMiddleware\n"
        "langchain_middleware_pii     1\n"
        "langchain_middleware_hitl    2\n"
        "langchain_middleware_models  1\n"
        "response_text                answer\n"
    )
    assert probe.calls[-1]["path"] == "/v1/runs/run_1"


def test_runs_cli_status_table_shows_structured_output_metadata() -> None:
    class StatusStructuredOutputProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_1",
                        "status": "completed",
                        "metadata": {
                            "structuredOutput": {
                                "strategy": "schema_passthrough",
                                "status": "repaired",
                                "schemaSource": "metadata.responseSchema",
                                "citationPolicy": "required",
                                "citationCount": 2,
                                "allowedCitationIds": ["doc_1:0", "doc_2:1"],
                                "ignoredSchema": {
                                    "reason": "invalid_response_schema",
                                    "source": "metadata.responseSchema",
                                },
                            }
                        },
                    },
                )
            return super().get_json(path, headers)

    probe = StatusStructuredOutputProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "status", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    output = stdout.getvalue()
    assert "structured_output_strategy" in output
    assert "schema_passthrough" in output
    assert "structured_output_status" in output
    assert "repaired" in output
    assert "structured_output_schema_source" in output
    assert "metadata.responseSchema" in output
    assert "structured_output_citation_policy" in output
    assert "required" in output
    assert "structured_output_citation_count" in output
    assert "2" in output
    assert "structured_output_allowed_citations" in output
    assert "2" in output
    assert "structured_output_ignored_reason" in output
    assert "invalid_response_schema" in output
    assert "doc_1:0" not in output
    assert "doc_2:1" not in output


def test_runs_cli_status_table_shows_tool_profile_budget_drops() -> None:
    class StatusToolProfileProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_1",
                        "status": "completed",
                        "metadata": {
                            "resolvedToolProfileBudget": {
                                "source": "metadata",
                                "maxTools": 1,
                                "configuredToolCount": 3,
                                "activeToolCount": 1,
                                "activeTools": ["Rag:hybrid_search"],
                                "droppedToolCount": 2,
                                "droppedTools": [
                                    {"name": "shell", "reason": "denied_tool"},
                                    {"name": "browser", "reason": "max_tools_exceeded"},
                                ],
                            }
                        },
                    },
                )
            return super().get_json(path, headers)

    probe = StatusToolProfileProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "status", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert "tool_profile_budget_source" in stdout.getvalue()
    assert "tool_profile_budget_max" in stdout.getvalue()
    assert "tool_profile_active_tools" in stdout.getvalue()
    assert "tool_profile_active_tool_names" in stdout.getvalue()
    assert "Rag:hybrid_search\n" in stdout.getvalue()
    assert "tool_profile_dropped_tools" in stdout.getvalue()
    assert "tool_profile_drop_reasons" in stdout.getvalue()
    assert "denied_tool=1,max_tools_exceeded=1\n" in stdout.getvalue()
    assert "tool_profile_dropped_sample" in stdout.getvalue()
    assert "shell:denied_tool,browser:max_tools_exceeded\n" in stdout.getvalue()


def test_runs_cli_status_table_shows_provider_runtime_metadata() -> None:
    class StatusProviderRuntimeProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_1",
                        "status": "completed",
                        "metadata": {
                            "model_provider": "openai",
                            "selected_model": "gpt-5-mini",
                            "model_fallback_used": True,
                        },
                        "response_text": "answer",
                    },
                )
            return super().get_json(path, headers)

    probe = StatusProviderRuntimeProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "status", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "FIELD                VALUE\n"
        "run_id               run_1\n"
        "status               completed\n"
        "model_provider       openai\n"
        "selected_model       gpt-5-mini\n"
        "model_fallback_used  true\n"
        "response_text        answer\n"
    )
    assert probe.calls[-1]["path"] == "/v1/runs/run_1"


def test_runs_cli_status_table_shows_provider_fallback_metadata() -> None:
    class StatusProviderFallbackProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_1",
                        "status": "completed",
                        "metadata": {
                            "providerFallback": {
                                "from_provider": "openai",
                                "from_model": "gpt-5-mini",
                                "to_provider": "anthropic",
                                "to_model": "claude-sonnet-5",
                                "reason": "provider_timeout",
                                "latency_ms": 250,
                                "cost_usd": 0.004,
                            },
                        },
                    },
                )
            return super().get_json(path, headers)

    probe = StatusProviderFallbackProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "status", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "FIELD                         VALUE\n"
        "run_id                        run_1\n"
        "status                        completed\n"
        "provider_fallback_from        openai/gpt-5-mini\n"
        "provider_fallback_to          anthropic/claude-sonnet-5\n"
        "provider_fallback_reason      provider_timeout\n"
        "provider_fallback_latency_ms  250\n"
        "provider_fallback_cost_usd    0.004\n"
    )


def test_runs_cli_status_table_shows_token_usage_metadata() -> None:
    class StatusTokenUsageProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_1",
                        "status": "completed",
                        "metadata": {
                            "tokenUsage": {
                                "inputTokens": 120,
                                "outputTokens": 35,
                                "totalTokens": 155,
                                "cachedTokens": 40,
                                "reasoningTokens": 7,
                            },
                        },
                        "response_text": "answer",
                    },
                )
            return super().get_json(path, headers)

    probe = StatusTokenUsageProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "status", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "FIELD             VALUE\n"
        "run_id            run_1\n"
        "status            completed\n"
        "input_tokens      120\n"
        "output_tokens     35\n"
        "total_tokens      155\n"
        "cached_tokens     40\n"
        "reasoning_tokens  7\n"
        "response_text     answer\n"
    )
    assert probe.calls[-1]["path"] == "/v1/runs/run_1"


def test_runs_cli_status_table_shows_langchain_usage_metadata() -> None:
    class StatusLangChainUsageProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_1",
                        "status": "completed",
                        "metadata": {
                            "usage_metadata": {
                                "input_tokens": 120,
                                "output_tokens": 35,
                                "total_tokens": 155,
                                "input_token_details": {"cache_read": 40},
                                "output_token_details": {"reasoning": 7},
                            },
                        },
                        "response_text": "answer",
                    },
                )
            return super().get_json(path, headers)

    probe = StatusLangChainUsageProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "status", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "FIELD             VALUE\n"
        "run_id            run_1\n"
        "status            completed\n"
        "input_tokens      120\n"
        "output_tokens     35\n"
        "total_tokens      155\n"
        "cached_tokens     40\n"
        "reasoning_tokens  7\n"
        "response_text     answer\n"
    )


def test_runs_cli_replay_can_render_operator_table_output() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "replay", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "SEQ  EVENT    NODE  TRACE  SUMMARY\n1    message               text=answer\n"
        "\n"
        "FIELD               VALUE\n"
        "diagnoseAction      reactor-runs diagnose run_1 --output table\n"
        "stateHistoryAction  reactor-admin state-history run_1 --output table\n"
        "replayNextAction    reactor-runs replay run_1 --after-sequence 1 --output table\n"
    )
    assert probe.calls[-1]["path"] == "/v1/runs/run_1/stream-events"


def test_runs_cli_replay_table_shows_state_history_next_action() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "replay", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert "stateHistoryAction  reactor-admin state-history run_1 --output table\n" in (
        stdout.getvalue()
    )


def test_runs_cli_replay_table_shows_diagnose_next_action() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "replay", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert "diagnoseAction      reactor-runs diagnose run_1 --output table\n" in (stdout.getvalue())


def test_runs_cli_replay_table_shows_continue_after_latest_sequence_action() -> None:
    class MultiEventProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            self.calls.append({"method": "GET", "path": path, "headers": headers})
            if path == "/v1/runs/run_1/stream-events":
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {"sequence": 1, "event_type": "run.stream.start", "payload": {}},
                        {"sequence": 3, "event_type": "run.stream.delta", "payload": {}},
                    ],
                )
            return super().get_json(path, headers)

    probe = MultiEventProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "replay", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert (
        "replayNextAction    reactor-runs replay run_1 --after-sequence 3 --output table\n"
        in stdout.getvalue()
    )


def test_runs_cli_replay_passes_stream_event_filters_to_api() -> None:
    class FilteredReplayProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            self.calls.append({"method": "GET", "path": path, "headers": headers})
            if path == "/v1/runs/run_1/stream-events?after_sequence=3&event_type=run.stream.token":
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "sequence": 4,
                            "event_type": "run.stream.token",
                            "payload": {"text": "next"},
                        }
                    ],
                )
            return RunCliHttpResult(ok=False, status_code=404, error="not_found")

    probe = FilteredReplayProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "replay",
            "run_1",
            "--after-sequence",
            "3",
            "--event-type",
            "run.stream.token",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert probe.calls[-1]["path"] == (
        "/v1/runs/run_1/stream-events?after_sequence=3&event_type=run.stream.token"
    )


def test_runs_cli_replay_table_shows_langgraph_node() -> None:
    class ReplayGraphNodeProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "sequence": 2,
                            "event_type": "run.stream.token",
                            "payload": {
                                "graph_node": "model",
                                "trace_id": "trace_1",
                                "text": "answer",
                            },
                        }
                    ],
                )
            return super().get_json(path, headers)

    probe = ReplayGraphNodeProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "replay", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "SEQ  EVENT             NODE   TRACE    SUMMARY\n"
        "2    run.stream.token  model  trace_1  text=answer\n"
        "\n"
        "FIELD               VALUE\n"
        "diagnoseAction      reactor-runs diagnose run_1 --output table\n"
        "stateHistoryAction  reactor-admin state-history run_1 --output table\n"
        "replayNextAction    reactor-runs replay run_1 --after-sequence 2 --output table\n"
    )


def test_runs_cli_replay_table_shows_langgraph_stream_linkage() -> None:
    class ReplayStreamLinkageProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "sequence": 2,
                            "event_type": "run.stream.token",
                            "payload": {
                                "graphNode": "model",
                                "traceId": "trace_1",
                                "runId": "lg_run_1",
                                "parentIds": ["root_run", "branch_run"],
                                "text": "answer",
                            },
                        }
                    ],
                )
            return super().get_json(path, headers)

    probe = ReplayStreamLinkageProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "replay", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert (
        "2    run.stream.token  model  trace_1  text=answer streamRun=lg_run_1 parentRuns=2\n"
    ) in stdout.getvalue()


def test_runs_cli_replay_table_shows_langgraph_stream_semantics() -> None:
    class ReplayStreamSemanticsProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "sequence": 2,
                            "event_type": "run.stream.token",
                            "payload": {
                                "graphNode": "model",
                                "traceId": "trace_1",
                                "mode": "messages",
                                "version": "v3",
                                "text": "answer",
                            },
                        }
                    ],
                )
            return super().get_json(path, headers)

    probe = ReplayStreamSemanticsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "replay", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert (
        "2    run.stream.token  model  trace_1  text=answer mode=messages version=v3\n"
    ) in stdout.getvalue()


def test_runs_cli_replay_table_omits_raw_private_stream_payload() -> None:
    class ReplayPrivatePayloadProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "sequence": 3,
                            "event_type": "run.stream.approval",
                            "payload": {
                                "graph_node": "approval_gate",
                                "approval_status": "pending",
                                "approval_id": "approval_1",
                                "input_payload": {"url": "https://private.example"},
                                "raw_user_input": "private user request",
                            },
                        }
                    ],
                )
            return super().get_json(path, headers)

    probe = ReplayPrivatePayloadProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "replay", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "SEQ  EVENT                NODE           TRACE  SUMMARY\n"
        "3    run.stream.approval  approval_gate         "
        "approvalStatus=pending approvalId=approval_1\n"
        "\n"
        "FIELD               VALUE\n"
        "diagnoseAction      reactor-runs diagnose run_1 --output table\n"
        "stateHistoryAction  reactor-admin state-history run_1 --output table\n"
        "replayNextAction    reactor-runs replay run_1 --after-sequence 3 --output table\n"
    )
    assert "https://private.example" not in stdout.getvalue()
    assert "private user request" not in stdout.getvalue()


def test_runs_cli_replay_table_redacts_secret_shaped_stream_text() -> None:
    class ReplaySecretTextProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "sequence": 4,
                            "event_type": "run.stream.token",
                            "payload": {
                                "graph_node": "model",
                                "trace_id": "trace_1",
                                "text": "provider token sk-test-secret-value",
                            },
                        }
                    ],
                )
            return super().get_json(path, headers)

    probe = ReplaySecretTextProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "replay", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert "sk-test-secret-value" not in stdout.getvalue()
    assert "text=provider token [REDACTED]" in stdout.getvalue()


def test_runs_cli_replay_json_omits_raw_private_stream_payload() -> None:
    class ReplayPrivatePayloadProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "sequence": 3,
                            "event_type": "run.stream.approval",
                            "node": "approval_gate",
                            "payload": {
                                "trace_id": "trace_1",
                                "approval_status": "pending",
                                "approval_id": "approval_1",
                                "input_payload": {"url": "https://private.example"},
                                "raw_user_input": "private user request",
                            },
                        }
                    ],
                )
            return super().get_json(path, headers)

    probe = ReplayPrivatePayloadProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "replay", "run_1"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == [
        {
            "sequence": 3,
            "event_type": "run.stream.approval",
            "node": "approval_gate",
        }
    ]
    assert "https://private.example" not in stdout.getvalue()
    assert "private user request" not in stdout.getvalue()


def test_runs_cli_lists_tool_invocations_with_status_filter() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "tool-invocations",
            "run_1",
            "--status",
            "failed",
            "--limit",
            "25",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == [
        {
            "id": "tool_1",
            "runId": "run_1",
            "toolId": "Webhook:send",
            "status": "failed",
            "success": False,
            "input": {"url": "https://example.com"},
            "output": None,
            "error": {"message": "approval required"},
        }
    ]
    assert probe.calls[-1]["path"] == "/v1/runs/run_1/tool-invocations?limit=25&status=failed"


def test_runs_cli_tool_invocations_can_render_operator_table_output() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "tool-invocations",
            "run_1",
            "--status",
            "failed",
            "--limit",
            "25",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "ID      TOOL          STATUS  SUCCESS  ERROR\n"
        "tool_1  Webhook:send  failed  false    approval required\n"
    )
    assert probe.calls[-1]["path"] == "/v1/runs/run_1/tool-invocations?limit=25&status=failed"


def test_runs_cli_diagnose_aggregates_run_events_and_tool_invocations() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_1"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == {
        "runId": "run_1",
        "status": {
            "ok": True,
            "statusCode": 200,
            "body": {
                "run_id": "run_1",
                "status": "completed",
            },
        },
        "streamEvents": {
            "ok": True,
            "statusCode": 200,
            "body": [{"sequence": 1, "event_type": "message"}],
        },
        "toolInvocations": {
            "ok": True,
            "statusCode": 200,
            "body": [
                {
                    "id": "tool_ok",
                    "runId": "run_1",
                    "toolId": "Rag:hybrid_search",
                    "status": "succeeded",
                    "success": True,
                }
            ],
        },
    }
    assert [call["path"] for call in probe.calls] == [
        "/v1/runs/run_1",
        "/v1/runs/run_1/stream-events",
        "/v1/runs/run_1/tool-invocations?limit=100",
    ]


def test_runs_cli_diagnose_url_encodes_run_id_path_segments() -> None:
    class EncodedRunProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            self.calls.append({"method": "GET", "path": path, "headers": headers})
            if path == "/v1/runs/run%2Fneeds%20encoding":
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={"run_id": "run/needs encoding", "status": "completed"},
                )
            if path == "/v1/runs/run%2Fneeds%20encoding/stream-events":
                return RunCliHttpResult(ok=True, status_code=200, body=[])
            if path == "/v1/runs/run%2Fneeds%20encoding/tool-invocations?limit=100":
                return RunCliHttpResult(ok=True, status_code=200, body=[])
            return RunCliHttpResult(ok=False, status_code=404, error="not found")

    probe = EncodedRunProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run/needs encoding"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert [call["path"] for call in probe.calls] == [
        "/v1/runs/run%2Fneeds%20encoding",
        "/v1/runs/run%2Fneeds%20encoding/stream-events",
        "/v1/runs/run%2Fneeds%20encoding/tool-invocations?limit=100",
    ]


def test_runs_cli_diagnose_json_omits_raw_payload_fields() -> None:
    class DiagnosePayloadProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_private":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_private",
                        "status": "completed",
                        "threadId": "thread_private",
                        "checkpointNs": "reactor",
                        "lastCheckpointId": "checkpoint_private",
                        "input_text": "private diagnose user request",
                        "response_text": "private diagnose model response",
                        "metadata": {
                            "model_provider": "openai",
                            "selected_model": "gpt-5-mini",
                            "tokenUsage": {"totalTokens": 42},
                        },
                    },
                )
            if path == "/v1/runs/run_private/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "sequence": 1,
                            "event_type": "message",
                            "node": "completion",
                            "payload": {"text": "private streamed token"},
                        }
                    ],
                )
            if path == "/v1/runs/run_private/tool-invocations?limit=100":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "id": "tool_private",
                            "runId": "run_private",
                            "toolId": "Webhook:send",
                            "status": "failed",
                            "success": False,
                            "input": {"url": "https://private.example"},
                            "output": {"body": "private tool output"},
                            "error": {"message": "approval required"},
                        }
                    ],
                )
            return super().get_json(path, headers)

    probe = DiagnosePayloadProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_private"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == {
        "runId": "run_private",
        "status": {
            "ok": True,
            "statusCode": 200,
            "body": {
                "run_id": "run_private",
                "status": "completed",
                "threadId": "thread_private",
                "checkpointNs": "reactor",
                "lastCheckpointId": "checkpoint_private",
                "metadata": {
                    "model_provider": "openai",
                    "selected_model": "gpt-5-mini",
                    "tokenUsage": {"totalTokens": 42},
                },
            },
        },
        "streamEvents": {
            "ok": True,
            "statusCode": 200,
            "body": [{"sequence": 1, "event_type": "message", "node": "completion"}],
        },
        "toolInvocations": {
            "ok": True,
            "statusCode": 200,
            "body": [
                {
                    "id": "tool_private",
                    "runId": "run_private",
                    "toolId": "Webhook:send",
                    "status": "failed",
                    "success": False,
                    "error": {"message": "approval required"},
                }
            ],
        },
        "nextActions": [
            {
                "id": "fork-checkpoint",
                "label": "Fork this completed run from its latest LangGraph checkpoint",
                "sourceRunId": "run_private",
                "threadId": "thread_private",
                "checkpointNs": "reactor",
                "checkpointId": "checkpoint_private",
                "command": (
                    "reactor-runs fork run_private --checkpoint-ns reactor "
                    "--checkpoint-id checkpoint_private --output table"
                ),
            },
            {
                "id": "inspect-state-history",
                "label": "Inspect this run's LangGraph checkpoint state history",
                "sourceRunId": "run_private",
                "threadId": "thread_private",
                "checkpointNs": "reactor",
                "checkpointId": "checkpoint_private",
                "command": "reactor-admin state-history run_private --output table",
            },
        ],
    }
    assert "private diagnose user request" not in stdout.getvalue()
    assert "private diagnose model response" not in stdout.getvalue()
    assert "private streamed token" not in stdout.getvalue()
    assert "private tool output" not in stdout.getvalue()
    assert "https://private.example" not in stdout.getvalue()


def test_runs_cli_diagnose_can_render_operator_table_output() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "SECTION          OK    STATUS  SUMMARY\n"
        "status           true  200     completed\n"
        "streamEvents     true  200     events=1 traced=0/1\n"
        "toolInvocations  true  200     tools=1 failed=0\n"
    )
    assert [call["path"] for call in probe.calls] == [
        "/v1/runs/run_1",
        "/v1/runs/run_1/stream-events",
        "/v1/runs/run_1/tool-invocations?limit=100",
    ]


def test_runs_cli_diagnose_completed_langgraph_stream_without_checkpoint_suggests_replay() -> None:
    class CompletedLangGraphStreamProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_stream/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "sequence": 2,
                            "event_type": "run.stream.token",
                            "payload": {"trace_id": "trace_1", "text": "answer"},
                        }
                    ],
                )
            if path == "/v1/runs/run_stream":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={"run_id": "run_stream", "status": "completed"},
                )
            if path == "/v1/runs/run_stream/tool-invocations?limit=100":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(ok=True, status_code=200, body=[])
            return super().get_json(path, headers)

    probe = CompletedLangGraphStreamProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_stream"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["nextActions"] == [
        {
            "id": "replay-stream",
            "label": "Replay this run's persisted LangGraph stream events",
            "sourceRunId": "run_stream",
            "command": "reactor-runs replay run_stream --output table",
        }
    ]


def test_runs_cli_diagnose_completed_non_langgraph_event_does_not_suggest_replay() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_1"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert "nextActions" not in payload


def test_runs_cli_diagnose_table_summarizes_stream_event_types() -> None:
    class StreamEventTypeProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {"sequence": 1, "event_type": "run.stream.started", "payload": {}},
                        {
                            "sequence": 2,
                            "event_type": "run.stream.token",
                            "payload": {"trace_id": "trace_1", "text": "answer"},
                        },
                        {
                            "sequence": 3,
                            "event_type": "run.stream.approval",
                            "payload": {"traceId": "trace_2", "approval_status": "pending"},
                        },
                    ],
                )
            return super().get_json(path, headers)

    probe = StreamEventTypeProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert "streamEvents" in stdout.getvalue()
    assert "events=3 traced=2/3 approval=1 started=1 token=1" in stdout.getvalue()
    assert "nextAction.replay-stream" in stdout.getvalue()


def test_runs_cli_diagnose_pending_approval_suggests_resume_next_action() -> None:
    class PendingApprovalProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_waiting":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_waiting",
                        "status": "running",
                        "threadId": "thread_waiting",
                    },
                )
            if path == "/v1/runs/run_waiting/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "sequence": 4,
                            "event_type": "run.stream.approval",
                            "payload": {
                                "approval_status": "pending",
                                "approval_id": "approval_1",
                            },
                        }
                    ],
                )
            if path == "/v1/runs/run_waiting/tool-invocations?limit=100":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(ok=True, status_code=200, body=[])
            return super().get_json(path, headers)

    probe = PendingApprovalProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_waiting"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["nextActions"] == [
        {
            "id": "replay-stream",
            "label": "Replay this running run's persisted LangGraph stream events",
            "sourceRunId": "run_waiting",
            "threadId": "thread_waiting",
            "command": "reactor-runs replay run_waiting --output table",
        },
        {
            "id": "resume-approval",
            "label": "Resume this interrupted LangGraph run with the pending approval",
            "sourceRunId": "run_waiting",
            "threadId": "thread_waiting",
            "approvalId": "approval_1",
            "command": "reactor-runs resume run_waiting --approval-id approval_1 --output table",
        },
        {
            "id": "reject-approval",
            "label": "Reject this pending LangGraph approval and resume the run",
            "sourceRunId": "run_waiting",
            "threadId": "thread_waiting",
            "approvalId": "approval_1",
            "command": (
                "reactor-runs resume run_waiting --approval-id approval_1 "
                "--reject --reason 'operator rejected approval' --output table"
            ),
        },
        {
            "id": "cancel-run",
            "label": "Cancel this running Reactor run",
            "sourceRunId": "run_waiting",
            "threadId": "thread_waiting",
            "command": (
                "reactor-runs cancel run_waiting "
                "--reason 'operator requested cancellation' --output table"
            ),
        },
    ]


def test_runs_cli_diagnose_table_lists_each_pending_approval_next_action() -> None:
    class PendingApprovalProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_waiting":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_waiting",
                        "status": "running",
                        "threadId": "thread_waiting",
                    },
                )
            if path == "/v1/runs/run_waiting/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "sequence": 4,
                            "event_type": "run.stream.approval",
                            "payload": {
                                "approval_status": "pending",
                                "approval_id": "approval_1",
                            },
                        }
                    ],
                )
            if path == "/v1/runs/run_waiting/tool-invocations?limit=100":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(ok=True, status_code=200, body=[])
            return super().get_json(path, headers)

    probe = PendingApprovalProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "diagnose",
            "run_waiting",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    output = stdout.getvalue()
    assert "nextAction.resume-approval" in output
    assert "reactor-runs resume run_waiting --approval-id approval_1 --output table" in output
    assert "nextAction.resume-approval.sourceRunId" in output
    assert "nextAction.resume-approval.threadId" in output
    assert "nextAction.resume-approval.approvalId" in output
    assert "run_waiting" in output
    assert "approval_1" in output
    assert "nextAction.reject-approval" in output
    assert (
        "reactor-runs resume run_waiting --approval-id approval_1 "
        "--reject --reason 'operator rejected approval' --output table"
    ) in output
    assert "nextAction.reject-approval.sourceRunId" in output
    assert "nextAction.reject-approval.threadId" in output
    assert "nextAction.reject-approval.approvalId" in output
    assert "nextAction.cancel-run" in output
    assert (
        "reactor-runs cancel run_waiting --reason 'operator requested cancellation' --output table"
    ) in output
    assert "nextAction.cancel-run.sourceRunId" in output
    assert "nextAction.cancel-run.threadId" in output


def test_runs_cli_diagnose_running_run_suggests_cancel_next_action() -> None:
    class RunningRunProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_running":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={"run_id": "run_running", "status": "running"},
                )
            if path == "/v1/runs/run_running/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "sequence": 1,
                            "event_type": "run.stream.started",
                            "payload": {"graph_node": "context"},
                        }
                    ],
                )
            if path == "/v1/runs/run_running/tool-invocations?limit=100":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(ok=True, status_code=200, body=[])
            return super().get_json(path, headers)

    probe = RunningRunProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_running"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["nextActions"] == [
        {
            "id": "replay-stream",
            "label": "Replay this running run's persisted LangGraph stream events",
            "sourceRunId": "run_running",
            "command": "reactor-runs replay run_running --output table",
        },
        {
            "id": "cancel-run",
            "label": "Cancel this running Reactor run",
            "sourceRunId": "run_running",
            "command": (
                "reactor-runs cancel run_running "
                "--reason 'operator requested cancellation' --output table"
            ),
        },
    ]


def test_runs_cli_diagnose_started_run_suggests_running_recovery_actions() -> None:
    class StartedRunProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_started":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={"run_id": "run_started", "status": "started"},
                )
            if path == "/v1/runs/run_started/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[{"sequence": 1, "event_type": "run.stream.started"}],
                )
            if path == "/v1/runs/run_started/tool-invocations?limit=100":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(ok=True, status_code=200, body=[])
            return super().get_json(path, headers)

    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_started"],
        http_probe=StartedRunProbe(),
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    actions = {
        action["id"]: action["command"] for action in json.loads(stdout.getvalue())["nextActions"]
    }
    assert actions["replay-stream"] == "reactor-runs replay run_started --output table"
    assert actions["cancel-run"] == (
        "reactor-runs cancel run_started --reason 'operator requested cancellation' --output table"
    )


def test_runs_cli_diagnose_reports_partial_tool_invocation_failure() -> None:
    class PartialFailureProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1/tool-invocations?limit=100":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=False,
                    status_code=503,
                    error="tool diagnostics unavailable",
                )
            return super().get_json(path, headers)

    probe = PartialFailureProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_1"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == {
        "runId": "run_1",
        "status": {
            "ok": True,
            "statusCode": 200,
            "body": {
                "run_id": "run_1",
                "status": "completed",
            },
        },
        "streamEvents": {
            "ok": True,
            "statusCode": 200,
            "body": [{"sequence": 1, "event_type": "message"}],
        },
        "toolInvocations": {
            "ok": False,
            "statusCode": 503,
            "error": "tool diagnostics unavailable",
        },
    }


def test_runs_cli_diagnose_reconciliation_tools_suggests_filtered_tool_review() -> None:
    class ReconciliationToolProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1/tool-invocations?limit=100":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "id": "tool_reconcile",
                            "runId": "run_1",
                            "toolId": "Webhook:send",
                            "status": "requires_reconciliation",
                            "success": False,
                        }
                    ],
                )
            return super().get_json(path, headers)

    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_1"],
        http_probe=ReconciliationToolProbe(),
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    actions = {action["id"]: action for action in payload["nextActions"]}
    assert actions["inspect-reconciliation-tools"]["sourceRunId"] == "run_1"
    assert actions["inspect-reconciliation-tools"]["toolStatus"] == "requires_reconciliation"
    assert actions["inspect-reconciliation-tools"]["command"] == (
        "reactor-runs tool-invocations run_1 --status requires_reconciliation --output table"
    )


def test_runs_cli_diagnose_table_shows_reconciliation_tool_next_action() -> None:
    class ReconciliationToolProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1/tool-invocations?limit=100":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "id": "tool_reconcile",
                            "runId": "run_1",
                            "toolId": "Webhook:send",
                            "status": "requires_reconciliation",
                            "success": False,
                        }
                    ],
                )
            return super().get_json(path, headers)

    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_1", "--output", "table"],
        http_probe=ReconciliationToolProbe(),
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    output = stdout.getvalue()
    assert "nextAction.inspect-reconciliation-tools" in output
    assert (
        "reactor-runs tool-invocations run_1 --status requires_reconciliation --output table"
    ) in output
    assert "nextAction.inspect-reconciliation-tools.sourceRunId" in output
    assert "run_1" in output
    assert "nextAction.inspect-reconciliation-tools.toolStatus" in output
    assert "requires_reconciliation" in output


def test_runs_cli_diagnose_can_filter_tool_invocations_by_status() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "diagnose",
            "run_1",
            "--tool-status",
            "failed",
            "--tool-limit",
            "25",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["toolInvocations"]["body"] == [
        {
            "id": "tool_1",
            "runId": "run_1",
            "toolId": "Webhook:send",
            "status": "failed",
            "success": False,
            "error": {"message": "approval required"},
        }
    ]
    assert [call["path"] for call in probe.calls] == [
        "/v1/runs/run_1",
        "/v1/runs/run_1/stream-events",
        "/v1/runs/run_1/tool-invocations?limit=25&status=failed",
    ]


def test_runs_cli_diagnose_table_summarizes_failed_tool_names() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "diagnose",
            "run_1",
            "--tool-status",
            "failed",
            "--tool-limit",
            "25",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "SECTION          OK    STATUS  SUMMARY\n"
        "status           true  200     completed\n"
        "streamEvents     true  200     events=1 traced=0/1\n"
        "toolInvocations  true  200     tools=1 failed=1 failedTools=Webhook:send\n"
    )


def test_runs_cli_diagnose_table_summarizes_pending_approval_recovery_metadata() -> None:
    class ApprovalToolProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_waiting":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={"run_id": "run_waiting", "status": "running"},
                )
            if path == "/v1/runs/run_waiting/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "sequence": 2,
                            "event_type": "run.stream.approval",
                            "payload": {
                                "approval_status": "pending",
                                "approval_id": "approval_1",
                            },
                        }
                    ],
                )
            if path == "/v1/runs/run_waiting/tool-invocations?limit=100":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "id": "tool_waiting",
                            "runId": "run_waiting",
                            "toolId": "Webhook:send",
                            "status": "pending",
                            "success": False,
                            "approvalId": "approval_1",
                            "idempotencyKey": "idem_safe_1",
                            "execution": {
                                "riskLevel": "high",
                                "approvalRequired": True,
                            },
                            "input": {"url": "https://private.example"},
                        }
                    ],
                )
            return super().get_json(path, headers)

    probe = ApprovalToolProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_waiting", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    output = stdout.getvalue()
    assert "toolInvocations" in output
    assert (
        "tools=1 failed=0 pendingApprovals=1 approvalIds=approval_1 "
        "riskLevels=high idempotencyKeys=idem_safe_1"
    ) in output
    assert "https://private.example" not in output


def test_runs_cli_diagnose_table_summarizes_provider_runtime_metadata() -> None:
    class DiagnoseProviderRuntimeProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_1",
                        "status": "completed",
                        "metadata": {
                            "model_provider": "openai",
                            "selected_model": "gpt-5-mini",
                            "model_fallback_used": True,
                        },
                    },
                )
            return super().get_json(path, headers)

    probe = DiagnoseProviderRuntimeProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert (
        "status           true  200     completed provider=openai model=gpt-5-mini fallback=true\n"
    ) in stdout.getvalue()


def test_runs_cli_diagnose_table_summarizes_provider_fallback_metadata() -> None:
    class DiagnoseProviderFallbackProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_1",
                        "status": "completed",
                        "metadata": {
                            "providerFallback": {
                                "from_provider": "openai",
                                "from_model": "gpt-5-mini",
                                "to_provider": "anthropic",
                                "to_model": "claude-sonnet-5",
                                "reason": "provider_timeout",
                                "latency_ms": 250,
                                "cost_usd": 0.004,
                            },
                        },
                    },
                )
            return super().get_json(path, headers)

    probe = DiagnoseProviderFallbackProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert (
        "completed fallbackFrom=openai/gpt-5-mini "
        "fallbackTo=anthropic/claude-sonnet-5 fallbackReason=provider_timeout "
        "fallbackLatencyMs=250 fallbackCostUsd=0.004\n"
    ) in stdout.getvalue()


def test_runs_cli_diagnose_table_summarizes_token_usage_metadata() -> None:
    class DiagnoseTokenUsageProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_1",
                        "status": "completed",
                        "metadata": {
                            "tokenUsage": {
                                "inputTokens": 120,
                                "outputTokens": 35,
                                "totalTokens": 155,
                                "cachedTokens": 40,
                                "reasoningTokens": 7,
                            },
                        },
                    },
                )
            return super().get_json(path, headers)

    probe = DiagnoseTokenUsageProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert "completed tokens=155 input=120 output=35 cached=40 reasoning=7\n" in (stdout.getvalue())


def test_runs_cli_diagnose_table_summarizes_langchain_middleware_policy() -> None:
    class DiagnoseMiddlewareProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_1",
                        "status": "completed",
                        "metadata": {
                            "langchainMiddlewarePolicy": {
                                "status": "applied",
                                "source": "tenant_runtime_setting",
                                "policy": {
                                    "modelCallRunLimit": 3,
                                    "toolCallRunLimit": 2,
                                    "modelRetryMaxRetries": 1,
                                    "toolRetryMaxRetries": 2,
                                },
                            },
                            "langchainMiddlewareChain": {
                                "status": "applied",
                                "count": 2,
                                "middleware": ["ModelCallLimitMiddleware", "PIIMiddleware"],
                                "piiRuleCount": 1,
                                "hitlToolCount": 2,
                                "fallbackModelCount": 1,
                            },
                        },
                    },
                )
            return super().get_json(path, headers)

    probe = DiagnoseMiddlewareProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert (
        "completed middleware=applied middlewareSource=tenant_runtime_setting "
        "middlewareModelLimit=3 middlewareToolLimit=2 middlewareModelRetries=1 "
        "middlewareToolRetries=2 middlewareCount=2 middlewarePii=1 middlewareHitl=2 "
        "middlewareModels=1 middlewareChain=ModelCallLimitMiddleware,PIIMiddleware\n"
    ) in stdout.getvalue()


def test_runs_cli_diagnose_table_summarizes_tool_profile_budget_drops() -> None:
    class DiagnoseToolProfileProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_1":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_1",
                        "status": "completed",
                        "metadata": {
                            "resolvedToolProfileBudget": {
                                "source": "tenant_runtime_setting",
                                "maxTools": 2,
                                "configuredToolCount": 4,
                                "activeToolCount": 2,
                                "activeTools": ["Rag:hybrid_search", "Docs:lookup"],
                                "droppedToolCount": 2,
                                "dropped_tools": [
                                    {"name": "shell", "reason": "risk_level_not_allowed"},
                                    {"name": "browser", "reason": "max_tools_exceeded"},
                                ],
                            }
                        },
                    },
                )
            return super().get_json(path, headers)

    probe = DiagnoseToolProfileProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_1", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert exit_code == 0
    assert (
        "completed toolBudgetSource=tenant_runtime_setting toolBudgetMax=2 "
        "activeTools=2/4 droppedTools=2 "
        "dropReasons=max_tools_exceeded=1,risk_level_not_allowed=1 "
        "droppedToolSample=shell:risk_level_not_allowed,browser:max_tools_exceeded "
        "activeToolNames=Rag:hybrid_search,Docs:lookup\n"
    ) in stdout.getvalue()


def test_runs_cli_diagnose_failed_run_suggests_eval_promotion_next_action() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_failed"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["nextActions"] == [
        {
            "id": "promote-eval",
            "label": "Promote failed run into a source-controlled eval case",
            "evalCaseId": "case_run_failed",
            "sourceRunId": "run_failed",
            "caseFile": "promoted-case.json",
            "runFile": "promoted-run.json",
            "suiteFile": "tests/fixtures/agent-eval/regression-suite.json",
            "reportFile": "reports/langsmith-eval-sync-dry-run.json",
            "readinessReportArg": (
                "--readiness-report langsmith_eval_sync=reports/langsmith-eval-sync-dry-run.json"
            ),
            "requiredReadinessReports": ["langsmith_eval_sync"],
            "readinessReports": {
                "langsmith_eval_sync": "reports/langsmith-eval-sync-dry-run.json",
            },
            "evalTags": ["promoted-from-failed-run", "run-diagnostics"],
            "command": (
                "reactor-runs promote-eval run_failed --case-id case_run_failed "
                "--case-file promoted-case.json --run-file promoted-run.json "
                "--tag promoted-from-failed-run --tag run-diagnostics "
                "--apply-suite-file tests/fixtures/agent-eval/regression-suite.json "
                "--apply-dry-run --apply-require-source-run-id "
                "--apply-require-run-file --apply-require-context-diagnostics "
                "--apply-suite-summary "
                "--langsmith-dry-run-report-file reports/langsmith-eval-sync-dry-run.json "
                "--output table"
            ),
        }
    ]


def test_runs_cli_diagnose_failed_run_with_stream_events_suggests_replay() -> None:
    class FailedStreamProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_failed/stream-events":
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[{"sequence": 1, "event_type": "run.stream.error"}],
                )
            return super().get_json(path, headers)

    probe = FailedStreamProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_failed"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    actions = {action["id"]: action for action in payload["nextActions"]}
    assert actions["replay-stream"]["sourceRunId"] == "run_failed"
    assert actions["replay-stream"]["command"] == "reactor-runs replay run_failed --output table"
    assert "reactor-runs promote-eval run_failed" in actions["promote-eval"]["command"]


def test_runs_cli_diagnose_failed_run_with_checkpoint_suggests_fork_and_history() -> None:
    class FailedCheckpointProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            result = super().get_json(path, headers)
            if path == "/v1/runs/run_failed" and isinstance(result.body, dict):
                result.body["checkpointNs"] = "reactor"
                result.body["lastCheckpointId"] = "checkpoint_7"
            return result

    probe = FailedCheckpointProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_failed"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    actions = {action["id"]: action for action in payload["nextActions"]}
    assert actions["fork-checkpoint"]["sourceRunId"] == "run_failed"
    assert actions["fork-checkpoint"]["checkpointNs"] == "reactor"
    assert actions["fork-checkpoint"]["checkpointId"] == "checkpoint_7"
    assert actions["fork-checkpoint"]["command"] == (
        "reactor-runs fork run_failed --checkpoint-ns reactor "
        "--checkpoint-id checkpoint_7 --output table"
    )
    assert actions["inspect-state-history"]["sourceRunId"] == "run_failed"
    assert actions["inspect-state-history"]["checkpointNs"] == "reactor"
    assert actions["inspect-state-history"]["checkpointId"] == "checkpoint_7"
    assert actions["inspect-state-history"]["command"] == (
        "reactor-admin state-history run_failed --output table"
    )
    assert "reactor-runs promote-eval run_failed" in actions["promote-eval"]["command"]


def test_runs_cli_diagnose_failed_rag_candidate_run_uses_candidate_eval_lane() -> None:
    class CandidateFailedRunProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            result = super().get_json(path, headers)
            if path == "/v1/runs/run_failed" and isinstance(result.body, dict):
                metadata = cast(dict[str, object], result.body["metadata"])
                metadata["workflowTags"] = [
                    "collection:rag-ingestion-candidate",
                    "rag-candidate:c1",
                    "expected-citation:candidate-runbook.md",
                ]
            return result

    probe = CandidateFailedRunProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_failed"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    action = payload["nextActions"][0]
    assert action["evalCaseId"] == "case_rag_candidate_c1"
    assert action["sourceRunId"] == "run_failed"
    assert action["caseFile"] == "evals/cases/case_rag_candidate_c1.json"
    assert action["runFile"] == "evals/runs/run_failed.json"
    assert action["suiteFile"] == "evals/regression/rag-ingestion-candidate.json"
    assert action["datasetName"] == "reactor-rag-ingestion-candidate"
    assert (
        action["reportFile"]
        == "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
    )
    assert action["readinessReportArg"] == (
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report "
        "langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json"
    )
    assert action["requiredReadinessReports"] == ["hardening_suite", "langsmith_eval_sync"]
    assert action["readinessReports"] == {
        "hardening_suite": "reports/hardening-suite.json",
        "langsmith_eval_sync": (
            "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
        ),
    }
    assert action["evalTags"] == [
        "promoted-from-failed-run",
        "run-diagnostics",
        "collection:rag-ingestion-candidate",
        "rag-candidate:c1",
        "expected-citation:candidate-runbook.md",
    ]
    command = action["command"]
    assert "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1" in command
    assert "--tag expected-citation:candidate-runbook.md" in command
    assert "--apply-suite-file evals/regression/rag-ingestion-candidate.json" in command
    assert "--apply-dataset-name reactor-rag-ingestion-candidate" in command
    assert "--langsmith-dry-run-report-file artifacts/langsmith/" in command
    assert "--case-id case_rag_candidate_c1" in command
    assert "--case-file evals/cases/case_rag_candidate_c1.json" in command
    assert "--run-file evals/runs/run_failed.json" in command
    assert "rag-ingestion-candidate-case_rag_candidate_c1.json" in command


def test_runs_cli_diagnose_failed_documents_ask_run_requires_hardening_readiness() -> None:
    class DocumentsAskFailedRunProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            result = super().get_json(path, headers)
            if path == "/v1/runs/run_failed" and isinstance(result.body, dict):
                metadata = cast(dict[str, object], result.body["metadata"])
                metadata["workflowTags"] = [
                    "documents-ask",
                    "rag",
                    "grounding",
                    "expected-citation:runbook.md",
                ]
            return result

    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_failed"],
        http_probe=DocumentsAskFailedRunProbe(),
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    action = payload["nextActions"][0]
    assert action["suiteFile"] == "tests/fixtures/agent-eval/regression-suite.json"
    assert action["reportFile"] == "reports/langsmith-eval-sync-dry-run.json"
    assert action["readinessReportArg"] == (
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=reports/langsmith-eval-sync-dry-run.json"
    )
    assert action["requiredReadinessReports"] == ["hardening_suite", "langsmith_eval_sync"]
    assert action["readinessReports"] == {
        "hardening_suite": "reports/hardening-suite.json",
        "langsmith_eval_sync": "reports/langsmith-eval-sync-dry-run.json",
    }
    assert action["evalTags"] == [
        "promoted-from-failed-run",
        "run-diagnostics",
        "expected-citation:runbook.md",
        "documents-ask",
        "rag",
        "grounding",
    ]
    assert "--tag documents-ask" in action["command"]
    assert "--tag expected-citation:runbook.md" in action["command"]
    assert "--apply-dataset-name reactor-rag-ingestion-candidate" not in action["command"]


def test_runs_cli_diagnose_ignores_unslugged_rag_candidate_tag() -> None:
    class CandidateFailedRunProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            result = super().get_json(path, headers)
            if path == "/v1/runs/run_failed" and isinstance(result.body, dict):
                metadata = cast(dict[str, object], result.body["metadata"])
                metadata["tags"] = ["rag-candidate:bad/path"]
            return result

    probe = CandidateFailedRunProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_failed"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    command = payload["nextActions"][0]["command"]
    assert "--apply-suite-file evals/regression/rag-ingestion-candidate.json" not in command
    assert "--tag rag-candidate:bad/path" not in command
    assert "--case-id case_rag_candidate_bad_path" not in command
    assert "--case-id case_run_failed" in command


def test_runs_cli_diagnose_failed_run_infers_candidate_memory_lane_from_feedback_queue() -> None:
    class FeedbackQueueFailedRunProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            result = super().get_json(path, headers)
            if path == "/v1/runs/run_failed" and isinstance(result.body, dict):
                metadata = cast(dict[str, object], result.body["metadata"])
                metadata["feedbackReviewQueue"] = {
                    "caseIds": ["case-rag-candidate-c1"],
                    "workflowTagCounts": {
                        "collection:rag-ingestion-candidate": 1,
                        "memory": 1,
                    },
                }
            return result

    probe = FeedbackQueueFailedRunProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_failed"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    command = payload["nextActions"][0]["command"]
    assert "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1" in command
    assert "--tag memory" in command
    assert "--apply-suite-file evals/regression/rag-ingestion-candidate.json" in command
    assert "--apply-dataset-name reactor-rag-ingestion-candidate" in command
    assert "--case-id case_rag_candidate_c1" in command
    assert "rag-ingestion-candidate-case_rag_candidate_c1.json" in command


def test_runs_cli_diagnose_failed_run_preserves_grounding_feedback_queue_tag() -> None:
    class FeedbackQueueFailedRunProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            result = super().get_json(path, headers)
            if path == "/v1/runs/run_failed" and isinstance(result.body, dict):
                metadata = cast(dict[str, object], result.body["metadata"])
                metadata["feedbackReviewQueue"] = {
                    "caseIds": ["case_rag_grounding"],
                    "workflowTagCounts": {
                        "rag": 1,
                        "grounding": 1,
                    },
                }
            return result

    probe = FeedbackQueueFailedRunProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_failed"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    command = payload["nextActions"][0]["command"]
    assert "--tag rag --tag grounding" in command
    assert "--apply-suite-file tests/fixtures/agent-eval/regression-suite.json" in command


def test_runs_cli_diagnose_ignores_invalid_candidate_feedback_queue() -> None:
    class FeedbackQueueFailedRunProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            result = super().get_json(path, headers)
            if path == "/v1/runs/run_failed" and isinstance(result.body, dict):
                metadata = cast(dict[str, object], result.body["metadata"])
                metadata["feedbackReviewQueue"] = {
                    "caseIds": ["case-rag-candidate-bad/path"],
                    "workflowTagCounts": {
                        "collection:rag-ingestion-candidate": 1,
                        "rag-candidate:bad/path": 1,
                    },
                }
            return result

    probe = FeedbackQueueFailedRunProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_failed"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    command = payload["nextActions"][0]["command"]
    assert "--apply-suite-file evals/regression/rag-ingestion-candidate.json" not in command
    assert "--tag collection:rag-ingestion-candidate" not in command
    assert "--tag rag-candidate:bad/path" not in command
    assert "--case-id case_run_failed" in command


def test_runs_cli_diagnose_table_shows_eval_promotion_next_action() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_failed", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    output = stdout.getvalue()
    assert "nextAction.promote-eval" in output
    assert (
        "reactor-runs promote-eval run_failed --case-id case_run_failed "
        "--case-file promoted-case.json --run-file promoted-run.json "
        "--tag promoted-from-failed-run --tag run-diagnostics "
        "--apply-suite-file tests/fixtures/agent-eval/regression-suite.json "
        "--apply-dry-run --apply-require-source-run-id "
        "--apply-require-run-file --apply-require-context-diagnostics "
        "--apply-suite-summary "
        "--langsmith-dry-run-report-file reports/langsmith-eval-sync-dry-run.json "
        "--output table"
    ) in output
    assert "nextAction.promote-eval.evalCaseId" in output
    assert "case_run_failed" in output
    assert "nextAction.promote-eval.sourceRunId" in output
    assert "run_failed" in output
    assert "nextAction.promote-eval.readinessReportArg" in output
    assert "--readiness-report langsmith_eval_sync=reports/langsmith-eval-sync-dry-run.json" in (
        output
    )
    assert "nextAction.promote-eval.requiredReadinessReports" in output
    assert "langsmith_eval_sync" in output
    assert "nextAction.promote-eval.readinessReports.langsmith_eval_sync" in output


def test_runs_cli_diagnose_table_shows_rag_candidate_eval_artifacts() -> None:
    class CandidateFailedRunProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            result = super().get_json(path, headers)
            if path == "/v1/runs/run_failed" and isinstance(result.body, dict):
                metadata = cast(dict[str, object], result.body["metadata"])
                metadata["tags"] = ["collection:rag-ingestion-candidate", "rag-candidate:c1"]
            return result

    probe = CandidateFailedRunProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_failed", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    output = stdout.getvalue()
    assert "nextAction.promote-eval.caseFile" in output
    assert "evals/cases/case_rag_candidate_c1.json" in output
    assert "nextAction.promote-eval.runFile" in output
    assert "evals/runs/run_failed.json" in output
    assert "nextAction.promote-eval.suiteFile" in output
    assert "evals/regression/rag-ingestion-candidate.json" in output
    assert "nextAction.promote-eval.datasetName" in output
    assert "reactor-rag-ingestion-candidate" in output
    assert "nextAction.promote-eval.candidateTag" in output
    assert "rag-candidate:c1" in output
    assert "nextAction.promote-eval.reportFile" in output
    assert "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json" in output
    assert "nextAction.promote-eval.readinessReportArg" in output
    assert (
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report "
        "langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
    ) in output
    assert "nextAction.promote-eval.requiredReadinessReports" in output
    assert "hardening_suite,langsmith_eval_sync" in output
    assert "nextAction.promote-eval.readinessReports.hardening_suite" in output
    assert "reports/hardening-suite.json" in output
    assert "nextAction.promote-eval.readinessReports.langsmith_eval_sync" in output
    assert "nextAction.promote-eval.evalTags" in output
    assert "promoted-from-failed-run,run-diagnostics" in output


def test_runs_cli_diagnose_completed_checkpoint_run_suggests_fork_next_action() -> None:
    class CheckpointDiagnoseProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_checkpoint":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_checkpoint",
                        "status": "completed",
                        "threadId": "thread_1",
                        "checkpointNs": "reactor",
                        "lastCheckpointId": "checkpoint_1",
                        "response_text": "answer",
                    },
                )
            if path == "/v1/runs/run_checkpoint/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "sequence": 1,
                            "event_type": "run.stream.token",
                            "payload": {"graph_node": "model", "text": "answer"},
                        }
                    ],
                )
            if path == "/v1/runs/run_checkpoint/tool-invocations?limit=100":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(ok=True, status_code=200, body=[])
            return super().get_json(path, headers)

    probe = CheckpointDiagnoseProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_checkpoint"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["nextActions"] == [
        {
            "id": "replay-stream",
            "label": "Replay this run's persisted LangGraph stream events",
            "sourceRunId": "run_checkpoint",
            "threadId": "thread_1",
            "checkpointNs": "reactor",
            "checkpointId": "checkpoint_1",
            "command": "reactor-runs replay run_checkpoint --output table",
        },
        {
            "id": "fork-checkpoint",
            "label": "Fork this completed run from its latest LangGraph checkpoint",
            "sourceRunId": "run_checkpoint",
            "threadId": "thread_1",
            "checkpointNs": "reactor",
            "checkpointId": "checkpoint_1",
            "command": (
                "reactor-runs fork run_checkpoint --checkpoint-ns reactor "
                "--checkpoint-id checkpoint_1 --output table"
            ),
        },
        {
            "id": "inspect-state-history",
            "label": "Inspect this run's LangGraph checkpoint state history",
            "sourceRunId": "run_checkpoint",
            "threadId": "thread_1",
            "checkpointNs": "reactor",
            "checkpointId": "checkpoint_1",
            "command": "reactor-admin state-history run_checkpoint --output table",
        },
    ]


def test_runs_cli_diagnose_succeeded_checkpoint_run_suggests_completed_recovery_actions() -> None:
    class SucceededCheckpointProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_succeeded":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_succeeded",
                        "status": "succeeded",
                        "checkpointNs": "reactor",
                        "lastCheckpointId": "checkpoint_1",
                    },
                )
            if path == "/v1/runs/run_succeeded/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[{"sequence": 1, "event_type": "run.stream.completed"}],
                )
            if path == "/v1/runs/run_succeeded/tool-invocations?limit=100":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(ok=True, status_code=200, body=[])
            return super().get_json(path, headers)

    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_succeeded"],
        http_probe=SucceededCheckpointProbe(),
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    actions = {
        action["id"]: action["command"] for action in json.loads(stdout.getvalue())["nextActions"]
    }
    assert actions["replay-stream"] == "reactor-runs replay run_succeeded --output table"
    assert actions["fork-checkpoint"] == (
        "reactor-runs fork run_succeeded --checkpoint-ns reactor "
        "--checkpoint-id checkpoint_1 --output table"
    )
    assert actions["inspect-state-history"] == (
        "reactor-admin state-history run_succeeded --output table"
    )


def test_runs_cli_diagnose_table_shows_all_checkpoint_next_actions() -> None:
    class CheckpointDiagnoseProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            if path == "/v1/runs/run_checkpoint":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_checkpoint",
                        "status": "completed",
                        "threadId": "thread_1",
                        "checkpointNs": "reactor",
                        "lastCheckpointId": "checkpoint_1",
                    },
                )
            if path == "/v1/runs/run_checkpoint/stream-events":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body=[
                        {
                            "sequence": 1,
                            "event_type": "run.stream.token",
                            "payload": {"graph_node": "model", "text": "answer"},
                        }
                    ],
                )
            if path == "/v1/runs/run_checkpoint/tool-invocations?limit=100":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return RunCliHttpResult(ok=True, status_code=200, body=[])
            return super().get_json(path, headers)

    probe = CheckpointDiagnoseProbe()
    stdout = StringIO()

    exit_code = run_cli(
        ["--base-url", "http://reactor.local", "diagnose", "run_checkpoint", "--output", "table"],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    assert "reactor-runs replay run_checkpoint --output table" in stdout.getvalue()
    assert "nextAction.replay-stream.threadId" in stdout.getvalue()
    assert "nextAction.replay-stream.checkpointNs" in stdout.getvalue()
    assert "nextAction.replay-stream.checkpointId" in stdout.getvalue()
    assert (
        "reactor-runs fork run_checkpoint --checkpoint-ns reactor "
        "--checkpoint-id checkpoint_1 --output table"
    ) in stdout.getvalue()
    assert "nextAction.fork-checkpoint.threadId" in stdout.getvalue()
    assert "nextAction.inspect-state-history.threadId" in stdout.getvalue()
    assert "thread_1" in stdout.getvalue()
    assert "reactor-admin state-history run_checkpoint --output table" in stdout.getvalue()


def test_runs_cli_cancel_posts_reason_to_existing_cancel_api() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "cancel",
            "run_1",
            "--reason",
            "operator requested",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == {
        "run_id": "run_1",
        "status": "cancelled",
        "response": "Run cancelled.",
    }
    assert probe.calls[-1] == {
        "method": "POST",
        "path": "/v1/runs/run_1/cancel",
        "headers": {
            "Content-Type": "application/json",
            "X-Reactor-Tenant-Id": "tenant_1",
            "X-Reactor-User-Id": "operator_1",
        },
        "payload": {"reason": "operator requested"},
    }


def test_runs_cli_cancel_can_render_operator_table_output() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "cancel",
            "run_1",
            "--reason",
            "operator requested",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "FIELD               VALUE\n"
        "run_id              run_1\n"
        "status              cancelled\n"
        "response            Run cancelled.\n"
        "diagnoseAction      reactor-runs diagnose run_1 --output table\n"
        "stateHistoryAction  reactor-admin state-history run_1 --output table\n"
        "replayAction        reactor-runs replay run_1 --output table\n"
    )
    assert probe.calls[-1]["path"] == "/v1/runs/run_1/cancel"


def test_runs_cli_resume_posts_approval_decision_to_existing_resume_api() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "resume",
            "run_1",
            "--approval-id",
            "approval_1",
            "--reject",
            "--reason",
            "unsafe write",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == {
        "run_id": "run_1",
        "status": "completed",
        "response": "resumed answer",
    }
    assert probe.calls[-1] == {
        "method": "POST",
        "path": "/v1/runs/run_1/resume",
        "headers": {
            "Content-Type": "application/json",
            "X-Reactor-Tenant-Id": "tenant_1",
            "X-Reactor-User-Id": "operator_1",
        },
        "payload": {
            "approvalId": "approval_1",
            "approved": False,
            "reason": "unsafe write",
        },
    }


def test_runs_cli_resume_can_render_operator_table_output() -> None:
    class ResumeApprovalProbe(FakeRunsProbe):
        def post_json(
            self,
            path: str,
            headers: dict[str, str],
            payload: dict[str, object],
        ) -> RunCliHttpResult:
            result = super().post_json(path, headers, payload)
            if path == "/v1/runs/run_1/resume":
                assert isinstance(result.body, dict)
                result.body["approvalId"] = "approval_1"
                result.body["approved"] = True
                result.body["nextActions"] = [
                    {
                        "id": "diagnose-run",
                        "command": "reactor-runs diagnose run_1 --output table",
                    },
                    {
                        "id": "inspect-state-history",
                        "command": "reactor-admin state-history run_1 --output table",
                    },
                    {
                        "id": "replay-stream",
                        "command": "reactor-runs replay run_1 --output table",
                    },
                    {
                        "id": "fork-checkpoint",
                        "command": (
                            "reactor-runs fork run_1 --checkpoint-ns reactor "
                            "--checkpoint-id checkpoint_1 --output table"
                        ),
                    },
                ]
            return result

    probe = ResumeApprovalProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "resume",
            "run_1",
            "--approval-id",
            "approval_1",
            "--reason",
            "approved by operator",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "FIELD               VALUE\n"
        "run_id              run_1\n"
        "status              completed\n"
        "approval_id         approval_1\n"
        "approved            true\n"
        "response            resumed answer\n"
        "nextAction          reactor-runs diagnose run_1 --output table\n"
        "stateHistoryAction  reactor-admin state-history run_1 --output table\n"
        "replayAction        reactor-runs replay run_1 --output table\n"
        "forkAction          reactor-runs fork run_1 --checkpoint-ns reactor "
        "--checkpoint-id checkpoint_1 --output table\n"
    )
    assert probe.calls[-1]["path"] == "/v1/runs/run_1/resume"


def test_runs_cli_fork_posts_checkpoint_branch_request_to_existing_fork_api() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "fork",
            "run_1",
            "--message",
            "try a safer branch",
            "--thread-id",
            "thread_fork",
            "--checkpoint-ns",
            "fork_ns",
            "--checkpoint-id",
            "checkpoint_7",
            "--metadata-json",
            '{"experiment":"safer-tools"}',
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == {
        "run_id": "run_fork",
        "source_run_id": "run_1",
        "thread_id": "thread_fork",
        "checkpoint_ns": "fork_ns",
        "status": "completed",
        "response": "forked answer",
        "provenance": {"source": "checkpoint_fork"},
    }
    assert probe.calls[-1] == {
        "method": "POST",
        "path": "/v1/runs/run_1/fork",
        "headers": {
            "Content-Type": "application/json",
            "X-Reactor-Tenant-Id": "tenant_1",
            "X-Reactor-User-Id": "operator_1",
        },
        "payload": {
            "message": "try a safer branch",
            "threadId": "thread_fork",
            "checkpointNs": "fork_ns",
            "checkpointId": "checkpoint_7",
            "metadata": {"experiment": "safer-tools"},
        },
    }


def test_runs_cli_fork_can_render_operator_table_output() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "fork",
            "run_1",
            "--message",
            "try a safer branch",
            "--thread-id",
            "thread_fork",
            "--checkpoint-ns",
            "fork_ns",
            "--checkpoint-id",
            "checkpoint_7",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "FIELD               VALUE\n"
        "run_id              run_fork\n"
        "source_run_id       run_1\n"
        "thread_id           thread_fork\n"
        "checkpoint_ns       fork_ns\n"
        "status              completed\n"
        "provenance_source   checkpoint_fork\n"
        "response            forked answer\n"
        "nextAction          reactor-runs diagnose run_fork --output table\n"
        "stateHistoryAction  reactor-admin state-history run_fork --output table\n"
        "replayAction        reactor-runs replay run_fork --output table\n"
    )
    assert probe.calls[-1]["path"] == "/v1/runs/run_1/fork"


def test_runs_cli_fork_table_shows_checkpoint_provenance() -> None:
    class ForkProvenanceProbe(FakeRunsProbe):
        def post_json(
            self,
            path: str,
            headers: dict[str, str],
            payload: dict[str, object],
        ) -> RunCliHttpResult:
            if path == "/v1/runs/run_1/fork":
                self.calls.append(
                    {
                        "method": "POST",
                        "path": path,
                        "headers": headers,
                        "payload": payload,
                    }
                )
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "run_id": "run_fork",
                        "source_run_id": "run_1",
                        "thread_id": "thread_fork",
                        "checkpoint_ns": "fork_ns",
                        "status": "completed",
                        "provenance": {
                            "source": "checkpoint_fork",
                            "forked_from_checkpoint_id": "checkpoint_7",
                            "fork_target_thread_id": "thread_fork",
                            "fork_target_checkpoint_ns": "fork_ns",
                        },
                        "response": "forked answer",
                    },
                )
            return super().post_json(path, headers, payload)

    probe = ForkProvenanceProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "fork",
            "run_1",
            "--message",
            "try a safer branch",
            "--thread-id",
            "thread_fork",
            "--checkpoint-ns",
            "fork_ns",
            "--checkpoint-id",
            "checkpoint_7",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "FIELD                      VALUE\n"
        "run_id                     run_fork\n"
        "source_run_id              run_1\n"
        "thread_id                  thread_fork\n"
        "checkpoint_ns              fork_ns\n"
        "status                     completed\n"
        "provenance_source          checkpoint_fork\n"
        "forked_from_checkpoint_id  checkpoint_7\n"
        "fork_target_thread_id      thread_fork\n"
        "fork_target_checkpoint_ns  fork_ns\n"
        "response                   forked answer\n"
        "nextAction                 reactor-runs diagnose run_fork --output table\n"
        "stateHistoryAction         reactor-admin state-history run_fork --output table\n"
        "replayAction               reactor-runs replay run_fork --output table\n"
    )
    assert probe.calls[-1]["path"] == "/v1/runs/run_1/fork"


def test_runs_cli_fork_table_accepts_camel_case_checkpoint_response() -> None:
    class CamelCaseForkProbe(FakeRunsProbe):
        def post_json(
            self,
            path: str,
            headers: dict[str, str],
            payload: dict[str, object],
        ) -> RunCliHttpResult:
            if path == "/v1/runs/run_1/fork":
                self.calls.append(
                    {
                        "method": "POST",
                        "path": path,
                        "headers": headers,
                        "payload": payload,
                    }
                )
                return RunCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "runId": "run_fork",
                        "sourceRunId": "run_1",
                        "threadId": "thread_fork",
                        "checkpointNs": "fork_ns",
                        "status": "completed",
                        "provenance": {
                            "source": "checkpoint_fork",
                            "forkedFromCheckpointId": "checkpoint_7",
                            "forkTargetThreadId": "thread_fork",
                            "forkTargetCheckpointNs": "fork_ns",
                        },
                        "responseText": "forked answer",
                    },
                )
            return super().post_json(path, headers, payload)

    probe = CamelCaseForkProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "fork",
            "run_1",
            "--message",
            "try a safer branch",
            "--thread-id",
            "thread_fork",
            "--checkpoint-ns",
            "fork_ns",
            "--checkpoint-id",
            "checkpoint_7",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert "run_id                     run_fork\n" in stdout.getvalue()
    assert "source_run_id              run_1\n" in stdout.getvalue()
    assert "thread_id                  thread_fork\n" in stdout.getvalue()
    assert "checkpoint_ns              fork_ns\n" in stdout.getvalue()
    assert "forked_from_checkpoint_id  checkpoint_7\n" in stdout.getvalue()
    assert "fork_target_thread_id      thread_fork\n" in stdout.getvalue()
    assert "fork_target_checkpoint_ns  fork_ns\n" in stdout.getvalue()
    assert "response_text              forked answer\n" in stdout.getvalue()
    assert "nextAction                 reactor-runs diagnose run_fork --output table\n" in (
        stdout.getvalue()
    )


def test_runs_cli_fork_table_shows_diagnose_next_action() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "fork",
            "run_1",
            "--message",
            "try a safer branch",
            "--thread-id",
            "thread_fork",
            "--checkpoint-ns",
            "fork_ns",
            "--checkpoint-id",
            "checkpoint_7",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert (
        "nextAction          reactor-runs diagnose run_fork --output table\n" in stdout.getvalue()
    )
    assert (
        "stateHistoryAction  reactor-admin state-history run_fork --output table\n"
        in stdout.getvalue()
    )


def test_runs_cli_can_promote_run_to_eval_case() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--name",
            "Provider timeout regression",
            "--expected-answer",
            "provider outage",
            "--tag",
            "regression",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "FIELD           VALUE\n"
        "id              case_failed_provider\n"
        "sourceRunId     run_failed\n"
        "assertionCount  2\n"
        "minScore        1.0\n"
        "enabled         true\n"
        "nextAction      reactor-runs promote-eval run_failed --case-id case_failed_provider "
        "--case-file promoted-case.json --run-file promoted-run.json "
        "--apply-suite-file tests/fixtures/agent-eval/regression-suite.json "
        "--apply-dry-run --apply-require-source-run-id "
        "--apply-require-run-file --apply-require-context-diagnostics "
        "--apply-suite-summary "
        "--langsmith-dry-run-report-file reports/langsmith-eval-sync-dry-run.json "
        "--output table\n"
    )
    assert probe.calls[-1] == {
        "method": "POST",
        "path": "/v1/admin/agent-eval/cases/promote",
        "headers": {
            "Content-Type": "application/json",
            "X-Reactor-Tenant-Id": "tenant_1",
            "X-Reactor-User-Id": "operator_1",
        },
        "payload": {
            "runId": "run_failed",
            "id": "case_failed_provider",
            "name": "Provider timeout regression",
            "expectedAnswerContains": ["provider outage"],
            "tags": ["regression"],
        },
    }


def test_runs_cli_promote_eval_accepts_feedback_source_option() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "provider outage",
            "--tag",
            "feedback:fb_1",
            "--tag",
            "feedback-rating:thumbs_down",
            "--feedback-source",
            "slack_button",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["payload"] == {
        "runId": "run_failed",
        "id": "case_failed_provider",
        "expectedAnswerContains": ["provider outage"],
        "tags": [
            "feedback:fb_1",
            "feedback-rating:thumbs_down",
            "feedback-source:slack_button",
        ],
    }


def test_runs_cli_promote_eval_adds_expected_citation_tag_from_expected_answer() -> None:
    probe = FakeRunsProbe()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_rag_answer",
            "--case-id",
            "case_rag_answer",
            "--expected-answer",
            "[doc_1]",
            "--tag",
            "documents-ask",
            "--tag",
            "rag",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=StringIO(),
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["payload"] == {
        "runId": "run_rag_answer",
        "id": "case_rag_answer",
        "expectedAnswerContains": ["[doc_1]"],
        "tags": ["documents-ask", "rag", "expected-citation:doc_1"],
    }


def test_runs_cli_rejects_placeholder_expected_answer_marker() -> None:
    probe = FakeRunsProbe()
    stderr = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "[replace-with-source-id]",
        ],
        http_probe=probe,
        stdout=StringIO(),
        stderr=stderr,
        environ={},
    )

    assert exit_code == 2
    assert "placeholder citation marker" in stderr.getvalue()
    assert not any(call["method"] == "POST" for call in probe.calls)


def test_runs_cli_rejects_embedded_placeholder_expected_answer_marker() -> None:
    probe = FakeRunsProbe()
    stderr = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "Expected citation: [replace-with-source-id]",
        ],
        http_probe=probe,
        stdout=StringIO(),
        stderr=stderr,
        environ={},
    )

    assert exit_code == 2
    assert "placeholder citation marker" in stderr.getvalue()
    assert not any(call["method"] == "POST" for call in probe.calls)


def test_runs_cli_promote_eval_table_shows_suite_apply_next_action() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "provider outage",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert (
        "nextAction      reactor-runs promote-eval run_failed --case-id case_failed_provider "
        "--case-file promoted-case.json --run-file promoted-run.json "
        "--apply-suite-file tests/fixtures/agent-eval/regression-suite.json "
        "--apply-dry-run --apply-require-source-run-id "
        "--apply-require-run-file --apply-require-context-diagnostics "
        "--apply-suite-summary "
        "--langsmith-dry-run-report-file reports/langsmith-eval-sync-dry-run.json "
        "--output table\n"
    ) in stdout.getvalue()


def test_runs_cli_promote_eval_table_uses_candidate_artifact_paths() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_rag_candidate_c1",
            "--expected-answer",
            "provider outage",
            "--tag",
            "collection:rag-ingestion-candidate",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    promote_call = next(
        call
        for call in probe.calls
        if call["method"] == "POST" and call["path"] == "/v1/admin/agent-eval/cases/promote"
    )
    payload = cast(dict[str, object], promote_call["payload"])
    assert payload["tags"] == ["collection:rag-ingestion-candidate", "rag-candidate:c1"]
    assert (
        "nextAction      reactor-runs promote-eval run_failed "
        "--case-id case_rag_candidate_c1 "
        "--expected-answer 'provider outage' "
        "--tag regression --tag promoted-from-failed-run "
        "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 "
        "--case-file evals/cases/case_rag_candidate_c1.json "
        "--run-file evals/runs/run_failed.json "
        "--apply-suite-file evals/regression/rag-ingestion-candidate.json "
        "--apply-dataset-name reactor-rag-ingestion-candidate "
        "--apply-require-source-run-id "
        "--apply-require-run-file --apply-require-context-diagnostics "
        "--apply-suite-summary "
        "--langsmith-dry-run-report-file "
        "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json "
        "--output table\n"
    ) in stdout.getvalue()


def test_runs_cli_promote_eval_candidate_suite_adds_collection_workflow_tag(
    tmp_path: Path,
) -> None:
    probe = FakeRunsProbe()
    suite_file = tmp_path / "rag-ingestion-candidate.json"
    case_file = tmp_path / "case.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_rag_candidate_c1",
            "--expected-answer",
            "provider outage",
            "--case-file",
            str(case_file),
            "--apply-suite-file",
            str(suite_file),
            "--apply-dataset-name",
            "reactor-rag-ingestion-candidate",
            "--apply-dry-run",
        ],
        http_probe=probe,
        stdout=StringIO(),
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    promote_call = next(
        call
        for call in probe.calls
        if call["method"] == "POST" and call["path"] == "/v1/admin/agent-eval/cases/promote"
    )
    payload = cast(dict[str, object], promote_call["payload"])
    assert payload["tags"] == ["collection:rag-ingestion-candidate", "rag-candidate:c1"]


def test_runs_cli_promote_eval_can_send_quality_assertions() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--forbidden-answer",
            "raw traceback",
            "--expected-tool",
            "Provider:call",
            "--forbidden-tool",
            "Shell:exec",
            "--expected-exposed-tool",
            "Provider:call",
            "--forbidden-exposed-tool",
            "Shell:exec",
            "--max-tool-exposure-count",
            "2",
            "--min-score",
            "0.75",
            "--disabled",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["payload"] == {
        "runId": "run_failed",
        "id": "case_failed_provider",
        "forbiddenAnswerContains": ["raw traceback"],
        "expectedToolNames": ["Provider:call"],
        "forbiddenToolNames": ["Shell:exec"],
        "expectedExposedToolNames": ["Provider:call"],
        "forbiddenExposedToolNames": ["Shell:exec"],
        "maxToolExposureCount": 2,
        "minScore": 0.75,
        "enabled": False,
    }


def test_runs_cli_promote_eval_can_export_case_file(tmp_path: Path) -> None:
    case_file = tmp_path / "promoted-case.json"
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "provider outage",
            "--case-file",
            str(case_file),
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert json.loads(case_file.read_text(encoding="utf-8"))["id"] == "case_failed_provider"
    assert json.loads(stdout.getvalue())["sourceRunId"] == "run_failed"


def test_runs_cli_promote_eval_can_export_run_fixture_file(tmp_path: Path) -> None:
    run_file = tmp_path / "promoted-run.json"
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "provider outage",
            "--run-file",
            str(run_file),
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert json.loads(run_file.read_text(encoding="utf-8")) == {
        "runId": "run_failed",
        "evalCaseId": "case_failed_provider",
        "userInput": "Investigate provider outage",
        "agentType": "standard",
        "model": "test-model",
        "finalAnswer": "Provider failed safely.",
        "toolCalls": [
            {
                "step": 1,
                "toolName": "Provider:call",
                "arguments": {},
                "success": False,
            }
        ],
        "toolExposure": {"count": 1, "names": ["Provider:call"]},
        "retrievedChunks": [],
        "errors": ["provider_timeout"],
    }
    assert json.loads(stdout.getvalue())["sourceRunId"] == "run_failed"
    assert [call["path"] for call in probe.calls] == [
        "/v1/admin/agent-eval/cases/promote",
        "/v1/runs/run_failed",
        "/v1/runs/run_failed/tool-invocations?limit=100",
    ]


def test_promoted_eval_run_fixture_preserves_context_manifest_diagnostics() -> None:
    class ContextDiagnosticsProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            result = super().get_json(path, headers)
            if path == "/v1/runs/run_failed" and isinstance(result.body, dict):
                result.body["metadata"] = {
                    **cast(dict[str, object], result.body["metadata"]),
                    "contextManifestDiagnostics": {
                        "memoryStatusCounts": {"active": 2, "tombstoned": 1},
                        "skippedMemoryStatusCounts": {"tombstoned": 1},
                    },
                }
            return result

    result = promoted_eval_run_fixture(
        "run_failed",
        {"id": "case_failed_provider", "userInput": "Investigate provider outage"},
        probe=ContextDiagnosticsProbe(),
        headers={},
    )

    assert result.ok is True
    assert isinstance(result.body, dict)
    assert result.body["contextManifestDiagnostics"] == {
        "memoryStatusCounts": {"active": 2, "tombstoned": 1},
        "skippedMemoryStatusCounts": {"tombstoned": 1},
    }


def test_promoted_eval_run_fixture_derives_context_manifest_diagnostics() -> None:
    class ContextManifestProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            result = super().get_json(path, headers)
            if path == "/v1/runs/run_failed" and isinstance(result.body, dict):
                result.body["metadata"] = {
                    **cast(dict[str, object], result.body["metadata"]),
                    "contextManifest": {
                        "sections": [
                            {
                                "name": "rag_context",
                                "metadata": {
                                    "ragGroundingPolicy": {
                                        "citationTracking": "required",
                                        "uncitedChunksTracked": True,
                                        "aclEvidence": "acl_hash_only",
                                        "rawAclMetadataVisible": False,
                                    },
                                    "citation_count": 1,
                                    "chunk_count": 1,
                                    "cited_chunk_count": 1,
                                    "uncited_chunk_count": 0,
                                    "citations": [
                                        {
                                            "citation_id": "doc_1",
                                            "source_uri": "kb://rollback",
                                            "content_hash": "hash_doc_1",
                                        }
                                    ],
                                },
                                "content_checksum": (
                                    "sha256:"
                                    "0123456789abcdef0123456789abcdef"
                                    "0123456789abcdef0123456789abcdef"
                                ),
                            }
                        ]
                    },
                }
            return result

    result = promoted_eval_run_fixture(
        "run_failed",
        {"id": "case_failed_provider", "userInput": "Investigate provider outage"},
        probe=ContextManifestProbe(),
        headers={},
    )

    assert result.ok is True
    assert isinstance(result.body, dict)
    diagnostics = cast(dict[str, object], result.body["contextManifestDiagnostics"])
    assert diagnostics["ok"] is True
    assert diagnostics["status"] == "passed"
    assert diagnostics["citationCount"] == 1
    assert diagnostics["chunkCount"] == 1
    assert diagnostics["citedChunkCount"] == 1


def test_runs_cli_promote_eval_can_apply_exported_case_and_run_to_suite(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "provider outage",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--apply-suite-file",
            str(suite_file),
            "--apply-require-run-file",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["promotedCase"]["id"] == "case_failed_provider"
    assert payload["suiteApply"]["status"] == "added"
    assert payload["suiteApply"]["runStatus"] == "added"
    suite = json.loads(suite_file.read_text(encoding="utf-8"))
    assert [case["id"] for case in suite["cases"]] == ["case_failed_provider"]
    assert [run["runId"] for run in suite["runs"]] == ["run_failed"]


def test_runs_cli_promote_eval_apply_derives_required_context_diagnostics(
    tmp_path: Path,
) -> None:
    class ContextManifestProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            result = super().get_json(path, headers)
            if path == "/v1/runs/run_failed" and isinstance(result.body, dict):
                result.body["metadata"] = {
                    **cast(dict[str, object], result.body["metadata"]),
                    "contextManifest": {
                        "sections": [
                            {
                                "name": "rag_context",
                                "metadata": {
                                    "ragGroundingPolicy": {
                                        "citationTracking": "required",
                                        "uncitedChunksTracked": True,
                                        "aclEvidence": "acl_hash_only",
                                        "rawAclMetadataVisible": False,
                                    },
                                    "citation_count": 1,
                                    "chunk_count": 1,
                                    "cited_chunk_count": 1,
                                    "uncited_chunk_count": 0,
                                    "citations": [
                                        {
                                            "citation_id": "doc_1",
                                            "source_uri": "kb://rollback",
                                            "content_hash": "hash_doc_1",
                                        }
                                    ],
                                },
                                "content_checksum": (
                                    "sha256:"
                                    "0123456789abcdef0123456789abcdef"
                                    "0123456789abcdef0123456789abcdef"
                                ),
                            }
                        ]
                    },
                }
            return result

    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "Provider failed safely.",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--apply-suite-file",
            str(suite_file),
            "--apply-require-run-file",
            "--apply-require-context-diagnostics",
        ],
        http_probe=ContextManifestProbe(),
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["suiteApply"]["contextManifestDiagnosticsPresent"] is True
    suite = json.loads(suite_file.read_text(encoding="utf-8"))
    diagnostics = suite["runs"][0]["contextManifestDiagnostics"]
    assert diagnostics["ok"] is True
    assert diagnostics["status"] == "passed"
    assert diagnostics["citationCount"] == 1


def test_runs_cli_promote_eval_apply_can_render_operator_table_output(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "provider outage",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--apply-suite-file",
            str(suite_file),
            "--apply-require-run-file",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    rows = dict(line.split(maxsplit=1) for line in stdout.getvalue().splitlines()[1:])
    assert rows["id"] == "case_failed_provider"
    assert rows["sourceRunId"] == "run_failed"
    assert rows["assertionCount"] == "2"
    assert rows["minScore"] == "1.0"
    assert rows["enabled"] == "true"
    assert rows["suiteStatus"] == "added"
    assert rows["suiteCaseCount"] == "1"
    assert rows["runStatus"] == "added"
    assert rows["runId"] == "run_failed"
    assert rows["runCount"] == "1"
    assert rows["suitePersistCommand"] == (
        f"reactor-runs promote-eval run_failed --case-id case_failed_provider "
        f"--case-file {case_file} --run-file {run_file} "
        f"--apply-suite-file {suite_file} --apply-require-run-file --output table"
    )


def test_runs_cli_promote_eval_apply_can_write_langsmith_dry_run_report(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    langsmith_report_file = tmp_path / "langsmith-dry-run.json"
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_rag_candidate_grounded_citation",
            "--expected-answer",
            "provider outage",
            "--tag",
            "collection:rag-ingestion-candidate",
            "--tag",
            "rag-candidate:grounded_citation",
            "--tag",
            "feedback-rating:thumbs_down",
            "--tag",
            "feedback-source:slack_button",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--apply-suite-file",
            str(suite_file),
            "--apply-require-run-file",
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
            "--feedback-review-status",
            "done",
            "--feedback-review-tag",
            "promoted",
            "--feedback-review-tag",
            "langsmith",
            "--feedback-review-note",
            (
                "Promoted to regression eval and reviewed in hardening/LangSmith. "
                "Required readiness reports: hardening_suite, langsmith_eval_sync."
            ),
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    langsmith = payload["suiteApply"]["langsmithDryRun"]
    assert langsmith["status"] == "skipped"
    assert langsmith["datasetName"] == "reactor-regression"
    assert langsmith["caseIds"] == ["case_rag_candidate_grounded_citation"]
    assert langsmith["metadataCaseIds"] == ["case_rag_candidate_grounded_citation"]
    assert langsmith["sourceRunIds"] == ["run_failed"]
    assert langsmith["caseSourceRunIds"] == {"case_rag_candidate_grounded_citation": "run_failed"}
    assert langsmith["caseFile"] == str(case_file)
    assert langsmith["runFile"] == str(run_file)
    assert langsmith["splitCounts"] == {"regression": 1}
    assert langsmith["sourceSuite"] == str(suite_file)
    assert langsmith["gradedRuns"] == 1
    assert langsmith["missingRunCases"] == 0
    assert langsmith["deterministicEvalFailedCases"] == 1
    assert langsmith["deterministicEvalMissingExpected"] == ["provider outage"]
    assert langsmith["releaseGate"] == {
        "reason": "dry_run_only",
        "requiredReport": "langsmith_eval_sync",
        "remediation": [
            "run_reactor_langsmith_eval_sync_without_dry_run",
            "include_passed_langsmith_eval_sync_report_in_release_readiness",
        ],
        "status": "blocked",
    }
    assert langsmith["liveSyncCommand"] == (
        f"uv run reactor-langsmith-eval-sync --suite-file {suite_file} "
        f"--dataset-name reactor-regression --report-file {langsmith_report_file} "
        "--feedback-review-status done --feedback-review-tag promoted "
        "--feedback-review-tag langsmith --feedback-review-note "
        "'Promoted to regression eval and reviewed in hardening/LangSmith. "
        "Required readiness reports: hardening_suite, langsmith_eval_sync.' "
        "--required-readiness-report langsmith_eval_sync "
        f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
    )
    assert langsmith["persistCommand"] == (
        f"reactor-runs promote-eval run_failed --case-id case_rag_candidate_grounded_citation "
        f"--case-file {case_file} --run-file {run_file} "
        f"--apply-suite-file {suite_file} "
        f"--apply-require-run-file "
        f"--langsmith-dry-run-report-file {langsmith_report_file} "
        "--feedback-review-status done "
        "--feedback-review-tag promoted "
        "--feedback-review-tag langsmith "
        "--feedback-review-note 'Promoted to regression eval and reviewed in hardening/LangSmith. "
        "Required readiness reports: hardening_suite, langsmith_eval_sync.' "
        "--output table"
    )
    assert langsmith["feedbackReviewQueue"]["reviewStatus"] == "done"
    assert langsmith["feedbackReviewQueue"]["reviewTags"] == ["promoted", "langsmith"]
    assert langsmith["feedbackReviewQueue"]["reviewNote"] == (
        "Promoted to regression eval and reviewed in hardening/LangSmith. "
        "Required readiness reports: hardening_suite, langsmith_eval_sync."
    )
    assert langsmith["requiredReadinessReports"] == ["langsmith_eval_sync"]
    assert langsmith["readinessReports"] == {"langsmith_eval_sync": str(langsmith_report_file)}
    assert langsmith["reportFile"] == str(langsmith_report_file)
    expected_readiness_command = release_readiness_command_for_reports(
        required_reports=["langsmith_eval_sync"],
        report_files={"langsmith_eval_sync": str(langsmith_report_file)},
    )
    actions = {action["id"]: action for action in langsmith["nextActions"]}
    assert actions["preflight-langsmith"]["command"] == (
        f"uv run reactor-langsmith-eval-sync --suite-file {suite_file} "
        f"--dataset-name reactor-regression --report-file {langsmith_report_file} "
        "--feedback-review-status done --feedback-review-tag promoted "
        "--feedback-review-tag langsmith --feedback-review-note "
        "'Promoted to regression eval and reviewed in hardening/LangSmith. "
        "Required readiness reports: hardening_suite, langsmith_eval_sync.' "
        "--required-readiness-report langsmith_eval_sync "
        f"--readiness-report langsmith_eval_sync={langsmith_report_file} "
        "--preflight-only --output table"
    )
    assert actions["preflight-langsmith"]["releaseReadinessCommand"] == expected_readiness_command
    assert actions["sync-langsmith"]["command"] == (
        f"uv run reactor-langsmith-eval-sync --suite-file {suite_file} "
        f"--dataset-name reactor-regression --report-file {langsmith_report_file} "
        "--feedback-review-status done --feedback-review-tag promoted "
        "--feedback-review-tag langsmith --feedback-review-note "
        "'Promoted to regression eval and reviewed in hardening/LangSmith. "
        "Required readiness reports: hardening_suite, langsmith_eval_sync.' "
        "--required-readiness-report langsmith_eval_sync "
        f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
    )
    assert actions["sync-langsmith"]["releaseReadinessCommand"] == expected_readiness_command
    assert actions["refresh-release-readiness"]["readinessReportArg"] == (
        f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
    )
    langsmith_report = json.loads(langsmith_report_file.read_text(encoding="utf-8"))
    assert langsmith_report["status"] == "skipped"
    assert langsmith_report["caseIds"] == ["case_rag_candidate_grounded_citation"]
    assert langsmith_report["feedbackReviewQueue"]["reviewStatus"] == "done"


def test_runs_cli_promote_eval_apply_dry_run_preserves_grounding_citations(
    tmp_path: Path,
) -> None:
    class GroundedRunProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            result = super().get_json(path, headers)
            if path != "/v1/runs/run_failed" or not isinstance(result.body, dict):
                return result
            result.body["metadata"] = {
                **cast(dict[str, object], result.body["metadata"]),
                "retrievedChunks": [
                    {
                        "documentId": "tenant-vectorstore-release",
                        "source": "runbook.md",
                        "title": "RAG Runbook",
                        "score": 0.91,
                        "cited": True,
                    },
                    {
                        "documentId": "tenant-vectorstore-release",
                        "source": "runbook.md",
                        "title": "RAG Runbook",
                        "score": 0.82,
                        "cited": False,
                    },
                ],
            }
            return result

    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    langsmith_report_file = tmp_path / "langsmith-dry-run.json"
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "provider outage",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--apply-suite-file",
            str(suite_file),
            "--apply-require-run-file",
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
            "--output",
            "table",
        ],
        http_probe=GroundedRunProbe(),
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    rows = dict(line.split(maxsplit=1) for line in stdout.getvalue().splitlines()[1:])
    assert rows["langsmithGroundingCases"] == "1"
    assert rows["langsmithGroundingCited"] == "1"
    assert rows["langsmithGroundingUncited"] == "1"
    assert rows["langsmithGroundingDocuments"] == "tenant-vectorstore-release"

    langsmith_report = json.loads(langsmith_report_file.read_text(encoding="utf-8"))
    trace_grading = langsmith_report["evidence"]["traceGrading"]
    assert trace_grading["gradedRuns"] == 1
    [grade] = trace_grading["grades"]
    grounding = next(
        dimension for dimension in grade["dimensions"] if dimension["name"] == "grounding"
    )
    assert grounding["name"] == "grounding"
    assert grounding["evidence"]["cited"] == 1
    assert grounding["evidence"]["uncited"] == 1


def test_runs_cli_promote_eval_preserves_chunk_citation_ids_in_grounding(
    tmp_path: Path,
) -> None:
    class ChunkCitationRunProbe(FakeRunsProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            result = super().get_json(path, headers)
            if path != "/v1/runs/run_failed" or not isinstance(result.body, dict):
                return result
            result.body["metadata"] = {
                **cast(dict[str, object], result.body["metadata"]),
                "retrievedChunks": [
                    {
                        "documentId": "tenant-vectorstore-release",
                        "citationId": "tenant-vectorstore-release:0",
                        "source": "runbook.md",
                        "title": "RAG Runbook",
                        "score": 0.91,
                        "cited": True,
                    }
                ],
            }
            result.body["response_text"] = "Provider failed safely. [tenant-vectorstore-release:0]"
            return result

    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    langsmith_report_file = tmp_path / "langsmith-dry-run.json"
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_documents_ask_chunk_citation",
            "--expected-answer",
            "[tenant-vectorstore-release:0]",
            "--tag",
            "documents-ask",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--apply-suite-file",
            str(suite_file),
            "--apply-require-run-file",
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
        ],
        http_probe=ChunkCitationRunProbe(),
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    run_payload = json.loads(run_file.read_text(encoding="utf-8"))
    assert run_payload["retrievedChunks"] == [
        {
            "documentId": "tenant-vectorstore-release",
            "citationId": "tenant-vectorstore-release:0",
            "source": "runbook.md",
            "title": "RAG Runbook",
            "score": 0.91,
            "cited": True,
        }
    ]
    langsmith_report = json.loads(langsmith_report_file.read_text(encoding="utf-8"))
    trace_grading = langsmith_report["evidence"]["traceGrading"]
    [grade] = trace_grading["grades"]
    grounding = next(
        dimension for dimension in grade["dimensions"] if dimension["name"] == "grounding"
    )
    assert grounding["evidence"]["citedDocuments"] == ["tenant-vectorstore-release:0"]


def test_runs_cli_promote_eval_apply_dry_run_langsmith_report_includes_pending_run(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    original_suite: dict[str, object] = {"cases": [], "runs": []}
    suite_file.write_text(json.dumps(original_suite) + "\n", encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    langsmith_report_file = tmp_path / "langsmith-dry-run.json"
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "provider outage",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--apply-suite-file",
            str(suite_file),
            "--apply-require-run-file",
            "--apply-dry-run",
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["suiteApply"]["status"] == "would_add"
    assert payload["suiteApply"]["runStatus"] == "would_add"
    assert payload["suiteApply"]["langsmithDryRun"]["caseIds"] == ["case_failed_provider"]
    assert payload["suiteApply"]["langsmithDryRun"]["gradedRuns"] == 1
    langsmith_report = json.loads(langsmith_report_file.read_text(encoding="utf-8"))
    assert langsmith_report["caseIds"] == ["case_failed_provider"]
    assert langsmith_report["evidence"]["traceGrading"]["gradedRuns"] == 1
    assert json.loads(suite_file.read_text(encoding="utf-8")) == original_suite


def test_runs_cli_promote_eval_rejects_rag_candidate_apply_with_non_candidate_case_id(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "rag-ingestion-candidate.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    stderr = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "provider outage",
            "--case-file",
            str(case_file),
            "--tag",
            "collection:rag-ingestion-candidate",
            "--apply-suite-file",
            str(suite_file),
            "--apply-dataset-name",
            "reactor-rag-ingestion-candidate",
        ],
        http_probe=FakeRunsProbe(),
        stdout=StringIO(),
        stderr=stderr,
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 2
    assert "RAG ingestion candidate suite apply requires --case-id case_rag_candidate_*" in (
        stderr.getvalue()
    )
    assert not case_file.exists()


def test_runs_cli_promote_eval_rejects_rag_candidate_tag_with_non_candidate_case_id() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "provider outage",
            "--tag",
            "collection:rag-ingestion-candidate",
            "--tag",
            "citation-failure",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=stderr,
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "RAG ingestion candidate promotion requires --case-id case_rag_candidate_*" in (
        stderr.getvalue()
    )


def test_runs_cli_promote_eval_rejects_rag_candidate_case_id_without_slug() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_rag_candidate_",
            "--expected-answer",
            "provider outage",
            "--tag",
            "collection:rag-ingestion-candidate",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=stderr,
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "RAG ingestion candidate promotion requires --case-id case_rag_candidate_*" in (
        stderr.getvalue()
    )


def test_runs_cli_promote_eval_rejects_unslugged_rag_candidate_case_id() -> None:
    probe = FakeRunsProbe()
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_rag_candidate_bad/path",
            "--expected-answer",
            "provider outage",
            "--tag",
            "collection:rag-ingestion-candidate",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=stderr,
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "RAG ingestion candidate promotion requires slugged --case-id" in stderr.getvalue()


def test_runs_cli_promote_eval_apply_table_includes_langsmith_dry_run_summary(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    langsmith_report_file = tmp_path / "langsmith-dry-run.json"
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "provider outage",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--apply-suite-file",
            str(suite_file),
            "--apply-require-run-file",
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    rows = dict(line.split(maxsplit=1) for line in stdout.getvalue().splitlines()[1:])
    assert rows["langsmithStatus"] == "skipped"
    assert rows["langsmithDataset"] == "reactor-regression"
    assert rows["langsmithExamples"] == "1"
    assert rows["langsmithCaseIds"] == "case_failed_provider"
    assert rows["langsmithMetadataIds"] == "case_failed_provider"
    assert rows["langsmithSourceRunIds"] == "1"
    assert rows["langsmithCaseSourceRunMappings"] == "1"
    assert rows["langsmithSplitCounts"] == "regression=1"
    assert rows["langsmithSourceSuite"] == str(suite_file)
    assert rows["langsmithGradedRuns"] == "1"
    assert rows["langsmithMissingRun"] == "0"
    assert rows["langsmithReleaseGate"] == "blocked"
    assert rows["langsmithGateReason"] == "dry_run_only"
    assert rows["langsmithRequiredReport"] == "langsmith_eval_sync"
    assert rows["langsmithReleaseNext"] == "run_reactor_langsmith_eval_sync_without_dry_run"
    assert rows["langsmithReleasePlan"] == (
        "run_reactor_langsmith_eval_sync_without_dry_run | "
        "include_passed_langsmith_eval_sync_report_in_release_readiness"
    )
    assert rows["langsmithSyncCommand"] == (
        f"uv run reactor-langsmith-eval-sync --suite-file {suite_file} "
        f"--dataset-name reactor-regression --dry-run --report-file {langsmith_report_file}"
    )
    assert rows["langsmithLiveSyncCommand"] == (
        f"uv run reactor-langsmith-eval-sync --suite-file {suite_file} "
        f"--dataset-name reactor-regression --report-file {langsmith_report_file} "
        "--required-readiness-report langsmith_eval_sync "
        f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
    )
    assert rows["suitePersistCommand"] == (
        f"reactor-runs promote-eval run_failed --case-id case_failed_provider "
        f"--case-file {case_file} --run-file {run_file} "
        f"--apply-suite-file {suite_file} "
        f"--apply-require-run-file "
        f"--langsmith-dry-run-report-file {langsmith_report_file} --output table"
    )
    assert rows["langsmithPersistCommand"] == rows["suitePersistCommand"]
    assert rows["langsmithSummaryCommand"] == (
        f"reactor-agent-eval-apply --suite-file {suite_file} "
        "--dataset-name reactor-regression --summary "
        f"--langsmith-dry-run-report-file {langsmith_report_file} --output table"
    )
    assert rows["langsmithReadinessCommand"] == (
        "uv run reactor-replatform-readiness --output "
        "reports/release/replatform-readiness.local.json "
        "--allow-deferred-release-gates "
        "&& uv run reactor-release-smoke-plan "
        "--readiness reports/release/replatform-readiness.local.json "
        "--output reports/release/release-smoke-plan.local.json "
        "&& uv run reactor-release-smoke-run "
        "--plan reports/release/release-smoke-plan.local.json "
        "--preflight-file reports/release/release-smoke-preflight.local.json "
        "--env-file reports/release/release-smoke-preflight.local.env "
        "--report-file reports/release-smoke-run.json "
        "--evidence-output reports/release-evidence.json "
        "--verified-at $(date -u +%Y-%m-%dT%H:%M:%SZ) "
        "--latest-tag $(git describe --tags --abbrev=0) "
        "--readiness-output reports/release-readiness.json "
        "--required-readiness-report langsmith_eval_sync "
        f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
    )
    assert rows["langsmithReportFile"] == str(langsmith_report_file)
    assert (
        rows["langsmithNextActionIds"]
        == "preflight-langsmith,sync-langsmith,refresh-release-readiness"
    )
    assert rows["langsmithNextAction.preflight-langsmith"] == (
        f"uv run reactor-langsmith-eval-sync --suite-file {suite_file} "
        f"--dataset-name reactor-regression --report-file {langsmith_report_file} "
        "--required-readiness-report langsmith_eval_sync "
        f"--readiness-report langsmith_eval_sync={langsmith_report_file} "
        "--preflight-only --output table"
    )
    assert (
        rows["langsmithNextAction.preflight-langsmith.releaseReadinessCommand"]
        == rows["langsmithReadinessCommand"]
    )
    assert rows["langsmithNextAction.sync-langsmith"] == (
        f"uv run reactor-langsmith-eval-sync --suite-file {suite_file} "
        f"--dataset-name reactor-regression --report-file {langsmith_report_file} "
        "--required-readiness-report langsmith_eval_sync "
        f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
    )
    assert (
        rows["langsmithNextAction.sync-langsmith.releaseReadinessCommand"]
        == rows["langsmithReadinessCommand"]
    )
    assert rows["langsmithNextAction.refresh-release-readiness.requiredReadinessReports"] == (
        "langsmith_eval_sync"
    )
    assert rows[
        "langsmithNextAction.refresh-release-readiness.readinessReports.langsmith_eval_sync"
    ] == str(langsmith_report_file)
    assert (
        rows["langsmithNextAction.refresh-release-readiness.remediationCommand"]
        == (rows["langsmithReadinessCommand"])
    )
    assert rows["langsmithNextAction.refresh-release-readiness.readinessReportArg"] == (
        f"--readiness-report langsmith_eval_sync={langsmith_report_file}"
    )


def test_runs_cli_promote_eval_apply_table_suggests_feedback_review_queue(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    langsmith_report_file = tmp_path / "langsmith-dry-run.json"
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "provider outage",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--tag",
            "feedback:fb_1",
            "--tag",
            "feedback-rating:thumbs_down",
            "--feedback-source",
            "slack_button",
            "--apply-suite-file",
            str(suite_file),
            "--apply-require-run-file",
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    rows = dict(line.split(maxsplit=1) for line in stdout.getvalue().splitlines()[1:])
    assert rows["langsmithFeedbackIdList"] == "fb_1"
    assert rows["langsmithFeedbackReviewIds"] == "fb_1"
    assert rows["langsmithFeedbackRatings"] == "thumbs_down=1"
    assert rows["langsmithFeedbackSources"] == "slack_button=1"
    assert rows["langsmithFeedbackReviewAction"] == (
        "reactor-admin feedback --feedback-id fb_1 --output table"
    )


def test_runs_cli_promote_eval_apply_table_shows_rating_only_feedback_queue(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    langsmith_report_file = tmp_path / "langsmith-dry-run.json"
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "provider outage",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--tag",
            "feedback-rating:thumbs_down",
            "--tag",
            "feedback-source:slack_button",
            "--tag",
            "run-diagnostics",
            "--apply-suite-file",
            str(suite_file),
            "--apply-require-run-file",
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    rows = dict(line.split(maxsplit=1) for line in stdout.getvalue().splitlines()[1:])
    assert rows["langsmithFeedbackQueueCases"] == "1"
    assert rows["langsmithFeedbackQueueRatings"] == "thumbs_down=1"
    assert rows["langsmithFeedbackQueueSources"] == "slack_button=1"
    assert rows["langsmithFeedbackQueueWorkflows"] == (
        "promoted-from-failed-run=1,run-diagnostics=1"
    )
    assert rows["langsmithFeedbackQueueReviewAction"] == (
        "reactor-admin feedback --rating thumbs_down --source slack_button "
        "--review-status inbox "
        "--case-id case_failed_provider "
        "--tag promoted-from-failed-run "
        "--limit 10 --output table"
    )


def test_runs_cli_promote_eval_apply_table_shows_candidate_feedback_queue_action(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    langsmith_report_file = tmp_path / "langsmith-dry-run.json"
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_rag_candidate_c1",
            "--expected-answer",
            "provider outage",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--tag",
            "feedback-rating:thumbs_down",
            "--feedback-source",
            "slack_button",
            "--tag",
            "collection:rag-ingestion-candidate",
            "--tag",
            "rag",
            "--apply-suite-file",
            str(suite_file),
            "--apply-dataset-name",
            "reactor-rag-ingestion-candidate",
            "--apply-require-run-file",
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    rows = dict(line.split(maxsplit=1) for line in stdout.getvalue().splitlines()[1:])
    assert rows["langsmithFeedbackQueueReviewAction"] == (
        "reactor-admin feedback --rating thumbs_down "
        "--source slack_button "
        "--review-status inbox "
        "--case-id case_rag_candidate_c1 "
        "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 "
        "--limit 10 --output table"
    )
    assert rows["langsmithFeedbackQueueExportAction"] == (
        "reactor-admin feedback-export --rating thumbs_down "
        "--source slack_button "
        "--review-status inbox "
        "--case-id case_rag_candidate_c1 "
        "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 "
        "--limit 10 --output json"
    )
    assert rows["langsmithFeedbackQueueBulkReviewAction"] == (
        "reactor-admin feedback-bulk-review --candidate-tag rag-candidate:c1 "
        "--source slack_button --status done --tag promoted --tag langsmith "
        "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 "
        "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
        "--output table"
    )
    assert rows["langsmithFeedbackQueueCandidateAction"] == (
        "reactor-admin rag-candidates --status INGESTED "
        "--tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:c1 --limit 10 --output table"
    )


def test_runs_cli_promote_eval_candidate_langsmith_report_requires_hardening_report(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    langsmith_report_file = tmp_path / "langsmith-dry-run.json"
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_rag_candidate_c1",
            "--expected-answer",
            "provider outage",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--tag",
            "feedback-rating:thumbs_down",
            "--tag",
            "collection:rag-ingestion-candidate",
            "--tag",
            "rag",
            "--apply-suite-file",
            str(suite_file),
            "--apply-dataset-name",
            "reactor-rag-ingestion-candidate",
            "--apply-require-run-file",
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    langsmith = payload["suiteApply"]["langsmithDryRun"]
    assert langsmith["requiredReadinessReports"] == [
        "hardening_suite",
        "langsmith_eval_sync",
    ]
    assert langsmith["readinessReports"] == {
        "hardening_suite": "reports/hardening-suite.json",
        "langsmith_eval_sync": str(langsmith_report_file),
    }
    assert "--required-readiness-report hardening_suite" in langsmith["readinessCommand"]
    assert (
        "--readiness-report hardening_suite=reports/hardening-suite.json"
        in langsmith["readinessCommand"]
    )
    actions = {action["id"]: action for action in langsmith["nextActions"]}
    assert actions["refresh-release-readiness"]["requiredReadinessReports"] == [
        "hardening_suite",
        "langsmith_eval_sync",
    ]
    assert actions["refresh-release-readiness"]["readinessReports"] == {
        "hardening_suite": "reports/hardening-suite.json",
        "langsmith_eval_sync": str(langsmith_report_file),
    }


def test_eval_case_table_shows_langsmith_product_boundary_readiness_command() -> None:
    table = format_eval_case_table(
        {
            "promotedCase": {
                "id": "case_rag_candidate_c1",
                "sourceRunId": "run_rag_candidate_1",
            },
            "suiteApply": {
                "langsmithDryRun": {
                    "status": "skipped",
                    "datasetName": "reactor-rag-ingestion-candidate",
                    "releaseGate": {
                        "status": "blocked",
                        "reason": "feedback_review_queue_source_missing",
                        "remediationCommand": (
                            "reactor-admin feedback --rating thumbs_down "
                            "--tag collection:rag-ingestion-candidate --output table"
                        ),
                    },
                    "productBoundaryReadinessCommand": (
                        "uv run reactor-release-smoke-run "
                        "--required-readiness-report hardening_suite "
                        "--required-readiness-report langsmith_eval_sync"
                    ),
                },
            },
        }
    )

    rows = dict(line.split(maxsplit=1) for line in table.splitlines()[1:])
    assert (
        "langsmithProductBoundaryReadinessCommand  uv run reactor-release-smoke-run "
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync\n"
    ) in table
    assert rows["langsmithReleaseGateRemediationCommand"] == (
        "reactor-admin feedback --rating thumbs_down "
        "--tag collection:rag-ingestion-candidate --output table"
    )


def test_runs_cli_promote_eval_apply_table_shows_memory_feedback_queue_action(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    langsmith_report_file = tmp_path / "langsmith-dry-run.json"
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "promote-eval",
            "run_failed",
            "--case-id",
            "memory_supersession_review",
            "--expected-answer",
            "provider outage",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--tag",
            "feedback-rating:thumbs_down",
            "--tag",
            "memory",
            "--apply-suite-file",
            str(suite_file),
            "--apply-require-run-file",
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "operator_1"},
    )

    assert exit_code == 0
    rows = dict(line.split(maxsplit=1) for line in stdout.getvalue().splitlines()[1:])
    assert rows["langsmithFeedbackQueueReviewAction"] == (
        "reactor-admin feedback --rating thumbs_down --review-status inbox "
        "--case-id memory_supersession_review "
        "--tag memory --limit 10 --output table"
    )
    assert rows["langsmithFeedbackQueueMemoryAction"] == MEMORY_LIFECYCLE_GATE_ACTION


def test_runs_cli_langsmith_feedback_review_action_uses_workflow_queue() -> None:
    assert langsmith_feedback_review_action(
        {
            "feedbackIdList": ["fb_1", "fb_2"],
            "feedbackRatings": {"thumbs_down": 2},
            "feedbackWorkflows": {"documents-ask": 1, "rag": 2},
        }
    ) == (
        "reactor-admin feedback --rating thumbs_down --review-status inbox "
        "--tag rag --limit 10 --output table"
    )


def test_runs_cli_langsmith_feedback_review_action_scopes_workflow_queue_by_source() -> None:
    assert langsmith_feedback_review_action(
        {
            "feedbackIdList": ["fb_1", "fb_2"],
            "feedbackRatings": {"thumbs_down": 2},
            "feedbackSources": {"slack_button": 2},
            "feedbackWorkflows": {"documents-ask": 1, "rag": 2},
        }
    ) == (
        "reactor-admin feedback --rating thumbs_down --source slack_button "
        "--review-status inbox --tag rag --limit 10 --output table"
    )


def test_runs_cli_langsmith_next_action_rows_include_feedback_id() -> None:
    rows = dict(
        langsmith_next_action_rows(
            [
                {
                    "id": "review-feedback-fb_1",
                    "command": "reactor-admin feedback --feedback-id fb_1 --output table",
                    "feedbackId": "fb_1",
                }
            ]
        )
    )

    assert rows["langsmithNextActionIds"] == "review-feedback-fb_1"
    assert rows["langsmithNextAction.review-feedback-fb_1"] == (
        "reactor-admin feedback --feedback-id fb_1 --output table"
    )
    assert rows["langsmithNextAction.review-feedback-fb_1.feedbackId"] == "fb_1"


def test_runs_cli_langsmith_next_action_rows_preserve_release_identity() -> None:
    rows = dict(
        langsmith_next_action_rows(
            [
                {
                    "id": "refresh-readiness",
                    "command": (
                        "uv run reactor-release-smoke-run "
                        "--readiness-report langsmith_eval_sync=reports/langsmith.json"
                    ),
                    "feedbackId": "fb_candidate",
                    "evalCaseId": "case_rag_candidate_c1",
                    "sourceRunId": "run_rag_candidate_1",
                    "candidateTag": "rag-candidate:c1",
                    "requiredReviewNote": "Reviewed RAG candidate feedback before release.",
                    "recommendedVersionBump": "minor",
                    "recommendedTagPattern": "v1.2.0",
                    "latestTagCommand": "git describe --tags --abbrev=0",
                    "recommendedTagSource": "release_readiness.tagRecommendation.recommendedTag",
                    "replatformReadinessFile": "reports/release/replatform-readiness.local.json",
                    "smokePlanFile": "reports/release/release-smoke-plan.local.json",
                    "releaseEvidenceFile": "reports/release-evidence.json",
                    "minorBoundaryReports": ["langsmith_eval_sync"],
                    "minorBlockedReports": ["langsmith_eval_sync"],
                    "minorBoundaryMissingEvidence": ["feedback_promotion.reviewed_feedback"],
                    "dependsOnActionIds": ["sync-langsmith"],
                    "requiredEnvAnyOf": [
                        ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                    ],
                    "missingEnvAnyOf": [
                        "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
                    ],
                    "recommendedEnv": ["LANGSMITH_ENDPOINT"],
                }
            ]
        )
    )

    assert rows["langsmithNextAction.refresh-readiness.feedbackId"] == "fb_candidate"
    assert rows["langsmithNextAction.refresh-readiness.evalCaseId"] == "case_rag_candidate_c1"
    assert rows["langsmithNextAction.refresh-readiness.sourceRunId"] == "run_rag_candidate_1"
    assert rows["langsmithNextAction.refresh-readiness.candidateTag"] == "rag-candidate:c1"
    assert rows["langsmithNextAction.refresh-readiness.requiredReviewNote"] == (
        "Reviewed RAG candidate feedback before release."
    )
    assert rows["langsmithNextAction.refresh-readiness.recommendedVersionBump"] == "minor"
    assert rows["langsmithNextAction.refresh-readiness.recommendedTagPattern"] == "v1.2.0"
    assert (
        rows["langsmithNextAction.refresh-readiness.latestTagCommand"]
        == "git describe --tags --abbrev=0"
    )
    assert (
        rows["langsmithNextAction.refresh-readiness.recommendedTagSource"]
        == "release_readiness.tagRecommendation.recommendedTag"
    )
    assert rows["langsmithNextAction.refresh-readiness.replatformReadinessFile"] == (
        "reports/release/replatform-readiness.local.json"
    )
    assert rows["langsmithNextAction.refresh-readiness.smokePlanFile"] == (
        "reports/release/release-smoke-plan.local.json"
    )
    assert rows["langsmithNextAction.refresh-readiness.releaseEvidenceFile"] == (
        "reports/release-evidence.json"
    )
    assert (
        rows["langsmithNextAction.refresh-readiness.minorBoundaryReports"] == "langsmith_eval_sync"
    )
    assert (
        rows["langsmithNextAction.refresh-readiness.minorBlockedReports"] == "langsmith_eval_sync"
    )
    assert (
        rows["langsmithNextAction.refresh-readiness.minorBoundaryMissingEvidence"]
        == "feedback_promotion.reviewed_feedback"
    )
    assert rows["langsmithNextAction.refresh-readiness.requiredEnvAnyOf.0"] == (
        "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    )
    assert rows["langsmithNextAction.refresh-readiness.missingEnvAnyOf"] == (
        "LANGSMITH_API_KEY|REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"
    )
    assert rows["langsmithNextAction.refresh-readiness.recommendedEnv"] == "LANGSMITH_ENDPOINT"
    assert rows["langsmithNextAction.refresh-readiness.dependsOnActionIds"] == "sync-langsmith"


def test_runs_cli_promote_eval_apply_can_include_suite_coverage_summary(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "provider outage",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--apply-suite-file",
            str(suite_file),
            "--apply-require-run-file",
            "--apply-suite-summary",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["suiteSummary"] == {
        "suiteFile": str(suite_file),
        "caseCount": 1,
        "enabledCases": 1,
        "disabledCases": 0,
        "runCount": 1,
        "coveredCases": 1,
        "missingRuns": 0,
        "missingRunIds": [],
        "caseIds": ["case_failed_provider"],
    }


def test_runs_cli_promote_eval_apply_dry_run_summarizes_pending_suite(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    original_suite: dict[str, object] = {"cases": [], "runs": []}
    suite_file.write_text(json.dumps(original_suite) + "\n", encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "operator_1",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "provider outage",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--apply-suite-file",
            str(suite_file),
            "--apply-require-run-file",
            "--apply-dry-run",
            "--apply-suite-summary",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["suiteApply"]["status"] == "would_add"
    assert payload["suiteSummary"] == {
        "suiteFile": str(suite_file),
        "caseCount": 1,
        "enabledCases": 1,
        "disabledCases": 0,
        "runCount": 1,
        "coveredCases": 1,
        "missingRuns": 0,
        "missingRunIds": [],
        "caseIds": ["case_failed_provider"],
    }
    assert json.loads(suite_file.read_text(encoding="utf-8")) == original_suite


def test_runs_cli_promote_eval_apply_table_includes_suite_coverage_summary(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    probe = FakeRunsProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_failed_provider",
            "--expected-answer",
            "provider outage",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--apply-suite-file",
            str(suite_file),
            "--apply-require-run-file",
            "--apply-suite-summary",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    rows = dict(line.split(maxsplit=1) for line in stdout.getvalue().splitlines()[1:])
    assert rows["suiteCoveredCases"] == "1"
    assert rows["suiteMissingRuns"] == "0"


def test_runs_cli_promote_eval_apply_table_shows_citation_failure_coverage(
    tmp_path: Path,
) -> None:
    class DocumentsAskCitationFailureProbe(FakeRunsProbe):
        def post_json(
            self,
            path: str,
            headers: dict[str, str],
            payload: dict[str, object],
        ) -> RunCliHttpResult:
            if path != "/v1/admin/agent-eval/cases/promote":
                return super().post_json(path, headers, payload)
            self.calls.append(
                {
                    "method": "POST",
                    "path": path,
                    "headers": headers,
                    "payload": payload,
                }
            )
            return RunCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "id": "case_documents_ask_citation",
                    "name": "Documents ask citation regression",
                    "userInput": "How should rollback work?",
                    "expectedAnswerContains": ["[runbook.md]"],
                    "forbiddenAnswerContains": [],
                    "expectedToolNames": [],
                    "forbiddenToolNames": [],
                    "expectedExposedToolNames": [],
                    "forbiddenExposedToolNames": [],
                    "maxToolExposureCount": None,
                    "agentType": "documents-ask",
                    "model": "test-model",
                    "enabled": True,
                    "tags": [
                        "rag",
                        "documents-ask",
                        "citation-failure",
                        "feedback:fb_1",
                        "feedback-rating:thumbs_down",
                        "feedback-source:slack_button",
                    ],
                    "minScore": 1.0,
                    "sourceRunId": "run_failed",
                    "assertionCount": 1,
                    "createdAt": "2026-07-01T00:00:00Z",
                    "updatedAt": "2026-07-01T00:00:00Z",
                },
            )

        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            result = super().get_json(path, headers)
            if path == "/v1/runs/run_failed" and isinstance(result.body, dict):
                result.body["input_text"] = "How should rollback work?"
                result.body["response_text"] = "Use runbook.md for rollback."
                result.body["metadata"] = {
                    "agentType": "documents-ask",
                    "model": "test-model",
                    "toolNames": ["Rag:hybrid_search"],
                    "exposedToolNames": ["Rag:hybrid_search"],
                    "retrievedChunks": [
                        {
                            "documentId": "doc_1",
                            "source": "runbook.md",
                            "title": "Runbook",
                            "score": 1.0,
                            "cited": False,
                        }
                    ],
                }
            return result

    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_documents_ask_citation",
            "--expected-answer",
            "[runbook.md]",
            "--tag",
            "rag",
            "--tag",
            "documents-ask",
            "--tag",
            "citation-failure",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--apply-suite-file",
            str(suite_file),
            "--apply-require-run-file",
            "--output",
            "table",
        ],
        http_probe=DocumentsAskCitationFailureProbe(),
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    rows = dict(line.split(maxsplit=1) for line in stdout.getvalue().splitlines()[1:])
    assert rows["coverageCitationMarkers"] == "true"
    assert rows["coverageRunCitationMarkers"] == "false"


def test_runs_cli_promote_eval_apply_table_shows_langsmith_deterministic_failures(
    tmp_path: Path,
) -> None:
    class DocumentsAskCitationFailureProbe(FakeRunsProbe):
        def post_json(
            self,
            path: str,
            headers: dict[str, str],
            payload: dict[str, object],
        ) -> RunCliHttpResult:
            if path != "/v1/admin/agent-eval/cases/promote":
                return super().post_json(path, headers, payload)
            self.calls.append(
                {
                    "method": "POST",
                    "path": path,
                    "headers": headers,
                    "payload": payload,
                }
            )
            return RunCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "id": "case_documents_ask_citation",
                    "name": "Documents ask citation regression",
                    "userInput": "How should rollback work?",
                    "expectedAnswerContains": ["[runbook.md]"],
                    "forbiddenAnswerContains": [],
                    "expectedToolNames": [],
                    "forbiddenToolNames": [],
                    "expectedExposedToolNames": [],
                    "forbiddenExposedToolNames": [],
                    "maxToolExposureCount": None,
                    "agentType": "documents-ask",
                    "model": "test-model",
                    "enabled": True,
                    "tags": [
                        "rag",
                        "documents-ask",
                        "citation-failure",
                        "feedback:fb_1",
                        "feedback-rating:thumbs_down",
                        "feedback-source:slack_button",
                    ],
                    "minScore": 1.0,
                    "sourceRunId": "run_failed",
                    "assertionCount": 1,
                    "createdAt": "2026-07-01T00:00:00Z",
                    "updatedAt": "2026-07-01T00:00:00Z",
                },
            )

        def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
            result = super().get_json(path, headers)
            if path == "/v1/runs/run_failed" and isinstance(result.body, dict):
                result.body["input_text"] = "How should rollback work?"
                result.body["response_text"] = "Use runbook.md for rollback."
                result.body["metadata"] = {
                    "agentType": "documents-ask",
                    "model": "test-model",
                    "toolNames": ["Rag:hybrid_search"],
                    "exposedToolNames": ["Rag:hybrid_search"],
                    "retrievedChunks": [
                        {
                            "documentId": "doc_1",
                            "source": "runbook.md",
                            "title": "Runbook",
                            "score": 1.0,
                            "cited": False,
                        }
                    ],
                }
            return result

    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text('{"cases": [], "runs": []}\n', encoding="utf-8")
    case_file = tmp_path / "promoted-case.json"
    run_file = tmp_path / "promoted-run.json"
    langsmith_report_file = tmp_path / "langsmith-dry-run.json"
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "promote-eval",
            "run_failed",
            "--case-id",
            "case_documents_ask_citation",
            "--expected-answer",
            "[runbook.md]",
            "--tag",
            "rag",
            "--tag",
            "documents-ask",
            "--tag",
            "citation-failure",
            "--case-file",
            str(case_file),
            "--run-file",
            str(run_file),
            "--apply-suite-file",
            str(suite_file),
            "--apply-require-run-file",
            "--langsmith-dry-run-report-file",
            str(langsmith_report_file),
            "--output",
            "table",
        ],
        http_probe=DocumentsAskCitationFailureProbe(),
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    rows = dict(line.split(maxsplit=1) for line in stdout.getvalue().splitlines()[1:])
    assert rows["langsmithDeterministicFailedCases"] == "1"
    assert rows["langsmithDeterministicMissingExpected"] == "[runbook.md]"


def test_runs_cli_requires_base_url_and_reports_api_errors() -> None:
    no_base_stderr = StringIO()
    no_base_exit = run_cli(
        ["create", "--message", "hello"],
        http_probe=FakeRunsProbe(),
        stdout=StringIO(),
        stderr=no_base_stderr,
        environ={},
    )

    failing_stderr = StringIO()
    failing_exit = run_cli(
        ["--base-url", "http://reactor.local", "status", "missing"],
        http_probe=FakeRunsProbe(),
        stdout=StringIO(),
        stderr=failing_stderr,
        environ={"REACTOR_TENANT_ID": "tenant_1", "REACTOR_USER_ID": "user_1"},
    )

    assert no_base_exit == 2
    assert "REACTOR_API_BASE_URL" in no_base_stderr.getvalue()
    assert failing_exit == 1
    assert "404" in failing_stderr.getvalue()
    assert "not found" in failing_stderr.getvalue()
