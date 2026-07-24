from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
    PIIMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)
from langchain_core.language_models import BaseChatModel

from reactor.core.settings import Settings
from reactor.providers.retry import is_transient_retry_exception

ChatModelSpec = str | BaseChatModel
SAFE_TOOL_RETRY_FAILURE_MESSAGE = '[tool_output:data]\n{"error":"tool_execution_failed"}'


@dataclass(frozen=True)
class PiiMiddlewareRule:
    pii_type: str
    strategy: Literal["block", "redact", "mask", "hash"]
    apply_to_input: bool = True
    apply_to_output: bool = True
    apply_to_tool_results: bool = True
    apply_to_stream_output: bool = True

    def validate(self) -> None:
        if not self.pii_type.strip():
            raise ValueError("pii_type is required")
        if self.strategy not in {"redact", "block", "hash", "mask"}:
            raise ValueError(f"unsupported PII strategy: {self.strategy}")


@dataclass(frozen=True)
class LangChainMiddlewarePolicy:
    model_call_run_limit: int | None = None
    tool_call_run_limit: int | None = None
    model_retry_max_retries: int = 1
    tool_retry_max_retries: int = 1
    pii_rules: tuple[PiiMiddlewareRule, ...] = ()

    def validate(self) -> None:
        for field_name, value in (
            ("model_call_run_limit", self.model_call_run_limit),
            ("tool_call_run_limit", self.tool_call_run_limit),
            ("model_retry_max_retries", self.model_retry_max_retries),
            ("tool_retry_max_retries", self.tool_retry_max_retries),
        ):
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must be non-negative")
        for rule in self.pii_rules:
            rule.validate()


DEFAULT_PII_RULES = (
    PiiMiddlewareRule("email", "redact"),
    PiiMiddlewareRule("url", "redact"),
    PiiMiddlewareRule("ip", "redact"),
    PiiMiddlewareRule("mac_address", "redact"),
    PiiMiddlewareRule("credit_card", "block"),
)
LANGCHAIN_MIDDLEWARE_POLICY_FIELDS = frozenset(
    {
        "modelCallRunLimit",
        "toolCallRunLimit",
        "modelRetryMaxRetries",
        "toolRetryMaxRetries",
        "piiRules",
    }
)
PII_MIDDLEWARE_RULE_FIELDS = frozenset(
    {
        "type",
        "strategy",
        "applyToInput",
        "applyToOutput",
        "applyToToolResults",
        "applyToStreamOutput",
    }
)


def default_langchain_middleware_policy(settings: Settings) -> LangChainMiddlewarePolicy:
    return LangChainMiddlewarePolicy(
        model_call_run_limit=settings.max_tool_calls + 1,
        tool_call_run_limit=settings.max_tool_calls,
        pii_rules=DEFAULT_PII_RULES,
    )


def safe_tool_retry_failure_message(_exception: Exception) -> str:
    return SAFE_TOOL_RETRY_FAILURE_MESSAGE


def langchain_middleware_policy_from_mapping(
    value: Mapping[str, object] | None,
) -> LangChainMiddlewarePolicy | None:
    if value is None:
        return None
    if not set(value).issubset(LANGCHAIN_MIDDLEWARE_POLICY_FIELDS):
        return None
    try:
        policy = LangChainMiddlewarePolicy(
            model_call_run_limit=optional_nonnegative_int(value.get("modelCallRunLimit")),
            tool_call_run_limit=optional_nonnegative_int(value.get("toolCallRunLimit")),
            model_retry_max_retries=nonnegative_int(
                value.get("modelRetryMaxRetries"),
                default=1,
            ),
            tool_retry_max_retries=nonnegative_int(
                value.get("toolRetryMaxRetries"),
                default=1,
            ),
            pii_rules=pii_rules_from_value(value.get("piiRules"), default=DEFAULT_PII_RULES),
        )
        policy.validate()
    except ValueError:
        return None
    return policy


def langchain_middleware_policy_metadata(
    policy: LangChainMiddlewarePolicy,
) -> dict[str, object]:
    return {
        "modelCallRunLimit": policy.model_call_run_limit,
        "toolCallRunLimit": policy.tool_call_run_limit,
        "modelRetryMaxRetries": policy.model_retry_max_retries,
        "toolRetryMaxRetries": policy.tool_retry_max_retries,
        "piiRules": [
            {
                "type": rule.pii_type,
                "strategy": rule.strategy,
                "applyToInput": rule.apply_to_input,
                "applyToOutput": rule.apply_to_output,
                "applyToToolResults": rule.apply_to_tool_results,
                "applyToStreamOutput": rule.apply_to_stream_output,
            }
            for rule in policy.pii_rules
        ],
    }


def optional_nonnegative_int(value: object) -> int | None:
    if value is None:
        return None
    return nonnegative_int(value, default=0)


