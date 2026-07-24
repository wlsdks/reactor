from __future__ import annotations

from sqlalchemy.dialects import postgresql

from reactor.guards.rules import (
    InputGuardRuleRecord,
    PatternType,
    RuleAction,
    parse_pattern_type,
    parse_rule_action,
)
from reactor.persistence.input_guard_rule_store import (
    build_input_guard_rule_list,
    build_input_guard_rule_update,
    build_input_guard_rule_upsert,
)
from reactor.persistence.models import Base


def test_input_guard_rule_model_is_registered_in_metadata() -> None:
    assert "input_guard_rules" in Base.metadata.tables
    table = Base.metadata.tables["input_guard_rules"]
    assert "ck_input_guard_rules_pattern" in {constraint.name for constraint in table.constraints}
    assert "ck_input_guard_rules_action" in {constraint.name for constraint in table.constraints}


def test_input_guard_rule_upsert_and_update_sql_are_tenant_scoped() -> None:
    rule = InputGuardRuleRecord(
        id="rule_1",
        tenant_id="tenant_1",
        name="Block",
        pattern="ignore previous",
        pattern_type=PatternType.KEYWORD,
        action=RuleAction.BLOCK,
    )

    upsert = str(build_input_guard_rule_upsert(rule).compile(dialect=postgresql.dialect()))
    update = build_input_guard_rule_update(
        tenant_id="tenant_1", rule_id="rule_1", rule=rule
    ).compile(dialect=postgresql.dialect())
    listed = build_input_guard_rule_list(tenant_id="tenant_1").compile(dialect=postgresql.dialect())

    assert "input_guard_rules" in upsert
    assert "ON CONFLICT" in upsert
    assert "input_guard_rules.tenant_id" in str(update)
    assert update.params["tenant_id_1"] == "tenant_1"
    assert listed.params["tenant_id_1"] == "tenant_1"


def test_input_guard_rule_parsers_and_validation() -> None:
    assert parse_pattern_type("regex") == PatternType.REGEX
    assert parse_pattern_type("keyword") == PatternType.KEYWORD
    assert parse_pattern_type("glob") is None
    assert parse_rule_action("block") == RuleAction.BLOCK
    assert parse_rule_action("warn") == RuleAction.WARN
    assert parse_rule_action("flag") == RuleAction.FLAG
    assert parse_rule_action("drop") is None
