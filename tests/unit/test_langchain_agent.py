from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

import pytest
from langchain.agents.structured_output import AutoStrategy
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command, GraphOutput, Interrupt
from pydantic import BaseModel

from reactor.agents.checkpoint_fork import checkpoint_id_from_config
from reactor.agents.interrupts import ApprovalResumeDecision
from reactor.agents.langchain_agent import (
    LANGCHAIN_CREATE_AGENT,
    build_langchain_agent,
    durable_interrupt_messages,
    durable_rag_context_metadata,
    extract_langchain_interrupt_actions,
    extract_response_text,
    langchain_middleware_chain_metadata,
    langchain_response_format,
    model_identifier,
    planned_langchain_middleware_chain_metadata,
    resolve_langchain_agent_models,
    retryable_tool_names,
    run_langchain_agent_once,
    stream_langchain_agent_events,
)
from reactor.agents.langchain_middleware import (
    LangChainMiddlewarePolicy,
    PiiMiddlewareRule,
    build_langchain_agent_middleware,
)
from reactor.agents.runner import public_run_metadata, response_policy_terminal_status, run_once
from reactor.agents.runtime_config import langgraph_checkpoint_thread_id, langgraph_durable_config
from reactor.agents.state import REACTOR_STATE_SCHEMA_VERSION
from reactor.agents.streaming import langchain_v2_stream_interrupts
from reactor.core.settings import Settings
from reactor.tools.catalog import ToolSpec
from reactor.tools.execution import ToolExecutionRequest, ToolExecutionResult, ToolPolicy


class RecordingChatModelFactory:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.models: list[object] = []

    def create(self, *, provider: str, model: str) -> object:
        self.calls.append((provider, model))
        created_model = object()
        self.models.append(created_model)
        return created_model


def test_model_identifier_uses_langchain_provider_model_format() -> None:
    assert model_identifier("openai", "gpt-5-mini") == "openai:gpt-5-mini"
    assert model_identifier("", "custom-model") == "custom-model"


def test_resolve_langchain_agent_models_uses_one_factory_for_primary_and_fallbacks() -> None:
    factory = RecordingChatModelFactory()

    primary, fallbacks = resolve_langchain_agent_models(
        provider="openai",
        model="gpt-5-mini",
        fallback_models=("anthropic:claude-sonnet-5", "google_genai:gemini-3-pro"),
        chat_model_factory=factory,
    )

    assert factory.calls == [
        ("openai", "gpt-5-mini"),
        ("anthropic", "claude-sonnet-5"),
        ("google_genai", "gemini-3-pro"),
    ]
    assert primary is factory.models[0]
    assert fallbacks == tuple(factory.models[1:])


def test_resolve_langchain_agent_models_rejects_primary_as_fallback() -> None:
    factory = RecordingChatModelFactory()

    with pytest.raises(ValueError, match="fallback model must differ from primary model"):
        resolve_langchain_agent_models(
            provider="openai",
            model="gpt-5-mini",
            fallback_models=("openai:gpt-5-mini",),
            chat_model_factory=factory,
        )

    assert factory.calls == []


def test_retryable_tool_names_allows_only_enabled_unapproved_reads() -> None:
    tools = [
        ToolSpec(
            tenant_id="tenant_1",
            namespace="Search",
            name="enabled",
            description="Search safe reference data.",
            risk_level="read",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        ),
        ToolSpec(
            tenant_id="tenant_1",
            namespace="Search",
            name="approval_required",
            description="Search reviewed reference data.",
            risk_level="read",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            requires_approval=True,
        ),
        ToolSpec(
            tenant_id="tenant_1",
            namespace="Webhook",
            name="send",
            description="Send a webhook.",
            risk_level="external_side_effect",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        ),
        ToolSpec(
            tenant_id="tenant_1",
            namespace="Search",
            name="disabled",
            description="Disabled search.",
            risk_level="read",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            enabled=False,
        ),
    ]

    assert retryable_tool_names(tools) == ("Search:enabled",)


def test_langchain_middleware_chain_metadata_counts_configured_fallback_models() -> None:
    metadata = langchain_middleware_chain_metadata(
        [object()],
        fallback_models=["anthropic:claude-sonnet-5", "google:gemini-3-pro"],
    )

    assert metadata["fallbackModelCount"] == 2


def test_planned_langchain_middleware_metadata_matches_actual_chain() -> None:
    settings = Settings(max_tool_calls=3)
    fallback_model = GenericFakeChatModel(messages=iter([AIMessage(content="fallback")]))
    interrupt_on_tools = ("Webhook:send",)
    actual = build_langchain_agent_middleware(
        settings,
        interrupt_on_tools=interrupt_on_tools,
        fallback_models=(fallback_model,),
    )

    assert planned_langchain_middleware_chain_metadata(
        settings,
        interrupt_on_tools=interrupt_on_tools,
        fallback_models=(fallback_model,),
    ) == langchain_middleware_chain_metadata(
        actual,
        interrupt_on_tools=interrupt_on_tools,
        fallback_models=(fallback_model,),
    )


def test_build_langchain_agent_passes_model_and_official_middleware(monkeypatch: Any) -> None:
    calls: list[dict[str, object]] = []
    checkpointer = object()
    graph_store = InMemoryStore()
    model_factory = RecordingChatModelFactory()

    def fake_create_agent(**kwargs: object) -> FakeLangChainAgent:
        calls.append(dict(kwargs))
        return FakeLangChainAgent("ok")

    monkeypatch.setattr("reactor.agents.langchain_agent.LANGCHAIN_CREATE_AGENT", fake_create_agent)

    agent = build_langchain_agent(
        Settings(max_tool_calls=2),
        provider="openai",
        model="gpt-5-mini",
        system_prompt="system",
        interrupt_on_tools=("DangerousServer:delete_file",),
        tools=[{"name": "Rag:hybrid_search"}],
        checkpointer=checkpointer,
        graph_store=graph_store,
        chat_model_factory=model_factory,
    )

    assert isinstance(agent, FakeLangChainAgent)
    assert calls[0]["model"] is model_factory.models[0]
    assert calls[0]["tools"] == [{"name": "Rag:hybrid_search"}]
    assert calls[0]["system_prompt"] == "system"
    assert calls[0]["checkpointer"] is checkpointer
    assert calls[0]["store"] is graph_store
    assert calls[0]["name"] == "reactor-langchain-agent"
    assert len(cast(Sequence[object], calls[0]["middleware"])) == 10


