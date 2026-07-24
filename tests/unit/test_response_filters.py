from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import HumanMessage

from reactor.agents.graph import build_reactor_graph
from reactor.agents.state import ReactorState
from reactor.response.boundary import (
    OutputBoundaryEnforcer,
    OutputBoundarySettings,
    OutputMinViolationMode,
)
from reactor.response.filters import (
    InternalBrandMaskResponseFilter,
    MaxLengthResponseFilter,
    ResponseFilter,
    ResponseFilterChain,
    ResponseFilterContext,
    SlackUserIdMaskResponseFilter,
)


async def test_max_length_response_filter_truncates_with_notice() -> None:
    context = ResponseFilterContext(
        tenant_id="tenant_1",
        user_id="user_1",
        tools_used=[],
        duration_ms=100,
    )

    result = await MaxLengthResponseFilter(max_length=10).filter(
        "This is a long response",
        context,
    )

    assert result.startswith("This is a ")
    assert "[Response truncated]" in result


async def test_response_filter_chain_orders_filters_and_fails_open() -> None:
    context = ResponseFilterContext(
        tenant_id="tenant_1",
        user_id="user_1",
        tools_used=[],
        duration_ms=100,
    )
    chain = ResponseFilterChain(
        [
            AppendFilter(order=50, suffix="!"),
            FailingFilter(order=20),
            AppendFilter(order=10, suffix="?"),
        ]
    )

    result = await chain.apply("ok", context)

    assert result == "ok?!"


async def test_slack_user_id_mask_filter_mentions_raw_ids_without_double_wrapping() -> None:
    context = ResponseFilterContext(
        tenant_id="tenant_1",
        user_id="user_1",
        tools_used=[],
        duration_ms=100,
    )
    response_filter = SlackUserIdMaskResponseFilter()

    assert await response_filter.filter("Slack ID는 U0123456789입니다.", context) == (
        "Slack ID는 <@U0123456789>입니다."
    )
    assert await response_filter.filter("Slack ID: `U0123456789`", context) == (
        "Slack ID: <@U0123456789>"
    )
    assert await response_filter.filter("<@U0123456789>님께 문의하세요.", context) == (
        "<@U0123456789>님께 문의하세요."
    )
    assert response_filter.order == 85


async def test_internal_brand_mask_filter_removes_legacy_stack_disclosure() -> None:
    context = ResponseFilterContext(
        tenant_id="tenant_1",
        user_id="user_1",
        tools_used=[],
        duration_ms=100,
    )
    response_filter = InternalBrandMaskResponseFilter()

    assert "Reactor(" not in await response_filter.filter("저는 Reactor(Reactor)입니다.", context)
    stack_result = await response_filter.filter(
        "**Kotlin과 Spring Boot** 기반 서비스이며 **Spring AI 기반의** 어시스턴트입니다.",
        context,
    )
    assert "Kotlin" not in stack_result
    assert "Spring Boot" not in stack_result
    assert "Spring AI" not in stack_result
    assert "서비스" in stack_result
    jvm_result = await response_filter.filter(
        "Reactor는 **JVM/Gradle 기반의** agent runtime입니다.",
        context,
    )
    assert "JVM" not in jvm_result
    assert "Gradle" not in jvm_result
    assert "agent runtime" in jvm_result
    assert "Kotlin" in await response_filter.filter(
        "Kotlin은 JVM 기반 프로그래밍 언어입니다.",
        context,
    )
    assert response_filter.order == 86


async def test_internal_brand_mask_filter_removes_company_org_disclosure() -> None:
    context = ResponseFilterContext(
        tenant_id="tenant_1",
        user_id="user_1",
        tools_used=[],
        duration_ms=100,
    )
    response_filter = InternalBrandMaskResponseFilter()

    result = await response_filter.filter(
        "This agent is deployed from LegacyOrg/reactor for Example Corp internal users.",
        context,
    )

    assert "Legacy" not in result
    assert "LegacyOrg" not in result
    assert "internal users" not in result
    assert "Reactor" in result


