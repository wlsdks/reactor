from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="REACTOR_",
        extra="ignore",
    )

    app_name: str = "Reactor"
    environment: str = "local"
    host: str = "127.0.0.1"
    port: int = 8000
    external_base_url: str = ""
    reload: bool = False
    strict_msgpack: bool = True
    api_replica_count: int = Field(default=1, ge=0)
    worker_replica_count: int = Field(default=1, ge=0)

    database_url: str | None = None
    database_required: bool = False
    redis_url: str | None = None
    redis_required: bool = False
    response_cache_enabled: bool = False
    response_cache_ttl_minutes: int = Field(default=0, ge=0)
    response_cache_max_size: int = Field(default=1024, gt=0)
    response_cache_semantic_enabled: bool = False
    response_cache_similarity_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    response_cache_max_candidates: int = Field(default=0, ge=0)
    response_cacheable_temperature: float = Field(default=0.0, ge=0.0)

    default_thread_id: str = "local-thread"
    default_checkpoint_ns: str = "reactor"
    default_model_provider: str = "openai"
    default_model: str = "gpt-5-mini"
    default_embedding_provider: str = "openai"
    default_embedding_model: str = "text-embedding-3-small"
    max_output_tokens: int = Field(default=4096, gt=0)
    max_tool_calls: int = Field(default=10, ge=0, le=100)
    agent_run_timeout_ms: int = Field(default=120_000, ge=1)
    multimodal_enabled: bool = True
    multimodal_max_files_per_request: int = Field(default=5, gt=0)
    multimodal_max_file_size_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    rag_ingestion_enabled: bool = True
    rag_ingestion_require_review: bool = True
    rag_ingestion_allowed_channels: list[str] = Field(default_factory=list)
    rag_ingestion_min_query_chars: int = Field(default=10)
    rag_ingestion_min_response_chars: int = Field(default=20)
    rag_ingestion_blocked_patterns: list[str] = Field(default_factory=list)
    rag_ingestion_dynamic_enabled: bool = True
    rag_ingestion_dynamic_refresh_ms: int = Field(default=30_000, ge=250)
    mcp_security_allowed_server_names: list[str] = Field(default_factory=list)
    mcp_security_max_tool_output_length: int = Field(default=50_000, ge=1_024, le=500_000)
    output_guard_dynamic_rules_enabled: bool = True
    eval_llm_judge_enabled: bool = False
    eval_llm_judge_provider: str = "openai"
    eval_llm_judge_model: str = "gpt-5-mini"
    scheduler_default_execution_timeout_ms: int = Field(default=300_000, ge=1_000)
    scheduler_lease_buffer_ms: int = Field(default=10_000, ge=0)
    scheduler_minimum_lease_ms: int = Field(default=5_000, ge=1_000)
    scheduler_retry_delay_ms: int = Field(default=2_000, ge=0)
    scheduler_max_executions_per_job: int = Field(default=200, gt=0)
    scheduler_enabled: bool = False
    scheduler_poll_interval_seconds: float = Field(default=60.0, gt=0)
    scheduler_lease_owner: str = "reactor-scheduler"
    scheduler_tenant_ids: list[str] = Field(default_factory=list)
    alert_scheduler_enabled: bool = False
    alert_scheduler_interval_seconds: float = Field(default=60.0, gt=0)
    prompt_lab_scheduler_enabled: bool = False
    prompt_lab_scheduler_interval_seconds: float = Field(default=86_400.0, gt=0)
    prompt_lab_scheduler_tenant_ids: list[str] = Field(default_factory=list)
    prompt_lab_scheduler_user_id: str = "system"
    prompt_lab_scheduler_template_ids: list[str] = Field(default_factory=list)
    prompt_lab_scheduler_candidate_count: int | None = Field(default=None, ge=1, le=20)
    prompt_lab_scheduler_judge_model: str | None = None
    observability_tracing_enabled: bool = False
    observability_trace_exporter: str = "none"
    observability_otlp_endpoint: str = ""
    observability_otlp_headers: list[str] = Field(default_factory=list)
    observability_trace_sample_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    observability_langsmith_project: str = ""
    observability_langsmith_endpoint: str = ""
    observability_langsmith_api_key: str = ""
    observability_langsmith_hide_inputs: bool = True
    observability_langsmith_hide_outputs: bool = True
    observability_langsmith_hide_metadata: bool = True
    slack_signing_secret: str = ""
    slack_previous_signing_secrets: list[str] = Field(default_factory=list)
    slack_bot_token: str = ""
    slack_app_token: str = ""
    slack_socket_mode_enabled: bool = False
    slack_require_channel_mention: bool = True
    slack_allowed_channel_ids: list[str] = Field(default_factory=list)
    slack_free_response_channel_ids: list[str] = Field(default_factory=list)
    slack_allowed_user_ids: list[str] = Field(default_factory=list)
    slack_signature_tolerance_seconds: int = Field(default=300, gt=0)
    slack_event_dedup_ttl_seconds: int = Field(default=600, gt=0)
    slack_user_rate_limit_enabled: bool = True
    slack_user_rate_limit_backend: str = "memory"
    slack_user_rate_limit_max_per_minute: int = Field(default=10, gt=0)
    slack_user_rate_limit_max_users: int = Field(default=50_000, gt=0)
    slack_user_rate_limit_redis_fail_open: bool = False
    slack_backpressure_enabled: bool = True
    slack_backpressure_max_concurrent_requests: int = Field(default=20, gt=0)
    slack_backpressure_request_timeout_seconds: float = Field(default=0.0, ge=0.0)
    slack_backpressure_fail_fast_on_saturation: bool = True
    slack_reminder_scheduler_enabled: bool = False
    slack_reminder_scheduler_interval_seconds: float = Field(default=60.0, gt=0)
    release_readiness_report_path: str = "reports/release-readiness.json"

    auth_jwt_secret: str = ""
    auth_jwt_expiration_ms: int = Field(default=86_400_000, gt=0)
    auth_api_keys: list[str] = Field(default_factory=list)
    auth_default_tenant_id: str = "default"
    auth_self_registration_enabled: bool = False
    auth_demo_login_enabled: bool = True
    auth_login_rate_limit_per_minute: int = Field(default=10, gt=0)
    auth_trust_forwarded_headers: bool = False
    auth_iam_enabled: bool = False
    auth_iam_base_url: str = ""
    auth_iam_issuer: str = "reactor-iam"
    auth_iam_auto_create_user: bool = True
    auth_iam_default_role: str = "USER"
    auth_iam_public_key_timeout_ms: int = Field(default=5000, gt=0)

    security_headers_enabled: bool = True
    request_body_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    trusted_hosts_enabled: bool = True
    trusted_hosts: list[str] = Field(
        default_factory=lambda: ["127.0.0.1", "localhost", "testserver"]
    )
    cors_enabled: bool = False
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    cors_allowed_methods: list[str] = Field(
        default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    )
    cors_allowed_headers: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = False
    cors_max_age: int = Field(default=3600, ge=0)

    def effective_redis_required(self) -> bool:
        if self.redis_required:
            return True
        if self.environment.strip().lower() not in {"prod", "production"}:
            return False
        return self.api_replica_count > 1 or self.worker_replica_count > 1


def database_required_for_runtime(settings: Settings) -> bool:
    if settings.database_required:
        return True
    return settings.environment.strip().lower() in {"prod", "production"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