def test_build_langchain_agent_passes_auto_strategy_for_schema_less_json(
    monkeypatch: Any,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_create_agent(**kwargs: object) -> FakeLangChainAgent:
        calls.append(dict(kwargs))
        return FakeLangChainAgent("ok")

    monkeypatch.setattr("reactor.agents.langchain_agent.LANGCHAIN_CREATE_AGENT", fake_create_agent)

    build_langchain_agent(
        Settings(),
        provider="openai",
        model="gpt-5-mini",
        response_format="JSON",
        chat_model_factory=RecordingChatModelFactory(),
    )

    response_format = calls[0]["response_format"]
    assert isinstance(response_format, AutoStrategy)
    assert response_format.schema == {"type": "object", "additionalProperties": True}
    helper_response_format = langchain_response_format("JSON")
    assert isinstance(helper_response_format, AutoStrategy)
    assert helper_response_format.schema == response_format.schema


def test_build_langchain_agent_passes_fallback_models_to_middleware(
    monkeypatch: Any,
) -> None:
    create_agent_calls: list[dict[str, object]] = []
    middleware_calls: list[dict[str, object]] = []
    model_factory = RecordingChatModelFactory()

    def fake_create_agent(**kwargs: object) -> FakeLangChainAgent:
        create_agent_calls.append(dict(kwargs))
        return FakeLangChainAgent("ok")

    def fake_middleware(*args: object, **kwargs: object) -> list[object]:
        middleware_calls.append({"args": args, "kwargs": kwargs})
        return []

    monkeypatch.setattr("reactor.agents.langchain_agent.LANGCHAIN_CREATE_AGENT", fake_create_agent)
    monkeypatch.setattr(
        "reactor.agents.langchain_agent.build_langchain_agent_middleware",
        fake_middleware,
    )

    build_langchain_agent(
        Settings(),
        provider="openai",
        model="gpt-5",
        fallback_models=["anthropic:claude-sonnet-5"],
        chat_model_factory=model_factory,
    )

    middleware_kwargs = cast(dict[str, object], middleware_calls[0]["kwargs"])
    assert model_factory.calls == [
        ("openai", "gpt-5"),
        ("anthropic", "claude-sonnet-5"),
    ]
    assert create_agent_calls[0]["model"] is model_factory.models[0]
    assert "primary_model" not in middleware_kwargs
    assert middleware_kwargs["fallback_models"] == (model_factory.models[1],)


def test_build_langchain_agent_passes_middleware_policy_to_middleware(
    monkeypatch: Any,
) -> None:
    create_agent_calls: list[dict[str, object]] = []
    middleware_calls: list[dict[str, object]] = []
    policy = LangChainMiddlewarePolicy(tool_call_run_limit=2)

    def fake_create_agent(**kwargs: object) -> FakeLangChainAgent:
        create_agent_calls.append(dict(kwargs))
        return FakeLangChainAgent("ok")

    def fake_middleware(*args: object, **kwargs: object) -> list[object]:
        middleware_calls.append({"args": args, "kwargs": kwargs})
        return []

    monkeypatch.setattr("reactor.agents.langchain_agent.LANGCHAIN_CREATE_AGENT", fake_create_agent)
    monkeypatch.setattr(
        "reactor.agents.langchain_agent.build_langchain_agent_middleware",
        fake_middleware,
    )

    build_langchain_agent(
        Settings(),
        provider="openai",
        model="gpt-5",
        middleware_policy=policy,
        chat_model_factory=RecordingChatModelFactory(),
    )

    assert create_agent_calls[0]["middleware"] == []
    middleware_kwargs = cast(dict[str, object], middleware_calls[0]["kwargs"])
    assert middleware_kwargs["policy"] is policy


def test_build_langchain_agent_prefers_pydantic_structured_output_schema(
    monkeypatch: Any,
) -> None:
    calls: list[dict[str, object]] = []

    class AnswerSchema(BaseModel):
        answer: str
        confidence: float

    def fake_create_agent(**kwargs: object) -> FakeLangChainAgent:
        calls.append(dict(kwargs))
        return FakeLangChainAgent("ok")

    monkeypatch.setattr("reactor.agents.langchain_agent.LANGCHAIN_CREATE_AGENT", fake_create_agent)

    build_langchain_agent(
        Settings(),
        provider="openai",
        model="gpt-5-mini",
        response_format="JSON",
        structured_output_schema=AnswerSchema,
        chat_model_factory=RecordingChatModelFactory(),
    )

    assert calls[0]["response_format"] is AnswerSchema


def test_build_langchain_agent_prefers_dataclass_structured_output_schema(
    monkeypatch: Any,
) -> None:
    calls: list[dict[str, object]] = []

    @dataclass(frozen=True)
    class AnswerSchema:
        answer: str
        confidence: float

    def fake_create_agent(**kwargs: object) -> FakeLangChainAgent:
        calls.append(dict(kwargs))
        return FakeLangChainAgent("ok")

    monkeypatch.setattr("reactor.agents.langchain_agent.LANGCHAIN_CREATE_AGENT", fake_create_agent)

    build_langchain_agent(
        Settings(),
        provider="openai",
        model="gpt-5-mini",
        response_format="JSON",
        structured_output_schema=AnswerSchema,
        chat_model_factory=RecordingChatModelFactory(),
    )

    assert calls[0]["response_format"] is AnswerSchema


async def test_run_langchain_agent_once_extracts_ai_message_response() -> None:
    agent = FakeLangChainAgent("agent response")
    result = await run_langchain_agent_once(
        "hello",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        agent=agent,
    )

    assert result.response == "agent response"
    assert result.token_usage is not None
    assert result.token_usage.total_tokens > 0
    assert agent.calls[0]["config"] == {
        "recursion_limit": 25,
        "run_name": "reactor.langchain_agent.invoke",
        "tags": ["reactor", "runtime:langchain_agent"],
        "metadata": {"reactor.runtime": "langchain_agent"},
        "configurable": {
            "thread_id": langgraph_checkpoint_thread_id(
                tenant_id="local",
                thread_id="thread_1",
                checkpoint_ns="reactor",
            ),
            "checkpoint_ns": "",
        },
    }
    assert agent.calls[0]["version"] == "v2"


async def test_run_langchain_agent_once_records_tool_output_guard_manifest() -> None:
    class AgentWithSanitizedToolResult(FakeLangChainAgent):
        async def ainvoke(
            self,
            input: object,
            config: RunnableConfig | None = None,
            *,
            version: str = "v1",
        ) -> object:
            self.calls.append({"input": input, "config": config or {}, "version": version})
            return {
                "messages": [
                    HumanMessage(content="search"),
                    ToolMessage(
                        content='[tool_output:data]\n{"text":"[REDACTED_CANARY]"}',
                        tool_call_id="call_1",
                        artifact={
                            "schema": "reactor.tool_result.v1",
                            "status": "succeeded",
                            "tool_id": "Search:lookup",
                            "idempotency_key": "tool:test",
                            "model_visible_text": (
                                '[tool_output:data]\n{"text":"[REDACTED_CANARY]"}'
                            ),
                            "sanitizer_findings": [
                                "instruction_like_tool_output",
                                "canary_secret",
                            ],
                        },
                    ),
                    AIMessage(content="grounded response"),
                ]
            }

    context_manifest: dict[str, object] = {
        "sections": [
            {
                "name": "latest_user_request",
                "source_type": "request",
                "tainted": False,
                "content_length": 6,
                "content_checksum": "sha256:request",
                "metadata": {},
            },
            {
                "name": "examples_or_rubrics",
                "source_type": "internal",
                "tainted": False,
                "content_length": 7,
                "content_checksum": "sha256:example",
                "metadata": {},
            },
        ]
    }
    result = await run_langchain_agent_once(
        "search",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        agent=AgentWithSanitizedToolResult("unused"),
        context_manifest=context_manifest,
    )

    assert result.response == "grounded response"
    assert result.response_metadata["tool_output_guard_findings"] == [
        "instruction_like_tool_output",
        "canary_secret",
    ]
    manifest = cast(dict[str, object], result.response_metadata["contextManifest"])
    sections = cast(list[dict[str, object]], manifest["sections"])
    assert [section["name"] for section in sections] == [
        "latest_user_request",
        "tool_outputs",
        "examples_or_rubrics",
    ]
    assert sections[1]["metadata"] == {
        "output_count": 1,
        "sanitized_count": 1,
        "findings": ["instruction_like_tool_output", "canary_secret"],
    }
    assert str(sections[1]["content_checksum"]).startswith("sha256:")
    assert "model_visible_text" not in json.dumps(manifest)
    assert "REDACTED_CANARY" not in json.dumps(manifest)
    public_metadata = public_run_metadata(result.response_metadata)
    assert public_metadata["tool_output_guard_findings"] == [
        "instruction_like_tool_output",
        "canary_secret",
    ]
    assert "REDACTED_CANARY" not in json.dumps(public_metadata)


async def test_run_langchain_agent_once_blocks_tool_artifact_content_mismatch() -> None:
    actual_content = '[tool_output:data]\n{"text":"actual"}'
    forged_artifact_content = '[tool_output:data]\n{"text":"forged-safe"}'

    class AgentWithMismatchedToolArtifact(FakeLangChainAgent):
        async def ainvoke(
            self,
            input: object,
            config: RunnableConfig | None = None,
            *,
            version: str = "v1",
        ) -> object:
            self.calls.append({"input": input, "config": config or {}, "version": version})
            return {
                "messages": [
                    ToolMessage(
                        content=actual_content,
                        tool_call_id="call_1",
                        artifact={
                            "schema": "reactor.tool_result.v1",
                            "status": "succeeded",
                            "tool_id": "Search:lookup",
                            "idempotency_key": "tool:mismatch",
                            "model_visible_text": forged_artifact_content,
                            "sanitizer_findings": [],
                        },
                    ),
                    AIMessage(content="must not complete"),
                ]
            }

    result = await run_langchain_agent_once(
        "search",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        agent=AgentWithMismatchedToolArtifact("unused"),
    )

    assert result.response == "Response blocked by tool output guard policy."
    assert result.response_metadata["stop_reason"] == "tool_output_guard_blocked"
    assert result.response_metadata["tool_output_guard_error_code"] == "ARTIFACT_CONTENT_MISMATCH"
    manifest = cast(dict[str, object], result.response_metadata["contextManifest"])
    sections = cast(list[dict[str, object]], manifest["sections"])
    tool_section = next(section for section in sections if section["name"] == "tool_outputs")
    tool_metadata = cast(dict[str, object], tool_section["metadata"])
    assert tool_metadata["artifact_content_mismatch_count"] == 1
    serialized_metadata = json.dumps(result.response_metadata)
    assert forged_artifact_content not in serialized_metadata
    assert actual_content not in serialized_metadata
    public_metadata = public_run_metadata(result.response_metadata)
    assert public_metadata["tool_output_guard_status"] == "blocked"
    assert public_metadata["tool_output_guard_error_code"] == "ARTIFACT_CONTENT_MISMATCH"


async def test_run_langchain_agent_once_blocks_unlabeled_tool_output() -> None:
    unlabeled_content = '{"text":"untrusted"}'

    class AgentWithUnlabeledToolOutput(FakeLangChainAgent):
        async def ainvoke(
            self,
            input: object,
            config: RunnableConfig | None = None,
            *,
            version: str = "v1",
        ) -> object:
            self.calls.append({"input": input, "config": config or {}, "version": version})
            return {
                "messages": [
                    ToolMessage(
                        content=unlabeled_content,
                        tool_call_id="call_1",
                        artifact={
                            "schema": "reactor.tool_result.v1",
                            "status": "succeeded",
                            "tool_id": "Search:lookup",
                            "idempotency_key": "tool:unlabeled",
                            "model_visible_text": unlabeled_content,
                            "sanitizer_findings": [],
                        },
                    ),
                    AIMessage(content="must not complete"),
                ]
            }

    result = await run_langchain_agent_once(
        "search",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        agent=AgentWithUnlabeledToolOutput("unused"),
    )

    assert result.response == "Response blocked by tool output guard policy."
    assert result.response_metadata["stop_reason"] == "tool_output_guard_blocked"
    assert result.response_metadata["tool_output_guard_error_code"] == "UNLABELED_TOOL_OUTPUT"
    manifest = cast(dict[str, object], result.response_metadata["contextManifest"])
    sections = cast(list[dict[str, object]], manifest["sections"])
    tool_section = next(section for section in sections if section["name"] == "tool_outputs")
    tool_metadata = cast(dict[str, object], tool_section["metadata"])
    assert tool_metadata["unlabeled_output_count"] == 1
    serialized_metadata = json.dumps(result.response_metadata)
    assert unlabeled_content not in serialized_metadata
    assert "must not complete" not in serialized_metadata


async def test_run_langchain_agent_once_resumes_the_same_durable_graph() -> None:
    agent = FakeLangChainAgent("resumed response")
    command = Command(resume={"decisions": [{"type": "approve"}]})

    result = await run_langchain_agent_once(
        "original request",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        agent=agent,
        resume_command=command,
    )

    assert result.response == "resumed response"
    assert agent.calls[0]["input"] is command
    assert cast(dict[str, object], agent.calls[0]["config"])["configurable"] == {
        "thread_id": langgraph_checkpoint_thread_id(
            tenant_id="local",
            thread_id="thread_1",
            checkpoint_ns="reactor",
        ),
        "checkpoint_ns": "",
    }


@pytest.mark.parametrize(
    "command",
    [
        Command(
            resume={
                "decisions": [
                    {"type": "approve"},
                    {"type": "approve"},
                ]
            }
        ),
        Command(
            resume={
                "decisions": [
                    {
                        "type": "edit",
                        "edited_action": {"name": "Webhook:send", "args": {"value": "changed"}},
                    }
                ]
            }
        ),
        Command(
            update={"messages": []},
            resume={"decisions": [{"type": "approve"}]},
        ),
    ],
)
async def test_run_langchain_agent_once_rejects_unsafe_hitl_resume_command(
    command: Command[Any],
) -> None:
    agent = FakeLangChainAgent("must not run")

    with pytest.raises(ValueError, match="invalid LangChain HITL resume command"):
        await run_langchain_agent_once(
            "original request",
            Settings(),
            provider="openai",
            model="gpt-5-mini",
            thread_id="thread_1",
            checkpoint_ns="reactor",
            agent=agent,
            resume_command=command,
        )

    assert agent.calls == []


async def test_real_create_agent_hitl_resume_executes_approved_tool_once(
    monkeypatch: Any,
) -> None:
    model = ToolCallingFakeModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "Webhook:send",
                            "args": {"value": "ok"},
                            "id": "call_1",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="resumed safely"),
            ]
        )
    )
    real_create_agent = LANGCHAIN_CREATE_AGENT

    def create_with_fake_model(**kwargs: object) -> object:
        kwargs["model"] = model
        return real_create_agent(**kwargs)

    monkeypatch.setattr(
        "reactor.agents.langchain_agent.LANGCHAIN_CREATE_AGENT",
        create_with_fake_model,
    )
    executions: list[str] = []

    async def handler(request: ToolExecutionRequest) -> ToolExecutionResult:
        executions.append(request.tool.qualified_name)
        return ToolExecutionResult.success({"ok": True})

    tool = ToolSpec(
        tenant_id="tenant_1",
        namespace="Webhook",
        name="send",
        description="Send a test webhook.",
        risk_level="external_side_effect",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
        },
        output_schema={"type": "object"},
    )
    checkpointer = InMemorySaver()

    interrupted = await run_langchain_agent_once(
        "send it",
        Settings(),
        provider="test",
        model="fake",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        tools=[tool],
        tool_handler=handler,
        tenant_id="tenant_1",
        user_id="user_1",
        checkpointer=checkpointer,
        chat_model_factory=RecordingChatModelFactory(),
    )
    resumed = await run_langchain_agent_once(
        "send it",
        Settings(),
        provider="test",
        model="fake",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        tools=[tool],
        tool_handler=handler,
        tenant_id="tenant_1",
        user_id="user_1",
        checkpointer=checkpointer,
        chat_model_factory=RecordingChatModelFactory(),
        resume_command=ApprovalResumeDecision(
            "approval_1",
            True,
            "admin_1",
        ).as_langchain_hitl_command(),
    )

    assert interrupted.interrupted is True
    assert resumed.response == "resumed safely"
    assert executions == ["Webhook:send"]


