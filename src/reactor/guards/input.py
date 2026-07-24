from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from reactor.guards.rules import InputGuardRuleRecord, PatternType, RuleAction
from reactor.runtime_settings.service import (
    GLOBAL_TENANT_ID,
    RuntimeSettingRecord,
    RuntimeSettingsResolver,
)

PROMPT_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"forget\s+everything\s+above", re.IGNORECASE),
    re.compile(r"reveal\s+(the\s+)?system\s+prompt", re.IGNORECASE),
    re.compile(r"system\s+prompt\s+dump", re.IGNORECASE),
    re.compile(r"\bsystem\s*:\s*override\s+safety\s+mode\b", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a\s+hacker\s+assistant", re.IGNORECASE),
    re.compile(r"you\s+are\s+no\s+longer\s+an\s+ai\s+assistant", re.IGNORECASE),
    re.compile(r"from\s+now\s+on.*\bDAN\b", re.IGNORECASE),
    re.compile(r"\b(do\s+anything\s+now|act\s+as\s+DAN|DAN\s+mode)\b", re.IGNORECASE),
    re.compile(
        r"(enter|switch|enable|activate).*(developer|jailbreak).*(mode|filters)", re.IGNORECASE
    ),
    re.compile(r"이전\s*지시\s*무시"),
    re.compile(r"시스템\s*프롬프트"),
    re.compile(r"너는\s*이제부터\s*chatgpt", re.IGNORECASE),
    re.compile(r"\[admin\].*(규칙|권한).*(무시|bypass)", re.IGNORECASE),
)

HIGH_SENSITIVITY_PROMPT_INJECTION_PATTERNS = (
    *PROMPT_INJECTION_PATTERNS,
    re.compile(r"\b(jailbreak|bypass|developer\s+message|hidden\s+instructions)\b", re.IGNORECASE),
    re.compile(r"(정책|보안|가드).*(우회|무시)"),
)

INPUT_VALIDATION_STAGE = "InputValidation"
INJECTION_DETECTION_STAGE = "InjectionDetection"
CUSTOM_RULE_STAGE = "DynamicRule"
DEFAULT_STAGE_ORDER = (INPUT_VALIDATION_STAGE, INJECTION_DETECTION_STAGE)
IGNORED_FORMAT_CHARACTERS = {
    "\u200b",
    "\u200c",
    "\u200d",
    "\ufeff",
    "\u00ad",
}
ACTION_ALLOWED = "allowed"
ACTION_REJECTED = "rejected"


class InputGuardBlocked(ValueError):
    def __init__(self, reason: str, *, metadata: dict[str, object] | None = None) -> None:
        self.reason = reason
        self.metadata = {
            "stage": "input_guard",
            "reason": reason,
            **(metadata or {}),
        }
        super().__init__(reason)

    def as_metadata(self) -> dict[str, object]:
        return dict(self.metadata)


class InputGuardRuleStore(Protocol):
    async def find_all(self, *, tenant_id: str) -> list[InputGuardRuleRecord]: ...


class RuntimeSettingsStore(Protocol):
    async def list(self, *, tenant_id: str | None = None) -> Sequence[RuntimeSettingRecord]: ...


class InputGuardMetricSink(Protocol):
    async def record(self, record: InputGuardMetricRecord) -> None: ...


@dataclass(frozen=True)
class InputGuardRuntimePolicy:
    enabled: bool = True
    input_validation_enabled: bool = True
    injection_detection_enabled: bool = True
    stage_order: tuple[str, ...] = DEFAULT_STAGE_ORDER
    min_length: int = 1
    max_length: int = 10_000
    sensitivity_level: str = "medium"


@dataclass(frozen=True)
class InputGuardStageEvaluation:
    stage: str
    passed: bool
    reason: str | None = None
    category: str | None = None


@dataclass(frozen=True)
class InputGuardEvaluation:
    passed: bool
    blocking_stage: str | None
    blocking_reason: str | None
    stage_results: tuple[InputGuardStageEvaluation, ...]


@dataclass(frozen=True)
class InputGuardMetricRecord:
    tenant_id: str
    user_id: str | None
    channel: str
    stage: str
    category: str | None
    reason_class: str | None
    reason_detail: str | None
    action: str


