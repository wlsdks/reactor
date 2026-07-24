from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from secrets import token_urlsafe
from typing import Any, cast

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from reactor.agents.checkpoints import Checkpointer, postgres_checkpointer
from reactor.agents.graph import build_reactor_graph, default_tool_handler
from reactor.agents.profiles import default_graph_profile_registry, standard_graph_profile
from reactor.agents.stores import GraphStore, in_memory_graph_store, postgres_graph_store
from reactor.auth.iam import IamExchangeConfig, IamTokenExchangeService
from reactor.auth.jwt import JwtTokenService
from reactor.auth.local_store import InMemoryTokenRevocationStore, InMemoryUserStore
from reactor.cache.response import InMemoryResponseCache, ResponseCacheConfig
from reactor.core.runtime_settings import (
    RuntimeSettingsApplyResult,
    apply_runtime_settings_to_settings,
)
from reactor.core.settings import Settings, database_required_for_runtime
from reactor.evals.judge import AgentEvalLlmJudge, LangChainAgentEvalLlmJudge
from reactor.followup import InMemoryFollowupSuggestionStore
from reactor.guards.input import InputGuard
from reactor.guards.intents import InMemoryIntentRegistry
from reactor.guards.output import OutputGuard
from reactor.migration import targets as migration_targets
from reactor.observability.alerts import AlertScheduler, AlertSchedulerConfig, AsyncAlertEvaluator
from reactor.persistence.a2a_store import SqlAlchemyA2ATaskStore
from reactor.persistence.admin_audit_store import SqlAlchemyAdminAuditStore
from reactor.persistence.agent_spec_store import SqlAlchemyAgentSpecStore
from reactor.persistence.alert_store import SqlAlchemyAlertRuleStore
from reactor.persistence.approval_store import SqlAlchemyApprovalStore
from reactor.persistence.auth_store import (
    SqlAlchemyTokenRevocationStore,
    SqlAlchemyUserIdentityStore,
    SqlAlchemyUserStore,
)
from reactor.persistence.durable_store import SqlAlchemyDurableStore
from reactor.persistence.eval_store import SqlAlchemyEvalCaseStore, SqlAlchemyEvalResultStore
from reactor.persistence.feedback_store import SqlAlchemyFeedbackStore
from reactor.persistence.input_guard_rule_store import SqlAlchemyInputGuardRuleStore
from reactor.persistence.input_guard_stats_store import (
    SqlAlchemyInputGuardMetricSink,
    SqlAlchemyInputGuardStatsQuery,
)
from reactor.persistence.intent_store import SqlAlchemyIntentRegistry
from reactor.persistence.mcp_store import SqlAlchemyMcpRegistryStore
from reactor.persistence.memory_store import SqlAlchemyMemoryStore
from reactor.persistence.migration_source_readers import (
    A2AAccessPolicySourceReader,
    A2AAgentCardSourceReader,
    A2APeerAgentSourceReader,
    A2APushSubscriptionSourceReader,
    A2ATaskEventSourceReader,
    A2ATaskSourceReader,
    AdminAuditSourceReader,
    AgentRunEventSourceReader,
    AgentRunSourceReader,
    AgentSpecSourceReader,
    AlertInstanceSourceReader,
    AlertRuleSourceReader,
    AuthTokenRevocationSourceReader,
    AuthUserSourceReader,
    DeadLetterJobSourceReader,
    EvalCaseSourceReader,
    EvalResultSourceReader,
    FeedbackSourceReader,
    IdempotencyRecordSourceReader,
    InboxEventSourceReader,
    InputGuardMetricSourceReader,
    InputGuardRuleSourceReader,
    IntentDefinitionSourceReader,
    McpAccessPolicySourceReader,
    McpServerSourceReader,
    McpServerStatusSourceReader,
    McpToolSnapshotSourceReader,
    MemoryEmbeddingSourceReader,
    MemoryItemSourceReader,
    MemoryNamespaceSourceReader,
    MemoryProposalSourceReader,
    ModelPricingSourceReader,
    OutboxEventSourceReader,
    OutputGuardRuleAuditSourceReader,
    OutputGuardRuleSourceReader,
    PendingApprovalSourceReader,
    PersonaSourceReader,
    PromptLabExperimentSourceReader,
    PromptLabReportSourceReader,
    PromptLabTrialSourceReader,
    PromptReleaseSourceReader,
    PromptTemplateSourceReader,
    PromptVersionSourceReader,
    RagChunkSourceReader,
    RagDocumentSourceReader,
    RagIngestionCandidateSourceReader,
    RagSourceSourceReader,
    RunQueueSourceReader,
    RuntimeSettingsSourceReader,
    ScheduledJobDeadLetterSourceReader,
    ScheduledJobExecutionSourceReader,
    ScheduledJobSourceReader,
    SlackBotSourceReader,
    SlackFaqRegistrationSourceReader,
    SlackProactiveChannelSourceReader,
    TenantSourceReader,
    ToolCatalogSourceReader,
    ToolInvocationSourceReader,
    UsageLedgerSourceReader,
    UserIdentitySourceReader,
)
from reactor.persistence.migration_store import (
    SqlAlchemyMigrationImportStore,
    SqlAlchemyRollbackSnapshotStore,
)
from reactor.persistence.output_guard_rule_store import (
    SqlAlchemyOutputGuardRuleAuditStore,
    SqlAlchemyOutputGuardRuleStore,
)
from reactor.persistence.persona_store import SqlAlchemyPersonaStore
from reactor.persistence.prompt_lab_store import SqlAlchemyPromptLabStore
from reactor.persistence.prompt_store import SqlAlchemyPromptStore
from reactor.persistence.rag_document_store import SqlAlchemyRagDocumentStore
from reactor.persistence.rag_ingest_store import SqlAlchemyFaqDocumentSink
from reactor.persistence.rag_ingestion_candidate_store import (
    SqlAlchemyRagIngestionCandidateStore,
)
from reactor.persistence.repositories.rag_postgres import PostgresRagRetriever
from reactor.persistence.run_store import SqlAlchemyRunStore
from reactor.persistence.runtime_settings_store import SqlAlchemyRuntimeSettingsStore
from reactor.persistence.scheduler_store import (
    SqlAlchemyScheduledJobDeadLetterStore,
    SqlAlchemyScheduledJobExecutionStore,
    SqlAlchemySchedulerStore,
)
from reactor.persistence.slack_store import (
    SqlAlchemyChannelFaqRegistrationStore,
    SqlAlchemyProactiveChannelStore,
    SqlAlchemySlackBotStore,
)
from reactor.persistence.tenant_store import SqlAlchemyTenantStore
from reactor.persistence.tool_invocation_store import SqlAlchemyToolInvocationStore
from reactor.persistence.tool_store import SqlAlchemyToolStore
from reactor.persistence.usage_ledger_store import (
    SqlAlchemyModelPricingStore,
    SqlAlchemyUsageLedger,
)
from reactor.prompt_lab.service import (
    LangChainPromptLabLlmJudge,
    PromptLabAutoOptimizer,
    PromptLabExecutor,
    PromptLabScheduledJobExecutor,
    PromptLabScheduler,
    PromptLabSchedulerRunner,
    PromptLabSchedulerRunnerConfig,
)
from reactor.providers.chat_models import ChatModelFactory, LangChainChatModelFactory
from reactor.providers.embeddings import LangChainEmbeddingProvider
from reactor.rag.ingestion_policy import RagIngestionPolicyProvider, RagIngestionPolicyStore
from reactor.rag.retriever import RankedChunk, RetrievalQuery
from reactor.rag.tool import (
    RAG_HYBRID_SEARCH_QUALIFIED_NAME,
    RagHybridSearchToolHandler,
    rag_hybrid_search_tool_spec,
)
from reactor.rag.vector_store import AuthorizedLangChainPgVectorStore, LangChainPgVectorStoreFactory
from reactor.runs.lifecycle import RedisRunLifecyclePublisher, RunLifecyclePublisher
from reactor.runs.service import RunService
from reactor.runtime_settings.service import GLOBAL_TENANT_ID, RuntimeSettingsResolver
from reactor.scheduler.worker import (
    SchedulerRunner,
    SchedulerRunnerConfig,
    SchedulerWorker,
    SchedulerWorkerConfig,
)
from reactor.slack.backpressure import SlackBackpressureLimiter
from reactor.slack.faq import InMemorySlackFaqMetrics
from reactor.slack.faq_ingestion import (
    ChannelFaqIngestionService as SlackChannelFaqIngestionService,
)
from reactor.slack.faq_ingestion import HttpSlackHistoryClient
from reactor.slack.faq_responder import SlackChannelFaqResponder
from reactor.slack.feedback import (
    FeedbackButtonHandler,
    InMemoryBotResponseTracker,
    InMemoryFeedbackStore,
    SlackApprovalButtonHandler,
    SlackInteractionHandler,
)
from reactor.slack.rate_limit import InMemorySlackUserRateLimiter, RedisSlackUserRateLimiter
from reactor.slack.reminder import (
    InMemorySlackReminderStore,
    SlackReminderScheduler,
    SlackReminderSchedulerRunner,
)
from reactor.slack.socket_mode import SlackSocketModeGateway, SlackSocketModeSdkRunner
from reactor.slack.worker import (
    ChannelFaqIngestionService,
    ChannelFaqIngestWorker,
    CompositeSlackThreadParticipationTracker,
    HttpSlackAssistantStatusClient,
    HttpSlackMessagingClient,
    HttpSlackResponseUrlClient,
    HttpSlackThreadContextClient,
    InMemorySlackAssistantThreadContextStore,
    InMemorySlackThreadParticipationTracker,
    RunStoreSlackThreadParticipationTracker,
    SlackEventPolicy,
    SlackEventWorker,
    SlackMessagingClient,
    SlackSlashCommandWorker,
)
from reactor.tools.catalog import ToolSpec
from reactor.tools.execution import ToolHandler
from reactor.tools.handlers import RoutedToolHandler
from reactor.workers.outbox_dispatcher import OutboxDispatcher, OutboxWorkerRegistry