async def test_real_create_agent_repeated_hitl_resumes_latest_pending_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = ToolCallingFakeModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "Webhook:send",
                            "args": {"value": "first"},
                            "id": "call_1",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "Webhook:send",
                            "args": {"value": "second"},
                            "id": "call_2",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="all approved actions completed"),
            ]
        )
    )
    real_create_agent = LANGCHAIN_CREATE_AGENT

    def create_with_fake_model(**kwargs: object) -> object:
        kwargs["model"] = model
        return real_create_agent(**kwargs)

    monkeypatch.setattr(
        "reactor.agents.langchain_agent.LANGCHAIN_CREATE_AGENT",
        create_with_fake_model,
    )
    executions: list[str] = []

    async def handler(request: ToolExecutionRequest) -> ToolExecutionResult:
        executions.append(str(request.input_payload["value"]))
        return ToolExecutionResult.success({"ok": True})

    tool = ToolSpec(
        tenant_id="tenant_1",
        namespace="Webhook",
        name="send",
        description="Send a test webhook.",
        risk_level="external_side_effect",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
        },
        output_schema={"type": "object"},
    )
    checkpointer = InMemorySaver()
    model_factory = RecordingChatModelFactory()

    first_interrupt = await run_langchain_agent_once(
        "send twice",
        Settings(),
        provider="test",
        model="fake",
        thread_id="thread_repeated_hitl",
        checkpoint_ns="reactor",
        tools=[tool],
        tool_handler=handler,
        tenant_id="tenant_1",
        user_id="user_1",
        checkpointer=checkpointer,
        chat_model_factory=model_factory,
    )
    second_interrupt = await run_langchain_agent_once(
        "send twice",
        Settings(),
        provider="test",
        model="fake",
        thread_id="thread_repeated_hitl",
        checkpoint_ns="reactor",
        tools=[tool],
        tool_handler=handler,
        tenant_id="tenant_1",
        user_id="user_1",
        checkpointer=checkpointer,
        chat_model_factory=model_factory,
        resume_command=ApprovalResumeDecision(
            "approval_1",
            True,
            "admin_1",
        ).as_langchain_hitl_command(),
    )
    completed = await run_langchain_agent_once(
        "send twice",
        Settings(),
        provider="test",
        model="fake",
        thread_id="thread_repeated_hitl",
        checkpoint_ns="reactor",
        tools=[tool],
        tool_handler=handler,
        tenant_id="tenant_1",
        user_id="user_1",
        checkpointer=checkpointer,
        chat_model_factory=model_factory,
        resume_command=ApprovalResumeDecision(
            "approval_2",
            True,
            "admin_1",
        ).as_langchain_hitl_command(),
    )

    assert first_interrupt.interrupted is True
    assert [action.arguments for action in first_interrupt.interrupt_actions] == [
        {"value": "first"}
    ]
    assert second_interrupt.interrupted is True
    assert [action.arguments for action in second_interrupt.interrupt_actions] == [
        {"value": "second"}
    ]
    assert completed.interrupted is False
    assert completed.response == "all approved actions completed"
    assert executions == ["first", "second"]


async def test_real_create_agent_hitl_resume_does_not_double_count_checkpoint_rag() -> None:
    model = ToolCallingFakeModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "Rag:hybrid_search",
                            "args": {"query": "policy"},
                            "id": "call_rag",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "Webhook:send",
                            "args": {"value": "ok"},
                            "id": "call_write",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="resumed safely"),
            ]
        )
    )
    real_create_agent = LANGCHAIN_CREATE_AGENT

    def create_with_fake_model(**kwargs: object) -> object:
        kwargs["model"] = model
        return real_create_agent(**kwargs)

    rag_tool = ToolSpec(
        tenant_id="tenant_1",
        namespace="Rag",
        name="hybrid_search",
        description="Search tenant documents.",
        risk_level="read",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        output_schema={"type": "object"},
    )
    write_tool = ToolSpec(
        tenant_id="tenant_1",
        namespace="Webhook",
        name="send",
        description="Send a test webhook.",
        risk_level="external_side_effect",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
        },
        output_schema={"type": "object"},
    )
    executions: list[str] = []

    async def handler(request: ToolExecutionRequest) -> ToolExecutionResult:
        executions.append(request.tool.qualified_name)
        if request.tool.qualified_name == "Rag:hybrid_search":
            return ToolExecutionResult.success(
                {
                    "chunks": [{"citation_id": "policy:1", "content": "grounded"}],
                    "citations": [
                        {
                            "citation_id": "policy:1",
                            "source_uri": "https://docs.example/policy",
                            "content_hash": "sha256:policy",
                        }
                    ],
                }
            )
        return ToolExecutionResult.success({"ok": True})

    initial_manifest: dict[str, object] = {
        "sections": [
            {
                "name": "rag_context",
                "source_type": "rag",
                "metadata": {"chunk_count": 0, "citation_count": 0, "citations": []},
            }
        ]
    }
    checkpointer = InMemorySaver()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "reactor.agents.langchain_agent.LANGCHAIN_CREATE_AGENT",
            create_with_fake_model,
        )
        interrupted = await run_langchain_agent_once(
            "search then send",
            Settings(),
            provider="test",
            model="fake",
            thread_id="thread_rag_resume",
            checkpoint_ns="reactor",
            tools=[rag_tool, write_tool],
            tool_handler=handler,
            tenant_id="tenant_1",
            user_id="user_1",
            checkpointer=checkpointer,
            context_manifest=initial_manifest,
            chat_model_factory=RecordingChatModelFactory(),
        )
        assert executions == ["Rag:hybrid_search"]
        checkpoint_tuple = await checkpointer.aget_tuple(
            langgraph_durable_config(
                tenant_id="tenant_1",
                thread_id="thread_rag_resume",
                checkpoint_ns="reactor",
            )
        )
        assert checkpoint_tuple is not None
        recovered_messages = await durable_interrupt_messages(
            checkpointer,
            config=langgraph_durable_config(
                tenant_id="tenant_1",
                thread_id="thread_rag_resume",
                checkpoint_ns="reactor",
            ),
        )
        assert recovered_messages.messages, list(
            cast(Mapping[str, object], checkpoint_tuple.checkpoint.get("channel_values", {}))
        )
        assert "contextManifest" in interrupted.response_metadata, {
            "response_metadata": interrupted.response_metadata,
            "recovered_message_types": [
                type(message).__name__ for message in recovered_messages.messages
            ],
            "channel_value_keys": list(
                cast(Mapping[str, object], checkpoint_tuple.checkpoint.get("channel_values", {}))
            ),
        }
        interrupted_manifest = cast(
            dict[str, object], interrupted.response_metadata["contextManifest"]
        )
        resumed = await run_langchain_agent_once(
            "search then send",
            Settings(),
            provider="test",
            model="fake",
            thread_id="thread_rag_resume",
            checkpoint_ns="reactor",
            tools=[rag_tool, write_tool],
            tool_handler=handler,
            tenant_id="tenant_1",
            user_id="user_1",
            checkpointer=checkpointer,
            context_manifest=interrupted_manifest,
            chat_model_factory=RecordingChatModelFactory(),
            resume_command=ApprovalResumeDecision(
                "approval_1",
                True,
                "admin_1",
            ).as_langchain_hitl_command(),
        )

    assert interrupted.interrupted is True
    interrupted_sections = cast(list[dict[str, object]], interrupted_manifest["sections"])
    interrupted_rag = next(
        section for section in interrupted_sections if section["name"] == "rag_context"
    )
    interrupted_rag_metadata = cast(dict[str, object], interrupted_rag["metadata"])
    assert interrupted_rag_metadata["chunk_count"] == 1
    assert interrupted_rag_metadata["runtime_chunk_count"] == 1
    interrupted_tool_outputs = next(
        section for section in interrupted_sections if section["name"] == "tool_outputs"
    )
    assert cast(dict[str, object], interrupted_tool_outputs["metadata"])["output_count"] == 1
    assert "[tool_output:data]" not in json.dumps(interrupted_manifest)
    resumed_manifest = cast(dict[str, object], resumed.response_metadata["contextManifest"])
    resumed_sections = cast(list[dict[str, object]], resumed_manifest["sections"])
    resumed_rag = next(section for section in resumed_sections if section["name"] == "rag_context")
    resumed_rag_metadata = cast(dict[str, object], resumed_rag["metadata"])
    assert resumed_rag_metadata["chunk_count"] == 1
    assert resumed_rag_metadata["runtime_chunk_count"] == 1


def test_durable_rag_context_metadata_rejects_foreign_schema_claim() -> None:
    claimed_citation_id = "foreign:claim"
    recognized, valid, metadata = durable_rag_context_metadata(
        ToolMessage(
            content=(
                "[tool_output:data]\n"
                + json.dumps(
                    {
                        "schema": "foreign.tool_result.v1",
                        "status": "succeeded",
                        "tool_id": "Rag:hybrid_search",
                        "idempotency_key": "tool:foreign",
                        "payload": {
                            "chunks": [{"citation_id": claimed_citation_id}],
                            "citations": [{"citation_id": claimed_citation_id}],
                        },
                    },
                    separators=(",", ":"),
                )
            ),
            tool_call_id="call_foreign",
            name="Rag:hybrid_search",
        )
    )

    assert recognized is True
    assert valid is False
    assert metadata is None


async def test_durable_interrupt_messages_reads_latest_after_pinned_replay() -> None:
    checkpointer = InMemorySaver()

    def acknowledge(state: MessagesState) -> dict[str, list[AIMessage]]:
        latest_human = next(
            message for message in reversed(state["messages"]) if isinstance(message, HumanMessage)
        )
        return {"messages": [AIMessage(content=f"ack:{latest_human.content}")]}

    builder = StateGraph(MessagesState)
    builder.add_node("acknowledge", acknowledge)
    builder.add_edge(START, "acknowledge")
    builder.add_edge("acknowledge", END)
    graph = builder.compile(checkpointer=checkpointer)
    base_config = langgraph_durable_config(
        tenant_id="tenant_1",
        thread_id="thread_replay_interrupt",
        checkpoint_ns="reactor",
    )
    await graph.ainvoke({"messages": [HumanMessage(content="source")]}, config=base_config)
    source_tuple = await checkpointer.aget_tuple(base_config)
    assert source_tuple is not None
    source_checkpoint_id = checkpoint_id_from_config(source_tuple.config)
    assert source_checkpoint_id is not None
    pinned_config = langgraph_durable_config(
        tenant_id="tenant_1",
        thread_id="thread_replay_interrupt",
        checkpoint_ns="reactor",
        checkpoint_id=source_checkpoint_id,
    )

    await graph.ainvoke({"messages": [HumanMessage(content="child")]}, config=pinned_config)
    recovered = await durable_interrupt_messages(checkpointer, config=pinned_config)

    assert extract_response_text(recovered.messages) == "ack:child"
    pinned_configurable = cast(
        dict[str, object],
        pinned_config.get("configurable", {}),
    )
    assert pinned_configurable["checkpoint_id"] == source_checkpoint_id


async def test_real_create_agent_v2_stream_exposes_interrupt_without_executing_tool(
    monkeypatch: Any,
) -> None:
    model = ToolCallingFakeModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "Webhook:send",
                            "args": {"value": "private-credential"},
                            "id": "call_1",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        ),
        disable_streaming=True,
    )
    real_create_agent = LANGCHAIN_CREATE_AGENT

    def create_with_fake_model(**kwargs: object) -> object:
        kwargs["model"] = model
        return real_create_agent(**kwargs)

    monkeypatch.setattr(
        "reactor.agents.langchain_agent.LANGCHAIN_CREATE_AGENT",
        create_with_fake_model,
    )
    executions: list[str] = []

    async def handler(request: ToolExecutionRequest) -> ToolExecutionResult:
        executions.append(request.tool.qualified_name)
        return ToolExecutionResult.success({"ok": True})

    frames = [
        frame
        async for frame in stream_langchain_agent_events(
            "send it",
            Settings(),
            provider="test",
            model="fake",
            thread_id="thread_stream_1",
            checkpoint_ns="reactor",
            tools=[
                ToolSpec(
                    tenant_id="tenant_1",
                    namespace="Webhook",
                    name="send",
                    description="Send a test webhook.",
                    risk_level="external_side_effect",
                    input_schema={
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                    },
                    output_schema={"type": "object"},
                )
            ],
            tool_handler=handler,
            tenant_id="tenant_1",
            user_id="user_1",
            checkpointer=InMemorySaver(),
            chat_model_factory=RecordingChatModelFactory(),
        )
    ]

    interrupt_frames = [frame for frame in frames if langchain_v2_stream_interrupts(frame)]
    assert len(interrupt_frames) == 1
    assert interrupt_frames[0]["event"] == "on_chain_stream"
    assert interrupt_frames[0]["parent_ids"] == []
    assert executions == []


