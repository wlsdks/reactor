from __future__ import annotations

from sqlalchemy.dialects import postgresql

from reactor.persistence.models import Base
from reactor.persistence.persona_store import (
    build_persona_list,
    build_persona_upsert,
    clear_default_personas,
)
from reactor.prompts.personas import PersonaRecord, resolve_nullable_field


def test_persona_model_is_registered_in_metadata() -> None:
    assert "personas" in Base.metadata.tables
    table = Base.metadata.tables["personas"]
    assert "ix_personas_active_created" in {index.name for index in table.indexes}
    assert "idx_personas_single_default" in {index.name for index in table.indexes}


def test_persona_table_is_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"personas"' in content
    assert "ix_personas_active_created" in content
    assert "idx_personas_single_default" in content
    assert "prompt_template_id" in content


def test_persona_upsert_active_list_and_clear_default_sql() -> None:
    record = PersonaRecord(
        id="persona_1",
        name="Support",
        system_prompt="Support prompt",
        is_default=True,
        prompt_template_id="template-1",
    )

    upsert = build_persona_upsert(record).compile(dialect=postgresql.dialect())
    active_list = build_persona_list(active=True).compile(dialect=postgresql.dialect())
    clear_default = clear_default_personas().compile(dialect=postgresql.dialect())

    assert "personas" in str(upsert)
    assert "ON CONFLICT" in str(upsert)
    assert upsert.params["id"] == "persona_1"
    assert upsert.params["system_prompt"] == "Support prompt"
    assert upsert.params["is_default"] is True
    assert upsert.params["prompt_template_id"] == "template-1"
    assert "personas.is_active IS true" in str(active_list)
    assert "UPDATE personas SET is_default" in str(clear_default)
    assert "personas.is_default IS true" in str(clear_default)


def test_persona_nullable_update_contract_matches_legacy_store() -> None:
    assert resolve_nullable_field(None, "existing") == "existing"
    assert resolve_nullable_field("", "existing") is None
    assert resolve_nullable_field("new", "existing") == "new"
