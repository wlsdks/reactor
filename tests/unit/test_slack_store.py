from __future__ import annotations

from sqlalchemy.dialects import postgresql

from reactor.persistence.models import Base
from reactor.persistence.slack_store import (
    build_faq_registration_upsert,
    build_faq_update_ingest_result,
    faq_registration_values,
    proactive_channel_values,
    slack_bot_values,
)
from reactor.slack.faq import (
    AutoReplyMode,
    ChannelFaqRegistration,
    IngestStatus,
)
from reactor.slack.models import (
    ProactiveChannelRecord,
    SlackBotInstanceRecord,
    mask_slack_token,
)

BOT_TOKEN = "xoxb-" + "fixture-token"
APP_TOKEN = "xapp-" + "fixture-token"


def test_slack_models_are_registered_in_metadata() -> None:
    bot_table = Base.metadata.tables["slack_bot_instances"]
    channel_table = Base.metadata.tables["slack_proactive_channels"]
    faq_table = Base.metadata.tables["channel_faq_registrations"]

    assert "uq_slack_bot_instances_name" in {
        constraint.name for constraint in bot_table.constraints
    }
    assert "uq_slack_proactive_channels_id" in {
        constraint.name for constraint in channel_table.constraints
    }
    assert "ix_slack_bot_instances_tenant_enabled" in {index.name for index in bot_table.indexes}
    assert "ix_slack_proactive_channels_tenant_added" in {
        index.name for index in channel_table.indexes
    }
    assert "uq_channel_faq_registrations_tenant_channel" in {
        constraint.name for constraint in faq_table.constraints
    }
    assert "ix_channel_faq_registrations_due" in {index.name for index in faq_table.indexes}


def test_slack_store_values_preserve_sensitive_tokens_only_in_persistence() -> None:
    bot = SlackBotInstanceRecord(
        id="bot_1",
        tenant_id="tenant_1",
        name="Support Bot",
        bot_token=BOT_TOKEN,
        app_token=APP_TOKEN,
        persona_id="support",
        default_channel="C123",
    )
    channel = ProactiveChannelRecord(
        tenant_id="tenant_1",
        channel_id="C123",
        channel_name="support",
    )

    bot_values = slack_bot_values(bot)
    channel_values = proactive_channel_values(channel)

    assert bot_values["bot_token"] == BOT_TOKEN
    assert bot_values["app_token"] == APP_TOKEN
    assert channel_values["tenant_id"] == "tenant_1"
    assert channel_values["channel_id"] == "C123"
    assert mask_slack_token(BOT_TOKEN) == "xoxb-f***"


def test_slack_table_names_compile_for_postgres() -> None:
    bot_table = Base.metadata.tables["slack_bot_instances"]
    channel_table = Base.metadata.tables["slack_proactive_channels"]
    faq_table = Base.metadata.tables["channel_faq_registrations"]

    bot_sql = str(bot_table.select().compile(dialect=postgresql.dialect()))
    channel_sql = str(channel_table.select().compile(dialect=postgresql.dialect()))
    faq_sql = str(faq_table.select().compile(dialect=postgresql.dialect()))

    assert "slack_bot_instances" in bot_sql
    assert "slack_proactive_channels" in channel_sql
    assert "channel_faq_registrations" in faq_sql


def test_faq_registration_values_and_upsert_preserve_legacy_contract() -> None:
    registration = ChannelFaqRegistration(
        tenant_id="tenant_1",
        channel_id="C123",
        channel_name="support",
        enabled=True,
        auto_reply_mode=AutoReplyMode.ALWAYS,
        confidence_threshold=0.82,
        days_back=14,
        re_ingest_interval_hours=12,
        registered_by="admin_1",
    )

    values = faq_registration_values(registration)
    upsert = str(build_faq_registration_upsert(registration).compile(dialect=postgresql.dialect()))

    assert values["tenant_id"] == "tenant_1"
    assert values["channel_id"] == "C123"
    assert values["auto_reply_mode"] == "always"
    assert values["confidence_threshold"] == 0.82
    assert "ON CONFLICT" in upsert
    assert "uq_channel_faq_registrations_tenant_channel" in upsert


def test_faq_ingest_result_update_sets_status_counts_and_error() -> None:
    statement = build_faq_update_ingest_result(
        tenant_id="tenant_1",
        channel_id="C123",
        status=IngestStatus.FAILED,
        message_count=11,
        chunk_count=3,
        error="failed",
    )

    compiled = statement.compile(dialect=postgresql.dialect())

    assert "UPDATE channel_faq_registrations" in str(compiled)
    assert compiled.params["last_status"] == "failed"
    assert compiled.params["last_message_count"] == 11
    assert compiled.params["last_chunk_count"] == 3
    assert compiled.params["last_error"] == "failed"
