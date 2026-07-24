from __future__ import annotations

from sqlalchemy.dialects import postgresql

from reactor.guards.output_rules import (
    OutputGuardRuleAction,
    OutputGuardRuleEvaluator,
    OutputGuardRuleRecord,
    parse_output_guard_action,
)
from reactor.persistence.models import Base
from reactor.persistence.output_guard_rule_store import (
    build_output_guard_rule_list,
    build_output_guard_rule_update,
    build_output_guard_rule_upsert,
)


def test_output_guard_rule_model_is_registered_in_metadata() -> None:
    assert "output_guard_rules" in Base.metadata.tables
    assert "output_guard_rule_audits" in Base.metadata.tables
    rule_table = Base.metadata.tables["output_guard_rules"]
    audit_table = Base.metadata.tables["output_guard_rule_audits"]

    assert "ck_output_guard_rules_action" in {
        constraint.name for constraint in rule_table.constraints
    }
    assert "ck_output_guard_rule_audits_action" in {
        constraint.name for constraint in audit_table.constraints
    }


def test_output_guard_rule_upsert_update_and_list_are_tenant_scoped() -> None:
    rule = OutputGuardRuleRecord(
        id="rule_1",
        tenant_id="tenant_1",
        name="Mask token",
        pattern=r"token-\d+",
        action=OutputGuardRuleAction.MASK,
    )

    upsert = str(build_output_guard_rule_upsert(rule).compile(dialect=postgresql.dialect()))
    update = build_output_guard_rule_update(
        tenant_id="tenant_1", rule_id="rule_1", rule=rule
    ).compile(dialect=postgresql.dialect())
    listed = build_output_guard_rule_list(tenant_id="tenant_1", include_disabled=False).compile(
        dialect=postgresql.dialect()
    )

    assert "output_guard_rules" in upsert
    assert "ON CONFLICT" in upsert
    assert "output_guard_rules.tenant_id" in str(update)
    assert update.params["tenant_id_1"] == "tenant_1"
    assert listed.params["tenant_id_1"] == "tenant_1"


def test_output_guard_rule_evaluator_masks_then_rejects_by_priority_order() -> None:
    evaluator = OutputGuardRuleEvaluator()
    rules = [
        OutputGuardRuleRecord(
            id="mask",
            name="Mask account",
            pattern=r"acct-\d+",
            action=OutputGuardRuleAction.MASK,
            replacement="[ACCOUNT]",
            priority=1,
        ),
        OutputGuardRuleRecord(
            id="reject",
            name="Reject secret",
            pattern="do-not-send",
            action=OutputGuardRuleAction.REJECT,
            priority=2,
        ),
    ]

    masked = evaluator.evaluate(content="acct-123 is safe", rules=rules)
    rejected = evaluator.evaluate(content="acct-123 do-not-send", rules=rules)

    assert masked.blocked is False
    assert masked.modified is True
    assert masked.content == "[ACCOUNT] is safe"
    assert [match.rule_id for match in masked.matched_rules] == ["mask"]
    assert rejected.blocked is True
    assert rejected.content == "[ACCOUNT] do-not-send"
    assert rejected.blocked_by is not None
    assert rejected.blocked_by.rule_id == "reject"


def test_output_guard_rule_parses_only_legacy_actions() -> None:
    assert parse_output_guard_action("mask") == OutputGuardRuleAction.MASK
    assert parse_output_guard_action("REJECT") == OutputGuardRuleAction.REJECT
    assert parse_output_guard_action("BLOCK") is None
