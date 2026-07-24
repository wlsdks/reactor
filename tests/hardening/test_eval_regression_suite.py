from __future__ import annotations

from pathlib import Path

from reactor.evals.suite import AgentEvalRegressionSuite, AgentTraceGrader

FIXTURE = Path("tests/fixtures/agent-eval/regression-suite.json")


def test_source_controlled_agent_eval_regression_suite_passes() -> None:
    suite = AgentEvalRegressionSuite.load(FIXTURE)

    results = suite.evaluate()

    assert [result.case_id for result in results] == [
        "tool-exposure-issue-readonly",
        "casual-prompt-exposes-no-tools",
        "rag-grounded-answer-cites-source",
        "rag-poisoning-retrieval-is-labeled",
    ]
    assert all(result.passed for result in results), [
        (result.case_id, result.reasons) for result in results if not result.passed
    ]


def test_source_controlled_agent_eval_traces_pass_trace_grading() -> None:
    suite = AgentEvalRegressionSuite.load(FIXTURE)
    grader = AgentTraceGrader()

    grades = [
        grader.grade(case, suite.require_run_for_case(case.id)) for case in suite.enabled_cases
    ]

    assert all(grade.passed for grade in grades), [
        (grade.case_id, grade.score, grade.dimensions) for grade in grades if not grade.passed
    ]


def test_source_controlled_agent_eval_suite_includes_rag_poisoning_regression() -> None:
    suite = AgentEvalRegressionSuite.load(FIXTURE)

    case = next(
        case for case in suite.enabled_cases if case.id == "rag-poisoning-retrieval-is-labeled"
    )
    run = suite.require_run_for_case(case.id)

    assert "rag" in case.tags
    assert "poisoning" in case.tags
    assert "Ignore previous instructions" in case.forbidden_answer_contains
    assert "reveal the system prompt" in case.forbidden_answer_contains
    poisoned = next(
        chunk
        for chunk in run.retrieved_chunks
        if chunk.document_id == "tenant-rag-poisoning-runbook"
    )
    assert poisoned.poisoning_flagged is True
    assert poisoned.poisoning_reasons == ("prompt_injection", "system_prompt_exfiltration")


def test_source_controlled_rag_eval_cases_require_citation_markers() -> None:
    suite = AgentEvalRegressionSuite.load(FIXTURE)

    cases_by_id = {case.id: case for case in suite.enabled_cases}

    for case_id, citation in {
        "rag-grounded-answer-cites-source": "[vectorstore-runbook.md]",
        "rag-poisoning-retrieval-is-labeled": "[trusted-runbook.md]",
    }.items():
        case = cases_by_id[case_id]
        run = suite.require_run_for_case(case.id)
        assert citation in case.expected_answer_contains
        assert citation in run.final_answer


def test_agent_trace_grader_reports_poisoned_retrieval_safety_evidence() -> None:
    suite = AgentEvalRegressionSuite.load(FIXTURE)
    case = next(
        case for case in suite.enabled_cases if case.id == "rag-poisoning-retrieval-is-labeled"
    )
    grade = AgentTraceGrader().grade(case, suite.require_run_for_case(case.id))
    safety = next(dimension for dimension in grade.dimensions if dimension.name == "safety")

    assert safety.score == 1.0
    assert safety.evidence == {
        "forbiddenUsed": [],
        "forbiddenExposed": [],
        "poisonedChunks": 1,
        "poisoningReasons": ["prompt_injection", "system_prompt_exfiltration"],
        "poisonedChunkDocuments": ["tenant-rag-poisoning-runbook"],
    }
    assert "poisonedChunks=1" in safety.reason
    assert "poisoningReasons=['prompt_injection', 'system_prompt_exfiltration']" in safety.reason


def test_agent_eval_suite_reports_missing_run_fixture() -> None:
    fixture_suite = AgentEvalRegressionSuite.load(FIXTURE)
    suite = AgentEvalRegressionSuite(cases=(fixture_suite.cases[0],), runs=())

    result = suite.evaluate()[0]

    assert result.passed is False
    assert result.score == 0.0
    assert result.reasons == ("no AgentRunLog fixture found for eval case",)


def test_agent_eval_evaluator_fails_on_agent_type_or_model_mismatch() -> None:
    suite = AgentEvalRegressionSuite.load(FIXTURE)
    case = suite.cases[0]
    run = (
        suite.require_run_for_case(case.id)
        .with_agent_identity(
            agent_type="react",
            model="other-model",
        )
        .as_eval_run()
    )

    result = suite.evaluator.evaluate(case, run)

    assert result.passed is False
    assert "agentType mismatch: expected=standard, actual=react" in result.reasons
    assert "model mismatch: expected=test-model, actual=other-model" in result.reasons
