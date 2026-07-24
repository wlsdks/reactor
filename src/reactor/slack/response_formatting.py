from __future__ import annotations

import re
from shlex import quote

from reactor.agents.runner import RunResult

_GENERIC_REFUSAL_PATTERNS = (
    re.compile("요청하신 작업을 수행할 수 없습니다"),
    re.compile("어떤 작업을 해야 하는지 알려주시면"),
    re.compile(r"cannot (fulfill|complete) (this )?request", re.IGNORECASE),
    re.compile(r"unable to (help|proceed)", re.IGNORECASE),
)
_TASK_PLANNING_MARKERS = ("할 일", "today", "task", "priority", "my-work", "mywork")


def format_slack_run_response(result: RunResult, *, original_prompt: str) -> str:
    content = result.response.strip()
    if result.status != "completed":
        return _with_run_reference(
            f":warning: {content or 'An error occurred while processing your request.'}",
            result=result,
        )
    if not content:
        return _with_run_reference("I processed your request but have no response.", result=result)
    if _is_generic_refusal(content):
        return _with_run_reference(_best_effort_fallback(original_prompt), result=result)
    return _with_run_reference(content, result=result)


def _with_run_reference(content: str, *, result: RunResult) -> str:
    if not result.run_id:
        return content
    quoted_run_id = quote(result.run_id)
    return (
        f"{content}\n\n"
        f"_Run: `{result.run_id}`_\n"
        f"_Diagnose: `reactor-runs diagnose {quoted_run_id} --output table`_\n"
        f"_Replay events: `reactor-runs replay {quoted_run_id} --output table`_\n"
        f"_State history: `reactor-admin state-history {quoted_run_id} --output table`_\n"
        "_Feedback review: `reactor-admin feedback --rating thumbs_down "
        "--review-status inbox --limit 10 --output table`_"
    )


def _is_generic_refusal(content: str) -> bool:
    return any(pattern.search(content) is not None for pattern in _GENERIC_REFUSAL_PATTERNS)


def _best_effort_fallback(prompt: str) -> str:
    if _looks_like_task_planning(prompt):
        return (
            "바로 실행 가능한 초안으로 정리합니다.\n"
            "1. 오늘 반드시 끝낼 핵심 작업 1개를 먼저 확정합니다.\n"
            "2. 그 다음 우선순위 작업 2개를 60분 단위로 배치합니다.\n"
            "3. 마지막으로 10분 점검 슬롯을 예약해 지연 요인을 정리합니다.\n"
            "필요하면 현재 업무 맥락(프로젝트/마감일)을 주시면 바로 맞춤형으로 다시 정리해드릴게요."
        )
    return (
        "요청을 처리하기에 충분한 실시간 맥락이 없어도, 우선 실행 가능한 답을 먼저 드립니다.\n"
        "- 목표를 한 줄로 확정\n"
        "- 다음 행동 1개를 30분 내 완료 가능한 크기로 분해\n"
        "- 완료 기준을 한 줄로 정의\n"
        "필요한 맥락을 알려주시면 바로 구체화하겠습니다."
    )


def _looks_like_task_planning(prompt: str) -> bool:
    normalized = prompt.lower()
    return any(marker in normalized for marker in _TASK_PLANNING_MARKERS)