@pytest.mark.parametrize(
    ("event_type", "parent_ids"),
    [
        ("on_chain_stream", None),
        ("on_chain_stream", ["trace_graph"]),
        ("on_chain_stream", "trace_graph"),
        ("on_chain_end", []),
    ],
)
def test_langchain_v2_stream_interrupts_requires_root_stream_lineage(
    event_type: str,
    parent_ids: object,
) -> None:
    raw_event: dict[str, object] = {
        "event": event_type,
        "data": {"chunk": {"__interrupt__": (Interrupt(value={"approval": "pending"}),)}},
    }
    if parent_ids is not None:
        raw_event["parent_ids"] = parent_ids

    assert langchain_v2_stream_interrupts(raw_event) == ()


async def test_run_langchain_agent_once_fails_closed_on_langgraph_interrupt() -> None:
    agent = FakeLangChainAgent(
        "",
        interrupts=(
            {
                "action_requests": [
                    {
                        "name": "Webhook:send",
                        "args": {"authorization": "private-credential"},
                    }
                ]
            },
        ),
    )

    result = await run_langchain_agent_once(
        "send the webhook",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        agent=agent,
    )

    assert result.interrupted is True
    assert result.response == "Agent run paused for approval."
    assert result.response_metadata == {
        "approval_status": "pending",
        "stop_reason": "langchain_interrupt",
    }
    assert len(result.interrupt_actions) == 1
    assert result.interrupt_actions[0].tool_name == "Webhook:send"
    assert result.interrupt_actions[0].arguments == {"authorization": "private-credential"}
    assert "private-credential" not in repr(result)


async def test_run_langchain_agent_once_fails_closed_on_invalid_interrupt_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = FakeLangChainAgent(
        "",
        interrupts=(Interrupt(value={"action_requests": []}),),
    )
    checkpointer = InMemorySaver()
    checkpoint_reads = 0

    async def record_checkpoint_read(config: RunnableConfig) -> None:
        nonlocal checkpoint_reads
        del config
        checkpoint_reads += 1

    monkeypatch.setattr(checkpointer, "aget_tuple", record_checkpoint_read)

    result = await run_langchain_agent_once(
        "send the webhook",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        agent=agent,
        checkpointer=checkpointer,
    )

    assert result.interrupted is False
    assert result.interrupt_actions == ()
    assert result.response == "Agent run failed because interrupt actions were invalid."
    assert result.response_metadata["stop_reason"] == "interrupt_action_invalid"
    assert result.response_metadata["interrupt_action_status"] == "invalid"
    assert response_policy_terminal_status(result.response_metadata) == "failed"
    assert public_run_metadata(result.response_metadata) == {
        "stop_reason": "interrupt_action_invalid",
        "interrupt_action_status": "invalid",
    }
    assert checkpoint_reads == 0


async def test_run_langchain_agent_once_preserves_interrupt_when_checkpoint_read_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpointer = InMemorySaver()

    async def fail_checkpoint_read(config: RunnableConfig) -> None:
        del config
        raise RuntimeError("checkpoint unavailable")

    monkeypatch.setattr(checkpointer, "aget_tuple", fail_checkpoint_read)
    agent = FakeLangChainAgent(
        "checkpoint fallback",
        interrupts=(
            {
                "action_requests": [
                    {
                        "name": "Webhook:send",
                        "args": {"destination": "test-channel"},
                    }
                ]
            },
        ),
    )

    result = await run_langchain_agent_once(
        "send the webhook",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_checkpoint_failure",
        checkpoint_ns="reactor",
        agent=agent,
        checkpointer=checkpointer,
    )

    assert result.interrupted is True
    assert result.response == "Agent run paused for approval."
    assert result.response_metadata["stop_reason"] == "langchain_interrupt"
    assert result.response_metadata["checkpointEvidenceRecovery"] == {
        "status": "failed",
        "operation": "latest_checkpoint_read",
        "fallback": "graph_output_messages",
    }
    assert [action.tool_name for action in result.interrupt_actions] == ["Webhook:send"]


async def test_durable_interrupt_messages_propagates_checkpoint_read_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpointer = InMemorySaver()

    async def cancel_checkpoint_read(config: RunnableConfig) -> None:
        del config
        raise asyncio.CancelledError

    monkeypatch.setattr(checkpointer, "aget_tuple", cancel_checkpoint_read)

    with pytest.raises(asyncio.CancelledError):
        await durable_interrupt_messages(
            checkpointer,
            config=langgraph_durable_config(
                tenant_id="tenant_1",
                thread_id="thread_cancelled_read",
                checkpoint_ns="reactor",
            ),
        )


def test_extract_langchain_interrupt_actions_preserves_batch_order() -> None:
    output = GraphOutput[dict[str, object]](
        value={},
        interrupts=(
            Interrupt(
                value={
                    "action_requests": [
                        {"name": "Files:write", "args": {"path": "report.txt"}},
                        {"name": "Mail:send", "args": {"to": "private@example.test"}},
                    ]
                }
            ),
        ),
    )

    actions = extract_langchain_interrupt_actions(output)

    assert [action.tool_name for action in actions] == ["Files:write", "Mail:send"]
    assert actions[1].arguments == {"to": "private@example.test"}
    assert "private@example.test" not in repr(actions)


def test_extract_langchain_interrupt_actions_fails_closed_on_malformed_batch() -> None:
    output = GraphOutput[dict[str, object]](
        value={},
        interrupts=(
            Interrupt(
                value={
                    "action_requests": [
                        {"name": "Files:write", "args": {"path": "report.txt"}},
                        {"name": "Broken:no_args"},
                    ]
                }
            ),
        ),
    )

    assert extract_langchain_interrupt_actions(output) == ()


async def test_runner_preserves_langchain_interrupt_status() -> None:
    result = await run_once(
        "send the webhook",
        Settings(default_model_provider="openai", default_model="gpt-5-mini"),
        run_id="run_interrupt",
        tenant_id="tenant_1",
        user_id="user_1",
        thread_id="thread_1",
        runtime="langchain_agent",
        langchain_agent=FakeLangChainAgent(
            "",
            interrupts=(
                {"action_requests": [{"name": "Webhook:send", "args": {"private": "payload"}}]},
            ),
        ),
    )

    assert result.status == "interrupted"
    assert result.response == "Agent run paused for approval."
    assert result.as_response()["metadata"] == {
        "approval_status": "pending",
        "stop_reason": "langchain_interrupt",
    }
    assert [action.tool_name for action in result.interrupt_actions] == ["Webhook:send"]
    assert "payload" not in repr(result.as_response())
    assert "payload" not in repr(result)


async def test_run_langchain_agent_once_records_active_middleware_chain(
    monkeypatch: Any,
) -> None:
    create_agent_calls: list[dict[str, object]] = []

    def fake_create_agent(**kwargs: object) -> FakeLangChainAgent:
        create_agent_calls.append(dict(kwargs))
        return FakeLangChainAgent("agent response")

    monkeypatch.setattr("reactor.agents.langchain_agent.LANGCHAIN_CREATE_AGENT", fake_create_agent)

    result = await run_langchain_agent_once(
        "hello",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        tools=[
            ToolSpec(
                tenant_id="tenant_1",
                namespace="Webhook",
                name="send",
                description="Send webhook.",
                risk_level="external_side_effect",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )
        ],
        tool_handler=unused_tool_handler,
        middleware_policy=LangChainMiddlewarePolicy(
            model_call_run_limit=4,
            tool_call_run_limit=3,
            pii_rules=(PiiMiddlewareRule("email", "block"),),
        ),
        chat_model_factory=RecordingChatModelFactory(),
    )

    assert result.response == "agent response"
    assert result.response_metadata["langchainMiddlewareChain"] == {
        "status": "applied",
        "count": 6,
        "middleware": [
            "ModelCallLimitMiddleware",
            "ToolCallLimitMiddleware",
            "ModelRetryMiddleware",
            "ToolRetryMiddleware",
            "PIIMiddleware",
            "HumanInTheLoopMiddleware",
        ],
        "piiRuleCount": 1,
        "hitlToolCount": 1,
        "fallbackModelCount": 0,
    }
    assert create_agent_calls[0]["middleware"]


async def test_run_langchain_agent_once_passes_tool_invocation_store_to_tools(
    monkeypatch: Any,
) -> None:
    captured: dict[str, object] = {}

    class FakeToolInvocationStore:
        async def save(self, record: Any) -> Any:
            return record

    store = FakeToolInvocationStore()

    def fake_build_langchain_tools(*args: object, **kwargs: object) -> list[object]:
        captured["args"] = args
        captured.update(kwargs)
        return []

    monkeypatch.setattr(
        "reactor.agents.langchain_agent.build_langchain_tools",
        fake_build_langchain_tools,
    )

    result = await run_langchain_agent_once(
        "hello",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        agent=FakeLangChainAgent("agent response"),
        tools=[
            ToolSpec(
                tenant_id="tenant_1",
                namespace="Rag",
                name="hybrid_search",
                description="Search tenant documents.",
                risk_level="read",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )
        ],
        tool_handler=unused_tool_handler,
        tool_invocation_store=cast(Any, store),
    )

    assert result.response == "agent response"
    assert captured["tool_invocation_store"] is store


def test_public_run_metadata_preserves_langchain_middleware_chain() -> None:
    assert public_run_metadata(
        {
            "langchainMiddlewareChain": {
                "status": "applied",
                "count": 5,
                "middleware": ["ModelCallLimitMiddleware"],
                "piiRuleCount": 1,
                "hitlToolCount": 0,
                "fallbackModelCount": 0,
                "raw_payload": "secret",
            }
        }
    ) == {
        "langchainMiddlewareChain": {
            "status": "applied",
            "count": 5,
            "middleware": ["ModelCallLimitMiddleware"],
            "piiRuleCount": 1,
            "hitlToolCount": 0,
            "fallbackModelCount": 0,
        }
    }


def test_public_run_metadata_preserves_sanitized_research_plan() -> None:
    assert public_run_metadata(
        {
            "research_plan": {
                "status": "planned",
                "evidenceStatus": "grounded",
                "citationIds": ["doc_1:0"],
                "sourceLabels": ["https://docs.example/runtime"],
                "sourceCount": 1,
                "answerContract": {
                    "status": "ready",
                    "citationIds": ["doc_1:0"],
                    "sourceLabels": ["https://docs.example/runtime"],
                    "citationStyle": "manifest_ids",
                    "uncitedClaimsAllowed": False,
                    "internalPrompt": "do not expose",
                    "raw_payload": {"api_key": "sk-test-secret"},
                },
                "answerExtraction": {
                    "status": "available",
                    "matchedCitationCount": 1,
                    "hashMismatchCount": 0,
                    "missingChunkCount": 0,
                    "raw_payload": {"api_key": "sk-test-secret"},
                },
                "internalNotes": "do not expose",
                "acl_proof": {"tenant_id": "tenant_1"},
                "raw_payload": {"api_key": "sk-test-secret"},
            }
        }
    ) == {
        "research_plan": {
            "status": "planned",
            "evidenceStatus": "grounded",
            "citationIds": ["doc_1:0"],
            "sourceLabels": ["https://docs.example/runtime"],
            "sourceCount": 1,
            "answerContract": {
                "status": "ready",
                "citationIds": ["doc_1:0"],
                "sourceLabels": ["https://docs.example/runtime"],
                "citationStyle": "manifest_ids",
                "uncitedClaimsAllowed": False,
            },
            "answerExtraction": {
                "status": "available",
                "matchedCitationCount": 1,
                "hashMismatchCount": 0,
                "missingChunkCount": 0,
            },
        }
    }


def test_public_run_metadata_drops_raw_tool_input_aliases() -> None:
    assert public_run_metadata(
        {
            "langchainMiddlewareChain": {
                "status": "applied",
                "count": 1,
                "toolInput": {"api_key": "sk-test-secret"},
                "inputPayload": {"password": "hidden"},
                "tool_arguments": {"url": "https://internal.example"},
                "children": [
                    {
                        "toolInput": {"secret": "hidden"},
                        "status": "kept",
                    }
                ],
            }
        }
    ) == {
        "langchainMiddlewareChain": {
            "status": "applied",
            "count": 1,
            "children": [{"status": "kept"}],
        }
    }


