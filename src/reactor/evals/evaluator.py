from __future__ import annotations

from reactor.evals.models import AgentEvalCaseRecord, AgentEvalCaseResultRecord, AgentEvalRunRecord


class AgentEvalRegressionEvaluator:
    def evaluate(
        self,
        case: AgentEvalCaseRecord,
        run: AgentEvalRunRecord,
    ) -> AgentEvalCaseResultRecord:
        answer = run.final_answer.lower()
        tools = set(run.tool_names)
        exposed_tools = set(run.exposed_tool_names)

        missing_answer = tuple(
            expected for expected in case.expected_answer_contains if expected.lower() not in answer
        )
        matched_forbidden_answer = tuple(
            forbidden for forbidden in case.forbidden_answer_contains if forbidden.lower() in answer
        )
        missing_tools = tuple(
            expected for expected in case.expected_tool_names if expected not in tools
        )
        forbidden_tools = tuple(
            forbidden for forbidden in case.forbidden_tool_names if forbidden in tools
        )
        missing_exposed_tools = tuple(
            expected
            for expected in case.expected_exposed_tool_names
            if expected not in exposed_tools
        )
        forbidden_exposed_tools = tuple(
            forbidden
            for forbidden in case.forbidden_exposed_tool_names
            if forbidden in exposed_tools
        )
        exposure_exceeded = (
            case.max_tool_exposure_count is not None
            and len(run.exposed_tool_names) > case.max_tool_exposure_count
        )
        agent_type_mismatch = case.agent_type is not None and case.agent_type != run.agent_type
        model_mismatch = case.model is not None and case.model != run.model
        reasons = build_reasons(
            case=case,
            run=run,
            missing_answer=missing_answer,
            forbidden_answer=matched_forbidden_answer,
            missing_tools=missing_tools,
            forbidden_tools=forbidden_tools,
            missing_exposed_tools=missing_exposed_tools,
            forbidden_exposed_tools=forbidden_exposed_tools,
            exposure_exceeded=exposure_exceeded,
            agent_type_mismatch=agent_type_mismatch,
            model_mismatch=model_mismatch,
        )
        failed_count = len(reasons)
        assertion_count = max(1, case.assertion_count)
        score = max(0.0, 1.0 - (failed_count / assertion_count))
        passed = not reasons and score >= case.min_score
        return AgentEvalCaseResultRecord(
            case_id=case.id,
            run_id=run.run_id,
            passed=passed,
            score=round(score, 4),
            reasons=reasons,
            missing_expected_answer_contains=missing_answer,
            missing_expected_tools=missing_tools,
            forbidden_tools_used=forbidden_tools,
            missing_expected_exposed_tools=missing_exposed_tools,
            forbidden_tools_exposed=forbidden_exposed_tools,
            tool_exposure_count_exceeded=exposure_exceeded,
            agent_type_mismatch=agent_type_mismatch,
            model_mismatch=model_mismatch,
        )


def build_reasons(
    *,
    case: AgentEvalCaseRecord,
    run: AgentEvalRunRecord,
    missing_answer: tuple[str, ...],
    forbidden_answer: tuple[str, ...],
    missing_tools: tuple[str, ...],
    forbidden_tools: tuple[str, ...],
    missing_exposed_tools: tuple[str, ...],
    forbidden_exposed_tools: tuple[str, ...],
    exposure_exceeded: bool,
    agent_type_mismatch: bool,
    model_mismatch: bool,
) -> tuple[str, ...]:
    reasons: list[str] = []
    reasons.extend(f"missing expected answer text: {item}" for item in missing_answer)
    reasons.extend(f"forbidden answer text matched: {item}" for item in forbidden_answer)
    reasons.extend(f"missing expected tool: {item}" for item in missing_tools)
    reasons.extend(f"forbidden tool used: {item}" for item in forbidden_tools)
    reasons.extend(f"missing expected exposed tool: {item}" for item in missing_exposed_tools)
    reasons.extend(f"forbidden exposed tool: {item}" for item in forbidden_exposed_tools)
    if exposure_exceeded:
        reasons.append("tool exposure count exceeded")
    if agent_type_mismatch:
        reasons.append(f"agentType mismatch: expected={case.agent_type}, actual={run.agent_type}")
    if model_mismatch:
        reasons.append(f"model mismatch: expected={case.model}, actual={run.model}")
    return tuple(reasons)