async def test_graph_applies_response_filter_chain_after_output_guard() -> None:
    graph = build_reactor_graph(
        response_filter_chain=ResponseFilterChain([MaxLengthResponseFilter(max_length=30)])
    )

    result = await graph.ainvoke(
        ReactorState(
            run_id="run_test",
            tenant_id="tenant_1",
            user_id="user_1",
            messages=[
                HumanMessage(content="Please produce a deliberately long answer for truncation")
            ],
            tool_call_count=0,
        )
    )

    assert "[Response truncated]" in result["response_text"]
    assert result["response_metadata"]["response_filter_status"] == "modified"


async def test_graph_applies_internal_brand_filter_to_model_output() -> None:
    graph = build_reactor_graph(
        response_filter_chain=ResponseFilterChain([InternalBrandMaskResponseFilter()])
    )

    result = await graph.ainvoke(
        ReactorState(
            run_id="run_test",
            tenant_id="tenant_1",
            user_id="user_1",
            messages=[
                HumanMessage(
                    content=(
                        "Say exactly: This agent is deployed from LegacyOrg/reactor "
                        "for Example Corp internal users."
                    )
                )
            ],
            tool_call_count=0,
        )
    )

    assert "Legacy" not in result["response_text"]
    assert "internal users" not in result["response_text"]
    assert result["response_metadata"]["response_filter_status"] == "modified"


async def test_graph_applies_output_boundary_after_response_filters() -> None:
    graph = build_reactor_graph(
        response_filter_chain=ResponseFilterChain([AppendFilter(order=10, suffix=" tail")]),
        output_boundary_enforcer=OutputBoundaryEnforcer(
            settings=OutputBoundarySettings(output_max_chars=40)
        ),
    )

    result = await graph.ainvoke(
        ReactorState(
            run_id="run_test",
            tenant_id="tenant_1",
            user_id="user_1",
            messages=[HumanMessage(content="Produce a long answer for boundary enforcement")],
            tool_call_count=0,
        )
    )

    assert result["response_text"].endswith("[Response truncated]")
    assert " tail" not in result["response_text"]
    assert result["response_metadata"]["output_boundary_status"] == "modified"


async def test_graph_blocks_response_text_when_output_boundary_fails() -> None:
    graph = build_reactor_graph(
        output_boundary_enforcer=OutputBoundaryEnforcer(
            settings=OutputBoundarySettings(
                output_min_chars=500,
                output_min_violation_mode=OutputMinViolationMode.FAIL,
            )
        ),
    )

    result = await graph.ainvoke(
        ReactorState(
            run_id="run_test",
            tenant_id="tenant_1",
            user_id="user_1",
            messages=[HumanMessage(content="short answer")],
            tool_call_count=0,
        )
    )

    assert result["response_text"] == "Response blocked by output boundary policy."
    assert result["response_metadata"]["output_boundary_status"] == "failed"
    assert result["response_metadata"]["stop_reason"] == "output_boundary_failed"
    assert "Reactor Python/LangGraph runtime is ready" not in result["response_text"]


async def test_graph_retries_once_when_output_boundary_requires_longer_response() -> None:
    graph = build_reactor_graph(
        output_boundary_enforcer=OutputBoundaryEnforcer(
            settings=OutputBoundarySettings(
                output_min_chars=120,
                output_min_violation_mode=OutputMinViolationMode.RETRY_ONCE,
            )
        ),
    )

    result = await graph.ainvoke(
        ReactorState(
            run_id="run_test",
            tenant_id="tenant_1",
            user_id="user_1",
            messages=[HumanMessage(content="brief")],
            tool_call_count=0,
        )
    )

    assert len(result["response_text"]) >= 120
    assert "Additional detail" in result["response_text"]
    assert result["response_metadata"]["output_boundary_status"] == "modified"
    assert result["response_metadata"]["output_boundary_retry"] == "used"


@dataclass(frozen=True)
class AppendFilter:
    order: int
    suffix: str

    async def filter(self, content: str, context: ResponseFilterContext) -> str:
        del context
        return f"{content}{self.suffix}"


@dataclass(frozen=True)
class FailingFilter:
    order: int

    async def filter(self, content: str, context: ResponseFilterContext) -> str:
        del content, context
        raise RuntimeError("filter failed")


def test_custom_filter_fixtures_satisfy_protocol() -> None:
    assert isinstance(AppendFilter(order=1, suffix="!"), ResponseFilter)
