from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import httpx
import pytest
import respx

from reactor.agents.runner import RunResult
from reactor.slack.backpressure import SlackBackpressureLimiter
from reactor.slack.faq import (
    ChannelFaqRegistration,
    InMemoryChannelFaqRegistrationStore,
    InMemorySlackFaqMetrics,
)
from reactor.slack.feedback import FeedbackRating, InMemoryBotResponseTracker, InMemoryFeedbackStore
from reactor.slack.rate_limit import InMemorySlackUserRateLimiter
from reactor.slack.reminder import InMemorySlackReminderStore
from reactor.slack.worker import (
    ChannelFaqIngestPayload,
    ChannelFaqIngestResult,
    ChannelFaqIngestWorker,
    HttpSlackAssistantStatusClient,
    HttpSlackMessagingClient,
    HttpSlackResponseUrlClient,
    HttpSlackThreadContextClient,
    InMemorySlackAssistantThreadContextStore,
    RunStoreSlackThreadParticipationTracker,
    SlackEventPayload,
    SlackEventPolicy,
    SlackEventWorker,
    SlackMessageSendResult,
    SlackMessagingClient,
    SlackResponseUrlClient,
    SlackRetryableSendError,
    SlackSlashCommandPayload,
    SlackSlashCommandWorker,
    SlackThreadMessage,
    SlackThreadParticipationTracker,
)
from reactor.tools.approval import ApprovalRequest

SLACK_TEST_BOT_TOKEN = "xoxb-test-token"  # noqa: S105


async def test_slack_command_worker_posts_question_and_replies_in_thread() -> None:
    run_service = RecordingRunService(response="Here is the answer.")
    response_url_client = RecordingResponseUrlClient()
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="1710000000.000100"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    worker = SlackSlashCommandWorker(
        run_service=run_service,
        response_url_client=response_url_client,
        messaging_client=messaging_client,
    )

    await worker.handle(
        SlackSlashCommandPayload(
            tenant_id="tenant_1",
            command="/reactor",
            text="what changed?",
            user_id="U1",
            user_name="sample-user",
            channel_id="C1",
            channel_name="general",
            team_id="T1",
            response_url="https://hooks.slack.test/response",
            trigger_id="123.456",
            entrypoint="slash_command",
        )
    )

    assert run_service.messages == ["what changed?"]
    assert run_service.metadata[0]["channel"] == "slack"
    assert run_service.metadata[0]["entrypoint"] == "slash_command"
    assert run_service.metadata[0]["slackThreadTs"] == "1710000000.000100"
    assert run_service.thread_ids == ["slack-C1-1710000000.000100"]
    assert messaging_client.sent == [
        (
            "C1",
            {
                "text": "",
                "thread_ts": None,
                "attachments": [
                    {
                        "color": "#36a64f",
                        "text": "*<@U1> 님의 질문*\nwhat changed?",
                        "mrkdwn_in": ["text"],
                    }
                ],
            },
        ),
        (
            "C1",
            {
                "text": (
                    "<@U1> Here is the answer.\n\n"
                    "_Run: `run_1`_\n"
                    "_Diagnose: `reactor-runs diagnose run_1 --output table`_\n"
                    "_Replay events: `reactor-runs replay run_1 --output table`_\n"
                    "_State history: `reactor-admin state-history run_1 --output table`_\n"
                    "_Feedback review: `reactor-admin feedback --rating thumbs_down "
                    "--review-status inbox --limit 10 "
                    "--output table`_"
                ),
                "thread_ts": "1710000000.000100",
                "attachments": None,
            },
        ),
    ]
    assert response_url_client.sent == []


async def test_slack_command_worker_posts_approval_buttons_for_pending_approval() -> None:
    run_service = RecordingRunService(
        response="Approval required.",
        response_metadata={
            "approval_status": "pending",
            "approval_request": {
                "run_id": "run_1",
                "tenant_id": "tenant_1",
                "tool_id": "builtin:send_webhook",
                "tool_risk_level": "external_side_effect",
                "tool_timeout_ms": 15000,
                "requested_by": "U1",
                "input_payload": {"url": "https://example.com"},
            },
        },
    )
    response_url_client = RecordingResponseUrlClient()
    approval_store = RecordingApprovalRequestStore()
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="1710000000.000100"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    worker = SlackSlashCommandWorker(
        run_service=run_service,
        response_url_client=response_url_client,
        messaging_client=messaging_client,
        approval_store=approval_store,
    )

    await worker.handle(
        SlackSlashCommandPayload(
            tenant_id="tenant_1",
            command="/reactor",
            text="send the webhook",
            user_id="U1",
            user_name="sample-user",
            channel_id="C1",
            channel_name="general",
            team_id="T1",
            response_url="https://hooks.slack.test/response",
            trigger_id="123.456",
            entrypoint="slash_command",
        )
    )

    assert messaging_client.sent[1] == (
        "C1",
        {
            "text": (
                "<@U1> Approval required.\n\n"
                "_Run: `run_1`_\n"
                "_Diagnose: `reactor-runs diagnose run_1 --output table`_\n"
                "_Replay events: `reactor-runs replay run_1 --output table`_\n"
                "_State history: `reactor-admin state-history run_1 --output table`_\n"
                "_Feedback review: `reactor-admin feedback --rating thumbs_down "
                "--review-status inbox --limit 10 "
                "--output table`_\n"
                "_Resume: `reactor-runs resume run_1 --approval-id approval_1 --output table`_"
            ),
            "thread_ts": "1710000000.000100",
            "attachments": None,
            "blocks": expected_approval_blocks(),
        },
    )
    assert approval_store.requests == [
        (
            "tenant_1",
            "run_1",
            "builtin:send_webhook",
            "U1",
            {
                "run_id": "run_1",
                "tenant_id": "tenant_1",
                "tool_id": "builtin:send_webhook",
                "tool_risk_level": "external_side_effect",
                "tool_timeout_ms": 15000,
                "requested_by": "U1",
                "input_payload": {"url": "https://example.com"},
                "slack_channel_id": "C1",
                "slack_thread_ts": "1710000000.000100",
            },
        )
    ]
    assert response_url_client.sent == []


async def test_slack_command_worker_includes_cli_resume_fallback_for_pending_approval() -> None:
    run_service = RecordingRunService(
        response="Approval required.",
        response_metadata={
            "approval_status": "pending",
            "approval_request": {
                "run_id": "run_1",
                "tenant_id": "tenant_1",
                "tool_id": "builtin:send_webhook",
                "tool_risk_level": "external_side_effect",
                "tool_timeout_ms": 15000,
                "requested_by": "U1",
            },
        },
    )
    approval_store = RecordingApprovalRequestStore()
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="1710000000.000100"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    worker = SlackSlashCommandWorker(
        run_service=run_service,
        response_url_client=RecordingResponseUrlClient(),
        messaging_client=messaging_client,
        approval_store=approval_store,
    )

    await worker.handle(
        SlackSlashCommandPayload(
            tenant_id="tenant_1",
            command="/reactor",
            text="send the webhook",
            user_id="U1",
            user_name="sample-user",
            channel_id="C1",
            channel_name="general",
            team_id="T1",
            response_url="https://hooks.slack.test/response",
            trigger_id="123.456",
            entrypoint="slash_command",
        )
    )

    assert "_Resume: `reactor-runs resume run_1 --approval-id approval_1 --output table`_" in str(
        messaging_client.sent[1][1]["text"]
    )


async def test_slack_command_worker_falls_back_to_response_url_when_question_post_fails() -> None:
    run_service = RecordingRunService(response="Fallback answer.")
    response_url_client = RecordingResponseUrlClient()
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=False, error="channel_not_found"),
        reply_result=SlackMessageSendResult(ok=True, ts="unused"),
    )
    worker = SlackSlashCommandWorker(
        run_service=run_service,
        response_url_client=response_url_client,
        messaging_client=messaging_client,
    )

    await worker.handle(
        SlackSlashCommandPayload(
            tenant_id="tenant_1",
            command="/reactor",
            text="fallback please",
            user_id="U1",
            user_name="sample-user",
            channel_id="C1",
            channel_name="general",
            team_id="T1",
            response_url="https://hooks.slack.test/response",
            trigger_id="123.456",
            entrypoint="slash_command",
        )
    )

    assert run_service.thread_ids == ["slack-cmd-C1-U1"]
    assert response_url_client.sent == [
        (
            "https://hooks.slack.test/response",
            {
                "response_type": "in_channel",
                "text": "",
                "attachments": [
                    {
                        "color": "#36a64f",
                        "text": "*<@U1> 님의 질문*\nfallback please",
                        "mrkdwn_in": ["text"],
                    }
                ],
            },
        ),
        (
            "https://hooks.slack.test/response",
            {
                "response_type": "in_channel",
                "text": (
                    "<@U1> Fallback answer.\n\n"
                    "_Run: `run_1`_\n"
                    "_Diagnose: `reactor-runs diagnose run_1 --output table`_\n"
                    "_Replay events: `reactor-runs replay run_1 --output table`_\n"
                    "_State history: `reactor-admin state-history run_1 --output table`_\n"
                    "_Feedback review: `reactor-admin feedback --rating thumbs_down "
                    "--review-status inbox --limit 10 "
                    "--output table`_"
                ),
            },
        ),
    ]


