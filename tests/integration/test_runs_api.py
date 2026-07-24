from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from reactor.agents.runner import RunResult
from reactor.api.app import create_app
from reactor.api.routers import runs as runs_router
from reactor.core.settings import Settings
from reactor.persistence.run_store import SessionRunRecord
from reactor.persistence.tool_invocation_store import ToolInvocationRecord

USER_HEADERS = {
    "X-Reactor-User-Id": "user_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "USER",
}

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}


async def test_runs_openapi_names_operator_next_action_contract() -> None:
    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    schemas = response.json()["components"]["schemas"]
    assert schemas["RunOperatorNextAction"]["required"] == ["id", "label", "command"]
    assert schemas["RunOperatorNextAction"]["properties"]["id"]["type"] == "string"
    assert schemas["RunOperatorNextAction"]["properties"]["label"]["type"] == "string"
    assert schemas["RunOperatorNextAction"]["properties"]["command"]["type"] == "string"
    assert schemas["RunOperatorNextAction"]["properties"]["sourceRunId"]["anyOf"] == [
        {"type": "string"},
        {"type": "null"},
    ]
    assert schemas["RunOperatorNextAction"]["properties"]["threadId"]["anyOf"] == [
        {"type": "string"},
        {"type": "null"},
    ]
    assert schemas["RunOperatorNextAction"]["properties"]["checkpointNs"]["anyOf"] == [
        {"type": "string"},
        {"type": "null"},
    ]
    assert schemas["RunOperatorNextAction"]["properties"]["checkpointId"]["anyOf"] == [
        {"type": "string"},
        {"type": "null"},
    ]
    assert schemas["RunOperatorNextAction"]["properties"]["approvalId"]["anyOf"] == [
        {"type": "string"},
        {"type": "null"},
    ]
    for response_schema in ("RunDetailResponse", "RunOperationResponse", "ForkRunResponse"):
        assert schemas[response_schema]["properties"]["nextActions"]["items"] == {
            "$ref": "#/components/schemas/RunOperatorNextAction"
        }