class InputGuard:
    def __init__(
        self,
        dynamic_rule_store: InputGuardRuleStore | None = None,
        runtime_settings_store: RuntimeSettingsStore | None = None,
        metric_sink: InputGuardMetricSink | None = None,
    ) -> None:
        self._dynamic_rule_store = dynamic_rule_store
        self._runtime_settings_store = runtime_settings_store
        self._metric_sink = metric_sink

    def check(self, text: str) -> None:
        check_text_with_policy(text, InputGuardRuntimePolicy())

    async def evaluate_async(
        self,
        text: str,
        *,
        tenant_id: str = "global",
    ) -> InputGuardEvaluation:
        policy = await self._runtime_policy(tenant_id=tenant_id)
        if not policy.enabled:
            return InputGuardEvaluation(
                passed=True,
                blocking_stage=None,
                blocking_reason=None,
                stage_results=(),
            )
        return evaluate_text_with_policy(text, policy)

    async def check_async(
        self,
        text: str,
        *,
        tenant_id: str = "global",
        user_id: str | None = None,
        channel: str = "agent",
    ) -> None:
        evaluation = await self.evaluate_async(text, tenant_id=tenant_id)
        await self._record_stage_metrics(
            evaluation,
            tenant_id=tenant_id,
            user_id=user_id,
            channel=channel,
        )
        if not evaluation.passed:
            raise InputGuardBlocked(evaluation.blocking_reason or "input_guard_blocked")
        if not evaluation.stage_results:
            return
        if self._dynamic_rule_store is None:
            return
        for rule in await self._dynamic_rule_store.find_all(tenant_id=tenant_id):
            rule.validate()
            if not rule.enabled or not custom_rule_matches(rule, text):
                continue
            if rule.action == RuleAction.BLOCK:
                await self._record_metric(
                    InputGuardMetricRecord(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        channel=channel,
                        stage=CUSTOM_RULE_STAGE,
                        category=rule.category,
                        reason_class=rule.category,
                        reason_detail=rule.name,
                        action=ACTION_REJECTED,
                    )
                )
                raise InputGuardBlocked(f"custom_rule:{rule.name}")

    async def _record_stage_metrics(
        self,
        evaluation: InputGuardEvaluation,
        *,
        tenant_id: str,
        user_id: str | None,
        channel: str,
    ) -> None:
        for result in evaluation.stage_results:
            await self._record_metric(
                InputGuardMetricRecord(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    channel=channel,
                    stage=result.stage,
                    category=result.category or stage_category(result.stage),
                    reason_class=result.category if not result.passed else None,
                    reason_detail=result.reason,
                    action=ACTION_ALLOWED if result.passed else ACTION_REJECTED,
                )
            )

    async def _record_metric(self, record: InputGuardMetricRecord) -> None:
        if self._metric_sink is None:
            return
        try:
            await self._metric_sink.record(record)
        except Exception:
            return

    async def _runtime_policy(self, *, tenant_id: str) -> InputGuardRuntimePolicy:
        if self._runtime_settings_store is None:
            return InputGuardRuntimePolicy()
        try:
            records = list(await self._runtime_settings_store.list(tenant_id=tenant_id))
            if tenant_id != GLOBAL_TENANT_ID:
                records = [
                    *(await self._runtime_settings_store.list(tenant_id=GLOBAL_TENANT_ID)),
                    *records,
                ]
            resolver = RuntimeSettingsResolver(records)
            policy = InputGuardRuntimePolicy(
                enabled=resolver.get_boolean("guard.enabled", True, tenant_id=tenant_id),
                input_validation_enabled=resolver.get_boolean(
                    "guard.stage.InputValidation.enabled",
                    True,
                    tenant_id=tenant_id,
                ),
                injection_detection_enabled=resolver.get_boolean(
                    "guard.stage.InjectionDetection.enabled",
                    True,
                    tenant_id=tenant_id,
                ),
                stage_order=resolve_stage_order(resolver, tenant_id=tenant_id),
                min_length=resolver.get_int(
                    "guard.stage.InputValidation.minLength",
                    1,
                    tenant_id=tenant_id,
                ),
                max_length=resolver.get_int(
                    "guard.stage.InputValidation.maxLength",
                    10_000,
                    tenant_id=tenant_id,
                ),
                sensitivity_level=resolver.get_string(
                    "guard.stage.InjectionDetection.sensitivityLevel",
                    "medium",
                    tenant_id=tenant_id,
                ),
            )
            validate_runtime_policy(policy)
            return policy
        except Exception as error:
            raise InputGuardBlocked("runtime_settings_unavailable") from error


def custom_rule_matches(rule: InputGuardRuleRecord, text: str) -> bool:
    if rule.pattern_type == PatternType.KEYWORD:
        return rule.pattern.casefold() in text.casefold()
    return re.search(rule.pattern, text, re.IGNORECASE) is not None


