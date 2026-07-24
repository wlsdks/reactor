from __future__ import annotations

from sqlalchemy.dialects import postgresql

from reactor.agents.specs import AgentSpecMode, AgentSpecRecord, parse_agent_spec_mode
from reactor.persistence.agent_spec_store import build_agent_spec_list, build_agent_spec_upsert
from reactor.persistence.models import Base


def test_agent_spec_model_is_registered_in_metadata() -> None:
    assert "agent_specs" in Base.metadata.tables
    table = Base.metadata.tables["agent_specs"]
    assert "ck_agent_specs_mode" in {constraint.name for constraint in table.constraints}
    assert "uq_agent_specs_name" in {constraint.name for constraint in table.constraints}
    assert "ix_agent_specs_enabled" in {index.name for index in table.indexes}


def test_agent_spec_table_is_created_by_baseline_migration() -> None:
    migration = "migrations/versions/202606260001_initial_agent_runs.py"
    with open(migration) as file:
        content = file.read()

    assert '"agent_specs"' in content
    assert "ck_agent_specs_mode" in content
    assert "uq_agent_specs_name" in content
    assert "ix_agent_specs_enabled" in content


def test_agent_spec_upsert_and_enabled_list_sql() -> None:
    record = AgentSpecRecord(
        id="spec_1",
        name="translator",
        tool_names=("translate",),
        keywords=("translation",),
        mode=AgentSpecMode.PLAN_EXECUTE,
    )

    upsert = build_agent_spec_upsert(record).compile(dialect=postgresql.dialect())
    enabled = build_agent_spec_list(enabled=True).compile(dialect=postgresql.dialect())

    assert "agent_specs" in str(upsert)
    assert "ON CONFLICT" in str(upsert)
    assert upsert.params["id"] == "spec_1"
    assert upsert.params["tool_names"] == ["translate"]
    assert upsert.params["keywords"] == ["translation"]
    assert upsert.params["mode"] == "PLAN_EXECUTE"
    assert "agent_specs.enabled IS true" in str(enabled)


def test_agent_spec_mode_parser_matches_legacy_modes() -> None:
    assert parse_agent_spec_mode(None) == AgentSpecMode.REACT
    assert parse_agent_spec_mode("REACT") == AgentSpecMode.REACT
    assert parse_agent_spec_mode("STANDARD") == AgentSpecMode.STANDARD
    assert parse_agent_spec_mode("PLAN_EXECUTE") == AgentSpecMode.PLAN_EXECUTE
    assert parse_agent_spec_mode("react") is None
    assert parse_agent_spec_mode("INVALID") is None