def nonnegative_int(value: object, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid integer")
    if isinstance(value, int) and value >= 0:
        return value
    raise ValueError("expected non-negative integer")


def pii_rules_from_value(
    value: object,
    *,
    default: tuple[PiiMiddlewareRule, ...],
) -> tuple[PiiMiddlewareRule, ...]:
    if value is None:
        return default
    if not isinstance(value, list):
        raise ValueError("piiRules must be a list")
    if not value:
        raise ValueError("piiRules must contain at least one rule")
    return tuple(pii_rule_from_mapping(item) for item in cast(list[object], value))


def pii_rule_from_mapping(value: object) -> PiiMiddlewareRule:
    if not isinstance(value, Mapping):
        raise ValueError("pii rule must be an object")
    typed_value = cast(Mapping[str, object], value)
    if not set(typed_value).issubset(PII_MIDDLEWARE_RULE_FIELDS):
        raise ValueError("pii rule contains unsupported fields")
    apply_to_output = bool_field(typed_value, "applyToOutput", default=True)
    apply_to_stream_output = bool_field(
        typed_value,
        "applyToStreamOutput",
        default=apply_to_output,
    )
    if apply_to_stream_output != apply_to_output:
        raise ValueError("applyToStreamOutput must match applyToOutput")
    rule = PiiMiddlewareRule(
        pii_type=string_field(typed_value, "type"),
        strategy=pii_strategy_field(typed_value, "strategy"),
        apply_to_input=bool_field(typed_value, "applyToInput", default=True),
        apply_to_output=apply_to_output,
        apply_to_tool_results=bool_field(typed_value, "applyToToolResults", default=True),
        apply_to_stream_output=apply_to_stream_output,
    )
    rule.validate()
    return rule


def string_field(value: Mapping[str, object], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{key} is required")
    return raw.strip()


def pii_strategy_field(
    value: Mapping[str, object],
    key: str,
) -> Literal["block", "redact", "mask", "hash"]:
    raw = string_field(value, key)
    if raw not in {"block", "redact", "mask", "hash"}:
        raise ValueError(f"unsupported PII strategy: {raw}")
    return cast(Literal["block", "redact", "mask", "hash"], raw)


def bool_field(value: Mapping[str, object], key: str, *, default: bool) -> bool:
    raw = value.get(key)
    if raw is None:
        return default
    if not isinstance(raw, bool):
        raise ValueError(f"{key} must be boolean")
    return raw


def build_langchain_agent_middleware(
    settings: Settings,
    *,
    interrupt_on_tools: Sequence[str] = (),
    retry_on_tools: Sequence[str] = (),
    fallback_models: Sequence[ChatModelSpec] = (),
    policy: LangChainMiddlewarePolicy | None = None,
) -> list[object]:
    effective_policy = policy or default_langchain_middleware_policy(settings)
    effective_policy.validate()
    middleware: list[object] = []
    if effective_policy.model_call_run_limit is not None:
        middleware.append(
            ModelCallLimitMiddleware(
                run_limit=effective_policy.model_call_run_limit,
                exit_behavior="error",
            )
        )
    if effective_policy.tool_call_run_limit is not None:
        middleware.append(
            ToolCallLimitMiddleware(
                run_limit=effective_policy.tool_call_run_limit,
                exit_behavior="continue",
            )
        )
    if fallback_models:
        middleware.append(
            ModelFallbackMiddleware(
                fallback_models[0],
                *fallback_models[1:],
            )
        )
    middleware.extend(
        [
            ModelRetryMiddleware(
                max_retries=effective_policy.model_retry_max_retries,
                retry_on=is_transient_retry_exception,
                on_failure="error",
            ),
            ToolRetryMiddleware(
                max_retries=effective_policy.tool_retry_max_retries,
                tools=list(retry_on_tools),
                retry_on=is_transient_retry_exception,
                on_failure=safe_tool_retry_failure_message,
            ),
        ]
    )
    middleware.extend(
        PIIMiddleware(
            rule.pii_type,
            strategy=rule.strategy,
            apply_to_input=rule.apply_to_input,
            apply_to_output=rule.apply_to_output,
            apply_to_tool_results=rule.apply_to_tool_results,
        )
        for rule in effective_policy.pii_rules
    )
    if interrupt_on_tools:
        middleware.append(
            HumanInTheLoopMiddleware(
                interrupt_on={tool_name: True for tool_name in interrupt_on_tools},
            )
        )
    return middleware


def planned_langchain_middleware_names(
    settings: Settings,
    *,
    interrupt_on_tools: Sequence[str] = (),
    fallback_models: Sequence[ChatModelSpec] = (),
    policy: LangChainMiddlewarePolicy | None = None,
) -> list[str]:
    effective_policy = policy or default_langchain_middleware_policy(settings)
    effective_policy.validate()
    names: list[str] = []
    if effective_policy.model_call_run_limit is not None:
        names.append("ModelCallLimitMiddleware")
    if effective_policy.tool_call_run_limit is not None:
        names.append("ToolCallLimitMiddleware")
    if fallback_models:
        names.append("ModelFallbackMiddleware")
    names.extend(["ModelRetryMiddleware", "ToolRetryMiddleware"])
    names.extend("PIIMiddleware" for _ in effective_policy.pii_rules)
    if interrupt_on_tools:
        names.append("HumanInTheLoopMiddleware")
    return names
