from __future__ import annotations

from collections.abc import Mapping

from reactor.slack.feedback import (
    Feedback,
    FeedbackButtonHandler,
    FeedbackRating,
    InMemoryBotResponseTracker,
    InMemoryFeedbackStore,
    SlackApprovalButtonHandler,
    SlackInteractionHandler,
    SlackInteractionPayload,
    TrackedBotResponse,
    feedback_rating_from_action_id,
    slack_approval_resume_ack,
)
from reactor.tools.approval import ApprovalDecision


async def test_in_memory_feedback_store_duplicate_save_preserves_review_state() -> None:
    store = InMemoryFeedbackStore()
    original = await store.save(
        Feedback(
            feedback_id="slack-reaction:tenant_1:C1:1710000001.000200:U2:-1",
            tenant_id="tenant_1",
            query="Q",
            response="A",
            rating=FeedbackRating.THUMBS_DOWN,
            session_id="session_1",
            user_id="U2",
            source="slack_reaction",
        )
    )
    reviewed = await store.update_review(
        tenant_id="tenant_1",
        feedback_id=original.feedback_id,
        expected_version=1,
        status="done",
        tags=["reviewed"],
        note="promoted to eval",
        actor="operator_1",
    )

    saved = await store.save(
        Feedback(
            feedback_id=original.feedback_id,
            tenant_id="tenant_1",
            query="Q",
            response="A replayed",
            rating=FeedbackRating.THUMBS_DOWN,
            session_id="session_1",
            user_id="U2",
            source="slack_reaction",
        )
    )

    assert len(store.records) == 1
    assert saved.response == "A replayed"
    assert saved.created_at == original.created_at
    assert saved.review_status == "done"
    assert saved.review_tags == ["reviewed"]
    assert saved.reviewed_by == "operator_1"
    assert saved.reviewed_at == reviewed.reviewed_at
    assert saved.review_note == "promoted to eval"
    assert saved.version == 2


async def test_in_memory_feedback_store_filters_case_id_before_limit() -> None:
    store = InMemoryFeedbackStore()
    await store.save(
        Feedback(
            feedback_id="fb_target",
            tenant_id="tenant_1",
            query="documents-ask RAG candidate answer missed citation evidence",
            response="Use [runbook.md].",
            rating=FeedbackRating.THUMBS_DOWN,
            session_id="session_target",
            run_id="run_rag_candidate_c1",
            user_id="U1",
            source="admin_cli",
            tags=["collection:rag-ingestion-candidate", "rag-candidate:c1", "documents-ask"],
        )
    )
    for index in range(125):
        await store.save(
            Feedback(
                feedback_id=f"fb_other_{index}",
                tenant_id="tenant_1",
                query="Other answer",
                response="Other response",
                rating=FeedbackRating.THUMBS_DOWN,
                session_id=f"session_other_{index}",
                run_id=f"run_other_{index}",
                user_id="U1",
                source="admin_cli",
                tags=["documents-ask"],
            )
        )

    records = await store.list(
        tenant_id="tenant_1",
        review_status="inbox",
        case_id="case_rag_candidate_c1",
        limit=10,
    )

    assert [record.feedback_id for record in records] == ["fb_target"]


def test_slack_approval_resume_ack_quotes_run_operator_commands() -> None:
    assert slack_approval_resume_ack("Approval approved", run_id="run needs quoting") == (
        "Approval approved\n\n"
        "_Diagnose: `reactor-runs diagnose 'run needs quoting' --output table`_\n"
        "_State history: `reactor-admin state-history 'run needs quoting' --output table`_\n"
        "_Replay events: `reactor-runs replay 'run needs quoting' --output table`_\n"
        "_Feedback review: `reactor-admin feedback --rating thumbs_down "
        "--review-status inbox --limit 10 "
        "--output table`_"
    )


