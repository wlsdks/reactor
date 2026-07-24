from __future__ import annotations

from typing import cast

import pytest
from langgraph.types import Command

from reactor.agents.graph_boundary import JsonSafeReactorGraph, normalize_reactor_graph_input
from reactor.agents.interrupts import approval_resume_from_raw
from reactor.agents.tool_state import (
    PENDING_TOOL_REQUEST_SCHEMA_VERSION,
    pending_tool_request_from_raw,
    pending_tool_request_to_state_payload,
)
from reactor.tools.catalog import ToolSpec


def test_pending_tool_request_round_trip_preserves_catalog_identity() -> None:
    request = {
        "tool": tool_spec(catalog_id="tool_catalog_1"),
        "input_payload": {"items": ("first", "second")},
    }

    payload = pending_tool_request_to_state_payload(request)
    restored = pending_tool_request_from_raw(payload)

    assert payload["schema_version"] == PENDING_TOOL_REQUEST_SCHEMA_VERSION
    assert payload["input_payload"] == {"items": ["first", "second"]}
    assert restored.tool.catalog_id == "tool_catalog_1"
    assert restored.input_payload == {"items": ["first", "second"]}


def test_pending_tool_request_rejects_unknown_schema_version() -> None:
    with pytest.raises(ValueError, match="unsupported pending_tool_request schema_version"):
        pending_tool_request_from_raw(
            {
                "schema_version": "reactor.pending_tool_request.v2",
                "tool": tool_spec(),
                "input_payload": {},
            }
        )


def test_pending_tool_request_rejects_non_json_checkpoint_values() -> None:
    with pytest.raises(ValueError, match="unsupported value type: object"):
        pending_tool_request_to_state_payload(
            {
                "tool": tool_spec(),
                "input_payload": {"unsafe": object()},
            }
        )


def test_graph_input_boundary_normalizes_pending_tool_request_list() -> None:
    normalized = normalize_reactor_graph_input(
        {
            "pending_tool_requests": [
                {
                    "tool": tool_spec(),
                    "input_payload": {"attempt": 1},
                }
            ]
        }
    )

    assert isinstance(normalized, dict)
    typed_normalized = cast(dict[str, object], normalized)
    pending = typed_normalized["pending_tool_requests"]
    assert isinstance(pending, list)
    typed_pending = cast(list[dict[str, object]], pending)
    assert typed_pending[0]["schema_version"] == PENDING_TOOL_REQUEST_SCHEMA_VERSION
    assert isinstance(typed_pending[0]["tool"], dict)


def test_graph_input_boundary_versions_approval_resume_command() -> None:
    normalized = normalize_reactor_graph_input(
        Command(
            resume={
                "approval_id": "approval_1",
                "approved": True,
                "decided_by": "admin_1",
                "reason": None,
            }
        )
    )

    assert isinstance(normalized, Command)
    assert normalized.resume == {
        "schema_version": "reactor.approval_resume.v1",
        "approval_id": "approval_1",
        "approved": True,
        "decided_by": "admin_1",
        "reason": None,
    }


def test_graph_input_boundary_rejects_resume_command_control_updates() -> None:
    with pytest.raises(ValueError, match="may only contain resume"):
        normalize_reactor_graph_input(
            Command(
                update={"approval_status": "approved"},
                resume={
                    "approval_id": "approval_1",
                    "approved": True,
                    "decided_by": "admin_1",
                    "reason": None,
                },
            )
        )


def test_graph_input_boundary_rejects_unknown_state_schema_version() -> None:
    with pytest.raises(ValueError, match="unsupported reactor state_schema_version"):
        normalize_reactor_graph_input(
            {
                "state_schema_version": "reactor.agent.state.v2",
                "messages": [],
            }
        )


def test_graph_boundary_rejects_synchronous_invoke() -> None:
    graph = JsonSafeReactorGraph(object())

    with pytest.raises(RuntimeError, match="use ainvoke"):
        graph.invoke({"messages": []})


def test_graph_boundary_rejects_synchronous_stream() -> None:
    graph = JsonSafeReactorGraph(object())

    with pytest.raises(RuntimeError, match="use astream"):
        graph.stream({"messages": []})


def test_approval_resume_rejects_unknown_schema_and_fields() -> None:
    with pytest.raises(ValueError, match="unsupported approval_resume schema_version"):
        approval_resume_from_raw(
            {
                "schema_version": "reactor.approval_resume.v2",
                "approval_id": "approval_1",
                "approved": True,
                "decided_by": "admin_1",
                "reason": None,
            }
        )
    with pytest.raises(ValueError, match="contains unsupported fields"):
        approval_resume_from_raw(
            {
                "approval_id": "approval_1",
                "approved": True,
                "decided_by": "admin_1",
                "reason": None,
                "update": {"approval_status": "approved"},
            }
        )


def tool_spec(*, catalog_id: str | None = None) -> ToolSpec:
    return ToolSpec(
        tenant_id="tenant_1",
        namespace="builtin",
        name="send_webhook",
        description="Send a webhook.",
        risk_level="external_side_effect",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        catalog_id=catalog_id,
    )
