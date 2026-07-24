from __future__ import annotations

import hmac
import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from urllib.parse import quote

from httpx import ASGITransport, AsyncClient

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.api.app import create_app
from reactor.persistence.durable_store import OutboxRequest
from reactor.slack.faq import (
    FaqOutcome,
    InMemoryChannelFaqRegistrationStore,
    InMemorySlackFaqMetrics,
)
from reactor.slack.faq_responder import FaqAutoReply, FaqCandidate
from reactor.slack.models import ProactiveChannelRecord, SlackBotInstanceRecord

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}

MANAGER_HEADERS = {
    "X-Reactor-User-Id": "manager_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN_MANAGER",
}
SLACK_TEST_SIGNING_SECRET = "secret"  # noqa: S105
SLACK_PREVIOUS_SIGNING_SECRET = "old-secret"  # noqa: S105


async def test_slack_bot_api_crud_masks_tokens_and_requires_full_admin() -> None:
    bot_store = FakeSlackBotStore()
    app = create_app()
    app.state.reactor = FakeContainer(slack_bot_store=bot_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/slack-bots", headers=MANAGER_HEADERS)
        created = await client.post(
            "/api/admin/slack-bots",
            headers=ADMIN_HEADERS,
            json={
                "name": "Support Bot",
                "botToken": "xoxb-secret-token",
                "appToken": "xapp-secret-token",
                "personaId": "support",
                "defaultChannel": "C123",
            },
        )
        bot_id = created.json()["id"]
        duplicate = await client.post(
            "/v1/admin/slack-bots",
            headers=ADMIN_HEADERS,
            json={
                "name": "Support Bot",
                "botToken": "xoxb-other",
                "appToken": "xapp-other",
                "personaId": "support",
            },
        )
        fetched = await client.get(f"/v1/admin/slack-bots/{bot_id}", headers=ADMIN_HEADERS)
        updated = await client.put(
            f"/api/admin/slack-bots/{bot_id}",
            headers=ADMIN_HEADERS,
            json={"enabled": False, "defaultChannel": "C999"},
        )
        listed = await client.get("/v1/admin/slack-bots", headers=ADMIN_HEADERS)
        deleted = await client.delete(f"/api/admin/slack-bots/{bot_id}", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "permission required: slack:write"
    assert created.status_code == 201
    assert created.json()["botTokenMasked"] == "xoxb-s***"
    assert created.json()["appTokenMasked"] == "xapp-s***"
    assert "secret-token" not in created.text
    assert duplicate.status_code == 409
    assert fetched.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["defaultChannel"] == "C999"
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "Support Bot"
    assert deleted.status_code == 204


async def test_proactive_channel_api_records_admin_audit() -> None:
    channel_store = FakeProactiveChannelStore()
    audit_store = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        proactive_channel_store=channel_store,
        admin_audit_store=audit_store,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        added = await client.post(
            "/api/proactive-channels",
            headers=ADMIN_HEADERS,
            json={"channelId": "C123", "channelName": "support"},
        )
        conflict = await client.post(
            "/v1/proactive-channels",
            headers=ADMIN_HEADERS,
            json={"channelId": "C123", "channelName": "support"},
        )
        listed = await client.get("/v1/proactive-channels", headers=ADMIN_HEADERS)
        removed = await client.delete("/api/proactive-channels/C123", headers=ADMIN_HEADERS)
        missing = await client.delete("/v1/proactive-channels/C123", headers=ADMIN_HEADERS)

    assert added.status_code == 201
    assert added.json()["channelId"] == "C123"
    assert conflict.status_code == 409
    assert listed.status_code == 200
    assert listed.json()[0]["channelName"] == "support"
    assert removed.status_code == 204
    assert missing.status_code == 404
    assert [record.action for record in audit_store.saved] == [
        AdminAuditAction.ADD,
        AdminAuditAction.REMOVE,
    ]
    assert audit_store.saved[0].resource_id == "C123"
    assert audit_store.saved[0].actor == "admin_1"


async def test_slack_prompt_reload_ports_legacy_admin_endpoint() -> None:
    reloader = FakeSlackPromptReloader({"base": "prompt", "faq": "prompt"})
    app = create_app()
    app.state.reactor = FakeContainer(slack_prompt_reloader=reloader)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.post(
            "/api/admin/slack/prompts/reload",
            headers=MANAGER_HEADERS,
        )
        reloaded = await client.post(
            "/api/admin/slack/prompts/reload",
            headers=ADMIN_HEADERS,
        )
        reloaded_v1 = await client.post(
            "/v1/admin/slack/prompts/reload",
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert reloaded.status_code == 200
    assert reloaded.json() == {
        "reloaded": True,
        "sectionCount": 2,
        "sections": ["base", "faq"],
    }
    assert reloaded_v1.status_code == 200
    assert reloader.calls == 2


async def test_slack_faq_admin_api_crud_requires_full_admin() -> None:
    faq_store = InMemoryChannelFaqRegistrationStore()
    app = create_app()
    app.state.reactor = FakeContainer(channel_faq_registration_store=faq_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/slack/channels/faq", headers=MANAGER_HEADERS)
        created = await client.post(
            "/api/admin/slack/channels/faq",
            headers=ADMIN_HEADERS,
            json={
                "channelId": "C123",
                "channelName": "support",
                "enabled": True,
                "autoReplyMode": "always",
                "confidenceThreshold": 0.8,
                "daysBack": 14,
                "reIngestIntervalHours": 12,
            },
        )
        listed = await client.get("/v1/admin/slack/channels/faq", headers=ADMIN_HEADERS)
        fetched = await client.get("/v1/admin/slack/channels/faq/C123", headers=ADMIN_HEADERS)
        updated = await client.patch(
            "/api/admin/slack/channels/faq/C123",
            headers=ADMIN_HEADERS,
            json={"enabled": False, "autoReplyMode": "off"},
        )
        deleted = await client.delete("/v1/admin/slack/channels/faq/C123", headers=ADMIN_HEADERS)
        missing = await client.get("/api/admin/slack/channels/faq/C123", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "permission required: slack:write"
    assert created.status_code == 200
    assert created.json()["channelId"] == "C123"
    assert created.json()["registeredBy"] == "admin_1"
    assert created.json()["autoReplyMode"] == "always"
    assert created.json()["confidenceThreshold"] == 0.8
    assert listed.status_code == 200
    assert listed.json()["registrations"][0]["channelName"] == "support"
    assert fetched.status_code == 200
    assert fetched.json()["daysBack"] == 14
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["autoReplyMode"] == "off"
    assert deleted.status_code == 204
    assert missing.status_code == 404


async def test_slack_faq_admin_api_rejects_invalid_registration_options() -> None:
    faq_store = InMemoryChannelFaqRegistrationStore()
    app = create_app()
    app.state.reactor = FakeContainer(channel_faq_registration_store=faq_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        invalid_mode = await client.post(
            "/api/admin/slack/channels/faq",
            headers=ADMIN_HEADERS,
            json={"channelId": "C123", "autoReplyMode": "thread"},
        )
        invalid_threshold = await client.post(
            "/api/admin/slack/channels/faq",
            headers=ADMIN_HEADERS,
            json={"channelId": "C123", "confidenceThreshold": 1.2},
        )

    assert invalid_mode.status_code == 400
    assert invalid_mode.json()["detail"] == "Unsupported autoReplyMode: thread"
    assert invalid_threshold.status_code == 400
    assert invalid_threshold.json()["detail"] == (
        "confidence_threshold must be between 0.0 and 1.0"
    )


async def test_slack_faq_manual_ingest_marks_running_and_enqueues_work() -> None:
    faq_store = InMemoryChannelFaqRegistrationStore()
    durable_store = FakeDurableStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        channel_faq_registration_store=faq_store,
        durable_store=durable_store,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await client.post(
            "/api/admin/slack/channels/faq",
            headers=ADMIN_HEADERS,
            json={"channelId": "C123", "channelName": "support"},
        )
        triggered = await client.post(
            "/api/admin/slack/channels/faq/C123/ingest",
            headers=ADMIN_HEADERS,
        )
        missing = await client.post(
            "/v1/admin/slack/channels/faq/C999/ingest",
            headers=ADMIN_HEADERS,
        )

    assert triggered.status_code == 202
    assert triggered.json() == {
        "channelId": "C123",
        "status": "running",
        "outboxId": "outbox_1",
    }
    updated = faq_store.get(tenant_id="tenant_1", channel_id="C123")
    assert updated is not None
    assert updated.last_status == "running"
    assert len(durable_store.outbox) == 1
    request = durable_store.outbox[0]
    assert request.destination == "slack.faq_ingest"
    assert request.event_type == "slack.channel_faq_ingest"
    assert request.idempotency_key == "slack:faq-ingest:tenant_1:C123"
    assert request.payload == {
        "entrypoint": "manual_admin",
        "channelId": "C123",
        "daysBack": 30,
    }
    assert missing.status_code == 404
    assert len(durable_store.outbox) == 1


async def test_slack_faq_stats_events_and_feedback_api_exposes_metrics_snapshot() -> None:
    metrics = InMemorySlackFaqMetrics(clock_millis=lambda: 1782500000000)
    metrics.record_outcome(
        "C123",
        FaqOutcome.HIT,
        score=0.92,
        query="how to deploy reactor",
        matched_document_id="doc_1",
    )
    metrics.record_outcome("C123", FaqOutcome.SKIP_CONFIDENCE, score=0.42)
    metrics.record_feedback("C123", ["doc_1", "doc_2"], rating=True)
    metrics.record_feedback("C123", ["doc_2"], rating=False)
    app = create_app()
    app.state.reactor = FakeContainer(slack_faq_metrics=metrics)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        channel_stats = await client.get(
            "/api/admin/slack/channels/faq/C123/stats",
            headers=ADMIN_HEADERS,
        )
        overall_stats = await client.get(
            "/v1/admin/slack/channels/faq/stats",
            headers=ADMIN_HEADERS,
        )
        events = await client.get(
            "/api/admin/slack/channels/faq/C123/events",
            headers=ADMIN_HEADERS,
        )
        feedback = await client.get(
            "/v1/admin/slack/channels/faq/C123/feedback",
            headers=ADMIN_HEADERS,
        )

    assert channel_stats.status_code == 200
    assert channel_stats.json()["hits"] == 1
    assert channel_stats.json()["skipsByReason"] == {"skip_confidence": 1}
    assert channel_stats.json()["hitRatio"] == 0.5
    assert overall_stats.status_code == 200
    assert overall_stats.json()["total"] == 2
    assert events.status_code == 200
    assert events.json()["events"][0]["outcome"] == "skip_confidence"
    assert events.json()["events"][1]["matchedDocId"] == "doc_1"
    assert feedback.status_code == 200
    assert feedback.json()["feedback"]["doc_2"] == {
        "docId": "doc_2",
        "thumbsUp": 1,
        "thumbsDown": 1,
        "total": 2,
        "negativeRatio": 0.5,
    }


async def test_slack_faq_probe_and_dry_run_api_use_responder_contract() -> None:
    responder = FakeFaqResponder()
    app = create_app()
    app.state.reactor = FakeContainer(slack_faq_responder=responder)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        probe = await client.post(
            "/api/admin/slack/channels/faq/C123/probe",
            headers=ADMIN_HEADERS,
            json={"query": "reactor deploy", "topK": 2},
        )
        dry_run = await client.post(
            "/v1/admin/slack/channels/faq/C123/dry-run",
            headers=ADMIN_HEADERS,
            json={"query": "reactor faq", "userId": "U9", "asMention": False},
        )

    assert probe.status_code == 200
    assert probe.json()["candidates"][0] == {
        "documentId": "doc_1",
        "chunkIndex": 0,
        "score": 0.91,
        "text": "FAQ candidate",
        "metadata": {"source": "slack-faq"},
    }
    assert dry_run.status_code == 200
    assert dry_run.json()["matched"] is True
    assert dry_run.json()["reply"]["matchedDocIds"] == ["doc_1"]
    assert responder.probe_calls == [
        {
            "tenant_id": "tenant_1",
            "channel_id": "C123",
            "query": "reactor deploy",
            "top_k": 2,
        }
    ]
    assert responder.dry_run_calls == [
        {
            "tenant_id": "tenant_1",
            "channel_id": "C123",
            "user_id": "U9",
            "user_query": "reactor faq",
            "is_mention": False,
        }
    ]


async def test_slack_faq_scheduler_health_api_reports_disabled_or_heartbeat() -> None:
    app = create_app()
    app.state.reactor = FakeContainer()
    enabled_app = create_app()
    enabled_app.state.reactor = FakeContainer(slack_faq_scheduler=FakeFaqScheduler())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        disabled = await client.get(
            "/api/admin/slack/channels/faq/scheduler/health",
            headers=ADMIN_HEADERS,
        )
    async with AsyncClient(
        transport=ASGITransport(app=enabled_app),
        base_url="http://testserver",
    ) as client:
        enabled = await client.get(
            "/v1/admin/slack/channels/faq/scheduler/health",
            headers=ADMIN_HEADERS,
        )

    assert disabled.status_code == 200
    assert disabled.json() == {"enabled": False}
    assert enabled.status_code == 200
    assert enabled.json() == {
        "enabled": True,
        "tickCount": 7,
        "lastTickAt": 1782500000000,
        "intervalMs": 300000,
    }


async def test_slack_events_api_returns_challenge_without_enqueue() -> None:
    durable_store = FakeDurableStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        durable_store=durable_store,
        slack_signing_secret=SLACK_TEST_SIGNING_SECRET,
        slack_now_seconds=lambda: 1782500000,
    )
    body = '{"type":"url_verification","challenge":"challenge_123"}'
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/slack/events",
            content=body,
            headers=slack_headers(SLACK_TEST_SIGNING_SECRET, "1782500000", body),
        )

    assert response.status_code == 200
    assert response.json() == {"challenge": "challenge_123"}
    assert durable_store.outbox == []


async def test_slack_events_api_deduplicates_and_enqueues_signed_callback() -> None:
    durable_store = FakeDurableStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        durable_store=durable_store,
        slack_signing_secret=SLACK_TEST_SIGNING_SECRET,
        slack_now_seconds=lambda: 1782500000,
    )
    body = '{"event_id":"Ev123","team_id":"T1","event":{"type":"app_mention","text":"hi"}}'
    headers = slack_headers(SLACK_TEST_SIGNING_SECRET, "1782500000", body)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post("/api/slack/events", content=body, headers=headers)
        second = await client.post("/api/slack/events", content=body, headers=headers)

    assert first.status_code == 200
    assert first.json() == {"ok": True, "duplicate": False}
    assert second.status_code == 200
    assert second.json() == {"ok": True, "duplicate": True}
    assert len(durable_store.outbox) == 1
    request = durable_store.outbox[0]
    assert request.destination == "slack.events"
    assert request.event_type == "slack.event_callback"
    assert request.idempotency_key == "slack:event:tenant_1:Ev123"
    assert request.payload["entrypoint"] == "events_api"
    assert request.payload["retryNum"] is None


async def test_slack_events_api_records_gateway_audit_after_enqueue() -> None:
    durable_store = FakeDurableStore()
    audit_store = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        durable_store=durable_store,
        admin_audit_store=audit_store,
        slack_signing_secret=SLACK_TEST_SIGNING_SECRET,
        slack_now_seconds=lambda: 1782500000,
    )
    body = json.dumps(
        {
            "event_id": "EvAudit",
            "team_id": "T1",
            "event": {
                "type": "app_mention",
                "channel": "C123",
                "user": "U123",
                "text": "private user message",
            },
        },
        separators=(",", ":"),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/slack/events",
            content=body,
            headers=slack_headers(SLACK_TEST_SIGNING_SECRET, "1782500000", body),
        )

    assert response.status_code == 200
    assert len(audit_store.saved) == 1
    audit = audit_store.saved[0]
    assert audit.category == "slack_gateway"
    assert audit.action == AdminAuditAction.CREATE
    assert audit.actor == "slack:T1"
    assert audit.resource_type == "slack_event"
    assert audit.resource_id == "EvAudit"
    assert audit.detail is not None
    detail = json.loads(audit.detail)
    assert detail == {
        "channelId": "C123",
        "entrypoint": "events_api",
        "eventId": "EvAudit",
        "eventType": "app_mention",
        "idempotencyKey": "slack:event:tenant_1:EvAudit",
        "outboxId": "outbox_1",
        "teamId": "T1",
        "userId": "U123",
    }
    assert "private user message" not in audit.detail


async def test_slack_events_api_retries_enqueue_after_transient_failure() -> None:
    durable_store = FailingOnceDurableStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        durable_store=durable_store,
        slack_signing_secret=SLACK_TEST_SIGNING_SECRET,
        slack_now_seconds=lambda: 1782500000,
    )
    body = '{"event_id":"EvTransient","team_id":"T1","event":{"type":"app_mention","text":"hi"}}'
    transport = ASGITransport(app=app, raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post(
            "/api/slack/events",
            content=body,
            headers=slack_headers(SLACK_TEST_SIGNING_SECRET, "1782500000", body),
        )
        retry = await client.post(
            "/api/slack/events",
            content=body,
            headers={
                **slack_headers(SLACK_TEST_SIGNING_SECRET, "1782500000", body),
                "X-Slack-Retry-Num": "1",
                "X-Slack-Retry-Reason": "http_timeout",
            },
        )

    assert first.status_code == 500
    assert retry.status_code == 200
    assert retry.json() == {"ok": True, "duplicate": False}
    assert len(durable_store.outbox) == 1
    assert durable_store.outbox[0].idempotency_key == "slack:event:tenant_1:EvTransient"
    assert durable_store.outbox[0].payload["retryNum"] == "1"


async def test_slack_events_api_rejects_invalid_signature() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(
        durable_store=FakeDurableStore(),
        slack_signing_secret=SLACK_TEST_SIGNING_SECRET,
        slack_now_seconds=lambda: 1782500000,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/slack/events",
            content='{"event_id":"Ev123"}',
            headers={
                "X-Slack-Request-Timestamp": "1782500000",
                "X-Slack-Signature": "v0=bad",
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Signature mismatch"


async def test_slack_events_api_accepts_previous_signing_secret_during_rotation() -> None:
    durable_store = FakeDurableStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        durable_store=durable_store,
        slack_signing_secret=SLACK_TEST_SIGNING_SECRET,
        slack_previous_signing_secrets=[SLACK_PREVIOUS_SIGNING_SECRET],
        slack_now_seconds=lambda: 1782500000,
    )
    body = '{"event_id":"Ev456","team_id":"T1","event":{"type":"app_mention","text":"hi"}}'
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/slack/events",
            content=body,
            headers=slack_headers(SLACK_PREVIOUS_SIGNING_SECRET, "1782500000", body),
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "duplicate": False}
    assert durable_store.outbox[0].idempotency_key == "slack:event:tenant_1:Ev456"


async def test_slack_commands_api_validates_form_and_enqueues_ack() -> None:
    durable_store = FakeDurableStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        durable_store=durable_store,
        slack_signing_secret=SLACK_TEST_SIGNING_SECRET,
        slack_now_seconds=lambda: 1782500000,
    )
    form = (
        "command=%2Freactor&text=help&user_id=U1&user_name=sample-user"
        "&channel_id=C1&channel_name=general&team_id=T1"
        "&response_url=https%3A%2F%2Fhooks.slack.test%2Fresponse"
        "&trigger_id=123.456"
    )
    headers = slack_headers(SLACK_TEST_SIGNING_SECRET, "1782500000", form)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        accepted = await client.post(
            "/api/slack/commands",
            content=form,
            headers={
                **headers,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        invalid = await client.post(
            "/api/slack/commands",
            content="command=%2Freactor",
            headers={
                **slack_headers(
                    SLACK_TEST_SIGNING_SECRET,
                    "1782500000",
                    "command=%2Freactor",
                ),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

    assert accepted.status_code == 200
    assert accepted.json() == {
        "response_type": "ephemeral",
        "text": "요청을 처리하고 있습니다. 잠시만 기다려주세요.",
    }
    assert invalid.status_code == 400
    assert invalid.json() == {
        "response_type": "ephemeral",
        "text": "요청을 처리할 수 없습니다. 필수 Slack 필드가 누락되었습니다.",
    }
    assert len(durable_store.outbox) == 1
    request = durable_store.outbox[0]
    assert request.destination == "slack.commands"
    assert request.event_type == "slack.slash_command"
    assert request.idempotency_key == "slack:command:tenant_1:T1:U1:123.456"
    assert request.payload["command"]["text"] == "help"


async def test_slack_commands_api_disambiguates_missing_trigger_id_by_command_context() -> None:
    durable_store = FakeDurableStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        durable_store=durable_store,
        slack_signing_secret=SLACK_TEST_SIGNING_SECRET,
        slack_now_seconds=lambda: 1782500000,
    )
    base_form = (
        "command=%2Freactor&user_id=U1&user_name=sample-user"
        "&channel_id=C1&channel_name=general&team_id=T1"
        "&response_url=https%3A%2F%2Fhooks.slack.test%2Fresponse"
    )
    status_form = f"{base_form}&text=status"
    help_form = f"{base_form}&text=help"
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        status_response = await client.post(
            "/api/slack/commands",
            content=status_form,
            headers={
                **slack_headers(SLACK_TEST_SIGNING_SECRET, "1782500000", status_form),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        help_response = await client.post(
            "/api/slack/commands",
            content=help_form,
            headers={
                **slack_headers(SLACK_TEST_SIGNING_SECRET, "1782500000", help_form),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

    assert status_response.status_code == 200
    assert help_response.status_code == 200
    assert len(durable_store.outbox) == 2
    keys = [request.idempotency_key for request in durable_store.outbox]
    assert keys[0] != keys[1]
    assert all(key.startswith("slack:command:tenant_1:T1:U1:missing-trigger:") for key in keys)


async def test_slack_interactions_api_validates_form_and_enqueues_block_action() -> None:
    durable_store = FakeDurableStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        durable_store=durable_store,
        slack_signing_secret=SLACK_TEST_SIGNING_SECRET,
        slack_now_seconds=lambda: 1782500000,
    )
    interaction_payload = {
        "type": "block_actions",
        "team": {"id": "T1"},
        "user": {"id": "U1"},
        "channel": {"id": "C1"},
        "message": {"ts": "1710000001.000200"},
        "response_url": "https://hooks.slack.test/interaction",
        "actions": [{"action_id": "feedback.up", "value": "ok"}],
    }
    form = f"payload={quote(json.dumps(interaction_payload, separators=(',', ':')))}"
    headers = slack_headers(SLACK_TEST_SIGNING_SECRET, "1782500000", form)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        accepted = await client.post(
            "/api/slack/interactions",
            content=form,
            headers={
                **headers,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

    assert accepted.status_code == 200
    assert accepted.json() == {"ok": True}
    assert len(durable_store.outbox) == 1
    request = durable_store.outbox[0]
    assert request.destination == "slack.interactions"
    assert request.event_type == "slack.block_action"
    assert request.idempotency_key == (
        "slack:interaction:tenant_1:T1:U1:feedback.up:1710000001.000200"
    )
    assert request.payload["entrypoint"] == "interactivity"
    assert request.payload["interaction"] == interaction_payload


class FakeContainer:
    def __init__(
        self,
        *,
        slack_bot_store: FakeSlackBotStore | None = None,
        proactive_channel_store: FakeProactiveChannelStore | None = None,
        admin_audit_store: FakeAdminAuditStore | None = None,
        durable_store: FakeDurableStore | None = None,
        channel_faq_registration_store: InMemoryChannelFaqRegistrationStore | None = None,
        slack_faq_metrics: InMemorySlackFaqMetrics | None = None,
        slack_faq_responder: FakeFaqResponder | None = None,
        slack_faq_scheduler: FakeFaqScheduler | None = None,
        slack_prompt_reloader: FakeSlackPromptReloader | None = None,
        slack_signing_secret: str = "",
        slack_previous_signing_secrets: list[str] | None = None,
        slack_now_seconds: Any | None = None,
    ) -> None:
        self._slack_bot_store = slack_bot_store
        self._proactive_channel_store = proactive_channel_store
        self._admin_audit_store = admin_audit_store
        self._durable_store = durable_store
        self._channel_faq_registration_store = channel_faq_registration_store
        self._slack_faq_metrics = slack_faq_metrics
        self._slack_faq_responder = slack_faq_responder
        self._slack_faq_scheduler = slack_faq_scheduler
        self._slack_prompt_reloader = slack_prompt_reloader
        self.settings = FakeSettings(
            slack_signing_secret=slack_signing_secret,
            slack_previous_signing_secrets=slack_previous_signing_secrets or [],
        )
        self.slack_now_seconds = slack_now_seconds

    def slack_bot_store(self) -> FakeSlackBotStore | None:
        return self._slack_bot_store

    def proactive_channel_store(self) -> FakeProactiveChannelStore | None:
        return self._proactive_channel_store

    def admin_audit_store(self) -> FakeAdminAuditStore | None:
        return self._admin_audit_store

    def durable_store(self) -> FakeDurableStore | None:
        return self._durable_store

    def channel_faq_registration_store(self) -> InMemoryChannelFaqRegistrationStore | None:
        return self._channel_faq_registration_store

    def slack_faq_metrics(self) -> InMemorySlackFaqMetrics | None:
        return self._slack_faq_metrics

    def slack_faq_responder(self) -> FakeFaqResponder | None:
        return self._slack_faq_responder

    def slack_faq_scheduler(self) -> FakeFaqScheduler | None:
        return self._slack_faq_scheduler

    def slack_prompt_reloader(self) -> FakeSlackPromptReloader | None:
        return self._slack_prompt_reloader


class FakeSlackPromptReloader:
    def __init__(self, sections: dict[str, str]) -> None:
        self.sections = sections
        self.calls = 0

    def reload(self) -> dict[str, str]:
        self.calls += 1
        return dict(self.sections)


class FakeSlackBotStore:
    def __init__(self) -> None:
        self.records: dict[str, SlackBotInstanceRecord] = {}

    async def list(self, *, tenant_id: str) -> list[SlackBotInstanceRecord]:
        return sorted(
            [record for record in self.records.values() if record.tenant_id == tenant_id],
            key=lambda record: record.created_at,
        )

    async def get(self, *, tenant_id: str, bot_id: str) -> SlackBotInstanceRecord | None:
        record = self.records.get(bot_id)
        return record if record is not None and record.tenant_id == tenant_id else None

    async def save(self, record: SlackBotInstanceRecord) -> SlackBotInstanceRecord:
        self.records[record.id] = record
        return record

    async def delete(self, *, tenant_id: str, bot_id: str) -> bool:
        record = await self.get(tenant_id=tenant_id, bot_id=bot_id)
        if record is None:
            return False
        self.records.pop(bot_id)
        return True


class FakeProactiveChannelStore:
    def __init__(self) -> None:
        self.records: dict[str, ProactiveChannelRecord] = {}

    async def list(self, *, tenant_id: str) -> list[ProactiveChannelRecord]:
        return sorted(
            [record for record in self.records.values() if record.tenant_id == tenant_id],
            key=lambda record: record.added_at,
        )

    async def is_enabled(self, *, tenant_id: str, channel_id: str) -> bool:
        record = self.records.get(channel_id)
        return record is not None and record.tenant_id == tenant_id

    async def add(
        self, *, tenant_id: str, channel_id: str, channel_name: str | None
    ) -> ProactiveChannelRecord:
        record = ProactiveChannelRecord(
            tenant_id=tenant_id,
            channel_id=channel_id,
            channel_name=channel_name,
            added_at=datetime(2026, 6, 26, tzinfo=UTC),
        )
        self.records[channel_id] = record
        return record

    async def remove(self, *, tenant_id: str, channel_id: str) -> bool:
        if not await self.is_enabled(tenant_id=tenant_id, channel_id=channel_id):
            return False
        self.records.pop(channel_id)
        return True


class FakeAdminAuditStore:
    def __init__(self) -> None:
        self.saved: list[AdminAuditLog] = []

    async def save(self, log: AdminAuditLog, *, tenant_id: str) -> AdminAuditLog:
        del tenant_id
        self.saved.append(log)
        return log


class FakeDurableStore:
    def __init__(self) -> None:
        self.outbox: list[OutboxRequest] = []

    async def enqueue_outbox(self, request: OutboxRequest) -> str:
        self.outbox.append(request)
        return f"outbox_{len(self.outbox)}"


class FailingOnceDurableStore(FakeDurableStore):
    def __init__(self) -> None:
        super().__init__()
        self.failures_remaining = 1

    async def enqueue_outbox(self, request: OutboxRequest) -> str:
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise RuntimeError("transient enqueue failure")
        return await super().enqueue_outbox(request)


class FakeFaqResponder:
    def __init__(self) -> None:
        self.probe_calls: list[dict[str, object]] = []
        self.dry_run_calls: list[dict[str, object]] = []

    async def probe_top_k(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        query: str,
        top_k: int,
    ) -> list[FaqCandidate]:
        self.probe_calls.append(
            {
                "tenant_id": tenant_id,
                "channel_id": channel_id,
                "query": query,
                "top_k": top_k,
            }
        )
        return [
            FaqCandidate(
                document_id="doc_1",
                chunk_index=0,
                score=0.91,
                text="FAQ candidate",
                metadata={"source": "slack-faq"},
            )
        ]

    async def dry_run_auto_reply(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        user_id: str,
        user_query: str,
        is_mention: bool,
    ) -> FaqAutoReply:
        self.dry_run_calls.append(
            {
                "tenant_id": tenant_id,
                "channel_id": channel_id,
                "user_id": user_id,
                "user_query": user_query,
                "is_mention": is_mention,
            }
        )
        return FaqAutoReply(
            text="FAQ answer",
            score=0.91,
            threshold=0.75,
            matched_document_ids=["doc_1"],
        )


class FakeFaqScheduler:
    SCHEDULE_INTERVAL_MS = 300000

    def tick_count(self) -> int:
        return 7

    def last_tick_at(self) -> int:
        return 1782500000000


class FakeSettings:
    def __init__(
        self,
        *,
        slack_signing_secret: str,
        slack_previous_signing_secrets: list[str],
    ) -> None:
        self.slack_signing_secret = slack_signing_secret
        self.slack_previous_signing_secrets = slack_previous_signing_secrets
        self.slack_signature_tolerance_seconds = 300
        self.auth_default_tenant_id = "tenant_1"


def slack_headers(secret: str, timestamp: str, body: str) -> dict[str, str]:
    base = f"v0:{timestamp}:{body}".encode()
    digest = hmac.new(secret.encode(), base, sha256).hexdigest()
    return {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": f"v0={digest}",
    }