async def test_feedback_button_handler_saves_tracked_feedback_and_acks_in_thread() -> None:
    store = InMemoryFeedbackStore()
    tracker = InMemoryBotResponseTracker()
    tracker.track(
        TrackedBotResponse(
            channel_id="C1",
            message_ts="1710000001.000200",
            session_id="session_1",
            user_prompt="원래 질문",
            user_id="U1",
            response="봇 답변",
            run_id="run_1",
            tags=["slack", "agent-run"],
            template_id="slack-agent-run",
            model="gpt-5-mini",
            prompt_version=7,
            tools_used=["Rag:hybrid_search"],
        )
    )
    messaging_client = RecordingInteractionMessagingClient()
    handler = FeedbackButtonHandler(
        feedback_store=store,
        bot_response_tracker=tracker,
        messaging_client=messaging_client,
    )

    handled = await handler.handle(
        SlackInteractionPayload(
            type="block_actions",
            action_id="feedback.up",
            value=None,
            user_id="U2",
            channel_id="C1",
            message_ts="1710000001.000200",
            trigger_id="trigger_1",
            response_url="https://hooks.slack.test/interaction",
        ),
        tenant_id="tenant_1",
    )

    assert handled is True
    assert len(store.records) == 1
    assert store.records[0].query == "원래 질문"
    assert store.records[0].response == "봇 답변"
    assert store.records[0].rating == FeedbackRating.THUMBS_UP
    assert store.records[0].session_id == "session_1"
    assert store.records[0].user_id == "U1"
    assert store.records[0].run_id == "run_1"
    assert store.records[0].tags == ["slack", "agent-run", "rag", "grounding"]
    assert store.records[0].template_id == "slack-agent-run"
    assert store.records[0].model == "gpt-5-mini"
    assert store.records[0].prompt_version == 7
    assert store.records[0].tools_used == ["Rag:hybrid_search"]
    assert store.records[0].tenant_id == "tenant_1"
    assert messaging_client.thread_messages == [
        (
            "C1",
            "1710000001.000200",
            FeedbackButtonHandler.ACK_SUCCESS_UP,
        )
    ]
    assert messaging_client.response_url_messages == []


async def test_feedback_button_handler_negative_ack_includes_review_close_command() -> None:
    store = InMemoryFeedbackStore()
    tracker = InMemoryBotResponseTracker()
    tracker.track(
        TrackedBotResponse(
            channel_id="C1",
            message_ts="1710000001.000200",
            session_id="session_1",
            user_prompt="Where is the source?",
            user_id="U1",
            response="The answer omitted the citation.",
            run_id="run_1",
            tags=["slack", "agent-run"],
        )
    )
    messaging_client = RecordingInteractionMessagingClient()
    handler = FeedbackButtonHandler(
        feedback_store=store,
        bot_response_tracker=tracker,
        messaging_client=messaging_client,
    )

    handled = await handler.handle(
        SlackInteractionPayload(
            type="block_actions",
            action_id="feedback.down",
            value=None,
            user_id="U2",
            channel_id="C1",
            message_ts="1710000001.000200",
            trigger_id="trigger_1",
            response_url="https://hooks.slack.test/interaction",
        ),
        tenant_id="tenant_1",
    )

    assert handled is True
    ack = messaging_client.thread_messages[0][2]
    assert "reactor-admin feedback --feedback-id" in ack
    assert "reactor-admin feedback-review" in ack
    assert "--if-match 1 --status done" in ack
    assert "--tag promoted --tag langsmith" in ack
    assert (
        "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. "
        "Required readiness reports: hardening_suite, langsmith_eval_sync.'" in ack
    )
    assert "reactor-runs diagnose run_1 --output table" in ack
    assert "reactor-runs replay run_1 --output table" in ack
    assert "reactor-admin state-history run_1 --output table" in ack


async def test_feedback_button_handler_negative_ack_preserves_memory_review_tag() -> None:
    store = InMemoryFeedbackStore()
    tracker = InMemoryBotResponseTracker()
    tracker.track(
        TrackedBotResponse(
            channel_id="C1",
            message_ts="1710000001.000200",
            session_id="session_1",
            user_prompt="What should you remember about me?",
            user_id="U1",
            response="I forgot the preference you asked me to remember.",
            run_id="run_1",
            tags=["slack", "agent-run"],
        )
    )
    messaging_client = RecordingInteractionMessagingClient()
    handler = FeedbackButtonHandler(
        feedback_store=store,
        bot_response_tracker=tracker,
        messaging_client=messaging_client,
    )

    handled = await handler.handle(
        SlackInteractionPayload(
            type="block_actions",
            action_id="feedback.down",
            value=None,
            user_id="U2",
            channel_id="C1",
            message_ts="1710000001.000200",
            trigger_id="trigger_1",
            response_url="https://hooks.slack.test/interaction",
        ),
        tenant_id="tenant_1",
    )

    assert handled is True
    ack = messaging_client.thread_messages[0][2]
    assert "--tag slack" in ack
    assert "--tag memory" in ack