async def test_slack_command_worker_falls_back_when_thread_reply_fails() -> None:
    run_service = RecordingRunService(response="Thread answer.")
    response_url_client = RecordingResponseUrlClient()
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="1710000000.000100"),
        reply_result=SlackMessageSendResult(ok=False, error="rate_limited"),
    )
    worker = SlackSlashCommandWorker(
        run_service=run_service,
        response_url_client=response_url_client,
        messaging_client=messaging_client,
    )

    await worker.handle(
        SlackSlashCommandPayload(
            tenant_id="tenant_1",
            command="/reactor",
            text="reply fallback",
            user_id="U1",
            user_name=None,
            channel_id="C1",
            channel_name=None,
            team_id="T1",
            response_url="https://hooks.slack.test/response",
            trigger_id=None,
            entrypoint="slash_command",
        )
    )

    assert response_url_client.sent == [
        (
            "https://hooks.slack.test/response",
            {
                "response_type": "in_channel",
                "text": (
                    "<@U1> Thread answer.\n\n"
                    "_Run: `run_1`_\n"
                    "_Diagnose: `reactor-runs diagnose run_1 --output table`_\n"
                    "_Replay events: `reactor-runs replay run_1 --output table`_\n"
                    "_State history: `reactor-admin state-history run_1 --output table`_\n"
                    "_Feedback review: `reactor-admin feedback --rating thumbs_down "
                    "--review-status inbox --limit 10 "
                    "--output table`_"
                ),
            },
        )
    ]


async def test_slack_command_worker_rewrites_generic_refusal_before_replying() -> None:
    run_service = RecordingRunService(response="요청하신 작업을 수행할 수 없습니다")
    response_url_client = RecordingResponseUrlClient()
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="1710000000.000100"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    worker = SlackSlashCommandWorker(
        run_service=run_service,
        response_url_client=response_url_client,
        messaging_client=messaging_client,
    )

    await worker.handle(
        SlackSlashCommandPayload(
            tenant_id="tenant_1",
            command="/reactor",
            text="오늘 할 일 우선순위 알려줘",
            user_id="U1",
            user_name=None,
            channel_id="C1",
            channel_name=None,
            team_id="T1",
            response_url="https://hooks.slack.test/response",
            trigger_id=None,
            entrypoint="slash_command",
        )
    )

    reply = messaging_client.sent[-1][1]["text"]
    assert isinstance(reply, str)
    assert "바로 실행 가능한 초안으로 정리합니다." in reply
    assert "요청하신 작업을 수행할 수 없습니다" not in reply


async def test_slack_command_worker_prompts_for_blank_text_without_running_agent() -> None:
    run_service = RecordingRunService(response="unused")
    client = RecordingResponseUrlClient()
    worker = SlackSlashCommandWorker(run_service=run_service, response_url_client=client)

    await worker.handle(
        SlackSlashCommandPayload(
            tenant_id="tenant_1",
            command="/reactor",
            text="   ",
            user_id="U1",
            user_name=None,
            channel_id="C1",
            channel_name=None,
            team_id="T1",
            response_url="https://hooks.slack.test/response",
            trigger_id=None,
            entrypoint="slash_command",
        )
    )

    assert run_service.messages == []
    assert client.sent == [
        (
            "https://hooks.slack.test/response",
            {
                "response_type": "ephemeral",
                "text": "Please enter a question. Example: /reactor What are my tasks today?",
            },
        )
    ]


async def test_slack_command_worker_handles_help_without_running_agent() -> None:
    run_service = RecordingRunService(response="unused")
    client = RecordingResponseUrlClient()
    worker = SlackSlashCommandWorker(run_service=run_service, response_url_client=client)

    await worker.handle(
        SlackSlashCommandPayload(
            tenant_id="tenant_1",
            command="/reactor",
            text="help",
            user_id="U1",
            user_name=None,
            channel_id="C1",
            channel_name=None,
            team_id="T1",
            response_url="https://hooks.slack.test/response",
            trigger_id=None,
            entrypoint="slash_command",
        )
    )

    assert run_service.messages == []
    assert client.sent == [
        (
            "https://hooks.slack.test/response",
            {
                "response_type": "ephemeral",
                "text": (
                    "*Reactor Commands*\n\n"
                    "*General*\n"
                    "`/reactor <question>` - Ask the agent.\n"
                    "`/reactor help` - Show this help message.\n\n"
                    "*Daily Productivity*\n"
                    "`/reactor brief [focus]` - Daily brief with priorities and risk check.\n"
                    "`/reactor my-work [scope]` - Work status summary.\n\n"
                    "*After a Run*\n"
                    "`reactor-runs diagnose <run_id> --output table` - Inspect status and safe "
                    "metadata.\n"
                    "`reactor-runs replay <run_id> --output table` - Review replayable event "
                    "history.\n"
                    "`reactor-admin state-history <run_id> --output table` - Inspect graph state "
                    "history.\n"
                    "Copy the run id from the bot reply.\n\n"
                    "*Tips*\n"
                    "- Mention the bot in a channel for a threaded conversation.\n"
                    "- React to bot responses to provide feedback."
                ),
            },
        )
    ]


async def test_slack_command_worker_rewrites_brief_and_tags_intent_metadata() -> None:
    run_service = RecordingRunService(response="brief done")
    response_url_client = RecordingResponseUrlClient()
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="1710000000.000100"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    worker = SlackSlashCommandWorker(
        run_service=run_service,
        response_url_client=response_url_client,
        messaging_client=messaging_client,
    )

    await worker.handle(
        SlackSlashCommandPayload(
            tenant_id="tenant_1",
            command="/reactor",
            text="brief release handoff",
            user_id="U1",
            user_name="sample-user",
            channel_id="C1",
            channel_name="general",
            team_id="T1",
            response_url="https://hooks.slack.test/response",
            trigger_id="123.456",
            entrypoint="slash_command",
        )
    )

    assert "Create a personal daily brief for the user." in run_service.messages[0]
    assert "Focus: release handoff" in run_service.messages[0]
    assert run_service.metadata[0]["intent"] == "brief"


async def test_slack_command_worker_rewrites_my_work_and_tags_intent_metadata() -> None:
    run_service = RecordingRunService(response="my work")
    response_url_client = RecordingResponseUrlClient()
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=False, error="not_in_channel"),
        reply_result=SlackMessageSendResult(ok=True, ts="unused"),
    )
    worker = SlackSlashCommandWorker(
        run_service=run_service,
        response_url_client=response_url_client,
        messaging_client=messaging_client,
    )

    await worker.handle(
        SlackSlashCommandPayload(
            tenant_id="tenant_1",
            command="/reactor",
            text="my-work sprint board",
            user_id="U1",
            user_name="sample-user",
            channel_id="C1",
            channel_name="general",
            team_id="T1",
            response_url="https://hooks.slack.test/response",
            trigger_id="123.456",
            entrypoint="slash_command",
        )
    )

    assert "Summarize my work status as my personal assistant." in run_service.messages[0]
    assert "Scope: sprint board" in run_service.messages[0]
    assert run_service.metadata[0]["intent"] == "my_work"


async def test_slack_command_worker_adds_reminder_without_running_agent() -> None:
    run_service = RecordingRunService(response="unused")
    client = RecordingResponseUrlClient()
    store = InMemorySlackReminderStore()
    worker = SlackSlashCommandWorker(
        run_service=run_service,
        response_url_client=client,
        reminder_store=store,
    )

    await worker.handle(
        SlackSlashCommandPayload(
            tenant_id="tenant_1",
            command="/reactor",
            text="remind Submit PTO by Friday",
            user_id="U1",
            user_name=None,
            channel_id="C1",
            channel_name=None,
            team_id="T1",
            response_url="https://hooks.slack.test/response",
            trigger_id=None,
            entrypoint="slash_command",
        )
    )

    assert run_service.messages == []
    assert [reminder.text for reminder in store.list("U1")] == ["Submit PTO by Friday"]
    assert client.sent == [
        (
            "https://hooks.slack.test/response",
            {
                "response_type": "ephemeral",
                "text": "Saved reminder #1: Submit PTO by Friday",
            },
        )
    ]


