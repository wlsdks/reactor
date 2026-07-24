from __future__ import annotations

from reactor.agents.runner import RunResult
from reactor.slack.response_formatting import format_slack_run_response


def test_slack_response_formatter_rewrites_generic_task_refusal() -> None:
    result = run_result(response="요청하신 작업을 수행할 수 없습니다")

    text = format_slack_run_response(result, original_prompt="오늘 할 일 우선순위 알려줘")

    assert "바로 실행 가능한 초안으로 정리합니다." in text
    assert "요청하신 작업을 수행할 수 없습니다" not in text


def test_slack_response_formatter_surfaces_non_completed_status_as_warning() -> None:
    result = run_result(status="rejected", response="Guard blocked unsafe prompt")

    assert (
        format_slack_run_response(result, original_prompt="unsafe")
        == ":warning: Guard blocked unsafe prompt\n\n"
        "_Run: `run_1`_\n"
        "_Diagnose: `reactor-runs diagnose run_1 --output table`_\n"
        "_Replay events: `reactor-runs replay run_1 --output table`_\n"
        "_State history: `reactor-admin state-history run_1 --output table`_\n"
        "_Feedback review: `reactor-admin feedback --rating thumbs_down "
        "--review-status inbox --limit 10 "
        "--output table`_"
    )


def test_slack_response_formatter_replaces_blank_completed_response() -> None:
    result = run_result(response="  ")

    assert (
        format_slack_run_response(result, original_prompt="hello")
        == "I processed your request but have no response.\n\n"
        "_Run: `run_1`_\n"
        "_Diagnose: `reactor-runs diagnose run_1 --output table`_\n"
        "_Replay events: `reactor-runs replay run_1 --output table`_\n"
        "_State history: `reactor-admin state-history run_1 --output table`_\n"
        "_Feedback review: `reactor-admin feedback --rating thumbs_down "
        "--review-status inbox --limit 10 "
        "--output table`_"
    )


def test_slack_response_formatter_appends_run_id_for_follow_up_diagnostics() -> None:
    result = run_result(response="Here is the answer.")

    assert (
        format_slack_run_response(result, original_prompt="hello") == "Here is the answer.\n\n"
        "_Run: `run_1`_\n"
        "_Diagnose: `reactor-runs diagnose run_1 --output table`_\n"
        "_Replay events: `reactor-runs replay run_1 --output table`_\n"
        "_State history: `reactor-admin state-history run_1 --output table`_\n"
        "_Feedback review: `reactor-admin feedback --rating thumbs_down "
        "--review-status inbox --limit 10 "
        "--output table`_"
    )


def test_slack_response_formatter_quotes_run_operator_commands() -> None:
    result = run_result(response="Here is the answer.", run_id="run needs quoting")

    assert (
        format_slack_run_response(result, original_prompt="hello") == "Here is the answer.\n\n"
        "_Run: `run needs quoting`_\n"
        "_Diagnose: `reactor-runs diagnose 'run needs quoting' --output table`_\n"
        "_Replay events: `reactor-runs replay 'run needs quoting' --output table`_\n"
        "_State history: `reactor-admin state-history 'run needs quoting' --output table`_\n"
        "_Feedback review: `reactor-admin feedback --rating thumbs_down "
        "--review-status inbox --limit 10 "
        "--output table`_"
    )


def run_result(
    *,
    response: str,
    status: str = "completed",
    run_id: str = "run_1",
) -> RunResult:
    return RunResult(
        run_id=run_id,
        tenant_id="tenant_1",
        user_id="U1",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        status=status,
        response=response,
        provider="openai",
        model="gpt-5-mini",
    )
