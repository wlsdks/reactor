from __future__ import annotations

from collections.abc import Iterator
from typing import Any, ClassVar, cast

import pytest
from langchain.agents import create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    PIIMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool

from reactor.agents.langchain_middleware import (
    LangChainMiddlewarePolicy,
    PiiMiddlewareRule,
    build_langchain_agent_middleware,
    is_transient_retry_exception,
    langchain_middleware_policy_from_mapping,
)
from reactor.core.settings import Settings
from reactor.tools.catalog import ToolSpec
from reactor.tools.execution import ToolExecutionRequest, ToolExecutionResult, ToolPolicy
from reactor.tools.langchain_adapter import build_langchain_tool


class SequencedChatModel(GenericFakeChatModel):
    invocation_log: ClassVar[list[str]] = []
    label: str
    outcomes: list[object]

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        _ = messages, stop, run_manager, kwargs
        self.invocation_log.append(self.label)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, AIMessage)
        return ChatResult(generations=[ChatGeneration(message=outcome)])


class ToolFailureObservingChatModel(GenericFakeChatModel):
    observed_tool_content: ClassVar[str | None] = None
    invocation_count: int = 0
    requested_tool_name: str = "unstable_tool"

    def bind_tools(
        self,
        tools: Any,
        *,
        tool_choice: object | None = None,
        **kwargs: Any,
    ) -> ToolFailureObservingChatModel:
        _ = tools, tool_choice, kwargs
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        _ = stop, run_manager, kwargs
        self.invocation_count += 1
        if self.invocation_count == 1:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": self.requested_tool_name,
                        "args": {},
                        "id": "call_unstable",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            tool_message = next(
                message for message in reversed(messages) if isinstance(message, ToolMessage)
            )
            assert isinstance(tool_message.content, str)
            ToolFailureObservingChatModel.observed_tool_content = tool_message.content
            message = AIMessage(content="handled")
        return ChatResult(generations=[ChatGeneration(message=message)])


class StatusCodeError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


def test_retry_exception_policy_uses_transient_failures_only() -> None:
    assert is_transient_retry_exception(TimeoutError()) is True
    assert is_transient_retry_exception(ConnectionError()) is True
    assert is_transient_retry_exception(StatusCodeError(429)) is True
    assert is_transient_retry_exception(StatusCodeError(503)) is True
    assert is_transient_retry_exception(StatusCodeError(401)) is False
    assert is_transient_retry_exception(StatusCodeError(600)) is False
    assert is_transient_retry_exception(ValueError("invalid request")) is False


def test_build_langchain_agent_middleware_uses_official_safety_and_limit_middleware() -> None:
    middleware = build_langchain_agent_middleware(
        Settings(max_tool_calls=3),
        interrupt_on_tools=["DangerousServer:delete_file"],
    )

    assert [type(item) for item in middleware] == [
        ModelCallLimitMiddleware,
        ToolCallLimitMiddleware,
        ModelRetryMiddleware,
        ToolRetryMiddleware,
        PIIMiddleware,
        PIIMiddleware,
        PIIMiddleware,
        PIIMiddleware,
        PIIMiddleware,
        HumanInTheLoopMiddleware,
    ]
    pii_middleware = [
        cast(PIIMiddleware[Any, Any], item)
        for item in middleware
        if isinstance(item, PIIMiddleware)
    ]
    assert [(item.pii_type, item.strategy) for item in pii_middleware] == [
        ("email", "redact"),
        ("url", "redact"),
        ("ip", "redact"),
        ("mac_address", "redact"),
        ("credit_card", "block"),
    ]
    assert all(item.apply_to_output for item in pii_middleware)
    assert all(item.apply_to_tool_results for item in pii_middleware)
    assert cast(ModelCallLimitMiddleware, middleware[0]).run_limit == 4
    assert cast(ToolCallLimitMiddleware, middleware[1]).run_limit == 3
    assert cast(ModelRetryMiddleware[Any, Any], middleware[2]).max_retries == 1
    assert cast(ToolRetryMiddleware[Any, Any], middleware[3]).max_retries == 1


