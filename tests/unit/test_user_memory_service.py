from __future__ import annotations

from datetime import UTC, datetime

import pytest

from reactor.memory.service import (
    UserMemoryRecord,
    UserMemoryService,
    validate_user_memory_key_value,
)


def test_user_memory_key_value_validation_rejects_blank_or_raw_namespace_keys() -> None:
    with pytest.raises(ValueError, match="key must not be blank"):
        validate_user_memory_key_value("", "value")
    with pytest.raises(ValueError, match="value must not be blank"):
        validate_user_memory_key_value("key", "")
    with pytest.raises(ValueError, match="key must not contain ':'"):
        validate_user_memory_key_value("raw:tuple", "value")


async def test_user_memory_service_delegates_fact_preference_and_delete() -> None:
    store = RecordingUserMemoryStore()
    service = UserMemoryService(store)

    await service.update_fact(
        tenant_id="tenant_1",
        user_id="user_1",
        key=" team ",
        value=" platform ",
    )
    await service.update_preference(
        tenant_id="tenant_1",
        user_id="user_1",
        key=" language ",
        value=" Korean ",
    )
    memory = await service.get(tenant_id="tenant_1", user_id="user_1")
    await service.delete(tenant_id="tenant_1", user_id="user_1")

    assert memory is not None
    assert memory.facts == {"team": "platform"}
    assert memory.preferences == {"language": "Korean"}
    assert await service.get(tenant_id="tenant_1", user_id="user_1") is None


class RecordingUserMemoryStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], UserMemoryRecord] = {}

    async def get_user_memory(self, *, tenant_id: str, user_id: str) -> UserMemoryRecord | None:
        return self.records.get((tenant_id, user_id))

    async def upsert_user_memory_value(
        self,
        *,
        tenant_id: str,
        user_id: str,
        category: str,
        key: str,
        value: str,
    ) -> None:
        existing = self.records.get((tenant_id, user_id))
        facts = dict(existing.facts if existing else {})
        preferences = dict(existing.preferences if existing else {})
        if category == "fact":
            facts[key] = value
        else:
            preferences[key] = value
        self.records[(tenant_id, user_id)] = UserMemoryRecord(
            user_id=user_id,
            facts=facts,
            preferences=preferences,
            recent_topics=[],
            updated_at=datetime.now(UTC),
        )

    async def delete_user_memory(self, *, tenant_id: str, user_id: str) -> None:
        self.records.pop((tenant_id, user_id), None)
