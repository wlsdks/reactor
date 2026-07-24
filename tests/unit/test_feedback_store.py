from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from reactor.persistence.feedback_store import (
    feedback_from_model,
    feedback_upsert_update_values,
    feedback_values,
)
from reactor.persistence.models import Base, FeedbackRecord
from reactor.slack.feedback import Feedback, FeedbackRating


def test_feedback_table_is_registered_with_review_indexes() -> None:
    table = Base.metadata.tables["feedback"]

    assert "ck_feedback_rating" in {constraint.name for constraint in table.constraints}
    assert "ck_feedback_review_status" in {constraint.name for constraint in table.constraints}
    assert "ix_feedback_tenant_created" in {index.name for index in table.indexes}
    assert "ix_feedback_tenant_rating" in {index.name for index in table.indexes}
    assert "ix_feedback_review_status" in {index.name for index in table.indexes}
    assert "ix_feedback_tenant_template_rating" in {index.name for index in table.indexes}


def test_feedback_table_is_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"feedback"' in content
    assert "ck_feedback_rating" in content
    assert "ix_feedback_tenant_rating" in content
    assert "ix_feedback_review_status" in content


def test_feedback_prompt_metadata_is_created_by_followup_migration() -> None:
    migration = "migrations/versions/202606270002_feedback_prompt_metadata.py"
    with open(migration) as file:
        content = file.read()

    assert '"template_id"' in content
    assert '"prompt_version"' in content
    assert '"tools_used"' in content
    assert "ix_feedback_tenant_template_rating" in content


def test_feedback_table_compiles_for_postgres() -> None:
    table = Base.metadata.tables["feedback"]

    sql = str(table.select().compile(dialect=postgresql.dialect()))

    assert "feedback" in sql
    assert "review_status" in sql


def test_feedback_values_preserve_legacy_contract() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    feedback = Feedback(
        feedback_id="fb_1",
        tenant_id="tenant_1",
        query="원래 질문",
        response="답변",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_1",
        user_id="U1",
        comment="틀렸어요",
        intent="support",
        domain="auth",
        model="gpt-4.1-mini",
        prompt_version=2,
        tools_used=["rag.search"],
        duration_ms=321,
        tags=["accuracy"],
        template_id="tmpl-1",
        review_tags=["accuracy"],
        created_at=created_at,
        updated_at=created_at,
    )

    values = feedback_values(feedback)

    assert values["id"] == "fb_1"
    assert values["tenant_id"] == "tenant_1"
    assert values["query"] == "원래 질문"
    assert values["rating"] == "THUMBS_DOWN"
    assert values["session_id"] == "session_1"
    assert values["run_id"] == "run_1"
    assert values["user_id"] == "U1"
    assert values["intent"] == "support"
    assert values["domain"] == "auth"
    assert values["model"] == "gpt-4.1-mini"
    assert values["prompt_version"] == 2
    assert values["tools_used"] == ["rag.search"]
    assert values["duration_ms"] == 321
    assert values["tags"] == ["accuracy"]
    assert values["template_id"] == "tmpl-1"
    assert values["review_status"] == "inbox"
    assert values["review_tags"] == ["accuracy"]


def test_feedback_upsert_update_values_preserve_review_state() -> None:
    now = datetime(2026, 6, 26, tzinfo=UTC)
    feedback = Feedback(
        feedback_id="fb_1",
        tenant_id="tenant_1",
        query="Q",
        response="A replayed",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        user_id="U1",
        source="slack_reaction",
        review_status="inbox",
        review_tags=[],
        reviewed_by=None,
        reviewed_at=None,
        review_note=None,
        version=1,
        created_at=now,
        updated_at=now,
    )

    values = feedback_upsert_update_values(feedback)

    assert values["response"] == "A replayed"
    assert "id" not in values
    assert "created_at" not in values
    assert "review_status" not in values
    assert "review_tags" not in values
    assert "reviewed_by" not in values
    assert "reviewed_at" not in values
    assert "review_note" not in values
    assert "version" not in values


def test_feedback_from_model_maps_row() -> None:
    now = datetime(2026, 6, 26, tzinfo=UTC)
    row = FeedbackRecord(
        id="fb_1",
        tenant_id="tenant_1",
        query="Q",
        response="A",
        rating="THUMBS_UP",
        source="slack_button",
        comment=None,
        session_id="session_1",
        run_id="run_1",
        user_id="U1",
        intent="support",
        domain="auth",
        model="gpt-4.1-mini",
        prompt_version=2,
        tools_used=["rag.search"],
        duration_ms=321,
        tags=["accuracy"],
        template_id="tmpl-1",
        review_status="inbox",
        review_tags=["good"],
        version=1,
        created_at=now,
        updated_at=now,
    )

    feedback = feedback_from_model(row)

    assert feedback.feedback_id == "fb_1"
    assert feedback.rating == FeedbackRating.THUMBS_UP
    assert feedback.template_id == "tmpl-1"
    assert feedback.prompt_version == 2
    assert feedback.tools_used == ["rag.search"]
    assert feedback.review_tags == ["good"]
    assert feedback.created_at == now
