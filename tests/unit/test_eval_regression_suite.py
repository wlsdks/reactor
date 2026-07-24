from __future__ import annotations

import json
from pathlib import Path

import pytest

from reactor.evals.suite import (
    AgentEvalCaseRecord,
    AgentEvalRegressionSuite,
    AgentEvalRunFixture,
    AgentTraceGrader,
    retrieved_chunk_from_json,
)


def test_retrieved_chunk_fixture_preserves_cited_flag_for_grounding_review() -> None:
    chunk = retrieved_chunk_from_json(
        {
            "documentId": "doc_1",
            "citationId": "doc_1:0",
            "source": "docs://reactor/runbooks/rag.md",
            "title": "RAG runbook",
            "score": 1.0,
            "cited": True,
        }
    )

    assert chunk.cited is True
    assert chunk.document_id == "doc_1"
    assert chunk.citation_id == "doc_1:0"


def test_trace_grader_prefers_citation_id_for_grounding_evidence() -> None:
    run = AgentEvalRunFixture(
        run_id="run_1",
        eval_case_id="case_1",
        user_input="How should Reactor cite RAG answers?",
        agent_type="documents-ask",
        model="test-model",
        final_answer="Use Reactor citations. [docs_reactor_runbooks_rag_md:0]",
        retrieved_chunks=(
            retrieved_chunk_from_json(
                {
                    "documentId": "docs/reactor runbooks/rag.md",
                    "citationId": "docs_reactor_runbooks_rag_md:0",
                    "title": "RAG runbook",
                    "score": 1.0,
                    "cited": True,
                }
            ),
        ),
    )

    trace = AgentTraceGrader().grade(
        AgentEvalCaseRecord(
            id="case_1",
            name="RAG grounding",
            user_input="How should Reactor cite RAG answers?",
        ),
        run,
    )
    grade = next(item for item in trace.dimensions if item.name == "grounding")

    assert grade.evidence["citedDocuments"] == ["docs_reactor_runbooks_rag_md:0"]


def test_trace_grader_prefers_citation_id_for_poisoned_chunk_evidence() -> None:
    run = AgentEvalRunFixture(
        run_id="run_1",
        eval_case_id="case_1",
        user_input="How should Reactor cite RAG answers?",
        agent_type="documents-ask",
        model="test-model",
        final_answer="Use Reactor citations.",
        retrieved_chunks=(
            retrieved_chunk_from_json(
                {
                    "documentId": "docs/reactor runbooks/rag.md",
                    "citationId": "docs_reactor_runbooks_rag_md:0",
                    "title": "RAG runbook",
                    "score": 1.0,
                    "poisoning": {
                        "flagged": True,
                        "reasons": ["prompt_injection"],
                    },
                }
            ),
        ),
    )

    trace = AgentTraceGrader().grade(
        AgentEvalCaseRecord(
            id="case_1",
            name="RAG poisoning",
            user_input="How should Reactor treat poisoned retrieval?",
        ),
        run,
    )
    grade = next(item for item in trace.dimensions if item.name == "safety")

    assert grade.evidence["poisonedChunkDocuments"] == ["docs_reactor_runbooks_rag_md:0"]


def test_regression_suite_load_rejects_documents_ask_placeholder_citation_marker(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case_documents_placeholder",
                        "name": "Documents answer should cite a real source",
                        "userInput": "How should rollback work?",
                        "expectedAnswerContains": ["[replace-with-source-id]"],
                        "tags": ["rag", "documents-ask"],
                    }
                ],
                "runs": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="placeholder citation marker"):
        AgentEvalRegressionSuite.load(suite_file)


def test_regression_suite_load_marks_rag_documents_ask_cases_as_grounding(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case_documents_grounded",
                        "name": "Documents answer should cite a real source",
                        "userInput": "How should rollback work?",
                        "expectedAnswerContains": ["[runbook.md]"],
                        "tags": ["rag", "documents-ask"],
                    }
                ],
                "runs": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    suite = AgentEvalRegressionSuite.load(suite_file)

    assert suite.cases[0].tags == ("rag", "documents-ask", "grounding")