def test_in_memory_bot_response_tracker_evicts_oldest_tracked_replies() -> None:
    tracker = InMemoryBotResponseTracker(max_entries=2)

    tracker.track(
        TrackedBotResponse(
            channel_id="C1",
            message_ts="1710000001.000100",
            session_id="session_1",
            user_prompt="first",
        )
    )
    tracker.track(
        TrackedBotResponse(
            channel_id="C1",
            message_ts="1710000002.000200",
            session_id="session_2",
            user_prompt="second",
        )
    )
    tracker.track(
        TrackedBotResponse(
            channel_id="C1",
            message_ts="1710000003.000300",
            session_id="session_3",
            user_prompt="third",
        )
    )

    assert tracker.lookup("C1", "1710000001.000100") is None
    assert tracker.lookup("C1", "1710000002.000200") is not None
    assert tracker.lookup("C1", "1710000003.000300") is not None


async def test_feedback_button_handler_enriches_tracked_feedback_with_workflow_tags() -> None:
    store = InMemoryFeedbackStore()
    tracker = InMemoryBotResponseTracker()
    tracker.track(
        TrackedBotResponse(
            channel_id="C1",
            message_ts="1710000001.000200",
            session_id="session_1",
            user_prompt="Why did retrieval miss the source?",
            response="The RAG search answer omitted citation evidence.",
            run_id="run_1",
            tags=["slack", "agent-run"],
            template_id="slack-agent-run",
        )
    )
    messaging_client = RecordingInteractionMessagingClient()
    handler = FeedbackButtonHandler(
        feedback_store=store,
        bot_response_tracker=tracker,
        messaging_client=messaging_client,
    )

    handled = await handler.handle(
        SlackInteractionPayload(
            type="block_actions",
            action_id="feedback.down",
            value=None,
            user_id="U2",
            channel_id="C1",
            message_ts="1710000001.000200",
            trigger_id="trigger_1",
            response_url="https://hooks.slack.test/interaction",
        ),
        tenant_id="tenant_1",
    )

    assert handled is True
    assert store.records[0].tags == [
        "slack",
        "agent-run",
        "rag",
        "grounding",
        "citation-failure",
    ]
    assert store.records[0].feedback_id in messaging_client.thread_messages[0][2]
    assert "reactor-admin feedback" in messaging_client.thread_messages[0][2]


async def test_feedback_button_handler_ephemeral_ack_on_tracker_miss() -> None:
    store = InMemoryFeedbackStore()
    messaging_client = RecordingInteractionMessagingClient()
    handler = FeedbackButtonHandler(
        feedback_store=store,
        bot_response_tracker=InMemoryBotResponseTracker(),
        messaging_client=messaging_client,
    )

    handled = await handler.handle(
        SlackInteractionPayload(
            type="block_actions",
            action_id="feedback.down",
            value=None,
            user_id="U2",
            channel_id="C1",
            message_ts="missing",
            trigger_id=None,
            response_url="https://hooks.slack.test/interaction",
        ),
        tenant_id="tenant_1",
    )

    assert handled is True
    assert store.records == []
    assert messaging_client.thread_messages == []
    assert messaging_client.response_url_messages == [
        (
            "https://hooks.slack.test/interaction",
            FeedbackButtonHandler.ACK_EXPIRED,
            "ephemeral",
        )
    ]


def test_slack_interaction_payload_parses_block_action_shape() -> None:
    payload = SlackInteractionPayload.from_slack_payload(
        {
            "type": "block_actions",
            "user": {"id": "U2"},
            "channel": {"id": "C1"},
            "message": {"ts": "1710000001.000200"},
            "trigger_id": "trigger_1",
            "response_url": "https://hooks.slack.test/interaction",
            "actions": [{"action_id": "feedback.down", "value": "v"}],
        }
    )

    assert payload.action_id == "feedback.down"
    assert payload.value == "v"
    assert payload.user_id == "U2"
    assert payload.channel_id == "C1"
    assert payload.message_ts == "1710000001.000200"
    assert feedback_rating_from_action_id(payload.action_id) == FeedbackRating.THUMBS_DOWN


