from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from reactor.persistence.tool_invocation_store import ToolInvocationClaim, ToolInvocationRecord
from reactor.tools.catalog import ToolSpec
from reactor.tools.execution import (
    ToolExecutionOutcome,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolPolicy,
    ToolResultCache,
    admit_tool_execution,
    execute_tools_parallel,
    run_tool_with_timeout,
    tool_invocation_record_from_outcome,
)
from reactor.tools.handlers import RoutedToolHandler
from reactor.tools.idempotency import build_tool_idempotency_key


def test_read_tool_is_admitted_without_approval() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="builtin",
        name="search_docs",
        description="Search approved docs.",
        risk_level="read",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    request = ToolExecutionRequest(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        tool=spec,
        input_payload={"query": "hello"},
    )

    decision = admit_tool_execution(request, ToolPolicy())

    assert decision.allowed is True
    assert decision.requires_approval is False
    assert decision.idempotency_key.startswith("tool:tenant_1:run_1:builtin:search_docs:")


def test_write_tool_requires_approval_without_policy_override() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="builtin",
        name="send_webhook",
        description="Send a webhook.",
        risk_level="external_side_effect",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    request = ToolExecutionRequest(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        tool=spec,
        input_payload={"url": "https://example.com"},
    )

    decision = admit_tool_execution(request, ToolPolicy())

    assert decision.allowed is False
    assert decision.requires_approval is True
    assert decision.reason == "approval_required"


def test_write_tool_can_be_admitted_with_explicit_policy_and_approval() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="builtin",
        name="send_webhook",
        description="Send a webhook.",
        risk_level="write",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    request = ToolExecutionRequest(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        tool=spec,
        input_payload={"url": "https://example.com"},
        approval_id="approval_1",
    )

    decision = admit_tool_execution(
        request,
        ToolPolicy(allow_write_without_approval=False, approved_approval_ids={"approval_1"}),
    )

    assert decision.allowed is True
    assert decision.approval_id == "approval_1"


def test_shell_tool_requires_sandbox_even_when_read_only() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="Shell",
        name="exec",
        description="Run shell command.",
        risk_level="read",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        requires_approval=False,
    )
    request = ToolExecutionRequest(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        tool=spec,
        input_payload={"cmd": "pwd"},
    )

    decision = admit_tool_execution(request, ToolPolicy())

    assert decision.allowed is False
    assert decision.requires_approval is False
    assert decision.reason == "sandbox_required"


def test_file_write_tool_requires_sandbox_even_after_approval() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="FileSystem",
        name="write_file",
        description="Write file.",
        risk_level="write",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    request = ToolExecutionRequest(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        tool=spec,
        input_payload={"path": "workspace/out.txt"},
        approval_id="approval_1",
    )

    decision = admit_tool_execution(
        request,
        ToolPolicy(approved_approval_ids={"approval_1"}),
    )

    assert decision.allowed is False
    assert decision.requires_approval is False
    assert decision.reason == "sandbox_required"


def test_sandboxed_write_tool_still_requires_approval() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="FileSystem",
        name="write_file",
        description="Write file.",
        risk_level="write",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    request = ToolExecutionRequest(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        tool=spec,
        input_payload={"path": "workspace/out.txt"},
    )

    decision = admit_tool_execution(
        request,
        ToolPolicy(sandboxed_tool_names={"FileSystem:write_file"}),
    )

    assert decision.allowed is False
    assert decision.requires_approval is True
    assert decision.reason == "approval_required"


def test_tool_idempotency_key_is_stable_for_equivalent_payload_ordering() -> None:
    left = build_tool_idempotency_key(
        tenant_id="tenant_1",
        run_id="run_1",
        qualified_name="builtin:send_webhook",
        input_payload={"b": 2, "a": 1},
    )
    right = build_tool_idempotency_key(
        tenant_id="tenant_1",
        run_id="run_1",
        qualified_name="builtin:send_webhook",
        input_payload={"a": 1, "b": 2},
    )

    assert left == right


def test_tool_idempotency_key_includes_trusted_user_groups() -> None:
    without_group = build_tool_idempotency_key(
        tenant_id="tenant_1",
        run_id="run_1",
        qualified_name="Rag:hybrid_search",
        input_payload={"query": "policy"},
    )
    with_group = build_tool_idempotency_key(
        tenant_id="tenant_1",
        run_id="run_1",
        qualified_name="Rag:hybrid_search",
        input_payload={"query": "policy"},
        trusted_user_groups=("finance",),
    )

    assert without_group != with_group


def test_tool_idempotency_key_distinguishes_langchain_tool_calls() -> None:
    first = build_tool_idempotency_key(
        tenant_id="tenant_1",
        run_id="run_1",
        qualified_name="Rag:hybrid_search",
        input_payload={"query": "same"},
        tool_call_id="call_1",
    )
    replay = build_tool_idempotency_key(
        tenant_id="tenant_1",
        run_id="run_1",
        qualified_name="Rag:hybrid_search",
        input_payload={"query": "same"},
        tool_call_id="call_1",
    )
    distinct = build_tool_idempotency_key(
        tenant_id="tenant_1",
        run_id="run_1",
        qualified_name="Rag:hybrid_search",
        input_payload={"query": "same"},
        tool_call_id="call_2",
    )

    assert first == replay
    assert first != distinct