async def test_slack_command_worker_lists_completes_and_clears_reminders_without_agent() -> None:
    run_service = RecordingRunService(response="unused")
    client = RecordingResponseUrlClient()
    store = InMemorySlackReminderStore()
    store.add("U1", "A")
    store.add("U1", "B")
    worker = SlackSlashCommandWorker(
        run_service=run_service,
        response_url_client=client,
        reminder_store=store,
    )

    await worker.handle(slack_command_payload(text="remind list"))
    await worker.handle(slack_command_payload(text="remind done 1"))
    await worker.handle(slack_command_payload(text="remind clear"))

    assert run_service.messages == []
    assert client.sent == [
        (
            "https://hooks.slack.test/response",
            {"response_type": "ephemeral", "text": "Your reminders:\n- #1 A\n- #2 B"},
        ),
        (
            "https://hooks.slack.test/response",
            {"response_type": "ephemeral", "text": "Completed reminder #1: A"},
        ),
        (
            "https://hooks.slack.test/response",
            {"response_type": "ephemeral", "text": "Cleared 1 reminder(s)."},
        ),
    ]


async def test_slack_command_worker_reports_reminder_unavailable_without_agent() -> None:
    run_service = RecordingRunService(response="unused")
    client = RecordingResponseUrlClient()
    worker = SlackSlashCommandWorker(run_service=run_service, response_url_client=client)

    await worker.handle(
        SlackSlashCommandPayload(
            tenant_id="tenant_1",
            command="/reactor",
            text="remind list",
            user_id="U1",
            user_name=None,
            channel_id="C1",
            channel_name=None,
            team_id="T1",
            response_url="https://hooks.slack.test/response",
            trigger_id=None,
            entrypoint="slash_command",
        )
    )

    assert run_service.messages == []
    assert client.sent == [
        (
            "https://hooks.slack.test/response",
            {
                "response_type": "ephemeral",
                "text": "Reminder feature is temporarily unavailable. Please try again later.",
            },
        )
    ]


async def test_slack_command_worker_reports_agent_failure_to_response_url() -> None:
    client = RecordingResponseUrlClient()
    worker = SlackSlashCommandWorker(
        run_service=RaisingRunService(),
        response_url_client=client,
    )

    await worker.handle(
        SlackSlashCommandPayload(
            tenant_id="tenant_1",
            command="/reactor",
            text="fail",
            user_id="U1",
            user_name=None,
            channel_id="C1",
            channel_name=None,
            team_id="T1",
            response_url="https://hooks.slack.test/response",
            trigger_id=None,
            entrypoint="slash_command",
        )
    )

    assert client.sent == [
        (
            "https://hooks.slack.test/response",
            {
                "response_type": "in_channel",
                "text": "",
                "attachments": [
                    {
                        "color": "#36a64f",
                        "text": "*<@U1> 님의 질문*\nfail",
                        "mrkdwn_in": ["text"],
                    }
                ],
            },
        ),
        (
            "https://hooks.slack.test/response",
            {
                "response_type": "ephemeral",
                "text": ":x: 내부 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            },
        ),
    ]


async def test_slack_command_worker_rate_limits_user_before_running_agent() -> None:
    run_service = RecordingRunService(response="unused")
    client = RecordingResponseUrlClient()
    worker = SlackSlashCommandWorker(
        run_service=run_service,
        response_url_client=client,
        rate_limiter=InMemorySlackUserRateLimiter(max_requests_per_window=1),
    )

    await worker.handle(slack_command_payload(text="first request"))
    await worker.handle(slack_command_payload(text="second request"))

    assert run_service.messages == ["first request"]
    assert client.sent[-1] == (
        "https://hooks.slack.test/response",
        {
            "response_type": "ephemeral",
            "text": (
                ":no_entry: You are sending requests too quickly. "
                "Please wait a moment and try again."
            ),
        },
    )


async def test_slack_command_worker_awaits_async_rate_limiter_before_running_agent() -> None:
    run_service = RecordingRunService(response="unused")
    client = RecordingResponseUrlClient()
    worker = SlackSlashCommandWorker(
        run_service=run_service,
        response_url_client=client,
        rate_limiter=AsyncDenyingRateLimiter(),
    )

    await worker.handle(slack_command_payload(text="blocked request"))

    assert run_service.messages == []
    assert client.sent == [
        (
            "https://hooks.slack.test/response",
            {
                "response_type": "ephemeral",
                "text": (
                    ":no_entry: You are sending requests too quickly. "
                    "Please wait a moment and try again."
                ),
            },
        )
    ]


async def test_slack_command_worker_passes_tenant_to_rate_limiter() -> None:
    run_service = RecordingRunService(response="ok")
    client = RecordingResponseUrlClient()
    limiter = RecordingRateLimiter()
    worker = SlackSlashCommandWorker(
        run_service=run_service,
        response_url_client=client,
        rate_limiter=limiter,
    )

    await worker.handle(slack_command_payload(tenant_id="tenant_a", user_id="U1", text="hello"))

    assert limiter.calls == [("tenant_a", "U1")]
    assert run_service.messages == ["hello"]


async def test_slack_command_worker_rejects_when_backpressure_saturated() -> None:
    run_service = RecordingRunService(response="unused")
    client = RecordingResponseUrlClient()
    limiter = SlackBackpressureLimiter(
        max_concurrent_requests=1,
        request_timeout_seconds=0,
        fail_fast_on_saturation=True,
    )
    assert await limiter.acquire() is True
    worker = SlackSlashCommandWorker(
        run_service=run_service,
        response_url_client=client,
        backpressure_limiter=limiter,
    )

    await worker.handle(slack_command_payload(text="second request"))

    assert run_service.messages == []
    assert client.sent == [
        (
            "https://hooks.slack.test/response",
            {
                "response_type": "ephemeral",
                "text": (
                    ":hourglass_flowing_sand: Reactor is handling too many Slack "
                    "requests right now. Please try again shortly."
                ),
            },
        )
    ]


def test_slack_command_payload_maps_outbox_payload() -> None:
    payload = SlackSlashCommandPayload.from_outbox_payload(
        {
            "entrypoint": "slash_command",
            "command": {
                "command": "/reactor",
                "text": "help",
                "userId": "U1",
                "userName": "sample-user",
                "channelId": "C1",
                "channelName": "general",
                "teamId": "T1",
                "responseUrl": "https://hooks.slack.test/response",
                "triggerId": "123.456",
            },
        },
        tenant_id="tenant_1",
    )

    assert payload.tenant_id == "tenant_1"
    assert payload.text == "help"
    assert payload.response_url == "https://hooks.slack.test/response"


def test_slack_event_payload_maps_event_callback_outbox_payload() -> None:
    payload = SlackEventPayload.from_outbox_payload(
        {
            "entrypoint": "events_api",
            "payload": {
                "event_id": "Ev123",
                "team_id": "T1",
                "event": {
                    "type": "app_mention",
                    "user": "U1",
                    "channel": "C1",
                    "text": "<@UBOT> help me",
                    "ts": "1710000000.000100",
                    "thread_ts": "1710000000.000000",
                    "channel_type": "channel",
                },
            },
        },
        tenant_id="tenant_1",
    )

    assert payload.tenant_id == "tenant_1"
    assert payload.event_type == "app_mention"
    assert payload.user_id == "U1"
    assert payload.channel_id == "C1"
    assert payload.clean_text == "help me"
    assert payload.thread_ts == "1710000000.000000"
    assert payload.is_mention is True


def test_slack_event_payload_maps_bot_message_without_user_for_drop_policy() -> None:
    payload = SlackEventPayload.from_outbox_payload(
        {
            "entrypoint": "events_api",
            "payload": {
                "event_id": "EvBotMessage",
                "team_id": "T1",
                "event": {
                    "type": "message",
                    "subtype": "bot_message",
                    "bot_id": "B1",
                    "channel": "C1",
                    "text": "bot echo",
                    "ts": "1710000000.000100",
                    "channel_type": "channel",
                },
            },
        },
        tenant_id="tenant_1",
    )

    assert payload.event_type == "message"
    assert payload.user_id == ""
    assert payload.bot_id == "B1"
    assert payload.subtype == "bot_message"
    assert payload.is_bot_message is True


def test_slack_event_payload_maps_reaction_feedback_outbox_payload() -> None:
    payload = SlackEventPayload.from_outbox_payload(
        {
            "entrypoint": "events_api",
            "payload": {
                "event_id": "EvReaction",
                "team_id": "T1",
                "event": {
                    "type": "reaction_added",
                    "user": "U2",
                    "reaction": "+1",
                    "item": {
                        "type": "message",
                        "channel": "C1",
                        "ts": "1710000001.000200",
                    },
                },
            },
        },
        tenant_id="tenant_1",
    )

    assert payload.event_type == "reaction_added"
    assert payload.user_id == "U2"
    assert payload.channel_id == "C1"
    assert payload.ts == "1710000001.000200"
    assert payload.reaction == "+1"


def test_slack_event_payload_maps_assistant_thread_lifecycle_outbox_payload() -> None:
    payload = SlackEventPayload.from_outbox_payload(
        {
            "entrypoint": "socket_mode_events",
            "payload": {
                "event_id": "EvAssistantStarted",
                "team_id": "T1",
                "event": {
                    "type": "assistant_thread_started",
                    "assistant_thread": {
                        "channel_id": "D123",
                        "thread_ts": "1710000002.000300",
                        "user_id": "U1",
                        "context": {"channel_id": "C_CONTEXT"},
                    },
                },
            },
        },
        tenant_id="tenant_1",
    )

    assert payload.event_type == "assistant_thread_started"
    assert payload.user_id == "U1"
    assert payload.channel_id == "D123"
    assert payload.ts == "1710000002.000300"
    assert payload.thread_ts == "1710000002.000300"
    assert payload.channel_type == "im"
    assert payload.assistant_context_channel_id == "C_CONTEXT"
    assert payload.entrypoint == "socket_mode_events"


async def test_slack_event_worker_records_assistant_thread_context_and_sets_status() -> None:
    run_service = RecordingRunService(response="Assistant answer.")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000003.000400"),
    )
    assistant_context_store = InMemorySlackAssistantThreadContextStore()
    assistant_status_client = RecordingSlackAssistantStatusClient()
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        assistant_context_store=assistant_context_store,
        assistant_status_client=assistant_status_client,
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="assistant_thread_started",
            user_id="U1",
            channel_id="D123",
            text="",
            ts="1710000002.000300",
            thread_ts="1710000002.000300",
            channel_type="im",
            assistant_context_channel_id="C_CONTEXT",
            assistant_context_team_id="T1",
            entrypoint="socket_mode_events",
        )
    )
    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="message",
            user_id="U1",
            channel_id="D123",
            text="assistant question",
            ts="1710000002.500000",
            thread_ts="1710000002.000300",
            channel_type="im",
            entrypoint="events_api",
        )
    )

    assert run_service.messages == ["assistant question"]
    assert run_service.metadata[0]["slackAssistantContext"] == {
        "assistantChannelId": "D123",
        "threadTs": "1710000002.000300",
        "userId": "U1",
        "channelId": "C_CONTEXT",
        "teamId": "T1",
        "enterpriseId": None,
    }
    assert assistant_status_client.calls == [
        ("D123", "1710000002.000300", "is thinking..."),
        ("D123", "1710000002.000300", ""),
    ]


