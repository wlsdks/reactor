from __future__ import annotations

from collections.abc import Mapping

from langgraph.types import Interrupt

from reactor.agents.runner import RunResult, run_once
from reactor.core.settings import Settings


async def test_run_once_returns_completed_response() -> None:
    result = await run_once("hello", Settings())

    assert result.status == "completed"
    assert result.run_id.startswith("run_")
    assert result.tenant_id == "local"
    assert result.user_id == "anonymous"
    assert "hello" in result.response


async def test_run_once_preserves_graph_response_metadata() -> None:
    result = await run_once(
        "send the webhook",
        Settings(),
        run_id="run_1",
        graph=MetadataGraph(),
        tenant_id="tenant_1",
        user_id="U1",
        thread_id="thread_1",
    )

    assert result.response_metadata["approval_status"] == "pending"
    assert result.response_metadata["approval_request"] == {
        "run_id": "run_1",
        "tenant_id": "tenant_1",
        "tool_id": "builtin:send_webhook",
    }


async def test_run_once_reports_native_langgraph_interrupt_without_public_tool_input() -> None:
    class InterruptingGraph:
        async def ainvoke(
            self,
            input: object,
            config: object | None = None,
        ) -> dict[str, object]:
            _ = input, config
            return {
                "__interrupt__": (
                    Interrupt(
                        value={
                            "approval_status": "pending",
                            "approval_request": {
                                "tool_id": "Webhook:send",
                                "input_payload": {"authorization": "private-credential"},
                            },
                        },
                        id="interrupt_1",
                    ),
                )
            }

    result = await run_once(
        "send the webhook",
        Settings(),
        run_id="run_1",
        graph=InterruptingGraph(),
        tenant_id="tenant_1",
        user_id="user_1",
        thread_id="thread_1",
    )

    assert result.status == "interrupted"
    assert result.response == "Agent run paused for approval."
    assert result.response_metadata == {
        "approval_status": "pending",
        "stop_reason": "langgraph_interrupt",
    }
    assert len(result.interrupt_actions) == 1
    assert result.interrupt_actions[0].tool_name == "Webhook:send"
    assert result.interrupt_actions[0].arguments == {"authorization": "private-credential"}
    assert "private-credential" not in repr(result)
    assert "private-credential" not in repr(result.as_response())


def test_run_result_response_exposes_only_public_metadata() -> None:
    result = RunResult(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        status="completed",
        response="done",
        provider="openai",
        model="gpt-5-mini",
        response_metadata={
            "stop_reason": "completed",
            "state_schema_version": "reactor.agent.state.v1",
            "private_tool_payload": {"api_key": "sk-test-secret"},
            "approval_request": {
                "run_id": "run_1",
                "tenant_id": "tenant_1",
                "tool_id": "builtin:send_webhook",
                "tool_risk_level": "external_side_effect",
                "tool_timeout_ms": 15000,
                "requested_by": "user_1",
                "input_payload": {"api_key": "sk-test-secret"},
                "idempotency_key": "tool:run_1:builtin:send_webhook",
            },
        },
    )

    response = result.as_response()

    assert response["metadata"] == {
        "stop_reason": "completed",
        "state_schema_version": "reactor.agent.state.v1",
        "approval_request": {
            "run_id": "run_1",
            "tenant_id": "tenant_1",
            "tool_id": "builtin:send_webhook",
            "tool_risk_level": "external_side_effect",
            "tool_timeout_ms": 15000,
            "requested_by": "user_1",
            "idempotency_key": "tool:run_1:builtin:send_webhook",
        },
    }


def test_run_result_response_sanitizes_nested_public_metadata() -> None:
    result = RunResult(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        status="completed",
        response="done",
        provider="openai",
        model="gpt-5-mini",
        response_metadata={
            "tool_profile_budget": {
                "maxTools": 1,
                "dropped_tools": [
                    {
                        "tool": "builtin:send_webhook",
                        "reason": "max_tools_exceeded",
                        "input_payload": {"api_key": "sk-test-secret"},
                    }
                ],
            },
            "hook_failures": [
                {
                    "hook": "audit",
                    "error_type": "RuntimeError",
                    "raw_output": "sk-test-secret",
                }
            ],
        },
    )

    response = result.as_response()

    assert response["metadata"] == {
        "tool_profile_budget": {
            "maxTools": 1,
            "dropped_tools": [
                {
                    "tool": "builtin:send_webhook",
                    "reason": "max_tools_exceeded",
                }
            ],
        },
        "hook_failures": [
            {
                "hook": "audit",
                "error_type": "RuntimeError",
            }
        ],
    }