def check_text_with_policy(text: str, policy: InputGuardRuntimePolicy) -> None:
    evaluation = evaluate_text_with_policy(text, policy)
    if not evaluation.passed:
        raise InputGuardBlocked(evaluation.blocking_reason or "input_guard_blocked")


def evaluate_text_with_policy(text: str, policy: InputGuardRuntimePolicy) -> InputGuardEvaluation:
    validate_runtime_policy(policy)
    stage_results: list[InputGuardStageEvaluation] = []
    for stage in policy.stage_order:
        result = evaluate_stage(stage, text, policy)
        stage_results.append(result)
        if not result.passed:
            return InputGuardEvaluation(
                passed=False,
                blocking_stage=result.stage,
                blocking_reason=result.reason,
                stage_results=tuple(stage_results),
            )
    return InputGuardEvaluation(
        passed=True,
        blocking_stage=None,
        blocking_reason=None,
        stage_results=tuple(stage_results),
    )


def evaluate_stage(
    stage: str,
    text: str,
    policy: InputGuardRuntimePolicy,
) -> InputGuardStageEvaluation:
    try:
        if stage == INPUT_VALIDATION_STAGE:
            check_input_validation_stage(text, policy)
        elif stage == INJECTION_DETECTION_STAGE:
            check_injection_detection_stage(text, policy)
    except InputGuardBlocked as error:
        return InputGuardStageEvaluation(
            stage=stage,
            passed=False,
            reason=str(error),
            category=stage_category(stage),
        )
    return InputGuardStageEvaluation(stage=stage, passed=True)


def check_input_validation_stage(text: str, policy: InputGuardRuntimePolicy) -> None:
    if not policy.input_validation_enabled:
        return
    if len(text) < policy.min_length:
        raise InputGuardBlocked("input_too_short")
    if len(text) > policy.max_length:
        raise InputGuardBlocked("input_too_long")


def check_injection_detection_stage(text: str, policy: InputGuardRuntimePolicy) -> None:
    if not policy.injection_detection_enabled:
        return
    normalized = normalize_guard_text(text)
    if prompt_injection_detected(normalized, sensitivity_level=policy.sensitivity_level):
        raise InputGuardBlocked("prompt_injection")


def normalize_guard_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(
        character for character in normalized if character not in IGNORED_FORMAT_CHARACTERS
    )


def prompt_injection_detected(text: str, *, sensitivity_level: str) -> bool:
    patterns = (
        HIGH_SENSITIVITY_PROMPT_INJECTION_PATTERNS
        if sensitivity_level == "high"
        else PROMPT_INJECTION_PATTERNS
    )
    return any(pattern.search(text) for pattern in patterns)


def validate_runtime_policy(policy: InputGuardRuntimePolicy) -> None:
    if set(policy.stage_order) != set(DEFAULT_STAGE_ORDER):
        raise ValueError("input guard stage order must include all known stages")
    if len(policy.stage_order) != len(DEFAULT_STAGE_ORDER):
        raise ValueError("input guard stage order must not contain duplicates")
    if policy.min_length < 0:
        raise ValueError("InputValidation.minLength must be greater than or equal to 0")
    if policy.max_length < policy.min_length:
        raise ValueError("InputValidation.maxLength must be greater than or equal to minLength")
    if policy.sensitivity_level not in {"low", "medium", "high"}:
        raise ValueError("InjectionDetection.sensitivityLevel must be low, medium, or high")


def stage_category(stage: str) -> str:
    if stage == INPUT_VALIDATION_STAGE:
        return "input_validation"
    if stage == INJECTION_DETECTION_STAGE:
        return "prompt_injection"
    return "other"


def resolve_stage_order(
    resolver: RuntimeSettingsResolver,
    *,
    tenant_id: str,
) -> tuple[str, ...]:
    stage_indexes = {
        INPUT_VALIDATION_STAGE: resolver.get_int(
            "guard.stage.InputValidation.order",
            0,
            tenant_id=tenant_id,
        ),
        INJECTION_DETECTION_STAGE: resolver.get_int(
            "guard.stage.InjectionDetection.order",
            1,
            tenant_id=tenant_id,
        ),
    }
    return tuple(
        stage
        for stage, _ in sorted(
            stage_indexes.items(),
            key=lambda item: (item[1], DEFAULT_STAGE_ORDER.index(item[0])),
        )
    )
