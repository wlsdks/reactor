from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app
from reactor.core.settings import Settings
from reactor.observability.pricing import ModelPricing
from reactor.persistence.run_store import RunEventRecord, SessionListRecord, SessionRunRecord


async def test_sessions_require_authenticated_user_context() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/sessions")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing authenticated user context"


async def test_sessions_list_detail_export_and_delete_owned_session() -> None:
    run_store = FakeRunStore()
    run_store.sessions["run_1"] = session_record("run_1", user_id="user_1")
    app = create_app()
    app.state.reactor = FakeContainer(run_store)
    transport = ASGITransport(app=app)
    headers = {
        "X-Reactor-User-Id": "user_1",
        "X-Reactor-Tenant-Id": "tenant_1",
    }

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        listed = await client.get("/api/sessions", headers=headers)
        detail = await client.get("/v1/sessions/run_1", headers=headers)
        exported = await client.get("/api/sessions/run_1/export", headers=headers)
        markdown = await client.get(
            "/api/sessions/run_1/export",
            params={"format": "markdown"},
            headers=headers,
        )
        deleted = await client.delete("/v1/sessions/run_1", headers=headers)

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["sessionId"] == "run_1"
    assert detail.status_code == 200
    assert detail.json()["messages"][0]["role"] == "user"
    assert detail.json()["metadata"] == {
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
    }
    assert exported.status_code == 200
    assert exported.json()["messages"][1]["role"] == "assistant"
    assert markdown.status_code == 200
    assert "# Conversation: run_1" in markdown.text
    assert deleted.status_code == 204
    assert "run_1" not in run_store.sessions


async def test_sessions_deny_cross_user_access_unless_admin() -> None:
    run_store = FakeRunStore()
    run_store.sessions["run_1"] = session_record("run_1", user_id="owner_1")
    app = create_app()
    app.state.reactor = FakeContainer(run_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        denied = await client.get(
            "/api/sessions/run_1",
            headers={"X-Reactor-User-Id": "other_1", "X-Reactor-Tenant-Id": "tenant_1"},
        )
        admin = await client.get(
            "/api/sessions/run_1",
            headers={
                "X-Reactor-User-Id": "admin_1",
                "X-Reactor-Tenant-Id": "tenant_1",
                "X-Reactor-Role": "ADMIN",
            },
        )

    assert denied.status_code == 403
    assert denied.json()["detail"] == "Access denied to session"
    assert admin.status_code == 200


async def test_models_endpoint_lists_configured_provider_contract() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(None, settings=Settings())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/models")

    assert response.status_code == 200
    assert response.json()["defaultModel"] == "openai"
    assert response.json()["models"][0] == {"name": "openai", "isDefault": True}


async def test_models_endpoint_reads_provider_list_from_pricing_registry() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(
        None,
        settings=Settings(default_model_provider="anthropic", default_model="claude-sonnet-5"),
        model_pricing_store=FakeModelPricingStore(
            [
                model_pricing("pricing_openai", "openai", "gpt-5-mini"),
                model_pricing(
                    "pricing_anthropic",
                    "anthropic",
                    "claude-sonnet-5",
                    prompt="3.00",
                    completion="15.00",
                ),
            ]
        ),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/v1/models")

    assert response.status_code == 200
    assert response.json() == {
        "defaultModel": "anthropic",
        "models": [
            {"name": "anthropic", "isDefault": True},
            {"name": "openai", "isDefault": False},
        ],
    }


class FakeContainer:
    def __init__(
        self,
        run_store: FakeRunStore | None,
        *,
        settings: Settings | None = None,
        model_pricing_store: FakeModelPricingStore | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self._run_store = run_store
        self._model_pricing_store = model_pricing_store

    def run_store(self) -> FakeRunStore | None:
        return self._run_store

    def model_pricing_store(self) -> FakeModelPricingStore | None:
        return self._model_pricing_store


class FakeRunStore:
    def __init__(self) -> None:
        self.sessions: dict[str, SessionRunRecord] = {}

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
        raise NotImplementedError

    async def record_completed(
        self,
        *,
        result: object,
        metadata: Mapping[str, Any],
    ) -> None:
        raise NotImplementedError

    async def record_event(
        self,
        *,
        run_id: str,
        tenant_id: str,
        sequence: int,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        raise NotImplementedError

    async def list_events(
        self,
        *,
        run_id: str,
        after_sequence: int = 0,
    ) -> list[RunEventRecord]:
        return []

    async def list_sessions(
        self,
        *,
        tenant_id: str,
        user_id: str,
        limit: int,
        offset: int,
    ) -> SessionListRecord:
        items = [
            session
            for session in self.sessions.values()
            if session.tenant_id == tenant_id and session.user_id == user_id
        ]
        return SessionListRecord(items=items[offset : offset + limit], total=len(items))

    async def find_session(self, *, run_id: str) -> SessionRunRecord | None:
        return self.sessions.get(run_id)

    async def delete_session(self, *, run_id: str) -> bool:
        return self.sessions.pop(run_id, None) is not None


class FakeModelPricingStore:
    def __init__(self, records: list[ModelPricing]) -> None:
        self.records = records

    async def find_all(self) -> list[ModelPricing]:
        return self.records


def session_record(run_id: str, *, user_id: str) -> SessionRunRecord:
    return SessionRunRecord(
        run_id=run_id,
        tenant_id="tenant_1",
        user_id=user_id,
        thread_id="thread_1",
        checkpoint_ns="reactor",
        status="completed",
        input_text="hello",
        response_text="hi there",
        created_at="2026-06-27T00:00:00+00:00",
        updated_at="2026-06-27T00:00:01+00:00",
        metadata={
            "state_schema_version": "reactor.agent.state.v1",
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


def model_pricing(
    pricing_id: str,
    provider: str,
    model: str,
    *,
    prompt: str = "1.00",
    completion: str = "2.00",
) -> ModelPricing:
    return ModelPricing(
        id=pricing_id,
        provider=provider,
        model=model,
        prompt_price_per_1m=Decimal(prompt),
        completion_price_per_1m=Decimal(completion),
        effective_from=datetime(2026, 6, 1, tzinfo=UTC),
    )