async def test_slack_event_worker_posts_approval_buttons_for_pending_approval() -> None:
    run_service = RecordingRunService(
        response="Approval required.",
        response_metadata={
            "approval_status": "pending",
            "approval_request": {
                "run_id": "run_1",
                "tenant_id": "tenant_1",
                "tool_id": "builtin:send_webhook",
                "tool_risk_level": "external_side_effect",
                "tool_timeout_ms": 15000,
                "requested_by": "U1",
                "input_payload": {"url": "https://example.com"},
            },
        },
    )
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    approval_store = RecordingApprovalRequestStore()
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        approval_store=approval_store,
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="app_mention",
            user_id="U1",
            channel_id="C1",
            text="<@B1> send the webhook",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )

    assert messaging_client.sent == [
        (
            "C1",
            {
                "text": (
                    "<@U1> Approval required.\n\n"
                    "_Run: `run_1`_\n"
                    "_Diagnose: `reactor-runs diagnose run_1 --output table`_\n"
                    "_Replay events: `reactor-runs replay run_1 --output table`_\n"
                    "_State history: `reactor-admin state-history run_1 --output table`_\n"
                    "_Feedback review: `reactor-admin feedback --rating thumbs_down "
                    "--review-status inbox --limit 10 "
                    "--output table`_\n"
                    "_Resume: `reactor-runs resume run_1 --approval-id approval_1 --output table`_"
                ),
                "thread_ts": "1710000000.000100",
                "attachments": None,
                "blocks": expected_approval_blocks(),
            },
        )
    ]
    assert approval_store.requests == [
        (
            "tenant_1",
            "run_1",
            "builtin:send_webhook",
            "U1",
            {
                "run_id": "run_1",
                "tenant_id": "tenant_1",
                "tool_id": "builtin:send_webhook",
                "tool_risk_level": "external_side_effect",
                "tool_timeout_ms": 15000,
                "requested_by": "U1",
                "input_payload": {"url": "https://example.com"},
                "slack_channel_id": "C1",
                "slack_thread_ts": "1710000000.000100",
            },
        )
    ]


async def test_slack_event_worker_uses_faq_fast_path_before_agent() -> None:
    run_service = RecordingRunService(response="unused")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    responder = RecordingFaqResponder(
        reply=FakeFaqAutoReply(
            text="FAQ 정답 본문",
            score=0.95,
            threshold=0.8,
            matched_document_ids=["doc_1"],
        )
    )
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        faq_responder=responder,
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="app_mention",
            user_id="U1",
            channel_id="C1",
            text="<@UBOT> help me",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )

    assert run_service.messages == []
    assert responder.calls == [("tenant_1", "C1", "U1", "help me", True)]
    assert messaging_client.sent == [
        (
            "C1",
            {
                "text": "<@U1> FAQ 정답 본문",
                "thread_ts": "1710000000.000100",
                "attachments": None,
            },
        )
    ]


async def test_slack_event_worker_raises_retryable_error_on_rate_limited_thread_reply() -> None:
    run_service = RecordingRunService(response="Here is the answer.")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(
            ok=False,
            error="rate_limited",
            retry_after_seconds=7,
        ),
    )
    worker = SlackEventWorker(run_service=run_service, messaging_client=messaging_client)

    with pytest.raises(SlackRetryableSendError) as error:
        await worker.handle(
            SlackEventPayload(
                tenant_id="tenant_1",
                event_type="app_mention",
                user_id="U1",
                channel_id="C1",
                text="<@UBOT> help me",
                ts="1710000000.000100",
                thread_ts=None,
                channel_type="channel",
                entrypoint="events_api",
            )
        )

    assert str(error.value) == "rate_limited"
    assert error.value.retry_after_seconds == 7


async def test_slack_event_worker_records_reaction_feedback_for_tracked_faq_reply() -> None:
    run_service = RecordingRunService(response="unused")
    metrics = InMemorySlackFaqMetrics()
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        faq_responder=RecordingFaqResponder(
            reply=FakeFaqAutoReply(
                text="FAQ 정답 본문",
                score=0.95,
                threshold=0.8,
                matched_document_ids=["doc_1", "doc_2"],
            )
        ),
        faq_metrics=metrics,
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="app_mention",
            user_id="U1",
            channel_id="C1",
            text="<@UBOT> help me",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )
    reaction = SlackEventPayload(
        tenant_id="tenant_1",
        event_type="reaction_added",
        user_id="U2",
        channel_id="C1",
        text="",
        ts="1710000001.000200",
        thread_ts=None,
        channel_type=None,
        reaction="+1",
        entrypoint="events_api",
    )
    await worker.handle(reaction)
    await worker.handle(reaction)

    feedback = metrics.feedback_snapshot("C1")
    assert feedback["doc_1"].thumbs_up == 1
    assert feedback["doc_2"].thumbs_up == 1
    assert run_service.messages == []


def test_slack_faq_feedback_dedupe_uses_bounded_recent_event_window() -> None:
    metrics = InMemorySlackFaqMetrics(recent_limit=2)

    metrics.record_feedback("C1", ["doc_1"], True, event_id="event_1")
    metrics.record_feedback("C1", ["doc_1"], True, event_id="event_2")
    metrics.record_feedback("C1", ["doc_1"], True, event_id="event_3")
    metrics.record_feedback("C1", ["doc_1"], True, event_id="event_2")
    metrics.record_feedback("C1", ["doc_1"], True, event_id="event_3")
    metrics.record_feedback("C1", ["doc_1"], True, event_id="event_1")

    feedback = metrics.feedback_snapshot("C1")
    assert feedback["doc_1"].thumbs_up == 4


def test_slack_faq_reply_doc_tracking_uses_bounded_recent_window() -> None:
    metrics = InMemorySlackFaqMetrics(recent_limit=2)

    metrics.track_reply("C1", "1710000001.000100", ["doc_1"])
    metrics.track_reply("C1", "1710000002.000200", ["doc_2"])
    metrics.track_reply("C1", "1710000003.000300", ["doc_3"])

    assert metrics.doc_ids_for_reply("C1", "1710000001.000100") == []
    assert metrics.doc_ids_for_reply("C1", "1710000002.000200") == ["doc_2"]
    assert metrics.doc_ids_for_reply("C1", "1710000003.000300") == ["doc_3"]