def test_build_langchain_agent_middleware_accepts_policy_overrides() -> None:
    middleware = build_langchain_agent_middleware(
        Settings(max_tool_calls=3),
        policy=LangChainMiddlewarePolicy(
            model_call_run_limit=8,
            tool_call_run_limit=5,
            model_retry_max_retries=2,
            tool_retry_max_retries=3,
            pii_rules=(PiiMiddlewareRule("email", "block", apply_to_tool_results=False),),
        ),
    )

    assert cast(ModelCallLimitMiddleware, middleware[0]).run_limit == 8
    assert cast(ToolCallLimitMiddleware, middleware[1]).run_limit == 5
    assert cast(ModelRetryMiddleware[Any, Any], middleware[2]).max_retries == 2
    assert cast(ToolRetryMiddleware[Any, Any], middleware[3]).max_retries == 3
    pii_middleware = [
        cast(PIIMiddleware[Any, Any], item)
        for item in middleware
        if isinstance(item, PIIMiddleware)
    ]
    assert [(item.pii_type, item.strategy) for item in pii_middleware] == [("email", "block")]
    assert pii_middleware[0].apply_to_output is True
    assert pii_middleware[0].apply_to_tool_results is False


def test_langchain_middleware_policy_configures_pii_input_scope() -> None:
    policy = langchain_middleware_policy_from_mapping(
        {
            "piiRules": [
                {
                    "type": "email",
                    "strategy": "redact",
                    "applyToInput": False,
                    "applyToOutput": True,
                    "applyToToolResults": False,
                }
            ]
        }
    )

    assert policy is not None
    assert policy.pii_rules[0].apply_to_input is False
    middleware = build_langchain_agent_middleware(Settings(max_tool_calls=3), policy=policy)
    pii_middleware = [
        cast(PIIMiddleware[Any, Any], item)
        for item in middleware
        if isinstance(item, PIIMiddleware)
    ]
    assert len(pii_middleware) == 1
    assert pii_middleware[0].apply_to_input is False
    assert pii_middleware[0].apply_to_output is True
    assert pii_middleware[0].apply_to_tool_results is False


def test_langchain_middleware_policy_rejects_independent_stream_output_scope() -> None:
    assert (
        langchain_middleware_policy_from_mapping(
            {
                "piiRules": [
                    {
                        "type": "email",
                        "strategy": "redact",
                        "applyToOutput": True,
                        "applyToStreamOutput": False,
                    }
                ]
            }
        )
        is None
    )


def test_langchain_middleware_policy_preserves_supported_stream_output_scope() -> None:
    policy = langchain_middleware_policy_from_mapping(
        {
            "piiRules": [
                {
                    "type": "email",
                    "strategy": "redact",
                    "applyToOutput": True,
                    "applyToStreamOutput": True,
                }
            ]
        }
    )

    assert policy is not None
    assert policy.pii_rules[0].apply_to_output is True
    assert policy.pii_rules[0].apply_to_stream_output is True


def test_build_langchain_agent_middleware_omits_unset_limit_middleware() -> None:
    middleware = build_langchain_agent_middleware(
        Settings(max_tool_calls=3),
        policy=LangChainMiddlewarePolicy(
            model_call_run_limit=None,
            tool_call_run_limit=None,
            tool_retry_max_retries=0,
        ),
    )

    assert [type(item) for item in middleware] == [
        ModelRetryMiddleware,
        ToolRetryMiddleware,
    ]
    assert cast(ToolRetryMiddleware[Any, Any], middleware[1]).max_retries == 0


def test_langchain_middleware_policy_from_mapping_keeps_default_pii_when_omitted() -> None:
    policy = langchain_middleware_policy_from_mapping(
        {
            "modelCallRunLimit": 9,
            "toolCallRunLimit": 4,
            "modelRetryMaxRetries": 2,
            "toolRetryMaxRetries": 3,
        }
    )

    assert policy is not None
    assert policy.model_call_run_limit == 9
    assert policy.tool_call_run_limit == 4
    assert policy.model_retry_max_retries == 2
    assert policy.tool_retry_max_retries == 3
    assert [(rule.pii_type, rule.strategy) for rule in policy.pii_rules] == [
        ("email", "redact"),
        ("url", "redact"),
        ("ip", "redact"),
        ("mac_address", "redact"),
        ("credit_card", "block"),
    ]


