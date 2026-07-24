from __future__ import annotations

from reactor.rag.ingestion_candidate_ids import (
    command_slug,
    rag_candidate_case_id,
    rag_candidate_slug_from_case_id,
    rag_candidate_workflow_tag,
)


def test_rag_candidate_id_helpers_use_canonical_command_slug_policy() -> None:
    assert command_slug("candidate/needs quoting") == "candidate_needs_quoting"
    assert command_slug("bad.path") == "bad_path"
    assert command_slug("run quote; rm -rf /") == "run_quote_rm_rf"
    assert command_slug(":/") == "item"

    assert rag_candidate_case_id("candidate/needs quoting") == (
        "case_rag_candidate_candidate_needs_quoting"
    )
    assert rag_candidate_workflow_tag("candidate/needs quoting") == (
        "rag-candidate:candidate_needs_quoting"
    )


def test_rag_candidate_slug_from_case_id_rejects_noncanonical_ids() -> None:
    assert rag_candidate_slug_from_case_id("case_rag_candidate_c1") == "c1"
    assert rag_candidate_slug_from_case_id("case_failed_provider") is None
    assert rag_candidate_slug_from_case_id("case_rag_candidate_") is None
    assert rag_candidate_slug_from_case_id("case_rag_candidate_bad/path") is None
    assert rag_candidate_slug_from_case_id("case_rag_candidate_bad.path") is None
