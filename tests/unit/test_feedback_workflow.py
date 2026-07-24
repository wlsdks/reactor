from reactor.feedback.workflow import feedback_review_closed
from reactor.rag.ingestion_candidate_actions import RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE


def test_feedback_review_closed_requires_done_promoted_langsmith_and_canonical_note() -> None:
    assert feedback_review_closed(
        {
            "reviewStatus": "done",
            "reviewTags": ["promoted", "langsmith", "rag-candidate:c1"],
            "reviewNote": RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
        }
    )
    assert not feedback_review_closed(
        {
            "reviewStatus": "done",
            "reviewTags": ["promoted", "rag-candidate:c1"],
            "reviewNote": RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
        }
    )
    assert not feedback_review_closed(
        {
            "reviewStatus": "done",
            "reviewTags": ["promoted", "langsmith"],
            "reviewNote": "Reviewed hardening_suite and langsmith_eval_sync evidence.",
        }
    )
    assert not feedback_review_closed(
        {
            "reviewStatus": "inbox",
            "reviewTags": ["promoted", "langsmith"],
            "reviewNote": RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
        }
    )
    assert not feedback_review_closed(
        {
            "reviewStatus": "done",
            "reviewTags": ["promoted", "langsmith", ""],
            "reviewNote": RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
        }
    )
    assert not feedback_review_closed(
        {
            "reviewStatus": "done",
            "reviewTags": ["promoted", "langsmith", 123],
            "reviewNote": RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
        }
    )