def test_regression_suite_load_rejects_command_unsafe_run_id(tmp_path: Path) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case_1",
                        "name": "Grounded answer",
                        "userInput": "How should rollback work?",
                    }
                ],
                "runs": [
                    {
                        "runId": "run bad/path",
                        "evalCaseId": "case_1",
                        "userInput": "How should rollback work?",
                        "agentType": "documents-ask",
                        "model": "test-model",
                        "finalAnswer": "Use the rollback runbook.",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="runId must be command-safe"):
        AgentEvalRegressionSuite.load(suite_file)


def test_regression_suite_load_rejects_duplicate_run_ids(tmp_path: Path) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case_1",
                        "name": "Grounded answer",
                        "userInput": "How should rollback work?",
                    },
                    {
                        "id": "case_2",
                        "name": "Grounded follow-up",
                        "userInput": "How should replay work?",
                    },
                ],
                "runs": [
                    {
                        "runId": "run_shared",
                        "evalCaseId": "case_1",
                        "userInput": "How should rollback work?",
                        "agentType": "documents-ask",
                        "model": "test-model",
                        "finalAnswer": "Use the rollback runbook.",
                    },
                    {
                        "runId": "run_shared",
                        "evalCaseId": "case_2",
                        "userInput": "How should replay work?",
                        "agentType": "documents-ask",
                        "model": "test-model",
                        "finalAnswer": "Use the replay runbook.",
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate eval suite run id: run_shared"):
        AgentEvalRegressionSuite.load(suite_file)


def test_regression_suite_load_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case_shared",
                        "name": "Grounded answer",
                        "userInput": "How should rollback work?",
                    },
                    {
                        "id": "case_shared",
                        "name": "Grounded follow-up",
                        "userInput": "How should replay work?",
                    },
                ],
                "runs": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate eval suite case id: case_shared"):
        AgentEvalRegressionSuite.load(suite_file)