def test_tool_execution_result_returns_structured_error_payload() -> None:
    result = ToolExecutionResult.error("timeout", "tool timed out")

    assert result.status == "failed"
    assert result.payload == {"error": {"code": "timeout", "message": "tool timed out"}}


def test_tool_result_cache_returns_previous_result_for_same_idempotency_key() -> None:
    cache = ToolResultCache()
    request = ToolExecutionRequest(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        tool=ToolSpec(
            tenant_id="tenant_1",
            namespace="builtin",
            name="send_webhook",
            description="Send webhook.",
            risk_level="write",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        ),
        input_payload={"url": "https://example.com"},
        approval_id="approval_1",
    )
    result = ToolExecutionResult.success({"ok": True})

    cache.store(request, result)

    assert cache.get(request) == result


def test_tool_execution_outcome_builds_audit_record_with_policy_context() -> None:
    request = ToolExecutionRequest(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        tool=ToolSpec(
            tenant_id="tenant_1",
            namespace="builtin",
            name="send_webhook",
            description="Send webhook.",
            risk_level="write",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        ),
        input_payload={"url": "https://example.com", "body": {"b": 2, "a": 1}},
        approval_id="approval_1",
    )
    outcome = ToolExecutionOutcome(
        request=request,
        result=ToolExecutionResult.success({"ok": True, "message": "sent"}),
        cache_status="miss",
        executed=True,
    )
    started_at = datetime(2026, 6, 30, 1, 2, 3, tzinfo=UTC)
    completed_at = datetime(2026, 6, 30, 1, 2, 4, tzinfo=UTC)

    record = tool_invocation_record_from_outcome(
        outcome,
        invocation_id="tool_invocation_1",
        started_at=started_at,
        completed_at=completed_at,
    )

    assert record.id == "tool_invocation_1"
    assert record.tenant_id == "tenant_1"
    assert record.run_id == "run_1"
    assert record.tool_id == "builtin:send_webhook"
    assert record.approval_id == "approval_1"
    assert record.status == "succeeded"
    assert record.idempotency_key == request.idempotency_key
    assert record.request_checksum.startswith("sha256:")
    assert record.result_checksum and record.result_checksum.startswith("sha256:")
    assert record.input_payload == {
        "tool": "builtin:send_webhook",
        "riskLevel": "write",
        "approvalRequired": True,
        "cacheStatus": "miss",
        "executed": True,
        "payload": {"url": "https://example.com", "body": {"b": 2, "a": 1}},
    }
    assert record.output_payload == {"ok": True, "message": "sent"}
    assert record.error_payload is None
    assert record.started_at == started_at
    assert record.completed_at == completed_at


async def test_run_tool_with_timeout_returns_structured_timeout_error() -> None:
    request = ToolExecutionRequest(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        tool=ToolSpec(
            tenant_id="tenant_1",
            namespace="builtin",
            name="slow_tool",
            description="Slow tool.",
            risk_level="read",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            timeout_ms=1,
        ),
        input_payload={},
    )

    async def slow_handler() -> ToolExecutionResult:
        await asyncio.sleep(0.05)
        return ToolExecutionResult.success({"ok": True})

    result = await run_tool_with_timeout(request, slow_handler)

    assert result.status == "failed"
    assert result.payload == {
        "error": {
            "code": "timeout",
            "message": "tool timed out after 1ms",
        }
    }


