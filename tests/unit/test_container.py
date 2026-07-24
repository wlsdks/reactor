from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, cast

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from reactor.core.container import (
    AppContainer,
    database_agent_tool_handler,
    local_auth_settings,
    sqlalchemy_database_url,
)
from reactor.core.settings import Settings
from reactor.guards.intents import IntentDefinition
from reactor.rag.vector_store import AuthorizedLangChainPgVectorStore
from reactor.runs.lifecycle import RedisRunLifecyclePublisher
from reactor.slack.rate_limit import RedisSlackUserRateLimiter
from reactor.tools.handlers import RoutedToolHandler

SLACK_TEST_BOT_TOKEN = "xoxb-test-token"  # noqa: S105


def test_sqlalchemy_database_url_uses_psycopg_driver() -> None:
    assert (
        sqlalchemy_database_url("postgresql://reactor:reactor@localhost:5432/reactor")
        == "postgresql+psycopg://reactor:reactor@localhost:5432/reactor"
    )


def test_database_container_routes_builtin_rag_tool() -> None:
    handler = database_agent_tool_handler(Settings(), cast(Any, object()))

    assert isinstance(handler, RoutedToolHandler)
    assert "Rag:hybrid_search" in handler.route_names


def test_local_container_compiles_graph_without_checkpointer() -> None:
    container = AppContainer.local(Settings(database_url=None))

    assert container.engine is None
    assert container.session_factory is None
    assert container.checkpointer is None
    assert container.graph is not None
    assert container.graph_store is not None
    assert container.graph.store is container.graph_store
    assert container.durable_store() is None
    assert container.outbox_dispatcher() is None
    assert container.slack_socket_mode_gateway() is None
    assert container.slack_socket_mode_runner() is None
    assert container.tool_store() is None
    assert container.prompt_store() is None
    assert container.tool_invocation_store() is None
    assert container.approval_store() is None
    assert container.mcp_registry_store() is None
    assert container.channel_faq_registration_store() is None
    assert container.migration_import_store() is None
    assert container.migration_rollback_snapshot_store() is None
    assert container.migration_target_dispatcher() is None
    assert container.agent_run_source_reader() is None
    assert container.agent_run_event_source_reader() is None
    assert container.run_queue_source_reader() is None
    assert container.dead_letter_job_source_reader() is None
    assert container.idempotency_record_source_reader() is None
    assert container.outbox_event_source_reader() is None
    assert container.inbox_event_source_reader() is None
    assert container.runtime_settings_source_reader() is None
    assert container.prompt_template_source_reader() is None
    assert container.prompt_version_source_reader() is None
    assert container.prompt_release_source_reader() is None
    assert container.prompt_lab_experiment_source_reader() is None
    assert container.prompt_lab_trial_source_reader() is None
    assert container.prompt_lab_report_source_reader() is None
    assert container.persona_source_reader() is None
    assert container.agent_spec_source_reader() is None
    assert container.intent_definition_source_reader() is None
    assert container.slack_bot_source_reader() is None
    assert container.slack_proactive_channel_source_reader() is None
    assert container.slack_faq_registration_source_reader() is None
    assert container.feedback_source_reader() is None
    assert container.eval_case_source_reader() is None
    assert container.eval_result_source_reader() is None
    assert container.scheduled_job_source_reader() is None
    assert container.scheduled_job_execution_source_reader() is None
    assert container.scheduled_job_dead_letter_source_reader() is None
    assert container.model_pricing_source_reader() is None
    assert container.usage_ledger_source_reader() is None
    assert container.alert_rule_source_reader() is None
    assert container.alert_instance_source_reader() is None
    assert container.auth_user_source_reader() is None
    assert container.user_identity_source_reader() is None
    assert container.auth_token_revocation_source_reader() is None
    assert container.input_guard_rule_source_reader() is None
    assert container.input_guard_metric_source_reader() is None
    assert container.input_guard_stats_query() is None
    assert container.output_guard_rule_source_reader() is None
    assert container.output_guard_rule_audit_source_reader() is None
    assert container.admin_audit_source_reader() is None
    assert container.tool_catalog_source_reader() is None
    assert container.pending_approval_source_reader() is None
    assert container.tool_invocation_source_reader() is None
    assert container.mcp_server_source_reader() is None
    assert container.mcp_server_status_source_reader() is None
    assert container.mcp_tool_snapshot_source_reader() is None
    assert container.mcp_access_policy_source_reader() is None
    assert container.a2a_peer_agent_source_reader() is None
    assert container.a2a_agent_card_source_reader() is None
    assert container.a2a_task_source_reader() is None
    assert container.a2a_task_event_source_reader() is None
    assert container.a2a_push_subscription_source_reader() is None
    assert container.a2a_access_policy_source_reader() is None
    assert container.rag_source_source_reader() is None
    assert container.rag_document_source_reader() is None
    assert container.rag_chunk_source_reader() is None
    assert container.rag_ingestion_candidate_source_reader() is None
    assert container.memory_namespace_source_reader() is None
    assert container.memory_item_source_reader() is None
    assert container.memory_embedding_source_reader() is None
    assert container.memory_proposal_source_reader() is None
    assert container.faq_document_sink() is None
    assert container.slack_faq_responder() is None
    assert container.rag_vector_store() is None
    assert container.user_identity_store() is None
    assert container.user_store() is not None
    assert container.token_revocation_store() is not None
    assert container.settings.auth_jwt_secret
    assert container.run_lifecycle_publisher() is None