def test_langchain_middleware_policy_from_mapping_rejects_invalid_values() -> None:
    assert langchain_middleware_policy_from_mapping({"toolCallRunLimit": -1}) is None
    assert (
        langchain_middleware_policy_from_mapping(
            {"piiRules": [{"type": "email", "strategy": "delete"}]}
        )
        is None
    )
    assert (
        langchain_middleware_policy_from_mapping(
            {
                "piiRules": [
                    {
                        "type": "email",
                        "strategy": "redact",
                        "applyToOutputs": False,
                    }
                ]
            }
        )
        is None
    )


def test_build_langchain_agent_middleware_adds_official_model_fallback_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[tuple[object, tuple[object, ...]]] = []

    class RecordingModelFallbackMiddleware:
        def __init__(self, first_model: object, *additional_models: object) -> None:
            created.append((first_model, additional_models))

    monkeypatch.setattr(
        "reactor.agents.langchain_middleware.ModelFallbackMiddleware",
        RecordingModelFallbackMiddleware,
    )

    middleware = build_langchain_agent_middleware(
        Settings(max_tool_calls=3),
        fallback_models=["anthropic:claude-sonnet-5"],
    )

    assert isinstance(middleware[2], RecordingModelFallbackMiddleware)
    assert created == [("anthropic:claude-sonnet-5", ())]


async def test_model_retry_is_exhausted_per_model_before_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_retry_delay(
        attempt: int,
        *,
        backoff_factor: float,
        initial_delay: float,
        max_delay: float,
        jitter: bool,
    ) -> float:
        _ = attempt, backoff_factor, initial_delay, max_delay, jitter
        return 0.0

    monkeypatch.setattr(
        "langchain.agents.middleware.model_retry.calculate_delay",
        no_retry_delay,
    )
    SequencedChatModel.invocation_log = []
    primary = SequencedChatModel(
        messages=cast(Iterator[AIMessage | str], iter(())),
        label="primary",
        outcomes=[TimeoutError("primary-1"), TimeoutError("primary-2")],
    )
    fallback = SequencedChatModel(
        messages=cast(Iterator[AIMessage | str], iter(())),
        label="fallback",
        outcomes=[TimeoutError("fallback-1"), AIMessage(content="recovered")],
    )
    policy = LangChainMiddlewarePolicy(
        model_retry_max_retries=1,
        tool_retry_max_retries=0,
        pii_rules=(),
    )
    middleware = build_langchain_agent_middleware(
        Settings(),
        fallback_models=[fallback],
        policy=policy,
    )
    agent = cast(Any, create_agent)(
        model=primary,
        tools=[],
        middleware=middleware,
    )

    result = cast(
        dict[str, Any],
        await agent.ainvoke({"messages": [HumanMessage(content="hello")]}),
    )

    assert result["messages"][-1].content == "recovered"
    assert SequencedChatModel.invocation_log == [
        "primary",
        "primary",
        "fallback",
        "fallback",
    ]


async def test_model_retry_does_not_repeat_permanent_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_retry_delay(
        attempt: int,
        *,
        backoff_factor: float,
        initial_delay: float,
        max_delay: float,
        jitter: bool,
    ) -> float:
        _ = attempt, backoff_factor, initial_delay, max_delay, jitter
        return 0.0

    monkeypatch.setattr(
        "langchain.agents.middleware.model_retry.calculate_delay",
        no_retry_delay,
    )
    SequencedChatModel.invocation_log = []
    model = SequencedChatModel(
        messages=cast(Iterator[AIMessage | str], iter(())),
        label="primary",
        outcomes=[
            ValueError("invalid model request"),
            AIMessage(content="must not be reached"),
        ],
    )
    middleware = build_langchain_agent_middleware(
        Settings(),
        policy=LangChainMiddlewarePolicy(
            model_retry_max_retries=1,
            tool_retry_max_retries=0,
            pii_rules=(),
        ),
    )
    agent = cast(Any, create_agent)(
        model=model,
        tools=[],
        middleware=middleware,
    )

    with pytest.raises(ValueError, match="invalid model request"):
        await agent.ainvoke({"messages": [HumanMessage(content="hello")]})

    assert SequencedChatModel.invocation_log == ["primary"]