async def test_execute_tools_parallel_runs_requests_concurrently_and_preserves_order() -> None:
    active = 0
    max_active = 0
    requests = [
        ToolExecutionRequest(
            run_id="run_1",
            tenant_id="tenant_1",
            user_id="user_1",
            tool=ToolSpec(
                tenant_id="tenant_1",
                namespace="builtin",
                name=f"read_{index}",
                description="Read tool.",
                risk_level="read",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
            input_payload={"index": index},
        )
        for index in (1, 2)
    ]

    async def handler(request: ToolExecutionRequest) -> ToolExecutionResult:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return ToolExecutionResult.success({"tool": request.tool.name})

    outcomes = await execute_tools_parallel(requests, handler)

    assert max_active == 2
    assert [outcome.request.tool.name for outcome in outcomes] == ["read_1", "read_2"]
    assert [outcome.result.payload for outcome in outcomes] == [
        {"tool": "read_1"},
        {"tool": "read_2"},
    ]


async def test_idempotency_claim_failure_logs_safely_and_skips_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ClaimFailingStore:
        async def claim(self, record: ToolInvocationRecord) -> ToolInvocationClaim:
            _ = record
            raise RuntimeError("claim unavailable: private-storage-detail")

        async def save(self, record: ToolInvocationRecord) -> ToolInvocationRecord:
            raise AssertionError(f"unclaimed invocation must not be saved: {record.id}")

    warning_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def record_warning(*args: object, **kwargs: object) -> None:
        warning_calls.append((args, kwargs))

    monkeypatch.setattr("reactor.tools.execution.logger.warning", record_warning)
    request = ToolExecutionRequest(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        tool=ToolSpec(
            tenant_id="tenant_1",
            namespace="Webhook",
            name="send",
            description="Send a webhook.",
            risk_level="external_side_effect",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        ),
        input_payload={"url": "https://example.com"},
        approval_id="approval_1",
    )
    calls = 0

    async def handler(_request: ToolExecutionRequest) -> ToolExecutionResult:
        nonlocal calls
        calls += 1
        return ToolExecutionResult.success({"delivered": True})

    outcome = (
        await execute_tools_parallel(
            [request],
            handler,
            idempotency_store=ClaimFailingStore(),
        )
    )[0]

    assert calls == 0
    assert outcome.executed is False
    assert outcome.result.status == "failed"
    assert outcome.result.payload["error"]["code"] == "idempotency_unavailable"
    assert warning_calls == [
        (
            ("tool invocation idempotency claim failed",),
            {
                "extra": {
                    "tenant_id": "tenant_1",
                    "run_id": "run_1",
                    "tool_id": "Webhook:send",
                }
            },
        )
    ]
    assert "private-storage-detail" not in repr(warning_calls)


async def test_external_side_effect_requires_reconciliation_when_completion_audit_fails() -> None:
    class CompletionFailingStore:
        def __init__(self) -> None:
            self.claimed_record: ToolInvocationRecord | None = None

        async def claim(self, record: ToolInvocationRecord) -> ToolInvocationClaim:
            self.claimed_record = record
            return ToolInvocationClaim(claimed=True, record=record)

        async def save(self, record: ToolInvocationRecord) -> ToolInvocationRecord:
            _ = record
            raise RuntimeError("audit storage unavailable: private-storage-detail")

    request = ToolExecutionRequest(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        tool=ToolSpec(
            tenant_id="tenant_1",
            namespace="Webhook",
            name="send",
            description="Send a webhook.",
            risk_level="external_side_effect",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        ),
        input_payload={"url": "https://example.com"},
        approval_id="approval_1",
    )
    calls = 0

    async def handler(_request: ToolExecutionRequest) -> ToolExecutionResult:
        nonlocal calls
        calls += 1
        return ToolExecutionResult.success({"delivered": True})

    cache = ToolResultCache()
    store = CompletionFailingStore()

    outcome = (
        await execute_tools_parallel(
            [request],
            handler,
            cache=cache,
            idempotency_store=store,
        )
    )[0]

    assert calls == 1
    assert outcome.executed is True
    assert outcome.result.status == "requires_reconciliation"
    assert outcome.cache_status == "completion_save_error"
    assert cache.get(request) is None
    assert store.claimed_record is not None
    assert store.claimed_record.status == "started"
    assert "private-storage-detail" not in repr(outcome)


async def test_routed_tool_handler_fails_closed_for_unregistered_slack_tools() -> None:
    async def fallback(request: ToolExecutionRequest) -> ToolExecutionResult:
        return ToolExecutionResult.success({"fallback": request.tool.qualified_name})

    handler = RoutedToolHandler(routes={}, fallback=fallback)
    request = ToolExecutionRequest(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        tool=ToolSpec(
            tenant_id="tenant_1",
            namespace="Slack",
            name="send_message",
            description="Send a Slack message.",
            risk_level="external_side_effect",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        ),
        input_payload={"channel": "C1", "text": "hello"},
    )

    result = await handler(request)

    assert result.status == "failed"
    assert result.payload == {
        "error": {
            "code": "tool_not_configured",
            "message": "tool handler is not configured for Slack:send_message",
        }
    }


async def test_routed_tool_handler_keeps_fallback_for_non_reserved_tools() -> None:
    async def fallback(request: ToolExecutionRequest) -> ToolExecutionResult:
        return ToolExecutionResult.success({"fallback": request.tool.qualified_name})

    handler = RoutedToolHandler(routes={}, fallback=fallback)
    request = ToolExecutionRequest(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        tool=ToolSpec(
            tenant_id="tenant_1",
            namespace="Other",
            name="debug",
            description="Debug helper.",
            risk_level="read",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        ),
        input_payload={},
    )

    result = await handler(request)

    assert result == ToolExecutionResult.success({"fallback": "Other:debug"})


def test_disabled_tool_is_denied() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="builtin",
        name="search_docs",
        description="Search docs.",
        risk_level="read",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        enabled=False,
    )
    request = ToolExecutionRequest(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        tool=spec,
        input_payload={},
    )

    with pytest.raises(ValueError, match="tool is disabled"):
        request.validate()