async def test_slack_event_worker_records_reaction_feedback_for_tracked_agent_reply() -> None:
    run_service = RecordingRunService(
        response="The answer omitted the citation.",
        response_metadata={
            "prompt_version": 7,
            "toolsUsed": ["Rag:hybrid_search"],
        },
    )
    feedback_store = InMemoryFeedbackStore()
    bot_response_tracker = InMemoryBotResponseTracker()
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        bot_response_tracker=bot_response_tracker,
        feedback_store=feedback_store,
        faq_responder=RecordingFaqResponder(reply=None),
        event_policy=SlackEventPolicy(free_response_channel_ids=frozenset({"C1"})),
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="message",
            user_id="U1",
            channel_id="C1",
            text="Where is the source?",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )
    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="reaction_added",
            user_id="U2",
            channel_id="C1",
            text="",
            ts="1710000001.000200",
            thread_ts=None,
            channel_type=None,
            reaction="-1",
            entrypoint="events_api",
        )
    )

    assert len(feedback_store.records) == 1
    feedback = feedback_store.records[0]
    assert feedback.source == "slack_reaction"
    assert feedback.query == "Where is the source?"
    assert feedback.response == "The answer omitted the citation."
    assert feedback.rating == FeedbackRating.THUMBS_DOWN
    assert feedback.session_id == "slack-C1-1710000000.000100"
    assert feedback.run_id == "run_1"
    assert feedback.user_id == "U1"
    assert feedback.tenant_id == "tenant_1"
    assert feedback.tags == [
        "slack",
        "agent-run",
        "rag",
        "grounding",
        "citation-failure",
    ]
    assert feedback.template_id == "slack-agent-run"
    assert feedback.model == "gpt-5-mini"
    assert feedback.prompt_version == 7
    assert feedback.tools_used == ["Rag:hybrid_search"]


async def test_slack_event_worker_records_reaction_feedback_memory_handoff() -> None:
    run_service = RecordingRunService(
        response="I forgot the preference you asked me to remember.",
        response_metadata={"prompt_version": 7},
    )
    feedback_store = InMemoryFeedbackStore()
    bot_response_tracker = InMemoryBotResponseTracker()
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        bot_response_tracker=bot_response_tracker,
        feedback_store=feedback_store,
        faq_responder=RecordingFaqResponder(reply=None),
        event_policy=SlackEventPolicy(free_response_channel_ids=frozenset({"C1"})),
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="message",
            user_id="U1",
            channel_id="C1",
            text="Remember that I prefer short Korean answers.",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )
    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="reaction_added",
            user_id="U2",
            channel_id="C1",
            text="",
            ts="1710000001.000200",
            thread_ts=None,
            channel_type=None,
            reaction="-1",
            entrypoint="events_api",
        )
    )

    assert len(feedback_store.records) == 1
    feedback = feedback_store.records[0]
    assert feedback.source == "slack_reaction"
    assert feedback.user_id == "U1"
    assert feedback.query == "Remember that I prefer short Korean answers."
    assert feedback.rating == FeedbackRating.THUMBS_DOWN
    assert feedback.tags == ["slack", "agent-run", "memory"]


async def test_slack_event_worker_deduplicates_replayed_agent_reaction_feedback() -> None:
    run_service = RecordingRunService(response="Agent answer.")
    feedback_store = InMemoryFeedbackStore()
    bot_response_tracker = InMemoryBotResponseTracker()
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        bot_response_tracker=bot_response_tracker,
        feedback_store=feedback_store,
        faq_responder=RecordingFaqResponder(reply=None),
        event_policy=SlackEventPolicy(free_response_channel_ids=frozenset({"C1"})),
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="message",
            user_id="U1",
            channel_id="C1",
            text="일반 질문",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )
    reaction = SlackEventPayload(
        tenant_id="tenant_1",
        event_type="reaction_added",
        user_id="U2",
        channel_id="C1",
        text="",
        ts="1710000001.000200",
        thread_ts=None,
        channel_type=None,
        reaction="-1",
        entrypoint="events_api",
    )

    await worker.handle(reaction)
    await worker.handle(reaction)

    assert len(feedback_store.records) == 1
    feedback_id = feedback_store.records[0].feedback_id
    assert feedback_id.startswith("slack-reaction:")
    assert feedback_id != "slack-reaction:tenant_1:C1:1710000001.000200:U2:-1"
    assert "tenant_1" not in feedback_id
    assert "C1" not in feedback_id
    assert "U2" not in feedback_id
    assert "1710000001" not in feedback_id
    assert "-1" not in feedback_id


async def test_slack_event_worker_falls_back_to_agent_when_faq_misses() -> None:
    run_service = RecordingRunService(response="Agent answer.")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        faq_responder=RecordingFaqResponder(reply=None),
        event_policy=SlackEventPolicy(free_response_channel_ids=frozenset({"C1"})),
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="message",
            user_id="U1",
            channel_id="C1",
            text="일반 질문",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )

    assert run_service.messages == ["일반 질문"]
    assert run_service.thread_ids == ["slack-C1-1710000000.000100"]
    assert run_service.metadata[0]["entrypoint"] == "events_api"
    assert run_service.metadata[0]["slackEventType"] == "message"
    assert messaging_client.sent == [
        (
            "C1",
            {
                "text": (
                    "<@U1> Agent answer.\n\n"
                    "_Run: `run_1`_\n"
                    "_Diagnose: `reactor-runs diagnose run_1 --output table`_\n"
                    "_Replay events: `reactor-runs replay run_1 --output table`_\n"
                    "_State history: `reactor-admin state-history run_1 --output table`_\n"
                    "_Feedback review: `reactor-admin feedback --rating thumbs_down "
                    "--review-status inbox --limit 10 "
                    "--output table`_"
                ),
                "thread_ts": "1710000000.000100",
                "attachments": None,
            },
        )
    ]


async def test_slack_event_worker_tracks_agent_reply_for_feedback_buttons() -> None:
    run_service = RecordingRunService(
        response="Agent answer.",
        response_metadata={
            "prompt_version": 7,
            "toolsUsed": ["Rag:hybrid_search"],
        },
    )
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    bot_response_tracker = InMemoryBotResponseTracker()
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        bot_response_tracker=bot_response_tracker,
        faq_responder=RecordingFaqResponder(reply=None),
        event_policy=SlackEventPolicy(free_response_channel_ids=frozenset({"C1"})),
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="message",
            user_id="U1",
            channel_id="C1",
            text="일반 질문",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )

    tracked = bot_response_tracker.lookup("C1", "1710000001.000200")
    assert tracked is not None
    assert tracked.session_id == "slack-C1-1710000000.000100"
    assert tracked.user_prompt == "일반 질문"
    assert tracked.user_id == "U1"
    assert tracked.response == "Agent answer."
    assert tracked.run_id == "run_1"
    assert tracked.tags == ["slack", "agent-run"]
    assert tracked.template_id == "slack-agent-run"
    assert tracked.model == "gpt-5-mini"
    assert tracked.prompt_version == 7
    assert tracked.tools_used == ["Rag:hybrid_search"]
    assert messaging_client.sent[0][1]["blocks"] == expected_feedback_blocks()


async def test_slack_event_worker_ignores_unmentioned_channel_message_by_default() -> None:
    run_service = RecordingRunService(response="unused")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="unused"),
    )
    responder = RecordingFaqResponder(reply=None)
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        faq_responder=responder,
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="message",
            user_id="U1",
            channel_id="C1",
            text="일반 채널 메시지",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )

    assert run_service.messages == []
    assert responder.calls == []
    assert messaging_client.sent == []


async def test_slack_event_worker_allows_follow_up_in_thread_after_bot_participates() -> None:
    run_service = RecordingRunService(response="Agent answer.")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    tracker = RecordingThreadParticipationTracker()
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        faq_responder=RecordingFaqResponder(reply=None),
        thread_participation_tracker=tracker,
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="app_mention",
            user_id="U1",
            channel_id="C1",
            text="<@UBOT> initial question",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )
    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="message",
            user_id="U1",
            channel_id="C1",
            text="follow up without mention",
            ts="1710000002.000300",
            thread_ts="1710000000.000100",
            channel_type="channel",
            entrypoint="events_api",
        )
    )

    assert run_service.messages == ["initial question", "follow up without mention"]
    assert run_service.thread_ids == [
        "slack-C1-1710000000.000100",
        "slack-C1-1710000000.000100",
    ]
    assert tracker.recorded == [
        ("tenant_1", "C1", "1710000000.000100"),
        ("tenant_1", "C1", "1710000000.000100"),
    ]
    assert tracker.checked == [("tenant_1", "C1", "1710000000.000100")]
    assert messaging_client.sent == [
        (
            "C1",
            {
                "text": (
                    "<@U1> Agent answer.\n\n"
                    "_Run: `run_1`_\n"
                    "_Diagnose: `reactor-runs diagnose run_1 --output table`_\n"
                    "_Replay events: `reactor-runs replay run_1 --output table`_\n"
                    "_State history: `reactor-admin state-history run_1 --output table`_\n"
                    "_Feedback review: `reactor-admin feedback --rating thumbs_down "
                    "--review-status inbox --limit 10 "
                    "--output table`_"
                ),
                "thread_ts": "1710000000.000100",
                "attachments": None,
            },
        ),
        (
            "C1",
            {
                "text": (
                    "<@U1> Agent answer.\n\n"
                    "_Run: `run_1`_\n"
                    "_Diagnose: `reactor-runs diagnose run_1 --output table`_\n"
                    "_Replay events: `reactor-runs replay run_1 --output table`_\n"
                    "_State history: `reactor-admin state-history run_1 --output table`_\n"
                    "_Feedback review: `reactor-admin feedback --rating thumbs_down "
                    "--review-status inbox --limit 10 "
                    "--output table`_"
                ),
                "thread_ts": "1710000000.000100",
                "attachments": None,
            },
        ),
    ]


