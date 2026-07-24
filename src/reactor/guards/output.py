from __future__ import annotations

import re
from typing import Protocol

from reactor.guards.output_rules import OutputGuardRuleEvaluator, OutputGuardRuleRecord

SECRET_PATTERN = re.compile(
    r"\b(?:(?:sk|xox[baprs])-[-A-Za-z0-9_]{8,}|gh[pousr]_[A-Za-z0-9_]{20,})\b"
)
CANARY_SECRET_PATTERN = re.compile(r"\bREACTOR_CANARY_SECRET_[A-Z0-9_]+\b")
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CREDIT_CARD_CANDIDATE_PATTERN = re.compile(r"\b(?:\d[ -]?){13,19}\b")


class OutputGuardBlocked(ValueError):
    def __init__(self, reason: str, *, metadata: dict[str, object] | None = None) -> None:
        self.reason = reason
        self.metadata = {
            "stage": "output_guard",
            "reason": reason,
            **(metadata or {}),
        }
        super().__init__(reason)

    def as_metadata(self) -> dict[str, object]:
        return dict(self.metadata)


class OutputGuardRuleStore(Protocol):
    async def list(
        self, *, tenant_id: str, include_disabled: bool = True
    ) -> list[OutputGuardRuleRecord]: ...


class OutputGuard:
    def __init__(self, dynamic_rule_store: OutputGuardRuleStore | None = None) -> None:
        self._dynamic_rule_store = dynamic_rule_store
        self._evaluator = OutputGuardRuleEvaluator()

    def check(self, text: str) -> None:
        if SECRET_PATTERN.search(text):
            raise OutputGuardBlocked("secret_leak")
        if CANARY_SECRET_PATTERN.search(text):
            raise OutputGuardBlocked("canary_secret")
        if SSN_PATTERN.search(text):
            raise OutputGuardBlocked("pii_leak")
        if contains_luhn_valid_card_number(text):
            raise OutputGuardBlocked("pii_leak")

    async def check_async(self, text: str, *, tenant_id: str) -> str:
        self.check(text)
        if self._dynamic_rule_store is None:
            return text
        rules = await self._dynamic_rule_store.list(
            tenant_id=tenant_id,
            include_disabled=False,
        )
        evaluation = self._evaluator.evaluate(content=text, rules=rules)
        if evaluation.blocked:
            blocked_by = evaluation.blocked_by.rule_name if evaluation.blocked_by else "unknown"
            raise OutputGuardBlocked(f"dynamic_rule:{blocked_by}")
        return evaluation.content


def contains_luhn_valid_card_number(text: str) -> bool:
    for match in CREDIT_CARD_CANDIDATE_PATTERN.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if 13 <= len(digits) <= 19 and luhn_valid(digits):
            return True
    return False


def luhn_valid(digits: str) -> bool:
    checksum = 0
    parity = len(digits) % 2
    for index, character in enumerate(digits):
        value = int(character)
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        checksum += value
    return checksum % 10 == 0
