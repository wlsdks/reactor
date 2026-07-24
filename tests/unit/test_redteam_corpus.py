from __future__ import annotations

from pathlib import Path

from reactor.evals.redteam import RedTeamCorpus, RedTeamEvaluator

FIXTURE = Path("tests/fixtures/redteam/probes.json")


def test_redteam_corpus_loads_legacy_probe_axes() -> None:
    corpus = RedTeamCorpus.load(FIXTURE)

    assert corpus.version == "2026-06-27-python-port"
    assert corpus.axes == frozenset({"prompt_safety", "tool_selection", "output_safety"})
    assert corpus.case_by_id("prompt-safety-ignore-previous-ko").input_text.startswith("이전 지시")


def test_redteam_evaluator_uses_runtime_guards_for_prompt_and_output_safety() -> None:
    corpus = RedTeamCorpus.load(FIXTURE)

    results = RedTeamEvaluator().evaluate(corpus)

    assert all(result.passed for result in results), [result.to_json_dict() for result in results]
    blocked = {
        result.case_id: result.observed_reason for result in results if result.observed_blocked
    }
    assert blocked["prompt-safety-fake-admin"] == "prompt_injection"
    assert blocked["output-safety-service-api-secret"] == "secret_leak"
    assert blocked["output-safety-canary-secret"] == "canary_secret"
    assert blocked["output-safety-ssn-pii"] == "pii_leak"
    assert blocked["output-safety-card-pii"] == "pii_leak"


def test_redteam_evaluator_reports_guard_regressions() -> None:
    corpus = RedTeamCorpus.load(FIXTURE).select(case_ids={"prompt-safety-ignore-previous-ko"})

    results = RedTeamEvaluator(input_guard=None).evaluate(corpus)

    assert len(results) == 1
    assert results[0].passed is False
    assert results[0].reasons == ("expected input to be blocked",)