async def test_slack_approval_button_handler_decides_and_resumes_run() -> None:
    approval_store = RecordingApprovalStore()
    run_service = RecordingRunResumeService()
    messaging_client = RecordingInteractionMessagingClient()
    response_url_client = RecordingInteractionResponseUrlClient()
    handler = SlackApprovalButtonHandler(
        approval_store=approval_store,
        run_service=run_service,
        messaging_client=messaging_client,
        response_url_client=response_url_client,
    )

    handled = await handler.handle(
        SlackInteractionPayload(
            type="block_actions",
            action_id="approval.approve",
            value=(
                '{"approvalId":"approval_1","runId":"run_1",'
                '"threadId":"thread_1","checkpointNs":"reactor",'
                '"channelId":"C1","threadTs":"1710000000.000100"}'
            ),
            user_id="U_APPROVER",
            channel_id="C1",
            message_ts="1710000001.000200",
            trigger_id="trigger_1",
            response_url="https://hooks.slack.test/interaction",
        ),
        tenant_id="tenant_1",
    )

    assert handled is True
    assert approval_store.decisions == [("tenant_1", "approval_1", "U_APPROVER", True, None)]
    assert run_service.resume_calls == [
        ("run_1", "tenant_1", "U_APPROVER", "thread_1", "reactor", "approval_1", True, None)
    ]
    assert messaging_client.thread_messages == [
        ("C1", "1710000000.000100", approval_ack_with_actions("Approval approved")),
        ("C1", "1710000000.000100", "Approved tool result."),
    ]
    assert response_url_client.sent == [
        (
            "https://hooks.slack.test/interaction",
            {
                "replace_original": True,
                "text": "Approval approved by <@U_APPROVER>.",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "Approval approved by <@U_APPROVER>.",
                        },
                    }
                ],
            },
        )
    ]


async def test_slack_approval_button_handler_rejects_with_reason() -> None:
    approval_store = RecordingApprovalStore()
    run_service = RecordingRunResumeService()
    messaging_client = RecordingInteractionMessagingClient()
    handler = SlackApprovalButtonHandler(
        approval_store=approval_store,
        run_service=run_service,
        messaging_client=messaging_client,
    )

    handled = await handler.handle(
        SlackInteractionPayload(
            type="block_actions",
            action_id="approval.reject",
            value=(
                '{"approvalId":"approval_1","runId":"run_1","threadId":"thread_1",'
                '"checkpointNs":"reactor","reason":"Denied from Slack"}'
            ),
            user_id="U_APPROVER",
            channel_id="C1",
            message_ts="1710000001.000200",
            trigger_id=None,
            response_url=None,
        ),
        tenant_id="tenant_1",
    )

    assert handled is True
    assert approval_store.decisions == [
        ("tenant_1", "approval_1", "U_APPROVER", False, "Denied from Slack")
    ]
    assert run_service.resume_calls == [
        (
            "run_1",
            "tenant_1",
            "U_APPROVER",
            "thread_1",
            "reactor",
            "approval_1",
            False,
            "Denied from Slack",
        )
    ]
    assert messaging_client.thread_messages == [
        ("C1", "1710000001.000200", approval_ack_with_actions("Approval rejected"))
    ]


async def test_slack_approval_button_handler_replaces_expired_approval_buttons() -> None:
    approval_store = RecordingApprovalStore(decided=False)
    run_service = RecordingRunResumeService()
    messaging_client = RecordingInteractionMessagingClient()
    response_url_client = RecordingInteractionResponseUrlClient()
    handler = SlackApprovalButtonHandler(
        approval_store=approval_store,
        run_service=run_service,
        messaging_client=messaging_client,
        response_url_client=response_url_client,
    )

    handled = await handler.handle(
        SlackInteractionPayload(
            type="block_actions",
            action_id="approval.approve",
            value=(
                '{"approvalId":"approval_1","runId":"run_1",'
                '"threadId":"thread_1","checkpointNs":"reactor",'
                '"channelId":"C1","threadTs":"1710000000.000100"}'
            ),
            user_id="U_APPROVER",
            channel_id="C1",
            message_ts="1710000001.000200",
            trigger_id="trigger_1",
            response_url="https://hooks.slack.test/interaction",
        ),
        tenant_id="tenant_1",
    )

    assert handled is True
    assert run_service.resume_calls == []
    assert messaging_client.thread_messages == [
        ("C1", "1710000000.000100", SlackApprovalButtonHandler.ACK_EXPIRED)
    ]
    assert response_url_client.sent == [
        (
            "https://hooks.slack.test/interaction",
            {
                "replace_original": True,
                "text": SlackApprovalButtonHandler.ACK_EXPIRED,
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": SlackApprovalButtonHandler.ACK_EXPIRED,
                        },
                    }
                ],
            },
        )
    ]


