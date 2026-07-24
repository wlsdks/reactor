from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from reactor.kernel.ids import new_id

DEFAULT_REPLACEMENT = "[REDACTED]"


class OutputGuardRuleAction(StrEnum):
    MASK = "MASK"
    REJECT = "REJECT"


@dataclass(frozen=True)
class OutputGuardRuleRecord:
    id: str = field(default_factory=lambda: new_id("output_guard_rule"))
    tenant_id: str = "global"
    name: str = ""
    pattern: str = ""
    action: OutputGuardRuleAction = OutputGuardRuleAction.MASK
    replacement: str = DEFAULT_REPLACEMENT
    priority: int = 100
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not self.name.strip():
            raise ValueError("name is required")
        if len(self.name) > 120:
            raise ValueError("name must not exceed 120 characters")
        if not self.pattern.strip():
            raise ValueError("pattern is required")
        if len(self.pattern) > 5000:
            raise ValueError("pattern must not exceed 5000 characters")
        if len(self.replacement) > 256:
            raise ValueError("replacement must not exceed 256 characters")
        if not 1 <= self.priority <= 10_000:
            raise ValueError("priority must be between 1 and 10000")
        validate_regex_pattern(self.pattern)


class OutputGuardRuleAuditAction(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SIMULATE = "SIMULATE"


@dataclass(frozen=True)
class OutputGuardRuleAuditRecord:
    id: str = field(default_factory=lambda: new_id("output_guard_rule_audit"))
    tenant_id: str = "global"
    rule_id: str | None = None
    action: OutputGuardRuleAuditAction = OutputGuardRuleAuditAction.SIMULATE
    actor: str = "anonymous"
    detail: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class OutputGuardRuleMatch:
    rule_id: str
    rule_name: str
    action: OutputGuardRuleAction
    priority: int


@dataclass(frozen=True)
class InvalidOutputGuardRule:
    rule_id: str
    rule_name: str
    reason: str


@dataclass(frozen=True)
class OutputGuardEvaluation:
    blocked: bool
    content: str
    matched_rules: tuple[OutputGuardRuleMatch, ...] = ()
    blocked_by: OutputGuardRuleMatch | None = None
    invalid_rules: tuple[InvalidOutputGuardRule, ...] = ()

    @property
    def modified(self) -> bool:
        return (not self.blocked) and any(
            match.action == OutputGuardRuleAction.MASK for match in self.matched_rules
        )


class OutputGuardRuleEvaluator:
    def evaluate(
        self,
        *,
        content: str,
        rules: list[OutputGuardRuleRecord],
    ) -> OutputGuardEvaluation:
        if not rules:
            return OutputGuardEvaluation(blocked=False, content=content)

        result = content
        matched: list[OutputGuardRuleMatch] = []
        invalid: list[InvalidOutputGuardRule] = []

        for rule in rules:
            try:
                regex = re.compile(rule.pattern)
            except re.error:
                invalid.append(
                    InvalidOutputGuardRule(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        reason="invalid regex",
                    )
                )
                continue
            if regex.search(result) is None:
                continue
            rule_match = OutputGuardRuleMatch(
                rule_id=rule.id,
                rule_name=rule.name,
                action=rule.action,
                priority=rule.priority,
            )
            matched.append(rule_match)
            if rule.action == OutputGuardRuleAction.REJECT:
                return OutputGuardEvaluation(
                    blocked=True,
                    content=result,
                    matched_rules=tuple(matched),
                    blocked_by=rule_match,
                    invalid_rules=tuple(invalid),
                )
            result = regex.sub(rule.replacement, result)

        return OutputGuardEvaluation(
            blocked=False,
            content=result,
            matched_rules=tuple(matched),
            invalid_rules=tuple(invalid),
        )


def parse_output_guard_action(value: str) -> OutputGuardRuleAction | None:
    try:
        return OutputGuardRuleAction(value.strip().upper())
    except ValueError:
        return None


def validate_regex_pattern(pattern: str) -> None:
    try:
        re.compile(pattern)
    except re.error as error:
        raise ValueError("invalid regex pattern") from error
