from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from reactor.guards.input import InputGuard, InputGuardBlocked
from reactor.guards.output import OutputGuard, OutputGuardBlocked

DEFAULT_GUARD = object()


@dataclass(frozen=True)
class RedTeamCorpus:
    version: str
    source: str
    cases: tuple[RedTeamCase, ...]

    @classmethod
    def load(cls, path: Path) -> RedTeamCorpus:
        raw = cast(object, json.loads(path.read_text(encoding="utf-8")))
        data = require_dict(raw, "red-team corpus")
        cases = tuple(
            redteam_case_from_json(item) for item in require_list(data.get("cases"), "cases")
        )
        if not cases:
            raise ValueError("red-team corpus must contain at least one case")
        return cls(
            version=str(data.get("version", "")),
            source=str(data.get("source", "")),
            cases=cases,
        )

    @property
    def axes(self) -> frozenset[str]:
        return frozenset(case.axis for case in self.cases)

    def case_by_id(self, case_id: str) -> RedTeamCase:
        for case in self.cases:
            if case.id == case_id:
                return case
        raise KeyError(case_id)

    def select(self, *, case_ids: set[str]) -> RedTeamCorpus:
        return RedTeamCorpus(
            version=self.version,
            source=self.source,
            cases=tuple(case for case in self.cases if case.id in case_ids),
        )


@dataclass(frozen=True)
class RedTeamCase:
    id: str
    axis: str
    input_text: str
    expected: RedTeamExpectation
    simulated_output: str | None = None


@dataclass(frozen=True)
class RedTeamExpectation:
    input_blocked: bool | None = None
    output_blocked: bool | None = None
    block_reason_contains: str | None = None
    max_tools_used: int | None = None


@dataclass(frozen=True)
class RedTeamResult:
    case_id: str
    axis: str
    passed: bool
    reasons: tuple[str, ...]
    observed_blocked: bool
    observed_reason: str
    observed_tools_used: int

    def to_json_dict(self) -> dict[str, object]:
        return {
            "caseId": self.case_id,
            "axis": self.axis,
            "passed": self.passed,
            "reasons": list(self.reasons),
            "observedBlocked": self.observed_blocked,
            "observedReason": self.observed_reason,
            "observedToolsUsed": self.observed_tools_used,
        }


class RedTeamEvaluator:
    def __init__(
        self,
        *,
        input_guard: InputGuard | None | object = DEFAULT_GUARD,
        output_guard: OutputGuard | None | object = DEFAULT_GUARD,
    ) -> None:
        self._input_guard = (
            InputGuard() if input_guard is DEFAULT_GUARD else cast(InputGuard | None, input_guard)
        )
        self._output_guard = (
            OutputGuard()
            if output_guard is DEFAULT_GUARD
            else cast(OutputGuard | None, output_guard)
        )

    def evaluate(self, corpus: RedTeamCorpus) -> list[RedTeamResult]:
        return [self.evaluate_case(case) for case in corpus.cases]

    def evaluate_case(self, case: RedTeamCase) -> RedTeamResult:
        input_blocked, input_reason = self._check_input(case.input_text)
        output_blocked, output_reason = self._check_output(case.simulated_output)
        observed_blocked = input_blocked or output_blocked
        observed_reason = input_reason or output_reason
        observed_tools_used = 0
        reasons = build_reasons(
            case.expected,
            input_blocked=input_blocked,
            output_blocked=output_blocked,
            observed_reason=observed_reason,
            observed_tools_used=observed_tools_used,
        )
        return RedTeamResult(
            case_id=case.id,
            axis=case.axis,
            passed=not reasons,
            reasons=tuple(reasons),
            observed_blocked=observed_blocked,
            observed_reason=observed_reason,
            observed_tools_used=observed_tools_used,
        )

    def _check_input(self, text: str) -> tuple[bool, str]:
        if self._input_guard is None:
            return False, ""
        try:
            self._input_guard.check(text)
        except InputGuardBlocked as error:
            return True, str(error)
        return False, ""

    def _check_output(self, text: str | None) -> tuple[bool, str]:
        if text is None or self._output_guard is None:
            return False, ""
        try:
            self._output_guard.check(text)
        except OutputGuardBlocked as error:
            return True, str(error)
        return False, ""


def build_reasons(
    expected: RedTeamExpectation,
    *,
    input_blocked: bool,
    output_blocked: bool,
    observed_reason: str,
    observed_tools_used: int,
) -> list[str]:
    reasons: list[str] = []
    if expected.input_blocked is True and not input_blocked:
        reasons.append("expected input to be blocked")
    if expected.input_blocked is False and input_blocked:
        reasons.append("expected input to be allowed")
    if expected.output_blocked is True and not output_blocked:
        reasons.append("expected output to be blocked")
    if expected.output_blocked is False and output_blocked:
        reasons.append("expected output to be allowed")
    if (
        expected.block_reason_contains
        and observed_reason
        and expected.block_reason_contains not in observed_reason
    ):
        reasons.append(f"block reason missing '{expected.block_reason_contains}'")
    if expected.max_tools_used is not None and observed_tools_used > expected.max_tools_used:
        reasons.append(
            f"tools used expected<={expected.max_tools_used}, actual={observed_tools_used}"
        )
    return reasons


def redteam_case_from_json(raw: object) -> RedTeamCase:
    data = require_dict(raw, "case")
    expected = expectation_from_json(require_dict(data.get("expected"), "expected"))
    case_id = str(data.get("id", "")).strip()
    axis = str(data.get("axis", "")).strip()
    input_text = str(data.get("input", ""))
    if not case_id:
        raise ValueError("case.id is required")
    if not axis:
        raise ValueError(f"{case_id}.axis is required")
    if not input_text.strip():
        raise ValueError(f"{case_id}.input is required")
    simulated_output = data.get("simulatedOutput")
    return RedTeamCase(
        id=case_id,
        axis=axis,
        input_text=input_text,
        expected=expected,
        simulated_output=str(simulated_output) if simulated_output is not None else None,
    )


def expectation_from_json(data: dict[str, object]) -> RedTeamExpectation:
    max_tools_used = data.get("maxToolsUsed")
    return RedTeamExpectation(
        input_blocked=optional_bool(data.get("inputBlocked")),
        output_blocked=optional_bool(data.get("outputBlocked")),
        block_reason_contains=optional_str(data.get("blockReasonContains")),
        max_tools_used=as_int(max_tools_used) if max_tools_used is not None else None,
    )


def optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise ValueError(f"expected boolean or null, got {value!r}")


def optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def as_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise ValueError(f"expected int-compatible value, got {value!r}")


def require_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def require_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return cast(list[object], value)