async def test_slack_approval_button_handler_closes_malformed_approval_button() -> None:
    approval_store = RecordingApprovalStore()
    run_service = RecordingRunResumeService()
    messaging_client = RecordingInteractionMessagingClient()
    response_url_client = RecordingInteractionResponseUrlClient()
    handler = SlackApprovalButtonHandler(
        approval_store=approval_store,
        run_service=run_service,
        messaging_client=messaging_client,
        response_url_client=response_url_client,
    )

    handled = await handler.handle(
        SlackInteractionPayload(
            type="block_actions",
            action_id="approval.approve",
            value="{not-json",
            user_id="U_APPROVER",
            channel_id="C1",
            message_ts="1710000001.000200",
            trigger_id="trigger_1",
            response_url="https://hooks.slack.test/interaction",
        ),
        tenant_id="tenant_1",
    )

    assert handled is True
    assert approval_store.decisions == []
    assert run_service.resume_calls == []
    assert messaging_client.thread_messages == [
        ("C1", "1710000001.000200", SlackApprovalButtonHandler.ACK_INVALID)
    ]
    assert response_url_client.sent == [
        (
            "https://hooks.slack.test/interaction",
            {
                "replace_original": True,
                "text": SlackApprovalButtonHandler.ACK_INVALID,
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": SlackApprovalButtonHandler.ACK_INVALID,
                        },
                    }
                ],
            },
        )
    ]


async def test_slack_approval_button_handler_closes_channel_mismatch() -> None:
    approval_store = RecordingApprovalStore()
    run_service = RecordingRunResumeService()
    messaging_client = RecordingInteractionMessagingClient()
    response_url_client = RecordingInteractionResponseUrlClient()
    handler = SlackApprovalButtonHandler(
        approval_store=approval_store,
        run_service=run_service,
        messaging_client=messaging_client,
        response_url_client=response_url_client,
    )

    handled = await handler.handle(
        SlackInteractionPayload(
            type="block_actions",
            action_id="approval.approve",
            value=(
                '{"approvalId":"approval_1","runId":"run_1",'
                '"threadId":"thread_1","checkpointNs":"reactor",'
                '"channelId":"C_OTHER","threadTs":"1710000000.000100"}'
            ),
            user_id="U_APPROVER",
            channel_id="C1",
            message_ts="1710000001.000200",
            trigger_id="trigger_1",
            response_url="https://hooks.slack.test/interaction",
        ),
        tenant_id="tenant_1",
    )

    assert handled is True
    assert approval_store.decisions == []
    assert run_service.resume_calls == []
    assert messaging_client.thread_messages == [
        ("C1", "1710000001.000200", SlackApprovalButtonHandler.ACK_INVALID)
    ]
    assert response_url_client.sent == [
        (
            "https://hooks.slack.test/interaction",
            {
                "replace_original": True,
                "text": SlackApprovalButtonHandler.ACK_INVALID,
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": SlackApprovalButtonHandler.ACK_INVALID,
                        },
                    }
                ],
            },
        )
    ]


async def test_slack_approval_button_handler_keeps_decision_when_response_url_replace_fails() -> (
    None
):
    approval_store = RecordingApprovalStore()
    run_service = RecordingRunResumeService()
    messaging_client = RecordingInteractionMessagingClient()
    response_url_client = FailingInteractionResponseUrlClient()
    handler = SlackApprovalButtonHandler(
        approval_store=approval_store,
        run_service=run_service,
        messaging_client=messaging_client,
        response_url_client=response_url_client,
    )

    handled = await handler.handle(
        SlackInteractionPayload(
            type="block_actions",
            action_id="approval.reject",
            value=(
                '{"approvalId":"approval_1","runId":"run_1",'
                '"threadId":"thread_1","checkpointNs":"reactor",'
                '"channelId":"C1","threadTs":"1710000000.000100",'
                '"reason":"Denied from Slack"}'
            ),
            user_id="U_APPROVER",
            channel_id="C1",
            message_ts="1710000001.000200",
            trigger_id="trigger_1",
            response_url="https://hooks.slack.test/interaction",
        ),
        tenant_id="tenant_1",
    )

    assert handled is True
    assert approval_store.decisions == [
        ("tenant_1", "approval_1", "U_APPROVER", False, "Denied from Slack")
    ]
    assert run_service.resume_calls == [
        (
            "run_1",
            "tenant_1",
            "U_APPROVER",
            "thread_1",
            "reactor",
            "approval_1",
            False,
            "Denied from Slack",
        )
    ]
    assert messaging_client.thread_messages == [
        ("C1", "1710000000.000100", approval_ack_with_actions("Approval rejected"))
    ]
    assert response_url_client.calls == 1


