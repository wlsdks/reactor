from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast

import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.memory import InMemorySaver

from reactor import __version__
from reactor.a2a.access_policy import A2AAccessPolicyDraft, A2AAccessPolicyView
from reactor.a2a.peers import A2APeerDraft, A2APeerRecord
from reactor.a2a.tasks import A2ATaskDraft, A2ATaskRecord
from reactor.agents.runtime_config import (
    DEFAULT_LANGGRAPH_RECURSION_LIMIT,
    langgraph_checkpoint_thread_id,
    langgraph_durable_config,
)
from reactor.api.app import create_app
from reactor.api.routers import health as health_router
from reactor.api.routers.runs import FORK_PROVENANCE_METADATA_KEYS
from reactor.core.settings import Settings
from reactor.persistence.approval_store import ApprovalRecord
from reactor.persistence.run_store import (
    RunCompletionEvent,
    RunEventRecord,
    RunRecord,
    SessionRunRecord,
)
from reactor.runtime_settings.service import RuntimeSettingRecord
from reactor.tools.approval import ApprovalDecision, ApprovalRequest
from reactor.tools.catalog import ToolSpec

ADMIN_HEADERS = {"X-Reactor-Admin": "true", "X-Reactor-User-Id": "admin_1"}


async def test_health_and_ready_endpoints() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        health = await client.get("/healthz")
        actuator_health = await client.get("/actuator/health")
        ready = await client.get("/readyz")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert actuator_health.status_code == 200
    assert actuator_health.json() == {"status": "UP"}
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert app.version == __version__


async def test_admin_compatibility_a2a_diagnostics_alias() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/a2a/diagnostics")

    assert response.status_code == 200
    assert response.json()["protocolVersion"] == "1.0"


async def test_ready_endpoint_requires_redis_for_production_multi_replica(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        health_router,
        "get_settings",
        lambda: Settings(
            environment="production",
            api_replica_count=2,
            worker_replica_count=1,
            database_required=False,
            redis_url=None,
            redis_required=False,
        ),
    )
    transport = ASGITransport(app=create_app())

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        ready = await client.get("/readyz")

    assert ready.status_code == 503
    assert ready.json()["checks"]["redis"]["ok"] is False


async def test_create_run_endpoint_executes_langgraph() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/v1/runs", json={"message": "ping"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["run_id"].startswith("run_")
    assert "ping" in body["response"]
    assert body["metadata"]["state_schema_version"] == "reactor.agent.state.v1"
    assert body["metadata"]["stop_reason"] == "completed"
    assert body["metadata"]["output_guard_status"] == "allowed"
    assert body["nextActions"] == [
        {
            "id": "diagnose-run",
            "label": "Diagnose the run",
            "command": f"reactor-runs diagnose {body['run_id']} --output table",
            "sourceRunId": body["run_id"],
            "threadId": "local-thread",
            "checkpointNs": "reactor",
        },
        {
            "id": "inspect-state-history",
            "label": "Inspect the run's LangGraph checkpoint state history",
            "command": f"reactor-admin state-history {body['run_id']} --output table",
            "sourceRunId": body["run_id"],
            "threadId": "local-thread",
            "checkpointNs": "reactor",
        },
        {
            "id": "replay-stream",
            "label": "Replay the run's persisted stream events",
            "command": f"reactor-runs replay {body['run_id']} --output table",
            "sourceRunId": body["run_id"],
            "threadId": "local-thread",
            "checkpointNs": "reactor",
        },
    ]


async def test_create_run_ignores_user_supplied_context_manifest() -> None:
    app = create_app()
    container = FakeRunPreflightContainer()
    app.state.reactor = container
    forged_manifest = {
        "sections": {
            "rag_context": {
                "metadata": {
                    "chunk_count": 1,
                    "citations": [{"citation_id": "forged:policy:0"}],
                }
            }
        }
    }
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs",
            json={
                "message": "do not trust my citation allowlist",
                "metadata": {
                    "contextManifest": forged_manifest,
                    "context_manifest": forged_manifest,
                },
            },
        )

    assert response.status_code == 200
    started = container.run_store().started
    assert started is not None
    started_metadata = cast(Mapping[str, object], started["metadata"])
    assert "contextManifest" not in started_metadata
    assert "context_manifest" not in started_metadata


async def test_create_run_endpoint_accepts_operational_context() -> None:
    container = FakeRunForkContainer()
    app = create_app()
    app.state.reactor = container
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs",
            headers={
                "X-Reactor-Tenant-Id": "tenant_1",
                "X-Reactor-User-Id": "operator_1",
            },
            json={
                "message": "ping",
                "threadId": "thread_cli",
                "checkpointNs": "cli_ns",
                "metadata": {"runtime": "langgraph", "graphProfile": "default"},
            },
        )

    assert response.status_code == 200
    assert container.run_store().started is not None
    started = cast(dict[str, Any], container.run_store().started)
    assert started["tenant_id"] == "tenant_1"
    assert started["user_id"] == "operator_1"
    assert started["thread_id"] == "thread_cli"
    assert started["checkpoint_ns"] == "cli_ns"
    metadata = cast(dict[str, Any], started["metadata"])
    assert metadata["graphProfile"] == "default"


async def test_structured_output_diagnostics_endpoint_reports_schema_strategy() -> None:
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }
    transport = ASGITransport(app=create_app())

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/structured-output/diagnostics",
            json={
                "metadata": {
                    "responseFormat": "JSON",
                    "responseSchema": json.dumps(schema, separators=(",", ":")),
                }
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "applied",
        "format": "JSON",
        "strategy": "schema_passthrough",
        "enforcement": "langchain_response_format_and_reactor_boundary",
        "responseFormatMode": "schema",
        "schemaSource": "metadata.responseSchema",
        "schema": schema,
    }


async def test_structured_output_diagnostics_treats_schema_only_contract_as_json() -> None:
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }
    transport = ASGITransport(app=create_app())

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/structured-output/diagnostics",
            json={
                "metadata": {
                    "responseSchema": json.dumps(schema, separators=(",", ":")),
                }
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "applied",
        "format": "JSON",
        "strategy": "schema_passthrough",
        "enforcement": "langchain_response_format_and_reactor_boundary",
        "responseFormatMode": "schema",
        "schemaSource": "metadata.responseSchema",
        "schema": schema,
    }


async def test_structured_output_diagnostics_endpoint_reports_citation_boundary() -> None:
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }
    context_manifest = {
        "sections": {
            "rag_context": {
                "metadata": {
                    "chunk_count": 1,
                    "citations": [{"citation_id": "policy_doc:3"}],
                }
            }
        }
    }
    transport = ASGITransport(app=create_app())

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/structured-output/diagnostics",
            json={
                "metadata": {
                    "responseFormat": "JSON",
                    "responseSchema": json.dumps(schema, separators=(",", ":")),
                    "contextManifest": context_manifest,
                }
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "applied",
        "format": "JSON",
        "strategy": "schema_passthrough",
        "enforcement": "langchain_response_format_and_reactor_boundary",
        "responseFormatMode": "schema",
        "schemaSource": "metadata.responseSchema",
        "schema": {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "citations": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["policy_doc:3"]},
                    "minItems": 1,
                    "uniqueItems": True,
                },
            },
            "required": ["answer", "citations"],
        },
        "citationBoundary": {
            "status": "enforced",
            "source": "context_manifest",
            "citationIds": ["policy_doc:3"],
            "requiredMetadata": [
                "structured_output_allowed_citation_ids",
                "structured_output_citation_policy",
                "structured_output_citation_count",
            ],
        },
    }


async def test_structured_output_diagnostics_endpoint_reports_missing_citation_ids() -> None:
    context_manifest: dict[str, object] = {
        "sections": {
            "rag_context": {
                "metadata": {
                    "chunk_count": 1,
                    "citations": [],
                }
            }
        }
    }
    transport = ASGITransport(app=create_app())

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/structured-output/diagnostics",
            json={
                "metadata": {
                    "responseFormat": "JSON",
                    "contextManifest": context_manifest,
                }
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["schema"] == {
        "type": "object",
        "properties": {
            "citations": {
                "type": "array",
                "items": {"type": "string", "enum": []},
                "minItems": 1,
                "uniqueItems": True,
            }
        },
        "required": ["citations"],
    }
    assert body["citationBoundary"] == {
        "status": "enforced",
        "source": "context_manifest",
        "citationIds": [],
        "reason": "missing_context_citation_ids",
        "requiredMetadata": [
            "structured_output_allowed_citation_ids",
            "structured_output_citation_policy",
            "structured_output_citation_count",
        ],
    }


async def test_structured_output_diagnostics_endpoint_reports_invalid_schema() -> None:
    transport = ASGITransport(app=create_app())

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/structured-output/diagnostics",
            json={
                "metadata": {
                    "responseFormat": "JSON",
                    "responseSchema": '{"type":',
                }
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ignored",
        "format": "JSON",
        "strategy": "json_object_schema",
        "enforcement": "langchain_response_format_and_reactor_boundary",
        "responseFormatMode": "json_object",
        "fallbackReason": "invalid_response_schema",
        "ignoredSchema": {
            "status": "ignored",
            "reason": "invalid_response_schema",
            "source": "metadata.responseSchema",
        },
    }


async def test_run_preflight_endpoint_reports_execution_policy_without_creating_run() -> None:
    app = create_app()
    container = FakeRunPreflightContainer()
    app.state.reactor = container
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/preflight",
            headers={"X-Reactor-Tenant-Id": "tenant_1", "X-Reactor-User-Id": "user_1"},
            json={
                "message": "summarize policy",
                "threadId": "thread_policy",
                "checkpointNs": "policy_ns",
                "metadata": {
                    "runtime": "langchain_agent",
                    "graphProfile": "research",
                    "responseFormat": "JSON",
                    "responseSchema": json.dumps(schema, separators=(",", ":")),
                },
            },
        )

    assert response.status_code == 200
    assert container.run_store().started is None
    assert container.tool_provider.calls == ["tenant_1"]
    body = response.json()
    assert body["status"] == "ready"
    assert body["tenant_id"] == "tenant_1"
    assert body["user_id"] == "user_1"
    assert body["runtime"] == "langchain_agent"
    assert body["thread_id"] == "thread_policy"
    assert body["checkpoint_ns"] == "policy_ns"
    assert body["model"] == {
        "provider": "openai",
        "name": "gpt-5-mini",
    }
    assert body["middlewarePolicy"]["status"] == "applied"
    assert body["middlewarePolicy"]["policy"]["toolCallRunLimit"] == 2
    assert body["middlewareChain"]["status"] == "applied"
    assert body["middlewareChain"]["count"] >= 1
    assert body["toolProfileBudget"]["status"] == "applied"
    assert body["toolProfileBudget"]["configuredToolCount"] == 3
    assert body["toolProfileBudget"]["activeTools"] == ["Rag:hybrid_search"]
    assert body["toolProfileBudget"]["droppedTools"] == [
        {
            "tool": "Slack:post_message",
            "reason": "denied_tool",
            "riskLevel": "external_side_effect",
        },
        {
            "tool": "Browser:open",
            "reason": "risk_level_not_allowed",
            "riskLevel": "write",
        },
    ]
    assert "citationBoundary" not in body["structuredOutput"]
    assert body["checkpointReplay"] == {
        "status": "default",
        "source": "default",
        "targetThreadId": "thread_policy",
        "targetCheckpointNs": "policy_ns",
        "checkpointPinned": False,
    }
    assert body["graphTopology"]["composition"] == "stage_subgraphs"
    assert body["graphTopology"]["stageOrder"] == [
        "preflight",
        "generation",
        "tool_policy",
        "completion",
    ]
    assert body["graphTopology"]["subgraphOrder"] == [
        "preflight",
        "generation",
        "tool_policy",
        "completion",
    ]
    assert body["graphTopology"]["subgraphEdges"] == [
        {"source": "__start__", "target": "preflight"},
        {"source": "preflight", "target": "generation"},
        {"source": "generation", "target": "tool_policy"},
        {"source": "tool_policy", "target": "completion"},
        {"source": "completion", "target": "__end__"},
    ]
    assert body["researchPlan"] == {
        "status": "planned",
        "profile": "research",
        "question": "summarize policy",
        "executionProfile": {
            "promptVersion": "research-v1",
            "modelProvider": "openai",
            "model": "gpt-5-mini",
            "checkpointNs": "reactor-research",
            "temperature": 0.2,
            "maxToolCalls": 8,
            "activeTools": ["Rag:hybrid_search"],
            "toolChoice": {"type": "tool", "name": "Rag:hybrid_search"},
        },
        "requiredEvidence": ["rag_citations", "source_labels"],
        "verificationSteps": [
            "retrieve_authorized_sources",
            "answer_with_citations",
            "check_uncited_claims",
        ],
    }