async def test_slack_event_worker_allows_follow_up_from_durable_thread_participation() -> None:
    run_service = RecordingRunService(response="Restart-safe answer.")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000003.000400"),
    )
    tracker = RunStoreSlackThreadParticipationTracker(
        run_store=FakeSlackThreadRunLookup(existing={("tenant_1", "slack-C1-1710000000.000100")})
    )
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        faq_responder=RecordingFaqResponder(reply=None),
        thread_participation_tracker=tracker,
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="message",
            user_id="U1",
            channel_id="C1",
            text="restart follow up without mention",
            ts="1710000002.000300",
            thread_ts="1710000000.000100",
            channel_type="channel",
            entrypoint="events_api",
        )
    )

    assert run_service.messages == ["restart follow up without mention"]
    assert run_service.thread_ids == ["slack-C1-1710000000.000100"]
    assert messaging_client.sent == [
        (
            "C1",
            {
                "text": (
                    "<@U1> Restart-safe answer.\n\n"
                    "_Run: `run_1`_\n"
                    "_Diagnose: `reactor-runs diagnose run_1 --output table`_\n"
                    "_Replay events: `reactor-runs replay run_1 --output table`_\n"
                    "_State history: `reactor-admin state-history run_1 --output table`_\n"
                    "_Feedback review: `reactor-admin feedback --rating thumbs_down "
                    "--review-status inbox --limit 10 "
                    "--output table`_"
                ),
                "thread_ts": "1710000000.000100",
                "attachments": None,
            },
        )
    ]


async def test_slack_event_worker_hydrates_thread_context_for_first_thread_mention() -> None:
    run_service = RecordingRunService(response="Contextual answer.")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000003.000400"),
    )
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        faq_responder=RecordingFaqResponder(reply=None),
        thread_context_client=RecordingSlackThreadContextClient(
            messages=[
                SlackThreadMessage(
                    ts="1710000000.000100",
                    user_id="U_PARENT",
                    text="original production incident",
                ),
                SlackThreadMessage(
                    ts="1710000001.000200",
                    user_id="U2",
                    text="database saturation details",
                ),
                SlackThreadMessage(
                    ts="1710000002.000300",
                    user_id="U1",
                    text="<@UBOT> summarize mitigation",
                ),
            ]
        ),
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="app_mention",
            user_id="U1",
            channel_id="C1",
            text="<@UBOT> summarize mitigation",
            ts="1710000002.000300",
            thread_ts="1710000000.000100",
            channel_type="channel",
            entrypoint="events_api",
        )
    )

    assert run_service.messages == [
        (
            "[Slack thread context]\n"
            "- <@U_PARENT>: original production incident\n"
            "- <@U2>: database saturation details\n"
            "[Current Slack message]\n"
            "summarize mitigation"
        )
    ]


async def test_slack_event_worker_skips_thread_context_when_thread_already_participated() -> None:
    run_service = RecordingRunService(response="No duplicate context.")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000003.000400"),
    )
    tracker = RecordingThreadParticipationTracker()
    await tracker.record_participation(
        tenant_id="tenant_1",
        channel_id="C1",
        thread_ts="1710000000.000100",
    )
    context_client = RecordingSlackThreadContextClient(
        messages=[
            SlackThreadMessage(
                ts="1710000000.000100",
                user_id="U_PARENT",
                text="should not be fetched",
            )
        ]
    )
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        faq_responder=RecordingFaqResponder(reply=None),
        thread_participation_tracker=tracker,
        thread_context_client=context_client,
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="app_mention",
            user_id="U1",
            channel_id="C1",
            text="<@UBOT> already in context",
            ts="1710000002.000300",
            thread_ts="1710000000.000100",
            channel_type="channel",
            entrypoint="events_api",
        )
    )

    assert context_client.calls == []
    assert run_service.messages == ["already in context"]


async def test_slack_event_worker_ignores_bot_messages_before_policy_and_rate_limit() -> None:
    run_service = RecordingRunService(response="unused")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="unused"),
    )
    limiter = RecordingRateLimiter()
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        rate_limiter=limiter,
        event_policy=SlackEventPolicy(free_response_channel_ids=frozenset({"C1"})),
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="message",
            user_id="",
            channel_id="C1",
            text="bot echo",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            bot_id="B1",
            subtype="bot_message",
            entrypoint="events_api",
        )
    )

    assert run_service.messages == []
    assert limiter.calls == []
    assert messaging_client.sent == []


async def test_slack_event_worker_allows_dm_without_mention() -> None:
    run_service = RecordingRunService(response="DM answer.")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    worker = SlackEventWorker(run_service=run_service, messaging_client=messaging_client)

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="message",
            user_id="U1",
            channel_id="D1",
            text="DM 질문",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="im",
            entrypoint="events_api",
        )
    )

    assert run_service.messages == ["DM 질문"]
    assert run_service.thread_ids == ["slack-D1-1710000000.000100"]
    assert messaging_client.sent == [
        (
            "D1",
            {
                "text": (
                    "<@U1> DM answer.\n\n"
                    "_Run: `run_1`_\n"
                    "_Diagnose: `reactor-runs diagnose run_1 --output table`_\n"
                    "_Replay events: `reactor-runs replay run_1 --output table`_\n"
                    "_State history: `reactor-admin state-history run_1 --output table`_\n"
                    "_Feedback review: `reactor-admin feedback --rating thumbs_down "
                    "--review-status inbox --limit 10 "
                    "--output table`_"
                ),
                "thread_ts": "1710000000.000100",
                "attachments": None,
            },
        )
    ]


async def test_slack_event_worker_blocks_disallowed_user_before_rate_limit_and_agent() -> None:
    run_service = RecordingRunService(response="unused")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="unused"),
    )
    limiter = RecordingRateLimiter()
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        rate_limiter=limiter,
        event_policy=SlackEventPolicy(allowed_user_ids=frozenset({"U_ALLOWED"})),
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="app_mention",
            user_id="U_BLOCKED",
            channel_id="C1",
            text="<@UBOT> should not run",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )

    assert run_service.messages == []
    assert limiter.calls == []
    assert messaging_client.sent == []


async def test_slack_event_worker_blocks_channel_outside_allowlist() -> None:
    run_service = RecordingRunService(response="unused")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="unused"),
    )
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        event_policy=SlackEventPolicy(allowed_channel_ids=frozenset({"C_ALLOWED"})),
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="app_mention",
            user_id="U1",
            channel_id="C_BLOCKED",
            text="<@UBOT> should not run",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )

    assert run_service.messages == []
    assert messaging_client.sent == []


async def test_slack_event_worker_rewrites_generic_refusal_before_replying() -> None:
    run_service = RecordingRunService(response="cannot fulfill this request")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        faq_responder=RecordingFaqResponder(reply=None),
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="app_mention",
            user_id="U1",
            channel_id="C1",
            text="<@UBOT> deploy checklist",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )

    reply = messaging_client.sent[-1][1]["text"]
    assert isinstance(reply, str)
    assert "요청을 처리하기에 충분한 실시간 맥락이 없어도" in reply
    assert "cannot fulfill this request" not in reply


async def test_slack_event_worker_rate_limits_user_before_running_agent() -> None:
    run_service = RecordingRunService(response="unused")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        rate_limiter=InMemorySlackUserRateLimiter(max_requests_per_window=1),
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="app_mention",
            user_id="U1",
            channel_id="C1",
            text="<@UBOT> first",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )
    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="app_mention",
            user_id="U1",
            channel_id="C1",
            text="<@UBOT> second",
            ts="1710000002.000300",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )

    assert run_service.messages == ["first"]
    assert messaging_client.sent[-1] == (
        "C1",
        {
            "text": (
                "<@U1> :no_entry: You are sending requests too quickly. "
                "Please wait a moment and try again."
            ),
            "thread_ts": "1710000002.000300",
            "attachments": None,
        },
    )


async def test_slack_event_worker_passes_tenant_to_rate_limiter() -> None:
    run_service = RecordingRunService(response="ok")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    limiter = RecordingRateLimiter()
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        rate_limiter=limiter,
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_a",
            event_type="app_mention",
            user_id="U1",
            channel_id="C1",
            text="<@UBOT> hello",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )

    assert limiter.calls == [("tenant_a", "U1")]
    assert run_service.messages == ["hello"]


async def test_slack_event_worker_awaits_async_rate_limiter_before_running_agent() -> None:
    run_service = RecordingRunService(response="unused")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        rate_limiter=AsyncDenyingRateLimiter(),
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="app_mention",
            user_id="U1",
            channel_id="C1",
            text="<@UBOT> blocked",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )

    assert run_service.messages == []
    assert messaging_client.sent == [
        (
            "C1",
            {
                "text": (
                    "<@U1> :no_entry: You are sending requests too quickly. "
                    "Please wait a moment and try again."
                ),
                "thread_ts": "1710000000.000100",
                "attachments": None,
            },
        )
    ]


