from __future__ import annotations

import pytest

from reactor.slack.faq import (
    AutoReplyMode,
    ChannelFaqRegistration,
    ChannelFaqRegistrationService,
    InMemoryChannelFaqRegistrationStore,
    RegistrationOptions,
    RegistrationPatch,
)


def test_faq_registration_service_validates_threshold_and_interval() -> None:
    service = ChannelFaqRegistrationService(InMemoryChannelFaqRegistrationStore())

    with pytest.raises(ValueError, match="confidence_threshold"):
        service.register(
            tenant_id="tenant_1",
            channel_id="C123",
            options=RegistrationOptions(confidence_threshold=1.5),
        )

    with pytest.raises(ValueError, match="re_ingest_interval_hours"):
        service.register(
            tenant_id="tenant_1",
            channel_id="C123",
            options=RegistrationOptions(re_ingest_interval_hours=0),
        )


def test_faq_registration_service_registers_and_updates_channel() -> None:
    service = ChannelFaqRegistrationService(InMemoryChannelFaqRegistrationStore())

    registered = service.register(
        tenant_id="tenant_1",
        channel_id="C123",
        options=RegistrationOptions(
            channel_name="support",
            auto_reply_mode=AutoReplyMode.ALWAYS,
            confidence_threshold=0.75,
            days_back=7,
            re_ingest_interval_hours=12,
        ),
        actor="admin_1",
    )
    updated = service.update(
        tenant_id="tenant_1",
        channel_id="C123",
        patch=RegistrationPatch(enabled=False, auto_reply_mode=AutoReplyMode.OFF),
    )

    assert registered.channel_id == "C123"
    assert registered.registered_by == "admin_1"
    assert updated is not None
    assert updated.enabled is False
    assert updated.auto_reply_mode is AutoReplyMode.OFF
    assert service.list(tenant_id="tenant_1", enabled_only=True) == []


def test_faq_registration_store_updates_ingest_result() -> None:
    store = InMemoryChannelFaqRegistrationStore()
    store.save(
        ChannelFaqRegistration(
            tenant_id="tenant_1",
            channel_id="C123",
            auto_reply_mode=AutoReplyMode.MENTION,
        )
    )

    updated = store.update_ingest_result(
        tenant_id="tenant_1",
        channel_id="C123",
        status="ok",
        message_count=20,
        chunk_count=8,
        error=None,
    )

    assert updated is not None
    assert updated.last_status == "ok"
    assert updated.last_message_count == 20
    assert updated.last_chunk_count == 8