def test_public_run_metadata_preserves_rag_workflow_identity() -> None:
    assert public_run_metadata(
        {
            "candidate_id": "c1",
            "evalCaseId": "case_rag_candidate_c1",
            "workflowTags": [
                "collection:rag-ingestion-candidate",
                "rag",
                "rag-candidate:c1",
            ],
            "raw_payload": {"api_key": "sk-test-secret"},
        }
    ) == {
        "candidate_id": "c1",
        "evalCaseId": "case_rag_candidate_c1",
        "workflowTags": [
            "collection:rag-ingestion-candidate",
            "rag",
            "rag-candidate:c1",
        ],
    }


async def test_run_langchain_agent_once_serializes_structured_response() -> None:
    result = await run_langchain_agent_once(
        "hello",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        response_format="JSON",
        agent=FakeLangChainAgent("ignored", structured_response={"ok": True}),
    )

    assert json.loads(result.response) == {"ok": True}


async def test_run_langchain_agent_once_repairs_fenced_json_response() -> None:
    result = await run_langchain_agent_once(
        "hello",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        response_format="JSON",
        agent=FakeLangChainAgent('```json\n{"answer":"ok"}\n```'),
    )

    assert result.response == '{"answer":"ok"}'
    assert json.loads(result.response) == {"answer": "ok"}


async def test_run_langchain_agent_once_blocks_invalid_json_response() -> None:
    result = await run_langchain_agent_once(
        "hello",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        response_format="JSON",
        agent=FakeLangChainAgent("not json"),
    )

    assert result.response == "Response blocked by structured output policy."
    assert result.response_metadata == {
        "structured_output_status": "invalid",
        "structured_output_error_code": "INVALID_RESPONSE",
        "stop_reason": "structured_output_invalid",
    }


async def test_run_langchain_agent_once_does_not_fallback_from_empty_structured_response() -> None:
    result = await run_langchain_agent_once(
        "hello",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        response_format="JSON",
        agent=FakeLangChainAgent('{"unstructured":"must not be used"}', structured_response=""),
    )

    assert result.response == "Response blocked by structured output policy."
    assert result.response_metadata == {
        "structured_output_status": "invalid",
        "structured_output_error_code": "INVALID_RESPONSE",
        "stop_reason": "structured_output_invalid",
    }


async def test_run_langchain_agent_once_blocks_unserializable_structured_response() -> None:
    result = await run_langchain_agent_once(
        "hello",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        response_format="JSON",
        agent=FakeLangChainAgent(
            '{"unstructured":"must not be used"}',
            structured_response={"unsupported": {"set-value"}},
        ),
    )

    assert result.response == "Response blocked by structured output policy."
    assert result.response_metadata == {
        "structured_output_status": "invalid",
        "structured_output_error_code": "STRUCTURED_RESPONSE_SERIALIZATION_FAILED",
        "stop_reason": "structured_output_invalid",
    }


async def test_run_langchain_agent_once_requires_context_manifest_citations() -> None:
    result = await run_langchain_agent_once(
        "hello",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        response_format="JSON",
        structured_output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        context_manifest={
            "sections": [
                {
                    "name": "rag_context",
                    "metadata": {
                        "chunk_count": 1,
                        "citation_id": "policy_doc:3",
                        "citations": [{"citation_id": "policy_doc:3"}],
                    },
                }
            ]
        },
        agent=FakeLangChainAgent('{"answer":"grounded but missing citations"}'),
    )

    assert result.response == "Response blocked by structured output policy."
    assert result.response_metadata == {
        "structured_output_status": "invalid",
        "structured_output_error_code": "INVALID_RESPONSE",
        "stop_reason": "structured_output_invalid",
        "structured_output_citation_policy": "required",
        "structured_output_citation_count": 1,
        "structured_output_allowed_citation_ids": ["policy_doc:3"],
    }