async def test_slack_event_worker_rejects_when_backpressure_saturated() -> None:
    run_service = RecordingRunService(response="unused")
    messaging_client = RecordingSlackMessagingClient(
        question_result=SlackMessageSendResult(ok=True, ts="unused"),
        reply_result=SlackMessageSendResult(ok=True, ts="1710000001.000200"),
    )
    limiter = SlackBackpressureLimiter(
        max_concurrent_requests=1,
        request_timeout_seconds=0,
        fail_fast_on_saturation=True,
    )
    assert await limiter.acquire() is True
    worker = SlackEventWorker(
        run_service=run_service,
        messaging_client=messaging_client,
        backpressure_limiter=limiter,
    )

    await worker.handle(
        SlackEventPayload(
            tenant_id="tenant_1",
            event_type="app_mention",
            user_id="U1",
            channel_id="C1",
            text="<@UBOT> overloaded",
            ts="1710000000.000100",
            thread_ts=None,
            channel_type="channel",
            entrypoint="events_api",
        )
    )

    assert run_service.messages == []
    assert messaging_client.sent == [
        (
            "C1",
            {
                "text": (
                    "<@U1> :hourglass_flowing_sand: Reactor is handling too many "
                    "Slack requests right now. Please try again shortly."
                ),
                "thread_ts": "1710000000.000100",
                "attachments": None,
            },
        )
    ]


def test_channel_faq_ingest_payload_maps_outbox_payload() -> None:
    payload = ChannelFaqIngestPayload.from_outbox_payload(
        {
            "entrypoint": "manual_admin",
            "channelId": "C123",
            "daysBack": 14,
        },
        tenant_id="tenant_1",
    )

    assert payload.tenant_id == "tenant_1"
    assert payload.channel_id == "C123"
    assert payload.days_back == 14
    assert payload.entrypoint == "manual_admin"


async def test_channel_faq_ingest_worker_records_success_counts() -> None:
    store = InMemoryChannelFaqRegistrationStore()
    store.save(
        ChannelFaqRegistration(
            tenant_id="tenant_1",
            channel_id="C123",
            days_back=14,
        )
    )
    ingestion_service = RecordingChannelFaqIngestionService(
        result=ChannelFaqIngestResult(
            channel_id="C123",
            messages_scanned=42,
            document_count=8,
            chunk_count=16,
            api_calls=3,
        )
    )
    worker = ChannelFaqIngestWorker(
        registration_store=store,
        ingestion_service=ingestion_service,
    )

    result = await worker.handle(
        ChannelFaqIngestPayload(
            tenant_id="tenant_1",
            channel_id="C123",
            days_back=14,
            entrypoint="manual_admin",
        )
    )

    assert result.status == "ok"
    assert ingestion_service.calls == [("tenant_1", "C123", 140)]
    updated = store.get(tenant_id="tenant_1", channel_id="C123")
    assert updated is not None
    assert updated.last_status == "ok"
    assert updated.last_message_count == 42
    assert updated.last_chunk_count == 16
    assert updated.last_error is None


async def test_channel_faq_ingest_worker_records_failure_without_raising() -> None:
    store = InMemoryChannelFaqRegistrationStore()
    store.save(
        ChannelFaqRegistration(
            tenant_id="tenant_1",
            channel_id="C123",
        )
    )
    worker = ChannelFaqIngestWorker(
        registration_store=store,
        ingestion_service=RaisingChannelFaqIngestionService(),
    )

    result = await worker.handle(
        ChannelFaqIngestPayload(
            tenant_id="tenant_1",
            channel_id="C123",
            days_back=30,
            entrypoint="manual_admin",
        )
    )

    assert result.status == "failed"
    assert result.error == "slack_faq_ingestion_failed"
    updated = store.get(tenant_id="tenant_1", channel_id="C123")
    assert updated is not None
    assert updated.last_status == "failed"
    assert updated.last_message_count is None
    assert updated.last_chunk_count is None
    assert updated.last_error == "slack_faq_ingestion_failed"


@respx.mock
async def test_response_url_client_retries_server_errors() -> None:
    route = respx.post("https://hooks.slack.test/response").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200),
        ]
    )
    client = HttpSlackResponseUrlClient(
        max_retries=1,
        initial_delay_seconds=0,
        max_delay_seconds=0,
    )

    sent = await client.send(
        "https://hooks.slack.test/response",
        {"response_type": "in_channel", "text": "ok"},
    )

    assert sent is True
    assert route.call_count == 2


@respx.mock
async def test_response_url_client_does_not_retry_client_errors() -> None:
    route = respx.post("https://hooks.slack.test/response").mock(return_value=httpx.Response(404))
    client = HttpSlackResponseUrlClient(max_retries=3)

    sent = await client.send(
        "https://hooks.slack.test/response",
        {"response_type": "in_channel", "text": "ok"},
    )

    assert sent is False
    assert route.call_count == 1


@respx.mock
async def test_http_slack_messaging_client_posts_chat_message() -> None:
    route = respx.post("https://slack.com/api/chat.postMessage").mock(
        return_value=httpx.Response(
            200,
            json={"ok": True, "ts": "1710000000.000100", "channel": "C1"},
        )
    )
    client = HttpSlackMessagingClient(bot_token=SLACK_TEST_BOT_TOKEN)

    result = await client.send_message(
        channel_id="C1",
        text="hello",
        thread_ts="1710000000.000000",
        attachments=[{"text": "attachment"}],
    )

    assert result == SlackMessageSendResult(ok=True, ts="1710000000.000100")
    request = cast(httpx.Request, route.calls[0].request)
    assert request is not None
    assert request.headers["Authorization"] == f"Bearer {SLACK_TEST_BOT_TOKEN}"
    assert request.headers["Content-Type"] == "application/json"
    assert request.content == (
        b'{"channel":"C1","text":"hello","thread_ts":"1710000000.000000",'
        b'"attachments":[{"text":"attachment"}]}'
    )


@respx.mock
async def test_http_slack_messaging_client_posts_block_kit_blocks() -> None:
    route = respx.post("https://slack.com/api/chat.postMessage").mock(
        return_value=httpx.Response(
            200,
            json={"ok": True, "ts": "1710000000.000100", "channel": "C1"},
        )
    )
    client = HttpSlackMessagingClient(bot_token=SLACK_TEST_BOT_TOKEN)

    result = await client.send_message(
        channel_id="C1",
        text="approval required",
        thread_ts="1710000000.000000",
        blocks=[
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "action_id": "approval.approve",
                        "value": '{"approvalId":"approval_1"}',
                    }
                ],
            }
        ],
    )

    assert result == SlackMessageSendResult(ok=True, ts="1710000000.000100")
    request = cast(httpx.Request, route.calls[0].request)
    assert request.content == (
        b'{"channel":"C1","text":"approval required",'
        b'"thread_ts":"1710000000.000000",'
        b'"blocks":[{"type":"actions","elements":[{"type":"button",'
        b'"text":{"type":"plain_text","text":"Approve"},'
        b'"action_id":"approval.approve","value":"{\\"approvalId\\":\\"approval_1\\"}"}]}]}'
    )


@respx.mock
async def test_http_slack_messaging_client_returns_slack_api_error() -> None:
    respx.post("https://slack.com/api/chat.postMessage").mock(
        return_value=httpx.Response(200, json={"ok": False, "error": "channel_not_found"})
    )
    client = HttpSlackMessagingClient(bot_token=SLACK_TEST_BOT_TOKEN)

    result = await client.send_message(channel_id="C1", text="hello")

    assert result == SlackMessageSendResult(ok=False, error="channel_not_found")


@respx.mock
async def test_http_slack_messaging_client_preserves_retry_after_on_rate_limit() -> None:
    respx.post("https://slack.com/api/chat.postMessage").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "7"})
    )
    client = HttpSlackMessagingClient(bot_token=SLACK_TEST_BOT_TOKEN)

    result = await client.send_message(channel_id="C1", text="hello")

    assert result == SlackMessageSendResult(
        ok=False,
        error="rate_limited",
        retry_after_seconds=7,
    )


@respx.mock
async def test_http_slack_thread_context_client_fetches_conversation_replies() -> None:
    route = respx.get("https://slack.com/api/conversations.replies").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "messages": [
                    {
                        "ts": "1710000000.000100",
                        "user": "U_PARENT",
                        "text": "parent",
                    },
                    {
                        "ts": "1710000001.000200",
                        "bot_id": "B1",
                        "text": "bot diagnostic",
                    },
                ],
            },
        )
    )
    client = HttpSlackThreadContextClient(bot_token=SLACK_TEST_BOT_TOKEN)

    messages = await client.fetch_thread_messages(
        channel_id="C1",
        thread_ts="1710000000.000100",
        limit=2,
    )

    assert messages == [
        SlackThreadMessage(ts="1710000000.000100", user_id="U_PARENT", text="parent"),
        SlackThreadMessage(ts="1710000001.000200", user_id="B1", text="bot diagnostic"),
    ]
    request = cast(httpx.Request, route.calls[0].request)
    assert request.headers["Authorization"] == f"Bearer {SLACK_TEST_BOT_TOKEN}"
    assert request.url.params["channel"] == "C1"
    assert request.url.params["ts"] == "1710000000.000100"
    assert request.url.params["limit"] == "2"


