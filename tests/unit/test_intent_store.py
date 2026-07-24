from __future__ import annotations

from sqlalchemy.dialects import postgresql

from reactor.guards.intents import IntentDefinition
from reactor.persistence.intent_store import build_intent_upsert
from reactor.persistence.models import Base


def test_intent_definition_model_is_registered_in_metadata() -> None:
    assert "intent_definitions" in Base.metadata.tables
    table = Base.metadata.tables["intent_definitions"]
    assert "ix_intent_definitions_enabled" in {index.name for index in table.indexes}


def test_intent_definition_table_is_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"intent_definitions"' in content
    assert "ix_intent_definitions_enabled" in content


def test_intent_upsert_uses_name_conflict() -> None:
    statement = build_intent_upsert(
        IntentDefinition(
            name="support_ticket",
            description="Support ticket classifier",
            examples=("create a ticket",),
            keywords=("ticket",),
            profile="support",
        )
    )
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "intent_definitions" in sql
    assert "ON CONFLICT" in sql
    assert "name" in sql
    assert compiled.params["name"] == "support_ticket"
    assert compiled.params["description"] == "Support ticket classifier"
    assert compiled.params["examples"] == ["create a ticket"]
    assert compiled.params["keywords"] == ["ticket"]