class InMemoryMetricIngestionBuffer:
    def __init__(self, events: list[dict[str, object]]) -> None:
        self.events = events

    def publish(self, event: dict[str, object]) -> bool:
        self.events.append(dict(event))
        return True


def sqlalchemy_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def response_cache_from_settings(settings: Settings) -> InMemoryResponseCache | None:
    if not settings.response_cache_enabled:
        return None
    return InMemoryResponseCache(
        ResponseCacheConfig(
            ttl_minutes=settings.response_cache_ttl_minutes,
            max_size=settings.response_cache_max_size,
            semantic_enabled=settings.response_cache_semantic_enabled,
            similarity_threshold=settings.response_cache_similarity_threshold,
            max_candidates=settings.response_cache_max_candidates,
            cacheable_temperature=settings.response_cacheable_temperature,
        )
    )


def default_chat_model(settings: Settings, factory: ChatModelFactory) -> Any:
    return factory.create(
        provider=settings.default_model_provider,
        model=settings.default_model,
    )


def local_auth_settings(settings: Settings) -> Settings:
    if (
        settings.environment.strip().lower() == "local"
        and settings.auth_demo_login_enabled
        and not settings.auth_jwt_secret.strip()
    ):
        return settings.model_copy(update={"auth_jwt_secret": token_urlsafe(32)})
    return settings


def empty_metric_ingestion_events() -> list[dict[str, object]]:
    return []