@respx.mock
async def test_http_slack_assistant_status_client_posts_status_update() -> None:
    route = respx.post("https://slack.com/api/assistant.threads.setStatus").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    client = HttpSlackAssistantStatusClient(bot_token=SLACK_TEST_BOT_TOKEN)

    await client.set_status(
        channel_id="D123",
        thread_ts="1710000002.000300",
        status="is thinking...",
    )

    request = cast(httpx.Request, route.calls[0].request)
    assert request.headers["Authorization"] == f"Bearer {SLACK_TEST_BOT_TOKEN}"
    assert request.headers["Content-Type"] == "application/json"
    assert request.content == (
        b'{"channel_id":"D123","thread_ts":"1710000002.000300","status":"is thinking..."}'
    )


def slack_command_payload(
    text: str,
    *,
    tenant_id: str = "tenant_1",
    user_id: str = "U1",
) -> SlackSlashCommandPayload:
    return SlackSlashCommandPayload(
        tenant_id=tenant_id,
        command="/reactor",
        text=text,
        user_id=user_id,
        user_name=None,
        channel_id="C1",
        channel_name=None,
        team_id="T1",
        response_url="https://hooks.slack.test/response",
        trigger_id=None,
        entrypoint="slash_command",
    )


class RecordingRunService:
    def __init__(
        self,
        *,
        response: str,
        response_metadata: dict[str, object] | None = None,
    ) -> None:
        self._response = response
        self._response_metadata = response_metadata or {}
        self.messages: list[str] = []
        self.thread_ids: list[str | None] = []
        self.metadata: list[Mapping[str, object]] = []

    async def create_run(
        self,
        message: str,
        *,
        tenant_id: str = "local",
        user_id: str = "anonymous",
        thread_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> RunResult:
        self.messages.append(message)
        self.thread_ids.append(thread_id)
        self.metadata.append(metadata or {})
        return RunResult(
            run_id="run_1",
            tenant_id=tenant_id,
            user_id=user_id,
            thread_id=thread_id or "thread_1",
            checkpoint_ns="reactor",
            status="completed",
            response=self._response,
            provider="openai",
            model="gpt-5-mini",
            response_metadata=self._response_metadata,
        )


class RaisingRunService:
    async def create_run(self, *_: object, **__: object) -> RunResult:
        raise RuntimeError("agent unavailable")


class AsyncDenyingRateLimiter:
    async def try_acquire(self, tenant_id: str, user_id: str) -> bool:
        del tenant_id, user_id
        return False


class RecordingRateLimiter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def try_acquire(self, tenant_id: str, user_id: str) -> bool:
        self.calls.append((tenant_id, user_id))
        return True


class RecordingResponseUrlClient(SlackResponseUrlClient):
    def __init__(self) -> None:
        self.sent: list[tuple[str, Mapping[str, object]]] = []

    async def send(self, response_url: str, payload: Mapping[str, object]) -> bool:
        self.sent.append((response_url, payload))
        return True


class RecordingApprovalRequestStore:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, str, str, Mapping[str, object]]] = []

    async def request_approval(self, request: ApprovalRequest) -> str:
        self.requests.append(
            (
                request.tenant_id,
                request.run_id,
                request.tool_id,
                request.requested_by,
                request.request_payload,
            )
        )
        return "approval_1"


def expected_approval_blocks() -> list[Mapping[str, object]]:
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Approval required*\n"
                    "Tool: `builtin:send_webhook`\n"
                    "Risk: `external_side_effect`\n"
                    "Requested by: <@U1>"
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve"},
                    "style": "primary",
                    "action_id": "approval.approve",
                    "value": (
                        '{"approvalId":"approval_1",'
                        '"runId":"run_1","threadId":"slack-C1-1710000000.000100",'
                        '"checkpointNs":"reactor","channelId":"C1",'
                        '"threadTs":"1710000000.000100"}'
                    ),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Reject"},
                    "style": "danger",
                    "action_id": "approval.reject",
                    "value": (
                        '{"approvalId":"approval_1",'
                        '"runId":"run_1","threadId":"slack-C1-1710000000.000100",'
                        '"checkpointNs":"reactor","channelId":"C1",'
                        '"threadTs":"1710000000.000100","reason":"Rejected from Slack"}'
                    ),
                },
            ],
        },
    ]


def expected_feedback_blocks() -> list[Mapping[str, object]]:
    return [
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Helpful"},
                    "action_id": "feedback.up",
                    "value": "up",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Needs work"},
                    "action_id": "feedback.down",
                    "value": "down",
                },
            ],
        }
    ]


class RecordingSlackMessagingClient(SlackMessagingClient):
    def __init__(
        self,
        *,
        question_result: SlackMessageSendResult,
        reply_result: SlackMessageSendResult,
    ) -> None:
        self._question_result = question_result
        self._reply_result = reply_result
        self.sent: list[tuple[str, Mapping[str, object]]] = []

    async def send_message(
        self,
        *,
        channel_id: str,
        text: str,
        thread_ts: str | None = None,
        attachments: list[Mapping[str, object]] | None = None,
        blocks: list[Mapping[str, object]] | None = None,
    ) -> SlackMessageSendResult:
        payload: dict[str, object] = {
            "text": text,
            "thread_ts": thread_ts,
            "attachments": attachments,
        }
        if blocks is not None:
            payload["blocks"] = blocks
        self.sent.append((channel_id, payload))
        return self._question_result if thread_ts is None else self._reply_result


class RecordingThreadParticipationTracker(SlackThreadParticipationTracker):
    def __init__(self) -> None:
        self._threads: set[tuple[str, str, str]] = set()
        self.checked: list[tuple[str, str, str]] = []
        self.recorded: list[tuple[str, str, str]] = []

    async def has_participated(self, *, tenant_id: str, channel_id: str, thread_ts: str) -> bool:
        self.checked.append((tenant_id, channel_id, thread_ts))
        return (tenant_id, channel_id, thread_ts) in self._threads

    async def record_participation(
        self, *, tenant_id: str, channel_id: str, thread_ts: str
    ) -> None:
        self.recorded.append((tenant_id, channel_id, thread_ts))
        self._threads.add((tenant_id, channel_id, thread_ts))


class FakeSlackThreadRunLookup:
    def __init__(self, *, existing: set[tuple[str, str]]) -> None:
        self._existing = existing
        self.calls: list[tuple[str, str]] = []

    async def has_slack_thread_run(self, *, tenant_id: str, thread_id: str) -> bool:
        self.calls.append((tenant_id, thread_id))
        return (tenant_id, thread_id) in self._existing


class RecordingSlackThreadContextClient:
    def __init__(self, *, messages: list[SlackThreadMessage]) -> None:
        self._messages = messages
        self.calls: list[tuple[str, str, int]] = []

    async def fetch_thread_messages(
        self,
        *,
        channel_id: str,
        thread_ts: str,
        limit: int,
    ) -> list[SlackThreadMessage]:
        self.calls.append((channel_id, thread_ts, limit))
        return self._messages


class RecordingSlackAssistantStatusClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def set_status(self, *, channel_id: str, thread_ts: str, status: str) -> None:
        self.calls.append((channel_id, thread_ts, status))


class RecordingFaqResponder:
    def __init__(self, *, reply: FakeFaqAutoReply | None) -> None:
        self._reply = reply
        self.calls: list[tuple[str, str, str, str, bool]] = []

    async def try_auto_reply(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        user_id: str,
        user_query: str,
        is_mention: bool,
    ) -> FakeFaqAutoReply | None:
        self.calls.append((tenant_id, channel_id, user_id, user_query, is_mention))
        return self._reply


class FakeFaqAutoReply:
    def __init__(
        self,
        *,
        text: str,
        score: float,
        threshold: float,
        matched_document_ids: list[str],
    ) -> None:
        self.text = text
        self.score = score
        self.threshold = threshold
        self.matched_document_ids = matched_document_ids


class RecordingChannelFaqIngestionService:
    def __init__(self, *, result: ChannelFaqIngestResult) -> None:
        self._result = result
        self.calls: list[tuple[str, str, int]] = []

    async def ingest_recent(
        self, *, tenant_id: str, channel_id: str, max_messages: int
    ) -> ChannelFaqIngestResult:
        self.calls.append((tenant_id, channel_id, max_messages))
        return self._result


class RaisingChannelFaqIngestionService:
    async def ingest_recent(
        self, *, tenant_id: str, channel_id: str, max_messages: int
    ) -> ChannelFaqIngestResult:
        del tenant_id, channel_id, max_messages
        raise RuntimeError("slack history unavailable: private-workspace-detail")