def test_regression_suite_load_rejects_duplicate_run_eval_case_ids(tmp_path: Path) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case_1",
                        "name": "Grounded answer",
                        "userInput": "How should rollback work?",
                    }
                ],
                "runs": [
                    {
                        "runId": "run_first",
                        "evalCaseId": "case_1",
                        "userInput": "How should rollback work?",
                        "agentType": "documents-ask",
                        "model": "test-model",
                        "finalAnswer": "Use the rollback runbook.",
                    },
                    {
                        "runId": "run_second",
                        "evalCaseId": "case_1",
                        "userInput": "How should rollback work?",
                        "agentType": "documents-ask",
                        "model": "test-model",
                        "finalAnswer": "Use the other rollback runbook.",
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate eval suite run evalCaseId: case_1"):
        AgentEvalRegressionSuite.load(suite_file)


def test_regression_suite_load_rejects_run_unknown_eval_case_id(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case_1",
                        "name": "Grounded answer",
                        "userInput": "How should rollback work?",
                    }
                ],
                "runs": [
                    {
                        "runId": "run_orphan",
                        "evalCaseId": "case_missing",
                        "userInput": "How should rollback work?",
                        "agentType": "documents-ask",
                        "model": "test-model",
                        "finalAnswer": "Use the rollback runbook.",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="eval suite run references unknown case id: case_missing",
    ):
        AgentEvalRegressionSuite.load(suite_file)


def test_regression_suite_load_rejects_run_user_input_mismatch(tmp_path: Path) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case_1",
                        "name": "Grounded answer",
                        "userInput": "How should rollback work?",
                    }
                ],
                "runs": [
                    {
                        "runId": "run_1",
                        "evalCaseId": "case_1",
                        "userInput": "How should replay work?",
                        "agentType": "documents-ask",
                        "model": "test-model",
                        "finalAnswer": "Use the replay runbook.",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="eval suite run userInput mismatch: case_1"):
        AgentEvalRegressionSuite.load(suite_file)


def test_regression_suite_load_rejects_source_run_id_mismatch(
    tmp_path: Path,
) -> None:
    suite_file = tmp_path / "regression-suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case_1",
                        "name": "Grounded answer",
                        "userInput": "How should rollback work?",
                        "sourceRunId": "run_expected",
                    }
                ],
                "runs": [
                    {
                        "runId": "run_actual",
                        "evalCaseId": "case_1",
                        "userInput": "How should rollback work?",
                        "agentType": "documents-ask",
                        "model": "test-model",
                        "finalAnswer": "Use the rollback runbook.",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="eval suite sourceRunId mismatch: case_1"):
        AgentEvalRegressionSuite.load(suite_file)


def test_trace_grader_uses_explicit_retrieved_chunk_citation_counts() -> None:
    run = AgentEvalRunFixture(
        run_id="run_1",
        eval_case_id="case_1",
        user_input="How should Reactor cite RAG answers?",
        agent_type="documents-ask",
        model="test-model",
        final_answer="Use Reactor citations. [doc_1]",
        retrieved_chunks=(
            retrieved_chunk_from_json(
                {
                    "documentId": "doc_1",
                    "title": "RAG runbook",
                    "score": 1.0,
                    "cited": True,
                }
            ),
            retrieved_chunk_from_json(
                {
                    "documentId": "doc_2",
                    "title": "Extra context",
                    "score": 0.8,
                    "cited": False,
                }
            ),
        ),
    )

    trace = AgentTraceGrader().grade(
        AgentEvalCaseRecord(
            id="case_1",
            name="RAG grounding",
            user_input="How should Reactor cite RAG answers?",
        ),
        run,
    )
    grade = next(item for item in trace.dimensions if item.name == "grounding")

    assert grade.score == 1.0
    assert grade.reason == "retrieved=2 cited=1 uncited=1"
    assert grade.evidence == {
        "retrieved": 2,
        "cited": 1,
        "uncited": 1,
        "citedDocuments": ["doc_1"],
    }


def test_product_operations_regression_suite_covers_v1_2_workflow() -> None:
    suite = AgentEvalRegressionSuite.load(
        Path("tests/fixtures/agent-eval/product-operations-regression-suite.json")
    )

    assert len(suite.enabled_cases) == 12
    assert len(suite.runs) == 12
    tags = {tag for case in suite.enabled_cases for tag in case.tags}
    assert {
        "citation",
        "ungrounded",
        "weak-answer",
        "acl",
        "poisoning",
        "duplicate",
        "retry",
        "recovery",
        "failure-recovery",
    }.issubset(tags)
    assert all(result.passed for result in suite.evaluate())


def test_trace_grader_does_not_count_mention_only_grounding_as_citation() -> None:
    run = AgentEvalRunFixture(
        run_id="run_1",
        eval_case_id="case_1",
        user_input="How should Reactor cite RAG answers?",
        agent_type="documents-ask",
        model="test-model",
        final_answer="Use the RAG runbook at runbook.md for citation guidance.",
        retrieved_chunks=(
            retrieved_chunk_from_json(
                {
                    "documentId": "doc_1",
                    "source": "runbook.md",
                    "title": "RAG runbook",
                    "score": 1.0,
                }
            ),
        ),
    )

    trace = AgentTraceGrader().grade(
        AgentEvalCaseRecord(
            id="case_1",
            name="RAG grounding",
            user_input="How should Reactor cite RAG answers?",
        ),
        run,
    )
    grade = next(item for item in trace.dimensions if item.name == "grounding")

    assert grade.score == 0.5
    assert grade.reason == "retrieved=1 cited=False"


def test_trace_grader_records_evidence_for_bracketed_fallback_citations() -> None:
    run = AgentEvalRunFixture(
        run_id="run_1",
        eval_case_id="case_1",
        user_input="How should Reactor cite RAG answers?",
        agent_type="documents-ask",
        model="test-model",
        final_answer="Use Reactor citation guidance. [doc_1]",
        retrieved_chunks=(
            retrieved_chunk_from_json(
                {
                    "documentId": "doc_1",
                    "source": "runbook.md",
                    "title": "RAG runbook",
                    "score": 1.0,
                }
            ),
            retrieved_chunk_from_json(
                {
                    "documentId": "doc_2",
                    "source": "extra.md",
                    "title": "Extra context",
                    "score": 0.8,
                }
            ),
        ),
    )

    trace = AgentTraceGrader().grade(
        AgentEvalCaseRecord(
            id="case_1",
            name="RAG grounding",
            user_input="How should Reactor cite RAG answers?",
        ),
        run,
    )
    grade = next(item for item in trace.dimensions if item.name == "grounding")

    assert grade.score == 1.0
    assert grade.reason == "retrieved=2 cited=1 uncited=1"
    assert grade.evidence == {
        "retrieved": 2,
        "cited": 1,
        "uncited": 1,
        "citedDocuments": ["doc_1"],
    }