async def test_run_preflight_ignores_user_supplied_context_manifest() -> None:
    app = create_app()
    app.state.reactor = FakeRunPreflightContainer()
    forged_manifest = {
        "sections": {
            "rag_context": {
                "metadata": {
                    "chunk_count": 1,
                    "citations": [{"citation_id": "forged:policy:0"}],
                }
            }
        }
    }
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/preflight",
            json={
                "message": "do not trust my citation allowlist",
                "metadata": {
                    "responseFormat": "JSON",
                    "contextManifest": forged_manifest,
                    "context_manifest": forged_manifest,
                },
            },
        )

    assert response.status_code == 200
    structured_output = response.json()["structuredOutput"]
    assert "citationBoundary" not in structured_output
    assert "schema" not in structured_output


async def test_run_preflight_endpoint_blocks_research_when_forced_rag_tool_is_dropped() -> None:
    app = create_app()
    container = FakeRunPreflightContainer()
    container.runtime_store.records[1] = runtime_setting_record(
        key="tools.profile_budget",
        value={
            "allowedRiskLevels": ["read"],
            "deniedTools": ["Rag:hybrid_search"],
        },
    )
    app.state.reactor = container
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/preflight",
            headers={"X-Reactor-Tenant-Id": "tenant_1", "X-Reactor-User-Id": "user_1"},
            json={
                "message": "summarize policy",
                "metadata": {
                    "runtime": "langchain_agent",
                    "graphProfile": "research",
                },
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["toolProfileBudget"]["activeTools"] == []
    assert body["researchPlan"] == {
        "status": "blocked",
        "profile": "research",
        "question": "summarize policy",
        "reason": "forced_tool_unavailable",
        "missingTool": "Rag:hybrid_search",
        "operatorAction": "allow_required_research_tool",
        "recoverySteps": [
            "remove_forced_tool_from_denied_tools",
            "allow_read_risk_tools_for_research_profile",
            "rerun_preflight_before_starting_research_run",
        ],
    }


async def test_agent_card_endpoint() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/.well-known/agent-card.json")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Reactor"
    assert body["capabilities"]["streaming"] is True
    assert body["capabilities"]["pushNotifications"] is True
    assert body["skills"][0]["id"] == "reactor-agent-run"


async def test_agent_card_uses_configured_canonical_external_endpoint() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(Settings(external_base_url="https://api.reactor.example/"))
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/.well-known/agent-card.json")

    assert response.status_code == 200
    body = response.json()
    assert body["supportedInterfaces"] == [
        {
            "url": "https://api.reactor.example/a2a",
            "protocolBinding": "JSONRPC",
            "protocolVersion": "1.0",
        },
        {
            "url": "https://api.reactor.example/a2a",
            "protocolBinding": "REST",
            "protocolVersion": "1.0",
        },
    ]


async def test_run_events_endpoint_requires_persistence() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/runs/run_123/events")

    assert response.status_code == 503
    assert response.json()["detail"] == "run event persistence is not configured"


async def test_run_detail_endpoint_returns_tenant_scoped_run() -> None:
    app = create_app()
    app.state.reactor = FakeRunEventsContainer(
        [],
        tenant_id="tenant_1",
        user_id="user_1",
    )
    app.state.reactor.run_events_store.session = replace(
        app.state.reactor.run_events_store.session,
        metadata={
            "state_schema_version": "reactor.agent.state.v1",
            "last_checkpoint_id": "checkpoint_latest",
            "private_tool_payload": {"api_key": "sk-test-secret"},
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
        },
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/runs/run_123",
            headers={"X-Reactor-Tenant-Id": "tenant_1", "X-Reactor-User-Id": "user_1"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "run_id": "run_123",
        "tenant_id": "tenant_1",
        "user_id": "user_1",
        "thread_id": "thread_1",
        "checkpoint_ns": "default",
        "last_checkpoint_id": "checkpoint_latest",
        "status": "completed",
        "input_text": "hello",
        "response_text": "private answer",
        "created_at": "2026-06-28T00:00:00+00:00",
        "updated_at": "2026-06-28T00:00:01+00:00",
        "metadata": {
            "state_schema_version": "reactor.agent.state.v1",
            "tool_profile_budget": {
                "maxTools": 1,
                "dropped_tools": [
                    {
                        "tool": "builtin:send_webhook",
                        "reason": "max_tools_exceeded",
                    }
                ],
            },
        },
        "nextActions": [
            {
                "id": "diagnose-run",
                "label": "Diagnose the run",
                "command": "reactor-runs diagnose run_123 --output table",
                "sourceRunId": "run_123",
                "threadId": "thread_1",
                "checkpointNs": "default",
                "checkpointId": "checkpoint_latest",
            },
            {
                "id": "inspect-state-history",
                "label": "Inspect the run's LangGraph checkpoint state history",
                "command": "reactor-admin state-history run_123 --output table",
                "sourceRunId": "run_123",
                "threadId": "thread_1",
                "checkpointNs": "default",
                "checkpointId": "checkpoint_latest",
            },
            {
                "id": "replay-stream",
                "label": "Replay the run's persisted stream events",
                "command": "reactor-runs replay run_123 --output table",
                "sourceRunId": "run_123",
                "threadId": "thread_1",
                "checkpointNs": "default",
                "checkpointId": "checkpoint_latest",
            },
            {
                "id": "fork-checkpoint",
                "label": "Fork the run from its latest LangGraph checkpoint",
                "command": (
                    "reactor-runs fork run_123 --checkpoint-ns default "
                    "--checkpoint-id checkpoint_latest --output table"
                ),
                "sourceRunId": "run_123",
                "threadId": "thread_1",
                "checkpointNs": "default",
                "checkpointId": "checkpoint_latest",
            },
        ],
    }


async def test_stream_events_endpoint_replays_only_stream_events_after_sequence() -> None:
    app = create_app()
    app.state.reactor = FakeRunEventsContainer(
        [
            RunEventRecord(sequence=1, event_type="run.created", payload={"status": "started"}),
            RunEventRecord(sequence=2, event_type="run.stream.started", payload={}),
            RunEventRecord(sequence=3, event_type="run.stream.token", payload={"text": "hello"}),
            RunEventRecord(
                sequence=4,
                event_type="run.stream.tool",
                payload={
                    "tool_results": [
                        {
                            "tool_id": "builtin:send_webhook",
                            "status": "succeeded",
                            "payload": {"api_key": "sk-test-secret"},
                            "raw_output": "sk-test-secret",
                        }
                    ]
                },
            ),
            RunEventRecord(sequence=5, event_type="run.completed", payload={"status": "done"}),
            RunEventRecord(sequence=6, event_type="run.stream.completed", payload={}),
        ]
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/runs/run_123/stream-events", params={"after_sequence": 2})
        token_response = await client.get(
            "/v1/runs/run_123/stream-events",
            params={"after_sequence": 2, "event_type": "run.stream.token"},
        )

    assert response.status_code == 200
    assert response.json() == [
        {"sequence": 3, "event_type": "run.stream.token", "payload": {"text": "hello"}},
        {
            "sequence": 4,
            "event_type": "run.stream.tool",
            "payload": {
                "tool_results": [
                    {
                        "tool_id": "builtin:send_webhook",
                        "status": "succeeded",
                    }
                ]
            },
        },
        {"sequence": 6, "event_type": "run.stream.completed", "payload": {}},
    ]
    assert token_response.status_code == 200
    assert token_response.json() == [
        {"sequence": 3, "event_type": "run.stream.token", "payload": {"text": "hello"}},
    ]
    assert app.state.reactor.run_events_store.list_event_calls == [
        ("run_123", "local", 2),
        ("run_123", "local", 2),
    ]


async def test_stream_events_endpoint_redacts_secret_shaped_stream_text() -> None:
    app = create_app()
    app.state.reactor = FakeRunEventsContainer(
        [
            RunEventRecord(
                sequence=1,
                event_type="run.stream.token",
                payload={
                    "text": "provider token sk-test-secret-value for user@example.com",
                    "graph_node": "model",
                },
            )
        ]
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/runs/run_123/stream-events")

    assert response.status_code == 200
    assert response.json() == [
        {
            "sequence": 1,
            "event_type": "run.stream.token",
            "payload": {
                "text": "provider token [REDACTED] for [REDACTED]",
                "graph_node": "model",
            },
        }
    ]


async def test_stream_events_endpoint_preserves_approval_id_without_tool_input() -> None:
    app = create_app()
    app.state.reactor = FakeRunEventsContainer(
        [
            RunEventRecord(
                sequence=1,
                event_type="run.stream.approval",
                payload={
                    "approval_status": "pending",
                    "action_count": 1,
                    "approval_id": "approval_1",
                    "tool_input": {"authorization": "private-credential"},
                },
            )
        ]
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/runs/run_123/stream-events")

    assert response.status_code == 200
    assert response.json() == [
        {
            "sequence": 1,
            "event_type": "run.stream.approval",
            "payload": {
                "approval_status": "pending",
                "action_count": 1,
                "approval_id": "approval_1",
            },
        }
    ]
    assert "private-credential" not in response.text


async def test_run_resume_endpoint_resumes_interrupted_graph_with_principal_access() -> None:
    app = create_app()
    container = FakeRunResumeContainer()
    app.state.reactor = container
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/run_123/resume",
            headers={"X-Reactor-Tenant-Id": "tenant_1", "X-Reactor-User-Id": "user_1"},
            json={"approvalId": "approval_1", "approved": True},
        )

    assert response.status_code == 200
    assert response.json() == {
        "run_id": "run_123",
        "status": "completed",
        "response": "resumed answer",
        "metadata": {},
        "nextActions": [
            {
                "id": "diagnose-run",
                "label": "Diagnose the run",
                "command": "reactor-runs diagnose run_123 --output table",
                "sourceRunId": "run_123",
                "threadId": "thread_1",
                "checkpointNs": "reactor",
                "checkpointId": "checkpoint_interrupted_1",
            },
            {
                "id": "inspect-state-history",
                "label": "Inspect the run's LangGraph checkpoint state history",
                "command": "reactor-admin state-history run_123 --output table",
                "sourceRunId": "run_123",
                "threadId": "thread_1",
                "checkpointNs": "reactor",
                "checkpointId": "checkpoint_interrupted_1",
            },
            {
                "id": "replay-stream",
                "label": "Replay the run's persisted stream events",
                "command": "reactor-runs replay run_123 --output table",
                "sourceRunId": "run_123",
                "threadId": "thread_1",
                "checkpointNs": "reactor",
                "checkpointId": "checkpoint_interrupted_1",
            },
            {
                "id": "fork-checkpoint",
                "label": "Fork the run from its latest LangGraph checkpoint",
                "command": (
                    "reactor-runs fork run_123 --checkpoint-ns reactor "
                    "--checkpoint-id checkpoint_interrupted_1 --output table"
                ),
                "sourceRunId": "run_123",
                "threadId": "thread_1",
                "checkpointNs": "reactor",
                "checkpointId": "checkpoint_interrupted_1",
            },
        ],
    }
    graph_call = container.graph.calls[0]
    assert graph_call["config"] == {
        "recursion_limit": DEFAULT_LANGGRAPH_RECURSION_LIMIT,
        "run_name": "reactor.langgraph.resume",
        "tags": ["reactor", "runtime:langgraph"],
        "metadata": {"reactor.runtime": "langgraph"},
        "configurable": {
            "thread_id": langgraph_checkpoint_thread_id(
                tenant_id="tenant_1",
                thread_id="thread_1",
                checkpoint_ns="reactor",
            ),
            "checkpoint_ns": "",
            "checkpoint_id": "checkpoint_interrupted_1",
        },
    }
    assert graph_call["resume"] == {
        "schema_version": "reactor.approval_resume.v1",
        "approval_id": "approval_1",
        "approved": True,
        "decided_by": "user_1",
        "reason": None,
    }
    completed_result, completed_metadata = container.run_store().completed[0]
    assert completed_result.status == "completed"
    assert completed_metadata["resumed_from_run_id"] == "run_123"
    assert completed_metadata["approval_id"] == "approval_1"
    assert container.run_store().events[-1].event_type == "run.resumed"
    assert container.run_store().events[-1].payload == {
        "approval_id": "approval_1",
        "approved": True,
        "decided_by": "user_1",
        "resumed_by": "user_1",
        "reason": None,
        "runtime": "langgraph",
    }


async def test_run_cancel_endpoint_marks_run_cancelled_after_principal_access() -> None:
    app = create_app()
    container = FakeRunResumeContainer()
    app.state.reactor = container
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/run_123/cancel",
            headers={"X-Reactor-Tenant-Id": "tenant_1", "X-Reactor-User-Id": "user_1"},
            json={"reason": "user requested"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "run_id": "run_123",
        "status": "cancelled",
        "response": "Run cancelled.",
        "metadata": {},
        "nextActions": [
            {
                "id": "diagnose-run",
                "label": "Diagnose the run",
                "command": "reactor-runs diagnose run_123 --output table",
                "sourceRunId": "run_123",
                "threadId": "thread_1",
                "checkpointNs": "reactor",
                "checkpointId": "checkpoint_interrupted_1",
            },
            {
                "id": "inspect-state-history",
                "label": "Inspect the run's LangGraph checkpoint state history",
                "command": "reactor-admin state-history run_123 --output table",
                "sourceRunId": "run_123",
                "threadId": "thread_1",
                "checkpointNs": "reactor",
                "checkpointId": "checkpoint_interrupted_1",
            },
            {
                "id": "replay-stream",
                "label": "Replay the run's persisted stream events",
                "command": "reactor-runs replay run_123 --output table",
                "sourceRunId": "run_123",
                "threadId": "thread_1",
                "checkpointNs": "reactor",
                "checkpointId": "checkpoint_interrupted_1",
            },
            {
                "id": "fork-checkpoint",
                "label": "Fork the run from its latest LangGraph checkpoint",
                "command": (
                    "reactor-runs fork run_123 --checkpoint-ns reactor "
                    "--checkpoint-id checkpoint_interrupted_1 --output table"
                ),
                "sourceRunId": "run_123",
                "threadId": "thread_1",
                "checkpointNs": "reactor",
                "checkpointId": "checkpoint_interrupted_1",
            },
        ],
    }
    completed_result, completed_metadata = container.run_store().completed[0]
    assert completed_result.status == "cancelled"
    assert completed_metadata["cancelled_by"] == "user_1"
    assert completed_metadata["cancel_reason"] == "user requested"
    assert container.run_store().events[-1].event_type == "run.cancelled"
    assert container.run_store().events[-1].payload == {
        "status": "cancelled",
        "cancelled_by": "user_1",
        "reason": "user requested",
    }


async def test_run_cancel_endpoint_rejects_existing_terminal_run() -> None:
    app = create_app()
    container = FakeRunResumeContainer()
    container.run_store().session = replace(
        container.run_store().session,
        status="completed",
        response_text="already completed",
    )
    app.state.reactor = container
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/run_123/cancel",
            headers={"X-Reactor-Tenant-Id": "tenant_1", "X-Reactor-User-Id": "user_1"},
            json={"reason": "too late"},
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "run is not running"}
    assert container.run_store().completed == []
    assert all(event.event_type != "run.cancelled" for event in container.run_store().events)


async def test_run_fork_endpoint_starts_new_run_from_source_checkpoint_contract() -> None:
    app = create_app()
    container = FakeRunForkContainer()
    app.state.reactor = container
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/run_123/fork",
            headers={"X-Reactor-Tenant-Id": "tenant_1", "X-Reactor-User-Id": "user_1"},
            json={
                "message": "try a safer branch",
                "threadId": "thread_fork",
                "checkpointNs": "fork_ns",
                "checkpointId": "checkpoint_7",
                "metadata": {
                    "source": "spoofed",
                    "forkedFromRunId": "run_spoofed",
                    "forkTargetThreadId": "thread_spoofed",
                    "forkTargetCheckpointNs": "ns_spoofed",
                    "forkedFromExecutionContract": {
                        "runtime": "langchain_agent",
                        "graphProfile": "spoofed",
                    },
                    "experiment": "safer-tools",
                },
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source_run_id"] == "run_123"
    assert body["thread_id"] == "thread_fork"
    assert body["checkpoint_ns"] == "fork_ns"
    assert body["status"] == "completed"
    assert body["response"] == "forked answer"
    assert body["provenance"] == {
        "source": "checkpoint_fork",
        "forked_from_run_id": "run_123",
        "forked_from_thread_id": "thread_1",
        "forked_from_checkpoint_ns": "reactor",
        "forked_from_checkpoint_id": "checkpoint_7",
        "fork_target_thread_id": "thread_fork",
        "fork_target_checkpoint_ns": "fork_ns",
    }
    started = container.run_store().started
    assert started is not None
    assert started["input_text"] == "try a safer branch"
    assert started["thread_id"] == "thread_fork"
    assert started["checkpoint_ns"] == "fork_ns"
    metadata = cast(Mapping[str, object], started["metadata"])
    assert metadata["source"] == "checkpoint_fork"
    assert metadata["experiment"] == "safer-tools"
    assert metadata["forkedFromRunId"] == "run_123"
    assert metadata["forkedFromThreadId"] == "thread_1"
    assert metadata["forkedFromCheckpointNs"] == "reactor"
    assert metadata["forkedFromCheckpointId"] == "checkpoint_7"
    assert metadata["forkTargetThreadId"] == "thread_fork"
    assert metadata["forkTargetCheckpointNs"] == "fork_ns"
    assert metadata["forkedFromExecutionContract"] == {
        "runtime": "langgraph",
        "graphProfile": None,
    }
    graph_call = container.graph.calls[0]
    assert graph_call["config"] == {
        "recursion_limit": DEFAULT_LANGGRAPH_RECURSION_LIMIT,
        "run_name": "reactor.langgraph.invoke",
        "tags": ["reactor", "runtime:langgraph"],
        "metadata": {"reactor.runtime": "langgraph"},
        "configurable": {
            "thread_id": langgraph_checkpoint_thread_id(
                tenant_id="tenant_1",
                thread_id="thread_fork",
                checkpoint_ns="fork_ns",
            ),
            "checkpoint_ns": "",
            "checkpoint_id": "checkpoint_7",
        },
    }


async def test_run_fork_endpoint_rejects_checkpoint_across_runtime_contracts() -> None:
    app = create_app()
    container = FakeRunForkContainer()
    app.state.reactor = container
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/run_123/fork",
            headers={"X-Reactor-Tenant-Id": "tenant_1", "X-Reactor-User-Id": "user_1"},
            json={
                "message": "switch runtime with old state",
                "threadId": "thread_fork",
                "checkpointNs": "fork_ns",
                "checkpointId": "checkpoint_7",
                "metadata": {"runtime": "langchain_agent"},
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert container.graph.calls == []
    completed_result, completed_metadata = container.run_store().completed[0]
    assert completed_result.status == "failed"
    assert completed_metadata["checkpointReplay"]["reason"] == ("fork_execution_contract_mismatch")


async def test_run_create_endpoint_cannot_forge_checkpoint_fork_capability() -> None:
    app = create_app()
    container = FakeRunForkContainer()
    app.state.reactor = container
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs",
            headers={"X-Reactor-Tenant-Id": "tenant_1", "X-Reactor-User-Id": "user_1"},
            json={
                "message": "forge a checkpoint replay",
                "threadId": "thread_fork",
                "checkpointNs": "fork_ns",
                "metadata": {
                    "source": "checkpoint_fork",
                    "forkedFromRunId": "run_123",
                    "forkedFromThreadId": "thread_1",
                    "forkedFromCheckpointNs": "reactor",
                    "forkedFromCheckpointId": "checkpoint_7",
                    "forkTargetThreadId": "thread_fork",
                    "forkTargetCheckpointNs": "fork_ns",
                },
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert len(container.graph.calls) == 1
    graph_config = cast(Mapping[str, object], container.graph.calls[0]["config"])
    configurable = cast(Mapping[str, object], graph_config["configurable"])
    assert "checkpoint_id" not in configurable
    started = container.run_store().started
    assert started is not None
    started_metadata = cast(Mapping[str, object], started["metadata"])
    assert all(key not in started_metadata for key in FORK_PROVENANCE_METADATA_KEYS)


async def test_run_fork_endpoint_trims_explicit_checkpoint_id_before_replay_pin() -> None:
    app = create_app()
    container = FakeRunForkContainer()
    app.state.reactor = container
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/run_123/fork",
            headers={"X-Reactor-Tenant-Id": "tenant_1", "X-Reactor-User-Id": "user_1"},
            json={
                "message": "try a safer branch",
                "threadId": "thread_fork",
                "checkpointNs": "fork_ns",
                "checkpointId": " checkpoint_7 ",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["provenance"]["forked_from_checkpoint_id"] == "checkpoint_7"
    started = container.run_store().started
    assert started is not None
    metadata = cast(Mapping[str, object], started["metadata"])
    assert metadata["forkedFromCheckpointId"] == "checkpoint_7"
    graph_call = container.graph.calls[0]
    assert graph_call["config"] == {
        "recursion_limit": DEFAULT_LANGGRAPH_RECURSION_LIMIT,
        "run_name": "reactor.langgraph.invoke",
        "tags": ["reactor", "runtime:langgraph"],
        "metadata": {"reactor.runtime": "langgraph"},
        "configurable": {
            "thread_id": langgraph_checkpoint_thread_id(
                tenant_id="tenant_1",
                thread_id="thread_fork",
                checkpoint_ns="fork_ns",
            ),
            "checkpoint_ns": "",
            "checkpoint_id": "checkpoint_7",
        },
    }


async def test_run_fork_endpoint_does_not_inherit_stale_checkpoint_pin() -> None:
    app = create_app()
    container = FakeRunForkContainer()
    container.run_store().session = replace(
        container.run_store().session,
        metadata={
            "source": "checkpoint_fork",
            "forkedFromRunId": "older_run",
            "forkedFromThreadId": "older_thread",
            "forkedFromCheckpointNs": "older_ns",
            "forkedFromCheckpointId": "older_checkpoint",
            "forkTargetThreadId": "older_target_thread",
            "forkTargetCheckpointNs": "older_target_ns",
            "personaId": "analyst",
            "contextManifest": {"sections": {"rag_context": {"metadata": {"chunk_count": 1}}}},
        },
    )
    app.state.reactor = container
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/run_123/fork",
            headers={"X-Reactor-Tenant-Id": "tenant_1", "X-Reactor-User-Id": "user_1"},
            json={
                "message": "branch without replay pin",
                "threadId": "thread_fork",
                "checkpointNs": "fork_ns",
                "metadata": {
                    "forkedFromCheckpointId": "spoofed_checkpoint",
                    "forkTargetThreadId": "spoofed_target_thread",
                    "forkTargetCheckpointNs": "spoofed_target_ns",
                    "experiment": "no-pin",
                    "context_manifest": {
                        "sections": {"rag_context": {"metadata": {"chunk_count": 1}}}
                    },
                },
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["provenance"] == {
        "source": "checkpoint_fork",
        "forked_from_run_id": "run_123",
        "forked_from_thread_id": "thread_1",
        "forked_from_checkpoint_ns": "reactor",
        "forked_from_checkpoint_id": None,
        "fork_target_thread_id": "thread_fork",
        "fork_target_checkpoint_ns": "fork_ns",
    }
    started = container.run_store().started
    assert started is not None
    metadata = cast(Mapping[str, object], started["metadata"])
    assert metadata["source"] == "checkpoint_fork"
    assert metadata["forkedFromRunId"] == "run_123"
    assert metadata["forkedFromThreadId"] == "thread_1"
    assert metadata["forkedFromCheckpointNs"] == "reactor"
    assert "forkedFromCheckpointId" not in metadata
    assert metadata["forkTargetThreadId"] == "thread_fork"
    assert metadata["forkTargetCheckpointNs"] == "fork_ns"
    assert "contextManifest" not in metadata
    assert "context_manifest" not in metadata
    graph_call = container.graph.calls[0]
    assert graph_call["config"] == {
        "recursion_limit": DEFAULT_LANGGRAPH_RECURSION_LIMIT,
        "run_name": "reactor.langgraph.invoke",
        "tags": ["reactor", "runtime:langgraph"],
        "metadata": {"reactor.runtime": "langgraph"},
        "configurable": {
            "thread_id": langgraph_checkpoint_thread_id(
                tenant_id="tenant_1",
                thread_id="thread_fork",
                checkpoint_ns="fork_ns",
            ),
            "checkpoint_ns": "",
        },
    }


async def test_run_fork_endpoint_uses_source_last_checkpoint_id_when_body_omits_pin() -> None:
    app = create_app()
    container = FakeRunForkContainer()
    container.run_store().session = replace(
        container.run_store().session,
        metadata={
            "runtime": "langgraph",
            "last_checkpoint_id": "checkpoint_latest",
            "checkpointId": "user_controlled_checkpoint",
        },
    )
    app.state.reactor = container
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/run_123/fork",
            headers={"X-Reactor-Tenant-Id": "tenant_1", "X-Reactor-User-Id": "user_1"},
            json={
                "message": "branch from latest persisted checkpoint",
                "threadId": "thread_fork",
                "checkpointNs": "fork_ns",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["provenance"]["forked_from_checkpoint_id"] == "checkpoint_latest"
    started = container.run_store().started
    assert started is not None
    metadata = cast(Mapping[str, object], started["metadata"])
    assert metadata["forkedFromCheckpointId"] == "checkpoint_latest"
    graph_call = container.graph.calls[0]
    assert graph_call["config"] == {
        "recursion_limit": DEFAULT_LANGGRAPH_RECURSION_LIMIT,
        "run_name": "reactor.langgraph.invoke",
        "tags": ["reactor", "runtime:langgraph"],
        "metadata": {"reactor.runtime": "langgraph"},
        "configurable": {
            "thread_id": langgraph_checkpoint_thread_id(
                tenant_id="tenant_1",
                thread_id="thread_fork",
                checkpoint_ns="fork_ns",
            ),
            "checkpoint_ns": "",
            "checkpoint_id": "checkpoint_latest",
        },
    }


async def test_run_fork_endpoint_rejects_cross_user_access() -> None:
    app = create_app()
    app.state.reactor = FakeRunForkContainer()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/run_123/fork",
            headers={"X-Reactor-Tenant-Id": "tenant_1", "X-Reactor-User-Id": "user_other"},
            json={"message": "must not fork"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied to run"
    assert app.state.reactor.run_store().started is None


async def test_run_events_endpoint_rejects_cross_tenant_access() -> None:
    app = create_app()
    app.state.reactor = FakeRunEventsContainer(
        [
            RunEventRecord(
                sequence=1,
                event_type="run.stream.token",
                payload={"text": "private answer"},
            )
        ],
        tenant_id="tenant_private",
        user_id="user_private",
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/runs/run_123/events",
            headers={
                "X-Reactor-Tenant-Id": "tenant_other",
                "X-Reactor-User-Id": "user_private",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied to run"
    assert app.state.reactor.run_events_store.list_events_called is False


async def test_stream_events_endpoint_rejects_cross_user_access() -> None:
    app = create_app()
    app.state.reactor = FakeRunEventsContainer(
        [
            RunEventRecord(
                sequence=1,
                event_type="run.stream.token",
                payload={"text": "private streamed answer"},
            )
        ],
        tenant_id="tenant_private",
        user_id="user_private",
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/runs/run_123/stream-events",
            headers={
                "X-Reactor-Tenant-Id": "tenant_private",
                "X-Reactor-User-Id": "user_other",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied to run"
    assert app.state.reactor.run_events_store.list_events_called is False


async def test_approval_endpoint_requires_persistence() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        legacy_response = await client.get(
            "/api/approvals",
            params={"tenant_id": "tenant_1"},
            headers=ADMIN_HEADERS,
        )
        response = await client.get(
            "/v1/approvals",
            params={"tenant_id": "tenant_1"},
            headers=ADMIN_HEADERS,
        )

    assert legacy_response.status_code == 503
    assert legacy_response.json()["detail"] == "approval persistence is not configured"
    assert response.status_code == 503
    assert response.json()["detail"] == "approval persistence is not configured"


async def test_approval_admin_routes_scope_to_principal_tenant() -> None:
    store = FakeApprovalStore()
    publisher = RecordingLifecyclePublisher()
    app = create_app()
    app.state.reactor = FakeApprovalContainer(
        store,
        publisher=publisher,
        run_store=FakeApprovalRunStore(),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        unauthenticated = await client.get("/v1/approvals", params={"tenant_id": "tenant_1"})
        unauthenticated_create = await client.post(
            "/v1/approvals",
            json={
                "tenant_id": "tenant_1",
                "run_id": "run_1",
                "tool_id": "tool_1",
                "requested_by": "user_1",
                "request_payload": {"action": "write"},
            },
        )
        created = await client.post(
            "/v1/approvals",
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
            json={
                "run_id": "run_2",
                "tool_id": "tool_2",
                "request_payload": {"action": "delete"},
            },
        )
        listed = await client.get(
            "/v1/approvals",
            params={"tenant_id": "tenant_2", "status": "pending"},
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
        )
        approved = await client.post(
            "/v1/approvals/approval_1/approve",
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
            json={},
        )

    assert unauthenticated.status_code == 403
    assert unauthenticated_create.status_code == 403
    assert created.status_code == 201
    assert created.json() == {"approval_id": "approval_created", "status": "pending"}
    assert listed.status_code == 200
    listed_items = listed.json()
    assert [item["approval_id"] for item in listed_items] == ["approval_1"]
    assert listed_items[0]["request_payload"] == {
        "idempotency_key": "tool:run_1:tool_1",
        "tool_risk_level": "external_side_effect",
        "tool_timeout_ms": 15000,
    }
    assert listed_items[0]["requested_at"] == "2026-07-11T12:00:00+00:00"
    assert approved.status_code == 200
    assert approved.json() == {"approval_id": "approval_1", "status": "approved"}
    assert store.requests == [("tenant_1", "run_2", "tool_2", "admin_1", {"action": "delete"})]
    assert store.list_calls == [("tenant_1", 50, "pending")]
    assert store.decisions == [("tenant_1", "approval_1", "admin_1", True)]
    assert publisher.events == [
        {
            "event_type": "approval.requested",
            "approval_id": "approval_created",
            "tenant_id": "tenant_1",
            "run_id": "run_2",
            "tool_id": "tool_2",
            "requested_by": "admin_1",
            "status": "pending",
        },
        {
            "event_type": "approval.decided",
            "approval_id": "approval_1",
            "tenant_id": "tenant_1",
            "run_id": "run_1",
            "tool_id": "tool_1",
            "decided_by": "admin_1",
            "approved": True,
            "status": "approved",
            "reason": None,
        },
    ]


async def test_approval_create_requires_run_access() -> None:
    store = FakeApprovalStore()
    app = create_app()
    app.state.reactor = FakeApprovalContainer(
        store,
        run_store=FakeApprovalRunStore(
            SessionRunRecord(
                run_id="run_private",
                tenant_id="tenant_private",
                user_id="user_private",
                thread_id="thread_private",
                checkpoint_ns="reactor",
                status="running",
                input_text="private",
                response_text=None,
                created_at="2026-06-28T00:00:00+00:00",
                updated_at="2026-06-28T00:00:01+00:00",
                metadata={},
            )
        ),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/approvals",
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
            json={
                "tenant_id": "tenant_1",
                "run_id": "run_private",
                "tool_id": "tool_1",
                "requested_by": "admin_1",
                "request_payload": {"action": "write"},
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied to run"
    assert store.requests == []


async def test_approval_lifecycle_publisher_failure_does_not_fail_decision() -> None:
    store = FakeApprovalStore()
    app = create_app()
    app.state.reactor = FakeApprovalContainer(store, publisher=FailingLifecyclePublisher())
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/approvals/approval_1/reject",
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
            json={
                "tenant_id": "tenant_1",
                "decided_by": "admin_1",
                "reason": "not allowed",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"approval_id": "approval_1", "status": "rejected"}
    assert store.decisions == [("tenant_1", "approval_1", "admin_1", False)]


async def test_approval_reject_requires_nonblank_reason() -> None:
    store = FakeApprovalStore()
    app = create_app()
    app.state.reactor = FakeApprovalContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/approvals/approval_1/reject",
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
            json={"reason": "   "},
        )

    assert response.status_code == 422
    assert store.decisions == []


async def test_mcp_registry_endpoint_requires_persistence() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        legacy_response = await client.get(
            "/api/mcp/servers",
            params={"tenant_id": "tenant_1"},
            headers=ADMIN_HEADERS,
        )
        response = await client.get(
            "/v1/mcp/servers",
            params={"tenant_id": "tenant_1"},
            headers=ADMIN_HEADERS,
        )

    assert legacy_response.status_code == 503
    assert legacy_response.json()["detail"] == "MCP registry persistence is not configured"
    assert response.status_code == 503
    assert response.json()["detail"] == "MCP registry persistence is not configured"


async def test_a2a_agents_endpoint_requires_admin_and_returns_empty_when_store_is_absent() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        unauthenticated = await client.get("/v1/a2a/agents")
        response = await client.get("/v1/a2a/agents", headers=ADMIN_HEADERS)

    assert unauthenticated.status_code == 403
    assert unauthenticated.json()["detail"] == "admin access required"
    assert response.status_code == 200
    assert response.json() == {"agents": []}


async def test_a2a_diagnostics_exposes_sdk_boundary() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/a2a/diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["protocolVersion"] == "1.0"
    assert body["endpoint"] == "/a2a"
    assert body["sdkAvailable"] is True


async def test_a2a_diagnostics_uses_configured_canonical_external_endpoint() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(Settings(external_base_url="https://api.reactor.example"))
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/a2a/diagnostics")

    assert response.status_code == 200
    assert response.json()["endpoint"] == "https://api.reactor.example/a2a"


async def test_a2a_supported_interfaces_endpoint_uses_sdk_agent_card_metadata() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(Settings(external_base_url="https://api.reactor.example/"))
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/a2a/supported-interfaces")

    assert response.status_code == 200
    assert response.json() == {
        "supportedInterfaces": [
            {
                "url": "https://api.reactor.example/a2a",
                "protocolBinding": "JSONRPC",
                "protocolVersion": "1.0",
            },
            {
                "url": "https://api.reactor.example/a2a",
                "protocolBinding": "REST",
                "protocolVersion": "1.0",
            },
        ]
    }


async def test_a2a_supported_interfaces_endpoint_does_not_publish_invalid_base_url() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(Settings(external_base_url="api.reactor.example"))
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/a2a/supported-interfaces")

    assert response.status_code == 200
    assert response.json() == {"supportedInterfaces": []}


async def test_a2a_jsonrpc_endpoint_is_sdk_mounted() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/a2a", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["jsonrpc"] == "2.0"
    assert body["error"]["code"] == -32600


async def test_a2a_rest_message_send_uses_sdk_executor() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/a2a/message:send",
            headers={"A2A-Version": "1.0"},
            json={
                "message": {
                    "messageId": "msg_1",
                    "role": "ROLE_USER",
                    "parts": [{"text": "hello"}],
                },
                "configuration": {"acceptedOutputModes": ["text/plain"]},
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["message"]["role"] == "ROLE_AGENT"
    assert "Agent runtime is ready." in body["message"]["parts"][0]["text"]
    assert "Reactor Python/LangGraph" not in body["message"]["parts"][0]["text"]
    assert "hello" in body["message"]["parts"][0]["text"]


async def test_a2a_rest_message_send_uses_reactor_run_service_boundary() -> None:
    run_store = RecordingA2ARunStore()
    graph = RecordingA2AGraph()
    app = create_app()
    app.state.reactor = FakeA2ARunContainer(run_store, graph)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/a2a/message:send",
            headers={"A2A-Version": "1.0"},
            json={
                "message": {
                    "messageId": "msg_1",
                    "contextId": "ctx_1",
                    "role": "ROLE_USER",
                    "parts": [{"text": "persist this A2A request"}],
                },
                "configuration": {"acceptedOutputModes": ["text/plain"]},
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["message"]["parts"][0]["text"] == "a2a persisted answer"
    assert run_store.started is not None
    assert run_store.started["tenant_id"] == "local"
    assert run_store.started["user_id"] == "a2a_peer"
    assert run_store.started["thread_id"] == "ctx_1"
    assert run_store.started["input_text"] == "persist this A2A request"
    assert run_store.started["metadata"]["channel"] == "a2a"
    assert run_store.started["metadata"]["a2aMessageId"] == "msg_1"
    assert graph.inputs[0]["tenant_id"] == "local"
    assert graph.inputs[0]["user_id"] == "a2a_peer"


async def test_a2a_rest_message_send_uses_trusted_api_key_principal() -> None:
    run_store = RecordingA2ARunStore()
    graph = RecordingA2AGraph()
    api_key = "reactor-a2a-key-1"  # noqa: S105
    settings = Settings(
        auth_api_keys=[
            (
                "a2a_key:tenant_api:a2a_service:ADMIN_DEVELOPER:"
                f"{sha256(api_key.encode()).hexdigest()}:engineering,agents"
            )
        ]
    )
    app = create_app()
    app.state.reactor = FakeA2ARunContainer(run_store, graph, settings=settings)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/a2a/message:send",
            headers={
                "A2A-Version": "1.0",
                "X-Reactor-API-Key": api_key,
                "X-Reactor-User-Id": "spoofed_user",
                "X-Reactor-Tenant-Id": "spoofed_tenant",
                "X-Reactor-Groups": "executive",
            },
            json={
                "message": {
                    "messageId": "msg_1",
                    "contextId": "ctx_1",
                    "role": "ROLE_USER",
                    "parts": [{"text": "use trusted principal"}],
                },
                "configuration": {"acceptedOutputModes": ["text/plain"]},
            },
        )

    assert response.status_code == 200
    assert run_store.started is not None
    assert run_store.started["tenant_id"] == "tenant_api"
    assert run_store.started["user_id"] == "a2a_service"
    assert graph.inputs[0]["tenant_id"] == "tenant_api"
    assert graph.inputs[0]["user_id"] == "a2a_service"
    assert graph.inputs[0]["trusted_user_groups"] == ("engineering", "agents")


async def test_a2a_rest_message_send_does_not_trust_unsigned_group_headers() -> None:
    run_store = RecordingA2ARunStore()
    graph = RecordingA2AGraph()
    app = create_app()
    app.state.reactor = FakeA2ARunContainer(run_store, graph)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/a2a/message:send",
            headers={
                "A2A-Version": "1.0",
                "X-Reactor-Tenant-Id": "tenant_1",
                "X-Reactor-User-Id": "peer_user",
                "X-Reactor-Groups": "executive,finance",
            },
            json={
                "message": {
                    "messageId": "msg_1",
                    "contextId": "ctx_1",
                    "role": "ROLE_USER",
                    "parts": [{"text": "must not inherit spoofed groups"}],
                },
                "configuration": {"acceptedOutputModes": ["text/plain"]},
            },
        )

    assert response.status_code == 200
    assert run_store.started is not None
    assert run_store.started["tenant_id"] == "tenant_1"
    assert run_store.started["user_id"] == "peer_user"
    assert graph.inputs[0]["trusted_user_groups"] == ()


async def test_a2a_rest_message_send_rejects_invalid_api_key_without_running_graph() -> None:
    run_store = RecordingA2ARunStore()
    graph = RecordingA2AGraph()
    settings = Settings(
        auth_api_keys=[
            (
                "a2a_key:tenant_api:a2a_service:ADMIN_DEVELOPER:"
                f"{sha256(b'correct-key').hexdigest()}:engineering"
            )
        ]
    )
    app = create_app()
    app.state.reactor = FakeA2ARunContainer(run_store, graph, settings=settings)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/a2a/message:send",
            headers={
                "A2A-Version": "1.0",
                "X-Reactor-API-Key": "wrong-key",
                "X-Reactor-User-Id": "spoofed_user",
                "X-Reactor-Tenant-Id": "spoofed_tenant",
            },
            json={
                "message": {
                    "messageId": "msg_1",
                    "contextId": "ctx_1",
                    "role": "ROLE_USER",
                    "parts": [{"text": "must not run"}],
                },
                "configuration": {"acceptedOutputModes": ["text/plain"]},
            },
        )

    assert response.status_code == 401
    assert "invalid API key" in response.text
    assert run_store.started is None
    assert graph.inputs == []


async def test_a2a_rest_message_send_enforces_inbound_access_policy() -> None:
    run_store = RecordingA2ARunStore()
    graph = RecordingA2AGraph()
    policy_store = FakeA2AInboundPolicyStore(allow_inbound=False)
    app = create_app()
    app.state.reactor = FakeA2ARunContainer(run_store, graph, a2a_store=policy_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/a2a/message:send",
            headers={
                "A2A-Version": "1.0",
                "X-Reactor-Tenant-Id": "tenant_1",
                "X-Reactor-User-Id": "peer_user",
            },
            json={
                "message": {
                    "messageId": "msg_1",
                    "contextId": "ctx_1",
                    "role": "ROLE_USER",
                    "parts": [{"text": "must not enter graph"}],
                },
                "configuration": {"acceptedOutputModes": ["text/plain"]},
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "A2A inbound access is denied"
    assert policy_store.checked == [("tenant_1", None)]
    assert run_store.started is None
    assert graph.inputs == []


async def test_a2a_rest_message_send_checks_peer_specific_inbound_access_policy() -> None:
    run_store = RecordingA2ARunStore()
    graph = RecordingA2AGraph()
    policy_store = FakeA2AInboundPolicyStore(allow_inbound=False)
    app = create_app()
    app.state.reactor = FakeA2ARunContainer(run_store, graph, a2a_store=policy_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/a2a/message:send",
            headers={
                "A2A-Version": "1.0",
                "X-Reactor-Tenant-Id": "tenant_1",
                "X-Reactor-User-Id": "peer_user",
                "X-Reactor-A2A-Peer-Id": "peer_1",
                "X-Reactor-A2A-Skill-Id": "read",
            },
            json={
                "message": {
                    "messageId": "msg_1",
                    "contextId": "ctx_1",
                    "role": "ROLE_USER",
                    "parts": [{"text": "must not enter graph"}],
                },
                "configuration": {"acceptedOutputModes": ["text/plain"]},
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "A2A inbound access is denied"
    assert policy_store.checked == [("tenant_1", "peer_1")]
    assert run_store.started is None
    assert graph.inputs == []


async def test_a2a_rest_message_send_enforces_inbound_skill_allowlist() -> None:
    run_store = RecordingA2ARunStore()
    graph = RecordingA2AGraph()
    policy_store = FakeA2AInboundPolicyStore(allow_inbound=True, allowed_skills=["read"])
    app = create_app()
    app.state.reactor = FakeA2ARunContainer(run_store, graph, a2a_store=policy_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/a2a/message:send",
            headers={
                "A2A-Version": "1.0",
                "X-Reactor-Tenant-Id": "tenant_1",
                "X-Reactor-User-Id": "peer_user",
                "X-Reactor-A2A-Peer-Id": "peer_1",
                "X-Reactor-A2A-Skill-Id": "write",
            },
            json={
                "message": {
                    "messageId": "msg_1",
                    "contextId": "ctx_1",
                    "role": "ROLE_USER",
                    "parts": [{"text": "must not enter graph"}],
                },
                "configuration": {"acceptedOutputModes": ["text/plain"]},
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "A2A skill is not allowed"
    assert policy_store.checked == [("tenant_1", "peer_1")]
    assert policy_store.skill_checks == [("tenant_1", "peer_1", "write")]
    assert run_store.started is None
    assert graph.inputs == []


async def test_a2a_rest_message_send_records_peer_agent_id_in_run_metadata() -> None:
    run_store = RecordingA2ARunStore()
    graph = RecordingA2AGraph()
    policy_store = FakeA2AInboundPolicyStore(allow_inbound=True)
    app = create_app()
    app.state.reactor = FakeA2ARunContainer(run_store, graph, a2a_store=policy_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/a2a/message:send",
            headers={
                "A2A-Version": "1.0",
                "X-Reactor-Tenant-Id": "tenant_1",
                "X-Reactor-User-Id": "peer_user",
                "X-Reactor-A2A-Peer-Id": "peer_1",
                "X-Reactor-A2A-Skill-Id": "read",
            },
            json={
                "message": {
                    "messageId": "msg_1",
                    "contextId": "ctx_1",
                    "role": "ROLE_USER",
                    "parts": [{"text": "record peer identity"}],
                },
                "configuration": {"acceptedOutputModes": ["text/plain"]},
            },
        )

    assert response.status_code == 200
    assert policy_store.checked == [("tenant_1", "peer_1")]
    assert policy_store.skill_checks == [("tenant_1", "peer_1", "read")]
    assert run_store.started is not None
    assert run_store.started["metadata"]["a2aPeerAgentId"] == "peer_1"
    assert run_store.started["metadata"]["a2aSkillId"] == "read"


class FakeContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings


class FakeRunEventsContainer:
    settings = Settings()
    graph = None

    def __init__(
        self,
        events: list[RunEventRecord],
        *,
        tenant_id: str = "local",
        user_id: str = "anonymous",
    ) -> None:
        self._run_store = FakeRunEventsStore(events, tenant_id=tenant_id, user_id=user_id)

    def run_store(self) -> FakeRunEventsStore:
        return self._run_store

    @property
    def run_events_store(self) -> FakeRunEventsStore:
        return self._run_store


class FakeRunPreflightContainer:
    graph = None

    def __init__(self) -> None:
        self.settings = Settings(default_checkpoint_ns="reactor")
        self._run_store = FakeRunForkStore()
        self.tool_provider = FakeRunPreflightToolProvider()
        self.runtime_store = FakeRunPreflightRuntimeSettingsStore()

    def run_store(self) -> FakeRunForkStore:
        return self._run_store

    def tool_store(self) -> FakeRunPreflightToolProvider:
        return self.tool_provider

    def runtime_settings_store(self) -> FakeRunPreflightRuntimeSettingsStore:
        return self.runtime_store


class FakeRunPreflightToolProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.tools = [
            tool_spec("Rag", "hybrid_search", "read"),
            tool_spec("Slack", "post_message", "external_side_effect"),
            tool_spec("Browser", "open", "write"),
        ]

    async def list_enabled_tool_specs(self, tenant_id: str) -> list[ToolSpec]:
        self.calls.append(tenant_id)
        return self.tools


class FakeRunPreflightRuntimeSettingsStore:
    def __init__(self) -> None:
        self.records = [
            runtime_setting_record(
                key="langchain.middleware_policy",
                value={
                    "modelCallRunLimit": 3,
                    "toolCallRunLimit": 2,
                },
            ),
            runtime_setting_record(
                key="tools.profile_budget",
                value={
                    "allowedRiskLevels": ["read"],
                    "deniedTools": ["Slack:post_message"],
                },
            ),
        ]

    async def list(self, *, tenant_id: str | None = None) -> list[RuntimeSettingRecord]:
        return [
            record for record in self.records if tenant_id is None or record.tenant_id == tenant_id
        ]


def runtime_setting_record(
    *,
    key: str,
    value: Mapping[str, object],
    tenant_id: str = "tenant_1",
) -> RuntimeSettingRecord:
    return RuntimeSettingRecord(
        tenant_id=tenant_id,
        key=key,
        value=json.dumps(value, separators=(",", ":")),
        value_type="JSON",
        category="agent",
        description=None,
        updated_by="admin_1",
        updated_at=datetime(2026, 6, 30, tzinfo=UTC),
        metadata={},
    )


def tool_spec(namespace: str, name: str, risk_level: str) -> ToolSpec:
    return ToolSpec(
        tenant_id="tenant_1",
        namespace=namespace,
        name=name,
        description=f"{namespace} {name}",
        risk_level=risk_level,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )


class FakeRunEventsStore:
    def __init__(
        self,
        events: list[RunEventRecord],
        *,
        tenant_id: str,
        user_id: str,
    ) -> None:
        self.events = events
        self.session = SessionRunRecord(
            run_id="run_123",
            tenant_id=tenant_id,
            user_id=user_id,
            thread_id="thread_1",
            checkpoint_ns="default",
            status="completed",
            input_text="hello",
            response_text="private answer",
            created_at="2026-06-28T00:00:00+00:00",
            updated_at="2026-06-28T00:00:01+00:00",
            metadata={},
        )
        self.list_events_called = False
        self.list_event_calls: list[tuple[str, str | None, int]] = []

    async def find_session(self, *, run_id: str) -> SessionRunRecord | None:
        assert run_id == "run_123"
        return self.session

    async def list_events(
        self,
        *,
        run_id: str,
        tenant_id: str | None = None,
        after_sequence: int = 0,
    ) -> list[RunEventRecord]:
        assert run_id == "run_123"
        assert tenant_id == self.session.tenant_id
        self.list_events_called = True
        self.list_event_calls.append((run_id, tenant_id, after_sequence))
        return [event for event in self.events if event.sequence > after_sequence]


class FakeRunResumeContainer(FakeRunEventsContainer):
    def __init__(self) -> None:
        self.graph = RecordingResumeGraph()
        self.settings = Settings(default_checkpoint_ns="reactor")
        self._run_store = FakeRunResumeStore(
            [
                RunEventRecord(
                    sequence=1,
                    event_type="run.stream.approval",
                    payload={"approval_status": "pending"},
                )
            ],
            tenant_id="tenant_1",
            user_id="user_1",
        )
        self._approval_store = FakeRunResumeApprovalStore()
        self._tool_store = FakeRunResumeToolProvider()

    def run_store(self) -> FakeRunResumeStore:
        return self._run_store

    def approval_store(self) -> FakeRunResumeApprovalStore:
        return self._approval_store

    def tool_store(self) -> FakeRunResumeToolProvider:
        return self._tool_store


class FakeRunResumeToolProvider:
    async def list_enabled_tool_specs(self, tenant_id: str) -> list[ToolSpec]:
        assert tenant_id == "tenant_1"
        return [
            ToolSpec(
                tenant_id="tenant_1",
                namespace="Webhook",
                name="send",
                description="Send a webhook.",
                risk_level="write",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                catalog_id="tool_1",
            )
        ]


class FakeRunResumeApprovalStore:
    async def find_approval(
        self,
        *,
        tenant_id: str,
        approval_id: str,
    ) -> ApprovalRecord | None:
        if tenant_id != "tenant_1" or approval_id != "approval_1":
            return None
        return ApprovalRecord(
            id="approval_1",
            tenant_id="tenant_1",
            run_id="run_123",
            tool_id="tool_1",
            status="approved",
            requested_by="user_1",
            decided_by="user_1",
            request_payload={
                "runtime": "langgraph",
                "thread_id": "thread_1",
                "checkpoint_ns": "reactor",
                "tool_name": "Webhook:send",
            },
            decision_reason=None,
        )


class FakeRunResumeStore(FakeRunEventsStore):
    def __init__(
        self,
        events: list[RunEventRecord],
        *,
        tenant_id: str,
        user_id: str,
    ) -> None:
        super().__init__(events, tenant_id=tenant_id, user_id=user_id)
        self.completed: list[tuple[RunRecord, Mapping[str, Any]]] = []
        self.session = SessionRunRecord(
            run_id="run_123",
            tenant_id=tenant_id,
            user_id=user_id,
            thread_id="thread_1",
            checkpoint_ns="reactor",
            status="interrupted",
            input_text="hello",
            response_text=None,
            created_at="2026-06-28T00:00:00+00:00",
            updated_at="2026-06-28T00:00:01+00:00",
            metadata={
                "runtime": "langgraph",
                "last_checkpoint_id": "checkpoint_interrupted_1",
            },
        )
        self.resume_claimed = False

    async def claim_interrupted_resume(
        self,
        *,
        run_id: str,
        tenant_id: str,
        approval_id: str,
        claimed_by: str,
        runtime: str,
    ) -> bool:
        assert (run_id, tenant_id, approval_id, claimed_by, runtime) == (
            "run_123",
            "tenant_1",
            "approval_1",
            "user_1",
            "langgraph",
        )
        if self.resume_claimed:
            return False
        self.resume_claimed = True
        return True

    async def record_completed(
        self,
        *,
        result: RunRecord,
        metadata: Mapping[str, Any],
        completion_events: Sequence[RunCompletionEvent] = (),
    ) -> None:
        self.completed.append((result, metadata))
        next_sequence = max((event.sequence for event in self.events), default=0) + 1
        self.events.extend(
            RunEventRecord(
                sequence=next_sequence + offset,
                event_type=event.event_type,
                payload=dict(event.payload),
            )
            for offset, event in enumerate(completion_events)
        )

    async def record_cancelled_if_running(
        self,
        *,
        result: RunRecord,
        metadata: Mapping[str, Any],
    ) -> bool:
        if self.session.status != "running":
            return False
        self.completed.append((result, metadata))
        self.session = replace(
            self.session,
            status=result.status,
            response_text=result.response,
            metadata=metadata,
        )
        self.events.append(
            RunEventRecord(
                sequence=max((event.sequence for event in self.events), default=0) + 1,
                event_type="run.cancelled",
                payload={
                    "status": result.status,
                    "cancelled_by": metadata.get("cancelled_by"),
                    "reason": metadata.get("cancel_reason"),
                },
            )
        )
        return True

    async def record_cancelled_if_active(
        self,
        *,
        result: RunRecord,
        metadata: Mapping[str, Any],
    ) -> bool:
        if self.session.status not in {"running", "interrupted"}:
            return False
        self.session = replace(self.session, status="running")
        return await self.record_cancelled_if_running(result=result, metadata=metadata)

    async def record_event(
        self,
        *,
        run_id: str,
        tenant_id: str,
        sequence: int,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        assert run_id == "run_123"
        assert tenant_id == self.session.tenant_id
        self.events.append(
            RunEventRecord(sequence=sequence, event_type=event_type, payload=dict(payload))
        )


class RecordingResumeGraph:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def ainvoke(self, input: object, config: object | None = None) -> dict[str, object]:
        resume = getattr(input, "resume", None)
        self.calls.append({"resume": resume, "config": config})
        return {"response_text": "resumed answer", "messages": []}


class FakeRunForkContainer(FakeRunEventsContainer):
    def __init__(self) -> None:
        self.graph = RecordingForkGraph()
        self.settings = Settings(default_checkpoint_ns="reactor")
        self._run_store = FakeRunForkStore()
        self.checkpointer = InMemorySaver()
        source_config = langgraph_durable_config(
            tenant_id="tenant_1",
            thread_id="thread_1",
            checkpoint_ns="reactor",
        )
        for checkpoint_id in ("checkpoint_7", "checkpoint_latest"):
            checkpoint = empty_checkpoint()
            checkpoint["id"] = checkpoint_id
            self.checkpointer.put(
                source_config,
                checkpoint,
                {"source": "input", "step": -1, "parents": {}},
                checkpoint["channel_versions"],
            )

    def run_store(self) -> FakeRunForkStore:
        return self._run_store


class FakeRunForkStore(FakeRunEventsStore):
    def __init__(self) -> None:
        super().__init__([], tenant_id="tenant_1", user_id="user_1")
        self.started: dict[str, object] | None = None
        self.completed: list[tuple[RunRecord, Mapping[str, Any]]] = []
        self.session = SessionRunRecord(
            run_id="run_123",
            tenant_id="tenant_1",
            user_id="user_1",
            thread_id="thread_1",
            checkpoint_ns="reactor",
            status="completed",
            input_text="original prompt",
            response_text="original answer",
            created_at="2026-06-28T00:00:00+00:00",
            updated_at="2026-06-28T00:00:01+00:00",
            metadata={"runtime": "langgraph", "personaId": "analyst"},
        )

    async def record_started(
        self,
        *,
        run_id: str,
        tenant_id: str,
        user_id: str,
        thread_id: str,
        checkpoint_ns: str,
        input_text: str,
        metadata: Mapping[str, Any],
    ) -> str:
        self.started = {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "input_text": input_text,
            "metadata": dict(metadata),
        }
        return "queue_fork"

    async def record_completed(self, *, result: RunRecord, metadata: Mapping[str, Any]) -> None:
        self.completed.append((result, metadata))


class RecordingForkGraph:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def ainvoke(self, input: object, config: object | None = None) -> dict[str, object]:
        self.calls.append({"input": input, "config": config})
        return {"response_text": "forked answer", "messages": []}


async def test_a2a_agent_registration_requires_persistence() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        unauthenticated = await client.post(
            "/v1/a2a/agents",
            json={
                "tenantId": "tenant_1",
                "name": "peer-a",
                "endpointUrl": "https://peer.example/a2a",
                "agentCard": {"name": "Peer A", "protocolVersion": "1.0"},
            },
        )
        response = await client.post(
            "/v1/a2a/agents",
            headers=ADMIN_HEADERS,
            json={
                "tenantId": "tenant_1",
                "name": "peer-a",
                "endpointUrl": "https://peer.example/a2a",
                "agentCard": {"name": "Peer A", "protocolVersion": "1.0"},
            },
        )

    assert unauthenticated.status_code == 403
    assert unauthenticated.json()["detail"] == "admin access required"
    assert response.status_code == 503
    assert response.json()["detail"] == "A2A peer registry persistence is not configured"


async def test_a2a_agent_registration_rejects_non_http_endpoint() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/a2a/agents",
            headers=ADMIN_HEADERS,
            json={
                "tenantId": "tenant_1",
                "name": "peer-a",
                "endpointUrl": "file:///tmp/a2a",
                "agentCard": {"name": "Peer A", "protocolVersion": "1.0"},
            },
        )

    assert response.status_code == 422
    assert "endpointUrl must be an absolute http or https URL" in response.text


async def test_a2a_agent_admin_routes_scope_to_principal_tenant() -> None:
    store = FakeA2AAdminStore()
    app = create_app()
    app.state.reactor = FakeA2AAdminContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        registered = await client.post(
            "/v1/a2a/agents",
            headers=ADMIN_HEADERS,
            json={
                "tenantId": "tenant_2",
                "name": "peer-a",
                "endpointUrl": "https://peer.example/a2a",
                "agentCard": {"name": "Peer A", "protocolVersion": "1.0"},
            },
        )
        listed = await client.get("/v1/a2a/agents", headers=ADMIN_HEADERS)
        spoofed_list = await client.get(
            "/v1/a2a/agents",
            params={"tenant_id": "tenant_2"},
            headers=ADMIN_HEADERS,
        )

    assert registered.status_code == 200
    assert registered.json()["tenantId"] == "local"
    assert listed.status_code == 200
    assert [peer["tenantId"] for peer in listed.json()["agents"]] == ["local"]
    assert spoofed_list.status_code == 200
    assert [peer["tenantId"] for peer in spoofed_list.json()["agents"]] == ["local"]


async def test_a2a_access_policy_management_flow() -> None:
    store = FakeA2AAccessPolicyStore()
    app = create_app()
    app.state.reactor = FakeA2AAccessPolicyContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        unauthenticated = await client.put(
            "/v1/a2a/access-policy",
            json={
                "tenantId": "tenant_1",
                "peerAgentId": "peer_1",
                "allowInbound": True,
                "allowOutbound": False,
                "allowedSkills": ["read"],
            },
        )
        missing = await client.get(
            "/v1/a2a/access-policy",
            params={"tenant_id": "tenant_1", "peer_agent_id": "peer_1"},
            headers=ADMIN_HEADERS,
        )
        saved = await client.put(
            "/v1/a2a/access-policy",
            headers=ADMIN_HEADERS,
            json={
                "tenantId": "tenant_1",
                "peerAgentId": "peer_1",
                "allowInbound": True,
                "allowOutbound": False,
                "allowedSkills": ["read"],
            },
        )
        fetched = await client.get(
            "/v1/a2a/access-policy",
            params={"tenant_id": "tenant_1", "peer_agent_id": "peer_1"},
            headers=ADMIN_HEADERS,
        )

    expected = {
        "tenantId": "local",
        "peerAgentId": "peer_1",
        "allowInbound": True,
        "allowOutbound": False,
        "allowedSkills": ["read"],
    }
    assert unauthenticated.status_code == 403
    assert unauthenticated.json()["detail"] == "admin access required"
    assert missing.status_code == 404
    assert missing.json()["detail"] == "A2A access policy not found"
    assert saved.status_code == 200
    assert saved.json() == expected
    assert fetched.status_code == 200
    assert fetched.json() == expected


async def test_a2a_access_policy_admin_routes_scope_to_principal_tenant() -> None:
    store = FakeA2AAccessPolicyStore()
    app = create_app()
    app.state.reactor = FakeA2AAccessPolicyContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        saved = await client.put(
            "/v1/a2a/access-policy",
            headers=ADMIN_HEADERS,
            json={
                "tenantId": "tenant_2",
                "peerAgentId": "peer_1",
                "allowInbound": True,
                "allowOutbound": True,
                "allowedSkills": ["read"],
            },
        )
        fetched = await client.get(
            "/v1/a2a/access-policy",
            params={"tenant_id": "tenant_2", "peer_agent_id": "peer_1"},
            headers=ADMIN_HEADERS,
        )

    expected = {
        "tenantId": "local",
        "peerAgentId": "peer_1",
        "allowInbound": True,
        "allowOutbound": True,
        "allowedSkills": ["read"],
    }
    assert saved.status_code == 200
    assert saved.json() == expected
    assert fetched.status_code == 200
    assert fetched.json() == expected


async def test_a2a_access_policy_management_requires_persistence() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        get_response = await client.get(
            "/v1/a2a/access-policy",
            params={"tenant_id": "tenant_1"},
            headers=ADMIN_HEADERS,
        )
        put_response = await client.put(
            "/v1/a2a/access-policy",
            headers=ADMIN_HEADERS,
            json={"tenantId": "tenant_1", "allowOutbound": True},
        )

    assert get_response.status_code == 503
    assert get_response.json()["detail"] == "A2A access policy persistence is not configured"
    assert put_response.status_code == 503
    assert put_response.json()["detail"] == "A2A access policy persistence is not configured"


async def test_a2a_task_endpoint_requires_persistence() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/a2a/tasks",
            headers=ADMIN_HEADERS,
            json={
                "tenantId": "tenant_1",
                "contextId": "ctx_1",
                "messageId": "msg_1",
                "inputText": "delegate this",
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "A2A task persistence is not configured"


async def test_a2a_task_endpoint_requires_admin_access() -> None:
    store = FakeA2APolicyTaskStore(allow_outbound=True)
    app = create_app()
    app.state.reactor = FakeA2APolicyContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/a2a/tasks",
            json={
                "tenantId": "tenant_1",
                "peerAgentId": "peer_1",
                "contextId": "ctx_1",
                "messageId": "msg_1",
                "inputText": "delegate this",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "admin access required"
    assert store.created_drafts == []


async def test_a2a_task_endpoint_rejects_non_http_push_destination() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/a2a/tasks",
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
            json={
                "tenantId": "tenant_1",
                "contextId": "ctx_1",
                "messageId": "msg_1",
                "inputText": "delegate this",
                "pushDestination": "peer.example/events",
            },
        )

    assert response.status_code == 422
    assert "pushDestination must be an absolute http or https URL" in response.text


async def test_a2a_task_endpoint_enforces_outbound_access_policy() -> None:
    store = FakeA2APolicyTaskStore(allow_outbound=False)
    app = create_app()
    app.state.reactor = FakeA2APolicyContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/a2a/tasks",
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
            json={
                "tenantId": "tenant_1",
                "peerAgentId": "peer_1",
                "contextId": "ctx_1",
                "messageId": "msg_1",
                "inputText": "delegate this",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "A2A outbound access is denied"
    assert store.created_drafts == []


async def test_a2a_task_endpoint_scopes_task_creation_to_admin_principal_tenant() -> None:
    store = FakeA2APolicyTaskStore(allow_outbound=True)
    app = create_app()
    app.state.reactor = FakeA2APolicyContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/a2a/tasks",
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
            json={
                "tenantId": "tenant_2",
                "peerAgentId": "peer_1",
                "contextId": "ctx_1",
                "messageId": "msg_1",
                "inputText": "delegate this",
            },
        )

    assert response.status_code == 200
    assert response.json()["tenantId"] == "tenant_1"
    assert store.created_drafts[0].tenant_id == "tenant_1"
    assert store.created_drafts[0].idempotency_key == "a2a:tenant_1:ctx_1:msg_1"


async def test_a2a_task_metadata_cannot_override_trusted_control_fields() -> None:
    store = FakeA2APolicyTaskStore(allow_outbound=True)
    app = create_app()
    app.state.reactor = FakeA2APolicyContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/a2a/tasks",
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
            json={
                "tenantId": "tenant_2",
                "peerAgentId": "peer_1",
                "contextId": "ctx_1",
                "messageId": "msg_1",
                "skillId": "read",
                "userId": "user_1",
                "inputText": "delegate this",
                "metadata": {
                    "tenantId": "tenant_2",
                    "tenant_id": "tenant_2",
                    "peerAgentId": "peer_2",
                    "skillId": "write",
                    "contextId": "ctx_spoofed",
                    "messageId": "msg_spoofed",
                    "userId": "attacker",
                    "runId": "run_spoofed",
                    "threadId": "thread_spoofed",
                    "sessionId": "session_spoofed",
                    "idempotencyKey": "spoofed",
                    "source": "admin-console",
                },
            },
        )

    assert response.status_code == 200
    draft = store.created_drafts[0]
    assert draft.tenant_id == "tenant_1"
    assert draft.peer_agent_id == "peer_1"
    assert draft.skill_id == "read"
    assert draft.context_id == "ctx_1"
    assert draft.message_id == "msg_1"
    assert draft.user_id == "user_1"
    assert draft.idempotency_key == "a2a:tenant_1:ctx_1:msg_1"
    assert dict(draft.metadata) == {"source": "admin-console"}


async def test_a2a_task_endpoint_enforces_tenant_wide_outbound_access_policy() -> None:
    store = FakeA2APolicyTaskStore(allow_outbound=False, expected_peer_agent_id=None)
    app = create_app()
    app.state.reactor = FakeA2APolicyContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/a2a/tasks",
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
            json={
                "tenantId": "tenant_1",
                "contextId": "ctx_1",
                "messageId": "msg_1",
                "inputText": "delegate without peer",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "A2A outbound access is denied"
    assert store.created_drafts == []


async def test_a2a_task_endpoint_enforces_allowed_skill_policy() -> None:
    store = FakeA2APolicyTaskStore(allow_outbound=True, allowed_skills=["read"])
    app = create_app()
    app.state.reactor = FakeA2APolicyContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        denied = await client.post(
            "/v1/a2a/tasks",
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
            json={
                "tenantId": "tenant_1",
                "peerAgentId": "peer_1",
                "contextId": "ctx_1",
                "messageId": "msg_1",
                "inputText": "delegate this",
                "skillId": "write",
            },
        )
        allowed = await client.post(
            "/v1/a2a/tasks",
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
            json={
                "tenantId": "tenant_1",
                "peerAgentId": "peer_1",
                "contextId": "ctx_2",
                "messageId": "msg_2",
                "inputText": "delegate this",
                "skillId": "read",
            },
        )

    assert denied.status_code == 403
    assert denied.json()["detail"] == "A2A skill is not allowed"
    assert allowed.status_code == 200
    assert [draft.skill_id for draft in store.created_drafts] == ["read"]


async def test_a2a_task_events_endpoint_returns_tenant_scoped_timeline() -> None:
    app = create_app()
    app.state.reactor = FakeA2ATaskEventsContainer()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        unauthenticated = await client.get(
            "/v1/a2a/tasks/task_1/events",
            params={"tenant_id": "tenant_1"},
        )
        task = await client.get(
            "/v1/a2a/tasks/task_1",
            params={"tenant_id": "tenant_2"},
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
        )
        response = await client.get(
            "/v1/a2a/tasks/task_1/events",
            params={"tenant_id": "tenant_2"},
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
        )
        cross_tenant = await client.get(
            "/v1/a2a/tasks/task_1/events",
            params={"tenant_id": "tenant_2"},
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_2"},
        )

    assert unauthenticated.status_code == 403
    assert unauthenticated.json()["detail"] == "admin access required"
    assert task.status_code == 200
    assert task.json()["tenantId"] == "tenant_1"
    assert response.status_code == 200
    assert response.json() == {
        "events": [
            {
                "taskId": "task_1",
                "tenantId": "tenant_1",
                "sequence": 1,
                "eventType": "task.submitted",
                "payload": {"context_id": "ctx_1", "message_id": "msg_1"},
                "createdAt": "2026-06-28T00:00:00Z",
            }
        ]
    }
    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["detail"] == "A2A task not found"


async def test_a2a_task_cancel_endpoint_records_tenant_scoped_cancel_event() -> None:
    app = create_app()
    store = FakeA2ATaskEventsStore()
    app.state.reactor = FakeA2ATaskEventsContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        unauthenticated = await client.post("/v1/a2a/tasks/task_1/cancel")
        response = await client.post(
            "/v1/a2a/tasks/task_1/cancel",
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
            json={"reason": "operator requested"},
        )
        cross_tenant = await client.post(
            "/v1/a2a/tasks/task_1/cancel",
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_2"},
            json={"reason": "should not see task"},
        )

    assert unauthenticated.status_code == 403
    assert response.status_code == 200
    assert response.json()["tenantId"] == "tenant_1"
    assert response.json()["status"] == "cancelled"
    assert response.json()["eventSequence"] == 2
    assert store.cancel_calls == [("tenant_1", "task_1", "admin_1", "operator requested")]
    assert store.events[-1] == {
        "taskId": "task_1",
        "tenantId": "tenant_1",
        "sequence": 2,
        "eventType": "task.cancelled",
        "payload": {"cancelled_by": "admin_1", "reason": "operator requested"},
        "createdAt": "2026-06-28T00:00:01Z",
    }
    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["detail"] == "A2A task not found"


async def test_a2a_task_resume_endpoint_records_tenant_scoped_resume_event() -> None:
    app = create_app()
    store = FakeA2ATaskEventsStore()
    await store.cancel_task(
        tenant_id="tenant_1",
        task_id="task_1",
        cancelled_by="admin_1",
        reason="pause before resume",
    )
    app.state.reactor = FakeA2ATaskEventsContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        unauthenticated = await client.post("/v1/a2a/tasks/task_1/resume")
        response = await client.post(
            "/v1/a2a/tasks/task_1/resume",
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
            json={"reason": "operator resumed"},
        )
        cross_tenant = await client.post(
            "/v1/a2a/tasks/task_1/resume",
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_2"},
            json={"reason": "should not see task"},
        )

    assert unauthenticated.status_code == 403
    assert response.status_code == 200
    assert response.json()["tenantId"] == "tenant_1"
    assert response.json()["status"] == "submitted"
    assert response.json()["eventSequence"] == 3
    assert store.resume_calls == [("tenant_1", "task_1", "admin_1", "operator resumed")]
    assert store.events[-1] == {
        "taskId": "task_1",
        "tenantId": "tenant_1",
        "sequence": 3,
        "eventType": "task.resumed",
        "payload": {"resumed_by": "admin_1", "reason": "operator resumed"},
        "createdAt": "2026-06-28T00:00:02Z",
    }
    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["detail"] == "A2A task not found"


async def test_a2a_task_events_endpoint_requires_persistence() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/a2a/tasks/task_1/events",
            params={"tenant_id": "tenant_1"},
            headers={**ADMIN_HEADERS, "X-Reactor-Tenant-Id": "tenant_1"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "A2A task persistence is not configured"


class FakeA2ATaskEventsContainer:
    settings = Settings()

    def __init__(self, store: FakeA2ATaskEventsStore | None = None) -> None:
        self._store = store or FakeA2ATaskEventsStore()

    def a2a_task_store(self) -> FakeA2ATaskEventsStore:
        return self._store


class FakeA2ATaskEventsStore:
    def __init__(self) -> None:
        self.cancel_calls: list[tuple[str, str, str, str | None]] = []
        self.resume_calls: list[tuple[str, str, str, str | None]] = []
        self.task_status = "submitted"
        self.events: list[dict[str, object]] = [
            {
                "taskId": "task_1",
                "tenantId": "tenant_1",
                "sequence": 1,
                "eventType": "task.submitted",
                "payload": {"context_id": "ctx_1", "message_id": "msg_1"},
                "createdAt": "2026-06-28T00:00:00Z",
            }
        ]

    async def get_task(self, *, tenant_id: str, task_id: str) -> A2ATaskRecord | None:
        if tenant_id != "tenant_1" or task_id != "task_1":
            return None
        return A2ATaskRecord(
            task_id="task_1",
            tenant_id="tenant_1",
            run_id="run_1",
            thread_id="thread_1",
            session_id="session_1",
            context_id="ctx_1",
            message_id="msg_1",
            status=self.task_status,
            event_sequence=len(self.events),
        )

    async def list_task_events(
        self,
        *,
        tenant_id: str,
        task_id: str,
    ) -> list[dict[str, object]] | None:
        if tenant_id != "tenant_1" or task_id != "task_1":
            return None
        return self.events

    async def cancel_task(
        self,
        *,
        tenant_id: str,
        task_id: str,
        cancelled_by: str,
        reason: str | None,
    ) -> A2ATaskRecord | None:
        if tenant_id != "tenant_1" or task_id != "task_1":
            return None
        self.cancel_calls.append((tenant_id, task_id, cancelled_by, reason))
        self.task_status = "cancelled"
        self.events.append(
            {
                "taskId": "task_1",
                "tenantId": "tenant_1",
                "sequence": 2,
                "eventType": "task.cancelled",
                "payload": {"cancelled_by": cancelled_by, "reason": reason},
                "createdAt": "2026-06-28T00:00:01Z",
            }
        )
        return A2ATaskRecord(
            task_id="task_1",
            tenant_id="tenant_1",
            run_id="run_1",
            thread_id="thread_1",
            session_id="session_1",
            context_id="ctx_1",
            message_id="msg_1",
            status="cancelled",
            event_sequence=2,
        )

    async def resume_task(
        self,
        *,
        tenant_id: str,
        task_id: str,
        resumed_by: str,
        reason: str | None,
    ) -> A2ATaskRecord | None:
        if tenant_id != "tenant_1" or task_id != "task_1":
            return None
        self.resume_calls.append((tenant_id, task_id, resumed_by, reason))
        self.task_status = "submitted"
        self.events.append(
            {
                "taskId": "task_1",
                "tenantId": "tenant_1",
                "sequence": len(self.events) + 1,
                "eventType": "task.resumed",
                "payload": {"resumed_by": resumed_by, "reason": reason},
                "createdAt": "2026-06-28T00:00:02Z",
            }
        )
        return A2ATaskRecord(
            task_id="task_1",
            tenant_id="tenant_1",
            run_id="run_1",
            thread_id="thread_1",
            session_id="session_1",
            context_id="ctx_1",
            message_id="msg_1",
            status="submitted",
            event_sequence=len(self.events),
        )


class RecordingLifecyclePublisher:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def publish(self, event: dict[str, object]) -> bool:
        self.events.append(dict(event))
        return True


class FailingLifecyclePublisher:
    async def publish(self, event: dict[str, object]) -> bool:
        _ = event
        raise RuntimeError("fanout unavailable")


class FakeApprovalContainer:
    settings = Settings()

    def __init__(
        self,
        store: FakeApprovalStore,
        *,
        publisher: RecordingLifecyclePublisher | FailingLifecyclePublisher | None = None,
        run_store: object | None = None,
    ) -> None:
        self._store = store
        self._publisher = publisher
        self._run_store = run_store

    def approval_store(self) -> FakeApprovalStore:
        return self._store

    def run_store(self) -> object | None:
        return self._run_store

    def run_lifecycle_publisher(
        self,
    ) -> RecordingLifecyclePublisher | FailingLifecyclePublisher | None:
        return self._publisher


class FakeApprovalRunStore:
    def __init__(self, session: SessionRunRecord | None = None) -> None:
        self.session = session or SessionRunRecord(
            run_id="run_2",
            tenant_id="tenant_1",
            user_id="user_1",
            thread_id="thread_1",
            checkpoint_ns="reactor",
            status="running",
            input_text="hello",
            response_text=None,
            created_at="2026-06-28T00:00:00+00:00",
            updated_at="2026-06-28T00:00:01+00:00",
            metadata={},
        )
        self.find_calls: list[str] = []

    async def find_session(self, *, run_id: str) -> SessionRunRecord | None:
        self.find_calls.append(run_id)
        if run_id != self.session.run_id:
            return None
        return self.session


class FakeApprovalStore:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, str, str, dict[str, object]]] = []
        self.list_calls: list[tuple[str, int, str | None]] = []
        self.decisions: list[tuple[str, str, str, bool]] = []
        self.records = [
            ApprovalRecord(
                id="approval_1",
                tenant_id="tenant_1",
                run_id="run_1",
                tool_id="tool_1",
                status="pending",
                requested_by="user_1",
                decided_by=None,
                request_payload={
                    "action": "write",
                    "idempotency_key": "tool:run_1:tool_1",
                    "input_payload": {"api_key": "sk-test-secret", "url": "https://example.com"},
                    "tool_risk_level": "external_side_effect",
                    "tool_timeout_ms": 15000,
                },
                decision_reason=None,
                created_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
            )
        ]

    async def request_approval(self, request: ApprovalRequest) -> str:
        self.requests.append(
            (
                request.tenant_id,
                request.run_id,
                request.tool_id,
                request.requested_by,
                dict(request.request_payload),
            )
        )
        return "approval_created"

    async def list_pending(self, tenant_id: str, limit: int = 50) -> list[ApprovalRecord]:
        self.list_calls.append((tenant_id, limit, "pending"))
        return [record for record in self.records if record.tenant_id == tenant_id][:limit]

    async def list_approvals(
        self,
        tenant_id: str,
        limit: int = 50,
        status: str | None = None,
    ) -> list[ApprovalRecord]:
        self.list_calls.append((tenant_id, limit, status))
        return [
            record
            for record in self.records
            if record.tenant_id == tenant_id and (status is None or record.status == status)
        ][:limit]

    async def decide_approval(self, decision: ApprovalDecision) -> bool:
        self.decisions.append(
            (
                decision.tenant_id,
                decision.approval_id,
                decision.decided_by,
                decision.approved,
            )
        )
        return decision.tenant_id == "tenant_1" and decision.approval_id == "approval_1"

    async def find_approval(self, *, tenant_id: str, approval_id: str) -> ApprovalRecord | None:
        for record in self.records:
            if record.tenant_id == tenant_id and record.id == approval_id:
                return record
        return None


class FakeA2ARunContainer:
    def __init__(
        self,
        run_store: RecordingA2ARunStore,
        graph: RecordingA2AGraph,
        settings: Settings | None = None,
        a2a_store: object | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self._run_store = run_store
        self.graph = graph
        self._a2a_store = a2a_store

    def run_store(self) -> RecordingA2ARunStore:
        return self._run_store

    def usage_ledger(self) -> None:
        return None

    def a2a_task_store(self) -> object | None:
        return self._a2a_store


class FakeA2AInboundPolicyStore:
    def __init__(self, *, allow_inbound: bool, allowed_skills: list[str] | None = None) -> None:
        self.allow_inbound = allow_inbound
        self.allowed_skills = allowed_skills
        self.checked: list[tuple[str, str | None]] = []
        self.skill_checks: list[tuple[str, str | None, str | None]] = []
        self.sdk_tasks: dict[tuple[str, str], dict[str, object]] = {}

    async def is_inbound_allowed(
        self,
        *,
        tenant_id: str,
        peer_agent_id: str | None,
    ) -> bool:
        self.checked.append((tenant_id, peer_agent_id))
        return self.allow_inbound

    async def is_skill_allowed(
        self,
        *,
        tenant_id: str,
        peer_agent_id: str | None,
        skill_id: str | None,
    ) -> bool:
        self.skill_checks.append((tenant_id, peer_agent_id, skill_id))
        if self.allowed_skills is None or skill_id is None:
            return True
        return skill_id in self.allowed_skills

    async def save_sdk_task(
        self,
        *,
        tenant_id: str,
        task_id: str,
        context_id: str,
        status: str,
        payload: dict[str, object],
    ) -> None:
        _ = context_id, status
        self.sdk_tasks[(tenant_id, task_id)] = dict(payload)

    async def get_sdk_task(self, *, tenant_id: str, task_id: str) -> dict[str, object] | None:
        return self.sdk_tasks.get((tenant_id, task_id))

    async def list_sdk_tasks(
        self,
        *,
        tenant_id: str,
        context_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        matches = [
            task
            for (task_tenant_id, _), task in self.sdk_tasks.items()
            if task_tenant_id == tenant_id
            and (context_id is None or task.get("context_id") == context_id)
        ]
        return matches[:limit]

    async def delete_sdk_task(self, *, tenant_id: str, task_id: str) -> None:
        self.sdk_tasks.pop((tenant_id, task_id), None)


class RecordingA2ARunStore:
    def __init__(self) -> None:
        self.started: dict[str, Any] | None = None

    async def record_started(
        self,
        *,
        run_id: str,
        tenant_id: str,
        user_id: str,
        thread_id: str,
        checkpoint_ns: str,
        input_text: str,
        metadata: Mapping[str, Any],
    ) -> str:
        self.started = {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "input_text": input_text,
            "metadata": dict(metadata),
        }
        return "queue_1"

    async def record_completed(self, *, result: object, metadata: Mapping[str, Any]) -> None:
        return None

    async def record_event(
        self,
        *,
        run_id: str,
        tenant_id: str,
        sequence: int,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        return None

    async def list_events(
        self,
        *,
        run_id: str,
        after_sequence: int = 0,
    ) -> list[RunEventRecord]:
        return []


class RecordingA2AGraph:
    def __init__(self) -> None:
        self.inputs: list[dict[str, Any]] = []

    async def ainvoke(
        self,
        state: Mapping[str, Any],
        config: object | None = None,
    ) -> dict[str, Any]:
        _ = config
        self.inputs.append(dict(state))
        return {"response_text": "a2a persisted answer"}


class FakeA2AAccessPolicyContainer:
    settings = Settings()

    def __init__(self, store: FakeA2AAccessPolicyStore) -> None:
        self._store = store

    def a2a_task_store(self) -> FakeA2AAccessPolicyStore:
        return self._store


class FakeA2AAdminContainer:
    settings = Settings()

    def __init__(self, store: FakeA2AAdminStore) -> None:
        self._store = store

    def a2a_task_store(self) -> FakeA2AAdminStore:
        return self._store


class FakeA2AAdminStore:
    def __init__(self) -> None:
        self.peers: list[A2APeerRecord] = []

    async def register_peer(self, draft: A2APeerDraft) -> A2APeerRecord:
        record = A2APeerRecord(
            peer_agent_id=draft.peer_agent_id,
            tenant_id=draft.tenant_id,
            name=draft.name,
            endpoint_url=draft.endpoint_url,
            agent_card=draft.agent_card,
            enabled=draft.enabled,
        )
        self.peers.append(record)
        return record

    async def list_peers(self, *, tenant_id: str) -> list[A2APeerRecord]:
        return [peer for peer in self.peers if peer.tenant_id == tenant_id]


class FakeA2AAccessPolicyStore:
    def __init__(self) -> None:
        self.policy: A2AAccessPolicyView | None = None

    async def get_access_policy(
        self,
        *,
        tenant_id: str,
        peer_agent_id: str | None,
    ) -> A2AAccessPolicyView | None:
        if self.policy is None:
            return None
        if self.policy.tenant_id != tenant_id or self.policy.peer_agent_id != peer_agent_id:
            return None
        return self.policy

    async def save_access_policy_draft(
        self,
        draft: A2AAccessPolicyDraft,
    ) -> A2AAccessPolicyView:
        self.policy = A2AAccessPolicyView(
            tenant_id=draft.tenant_id,
            peer_agent_id=draft.peer_agent_id,
            allow_inbound=draft.allow_inbound,
            allow_outbound=draft.allow_outbound,
            allowed_skills=draft.allowed_skills,
        )
        return self.policy


class FakeA2APolicyContainer:
    settings = Settings()

    def __init__(self, store: FakeA2APolicyTaskStore) -> None:
        self._store = store

    def a2a_task_store(self) -> FakeA2APolicyTaskStore:
        return self._store


class FakeA2APolicyTaskStore:
    def __init__(
        self,
        *,
        allow_outbound: bool,
        allowed_skills: list[str] | None = None,
        expected_peer_agent_id: str | None = "peer_1",
    ) -> None:
        self.allow_outbound = allow_outbound
        self.allowed_skills = allowed_skills
        self.expected_peer_agent_id = expected_peer_agent_id
        self.created_drafts: list[A2ATaskDraft] = []

    async def is_outbound_allowed(
        self,
        *,
        tenant_id: str,
        peer_agent_id: str | None,
    ) -> bool:
        assert tenant_id == "tenant_1"
        assert peer_agent_id == self.expected_peer_agent_id
        return self.allow_outbound

    async def is_skill_allowed(
        self,
        *,
        tenant_id: str,
        peer_agent_id: str | None,
        skill_id: str | None,
    ) -> bool:
        assert tenant_id == "tenant_1"
        assert peer_agent_id == self.expected_peer_agent_id
        if self.allowed_skills is None or skill_id is None:
            return True
        return skill_id in self.allowed_skills

    async def create_task(self, draft: A2ATaskDraft) -> A2ATaskRecord:
        self.created_drafts.append(draft)
        return A2ATaskRecord(
            task_id=draft.task_id,
            tenant_id=draft.tenant_id,
            run_id=draft.run_id,
            thread_id=draft.thread_id,
            session_id=draft.session_id,
            context_id=draft.context_id,
            message_id=draft.message_id,
            status="submitted",
            event_sequence=1,
        )