async def test_slack_interaction_handler_routes_approval_outbox_payload() -> None:
    feedback_store = InMemoryFeedbackStore()
    tracker = InMemoryBotResponseTracker()
    approval_store = RecordingApprovalStore()
    run_service = RecordingRunResumeService()
    messaging_client = RecordingInteractionMessagingClient()
    handler = SlackInteractionHandler(
        feedback_handler=FeedbackButtonHandler(
            feedback_store=feedback_store,
            bot_response_tracker=tracker,
            messaging_client=messaging_client,
        ),
        approval_handler=SlackApprovalButtonHandler(
            approval_store=approval_store,
            run_service=run_service,
            messaging_client=messaging_client,
        ),
    )

    handled = await handler.handle_outbox_payload(
        {
            "interaction": {
                "type": "block_actions",
                "user": {"id": "U_APPROVER"},
                "channel": {"id": "C1"},
                "message": {"ts": "1710000001.000200"},
                "trigger_id": "trigger_1",
                "response_url": "https://hooks.slack.test/interaction",
                "actions": [
                    {
                        "action_id": "approval.approve",
                        "value": (
                            '{"approvalId":"approval_1","runId":"run_1",'
                            '"threadId":"thread_1","checkpointNs":"reactor"}'
                        ),
                    }
                ],
            }
        },
        tenant_id="tenant_1",
    )

    assert handled is True
    assert feedback_store.records == []
    assert approval_store.decisions == [("tenant_1", "approval_1", "U_APPROVER", True, None)]
    assert run_service.resume_calls == [
        ("run_1", "tenant_1", "U_APPROVER", "thread_1", "reactor", "approval_1", True, None)
    ]


class RecordingInteractionMessagingClient:
    def __init__(self) -> None:
        self.thread_messages: list[tuple[str, str | None, str]] = []
        self.response_url_messages: list[tuple[str, str, str]] = []

    async def send_message(
        self,
        *,
        channel_id: str,
        text: str,
        thread_ts: str | None = None,
    ) -> object:
        self.thread_messages.append((channel_id, thread_ts, text))
        return object()

    async def send_response_url(
        self,
        response_url: str,
        text: str,
        *,
        response_type: str,
    ) -> None:
        self.response_url_messages.append((response_url, text, response_type))


def approval_ack_with_actions(status: str) -> str:
    return (
        f"{status} by <@U_APPROVER>.\n\n"
        "_Diagnose: `reactor-runs diagnose run_1 --output table`_\n"
        "_State history: `reactor-admin state-history run_1 --output table`_\n"
        "_Replay events: `reactor-runs replay run_1 --output table`_\n"
        "_Feedback review: `reactor-admin feedback --rating thumbs_down "
        "--review-status inbox --limit 10 "
        "--output table`_"
    )


class RecordingInteractionResponseUrlClient:
    def __init__(self) -> None:
        self.sent: list[tuple[str, Mapping[str, object]]] = []

    async def send(self, response_url: str, payload: Mapping[str, object]) -> bool:
        self.sent.append((response_url, payload))
        return True


class FailingInteractionResponseUrlClient:
    def __init__(self) -> None:
        self.calls = 0

    async def send(self, response_url: str, payload: Mapping[str, object]) -> bool:
        self.calls += 1
        raise RuntimeError("slack_response_url_failed")


class RecordingApprovalStore:
    def __init__(self, *, decided: bool = True) -> None:
        self._decided = decided
        self.decisions: list[tuple[str, str, str, bool, str | None]] = []

    async def decide_approval(self, decision: ApprovalDecision) -> bool:
        self.decisions.append(
            (
                decision.tenant_id,
                decision.approval_id,
                decision.decided_by,
                decision.approved,
                decision.reason,
            )
        )
        return self._decided


class RecordingRunResumeService:
    def __init__(self) -> None:
        self.resume_calls: list[tuple[str, str, str, str, str, str, bool, str | None]] = []

    async def resume_run(
        self,
        *,
        run_id: str,
        tenant_id: str,
        user_id: str,
        thread_id: str,
        checkpoint_ns: str,
        approval_id: str,
        approved: bool,
        reason: str | None = None,
    ) -> object:
        self.resume_calls.append(
            (
                run_id,
                tenant_id,
                user_id,
                thread_id,
                checkpoint_ns,
                approval_id,
                approved,
                reason,
            )
        )
        return ResumeResult(response="Approved tool result.")


class ResumeResult:
    def __init__(self, *, response: str) -> None:
        self.response = response