async def test_run_langchain_agent_once_promotes_runtime_rag_citations_before_boundary() -> None:
    citation = {
        "citation_id": "policy_doc:3",
        "source_uri": "https://docs.example/policy",
        "document_id": "policy_doc",
        "chunk_index": 3,
        "content_hash": "sha256:policy",
        "acl_hash": "sha256:acl",
    }
    model_visible_text = "[tool_output:data]\n" + json.dumps(
        {
            "schema": "reactor.tool_result.v1",
            "status": "succeeded",
            "tool_id": "Rag:hybrid_search",
            "idempotency_key": "tool:rag",
            "payload": {
                "chunks": [citation],
                "citations": [citation],
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    class AgentWithRuntimeRagCitation(FakeLangChainAgent):
        async def ainvoke(
            self,
            input: object,
            config: RunnableConfig | None = None,
            *,
            version: str = "v1",
        ) -> object:
            self.calls.append({"input": input, "config": config or {}, "version": version})
            return {
                "messages": [
                    HumanMessage(content="search"),
                    ToolMessage(
                        content=model_visible_text,
                        tool_call_id="call_rag",
                        artifact={
                            "schema": "reactor.tool_result.v1",
                            "status": "succeeded",
                            "tool_id": "Rag:hybrid_search",
                            "idempotency_key": "tool:rag",
                            "model_visible_text": model_visible_text,
                            "sanitizer_findings": [],
                            "rag_context_manifest": {
                                "chunk_count": 1,
                                "cited_chunk_count": 1,
                                "uncited_chunk_count": 0,
                                "citation_count": 1,
                                "citation_id": "policy_doc:3",
                                "citations": [citation],
                            },
                        },
                    ),
                    AIMessage(content='{"answer":"grounded","citations":["policy_doc:3"]}'),
                ]
            }

    context_manifest: dict[str, object] = {
        "sections": [
            {
                "name": "rag_context",
                "source_type": "rag",
                "metadata": {
                    "chunk_count": 1,
                    "citation_count": 0,
                    "citations": [],
                },
            }
        ]
    }
    result = await run_langchain_agent_once(
        "search",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        response_format="JSON",
        structured_output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        context_manifest=context_manifest,
        agent=AgentWithRuntimeRagCitation("unused"),
    )

    assert json.loads(result.response) == {
        "answer": "grounded",
        "citations": ["policy_doc:3"],
    }
    assert result.response_metadata["structured_output_status"] == "valid"
    assert result.response_metadata["structured_output_allowed_citation_ids"] == ["policy_doc:3"]
    manifest = cast(dict[str, object], result.response_metadata["contextManifest"])
    sections = cast(list[dict[str, object]], manifest["sections"])
    rag_section = next(section for section in sections if section["name"] == "rag_context")
    assert cast(dict[str, object], rag_section["metadata"])["citations"] == [
        {
            "citation_id": "policy_doc:3",
            "source_uri": "https://docs.example/policy",
            "document_id": "policy_doc",
            "chunk_index": 3,
            "content_hash": "sha256:policy",
            "acl_hash": "sha256:acl",
        }
    ]


async def test_run_langchain_agent_once_blocks_oversized_runtime_rag_citation_id() -> None:
    oversized_citation_id = "x" * 257

    class AgentWithOversizedRuntimeCitation(FakeLangChainAgent):
        async def ainvoke(
            self,
            input: object,
            config: RunnableConfig | None = None,
            *,
            version: str = "v1",
        ) -> object:
            self.calls.append({"input": input, "config": config or {}, "version": version})
            return {
                "messages": [
                    ToolMessage(
                        content="[tool_output:data]\n{}",
                        tool_call_id="call_rag",
                        artifact={
                            "schema": "reactor.tool_result.v1",
                            "status": "succeeded",
                            "tool_id": "Rag:hybrid_search",
                            "idempotency_key": "tool:rag:oversized",
                            "model_visible_text": "[tool_output:data]\n{}",
                            "sanitizer_findings": [],
                            "rag_context_manifest": {
                                "chunk_count": 1,
                                "cited_chunk_count": 1,
                                "invalid_citation_id_count": 1,
                                "citations": [
                                    {
                                        "citation_id": oversized_citation_id,
                                        "source_uri": "https://docs.example/runtime",
                                    }
                                ],
                            },
                        },
                    ),
                    AIMessage(content='{"answer":"grounded","citations":["baseline:1"]}'),
                ]
            }

    result = await run_langchain_agent_once(
        "search",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        response_format="JSON",
        structured_output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        context_manifest={
            "sections": [
                {
                    "name": "rag_context",
                    "metadata": {
                        "chunk_count": 1,
                        "citation_id": "baseline:1",
                        "citations": [{"citation_id": "baseline:1"}],
                    },
                }
            ]
        },
        agent=AgentWithOversizedRuntimeCitation("unused"),
    )

    assert result.response == "Response blocked by structured output policy."
    assert result.response_metadata["structured_output_error_code"] == (
        "UNSAFE_CONTEXT_CITATION_IDS"
    )
    assert result.response_metadata["structured_output_unsafe_citation_count"] == 1
    assert oversized_citation_id not in json.dumps(result.response_metadata)


async def test_run_langchain_agent_once_blocks_orphan_runtime_rag_citation_claims() -> None:
    model_visible_text = "[tool_output:data]\n" + json.dumps(
        {
            "schema": "reactor.tool_result.v1",
            "status": "succeeded",
            "tool_id": "Rag:hybrid_search",
            "idempotency_key": "tool:rag:orphan",
            "payload": {
                "chunks": [
                    {"citation_id": "duplicate:1"},
                    {"citation_id": "duplicate:1"},
                    {"citation_id": "bad id"},
                    {"citation_id": "matched:1", "document_id": "doc_good"},
                ],
                "citations": [
                    {"citation_id": "orphan:1"},
                    {"citation_id": "matched:1", "document_id": "doc_bad"},
                ],
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    class AgentWithOrphanRuntimeCitation(FakeLangChainAgent):
        async def ainvoke(
            self,
            input: object,
            config: RunnableConfig | None = None,
            *,
            version: str = "v1",
        ) -> object:
            self.calls.append({"input": input, "config": config or {}, "version": version})
            return {
                "messages": [
                    ToolMessage(
                        content=model_visible_text,
                        tool_call_id="call_rag",
                        artifact={
                            "schema": "reactor.tool_result.v1",
                            "status": "succeeded",
                            "tool_id": "Rag:hybrid_search",
                            "idempotency_key": "tool:rag:orphan",
                            "model_visible_text": model_visible_text,
                            "sanitizer_findings": [],
                            "rag_context_manifest": {
                                "chunk_count": 4,
                                "cited_chunk_count": 0,
                                "uncited_chunk_count": 4,
                                "citation_count": 0,
                                "orphan_citation_id_count": 1,
                                "citation_metadata_mismatch_count": 1,
                                "duplicate_chunk_citation_id_count": 1,
                                "invalid_chunk_citation_id_count": 1,
                                "citations": [],
                            },
                        },
                    ),
                    AIMessage(content='{"answer":"grounded","citations":["baseline:1"]}'),
                ]
            }

    result = await run_langchain_agent_once(
        "search",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        response_format="JSON",
        structured_output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        context_manifest={
            "sections": [
                {
                    "name": "rag_context",
                    "metadata": {
                        "chunk_count": 1,
                        "citation_id": "baseline:1",
                        "citations": [{"citation_id": "baseline:1"}],
                    },
                }
            ]
        },
        agent=AgentWithOrphanRuntimeCitation("unused"),
    )

    assert result.response == "Response blocked by structured output policy."
    assert result.response_metadata["structured_output_error_code"] == (
        "UNSAFE_CONTEXT_CITATION_IDS"
    )
    assert result.response_metadata["structured_output_unsafe_citation_count"] == 4
    manifest = cast(dict[str, object], result.response_metadata["contextManifest"])
    sections = cast(list[dict[str, object]], manifest["sections"])
    rag_section = next(section for section in sections if section["name"] == "rag_context")
    assert cast(dict[str, object], rag_section["metadata"])["runtime_orphan_citation_id_count"] == 1
    assert (
        cast(dict[str, object], rag_section["metadata"])["runtime_citation_metadata_mismatch_count"]
        == 1
    )
    assert (
        cast(dict[str, object], rag_section["metadata"])[
            "runtime_duplicate_chunk_citation_id_count"
        ]
        == 1
    )
    assert (
        cast(dict[str, object], rag_section["metadata"])["runtime_invalid_chunk_citation_id_count"]
        == 1
    )


async def test_run_langchain_agent_once_blocks_omitted_runtime_rag_citations() -> None:
    class AgentWithOmittedRuntimeCitations(FakeLangChainAgent):
        async def ainvoke(
            self,
            input: object,
            config: RunnableConfig | None = None,
            *,
            version: str = "v1",
        ) -> object:
            self.calls.append({"input": input, "config": config or {}, "version": version})
            return {
                "messages": [
                    ToolMessage(
                        content="[tool_output:data]\n{}",
                        tool_call_id="call_rag",
                        artifact={
                            "schema": "reactor.tool_result.v1",
                            "status": "succeeded",
                            "tool_id": "Rag:hybrid_search",
                            "idempotency_key": "tool:rag:omitted",
                            "model_visible_text": "[tool_output:data]\n{}",
                            "sanitizer_findings": [],
                            "rag_context_manifest": {
                                "chunk_count": 21,
                                "cited_chunk_count": 20,
                                "omitted_citation_count": 1,
                                "citations": [{"citation_id": "runtime:1"}],
                            },
                        },
                    ),
                    AIMessage(content='{"answer":"grounded","citations":["baseline:1"]}'),
                ]
            }

    result = await run_langchain_agent_once(
        "search",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        response_format="JSON",
        structured_output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        context_manifest={
            "sections": [
                {
                    "name": "rag_context",
                    "metadata": {
                        "chunk_count": 1,
                        "citation_id": "baseline:1",
                        "citations": [{"citation_id": "baseline:1"}],
                    },
                }
            ]
        },
        agent=AgentWithOmittedRuntimeCitations("unused"),
    )

    assert result.response == "Response blocked by structured output policy."
    assert result.response_metadata["structured_output_error_code"] == (
        "UNSAFE_CONTEXT_CITATION_IDS"
    )
    assert result.response_metadata["structured_output_unsafe_citation_count"] == 1


async def test_run_langchain_agent_once_blocks_failed_rag_artifact_citation_claims() -> None:
    forged_citation_id = "forged:1"
    foreign_citation_id = "foreign:1"

    class AgentWithFailedRagArtifact(FakeLangChainAgent):
        async def ainvoke(
            self,
            input: object,
            config: RunnableConfig | None = None,
            *,
            version: str = "v1",
        ) -> object:
            self.calls.append({"input": input, "config": config or {}, "version": version})
            return {
                "messages": [
                    ToolMessage(
                        content="[tool_output:data]\n{}",
                        tool_call_id="call_rag",
                        artifact={
                            "schema": "reactor.tool_result.v1",
                            "status": "failed",
                            "tool_id": "Rag:hybrid_search",
                            "idempotency_key": "tool:rag:failed",
                            "model_visible_text": "[tool_output:data]\n{}",
                            "sanitizer_findings": [],
                            "rag_context_manifest": {
                                "chunk_count": 1,
                                "cited_chunk_count": 1,
                                "citations": [{"citation_id": forged_citation_id}],
                            },
                        },
                    ),
                    ToolMessage(
                        content="[tool_output:data]\n{}",
                        tool_call_id="call_foreign_rag",
                        artifact={
                            "schema": "foreign.tool_result.v1",
                            "status": "succeeded",
                            "tool_id": "Rag:hybrid_search",
                            "idempotency_key": "tool:rag:foreign",
                            "model_visible_text": "[tool_output:data]\n{}",
                            "sanitizer_findings": [],
                            "rag_context_manifest": {
                                "chunk_count": 1,
                                "cited_chunk_count": 1,
                                "citations": [{"citation_id": foreign_citation_id}],
                            },
                        },
                    ),
                    AIMessage(content='{"answer":"grounded","citations":["baseline:1"]}'),
                ]
            }

    result = await run_langchain_agent_once(
        "search",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        response_format="JSON",
        structured_output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        context_manifest={
            "sections": [
                {
                    "name": "rag_context",
                    "metadata": {
                        "chunk_count": 1,
                        "citation_id": "baseline:1",
                        "citations": [{"citation_id": "baseline:1"}],
                    },
                }
            ]
        },
        agent=AgentWithFailedRagArtifact("unused"),
    )

    assert result.response == "Response blocked by structured output policy."
    assert result.response_metadata["structured_output_error_code"] == (
        "UNSAFE_CONTEXT_CITATION_IDS"
    )
    assert result.response_metadata["structured_output_unsafe_citation_count"] == 2
    assert forged_citation_id not in json.dumps(result.response_metadata)
    assert foreign_citation_id not in json.dumps(result.response_metadata)


async def test_run_langchain_agent_once_blocks_rag_artifact_manifest_mismatch() -> None:
    forged_citation_id = "forged:1"
    model_visible_text = (
        '[tool_output:data]\n{"idempotency_key":"tool:rag:forged",'
        '"payload":{"chunks":[],"citations":[]},'
        '"schema":"reactor.tool_result.v1","status":"succeeded",'
        '"tool_id":"Rag:hybrid_search"}'
    )

    class AgentWithMismatchedRagArtifact(FakeLangChainAgent):
        async def ainvoke(
            self,
            input: object,
            config: RunnableConfig | None = None,
            *,
            version: str = "v1",
        ) -> object:
            self.calls.append({"input": input, "config": config or {}, "version": version})
            return {
                "messages": [
                    ToolMessage(
                        content=model_visible_text,
                        tool_call_id="call_rag",
                        artifact={
                            "schema": "reactor.tool_result.v1",
                            "status": "succeeded",
                            "tool_id": "Rag:hybrid_search",
                            "idempotency_key": "tool:rag:forged",
                            "model_visible_text": model_visible_text,
                            "sanitizer_findings": [],
                            "rag_context_manifest": {
                                "chunk_count": 1,
                                "cited_chunk_count": 1,
                                "citations": [{"citation_id": forged_citation_id}],
                            },
                        },
                    ),
                    AIMessage(
                        content=json.dumps(
                            {
                                "answer": "forged",
                                "citations": [forged_citation_id],
                            }
                        )
                    ),
                ]
            }

    result = await run_langchain_agent_once(
        "search",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        response_format="JSON",
        structured_output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        agent=AgentWithMismatchedRagArtifact("unused"),
    )

    assert result.response == "Response blocked by structured output policy."
    assert result.response_metadata["structured_output_error_code"] == (
        "UNSAFE_CONTEXT_CITATION_IDS"
    )
    assert result.response_metadata["structured_output_unsafe_citation_count"] == 1
    assert forged_citation_id not in json.dumps(result.response_metadata)


async def test_run_langchain_agent_once_blocks_unsafe_context_manifest_citations() -> None:
    result = await run_langchain_agent_once(
        "hello",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        response_format="JSON",
        structured_output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        context_manifest={
            "sections": [
                {
                    "name": "rag_context",
                    "metadata": {
                        "chunk_count": 1,
                        "citation_id": "doc bad/path:3",
                        "citations": [{"citation_id": "doc bad/path:3"}],
                    },
                }
            ]
        },
        agent=FakeLangChainAgent('{"answer":"grounded","citations":["doc bad/path:3"]}'),
    )

    assert result.response == "Response blocked by structured output policy."
    assert result.response_metadata == {
        "structured_output_status": "invalid",
        "structured_output_error_code": "UNSAFE_CONTEXT_CITATION_IDS",
        "stop_reason": "structured_output_invalid",
        "structured_output_citation_policy": "required",
        "structured_output_citation_count": 0,
        "structured_output_allowed_citation_ids": [],
        "structured_output_unsafe_citation_count": 1,
    }


async def test_run_langchain_agent_once_blocks_structured_response_schema_mismatch() -> None:
    result = await run_langchain_agent_once(
        "hello",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        response_format="JSON",
        structured_output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        agent=FakeLangChainAgent("ignored", structured_response={"ok": True}),
    )

    assert result.response == "Response blocked by structured output policy."


async def test_run_langchain_agent_once_enforces_schema_without_explicit_response_format() -> None:
    result = await run_langchain_agent_once(
        "hello",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        structured_output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        agent=FakeLangChainAgent("ignored", structured_response={"ok": True}),
    )

    assert result.response == "Response blocked by structured output policy."
    assert result.response_metadata == {
        "structured_output_status": "invalid",
        "structured_output_error_code": "INVALID_RESPONSE",
        "stop_reason": "structured_output_invalid",
    }


async def test_run_langchain_agent_once_serializes_string_structured_response() -> None:
    result = await run_langchain_agent_once(
        "hello",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        structured_output_schema={"type": "string"},
        agent=FakeLangChainAgent("ignored", structured_response="approved"),
    )

    assert result.response == '"approved"'
    assert result.response_metadata == {"structured_output_status": "valid"}


async def test_run_langchain_agent_once_serializes_pydantic_structured_response() -> None:
    class AnswerSchema(BaseModel):
        answer: str
        confidence: float

    result = await run_langchain_agent_once(
        "hello",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        response_format="JSON",
        agent=FakeLangChainAgent(
            "ignored",
            structured_response=AnswerSchema(answer="ok", confidence=0.8),
        ),
    )

    assert json.loads(result.response) == {"answer": "ok", "confidence": 0.8}


async def test_run_langchain_agent_once_serializes_dataclass_structured_response() -> None:
    @dataclass(frozen=True)
    class Answer:
        answer: str
        confidence: float

    result = await run_langchain_agent_once(
        "hello",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        response_format="JSON",
        agent=FakeLangChainAgent(
            "ignored",
            structured_response=Answer(answer="ok", confidence=0.8),
        ),
    )

    assert json.loads(result.response) == {"answer": "ok", "confidence": 0.8}


async def test_stream_langchain_agent_events_uses_native_astream_events() -> None:
    agent = FakeLangChainAgent("streamed")

    events = [
        event
        async for event in stream_langchain_agent_events(
            "hello",
            Settings(max_output_tokens=100),
            provider="openai",
            model="gpt-5-mini",
            thread_id="thread_1",
            checkpoint_ns="reactor",
            agent=agent,
        )
    ]

    assert events == [
        {
            "event": "on_chain_stream",
            "run_id": "trace_model",
            "metadata": {"langgraph_node": "model"},
            "data": {"chunk": {"response_text": "streamed"}},
        }
    ]
    assert agent.stream_calls == [
        {
            "input": {"messages": [HumanMessage(content="hello")]},
            "config": {
                "recursion_limit": 25,
                "run_name": "reactor.langchain_agent.stream",
                "tags": ["reactor", "runtime:langchain_agent"],
                "metadata": {"reactor.runtime": "langchain_agent"},
                "configurable": {
                    "thread_id": langgraph_checkpoint_thread_id(
                        tenant_id="local",
                        thread_id="thread_1",
                        checkpoint_ns="reactor",
                    ),
                    "checkpoint_ns": "",
                },
            },
            "version": "v2",
        }
    ]


async def test_stream_langchain_agent_events_does_not_claim_tools_without_handler(
    monkeypatch: Any,
) -> None:
    captured: dict[str, object] = {}

    def fake_build_langchain_agent(_settings: Settings, **kwargs: object) -> FakeLangChainAgent:
        captured.update(kwargs)
        return FakeLangChainAgent("streamed")

    monkeypatch.setattr(
        "reactor.agents.langchain_agent.build_langchain_agent",
        fake_build_langchain_agent,
    )

    events = [
        event
        async for event in stream_langchain_agent_events(
            "reply in thread",
            Settings(max_output_tokens=100),
            provider="openai",
            model="gpt-5-mini",
            thread_id="thread_1",
            checkpoint_ns="reactor",
            tools=[
                ToolSpec(
                    tenant_id="tenant_1",
                    namespace="Slack",
                    name="send_message",
                    description="Send a Slack reply.",
                    risk_level="external_side_effect",
                    input_schema={"type": "object"},
                    output_schema={"type": "object"},
                    enabled=True,
                )
            ],
            tool_handler=None,
            integration_context={"channel": "slack", "slack_channel_id": "C123"},
        )
    ]

    system_prompt = cast(str, captured["system_prompt"])
    assert events
    assert captured["tools"] == []
    assert "Slack surface: native gateway context only." in system_prompt
    assert "Slack tools available" not in system_prompt


async def test_stream_langchain_agent_events_passes_explicit_native_middleware_chain(
    monkeypatch: Any,
) -> None:
    captured: dict[str, object] = {}

    def fake_build_langchain_agent(_settings: Settings, **kwargs: object) -> FakeLangChainAgent:
        captured.update(kwargs)
        return FakeLangChainAgent("streamed")

    monkeypatch.setattr(
        "reactor.agents.langchain_agent.build_langchain_agent",
        fake_build_langchain_agent,
    )

    events = [
        event
        async for event in stream_langchain_agent_events(
            "use tools",
            Settings(max_output_tokens=100),
            provider="openai",
            model="gpt-5-mini",
            thread_id="thread_1",
            checkpoint_ns="reactor",
            tools=[
                ToolSpec(
                    tenant_id="tenant_1",
                    namespace="Webhook",
                    name="send",
                    description="Send webhook.",
                    risk_level="external_side_effect",
                    input_schema={"type": "object"},
                    output_schema={"type": "object"},
                )
            ],
            tool_handler=unused_tool_handler,
            middleware_policy=LangChainMiddlewarePolicy(
                model_call_run_limit=4,
                tool_call_run_limit=3,
                pii_rules=(PiiMiddlewareRule("email", "block"),),
            ),
        )
    ]

    middleware_names = [
        type(item).__name__ for item in cast(Sequence[object], captured["middleware"])
    ]
    assert events
    assert middleware_names == [
        "ModelCallLimitMiddleware",
        "ToolCallLimitMiddleware",
        "ModelRetryMiddleware",
        "ToolRetryMiddleware",
        "PIIMiddleware",
        "HumanInTheLoopMiddleware",
    ]
    assert captured["interrupt_on_tools"] == ("Webhook:send",)
    assert captured["fallback_models"] == ()


async def test_run_langchain_agent_once_interrupts_on_approval_required_tools(
    monkeypatch: Any,
) -> None:
    captured: dict[str, object] = {}

    def fake_build_langchain_agent(_settings: Settings, **kwargs: object) -> FakeLangChainAgent:
        captured.update(kwargs)
        return FakeLangChainAgent("ok")

    monkeypatch.setattr(
        "reactor.agents.langchain_agent.build_langchain_agent",
        fake_build_langchain_agent,
    )

    await run_langchain_agent_once(
        "use tools",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        tools=[
            ToolSpec(
                tenant_id="tenant_1",
                namespace="Rag",
                name="hybrid_search",
                description="Search.",
                risk_level="read",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
            ToolSpec(
                tenant_id="tenant_1",
                namespace="Webhook",
                name="send",
                description="Send webhook.",
                risk_level="external_side_effect",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
        ],
        tool_handler=unused_tool_handler,
        tenant_id="tenant_1",
        user_id="user_1",
    )

    assert captured["interrupt_on_tools"] == ("Webhook:send",)


async def test_langchain_hitl_middleware_owns_write_tool_approval_after_resume(
    monkeypatch: Any,
) -> None:
    captured: dict[str, object] = {}

    def fake_build_langchain_tools(*args: object, **kwargs: object) -> list[object]:
        captured.update(kwargs)
        return []

    def fake_build_langchain_agent(_settings: Settings, **_kwargs: object) -> FakeLangChainAgent:
        return FakeLangChainAgent("ok")

    monkeypatch.setattr(
        "reactor.agents.langchain_agent.build_langchain_tools",
        fake_build_langchain_tools,
    )
    monkeypatch.setattr(
        "reactor.agents.langchain_agent.build_langchain_agent",
        fake_build_langchain_agent,
    )

    await run_langchain_agent_once(
        "send",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        tools=[
            ToolSpec(
                tenant_id="tenant_1",
                namespace="Webhook",
                name="send",
                description="Send webhook.",
                risk_level="external_side_effect",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )
        ],
        tool_handler=unused_tool_handler,
        tenant_id="tenant_1",
        user_id="user_1",
    )

    assert cast(ToolPolicy, captured["policy"]).allow_write_without_approval is True


async def test_injected_langchain_agent_keeps_wrapper_write_approval_gate(
    monkeypatch: Any,
) -> None:
    captured: dict[str, object] = {}

    def fake_build_langchain_tools(*args: object, **kwargs: object) -> list[object]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(
        "reactor.agents.langchain_agent.build_langchain_tools",
        fake_build_langchain_tools,
    )

    await run_langchain_agent_once(
        "send",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        agent=FakeLangChainAgent("ok"),
        tools=[
            ToolSpec(
                tenant_id="tenant_1",
                namespace="Webhook",
                name="send",
                description="Send webhook.",
                risk_level="external_side_effect",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )
        ],
        tool_handler=unused_tool_handler,
        tenant_id="tenant_1",
        user_id="user_1",
    )

    assert cast(ToolPolicy, captured["policy"]).allow_write_without_approval is False


async def test_run_langchain_agent_once_exposes_only_enabled_slack_tools_in_context(
    monkeypatch: Any,
) -> None:
    captured: dict[str, object] = {}

    def fake_build_langchain_agent(_settings: Settings, **kwargs: object) -> FakeLangChainAgent:
        captured.update(kwargs)
        return FakeLangChainAgent("ok")

    monkeypatch.setattr(
        "reactor.agents.langchain_agent.build_langchain_agent",
        fake_build_langchain_agent,
    )

    await run_langchain_agent_once(
        "reply in thread",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        system_prompt="Follow tenant policy.",
        tools=[
            ToolSpec(
                tenant_id="tenant_1",
                namespace="Slack",
                name="send_message",
                description="Send a Slack reply.",
                risk_level="external_side_effect",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                enabled=True,
            ),
            ToolSpec(
                tenant_id="tenant_1",
                namespace="SlackMCP",
                name="search_history",
                description="Search Slack history.",
                risk_level="read",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                enabled=False,
            ),
        ],
        tool_handler=unused_tool_handler,
        tenant_id="tenant_1",
        user_id="user_1",
        integration_context={"channel": "slack", "slack_channel_id": "C123"},
    )

    system_prompt = cast(str, captured["system_prompt"])
    assert "Slack tools available: Slack:send_message." in system_prompt
    assert "SlackMCP:search_history" not in system_prompt


async def test_run_langchain_agent_once_does_not_claim_tools_without_handler(
    monkeypatch: Any,
) -> None:
    captured: dict[str, object] = {}

    def fake_build_langchain_agent(_settings: Settings, **kwargs: object) -> FakeLangChainAgent:
        captured.update(kwargs)
        return FakeLangChainAgent("ok")

    monkeypatch.setattr(
        "reactor.agents.langchain_agent.build_langchain_agent",
        fake_build_langchain_agent,
    )

    await run_langchain_agent_once(
        "reply in thread",
        Settings(max_output_tokens=100),
        provider="openai",
        model="gpt-5-mini",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        tools=[
            ToolSpec(
                tenant_id="tenant_1",
                namespace="Slack",
                name="send_message",
                description="Send a Slack reply.",
                risk_level="external_side_effect",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                enabled=True,
            )
        ],
        tool_handler=None,
        integration_context={"channel": "slack", "slack_channel_id": "C123"},
    )

    system_prompt = cast(str, captured["system_prompt"])
    assert captured["tools"] == []
    assert "Slack surface: native gateway context only." in system_prompt
    assert "Slack tools available" not in system_prompt


async def test_runner_uses_langchain_agent_runtime_when_requested() -> None:
    result = await run_once(
        "hello",
        Settings(default_model_provider="openai", default_model="gpt-5-mini"),
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        thread_id="thread_1",
        runtime="langchain_agent",
        langchain_agent=FakeLangChainAgent("native response"),
    )

    assert result.response == "native response"
    assert result.provider == "openai"
    assert result.model == "gpt-5-mini"
    assert result.run_id == "run_1"
    assert result.thread_id == "thread_1"


async def test_runner_rejects_langchain_structured_output_policy_failure() -> None:
    result = await run_once(
        "reply as json",
        Settings(default_model_provider="openai", default_model="gpt-5-mini"),
        run_id="run_invalid_json",
        tenant_id="tenant_1",
        user_id="user_1",
        thread_id="thread_1",
        runtime="langchain_agent",
        response_format="JSON",
        langchain_agent=FakeLangChainAgent("not json"),
    )

    assert result.status == "rejected"
    assert result.response == "Response blocked by structured output policy."
    assert result.response_metadata["stop_reason"] == "structured_output_invalid"


async def test_runner_times_out_langchain_agent_runtime_with_structured_result() -> None:
    result = await run_once(
        "hello",
        Settings(
            default_model_provider="openai",
            default_model="gpt-5-mini",
            agent_run_timeout_ms=1,
        ),
        run_id="run_timeout",
        tenant_id="tenant_1",
        user_id="user_1",
        thread_id="thread_1",
        runtime="langchain_agent",
        langchain_agent=HangingLangChainAgent(),
    )

    assert result.status == "timeout"
    assert result.response == "Agent run timed out after 1ms."
    assert result.provider == "openai"
    assert result.model == "gpt-5-mini"
    assert result.token_usage is not None


@pytest.mark.parametrize("runtime", ["langgraph", "langchain_agent"])
async def test_runner_propagates_external_cancellation_to_native_and_langchain_invocations(
    runtime: str,
) -> None:
    class CancellationAwareRunnable:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.cancelled = False

        async def ainvoke(
            self,
            input: object,
            config: RunnableConfig | None = None,
            *,
            version: str = "v1",
        ) -> dict[str, object]:
            _ = input, config, version
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            return {"messages": [AIMessage(content="unreachable")]}

        async def astream_events(
            self,
            input: dict[str, object],
            config: RunnableConfig | None = None,
            *,
            version: str,
        ):
            _ = input, config, version
            if False:
                yield {}

    runnable = CancellationAwareRunnable()
    task = asyncio.create_task(
        run_once(
            "cancel this run",
            Settings(agent_run_timeout_ms=10_000),
            run_id="run_cancelled",
            tenant_id="tenant_1",
            user_id="user_1",
            thread_id="thread_1",
            runtime=runtime,
            graph=runnable if runtime == "langgraph" else None,
            langchain_agent=runnable if runtime == "langchain_agent" else None,
        )
    )
    await asyncio.wait_for(runnable.started.wait(), timeout=1)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert runnable.cancelled is True


async def test_runner_invokes_langgraph_with_versioned_state_and_durable_config() -> None:
    class FakeGraph:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def ainvoke(
            self,
            input: object,
            config: dict[str, object] | None = None,
        ) -> dict[str, object]:
            self.calls.append({"input": input, "config": config or {}})
            return {"response_text": "graph response", "messages": []}

    graph = FakeGraph()

    result = await run_once(
        "hello",
        Settings(default_model_provider="openai", default_model="gpt-5-mini"),
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        thread_id="thread_1",
        graph=graph,
        provider="anthropic",
        model="claude-sonnet-5",
        system_prompt="Follow tenant policy.",
    )

    assert result.response == "graph response"
    assert result.provider == "anthropic"
    assert result.model == "claude-sonnet-5"
    graph_input = graph.calls[0]["input"]
    assert isinstance(graph_input, dict)
    assert graph_input["state_schema_version"] == REACTOR_STATE_SCHEMA_VERSION
    assert graph_input["model_provider"] == "anthropic"
    assert graph_input["selected_model"] == "claude-sonnet-5"
    assert graph_input["request_system_prompt"] == "Follow tenant policy."
    assert graph.calls[0]["config"] == {
        "recursion_limit": 25,
        "run_name": "reactor.langgraph.invoke",
        "tags": ["reactor", "runtime:langgraph"],
        "metadata": {"reactor.runtime": "langgraph"},
        "configurable": {
            "thread_id": langgraph_checkpoint_thread_id(
                tenant_id="tenant_1",
                thread_id="thread_1",
                checkpoint_ns="reactor",
            ),
            "checkpoint_ns": "",
        },
    }


async def test_runner_rejects_native_graph_structured_output_policy_failure() -> None:
    class StructuredFailureGraph:
        async def ainvoke(
            self,
            input: object,
            config: dict[str, object] | None = None,
        ) -> dict[str, object]:
            _ = input, config
            return {
                "response_text": "Response blocked by structured output policy.",
                "response_metadata": {
                    "structured_output_status": "invalid",
                    "stop_reason": "structured_output_invalid",
                },
            }

    result = await run_once(
        "reply as json",
        Settings(),
        run_id="run_invalid_native_json",
        tenant_id="tenant_1",
        user_id="user_1",
        thread_id="thread_1",
        graph=StructuredFailureGraph(),
        response_format="JSON",
    )

    assert result.status == "rejected"
    assert result.response_metadata["stop_reason"] == "structured_output_invalid"


async def test_runner_times_out_langgraph_execution_with_structured_result() -> None:
    class HangingGraph:
        async def ainvoke(
            self,
            input: object,
            config: dict[str, object] | None = None,
        ) -> dict[str, object]:
            await asyncio.Event().wait()
            return {"response_text": "unreachable", "messages": []}

    result = await run_once(
        "hello",
        Settings(
            default_model_provider="openai",
            default_model="gpt-5-mini",
            agent_run_timeout_ms=1,
        ),
        run_id="run_timeout",
        tenant_id="tenant_1",
        user_id="user_1",
        thread_id="thread_1",
        graph=HangingGraph(),
    )

    assert result.status == "timeout"
    assert result.response == "Agent run timed out after 1ms."
    assert result.provider == "openai"
    assert result.model == "gpt-5-mini"
    assert result.token_usage is not None


async def test_runner_passes_response_format_to_langchain_agent_runtime(
    monkeypatch: Any,
) -> None:
    captured: dict[str, object] = {}

    async def fake_run_langchain_agent_once(
        _message: str,
        _settings: Settings,
        **kwargs: object,
    ) -> object:
        captured.update(kwargs)
        return FakeLangChainAgentResult("native response")

    monkeypatch.setattr(
        "reactor.agents.runner.run_langchain_agent_once",
        fake_run_langchain_agent_once,
    )

    await run_once(
        "hello",
        Settings(default_model_provider="openai", default_model="gpt-5-mini"),
        run_id="run_1",
        thread_id="thread_1",
        response_format="JSON",
        runtime="langchain_agent",
    )

    assert captured["response_format"] == "JSON"


async def test_runner_preserves_langchain_agent_structured_output_metadata(
    monkeypatch: Any,
) -> None:
    async def fake_run_langchain_agent_once(
        _message: str,
        _settings: Settings,
        **_kwargs: object,
    ) -> object:
        return FakeLangChainAgentResult(
            "Response blocked by structured output policy.",
            response_metadata={
                "structured_output_status": "invalid",
                "structured_output_error_code": "INVALID_RESPONSE",
                "stop_reason": "structured_output_invalid",
            },
        )

    monkeypatch.setattr(
        "reactor.agents.runner.run_langchain_agent_once",
        fake_run_langchain_agent_once,
    )

    result = await run_once(
        "hello",
        Settings(default_model_provider="openai", default_model="gpt-5-mini"),
        run_id="run_1",
        thread_id="thread_1",
        response_format="JSON",
        runtime="langchain_agent",
    )

    assert result.response_metadata == {
        "structured_output_status": "invalid",
        "structured_output_error_code": "INVALID_RESPONSE",
        "stop_reason": "structured_output_invalid",
    }
    assert result.as_response()["metadata"] == {
        "structured_output_status": "invalid",
        "structured_output_error_code": "INVALID_RESPONSE",
        "stop_reason": "structured_output_invalid",
    }


async def test_runner_passes_system_prompt_to_langchain_agent_runtime(
    monkeypatch: Any,
) -> None:
    captured: dict[str, object] = {}

    async def fake_run_langchain_agent_once(
        _message: str,
        _settings: Settings,
        **kwargs: object,
    ) -> object:
        captured.update(kwargs)
        return FakeLangChainAgentResult("native response")

    monkeypatch.setattr(
        "reactor.agents.runner.run_langchain_agent_once",
        fake_run_langchain_agent_once,
    )

    await run_once(
        "hello",
        Settings(default_model_provider="openai", default_model="gpt-5-mini"),
        run_id="run_1",
        thread_id="thread_1",
        system_prompt="Follow tenant policy.",
        runtime="langchain_agent",
    )

    assert captured["system_prompt"] == "Follow tenant policy."


async def test_runner_passes_structured_output_schema_to_langchain_agent_runtime(
    monkeypatch: Any,
) -> None:
    captured: dict[str, object] = {}

    class AnswerSchema(BaseModel):
        answer: str
        confidence: float

    async def fake_run_langchain_agent_once(
        _message: str,
        _settings: Settings,
        **kwargs: object,
    ) -> object:
        captured.update(kwargs)
        return FakeLangChainAgentResult("native response")

    monkeypatch.setattr(
        "reactor.agents.runner.run_langchain_agent_once",
        fake_run_langchain_agent_once,
    )

    await run_once(
        "hello",
        Settings(default_model_provider="openai", default_model="gpt-5-mini"),
        run_id="run_1",
        thread_id="thread_1",
        response_format="JSON",
        runtime="langchain_agent",
        structured_output_schema=AnswerSchema,
    )

    assert captured["structured_output_schema"] is AnswerSchema


async def test_runner_passes_checkpointer_to_langchain_agent_runtime(
    monkeypatch: Any,
) -> None:
    captured: dict[str, object] = {}
    checkpointer = object()

    async def fake_run_langchain_agent_once(
        _message: str,
        _settings: Settings,
        **kwargs: object,
    ) -> object:
        captured.update(kwargs)
        return FakeLangChainAgentResult("native response")

    monkeypatch.setattr(
        "reactor.agents.runner.run_langchain_agent_once",
        fake_run_langchain_agent_once,
    )

    await run_once(
        "hello",
        Settings(default_model_provider="openai", default_model="gpt-5-mini"),
        run_id="run_1",
        thread_id="thread_1",
        runtime="langchain_agent",
        checkpointer=checkpointer,
    )

    assert captured["checkpointer"] is checkpointer


async def test_runner_passes_graph_store_to_langchain_agent_runtime(
    monkeypatch: Any,
) -> None:
    captured: dict[str, object] = {}
    graph_store = InMemoryStore()

    async def fake_run_langchain_agent_once(
        _message: str,
        _settings: Settings,
        **kwargs: object,
    ) -> object:
        captured.update(kwargs)
        return FakeLangChainAgentResult("native response")

    monkeypatch.setattr(
        "reactor.agents.runner.run_langchain_agent_once",
        fake_run_langchain_agent_once,
    )

    await run_once(
        "hello",
        Settings(default_model_provider="openai", default_model="gpt-5-mini"),
        run_id="run_1",
        thread_id="thread_1",
        runtime="langchain_agent",
        graph_store=graph_store,
    )

    assert captured["graph_store"] is graph_store


async def test_runner_passes_middleware_policy_to_langchain_agent_runtime(
    monkeypatch: Any,
) -> None:
    captured: dict[str, object] = {}
    policy = LangChainMiddlewarePolicy(tool_call_run_limit=2)

    async def fake_run_langchain_agent_once(
        _message: str,
        _settings: Settings,
        **kwargs: object,
    ) -> object:
        captured.update(kwargs)
        return FakeLangChainAgentResult("native response")

    monkeypatch.setattr(
        "reactor.agents.runner.run_langchain_agent_once",
        fake_run_langchain_agent_once,
    )

    await run_once(
        "hello",
        Settings(default_model_provider="openai", default_model="gpt-5-mini"),
        run_id="run_1",
        thread_id="thread_1",
        runtime="langchain_agent",
        middleware_policy=policy,
    )

    assert captured["middleware_policy"] is policy


async def test_runner_passes_fallback_models_to_langchain_agent_runtime(
    monkeypatch: Any,
) -> None:
    captured: dict[str, object] = {}

    async def fake_run_langchain_agent_once(
        _message: str,
        _settings: Settings,
        **kwargs: object,
    ) -> object:
        captured.update(kwargs)
        return FakeLangChainAgentResult("native response")

    monkeypatch.setattr(
        "reactor.agents.runner.run_langchain_agent_once",
        fake_run_langchain_agent_once,
    )

    await run_once(
        "hello",
        Settings(default_model_provider="openai", default_model="gpt-5"),
        run_id="run_1",
        thread_id="thread_1",
        runtime="langchain_agent",
        fallback_models=["anthropic:claude-sonnet-5"],
    )

    assert captured["fallback_models"] == ["anthropic:claude-sonnet-5"]


def test_extract_response_text_returns_latest_ai_message() -> None:
    assert (
        extract_response_text(
            [
                AIMessage(content="old"),
                HumanMessage(content="hello"),
                AIMessage(content="new"),
            ]
        )
        == "new"
    )


class FakeLangChainAgent:
    def __init__(
        self,
        response: str,
        structured_response: object | None = None,
        *,
        interrupts: tuple[object, ...] = (),
    ) -> None:
        self.response = response
        self.structured_response = structured_response
        self.interrupts = interrupts
        self.calls: list[dict[str, object]] = []
        self.stream_calls: list[dict[str, object]] = []

    async def ainvoke(
        self,
        input: object,
        config: RunnableConfig | None = None,
        *,
        version: str = "v1",
    ) -> object:
        self.calls.append({"input": input, "config": config or {}, "version": version})
        typed_input: Mapping[str, object] = (
            cast(Mapping[str, object], input) if isinstance(input, Mapping) else {}
        )
        raw_messages: object = typed_input.get("messages", [])
        messages = list(cast(Sequence[object], raw_messages))
        messages.append(AIMessage(content=self.response))
        result: dict[str, object] = {"messages": messages}
        if self.structured_response is not None:
            result["structured_response"] = self.structured_response
        if self.interrupts:
            return GraphOutput(
                value=result,
                interrupts=tuple(Interrupt(value=value) for value in self.interrupts),
            )
        return result

    async def astream_events(
        self,
        input: dict[str, object],
        config: RunnableConfig | None = None,
        *,
        version: str,
    ):
        self.stream_calls.append({"input": input, "config": config or {}, "version": version})
        yield {
            "event": "on_chain_stream",
            "run_id": "trace_model",
            "metadata": {"langgraph_node": "model"},
            "data": {"chunk": {"response_text": self.response}},
        }


class ToolCallingFakeModel(GenericFakeChatModel):
    def bind_tools(
        self,
        tools: Sequence[object],
        *,
        tool_choice: object | None = None,
        **kwargs: Any,
    ) -> ToolCallingFakeModel:
        _ = tools, tool_choice, kwargs
        return self


class FakeLangChainAgentResult:
    def __init__(
        self,
        response: str,
        *,
        response_metadata: dict[str, object] | None = None,
    ) -> None:
        self.response = response
        self.token_usage = None
        self.response_metadata = response_metadata or {}


class HangingLangChainAgent:
    async def ainvoke(
        self,
        input: object,
        config: RunnableConfig | None = None,
        *,
        version: str = "v1",
    ) -> dict[str, object]:
        _ = input
        _ = config
        _ = version
        await asyncio.Event().wait()
        return {"messages": [AIMessage(content="unreachable")]}

    async def astream_events(
        self,
        input: object,
        config: RunnableConfig | None = None,
        *,
        version: str,
    ):
        _ = input, config, version
        await asyncio.Event().wait()
        yield {
            "event": "on_chain_stream",
            "run_id": "unreachable",
            "metadata": {"langgraph_node": "model"},
            "data": {"chunk": {"response_text": "unreachable"}},
        }


async def unused_tool_handler(_request: ToolExecutionRequest) -> ToolExecutionResult:
    raise AssertionError("fake LangChain agent should not execute tools")