async def test_run_detail_api_exposes_operator_next_actions() -> None:
    run_store = FakeRunStore(
        [
            session_run(
                "run_1",
                tenant_id="tenant_1",
                user_id="user_1",
                metadata={"last_checkpoint_id": "checkpoint_1"},
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(run_store=run_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/runs/run_1", headers=USER_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["last_checkpoint_id"] == "checkpoint_1"
    assert body["nextActions"] == [
        {
            "id": "diagnose-run",
            "label": "Diagnose the run",
            "command": "reactor-runs diagnose run_1 --output table",
            "sourceRunId": "run_1",
            "threadId": "thread_1",
            "checkpointNs": "reactor",
            "checkpointId": "checkpoint_1",
        },
        {
            "id": "inspect-state-history",
            "label": "Inspect the run's LangGraph checkpoint state history",
            "command": "reactor-admin state-history run_1 --output table",
            "sourceRunId": "run_1",
            "threadId": "thread_1",
            "checkpointNs": "reactor",
            "checkpointId": "checkpoint_1",
        },
        {
            "id": "replay-stream",
            "label": "Replay the run's persisted stream events",
            "command": "reactor-runs replay run_1 --output table",
            "sourceRunId": "run_1",
            "threadId": "thread_1",
            "checkpointNs": "reactor",
            "checkpointId": "checkpoint_1",
        },
        {
            "id": "fork-checkpoint",
            "label": "Fork the run from its latest LangGraph checkpoint",
            "command": (
                "reactor-runs fork run_1 --checkpoint-ns reactor "
                "--checkpoint-id checkpoint_1 --output table"
            ),
            "sourceRunId": "run_1",
            "threadId": "thread_1",
            "checkpointNs": "reactor",
            "checkpointId": "checkpoint_1",
        },
    ]


async def test_run_detail_api_exposes_cancel_action_for_started_run() -> None:
    run_store = FakeRunStore(
        [
            session_run(
                "run_started",
                tenant_id="tenant_1",
                user_id="user_1",
                status="started",
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(run_store=run_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/runs/run_started", headers=USER_HEADERS)

    assert response.status_code == 200
    actions = {action["id"]: action for action in response.json()["nextActions"]}
    assert actions["cancel-run"]["threadId"] == "thread_1"
    assert actions["cancel-run"]["checkpointNs"] == "reactor"
    assert actions["cancel-run"]["command"] == (
        "reactor-runs cancel run_started --reason 'operator requested cancellation' --output table"
    )


async def test_run_detail_api_does_not_offer_checkpoint_fork_for_started_run() -> None:
    run_store = FakeRunStore(
        [
            session_run(
                "run_started",
                tenant_id="tenant_1",
                user_id="user_1",
                status="started",
                metadata={"last_checkpoint_id": "checkpoint_started"},
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(run_store=run_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/runs/run_started", headers=USER_HEADERS)

    assert response.status_code == 200
    action_ids = {action["id"] for action in response.json()["nextActions"]}
    assert "cancel-run" in action_ids
    assert "fork-checkpoint" not in action_ids


async def test_create_run_api_exposes_cancel_action_for_started_run(
    monkeypatch: MonkeyPatch,
) -> None:
    app = create_app()
    app.state.reactor = FakeContainer(run_store=FakeRunStore([]))
    service = FakeRunService(
        RunResult(
            run_id="run_started",
            tenant_id="tenant_1",
            user_id="user_1",
            thread_id="thread_1",
            checkpoint_ns="reactor",
            status="started",
            response="Run accepted.",
            provider="fake",
            model="fake-model",
        )
    )

    def fake_build_run_service(
        container: object,
        run_store: object | None = None,
    ) -> FakeRunService:
        del container, run_store
        return service

    monkeypatch.setattr(runs_router, "build_run_service", fake_build_run_service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs",
            headers=USER_HEADERS,
            json={"message": "start long work"},
        )

    assert response.status_code == 200
    actions = {action["id"]: action for action in response.json()["nextActions"]}
    assert actions["cancel-run"]["threadId"] == "thread_1"
    assert actions["cancel-run"]["checkpointNs"] == "reactor"
    assert actions["cancel-run"]["command"] == (
        "reactor-runs cancel run_started --reason 'operator requested cancellation' --output table"
    )


async def test_create_run_api_uses_configured_usage_ledger(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    usage_ledger = object()

    class RecordingRunService:
        def __init__(self, *_args: object, **kwargs: object) -> None:
            captured.update(kwargs)

        async def create_run(self, _message: str, **kwargs: object) -> RunResult:
            return RunResult(
                run_id="run_usage",
                tenant_id=str(kwargs["tenant_id"]),
                user_id=str(kwargs["user_id"]),
                thread_id="thread_usage",
                checkpoint_ns="reactor",
                status="completed",
                response="Usage tracked.",
                provider="openai",
                model="gpt-5-mini",
            )

    monkeypatch.setattr(runs_router, "RunService", RecordingRunService)
    app = create_app()
    app.state.reactor = FakeContainer(
        run_store=FakeRunStore([]),
        usage_ledger=usage_ledger,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs",
            headers=USER_HEADERS,
            json={"message": "track this run"},
        )

    assert response.status_code == 200
    assert captured["usage_ledger"] is usage_ledger


async def test_fork_run_api_exposes_cancel_action_for_started_fork(
    monkeypatch: MonkeyPatch,
) -> None:
    run_store = FakeRunStore(
        [
            session_run(
                "run_source",
                tenant_id="tenant_1",
                user_id="user_1",
                metadata={"last_checkpoint_id": "checkpoint_1"},
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(run_store=run_store)
    service = FakeRunService(
        RunResult(
            run_id="run_fork_started",
            tenant_id="tenant_1",
            user_id="user_1",
            thread_id="thread_fork",
            checkpoint_ns="reactor",
            status="started",
            response="Fork accepted.",
            provider="fake",
            model="fake-model",
        )
    )

    def fake_build_run_service(
        container: object,
        run_store: object | None = None,
    ) -> FakeRunService:
        del container, run_store
        return service

    monkeypatch.setattr(runs_router, "build_run_service", fake_build_run_service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/run_source/fork",
            headers=USER_HEADERS,
            json={"message": "fork long work", "threadId": "thread_fork"},
        )

    assert response.status_code == 200
    actions = {action["id"]: action for action in response.json()["nextActions"]}
    assert actions["cancel-run"]["threadId"] == "thread_fork"
    assert actions["cancel-run"]["checkpointNs"] == "reactor"
    assert actions["cancel-run"]["command"] == (
        "reactor-runs cancel run_fork_started "
        "--reason 'operator requested cancellation' --output table"
    )


async def test_cancel_run_api_preserves_checkpoint_fork_next_action(
    monkeypatch: MonkeyPatch,
) -> None:
    run_store = FakeRunStore(
        [
            session_run(
                "run_checkpoint",
                tenant_id="tenant_1",
                user_id="user_1",
                status="started",
                metadata={"last_checkpoint_id": "checkpoint_1"},
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(run_store=run_store)
    service = FakeRunService(
        RunResult(
            run_id="run_checkpoint",
            tenant_id="tenant_1",
            user_id="user_1",
            thread_id="thread_1",
            checkpoint_ns="reactor",
            status="cancelled",
            response="Run cancelled.",
            provider="fake",
            model="fake-model",
        )
    )

    def fake_build_run_service(
        container: object,
        run_store: object | None = None,
    ) -> FakeRunService:
        del container, run_store
        return service

    monkeypatch.setattr(runs_router, "build_run_service", fake_build_run_service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/run_checkpoint/cancel",
            headers=USER_HEADERS,
            json={"reason": "operator stop"},
        )

    assert response.status_code == 200
    actions = {action["id"]: action for action in response.json()["nextActions"]}
    assert actions["fork-checkpoint"] == {
        "id": "fork-checkpoint",
        "label": "Fork the run from its latest LangGraph checkpoint",
        "command": (
            "reactor-runs fork run_checkpoint --checkpoint-ns reactor "
            "--checkpoint-id checkpoint_1 --output table"
        ),
        "sourceRunId": "run_checkpoint",
        "threadId": "thread_1",
        "checkpointNs": "reactor",
        "checkpointId": "checkpoint_1",
    }


async def test_resume_run_api_preserves_checkpoint_fork_next_action(
    monkeypatch: MonkeyPatch,
) -> None:
    run_store = FakeRunStore(
        [
            session_run(
                "run_waiting",
                tenant_id="tenant_1",
                user_id="user_1",
                status="waiting_for_approval",
                metadata={"last_checkpoint_id": "checkpoint_approval"},
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(run_store=run_store)
    service = FakeRunService(
        RunResult(
            run_id="run_waiting",
            tenant_id="tenant_1",
            user_id="user_1",
            thread_id="thread_1",
            checkpoint_ns="reactor",
            status="completed",
            response="Resumed.",
            provider="fake",
            model="fake-model",
        )
    )

    def fake_build_run_service(
        container: object,
        run_store: object | None = None,
    ) -> FakeRunService:
        del container, run_store
        return service

    monkeypatch.setattr(runs_router, "build_run_service", fake_build_run_service)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/runs/run_waiting/resume",
            headers=USER_HEADERS,
            json={"approvalId": "approval_1", "approved": True, "reason": "ok"},
        )

    assert response.status_code == 200
    actions = {action["id"]: action for action in response.json()["nextActions"]}
    assert actions["fork-checkpoint"] == {
        "id": "fork-checkpoint",
        "label": "Fork the run from its latest LangGraph checkpoint",
        "command": (
            "reactor-runs fork run_waiting --checkpoint-ns reactor "
            "--checkpoint-id checkpoint_approval --output table"
        ),
        "sourceRunId": "run_waiting",
        "threadId": "thread_1",
        "checkpointNs": "reactor",
        "checkpointId": "checkpoint_approval",
    }


async def test_run_tool_invocations_api_returns_run_scoped_audit_trail() -> None:
    run_store = FakeRunStore(
        [
            session_run("run_1", tenant_id="tenant_1", user_id="user_1"),
            session_run("run_2", tenant_id="tenant_1", user_id="other_user"),
        ]
    )
    tool_store = FakeToolInvocationStore(
        [
            tool_invocation(
                "tool_1",
                run_id="run_1",
                tool_id="Rag:hybrid_search",
                status="succeeded",
                input_payload={
                    "tool": "Rag:hybrid_search",
                    "riskLevel": "read",
                    "approvalRequired": False,
                    "cacheStatus": None,
                    "executed": True,
                    "payload": {"query": "memory"},
                },
                output_payload={"matches": ["doc_1"]},
            ),
            tool_invocation(
                "tool_2",
                run_id="run_1",
                tool_id="Webhook:send",
                status="failed",
                input_payload={
                    "tool": "Webhook:send",
                    "riskLevel": "external_side_effect",
                    "approvalRequired": True,
                    "cacheStatus": None,
                    "executed": False,
                    "payload": {"url": "https://example.com"},
                },
                error_payload={
                    "error": {
                        "code": "approval_required",
                        "message": "approval required for Webhook:send https://example.com/body",
                    }
                },
            ),
            tool_invocation(
                "tool_3",
                run_id="run_1",
                tool_id="Webhook:send",
                status="succeeded",
                input_payload={
                    "tool": "Webhook:send",
                    "riskLevel": "external_side_effect",
                    "approvalRequired": True,
                    "cacheStatus": None,
                    "executed": True,
                    "payload": {"url": "https://output.example.com"},
                },
                output_payload={"body": "private webhook response"},
            ),
            tool_invocation(
                "tool_other",
                tenant_id="tenant_2",
                run_id="run_1",
                tool_id="Other:tool",
                status="succeeded",
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(run_store=run_store, tool_invocation_store=tool_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/v1/runs/run_2/tool-invocations", headers=USER_HEADERS)
        response = await client.get("/v1/runs/run_1/tool-invocations", headers=USER_HEADERS)
        failed_only = await client.get(
            "/v1/runs/run_1/tool-invocations",
            params={"status": "failed"},
            headers=USER_HEADERS,
        )
        invalid_status = await client.get(
            "/v1/runs/run_1/tool-invocations",
            params={"status": "pending"},
            headers=USER_HEADERS,
        )
        admin_response = await client.get(
            "/v1/runs/run_2/tool-invocations",
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "tool_1",
            "runId": "run_1",
            "toolId": "Rag:hybrid_search",
            "status": "succeeded",
            "success": True,
            "approvalId": None,
            "idempotencyKey": "idem_tool_1",
            "requestChecksum": "req_tool_1",
            "resultChecksum": "res_tool_1",
            "execution": {
                "riskLevel": "read",
                "approvalRequired": False,
                "cacheStatus": None,
                "executed": True,
            },
            "input": {"query": "memory"},
            "output": {"matches": ["doc_1"]},
            "error": None,
            "startedAt": "2026-06-26T01:00:00Z",
            "completedAt": "2026-06-26T01:00:00.080000Z",
            "durationMs": 80,
        },
        {
            "id": "tool_2",
            "runId": "run_1",
            "toolId": "Webhook:send",
            "status": "failed",
            "success": False,
            "approvalId": None,
            "idempotencyKey": "idem_tool_2",
            "requestChecksum": "req_tool_2",
            "resultChecksum": "res_tool_2",
            "execution": {
                "riskLevel": "external_side_effect",
                "approvalRequired": True,
                "cacheStatus": None,
                "executed": False,
            },
            "input": {"payloadPresent": True},
            "output": None,
            "error": {
                "error": {
                    "code": "approval_required",
                    "messagePresent": True,
                }
            },
            "startedAt": "2026-06-26T01:00:00Z",
            "completedAt": "2026-06-26T01:00:00.080000Z",
            "durationMs": 80,
        },
        {
            "id": "tool_3",
            "runId": "run_1",
            "toolId": "Webhook:send",
            "status": "succeeded",
            "success": True,
            "approvalId": None,
            "idempotencyKey": "idem_tool_3",
            "requestChecksum": "req_tool_3",
            "resultChecksum": "res_tool_3",
            "execution": {
                "riskLevel": "external_side_effect",
                "approvalRequired": True,
                "cacheStatus": None,
                "executed": True,
            },
            "input": {"payloadPresent": True},
            "output": {"payloadPresent": True},
            "error": None,
            "startedAt": "2026-06-26T01:00:00Z",
            "completedAt": "2026-06-26T01:00:00.080000Z",
            "durationMs": 80,
        },
    ]
    assert failed_only.status_code == 200
    assert [item["id"] for item in failed_only.json()] == ["tool_2"]
    assert "https://example.com" not in response.text
    assert "https://example.com/body" not in response.text
    assert "https://output.example.com" not in response.text
    assert "private webhook response" not in response.text
    assert invalid_status.status_code == 400
    assert (
        invalid_status.json()["detail"]
        == "status must be one of: cancelled, failed, requires_reconciliation, started, succeeded"
    )
    assert admin_response.status_code == 200
    assert tool_store.calls == [
        {"tenant_id": "tenant_1", "run_id": "run_1", "limit": 100, "status": None},
        {"tenant_id": "tenant_1", "run_id": "run_1", "limit": 100, "status": "failed"},
        {"tenant_id": "tenant_1", "run_id": "run_2", "limit": 100, "status": None},
    ]


async def test_run_tool_invocations_api_redacts_secret_shaped_payload_values() -> None:
    run_store = FakeRunStore([session_run("run_1", tenant_id="tenant_1", user_id="user_1")])
    tool_store = FakeToolInvocationStore(
        [
            tool_invocation(
                "tool_1",
                run_id="run_1",
                tool_id="Search:web",
                status="failed",
                input_payload={
                    "tool": "Search:web",
                    "riskLevel": "read",
                    "approvalRequired": False,
                    "cacheStatus": None,
                    "executed": True,
                    "payload": {
                        "query": "investigate api_key=sk-live-1234567890abcdef",
                        "nested": {"github": "ghp_1234567890abcdef1234567890abcdef1234"},
                    },
                },
                output_payload={
                    "summary": "provider returned sk-live-1234567890abcdef",
                },
                error_payload={
                    "message": "denied token ghp_1234567890abcdef1234567890abcdef1234",
                },
            )
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(run_store=run_store, tool_invocation_store=tool_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/runs/run_1/tool-invocations", headers=USER_HEADERS)

    assert response.status_code == 200
    encoded = response.text
    assert "sk-live-1234567890abcdef" not in encoded
    assert "ghp_1234567890abcdef1234567890abcdef1234" not in encoded
    item = response.json()[0]
    assert item["input"]["query"] == "investigate api_key=[REDACTED]"
    assert item["input"]["nested"]["github"] == "[REDACTED]"
    assert item["output"]["summary"] == "provider returned [REDACTED]"
    assert item["error"]["message"] == "denied token [REDACTED]"


def session_run(
    run_id: str,
    *,
    tenant_id: str,
    user_id: str,
    status: str = "completed",
    metadata: dict[str, object] | None = None,
) -> SessionRunRecord:
    return SessionRunRecord(
        run_id=run_id,
        tenant_id=tenant_id,
        user_id=user_id,
        thread_id="thread_1",
        checkpoint_ns="reactor",
        status=status,
        input_text="hello",
        response_text="response",
        created_at="2026-06-26T01:00:00+00:00",
        updated_at="2026-06-26T01:00:01+00:00",
        metadata=metadata or {},
    )


def tool_invocation(
    record_id: str,
    *,
    tenant_id: str = "tenant_1",
    run_id: str = "run_1",
    tool_id: str,
    status: str,
    input_payload: dict[str, object] | None = None,
    output_payload: dict[str, object] | None = None,
    error_payload: dict[str, object] | None = None,
) -> ToolInvocationRecord:
    started_at = datetime(2026, 6, 26, 1, 0, tzinfo=UTC)
    return ToolInvocationRecord(
        id=record_id,
        tenant_id=tenant_id,
        run_id=run_id,
        tool_id=tool_id,
        approval_id=None,
        status=status,
        idempotency_key=f"idem_{record_id}",
        request_checksum=f"req_{record_id}",
        result_checksum=f"res_{record_id}",
        input_payload=input_payload or {},
        output_payload=output_payload,
        error_payload=error_payload,
        started_at=started_at,
        completed_at=started_at + timedelta(milliseconds=80),
    )


class FakeContainer:
    def __init__(
        self,
        *,
        run_store: FakeRunStore,
        tool_invocation_store: FakeToolInvocationStore | None = None,
        usage_ledger: object | None = None,
    ) -> None:
        self.settings = Settings()
        self.graph = None
        self.checkpointer = None
        self.graph_store = None
        self._run_store = run_store
        self._tool_invocation_store = tool_invocation_store
        self._usage_ledger = usage_ledger

    def run_store(self) -> FakeRunStore:
        return self._run_store

    def tool_invocation_store(self) -> FakeToolInvocationStore | None:
        return self._tool_invocation_store

    def usage_ledger(self) -> object | None:
        return self._usage_ledger


class FakeRunStore:
    def __init__(self, runs: list[SessionRunRecord]) -> None:
        self.runs = {run.run_id: run for run in runs}

    async def find_session(self, *, run_id: str) -> SessionRunRecord | None:
        return self.runs.get(run_id)


class FakeRunService:
    def __init__(self, result: RunResult) -> None:
        self.result = result

    async def create_run(self, *args: Any, **kwargs: Any) -> RunResult:
        del args, kwargs
        return self.result

    async def cancel_run(self, *args: Any, **kwargs: Any) -> RunResult:
        del args, kwargs
        return self.result

    async def resume_run(self, *args: Any, **kwargs: Any) -> RunResult:
        del args, kwargs
        return self.result


class FakeToolInvocationStore:
    def __init__(self, records: list[ToolInvocationRecord]) -> None:
        self.records = records
        self.calls: list[dict[str, object]] = []

    async def list_for_run(
        self,
        *,
        tenant_id: str,
        run_id: str,
        limit: int = 100,
        status: str | None = None,
    ) -> list[ToolInvocationRecord]:
        self.calls.append(
            {"tenant_id": tenant_id, "run_id": run_id, "limit": limit, "status": status}
        )
        return [
            record
            for record in self.records
            if record.tenant_id == tenant_id
            and record.run_id == run_id
            and (status is None or record.status == status)
        ][:limit]
