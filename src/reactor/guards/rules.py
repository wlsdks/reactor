from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from reactor.kernel.ids import new_id


class PatternType(StrEnum):
    REGEX = "regex"
    KEYWORD = "keyword"


class RuleAction(StrEnum):
    BLOCK = "block"
    WARN = "warn"
    FLAG = "flag"


@dataclass(frozen=True)
class InputGuardRuleRecord:
    id: str = field(default_factory=lambda: new_id("input_guard_rule"))
    tenant_id: str = "global"
    name: str = ""
    pattern: str = ""
    pattern_type: PatternType = PatternType.REGEX
    action: RuleAction = RuleAction.BLOCK
    priority: int = 100
    category: str = "custom"
    description: str | None = None
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not self.name.strip():
            raise ValueError("name is required")
        if not self.pattern.strip():
            raise ValueError("pattern is required")
        if not 0 <= self.priority <= 10_000:
            raise ValueError("priority must be between 0 and 10000")
        if not self.category.strip():
            raise ValueError("category is required")
        if self.pattern_type == PatternType.REGEX:
            validate_regex_pattern(self.pattern)


def parse_pattern_type(value: str) -> PatternType | None:
    try:
        return PatternType(value.strip().lower())
    except ValueError:
        return None


def parse_rule_action(value: str) -> RuleAction | None:
    try:
        return RuleAction(value.strip().lower())
    except ValueError:
        return None


def validate_regex_pattern(pattern: str) -> None:
    try:
        re.compile(pattern)
    except re.error as error:
        raise ValueError("invalid regex pattern") from error