def test_run_result_response_preserves_public_langchain_middleware_policy_facet() -> None:
    result = RunResult(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        status="completed",
        response="done",
        provider="openai",
        model="gpt-5-mini",
        response_metadata={
            "langchainMiddlewarePolicy": {
                "status": "applied",
                "source": "tenant_runtime_setting",
                "settingKey": "langchain.middleware_policy",
                "tenantId": "tenant_1",
                "policy": {
                    "modelCallRunLimit": 4,
                    "toolCallRunLimit": 3,
                    "modelRetryMaxRetries": 1,
                    "toolRetryMaxRetries": 1,
                    "piiRules": [
                        {
                            "type": "email",
                            "strategy": "redact",
                            "applyToInput": True,
                            "applyToOutput": True,
                            "applyToToolResults": True,
                            "applyToStreamOutput": True,
                        }
                    ],
                },
            }
        },
    )

    assert result.as_response()["metadata"] == {
        "langchainMiddlewarePolicy": {
            "status": "applied",
            "source": "tenant_runtime_setting",
            "settingKey": "langchain.middleware_policy",
            "tenantId": "tenant_1",
            "policy": {
                "modelCallRunLimit": 4,
                "toolCallRunLimit": 3,
                "modelRetryMaxRetries": 1,
                "toolRetryMaxRetries": 1,
                "piiRules": [
                    {
                        "type": "email",
                        "strategy": "redact",
                        "applyToInput": True,
                        "applyToOutput": True,
                        "applyToToolResults": True,
                        "applyToStreamOutput": True,
                    }
                ],
            },
        }
    }


def test_run_result_response_preserves_public_structured_output_and_tool_budget_facets() -> None:
    result = RunResult(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        status="completed",
        response="done",
        provider="openai",
        model="gpt-5-mini",
        response_metadata={
            "structuredOutput": {
                "status": "applied",
                "strategy": "schema_passthrough",
                "schemaSource": "metadata.responseSchema",
                "raw_payload": {"api_key": "sk-test-secret"},
            },
            "resolvedToolProfileBudget": {
                "source": "tenant_runtime_setting",
                "settingKey": "tools.profile_budget",
                "tenantId": "tenant_1",
                "budget": {
                    "maxTools": 2,
                    "allowedRiskLevels": ["read"],
                    "allowedTools": ["Rag:hybrid_search"],
                    "deniedTools": ["Slack:post_message"],
                    "input_payload": {"api_key": "sk-test-secret"},
                },
                "configuredToolCount": 4,
                "activeToolCount": 2,
                "droppedToolCount": 2,
            },
        },
    )

    assert result.as_response()["metadata"] == {
        "structuredOutput": {
            "status": "applied",
            "strategy": "schema_passthrough",
            "schemaSource": "metadata.responseSchema",
        },
        "resolvedToolProfileBudget": {
            "source": "tenant_runtime_setting",
            "settingKey": "tools.profile_budget",
            "tenantId": "tenant_1",
            "budget": {
                "maxTools": 2,
                "allowedRiskLevels": ["read"],
                "allowedTools": ["Rag:hybrid_search"],
                "deniedTools": ["Slack:post_message"],
            },
            "configuredToolCount": 4,
            "activeToolCount": 2,
            "droppedToolCount": 2,
        },
    }


def test_run_result_response_preserves_public_context_and_checkpoint_facets() -> None:
    result = RunResult(
        run_id="run_1",
        tenant_id="tenant_1",
        user_id="user_1",
        thread_id="thread_1",
        checkpoint_ns="reactor",
        status="completed",
        response="done",
        provider="openai",
        model="gpt-5-mini",
        response_metadata={
            "contextManifest": {
                "sections": [{"name": "rag", "content_checksum": "sha256:abc"}],
                "ragGroundingPolicy": {"citationCount": 1},
                "acl": {"api_key": "sk-test-secret"},
                "raw_payload": {"api_key": "sk-test-secret"},
            },
            "checkpointProvenance": {
                "forkedFromRunId": "run_source",
                "forkedFromThreadId": "thread_source",
                "forkedFromCheckpointNs": "reactor",
                "forkedFromCheckpointId": "ckpt_1",
                "forkTargetThreadId": "thread_target",
                "forkTargetCheckpointNs": "reactor",
                "payload": {"api_key": "sk-test-secret"},
            },
        },
    )

    assert result.as_response()["metadata"] == {
        "contextManifest": {
            "sections": [{"name": "rag", "content_checksum": "sha256:abc"}],
            "ragGroundingPolicy": {"citationCount": 1},
        },
        "checkpointProvenance": {
            "forkedFromRunId": "run_source",
            "forkedFromThreadId": "thread_source",
            "forkedFromCheckpointNs": "reactor",
            "forkedFromCheckpointId": "ckpt_1",
            "forkTargetThreadId": "thread_target",
            "forkTargetCheckpointNs": "reactor",
        },
    }


class MetadataGraph:
    async def ainvoke(
        self,
        _state: Mapping[str, object],
        *,
        config: Mapping[str, object],
    ) -> dict[str, object]:
        del config
        return {
            "response_text": "Approval required.",
            "response_metadata": {
                "approval_status": "pending",
                "approval_request": {
                    "run_id": "run_1",
                    "tenant_id": "tenant_1",
                    "tool_id": "builtin:send_webhook",
                },
            },
        }