async def test_tool_retry_failure_hides_raw_exception_from_model() -> None:
    @tool
    def unstable_tool() -> str:
        """Exercise the framework tool retry failure boundary."""
        raise RuntimeError("PRIVATE_TOOL_EXCEPTION_DETAIL")

    ToolFailureObservingChatModel.observed_tool_content = None
    model = ToolFailureObservingChatModel(messages=cast(Iterator[AIMessage | str], iter(())))
    policy = LangChainMiddlewarePolicy(
        model_retry_max_retries=0,
        tool_retry_max_retries=0,
        pii_rules=(),
    )
    middleware = build_langchain_agent_middleware(
        Settings(),
        retry_on_tools=["unstable_tool"],
        policy=policy,
    )
    agent = cast(Any, create_agent)(
        model=model,
        tools=[unstable_tool],
        middleware=middleware,
    )

    await agent.ainvoke({"messages": [HumanMessage(content="run the tool")]})

    assert ToolFailureObservingChatModel.observed_tool_content == (
        '[tool_output:data]\n{"error":"tool_execution_failed"}'
    )


async def test_tool_retry_does_not_repeat_external_side_effect_without_durable_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_retry_delay(
        attempt: int,
        *,
        backoff_factor: float,
        initial_delay: float,
        max_delay: float,
        jitter: bool,
    ) -> float:
        _ = attempt, backoff_factor, initial_delay, max_delay, jitter
        return 0.0

    monkeypatch.setattr(
        "langchain.agents.middleware.tool_retry.calculate_delay",
        no_retry_delay,
    )
    calls = 0
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="Webhook",
        name="send",
        description="Send a webhook.",
        risk_level="external_side_effect",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    async def handler(_request: ToolExecutionRequest) -> ToolExecutionResult:
        nonlocal calls
        calls += 1
        raise RuntimeError("delivery outcome unknown")

    reactor_tool = build_langchain_tool(
        spec,
        handler=handler,
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        policy=ToolPolicy(allow_write_without_approval=True),
    )
    ToolFailureObservingChatModel.observed_tool_content = None
    model = ToolFailureObservingChatModel(
        messages=cast(Iterator[AIMessage | str], iter(())),
        requested_tool_name=spec.qualified_name,
    )
    middleware = build_langchain_agent_middleware(
        Settings(),
        policy=LangChainMiddlewarePolicy(
            model_retry_max_retries=0,
            tool_retry_max_retries=1,
            pii_rules=(),
        ),
    )
    agent = cast(Any, create_agent)(
        model=model,
        tools=[reactor_tool],
        middleware=middleware,
    )

    await agent.ainvoke({"messages": [HumanMessage(content="send it")]})

    assert calls == 1
    assert ToolFailureObservingChatModel.observed_tool_content is not None
    assert "delivery outcome unknown" not in ToolFailureObservingChatModel.observed_tool_content
    assert (
        '"status":"requires_reconciliation"' in ToolFailureObservingChatModel.observed_tool_content
    )


async def test_tool_retry_retries_allowlisted_read_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_retry_delay(
        attempt: int,
        *,
        backoff_factor: float,
        initial_delay: float,
        max_delay: float,
        jitter: bool,
    ) -> float:
        _ = attempt, backoff_factor, initial_delay, max_delay, jitter
        return 0.0

    monkeypatch.setattr(
        "langchain.agents.middleware.tool_retry.calculate_delay",
        no_retry_delay,
    )
    calls = 0
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="Search",
        name="lookup",
        description="Search safe reference data.",
        risk_level="read",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    async def handler(_request: ToolExecutionRequest) -> ToolExecutionResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("temporary read failure")
        return ToolExecutionResult.success({"answer": "available"})

    reactor_tool = build_langchain_tool(
        spec,
        handler=handler,
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
    )
    ToolFailureObservingChatModel.observed_tool_content = None
    model = ToolFailureObservingChatModel(
        messages=cast(Iterator[AIMessage | str], iter(())),
        requested_tool_name=spec.qualified_name,
    )
    middleware = build_langchain_agent_middleware(
        Settings(),
        retry_on_tools=[spec.qualified_name],
        policy=LangChainMiddlewarePolicy(
            model_retry_max_retries=0,
            tool_retry_max_retries=1,
            pii_rules=(),
        ),
    )
    agent = cast(Any, create_agent)(
        model=model,
        tools=[reactor_tool],
        middleware=middleware,
    )

    await agent.ainvoke({"messages": [HumanMessage(content="look it up")]})

    assert calls == 2
    assert ToolFailureObservingChatModel.observed_tool_content is not None
    assert '"status":"succeeded"' in ToolFailureObservingChatModel.observed_tool_content