@dataclass(frozen=True)
class AppContainer:
    settings: Settings
    engine: AsyncEngine | None
    session_factory: async_sessionmaker[AsyncSession] | None
    graph: Any
    checkpointer: Checkpointer | bool | None
    graph_store: GraphStore | None = None
    exit_stack: AsyncExitStack | None = None
    chat_model_factory: ChatModelFactory = field(default_factory=LangChainChatModelFactory)
    _slack_faq_metrics: InMemorySlackFaqMetrics | None = None
    _feedback_store: InMemoryFeedbackStore | SqlAlchemyFeedbackStore | None = None
    _bot_response_tracker: InMemoryBotResponseTracker | None = None
    _response_cache: InMemoryResponseCache | None = None
    _followup_suggestion_store: InMemoryFollowupSuggestionStore | None = None
    _intent_registry: InMemoryIntentRegistry | None = None
    _slack_reminder_store: InMemorySlackReminderStore = field(
        default_factory=InMemorySlackReminderStore
    )
    _slack_user_rate_limiter: InMemorySlackUserRateLimiter | RedisSlackUserRateLimiter | None = None
    _slack_backpressure_limiter: SlackBackpressureLimiter | None = None
    _slack_thread_participation_tracker: Any | None = None
    _slack_assistant_thread_context_store: InMemorySlackAssistantThreadContextStore = field(
        default_factory=InMemorySlackAssistantThreadContextStore
    )
    _rag_ingestion_policy_store: RagIngestionPolicyStore | None = None
    _rag_ingestion_policy_provider: RagIngestionPolicyProvider | None = None
    _rag_vector_store: Any | None = None
    _run_lifecycle_publisher: RunLifecyclePublisher | None = None
    _user_store: InMemoryUserStore | None = None
    _token_revocation_store: InMemoryTokenRevocationStore | None = None
    _metric_ingestion_events: list[dict[str, object]] = field(
        default_factory=empty_metric_ingestion_events
    )

    @classmethod
    def local(
        cls,
        settings: Settings,
        *,
        chat_model_factory: ChatModelFactory | None = None,
    ) -> AppContainer:
        settings = local_auth_settings(settings)
        intent_registry = InMemoryIntentRegistry()
        graph_profile_registry = default_graph_profile_registry()
        actual_chat_model_factory = chat_model_factory or LangChainChatModelFactory()
        graph_store = in_memory_graph_store()
        return cls(
            settings=settings,
            engine=None,
            session_factory=None,
            graph=build_reactor_graph(
                graph_store=graph_store,
                graph_profile=standard_graph_profile(),
                graph_profile_registry=graph_profile_registry,
                intent_registry=intent_registry,
                chat_model=default_chat_model(settings, actual_chat_model_factory)
                if chat_model_factory is not None
                else None,
            ),
            checkpointer=None,
            graph_store=graph_store,
            chat_model_factory=actual_chat_model_factory,
            _response_cache=response_cache_from_settings(settings),
            _intent_registry=intent_registry,
            _user_store=InMemoryUserStore(),
            _token_revocation_store=InMemoryTokenRevocationStore(),
        )

    @classmethod
    async def open(cls, settings: Settings) -> AppContainer:
        database_url = settings.database_url
        if database_url is None or not database_url.strip():
            if database_required_for_runtime(settings):
                raise RuntimeError("database_url is required for durable Reactor runtime")
            return cls.local(settings)

        settings = local_auth_settings(settings)
        engine = create_async_engine(
            sqlalchemy_database_url(database_url),
            pool_pre_ping=True,
        )
        exit_stack = AsyncExitStack()
        try:
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            intent_registry = SqlAlchemyIntentRegistry(session_factory)
            graph_profile_registry = default_graph_profile_registry()
            chat_model_factory = LangChainChatModelFactory()
            checkpointer = await exit_stack.enter_async_context(postgres_checkpointer(database_url))
            graph_store = await exit_stack.enter_async_context(postgres_graph_store(database_url))
            agent_tool_handler = database_agent_tool_handler(settings, session_factory)
            return cls(
                settings=settings,
                engine=engine,
                session_factory=session_factory,
                graph=build_reactor_graph(
                    checkpointer=checkpointer,
                    graph_store=graph_store,
                    input_guard=InputGuard(
                        dynamic_rule_store=SqlAlchemyInputGuardRuleStore(session_factory),
                        runtime_settings_store=SqlAlchemyRuntimeSettingsStore(session_factory),
                        metric_sink=SqlAlchemyInputGuardMetricSink(session_factory),
                    ),
                    output_guard=OutputGuard(
                        dynamic_rule_store=SqlAlchemyOutputGuardRuleStore(session_factory)
                    ),
                    graph_profile=standard_graph_profile(),
                    graph_profile_registry=graph_profile_registry,
                    intent_registry=intent_registry,
                    chat_model=default_chat_model(settings, chat_model_factory),
                    tool_handler=agent_tool_handler,
                    tool_invocation_store=SqlAlchemyToolInvocationStore(session_factory),
                    use_interrupts=True,
                ),
                checkpointer=checkpointer,
                graph_store=graph_store,
                exit_stack=exit_stack,
                chat_model_factory=chat_model_factory,
                _response_cache=response_cache_from_settings(settings),
            )
        except BaseException:
            try:
                await exit_stack.aclose()
            finally:
                await engine.dispose()
            raise

    async def close(self) -> None:
        if self._run_lifecycle_publisher is not None:
            close = getattr(self._run_lifecycle_publisher, "close", None)
            if close is not None:
                await close()
        if self._slack_user_rate_limiter is not None:
            close = getattr(self._slack_user_rate_limiter, "close", None)
            if close is not None:
                await close()
        if self.exit_stack is not None:
            await self.exit_stack.aclose()
        if self.engine is not None:
            await self.engine.dispose()

    def run_store(self) -> SqlAlchemyRunStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyRunStore(self.session_factory)

    def run_lifecycle_publisher(self) -> RunLifecyclePublisher | None:
        if not self.settings.redis_url:
            return None
        if self._run_lifecycle_publisher is None:
            object.__setattr__(
                self,
                "_run_lifecycle_publisher",
                RedisRunLifecyclePublisher(Redis.from_url(self.settings.redis_url)),
            )
        return self._run_lifecycle_publisher

    def durable_store(self) -> SqlAlchemyDurableStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyDurableStore(self.session_factory)

    def outbox_dispatcher(self) -> OutboxDispatcher | None:
        store = self.durable_store()
        if store is None:
            return None
        return OutboxDispatcher(
            store=store,
            registry=OutboxWorkerRegistry(
                slack_event_worker=self.slack_event_worker(),
                slack_command_worker=self.slack_slash_command_worker(),
                slack_faq_ingest_worker=self.slack_channel_faq_ingest_worker(),
                slack_interaction_worker=self.slack_interaction_handler(),
            ),
        )

    def slack_socket_mode_gateway(self) -> SlackSocketModeGateway | None:
        store = self.durable_store()
        if store is None:
            return None
        return SlackSocketModeGateway(
            durable_store=store,
            default_tenant_id=self.settings.auth_default_tenant_id,
        )

    def slack_socket_mode_runner(self) -> SlackSocketModeSdkRunner | None:
        gateway = self.slack_socket_mode_gateway()
        if gateway is None or not self.settings.slack_app_token.strip():
            return None
        return SlackSocketModeSdkRunner(
            app_token=self.settings.slack_app_token,
            gateway=gateway,
        )

    def tool_store(self) -> SqlAlchemyToolStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyToolStore(self.session_factory)

    def response_cache(self) -> InMemoryResponseCache | None:
        return self._response_cache

    def prompt_store(self) -> SqlAlchemyPromptStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyPromptStore(self.session_factory)

    def prompt_lab_store(self) -> SqlAlchemyPromptLabStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyPromptLabStore(self.session_factory)

    def prompt_lab_executor(self) -> PromptLabExecutor | None:
        experiment_store = self.prompt_lab_store()
        prompt_store = self.prompt_store()
        if experiment_store is None or prompt_store is None:
            return None
        return PromptLabExecutor(
            experiment_store=experiment_store,
            prompt_store=prompt_store,
            run_service=RunService(
                self.settings,
                self.run_store(),
                graph=self.graph,
                usage_ledger=self.usage_ledger(),
                tool_provider=self.tool_store(),
                tool_handler=self.agent_tool_handler(),
                tool_invocation_store=self.tool_invocation_store(),
                builtin_tool_specs=self.builtin_tool_specs,
                checkpointer=self.checkpointer,
                graph_store=self.graph_store,
                run_lifecycle_publisher=self.run_lifecycle_publisher(),
                runtime_settings_store=self.runtime_settings_store(),
                approval_store=self.approval_store(),
            ),
            llm_judge=self.prompt_lab_llm_judge(),
        )

    def prompt_lab_llm_judge(self) -> LangChainPromptLabLlmJudge | None:
        if not self.settings.eval_llm_judge_enabled:
            return None
        chat_model = self.chat_model_factory.create(
            provider=self.settings.eval_llm_judge_provider,
            model=self.settings.eval_llm_judge_model,
        )
        return LangChainPromptLabLlmJudge(chat_model)

    def prompt_lab_auto_optimizer(self) -> PromptLabAutoOptimizer | None:
        experiment_store = self.prompt_lab_store()
        prompt_store = self.prompt_store()
        feedback_store = self.feedback_store()
        executor = self.prompt_lab_executor()
        if experiment_store is None or prompt_store is None or executor is None:
            return None
        return PromptLabAutoOptimizer(
            experiment_store=experiment_store,
            prompt_store=prompt_store,
            feedback_store=feedback_store,
            executor=executor,
        )

    def prompt_lab_scheduler_runner(self) -> PromptLabSchedulerRunner | None:
        prompt_store = self.prompt_store()
        optimizer = self.prompt_lab_auto_optimizer()
        if prompt_store is None or optimizer is None:
            return None
        tenant_ids = tuple(self.settings.prompt_lab_scheduler_tenant_ids) or (
            self.settings.auth_default_tenant_id,
        )
        return PromptLabSchedulerRunner(
            scheduler=PromptLabScheduler(
                prompt_store=prompt_store,
                optimizer=optimizer,
                template_ids=self.settings.prompt_lab_scheduler_template_ids,
                candidate_count=self.settings.prompt_lab_scheduler_candidate_count,
                judge_model=(
                    self.settings.prompt_lab_scheduler_judge_model
                    if self.settings.prompt_lab_scheduler_judge_model
                    and self.settings.prompt_lab_scheduler_judge_model.strip()
                    else None
                ),
            ),
            config=PromptLabSchedulerRunnerConfig(
                poll_interval_seconds=self.settings.prompt_lab_scheduler_interval_seconds,
                tenant_ids=tenant_ids,
                user_id=self.settings.prompt_lab_scheduler_user_id,
            ),
        )

    def prompt_lab_scheduled_job_executor(self) -> PromptLabScheduledJobExecutor | None:
        optimizer = self.prompt_lab_auto_optimizer()
        if optimizer is None:
            return None
        return PromptLabScheduledJobExecutor(optimizer)

    def tool_invocation_store(self) -> SqlAlchemyToolInvocationStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyToolInvocationStore(self.session_factory)

    def approval_store(self) -> SqlAlchemyApprovalStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyApprovalStore(self.session_factory)

    def mcp_registry_store(self) -> SqlAlchemyMcpRegistryStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyMcpRegistryStore(self.session_factory)

    def a2a_task_store(self) -> SqlAlchemyA2ATaskStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyA2ATaskStore(self.session_factory, durable_store=self.durable_store())

    def runtime_settings_store(self) -> SqlAlchemyRuntimeSettingsStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyRuntimeSettingsStore(self.session_factory)

    async def effective_settings(
        self,
        *,
        tenant_id: str = GLOBAL_TENANT_ID,
    ) -> RuntimeSettingsApplyResult:
        store = self.runtime_settings_store()
        if store is None:
            return RuntimeSettingsApplyResult(settings=self.settings)

        records = list(await store.list(tenant_id=tenant_id))
        if tenant_id != GLOBAL_TENANT_ID:
            records = [*await store.list(tenant_id=GLOBAL_TENANT_ID), *records]

        return apply_runtime_settings_to_settings(
            self.settings,
            RuntimeSettingsResolver(records),
            tenant_id=tenant_id,
        )

    def rag_ingestion_policy_store(self) -> RagIngestionPolicyStore | None:
        if self._rag_ingestion_policy_store is None:
            settings_store = self.runtime_settings_store()
            if settings_store is None:
                return None
            object.__setattr__(
                self,
                "_rag_ingestion_policy_store",
                RagIngestionPolicyStore(settings_store),
            )
        return self._rag_ingestion_policy_store

    def rag_ingestion_policy_provider(self) -> RagIngestionPolicyProvider | None:
        if self._rag_ingestion_policy_provider is None:
            store = self.rag_ingestion_policy_store()
            if store is None:
                return None
            object.__setattr__(
                self,
                "_rag_ingestion_policy_provider",
                RagIngestionPolicyProvider(self.settings, store),
            )
        return self._rag_ingestion_policy_provider

    def rag_ingestion_candidate_store(self) -> SqlAlchemyRagIngestionCandidateStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyRagIngestionCandidateStore(self.session_factory)

    def admin_audit_store(self) -> SqlAlchemyAdminAuditStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyAdminAuditStore(self.session_factory)

    def agent_spec_store(self) -> SqlAlchemyAgentSpecStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyAgentSpecStore(self.session_factory)

    def persona_store(self) -> SqlAlchemyPersonaStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyPersonaStore(self.session_factory)

    def tenant_store(self) -> SqlAlchemyTenantStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyTenantStore(self.session_factory)

    def slack_bot_store(self) -> SqlAlchemySlackBotStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemySlackBotStore(self.session_factory)

    def proactive_channel_store(self) -> SqlAlchemyProactiveChannelStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyProactiveChannelStore(self.session_factory)

    def channel_faq_registration_store(self) -> SqlAlchemyChannelFaqRegistrationStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyChannelFaqRegistrationStore(self.session_factory)

    def slack_response_url_client(self) -> HttpSlackResponseUrlClient:
        return HttpSlackResponseUrlClient()

    def slack_messaging_client(self) -> SlackMessagingClient | None:
        if not self.settings.slack_bot_token.strip():
            return None
        return HttpSlackMessagingClient(bot_token=self.settings.slack_bot_token)

    def slack_thread_context_client(self) -> HttpSlackThreadContextClient | None:
        if not self.settings.slack_bot_token.strip():
            return None
        return HttpSlackThreadContextClient(bot_token=self.settings.slack_bot_token)

    def slack_assistant_status_client(self) -> HttpSlackAssistantStatusClient | None:
        if not self.settings.slack_bot_token.strip():
            return None
        return HttpSlackAssistantStatusClient(bot_token=self.settings.slack_bot_token)

    def slack_reminder_store(self) -> InMemorySlackReminderStore:
        return self._slack_reminder_store

    def slack_user_rate_limiter(
        self,
    ) -> InMemorySlackUserRateLimiter | RedisSlackUserRateLimiter | None:
        if not self.settings.slack_user_rate_limit_enabled:
            return None
        if self._slack_user_rate_limiter is None:
            backend = self.settings.slack_user_rate_limit_backend.strip().lower()
            if backend == "redis":
                if not self.settings.redis_url:
                    raise ValueError("redis_url is required for Redis Slack user rate limiting")
                limiter: InMemorySlackUserRateLimiter | RedisSlackUserRateLimiter = (
                    RedisSlackUserRateLimiter(
                        redis=Redis.from_url(self.settings.redis_url),
                        max_requests_per_minute=(
                            self.settings.slack_user_rate_limit_max_per_minute
                        ),
                        fail_open=self.settings.slack_user_rate_limit_redis_fail_open,
                    )
                )
            elif backend == "memory":
                limiter = InMemorySlackUserRateLimiter(
                    max_requests_per_window=(self.settings.slack_user_rate_limit_max_per_minute),
                    window_seconds=60.0,
                    max_users=self.settings.slack_user_rate_limit_max_users,
                )
            else:
                raise ValueError(f"Unsupported Slack user rate limit backend: {backend}")
            object.__setattr__(
                self,
                "_slack_user_rate_limiter",
                limiter,
            )
        return self._slack_user_rate_limiter

    def slack_backpressure_limiter(self) -> SlackBackpressureLimiter | None:
        if not self.settings.slack_backpressure_enabled:
            return None
        if self._slack_backpressure_limiter is None:
            object.__setattr__(
                self,
                "_slack_backpressure_limiter",
                SlackBackpressureLimiter(
                    max_concurrent_requests=(
                        self.settings.slack_backpressure_max_concurrent_requests
                    ),
                    request_timeout_seconds=(
                        self.settings.slack_backpressure_request_timeout_seconds
                    ),
                    fail_fast_on_saturation=(
                        self.settings.slack_backpressure_fail_fast_on_saturation
                    ),
                ),
            )
        return self._slack_backpressure_limiter

    def slack_reminder_scheduler(self) -> SlackReminderScheduler | None:
        messaging_client = self.slack_messaging_client()
        if messaging_client is None:
            return None
        return SlackReminderScheduler(
            reminder_store=self.slack_reminder_store(),
            messaging_client=messaging_client,
        )

    def slack_reminder_scheduler_runner(self) -> SlackReminderSchedulerRunner | None:
        scheduler = self.slack_reminder_scheduler()
        if scheduler is None:
            return None
        return SlackReminderSchedulerRunner(
            scheduler=scheduler,
            interval_seconds=self.settings.slack_reminder_scheduler_interval_seconds,
        )

    def slack_slash_command_worker(self) -> SlackSlashCommandWorker:
        return SlackSlashCommandWorker(
            run_service=RunService(
                self.settings,
                self.run_store(),
                graph=self.graph,
                usage_ledger=self.usage_ledger(),
                tool_provider=self.tool_store(),
                tool_handler=self.agent_tool_handler(),
                tool_invocation_store=self.tool_invocation_store(),
                builtin_tool_specs=self.builtin_tool_specs,
                checkpointer=self.checkpointer,
                graph_store=self.graph_store,
                run_lifecycle_publisher=self.run_lifecycle_publisher(),
                runtime_settings_store=self.runtime_settings_store(),
                approval_store=self.approval_store(),
            ),
            response_url_client=self.slack_response_url_client(),
            messaging_client=self.slack_messaging_client(),
            reminder_store=self.slack_reminder_store(),
            rate_limiter=self.slack_user_rate_limiter(),
            backpressure_limiter=self.slack_backpressure_limiter(),
            approval_store=self.approval_store(),
        )

    def slack_event_worker(self) -> SlackEventWorker | None:
        messaging_client = self.slack_messaging_client()
        if messaging_client is None:
            return None
        return SlackEventWorker(
            run_service=RunService(
                self.settings,
                self.run_store(),
                graph=self.graph,
                usage_ledger=self.usage_ledger(),
                tool_provider=self.tool_store(),
                tool_handler=self.agent_tool_handler(),
                tool_invocation_store=self.tool_invocation_store(),
                builtin_tool_specs=self.builtin_tool_specs,
                checkpointer=self.checkpointer,
                graph_store=self.graph_store,
                run_lifecycle_publisher=self.run_lifecycle_publisher(),
                runtime_settings_store=self.runtime_settings_store(),
                approval_store=self.approval_store(),
            ),
            messaging_client=messaging_client,
            faq_responder=self.slack_faq_responder(),
            faq_metrics=self.slack_faq_metrics(),
            rate_limiter=self.slack_user_rate_limiter(),
            backpressure_limiter=self.slack_backpressure_limiter(),
            event_policy=self.slack_event_policy(),
            thread_participation_tracker=self.slack_thread_participation_tracker(),
            thread_context_client=self.slack_thread_context_client(),
            assistant_context_store=self._slack_assistant_thread_context_store,
            assistant_status_client=self.slack_assistant_status_client(),
            approval_store=self.approval_store(),
            bot_response_tracker=self.bot_response_tracker(),
            feedback_store=self.feedback_store(),
        )

    def slack_thread_participation_tracker(self) -> Any:
        if self._slack_thread_participation_tracker is None:
            memory_tracker = InMemorySlackThreadParticipationTracker()
            run_store = self.run_store()
            tracker: Any
            if run_store is None:
                tracker = memory_tracker
            else:
                tracker = CompositeSlackThreadParticipationTracker(
                    memory_tracker,
                    RunStoreSlackThreadParticipationTracker(run_store=run_store),
                )
            object.__setattr__(self, "_slack_thread_participation_tracker", tracker)
        return self._slack_thread_participation_tracker

    def slack_event_policy(self) -> SlackEventPolicy:
        return SlackEventPolicy(
            require_channel_mention=self.settings.slack_require_channel_mention,
            allowed_channel_ids=normalized_slack_ids(self.settings.slack_allowed_channel_ids),
            free_response_channel_ids=normalized_slack_ids(
                self.settings.slack_free_response_channel_ids
            ),
            allowed_user_ids=normalized_slack_ids(self.settings.slack_allowed_user_ids),
        )

    def channel_faq_ingestion_service(self) -> ChannelFaqIngestionService | None:
        sink = self.faq_document_sink()
        if sink is None or not self.settings.slack_bot_token.strip():
            return None
        return SlackChannelFaqIngestionService(
            history_client=HttpSlackHistoryClient(bot_token=self.settings.slack_bot_token),
            document_sink=sink,
        )

    def faq_document_sink(self) -> SqlAlchemyFaqDocumentSink | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyFaqDocumentSink(
            self.session_factory,
            embedding_provider=self.embedding_provider(),
        )

    def rag_document_store(self) -> SqlAlchemyRagDocumentStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyRagDocumentStore(self.session_factory)

    def embedding_provider(self) -> LangChainEmbeddingProvider:
        return LangChainEmbeddingProvider(self.settings)

    def rag_vector_store(self) -> Any | None:
        if not self.settings.database_url:
            return None
        if self._rag_vector_store is None:
            object.__setattr__(
                self,
                "_rag_vector_store",
                AuthorizedLangChainPgVectorStore(
                    LangChainPgVectorStoreFactory().create(
                        self.settings,
                        embeddings=self.embedding_provider().langchain_embeddings(),
                    )
                ),
            )
        return self._rag_vector_store

    def slack_channel_faq_ingest_worker(self) -> ChannelFaqIngestWorker | None:
        store = self.channel_faq_registration_store()
        ingestion_service = self.channel_faq_ingestion_service()
        if store is None or ingestion_service is None:
            return None
        return ChannelFaqIngestWorker(
            registration_store=store,
            ingestion_service=ingestion_service,
        )

    def rag_retriever(self) -> PostgresRagRetriever | None:
        if self.session_factory is None:
            return None
        return PostgresRagRetriever(cast(Any, self.session_factory))

    def builtin_tool_specs(self, tenant_id: str) -> list[ToolSpec]:
        if self.rag_retriever() is None:
            return []
        return [rag_hybrid_search_tool_spec(tenant_id)]

    def agent_tool_handler(self) -> ToolHandler:
        retriever = self.rag_retriever()
        if retriever is None:
            return default_tool_handler
        rag_handler = RagHybridSearchToolHandler(
            retriever,
            LangChainEmbeddingProvider(self.settings),
        )
        return RoutedToolHandler(
            {RAG_HYBRID_SEARCH_QUALIFIED_NAME: rag_handler},
            fallback=default_tool_handler,
        )

    def slack_faq_responder(self) -> SlackChannelFaqResponder | None:
        store = self.channel_faq_registration_store()
        retriever = self.rag_retriever()
        if store is None or retriever is None:
            return None
        return SlackChannelFaqResponder(
            registration_store=store,
            retriever=FaqRetrieverAdapter(retriever),
        )

    def slack_faq_metrics(self) -> InMemorySlackFaqMetrics:
        if self._slack_faq_metrics is None:
            object.__setattr__(self, "_slack_faq_metrics", InMemorySlackFaqMetrics())
        metrics = self._slack_faq_metrics
        if metrics is None:
            raise RuntimeError("slack FAQ metrics were not initialized")
        return metrics

    def feedback_store(self) -> InMemoryFeedbackStore | SqlAlchemyFeedbackStore:
        if self.session_factory is not None:
            return SqlAlchemyFeedbackStore(self.session_factory)
        if self._feedback_store is None:
            object.__setattr__(self, "_feedback_store", InMemoryFeedbackStore())
        store = self._feedback_store
        if store is None:
            raise RuntimeError("feedback store was not initialized")
        return store

    def followup_suggestion_store(self) -> InMemoryFollowupSuggestionStore:
        if self._followup_suggestion_store is None:
            object.__setattr__(
                self,
                "_followup_suggestion_store",
                InMemoryFollowupSuggestionStore(),
            )
        store = self._followup_suggestion_store
        if store is None:
            raise RuntimeError("followup suggestion store was not initialized")
        return store

    def bot_response_tracker(self) -> InMemoryBotResponseTracker:
        if self._bot_response_tracker is None:
            object.__setattr__(self, "_bot_response_tracker", InMemoryBotResponseTracker())
        tracker = self._bot_response_tracker
        if tracker is None:
            raise RuntimeError("bot response tracker was not initialized")
        return tracker

    def slack_feedback_button_handler(self) -> FeedbackButtonHandler | None:
        messaging_client = self.slack_messaging_client()
        if messaging_client is None:
            return None
        return FeedbackButtonHandler(
            feedback_store=self.feedback_store(),
            bot_response_tracker=self.bot_response_tracker(),
            messaging_client=messaging_client,
        )

    def slack_approval_button_handler(self) -> SlackApprovalButtonHandler | None:
        messaging_client = self.slack_messaging_client()
        approval_store = self.approval_store()
        if messaging_client is None or approval_store is None:
            return None
        return SlackApprovalButtonHandler(
            approval_store=approval_store,
            run_service=RunService(
                self.settings,
                self.run_store(),
                graph=self.graph,
                usage_ledger=self.usage_ledger(),
                tool_provider=self.tool_store(),
                tool_handler=self.agent_tool_handler(),
                tool_invocation_store=self.tool_invocation_store(),
                builtin_tool_specs=self.builtin_tool_specs,
                checkpointer=self.checkpointer,
                graph_store=self.graph_store,
                run_lifecycle_publisher=self.run_lifecycle_publisher(),
                runtime_settings_store=self.runtime_settings_store(),
                approval_store=self.approval_store(),
            ),
            messaging_client=messaging_client,
            response_url_client=self.slack_response_url_client(),
        )

    def slack_interaction_handler(self) -> SlackInteractionHandler | None:
        feedback_handler = self.slack_feedback_button_handler()
        if feedback_handler is None:
            return None
        return SlackInteractionHandler(
            feedback_handler=feedback_handler,
            approval_handler=self.slack_approval_button_handler(),
        )

    def scheduler_store(self) -> SqlAlchemySchedulerStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemySchedulerStore(self.session_factory)

    def scheduler_runner(self) -> SchedulerRunner | None:
        job_store = self.scheduler_store()
        execution_store = self.scheduled_job_execution_store()
        if job_store is None or execution_store is None:
            return None
        tenant_ids = tuple(self.settings.scheduler_tenant_ids) or (
            self.settings.auth_default_tenant_id,
        )
        return SchedulerRunner(
            worker=SchedulerWorker(
                job_store=job_store,
                execution_store=execution_store,
                dead_letter_store=self.scheduled_job_dead_letter_store(),
                config=SchedulerWorkerConfig(
                    default_execution_timeout_ms=(
                        self.settings.scheduler_default_execution_timeout_ms
                    ),
                    lease_buffer_ms=self.settings.scheduler_lease_buffer_ms,
                    minimum_lease_ms=self.settings.scheduler_minimum_lease_ms,
                    retry_delay_ms=self.settings.scheduler_retry_delay_ms,
                    max_executions_per_job=self.settings.scheduler_max_executions_per_job,
                ),
            ),
            config=SchedulerRunnerConfig(
                poll_interval_seconds=self.settings.scheduler_poll_interval_seconds,
                lease_owner=self.settings.scheduler_lease_owner,
                tenant_ids=tenant_ids,
            ),
        )

    def eval_case_store(self) -> SqlAlchemyEvalCaseStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyEvalCaseStore(self.session_factory)

    def eval_result_store(self) -> SqlAlchemyEvalResultStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyEvalResultStore(self.session_factory)

    def eval_llm_judge(self) -> AgentEvalLlmJudge | None:
        if not self.settings.eval_llm_judge_enabled:
            return None
        chat_model = self.chat_model_factory.create(
            provider=self.settings.eval_llm_judge_provider,
            model=self.settings.eval_llm_judge_model,
        )
        return LangChainAgentEvalLlmJudge(chat_model)

    def scheduled_job_execution_store(self) -> SqlAlchemyScheduledJobExecutionStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyScheduledJobExecutionStore(self.session_factory)

    def scheduled_job_dead_letter_store(self) -> SqlAlchemyScheduledJobDeadLetterStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyScheduledJobDeadLetterStore(self.session_factory)

    def input_guard_rule_store(self) -> SqlAlchemyInputGuardRuleStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyInputGuardRuleStore(self.session_factory)

    def input_guard_stats_query(self) -> SqlAlchemyInputGuardStatsQuery | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyInputGuardStatsQuery(self.session_factory)

    def intent_registry(self) -> InMemoryIntentRegistry | SqlAlchemyIntentRegistry:
        if self.session_factory is not None:
            return SqlAlchemyIntentRegistry(self.session_factory)
        if self._intent_registry is None:
            object.__setattr__(self, "_intent_registry", InMemoryIntentRegistry())
        registry = self._intent_registry
        if registry is None:
            raise RuntimeError("intent registry was not initialized")
        return registry

    def output_guard_rule_store(self) -> SqlAlchemyOutputGuardRuleStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyOutputGuardRuleStore(self.session_factory)

    def output_guard_rule_audit_store(self) -> SqlAlchemyOutputGuardRuleAuditStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyOutputGuardRuleAuditStore(self.session_factory)

    def user_store(self) -> InMemoryUserStore | SqlAlchemyUserStore | None:
        if self._user_store is not None:
            return self._user_store
        if self.session_factory is None:
            return None
        return SqlAlchemyUserStore(self.session_factory)

    def user_identity_store(self) -> SqlAlchemyUserIdentityStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyUserIdentityStore(self.session_factory)

    def token_revocation_store(
        self,
    ) -> InMemoryTokenRevocationStore | SqlAlchemyTokenRevocationStore | None:
        if self._token_revocation_store is not None:
            return self._token_revocation_store
        if self.session_factory is None:
            return None
        return SqlAlchemyTokenRevocationStore(self.session_factory)

    def memory_store(self) -> SqlAlchemyMemoryStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyMemoryStore(self.session_factory)

    def migration_import_store(self) -> SqlAlchemyMigrationImportStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyMigrationImportStore(self.session_factory)

    def migration_rollback_snapshot_store(self) -> SqlAlchemyRollbackSnapshotStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyRollbackSnapshotStore(self.session_factory)

    def metric_ingestion_buffer(self) -> InMemoryMetricIngestionBuffer:
        return InMemoryMetricIngestionBuffer(self._metric_ingestion_events)

    def migration_target_dispatcher(self) -> migration_targets.MigrationTargetDispatcher | None:
        if self.session_factory is None:
            return None
        return migration_targets.MigrationTargetDispatcher(
            [
                migration_targets.RuntimeSettingsTargetWriter(
                    self.runtime_settings_store_required()
                ),
                migration_targets.PromptTemplateTargetWriter(self.prompt_store_required()),
                migration_targets.PromptVersionTargetWriter(self.prompt_store_required()),
                migration_targets.PromptReleaseTargetWriter(self.prompt_store_required()),
                migration_targets.PersonaTargetWriter(self.persona_store_required()),
                migration_targets.AgentSpecTargetWriter(self.agent_spec_store_required()),
                migration_targets.IntentDefinitionTargetWriter(self.intent_registry()),
                migration_targets.PromptLabExperimentTargetWriter(self.prompt_lab_store_required()),
                migration_targets.PromptLabTrialTargetWriter(self.prompt_lab_store_required()),
                migration_targets.PromptLabReportTargetWriter(self.prompt_lab_store_required()),
                migration_targets.AgentRunTargetWriter(self.run_store_required()),
                migration_targets.AgentRunEventTargetWriter(self.run_store_required()),
                migration_targets.RunQueueTargetWriter(self.durable_store_required()),
                migration_targets.DeadLetterJobTargetWriter(self.durable_store_required()),
                migration_targets.IdempotencyRecordTargetWriter(self.durable_store_required()),
                migration_targets.OutboxEventTargetWriter(self.durable_store_required()),
                migration_targets.InboxEventTargetWriter(self.durable_store_required()),
                migration_targets.SlackBotTargetWriter(self.slack_bot_store_required()),
                migration_targets.ProactiveChannelTargetWriter(
                    self.proactive_channel_store_required()
                ),
                migration_targets.FaqRegistrationTargetWriter(
                    self.channel_faq_registration_store_required()
                ),
                migration_targets.FeedbackTargetWriter(self.feedback_store()),
                migration_targets.EvalCaseTargetWriter(self.eval_case_store_required()),
                migration_targets.EvalResultTargetWriter(self.eval_result_store_required()),
                migration_targets.ScheduledJobTargetWriter(self.scheduler_store_required()),
                migration_targets.ScheduledJobExecutionTargetWriter(
                    self.scheduled_job_execution_store_required()
                ),
                migration_targets.ScheduledJobDeadLetterTargetWriter(
                    self.scheduled_job_dead_letter_store_required()
                ),
                migration_targets.ModelPricingTargetWriter(self.model_pricing_store_required()),
                migration_targets.UsageLedgerTargetWriter(self.usage_ledger_required()),
                migration_targets.TenantTargetWriter(self.tenant_store_required()),
                migration_targets.TenantSloConfigTargetWriter(self.tenant_store_required()),
                migration_targets.AlertRuleTargetWriter(self.alert_rule_store_required()),
                migration_targets.AlertInstanceTargetWriter(self.alert_rule_store_required()),
                migration_targets.AuthUserTargetWriter(self.user_store_required()),
                migration_targets.UserIdentityTargetWriter(self.user_identity_store_required()),
                migration_targets.AuthTokenRevocationTargetWriter(
                    self.token_revocation_store_required()
                ),
                migration_targets.InputGuardRuleTargetWriter(
                    self.input_guard_rule_store_required()
                ),
                migration_targets.InputGuardMetricTargetWriter(
                    SqlAlchemyInputGuardMetricSink(self.session_factory)
                ),
                migration_targets.OutputGuardRuleTargetWriter(
                    self.output_guard_rule_store_required()
                ),
                migration_targets.OutputGuardRuleAuditTargetWriter(
                    self.output_guard_rule_audit_store_required()
                ),
                migration_targets.AdminAuditTargetWriter(self.admin_audit_store_required()),
                migration_targets.ToolCatalogTargetWriter(self.tool_store_required()),
                migration_targets.PendingApprovalTargetWriter(self.approval_store_required()),
                migration_targets.ToolInvocationTargetWriter(self.tool_invocation_store_required()),
                migration_targets.McpServerTargetWriter(self.mcp_registry_store_required()),
                migration_targets.McpServerStatusTargetWriter(self.mcp_registry_store_required()),
                migration_targets.McpToolSnapshotTargetWriter(self.mcp_registry_store_required()),
                migration_targets.McpAccessPolicyTargetWriter(self.mcp_registry_store_required()),
                migration_targets.A2APeerAgentTargetWriter(self.a2a_task_store_required()),
                migration_targets.A2AAgentCardTargetWriter(self.a2a_task_store_required()),
                migration_targets.A2ATaskTargetWriter(self.a2a_task_store_required()),
                migration_targets.A2ATaskEventTargetWriter(self.a2a_task_store_required()),
                migration_targets.A2APushSubscriptionTargetWriter(self.a2a_task_store_required()),
                migration_targets.A2AAccessPolicyTargetWriter(self.a2a_task_store_required()),
                migration_targets.RagSourceTargetWriter(self.faq_document_sink_required()),
                migration_targets.RagDocumentTargetWriter(self.faq_document_sink_required()),
                migration_targets.RagChunkTargetWriter(self.faq_document_sink_required()),
                migration_targets.RagIngestionCandidateTargetWriter(
                    self.rag_ingestion_candidate_store_required()
                ),
                migration_targets.MetricAgentExecutionTargetWriter(self.metric_ingestion_buffer()),
                migration_targets.MetricSessionTargetWriter(self.metric_ingestion_buffer()),
                migration_targets.MetricSpanTargetWriter(self.metric_ingestion_buffer()),
                migration_targets.MetricAuditTrailTargetWriter(self.metric_ingestion_buffer()),
                migration_targets.MetricQuotaEventTargetWriter(self.metric_ingestion_buffer()),
                migration_targets.MetricHitlEventTargetWriter(self.metric_ingestion_buffer()),
                migration_targets.MetricToolCallTargetWriter(self.metric_ingestion_buffer()),
                migration_targets.MetricMcpHealthTargetWriter(self.metric_ingestion_buffer()),
                migration_targets.MetricEvalResultTargetWriter(self.metric_ingestion_buffer()),
                migration_targets.MemoryNamespaceTargetWriter(self.memory_store_required()),
                migration_targets.MemoryItemTargetWriter(self.memory_store_required()),
                migration_targets.MemoryEmbeddingTargetWriter(self.memory_store_required()),
                migration_targets.MemoryProposalTargetWriter(self.memory_store_required()),
            ]
        )

    def required_component(self, component: Any | None, name: str) -> Any:
        if component is None:
            raise RuntimeError(f"{name} is required")
        return component

    def runtime_settings_store_required(self) -> Any:
        return self.required_component(self.runtime_settings_store(), "runtime_settings_store")

    def prompt_store_required(self) -> Any:
        return self.required_component(self.prompt_store(), "prompt_store")

    def persona_store_required(self) -> Any:
        return self.required_component(self.persona_store(), "persona_store")

    def agent_spec_store_required(self) -> Any:
        return self.required_component(self.agent_spec_store(), "agent_spec_store")

    def prompt_lab_store_required(self) -> Any:
        return self.required_component(self.prompt_lab_store(), "prompt_lab_store")

    def run_store_required(self) -> Any:
        return self.required_component(self.run_store(), "run_store")

    def durable_store_required(self) -> Any:
        return self.required_component(self.durable_store(), "durable_store")

    def slack_bot_store_required(self) -> Any:
        return self.required_component(self.slack_bot_store(), "slack_bot_store")

    def proactive_channel_store_required(self) -> Any:
        return self.required_component(self.proactive_channel_store(), "proactive_channel_store")

    def channel_faq_registration_store_required(self) -> Any:
        return self.required_component(
            self.channel_faq_registration_store(),
            "channel_faq_registration_store",
        )

    def eval_case_store_required(self) -> Any:
        return self.required_component(self.eval_case_store(), "eval_case_store")

    def eval_result_store_required(self) -> Any:
        return self.required_component(self.eval_result_store(), "eval_result_store")

    def scheduler_store_required(self) -> Any:
        return self.required_component(self.scheduler_store(), "scheduler_store")

    def scheduled_job_execution_store_required(self) -> Any:
        return self.required_component(
            self.scheduled_job_execution_store(),
            "scheduled_job_execution_store",
        )

    def scheduled_job_dead_letter_store_required(self) -> Any:
        return self.required_component(
            self.scheduled_job_dead_letter_store(),
            "scheduled_job_dead_letter_store",
        )

    def model_pricing_store_required(self) -> Any:
        return self.required_component(self.model_pricing_store(), "model_pricing_store")

    def usage_ledger_required(self) -> Any:
        return self.required_component(self.usage_ledger(), "usage_ledger")

    def tenant_store_required(self) -> Any:
        return self.required_component(self.tenant_store(), "tenant_store")

    def alert_rule_store_required(self) -> Any:
        return self.required_component(self.alert_rule_store(), "alert_rule_store")

    def user_store_required(self) -> Any:
        return self.required_component(self.user_store(), "user_store")

    def user_identity_store_required(self) -> Any:
        return self.required_component(self.user_identity_store(), "user_identity_store")

    def token_revocation_store_required(self) -> Any:
        return self.required_component(self.token_revocation_store(), "token_revocation_store")

    def input_guard_rule_store_required(self) -> Any:
        return self.required_component(self.input_guard_rule_store(), "input_guard_rule_store")

    def output_guard_rule_store_required(self) -> Any:
        return self.required_component(self.output_guard_rule_store(), "output_guard_rule_store")

    def output_guard_rule_audit_store_required(self) -> Any:
        return self.required_component(
            self.output_guard_rule_audit_store(),
            "output_guard_rule_audit_store",
        )

    def admin_audit_store_required(self) -> Any:
        return self.required_component(self.admin_audit_store(), "admin_audit_store")

    def tool_store_required(self) -> Any:
        return self.required_component(self.tool_store(), "tool_store")

    def approval_store_required(self) -> Any:
        return self.required_component(self.approval_store(), "approval_store")

    def tool_invocation_store_required(self) -> Any:
        return self.required_component(self.tool_invocation_store(), "tool_invocation_store")

    def mcp_registry_store_required(self) -> Any:
        return self.required_component(self.mcp_registry_store(), "mcp_registry_store")

    def a2a_task_store_required(self) -> Any:
        return self.required_component(self.a2a_task_store(), "a2a_task_store")

    def faq_document_sink_required(self) -> Any:
        return self.required_component(self.faq_document_sink(), "faq_document_sink")

    def rag_ingestion_candidate_store_required(self) -> Any:
        return self.required_component(
            self.rag_ingestion_candidate_store(),
            "rag_ingestion_candidate_store",
        )

    def memory_store_required(self) -> Any:
        return self.required_component(self.memory_store(), "memory_store")

    def agent_run_source_reader(self) -> AgentRunSourceReader | None:
        if self.session_factory is None:
            return None
        return AgentRunSourceReader(self.session_factory)

    def agent_run_event_source_reader(self) -> AgentRunEventSourceReader | None:
        if self.session_factory is None:
            return None
        return AgentRunEventSourceReader(self.session_factory)

    def run_queue_source_reader(self) -> RunQueueSourceReader | None:
        if self.session_factory is None:
            return None
        return RunQueueSourceReader(self.session_factory)

    def dead_letter_job_source_reader(self) -> DeadLetterJobSourceReader | None:
        if self.session_factory is None:
            return None
        return DeadLetterJobSourceReader(self.session_factory)

    def idempotency_record_source_reader(self) -> IdempotencyRecordSourceReader | None:
        if self.session_factory is None:
            return None
        return IdempotencyRecordSourceReader(self.session_factory)

    def outbox_event_source_reader(self) -> OutboxEventSourceReader | None:
        if self.session_factory is None:
            return None
        return OutboxEventSourceReader(self.session_factory)

    def inbox_event_source_reader(self) -> InboxEventSourceReader | None:
        if self.session_factory is None:
            return None
        return InboxEventSourceReader(self.session_factory)

    def runtime_settings_source_reader(self) -> RuntimeSettingsSourceReader | None:
        if self.session_factory is None:
            return None
        return RuntimeSettingsSourceReader(self.session_factory)

    def prompt_template_source_reader(self) -> PromptTemplateSourceReader | None:
        if self.session_factory is None:
            return None
        return PromptTemplateSourceReader(self.session_factory)

    def prompt_version_source_reader(self) -> PromptVersionSourceReader | None:
        if self.session_factory is None:
            return None
        return PromptVersionSourceReader(self.session_factory)

    def prompt_release_source_reader(self) -> PromptReleaseSourceReader | None:
        if self.session_factory is None:
            return None
        return PromptReleaseSourceReader(self.session_factory)

    def prompt_lab_experiment_source_reader(self) -> PromptLabExperimentSourceReader | None:
        if self.session_factory is None:
            return None
        return PromptLabExperimentSourceReader(self.session_factory)

    def prompt_lab_trial_source_reader(self) -> PromptLabTrialSourceReader | None:
        if self.session_factory is None:
            return None
        return PromptLabTrialSourceReader(self.session_factory)

    def prompt_lab_report_source_reader(self) -> PromptLabReportSourceReader | None:
        if self.session_factory is None:
            return None
        return PromptLabReportSourceReader(self.session_factory)

    def persona_source_reader(self) -> PersonaSourceReader | None:
        if self.session_factory is None:
            return None
        return PersonaSourceReader(self.session_factory)

    def agent_spec_source_reader(self) -> AgentSpecSourceReader | None:
        if self.session_factory is None:
            return None
        return AgentSpecSourceReader(self.session_factory)

    def intent_definition_source_reader(self) -> IntentDefinitionSourceReader | None:
        if self.session_factory is None:
            return None
        return IntentDefinitionSourceReader(self.session_factory)

    def slack_bot_source_reader(self) -> SlackBotSourceReader | None:
        if self.session_factory is None:
            return None
        return SlackBotSourceReader(self.session_factory)

    def slack_proactive_channel_source_reader(self) -> SlackProactiveChannelSourceReader | None:
        if self.session_factory is None:
            return None
        return SlackProactiveChannelSourceReader(self.session_factory)

    def slack_faq_registration_source_reader(self) -> SlackFaqRegistrationSourceReader | None:
        if self.session_factory is None:
            return None
        return SlackFaqRegistrationSourceReader(self.session_factory)

    def feedback_source_reader(self) -> FeedbackSourceReader | None:
        if self.session_factory is None:
            return None
        return FeedbackSourceReader(self.session_factory)

    def eval_case_source_reader(self) -> EvalCaseSourceReader | None:
        if self.session_factory is None:
            return None
        return EvalCaseSourceReader(self.session_factory)

    def eval_result_source_reader(self) -> EvalResultSourceReader | None:
        if self.session_factory is None:
            return None
        return EvalResultSourceReader(self.session_factory)

    def scheduled_job_source_reader(self) -> ScheduledJobSourceReader | None:
        if self.session_factory is None:
            return None
        return ScheduledJobSourceReader(self.session_factory)

    def scheduled_job_execution_source_reader(
        self,
    ) -> ScheduledJobExecutionSourceReader | None:
        if self.session_factory is None:
            return None
        return ScheduledJobExecutionSourceReader(self.session_factory)

    def scheduled_job_dead_letter_source_reader(
        self,
    ) -> ScheduledJobDeadLetterSourceReader | None:
        if self.session_factory is None:
            return None
        return ScheduledJobDeadLetterSourceReader(self.session_factory)

    def model_pricing_source_reader(self) -> ModelPricingSourceReader | None:
        if self.session_factory is None:
            return None
        return ModelPricingSourceReader(self.session_factory)

    def usage_ledger_source_reader(self) -> UsageLedgerSourceReader | None:
        if self.session_factory is None:
            return None
        return UsageLedgerSourceReader(self.session_factory)

    def tenant_source_reader(self) -> TenantSourceReader | None:
        if self.session_factory is None:
            return None
        return TenantSourceReader(self.session_factory)

    def alert_rule_source_reader(self) -> AlertRuleSourceReader | None:
        if self.session_factory is None:
            return None
        return AlertRuleSourceReader(self.session_factory)

    def alert_instance_source_reader(self) -> AlertInstanceSourceReader | None:
        if self.session_factory is None:
            return None
        return AlertInstanceSourceReader(self.session_factory)

    def auth_user_source_reader(self) -> AuthUserSourceReader | None:
        if self.session_factory is None:
            return None
        return AuthUserSourceReader(self.session_factory)

    def user_identity_source_reader(self) -> UserIdentitySourceReader | None:
        if self.session_factory is None:
            return None
        return UserIdentitySourceReader(self.session_factory)

    def auth_token_revocation_source_reader(self) -> AuthTokenRevocationSourceReader | None:
        if self.session_factory is None:
            return None
        return AuthTokenRevocationSourceReader(self.session_factory)

    def input_guard_rule_source_reader(self) -> InputGuardRuleSourceReader | None:
        if self.session_factory is None:
            return None
        return InputGuardRuleSourceReader(self.session_factory)

    def input_guard_metric_source_reader(self) -> InputGuardMetricSourceReader | None:
        if self.session_factory is None:
            return None
        return InputGuardMetricSourceReader(self.session_factory)

    def output_guard_rule_source_reader(self) -> OutputGuardRuleSourceReader | None:
        if self.session_factory is None:
            return None
        return OutputGuardRuleSourceReader(self.session_factory)

    def output_guard_rule_audit_source_reader(self) -> OutputGuardRuleAuditSourceReader | None:
        if self.session_factory is None:
            return None
        return OutputGuardRuleAuditSourceReader(self.session_factory)

    def admin_audit_source_reader(self) -> AdminAuditSourceReader | None:
        if self.session_factory is None:
            return None
        return AdminAuditSourceReader(self.session_factory)

    def tool_catalog_source_reader(self) -> ToolCatalogSourceReader | None:
        if self.session_factory is None:
            return None
        return ToolCatalogSourceReader(self.session_factory)

    def pending_approval_source_reader(self) -> PendingApprovalSourceReader | None:
        if self.session_factory is None:
            return None
        return PendingApprovalSourceReader(self.session_factory)

    def tool_invocation_source_reader(self) -> ToolInvocationSourceReader | None:
        if self.session_factory is None:
            return None
        return ToolInvocationSourceReader(self.session_factory)

    def mcp_server_source_reader(self) -> McpServerSourceReader | None:
        if self.session_factory is None:
            return None
        return McpServerSourceReader(self.session_factory)

    def mcp_server_status_source_reader(self) -> McpServerStatusSourceReader | None:
        if self.session_factory is None:
            return None
        return McpServerStatusSourceReader(self.session_factory)

    def mcp_tool_snapshot_source_reader(self) -> McpToolSnapshotSourceReader | None:
        if self.session_factory is None:
            return None
        return McpToolSnapshotSourceReader(self.session_factory)

    def mcp_access_policy_source_reader(self) -> McpAccessPolicySourceReader | None:
        if self.session_factory is None:
            return None
        return McpAccessPolicySourceReader(self.session_factory)

    def a2a_peer_agent_source_reader(self) -> A2APeerAgentSourceReader | None:
        if self.session_factory is None:
            return None
        return A2APeerAgentSourceReader(self.session_factory)

    def a2a_agent_card_source_reader(self) -> A2AAgentCardSourceReader | None:
        if self.session_factory is None:
            return None
        return A2AAgentCardSourceReader(self.session_factory)

    def a2a_task_source_reader(self) -> A2ATaskSourceReader | None:
        if self.session_factory is None:
            return None
        return A2ATaskSourceReader(self.session_factory)

    def a2a_task_event_source_reader(self) -> A2ATaskEventSourceReader | None:
        if self.session_factory is None:
            return None
        return A2ATaskEventSourceReader(self.session_factory)

    def a2a_push_subscription_source_reader(self) -> A2APushSubscriptionSourceReader | None:
        if self.session_factory is None:
            return None
        return A2APushSubscriptionSourceReader(self.session_factory)

    def a2a_access_policy_source_reader(self) -> A2AAccessPolicySourceReader | None:
        if self.session_factory is None:
            return None
        return A2AAccessPolicySourceReader(self.session_factory)

    def rag_source_source_reader(self) -> RagSourceSourceReader | None:
        if self.session_factory is None:
            return None
        return RagSourceSourceReader(self.session_factory)

    def rag_document_source_reader(self) -> RagDocumentSourceReader | None:
        if self.session_factory is None:
            return None
        return RagDocumentSourceReader(self.session_factory)

    def rag_chunk_source_reader(self) -> RagChunkSourceReader | None:
        if self.session_factory is None:
            return None
        return RagChunkSourceReader(self.session_factory)

    def rag_ingestion_candidate_source_reader(self) -> RagIngestionCandidateSourceReader | None:
        if self.session_factory is None:
            return None
        return RagIngestionCandidateSourceReader(self.session_factory)

    def memory_namespace_source_reader(self) -> MemoryNamespaceSourceReader | None:
        if self.session_factory is None:
            return None
        return MemoryNamespaceSourceReader(self.session_factory)

    def memory_item_source_reader(self) -> MemoryItemSourceReader | None:
        if self.session_factory is None:
            return None
        return MemoryItemSourceReader(self.session_factory)

    def memory_embedding_source_reader(self) -> MemoryEmbeddingSourceReader | None:
        if self.session_factory is None:
            return None
        return MemoryEmbeddingSourceReader(self.session_factory)

    def memory_proposal_source_reader(self) -> MemoryProposalSourceReader | None:
        if self.session_factory is None:
            return None
        return MemoryProposalSourceReader(self.session_factory)

    def model_pricing_store(self) -> SqlAlchemyModelPricingStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyModelPricingStore(self.session_factory)

    def usage_ledger(self) -> SqlAlchemyUsageLedger | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyUsageLedger(self.session_factory)

    def alert_rule_store(self) -> SqlAlchemyAlertRuleStore | None:
        if self.session_factory is None:
            return None
        return SqlAlchemyAlertRuleStore(self.session_factory)

    def alert_scheduler(self) -> AlertScheduler | None:
        store = self.alert_rule_store()
        if store is None:
            return None
        return AlertScheduler(
            AsyncAlertEvaluator(store),
            config=AlertSchedulerConfig(
                interval_seconds=self.settings.alert_scheduler_interval_seconds,
                initial_delay_seconds=self.settings.alert_scheduler_interval_seconds,
            ),
        )

    def iam_token_exchange_service(self) -> IamTokenExchangeService | None:
        if not self.settings.auth_iam_enabled or not self.settings.auth_iam_base_url.strip():
            return None
        user_store = self.user_store()
        if user_store is None or not self.settings.auth_jwt_secret:
            return None
        return IamTokenExchangeService(
            config=IamExchangeConfig.from_settings(self.settings),
            user_store=user_store,
            jwt_tokens=JwtTokenService(
                secret=self.settings.auth_jwt_secret,
                expiration_ms=self.settings.auth_jwt_expiration_ms,
                default_tenant_id=self.settings.auth_default_tenant_id,
            ),
        )


def database_agent_tool_handler(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> ToolHandler:
    return RoutedToolHandler(
        {
            RAG_HYBRID_SEARCH_QUALIFIED_NAME: RagHybridSearchToolHandler(
                PostgresRagRetriever(cast(Any, session_factory)),
                LangChainEmbeddingProvider(settings),
            )
        },
        fallback=default_tool_handler,
    )


def normalized_slack_ids(values: list[str]) -> frozenset[str]:
    return frozenset(value.strip() for value in values if value.strip())


class FaqRetrieverAdapter:
    def __init__(self, retriever: PostgresRagRetriever) -> None:
        self._retriever = retriever

    async def retrieve(self, query: RetrievalQuery) -> list[RankedChunk]:
        return await self._retriever.retrieve(query, [0.0] * 1536)