def test_local_auth_settings_never_invents_a_production_secret() -> None:
    production = Settings(environment="production", auth_jwt_secret="")

    resolved = local_auth_settings(production)

    assert resolved is production
    assert resolved.auth_jwt_secret == ""


async def test_open_container_rejects_missing_required_database() -> None:
    settings = Settings(
        environment="production",
        database_required=True,
        database_url=None,
    )

    with pytest.raises(RuntimeError, match="database_url is required"):
        await AppContainer.open(settings)


async def test_open_container_rejects_blank_required_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_engine_factory(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("blank database_url must fail before engine creation")

    monkeypatch.setattr("reactor.core.container.create_async_engine", fail_engine_factory)

    with pytest.raises(RuntimeError, match="database_url is required"):
        await AppContainer.open(
            Settings(
                environment="production",
                database_required=True,
                database_url="   ",
            )
        )


@pytest.mark.parametrize(
    "startup_error",
    [RuntimeError("graph store unavailable"), asyncio.CancelledError()],
    ids=["runtime-error", "cancelled"],
)
async def test_open_container_cleans_durable_resources_when_graph_store_startup_fails(
    monkeypatch: pytest.MonkeyPatch,
    startup_error: BaseException,
) -> None:
    class FakeEngine:
        def __init__(self) -> None:
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    engine = FakeEngine()
    checkpoint_closed = False

    @asynccontextmanager
    async def fake_checkpointer(_database_url: str):
        nonlocal checkpoint_closed
        try:
            yield object()
        finally:
            checkpoint_closed = True

    @asynccontextmanager
    async def failing_graph_store(_database_url: str):
        raise startup_error
        yield object()

    def fake_engine_factory(*_args: object, **_kwargs: object) -> FakeEngine:
        return engine

    def fake_session_factory(*_args: object, **_kwargs: object) -> object:
        return object()

    monkeypatch.setattr("reactor.core.container.create_async_engine", fake_engine_factory)
    monkeypatch.setattr("reactor.core.container.async_sessionmaker", fake_session_factory)
    monkeypatch.setattr("reactor.core.container.postgres_checkpointer", fake_checkpointer)
    monkeypatch.setattr("reactor.core.container.postgres_graph_store", failing_graph_store)

    with pytest.raises(type(startup_error)):
        await AppContainer.open(
            Settings(database_url="postgresql://reactor:reactor@localhost:5432/reactor")
        )

    assert checkpoint_closed is True
    assert engine.disposed is True


async def test_open_container_disposes_engine_when_session_factory_startup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeEngine:
        def __init__(self) -> None:
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    engine = FakeEngine()

    def fail_session_factory(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("session factory unavailable")

    def fake_engine_factory(*_args: object, **_kwargs: object) -> FakeEngine:
        return engine

    monkeypatch.setattr("reactor.core.container.create_async_engine", fake_engine_factory)
    monkeypatch.setattr("reactor.core.container.async_sessionmaker", fail_session_factory)

    with pytest.raises(RuntimeError, match="session factory unavailable"):
        await AppContainer.open(
            Settings(database_url="postgresql://reactor:reactor@localhost:5432/reactor")
        )

    assert engine.disposed is True


def test_database_container_builds_full_migration_target_dispatcher() -> None:
    container = AppContainer(
        settings=Settings(database_url="postgresql://reactor:reactor@localhost:5432/reactor"),
        engine=None,
        session_factory=cast(Any, object()),
        graph=None,
        checkpointer=None,
    )

    dispatcher = container.migration_target_dispatcher()

    assert dispatcher is not None
    assert set(dispatcher.target_tables) == {
        "a2a_access_policies",
        "a2a_agent_cards",
        "a2a_peer_agents",
        "a2a_push_subscriptions",
        "a2a_task_events",
        "a2a_tasks",
        "admin_audits",
        "agent_eval_cases",
        "agent_eval_results",
        "agent_run_events",
        "agent_runs",
        "agent_specs",
        "alert_instances",
        "alert_rules",
        "auth_token_revocations",
        "channel_faq_registrations",
        "dead_letter_jobs",
        "feedback",
        "idempotency_records",
        "inbox_events",
        "input_guard_rules",
        "intent_definitions",
        "mcp_access_policies",
        "mcp_server_status",
        "mcp_servers",
        "mcp_tool_snapshots",
        "memory_embeddings",
        "memory_items",
        "memory_namespaces",
        "memory_proposals",
        "metric_agent_executions",
        "metric_audit_trail",
        "metric_eval_results",
        "metric_guard_events",
        "metric_hitl_events",
        "metric_mcp_health",
        "metric_quota_events",
        "metric_sessions",
        "metric_spans",
        "metric_tool_calls",
        "model_pricing",
        "outbox_events",
        "output_guard_rule_audits",
        "output_guard_rules",
        "pending_approvals",
        "personas",
        "prompt_lab_experiments",
        "prompt_lab_reports",
        "prompt_lab_trials",
        "prompt_releases",
        "prompt_templates",
        "prompt_versions",
        "rag_chunks",
        "rag_documents",
        "rag_ingestion_candidates",
        "rag_sources",
        "run_queue",
        "runtime_settings",
        "scheduled_job_dead_letters",
        "scheduled_job_executions",
        "scheduled_jobs",
        "slack_bot_instances",
        "slack_proactive_channels",
        "tenant_slo_config",
        "tenants",
        "tool_catalog",
        "tool_invocations",
        "usage_ledger",
        "user_identities",
        "users",
    }


def test_local_container_builds_slack_command_worker() -> None:
    container = AppContainer.local(Settings(database_url=None))

    assert container.slack_response_url_client() is not None
    assert container.slack_messaging_client() is None
    assert container.slack_reminder_store() is container.slack_reminder_store()
    assert container.slack_user_rate_limiter() is container.slack_user_rate_limiter()
    assert container.slack_backpressure_limiter() is container.slack_backpressure_limiter()
    assert container.slack_reminder_scheduler() is None
    assert container.slack_slash_command_worker() is not None
    assert container.slack_event_worker() is None
    assert container.slack_channel_faq_ingest_worker() is None


def test_local_container_can_build_redis_slack_user_rate_limiter() -> None:
    container = AppContainer.local(
        Settings(
            database_url=None,
            redis_url="redis://localhost:6379/0",
            slack_user_rate_limit_backend="redis",
        )
    )

    assert isinstance(container.slack_user_rate_limiter(), RedisSlackUserRateLimiter)


def test_container_builds_redis_run_lifecycle_publisher_when_redis_is_configured() -> None:
    container = AppContainer.local(
        Settings(database_url=None, redis_url="redis://localhost:6379/0")
    )

    publisher = container.run_lifecycle_publisher()

    assert isinstance(publisher, RedisRunLifecyclePublisher)
    assert container.run_lifecycle_publisher() is publisher


async def test_container_close_closes_cached_redis_run_lifecycle_publisher() -> None:
    redis = ClosingRedis()
    publisher = RedisRunLifecyclePublisher(redis)
    container = AppContainer.local(Settings(database_url=None))
    object.__setattr__(container, "_run_lifecycle_publisher", publisher)

    await container.close()

    assert redis.closed is True


async def test_container_close_closes_cached_redis_slack_user_rate_limiter() -> None:
    redis = ClosingRedis()
    limiter = RedisSlackUserRateLimiter(redis=redis)
    container = AppContainer.local(Settings(database_url=None))
    object.__setattr__(container, "_slack_user_rate_limiter", limiter)

    await container.close()

    assert redis.closed is True


def test_local_container_builds_slack_messaging_client_when_bot_token_is_configured() -> None:
    container = AppContainer.local(
        Settings(
            database_url=None,
            slack_bot_token=SLACK_TEST_BOT_TOKEN,
        )
    )

    assert container.slack_messaging_client() is not None
    assert container.slack_thread_context_client() is not None
    assert container.slack_assistant_status_client() is not None
    assert container.slack_reminder_scheduler() is not None
    assert container.slack_event_worker() is not None


def test_container_builds_slack_event_policy_from_settings() -> None:
    container = AppContainer.local(
        Settings(
            database_url=None,
            slack_require_channel_mention=False,
            slack_allowed_channel_ids=[" C1 ", "", "C2"],
            slack_free_response_channel_ids=["C_FREE"],
            slack_allowed_user_ids=[" U1 "],
        )
    )

    policy = container.slack_event_policy()

    assert policy.require_channel_mention is False
    assert policy.allowed_channel_ids == frozenset({"C1", "C2"})
    assert policy.free_response_channel_ids == frozenset({"C_FREE"})
    assert policy.allowed_user_ids == frozenset({"U1"})


def test_container_reuses_slack_thread_participation_tracker() -> None:
    container = AppContainer.local(
        Settings(
            database_url=None,
            slack_bot_token=SLACK_TEST_BOT_TOKEN,
        )
    )

    first_worker = container.slack_event_worker()
    second_worker = container.slack_event_worker()

    assert first_worker is not None
    assert second_worker is not None
    assert first_worker.thread_participation_tracker is second_worker.thread_participation_tracker


def test_container_wires_shared_slack_bot_response_tracker_to_event_worker() -> None:
    container = AppContainer.local(
        Settings(
            database_url=None,
            slack_bot_token=SLACK_TEST_BOT_TOKEN,
        )
    )

    worker = container.slack_event_worker()

    assert worker is not None
    assert worker.bot_response_tracker is container.bot_response_tracker()


def test_container_wires_shared_slack_feedback_store_to_event_worker() -> None:
    container = AppContainer.local(
        Settings(
            database_url=None,
            slack_bot_token=SLACK_TEST_BOT_TOKEN,
        )
    )

    worker = container.slack_event_worker()

    assert worker is not None
    assert worker.feedback_store is container.feedback_store()


async def test_local_container_graph_uses_shared_intent_registry() -> None:
    container = AppContainer.local(Settings(database_url=None))
    await container.intent_registry().save(
        IntentDefinition(
            name="rag_lookup",
            description="RAG lookup",
            keywords=("source",),
            profile="rag",
        )
    )

    result = await container.graph.ainvoke(
        {
            "run_id": "run_test",
            "tenant_id": "tenant_1",
            "user_id": "user_1",
            "messages": [HumanMessage(content="find source")],
            "tool_call_count": 0,
        }
    )

    assert result["graph_profile"] == "rag"
    assert result["active_tools"] == ["Rag:hybrid_search"]
    assert result["response_metadata"]["intent_name"] == "rag_lookup"


async def test_local_container_graph_uses_chat_model_factory_when_injected() -> None:
    factory = RecordingChatModelFactory(FakeChatModel("factory model response"))
    container = AppContainer.local(
        Settings(database_url=None),
        chat_model_factory=factory,
    )

    result = await container.graph.ainvoke(
        {
            "run_id": "run_test",
            "tenant_id": "tenant_1",
            "user_id": "user_1",
            "messages": [HumanMessage(content="hello model")],
            "tool_call_count": 0,
        }
    )

    assert result["response_text"] == "factory model response"
    assert result["response_metadata"]["model_runtime"] == "langchain"
    assert factory.calls == [("openai", "gpt-5-mini")]


def test_container_builds_llm_judges_through_chat_model_factory() -> None:
    factory = RecordingChatModelFactory()
    container = AppContainer.local(
        Settings(database_url=None, eval_llm_judge_enabled=True),
        chat_model_factory=factory,
    )

    assert container.prompt_lab_llm_judge() is not None
    assert container.eval_llm_judge() is not None
    assert factory.calls == [
        ("openai", "gpt-5-mini"),
        ("openai", "gpt-5-mini"),
        ("openai", "gpt-5-mini"),
    ]


def test_container_builds_langchain_pgvector_store_when_database_url_is_configured(
    monkeypatch: Any,
) -> None:
    calls: list[dict[str, object]] = []
    raw_store = object()

    def fake_create(
        self: object,
        settings: Settings,
        *,
        embeddings: object,
        collection_name: str = "reactor_rag",
    ) -> object:
        del self
        calls.append(
            {
                "database_url": settings.database_url,
                "embeddings": embeddings,
                "collection_name": collection_name,
            }
        )
        return raw_store

    monkeypatch.setattr(
        "reactor.core.container.LangChainPgVectorStoreFactory.create",
        fake_create,
    )

    def fake_init_embeddings(model: str, *, provider: str) -> str:
        del model, provider
        return "embeddings"

    monkeypatch.setattr(
        "reactor.providers.embeddings.LANGCHAIN_INIT_EMBEDDINGS",
        fake_init_embeddings,
    )

    container = AppContainer.local(
        Settings(database_url="postgresql://reactor:reactor@localhost:5432/reactor")
    )

    vector_store = container.rag_vector_store()

    assert isinstance(vector_store, AuthorizedLangChainPgVectorStore)
    assert calls == [
        {
            "database_url": "postgresql://reactor:reactor@localhost:5432/reactor",
            "embeddings": "embeddings",
            "collection_name": "reactor_rag",
        }
    ]


class RecordingChatModelFactory:
    def __init__(self, chat_model: object | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._chat_model = chat_model or FakeChatModel("factory response")

    def create(self, *, provider: str, model: str) -> object:
        self.calls.append((provider, model))
        return self._chat_model


class FakeChatModel:
    def __init__(self, response: str) -> None:
        self._response = response

    async def ainvoke(self, input: object, config: object | None = None) -> AIMessage:
        del input, config
        return AIMessage(content=self._response)


class ClosingRedis:
    def __init__(self) -> None:
        self.closed = False

    async def publish(self, channel: str, payload: str) -> int:
        _ = channel, payload
        return 1

    async def eval(self, script: str, numkeys: int, *keys_and_args: object) -> int:
        _ = script, numkeys, keys_and_args
        return 1

    async def aclose(self) -> None:
        self.closed = True
