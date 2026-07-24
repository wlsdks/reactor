from __future__ import annotations

from datetime import UTC, datetime, timedelta

from reactor.core.settings import Settings
from reactor.rag.ingestion_policy import (
    RAG_INGESTION_POLICY_SETTING_KEY,
    RagIngestionPolicy,
    RagIngestionPolicyStore,
    normalize_policy,
)
from reactor.runtime_settings.service import RuntimeSettingRecord, RuntimeSettingUpdate


def test_rag_ingestion_policy_from_settings_normalizes_config_defaults() -> None:
    policy = RagIngestionPolicy.from_settings(
        Settings(
            rag_ingestion_enabled=True,
            rag_ingestion_require_review=True,
            rag_ingestion_allowed_channels=[" Slack ", "", "EMAIL"],
            rag_ingestion_min_query_chars=0,
            rag_ingestion_min_response_chars=-1,
            rag_ingestion_blocked_patterns=[" secret ", ""],
        )
    )

    assert policy.enabled is True
    assert policy.require_review is True
    assert policy.allowed_channels == ("email", "slack")
    assert policy.min_query_chars == 1
    assert policy.min_response_chars == 1
    assert policy.blocked_patterns == ("secret",)


async def test_rag_ingestion_policy_store_round_trips_runtime_setting_json() -> None:
    now = datetime.now(UTC)
    runtime_store = FakeRuntimeSettingsStore(now=now)
    store = RagIngestionPolicyStore(runtime_store)
    policy = normalize_policy(
        RagIngestionPolicy(
            enabled=True,
            require_review=False,
            allowed_channels=("Slack", "confluence"),
            min_query_chars=8,
            min_response_chars=20,
            blocked_patterns=(" secret ",),
            created_at=now - timedelta(minutes=1),
            updated_at=now,
        )
    )

    saved = await store.save(policy, actor="admin_1")
    loaded = await store.get_or_none()
    await store.delete()
    deleted = await store.get_or_none()

    assert saved.allowed_channels == ("confluence", "slack")
    assert loaded == saved
    assert deleted is None
    assert runtime_store.saved_update is not None
    assert runtime_store.saved_update.key == RAG_INGESTION_POLICY_SETTING_KEY
    assert runtime_store.saved_update.value_type == "JSON"
    assert runtime_store.deleted == [(RAG_INGESTION_POLICY_SETTING_KEY, "global")]


class FakeRuntimeSettingsStore:
    def __init__(self, *, now: datetime) -> None:
        self.now = now
        self.record: RuntimeSettingRecord | None = None
        self.saved_update: RuntimeSettingUpdate | None = None
        self.deleted: list[tuple[str, str]] = []

    async def set(self, update: RuntimeSettingUpdate) -> RuntimeSettingRecord:
        self.saved_update = update
        self.record = RuntimeSettingRecord(
            key=update.key,
            value=update.value,
            value_type=update.value_type,
            category=update.category,
            tenant_id=update.tenant_id,
            description=update.description,
            updated_by=update.updated_by,
            updated_at=self.now,
            metadata=update.metadata,
        )
        return self.record

    async def find(
        self,
        key: str,
        *,
        tenant_id: str = "global",
    ) -> RuntimeSettingRecord | None:
        del key, tenant_id
        return self.record

    async def delete(self, key: str, *, tenant_id: str = "global") -> None:
        self.record = None
        self.deleted.append((key, tenant_id))
