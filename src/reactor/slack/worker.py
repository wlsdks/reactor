from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from inspect import isawaitable
from typing import Any, Protocol, cast

import httpx

from reactor.feedback.workflow import feedback_with_workflow_tags
from reactor.slack.faq import IngestStatus
from reactor.slack.feedback import (
    BotResponseTracker,
    Feedback,
    FeedbackRating,
    FeedbackStore,
    TrackedBotResponse,
)
from reactor.slack.intent import (
    SlackHelpIntent,
    SlackReminderAddIntent,
    SlackReminderClearIntent,
    SlackReminderDoneIntent,
    SlackReminderListIntent,
    parse_slack_slash_intent,
    slack_help_text,
)
from reactor.slack.reminder import SlackReminder
from reactor.slack.response_formatting import format_slack_run_response
from reactor.tools.approval import ApprovalRequest

SLACK_MENTION_PATTERN = "<@"
SLACK_FAQ_INGESTION_FAILED = "slack_faq_ingestion_failed"


def parse_retry_after_seconds(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value.strip())
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


class SlackRetryableSendError(RuntimeError):
    def __init__(self, error: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(error)
        self.retry_after_seconds = retry_after_seconds


class SlackResponseUrlClient(Protocol):
    async def send(self, response_url: str, payload: Mapping[str, object]) -> bool: ...


@dataclass(frozen=True)
class SlackMessageSendResult:
    ok: bool
    ts: str | None = None
    error: str | None = None
    retry_after_seconds: int | None = None


class SlackMessagingClient(Protocol):
    async def send_message(
        self,
        *,
        channel_id: str,
        text: str,
        thread_ts: str | None = None,
        attachments: list[Mapping[str, object]] | None = None,
        blocks: list[Mapping[str, object]] | None = None,
    ) -> SlackMessageSendResult: ...


class ApprovalRequestStore(Protocol):
    async def request_approval(self, request: ApprovalRequest) -> str: ...


@dataclass(frozen=True)
class SlackApprovalRender:
    approval_id: str
    blocks: list[Mapping[str, object]]


@dataclass(frozen=True)
class SlackThreadMessage:
    ts: str
    user_id: str
    text: str


class SlackThreadContextClient(Protocol):
    async def fetch_thread_messages(
        self,
        *,
        channel_id: str,
        thread_ts: str,
        limit: int,
    ) -> list[SlackThreadMessage]: ...


@dataclass(frozen=True)
class SlackAssistantThreadContext:
    assistant_channel_id: str
    thread_ts: str
    user_id: str
    channel_id: str | None = None
    team_id: str | None = None
    enterprise_id: str | None = None

    def to_metadata(self) -> dict[str, str | None]:
        return {
            "assistantChannelId": self.assistant_channel_id,
            "threadTs": self.thread_ts,
            "userId": self.user_id,
            "channelId": self.channel_id,
            "teamId": self.team_id,
            "enterpriseId": self.enterprise_id,
        }


class SlackAssistantThreadContextStore(Protocol):
    async def save(self, *, tenant_id: str, context: SlackAssistantThreadContext) -> None: ...

    async def get(
        self,
        *,
        tenant_id: str,
        assistant_channel_id: str,
        thread_ts: str,
    ) -> SlackAssistantThreadContext | None: ...


class InMemorySlackAssistantThreadContextStore:
    def __init__(self, *, max_threads: int = 50_000) -> None:
        self._max_threads = max_threads
        self._contexts: dict[tuple[str, str, str], SlackAssistantThreadContext] = {}

    async def save(self, *, tenant_id: str, context: SlackAssistantThreadContext) -> None:
        key = (tenant_id, context.assistant_channel_id, context.thread_ts)
        self._contexts.pop(key, None)
        self._contexts[key] = context
        while len(self._contexts) > self._max_threads:
            self._contexts.pop(next(iter(self._contexts)))

    async def get(
        self,
        *,
        tenant_id: str,
        assistant_channel_id: str,
        thread_ts: str,
    ) -> SlackAssistantThreadContext | None:
        return self._contexts.get((tenant_id, assistant_channel_id, thread_ts))


class SlackAssistantStatusClient(Protocol):
    async def set_status(self, *, channel_id: str, thread_ts: str, status: str) -> None: ...


class SlackThreadParticipationTracker(Protocol):
    async def has_participated(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        thread_ts: str,
    ) -> bool: ...

    async def record_participation(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        thread_ts: str,
    ) -> None: ...


class SlackThreadRunLookup(Protocol):
    async def has_slack_thread_run(self, *, tenant_id: str, thread_id: str) -> bool: ...


class InMemorySlackThreadParticipationTracker:
    def __init__(self, *, max_threads: int = 50_000) -> None:
        self._max_threads = max_threads
        self._threads: dict[tuple[str, str, str], None] = {}

    async def has_participated(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        thread_ts: str,
    ) -> bool:
        return (tenant_id, channel_id, thread_ts) in self._threads

    async def record_participation(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        thread_ts: str,
    ) -> None:
        key = (tenant_id, channel_id, thread_ts)
        self._threads.pop(key, None)
        self._threads[key] = None
        while len(self._threads) > self._max_threads:
            self._threads.pop(next(iter(self._threads)))


class RunStoreSlackThreadParticipationTracker:
    def __init__(self, *, run_store: SlackThreadRunLookup) -> None:
        self._run_store = run_store

    async def has_participated(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        thread_ts: str,
    ) -> bool:
        return await self._run_store.has_slack_thread_run(
            tenant_id=tenant_id,
            thread_id=slack_thread_id_from_parts(channel_id=channel_id, thread_ts=thread_ts),
        )

    async def record_participation(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        thread_ts: str,
    ) -> None:
        del tenant_id, channel_id, thread_ts


class CompositeSlackThreadParticipationTracker:
    def __init__(self, *trackers: SlackThreadParticipationTracker) -> None:
        self._trackers = trackers

    async def has_participated(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        thread_ts: str,
    ) -> bool:
        for tracker in self._trackers:
            if await tracker.has_participated(
                tenant_id=tenant_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
            ):
                return True
        return False

    async def record_participation(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        thread_ts: str,
    ) -> None:
        for tracker in self._trackers:
            await tracker.record_participation(
                tenant_id=tenant_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
            )


@dataclass(frozen=True)
class ChannelFaqIngestResult:
    channel_id: str
    messages_scanned: int
    document_count: int
    chunk_count: int
    api_calls: int
    status: str = IngestStatus.OK.value
    error: str | None = None


class ChannelFaqIngestionService(Protocol):
    async def ingest_recent(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        max_messages: int,
    ) -> ChannelFaqIngestResult: ...


class SlackFaqResponder(Protocol):
    async def try_auto_reply(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        user_id: str,
        user_query: str,
        is_mention: bool,
    ) -> Any: ...


class SlackFaqMetrics(Protocol):
    def track_reply(self, channel_id: str, message_ts: str, doc_ids: list[str]) -> None: ...

    def doc_ids_for_reply(self, channel_id: str, message_ts: str) -> list[str]: ...

    def record_feedback(
        self,
        channel_id: str,
        doc_ids: list[str],
        rating: bool,
        *,
        event_id: str | None = None,
    ) -> None: ...


class SlackReminderStore(Protocol):
    def add(self, user_id: str, text: str) -> SlackReminder: ...

    def list(self, user_id: str) -> list[SlackReminder]: ...

    def done(self, user_id: str, reminder_id: int) -> SlackReminder | None: ...

    def clear(self, user_id: str) -> int: ...


class SlackUserRateLimiter(Protocol):
    def try_acquire(self, tenant_id: str, user_id: str) -> bool | Awaitable[bool]: ...


class SlackBackpressureController(Protocol):
    async def acquire(self) -> bool: ...

    def release(self) -> None: ...


class HttpSlackMessagingClient:
    def __init__(
        self,
        *,
        bot_token: str,
        timeout_seconds: float = 5.0,
        api_base_url: str = "https://slack.com/api",
    ) -> None:
        self._bot_token = bot_token
        self._timeout_seconds = timeout_seconds
        self._api_base_url = api_base_url.rstrip("/")

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
            "channel": channel_id,
            "text": text,
        }
        if thread_ts is not None:
            payload["thread_ts"] = thread_ts
        if attachments is not None:
            payload["attachments"] = attachments
        if blocks is not None:
            payload["blocks"] = blocks
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                f"{self._api_base_url}/chat.postMessage",
                content=json.dumps(payload, separators=(",", ":")),
                headers={
                    "Authorization": f"Bearer {self._bot_token}",
                    "Content-Type": "application/json",
                },
            )
        if response.status_code == 429:
            return SlackMessageSendResult(
                ok=False,
                error="rate_limited",
                retry_after_seconds=parse_retry_after_seconds(response.headers.get("Retry-After")),
            )
        if response.status_code >= 400:
            return SlackMessageSendResult(ok=False, error=f"http_{response.status_code}")
        body = response.json()
        if not isinstance(body, dict):
            return SlackMessageSendResult(ok=False, error="invalid_response")
        response_body = cast(dict[str, object], body)
        if response_body.get("ok") is True:
            ts = response_body.get("ts")
            return SlackMessageSendResult(ok=True, ts=ts if isinstance(ts, str) else None)
        error = response_body.get("error")
        return SlackMessageSendResult(
            ok=False,
            error=error if isinstance(error, str) else "slack_api_error",
        )


class HttpSlackThreadContextClient:
    def __init__(
        self,
        *,
        bot_token: str,
        timeout_seconds: float = 5.0,
        api_base_url: str = "https://slack.com/api",
    ) -> None:
        self._bot_token = bot_token
        self._timeout_seconds = timeout_seconds
        self._api_base_url = api_base_url.rstrip("/")

    async def fetch_thread_messages(
        self,
        *,
        channel_id: str,
        thread_ts: str,
        limit: int,
    ) -> list[SlackThreadMessage]:
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.get(
                f"{self._api_base_url}/conversations.replies",
                params={
                    "channel": channel_id,
                    "ts": thread_ts,
                    "limit": max(1, min(limit, 100)),
                },
                headers={"Authorization": f"Bearer {self._bot_token}"},
            )
        if response.status_code >= 400:
            return []
        raw_body = response.json()
        if not isinstance(raw_body, dict):
            return []
        body = cast(dict[str, object], raw_body)
        if body.get("ok") is not True:
            return []
        raw_messages = body.get("messages")
        if not isinstance(raw_messages, list):
            return []
        messages: list[SlackThreadMessage] = []
        for raw in cast(list[object], raw_messages):
            if not isinstance(raw, Mapping):
                continue
            message = slack_thread_message_from_payload(cast(Mapping[str, object], raw))
            if message is not None:
                messages.append(message)
        return messages


class HttpSlackAssistantStatusClient:
    def __init__(
        self,
        *,
        bot_token: str,
        timeout_seconds: float = 5.0,
        api_base_url: str = "https://slack.com/api",
    ) -> None:
        self._bot_token = bot_token
        self._timeout_seconds = timeout_seconds
        self._api_base_url = api_base_url.rstrip("/")

    async def set_status(self, *, channel_id: str, thread_ts: str, status: str) -> None:
        payload = {
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "status": status,
        }
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            await client.post(
                f"{self._api_base_url}/assistant.threads.setStatus",
                content=json.dumps(payload, separators=(",", ":")),
                headers={
                    "Authorization": f"Bearer {self._bot_token}",
                    "Content-Type": "application/json",
                },
            )


class HttpSlackResponseUrlClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 5.0,
        max_retries: int = 3,
        initial_delay_seconds: float = 0.5,
        max_delay_seconds: float = 8.0,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._initial_delay_seconds = initial_delay_seconds
        self._max_delay_seconds = max_delay_seconds

    async def send(self, response_url: str, payload: Mapping[str, object]) -> bool:
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            for attempt in range(self._max_retries + 1):
                try:
                    response = await client.post(response_url, json=dict(payload))
                    if 400 <= response.status_code < 500:
                        return False
                    if response.status_code < 500:
                        return True
                except httpx.RequestError:
                    if attempt >= self._max_retries:
                        return False
                if attempt >= self._max_retries:
                    return False
                await asyncio.sleep(self._retry_delay(attempt))
        return False

    def _retry_delay(self, attempt: int) -> float:
        return min(
            self._initial_delay_seconds * (2**attempt),
            self._max_delay_seconds,
        )


@dataclass(frozen=True)
class SlackSlashCommandPayload:
    tenant_id: str
    command: str
    text: str
    user_id: str
    user_name: str | None
    channel_id: str
    channel_name: str | None
    team_id: str | None
    response_url: str
    trigger_id: str | None
    entrypoint: str = "slash_command"

    @classmethod
    def from_outbox_payload(
        cls,
        payload: Mapping[str, object],
        *,
        tenant_id: str,
    ) -> SlackSlashCommandPayload:
        command = payload.get("command")
        if not isinstance(command, Mapping):
            raise ValueError("Slack slash command payload is missing command object")
        command_payload = cast(Mapping[str, object], command)
        return cls(
            tenant_id=tenant_id,
            command=_required_str(command_payload, "command"),
            text=_optional_str(command_payload, "text") or "",
            user_id=_required_str(command_payload, "userId"),
            user_name=_optional_str(command_payload, "userName"),
            channel_id=_required_str(command_payload, "channelId"),
            channel_name=_optional_str(command_payload, "channelName"),
            team_id=_optional_str(command_payload, "teamId"),
            response_url=_required_str(command_payload, "responseUrl"),
            trigger_id=_optional_str(command_payload, "triggerId"),
            entrypoint=_optional_str(payload, "entrypoint") or "slash_command",
        )


@dataclass(frozen=True)
class ChannelFaqIngestPayload:
    tenant_id: str
    channel_id: str
    days_back: int
    entrypoint: str = "manual_admin"

    @classmethod
    def from_outbox_payload(
        cls,
        payload: Mapping[str, object],
        *,
        tenant_id: str,
    ) -> ChannelFaqIngestPayload:
        return cls(
            tenant_id=tenant_id,
            channel_id=_required_str(payload, "channelId"),
            days_back=_optional_int(payload, "daysBack") or 30,
            entrypoint=_optional_str(payload, "entrypoint") or "manual_admin",
        )


@dataclass(frozen=True)
class SlackEventPayload:
    tenant_id: str
    event_type: str
    user_id: str
    channel_id: str
    text: str
    ts: str
    thread_ts: str | None
    channel_type: str | None
    bot_id: str | None = None
    subtype: str | None = None
    reaction: str | None = None
    assistant_context_channel_id: str | None = None
    assistant_context_team_id: str | None = None
    assistant_context_enterprise_id: str | None = None
    entrypoint: str = "events_api"

    @classmethod
    def from_outbox_payload(
        cls,
        payload: Mapping[str, object],
        *,
        tenant_id: str,
    ) -> SlackEventPayload:
        callback_payload = payload.get("payload")
        if not isinstance(callback_payload, Mapping):
            raise ValueError("Slack event payload is missing callback payload object")
        callback_mapping = cast(Mapping[str, object], callback_payload)
        event: object = callback_mapping.get("event")
        if not isinstance(event, Mapping):
            raise ValueError("Slack event payload is missing event object")
        event_payload = cast(Mapping[str, object], event)
        event_type = _required_str(event_payload, "type")
        if event_type in {"assistant_thread_started", "assistant_thread_context_changed"}:
            thread_ts = slack_assistant_thread_ts(event_payload)
            return cls(
                tenant_id=tenant_id,
                event_type=event_type,
                user_id=slack_assistant_thread_user_id(event_payload),
                channel_id=slack_assistant_thread_channel_id(event_payload),
                text="",
                ts=thread_ts,
                thread_ts=thread_ts,
                channel_type=_optional_str(event_payload, "channel_type") or "im",
                subtype=_optional_str(event_payload, "subtype"),
                assistant_context_channel_id=slack_assistant_context_channel_id(event_payload),
                assistant_context_team_id=slack_assistant_context_team_id(event_payload),
                assistant_context_enterprise_id=slack_assistant_context_enterprise_id(
                    event_payload
                ),
                entrypoint=_optional_str(payload, "entrypoint") or "events_api",
            )
        if event_type == "reaction_added":
            item = event_payload.get("item")
            if not isinstance(item, Mapping):
                raise ValueError("Slack reaction event payload is missing item object")
            item_payload = cast(Mapping[str, object], item)
            if _optional_str(item_payload, "type") != "message":
                raise ValueError("Slack reaction event item must be a message")
            return cls(
                tenant_id=tenant_id,
                event_type=event_type,
                user_id=_required_str(event_payload, "user"),
                channel_id=_required_str(item_payload, "channel"),
                text="",
                ts=_required_str(item_payload, "ts"),
                thread_ts=None,
                channel_type=None,
                reaction=_required_str(event_payload, "reaction"),
                subtype=_optional_str(event_payload, "subtype"),
                entrypoint=_optional_str(payload, "entrypoint") or "events_api",
            )
        return cls(
            tenant_id=tenant_id,
            event_type=event_type,
            user_id=_optional_str(event_payload, "user") or "",
            channel_id=_required_str(event_payload, "channel"),
            text=_optional_str(event_payload, "text") or "",
            ts=_required_str(event_payload, "ts"),
            thread_ts=_optional_str(event_payload, "thread_ts"),
            channel_type=_optional_str(event_payload, "channel_type"),
            bot_id=_optional_str(event_payload, "bot_id"),
            subtype=_optional_str(event_payload, "subtype"),
            entrypoint=_optional_str(payload, "entrypoint") or "events_api",
        )

    @property
    def is_mention(self) -> bool:
        return self.event_type == "app_mention"

    @property
    def is_bot_message(self) -> bool:
        return self.event_type == "message" and (
            self.bot_id is not None or self.subtype is not None or not self.user_id
        )

    @property
    def clean_text(self) -> str:
        return strip_slack_mentions(self.text)

    @property
    def target_thread_ts(self) -> str:
        return self.thread_ts or self.ts


@dataclass(frozen=True)
class SlackEventPolicy:
    require_channel_mention: bool = True
    allowed_channel_ids: frozenset[str] = frozenset()
    free_response_channel_ids: frozenset[str] = frozenset()
    allowed_user_ids: frozenset[str] = frozenset()

    def allows(
        self,
        payload: SlackEventPayload,
        *,
        thread_has_participation: bool = False,
    ) -> bool:
        if self.allowed_user_ids and payload.user_id not in self.allowed_user_ids:
            return False
        if self.allowed_channel_ids and payload.channel_id not in self.allowed_channel_ids:
            return False
        if payload.channel_type == "im":
            return True
        if payload.channel_id in self.free_response_channel_ids:
            return True
        if thread_has_participation:
            return True
        return not self.require_channel_mention or payload.is_mention


class SlackSlashCommandWorker:
    def __init__(
        self,
        *,
        run_service: Any,
        response_url_client: SlackResponseUrlClient,
        messaging_client: SlackMessagingClient | None = None,
        reminder_store: SlackReminderStore | None = None,
        rate_limiter: SlackUserRateLimiter | None = None,
        backpressure_limiter: SlackBackpressureController | None = None,
        approval_store: ApprovalRequestStore | None = None,
    ) -> None:
        self._run_service = run_service
        self._response_url_client = response_url_client
        self._messaging_client = messaging_client
        self._reminder_store = reminder_store
        self._rate_limiter = rate_limiter
        self._backpressure_limiter = backpressure_limiter
        self._approval_store = approval_store

    async def handle_outbox_payload(
        self,
        payload: Mapping[str, object],
        *,
        tenant_id: str,
    ) -> None:
        await self.handle(
            SlackSlashCommandPayload.from_outbox_payload(payload, tenant_id=tenant_id)
        )

    async def handle(self, payload: SlackSlashCommandPayload) -> None:
        raw_prompt = payload.text.strip()
        if not raw_prompt:
            await self._send(
                payload.response_url,
                response_type="ephemeral",
                text="Please enter a question. Example: /reactor What are my tasks today?",
            )
            return
        if self._rate_limiter is not None and not await slack_user_rate_limit_allows(
            self._rate_limiter,
            payload.tenant_id,
            payload.user_id,
        ):
            await self._send(
                payload.response_url,
                response_type="ephemeral",
                text=(
                    ":no_entry: You are sending requests too quickly. "
                    "Please wait a moment and try again."
                ),
            )
            return
        intent = parse_slack_slash_intent(raw_prompt)
        if isinstance(intent, SlackHelpIntent):
            await self._send(
                payload.response_url,
                response_type="ephemeral",
                text=slack_help_text(payload.command),
            )
            return
        if isinstance(
            intent,
            (
                SlackReminderAddIntent,
                SlackReminderListIntent,
                SlackReminderDoneIntent,
                SlackReminderClearIntent,
            ),
        ):
            await self._handle_reminder_intent(payload, intent)
            return
        if self._backpressure_limiter is not None:
            acquired = await self._backpressure_limiter.acquire()
            if not acquired:
                await self._send(
                    payload.response_url,
                    response_type="ephemeral",
                    text=(
                        ":hourglass_flowing_sand: Reactor is handling too many Slack "
                        "requests right now. Please try again shortly."
                    ),
                )
                return
            try:
                await self._handle_agent_intent(payload, raw_prompt, intent)
            finally:
                self._backpressure_limiter.release()
            return
        await self._handle_agent_intent(payload, raw_prompt, intent)

    async def _handle_agent_intent(
        self,
        payload: SlackSlashCommandPayload,
        raw_prompt: str,
        intent: Any,
    ) -> None:
        question = question_attachment(payload)
        thread_ts: str | None = None
        if self._messaging_client is not None:
            question_result = await self._messaging_client.send_message(
                channel_id=slack_target_channel_id(payload),
                text="",
                attachments=[question],
            )
            if question_result.ok and question_result.ts is not None:
                thread_ts = question_result.ts
            else:
                await self._send(
                    payload.response_url,
                    response_type="in_channel",
                    text="",
                    attachments=[question],
                )
        else:
            await self._send(
                payload.response_url,
                response_type="in_channel",
                text="",
                attachments=[question],
            )
        try:
            result = await self._run_service.create_run(
                intent.prompt,
                tenant_id=payload.tenant_id,
                user_id=payload.user_id,
                thread_id=slack_thread_id(payload, thread_ts),
                metadata={
                    "source": "slack",
                    "channel": "slack",
                    "entrypoint": payload.entrypoint,
                    "slackChannelId": payload.channel_id,
                    "slackChannelName": payload.channel_name,
                    "slackTeamId": payload.team_id,
                    "slackUserId": payload.user_id,
                    "slackUserName": payload.user_name,
                    "slackCommand": payload.command,
                    "slackTriggerId": payload.trigger_id,
                    "slackThreadTs": thread_ts,
                    "intent": intent.mode,
                },
            )
        except Exception:
            await self._send(
                payload.response_url,
                response_type="ephemeral",
                text=":x: 내부 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            )
            return
        response_text = mention_user(
            payload.user_id,
            format_slack_run_response(result, original_prompt=raw_prompt),
        )
        approval_blocks = await self._approval_blocks_for_result(
            result,
            payload=payload,
            thread_ts=thread_ts,
        )
        response_text = with_approval_resume_reference(
            response_text,
            result=result,
            approval=approval_blocks,
        )
        if self._messaging_client is not None and thread_ts is not None:
            send_result = await self._messaging_client.send_message(
                channel_id=slack_target_channel_id(payload),
                text=response_text,
                thread_ts=thread_ts,
                blocks=approval_blocks.blocks if approval_blocks is not None else None,
            )
            if send_result.ok:
                return
        await self._send(
            payload.response_url,
            response_type="in_channel",
            text=response_text,
            blocks=approval_blocks.blocks if approval_blocks is not None else None,
        )

    async def _approval_blocks_for_result(
        self,
        result: Any,
        *,
        payload: SlackSlashCommandPayload,
        thread_ts: str | None,
    ) -> SlackApprovalRender | None:
        if self._approval_store is None or thread_ts is None:
            return None
        approval_request = approval_request_from_result(result)
        if approval_request is None:
            return None
        run_id = string_value(approval_request, "run_id") or result.run_id
        tool_id = string_value(approval_request, "tool_id")
        requested_by = string_value(approval_request, "requested_by") or payload.user_id
        if tool_id is None:
            return None
        request_payload = {
            **approval_request,
            "slack_channel_id": payload.channel_id,
            "slack_thread_ts": thread_ts,
        }
        approval_id = await self._approval_store.request_approval(
            ApprovalRequest(
                tenant_id=payload.tenant_id,
                run_id=run_id,
                tool_id=tool_id,
                requested_by=requested_by,
                request_payload=request_payload,
            )
        )
        return SlackApprovalRender(
            approval_id=approval_id,
            blocks=approval_blocks(
                approval_id=approval_id,
                result=result,
                tool_id=tool_id,
                requested_by=requested_by,
                channel_id=payload.channel_id,
                thread_ts=thread_ts,
            ),
        )

    async def _send(
        self,
        response_url: str,
        *,
        response_type: str,
        text: str,
        attachments: list[Mapping[str, object]] | None = None,
        blocks: list[Mapping[str, object]] | None = None,
    ) -> bool:
        payload: dict[str, object] = {
            "response_type": response_type,
            "text": text,
        }
        if attachments is not None:
            payload["attachments"] = attachments
        if blocks is not None:
            payload["blocks"] = blocks
        return await self._response_url_client.send(
            response_url,
            payload,
        )

    async def _handle_reminder_intent(
        self,
        payload: SlackSlashCommandPayload,
        intent: (
            SlackReminderAddIntent
            | SlackReminderListIntent
            | SlackReminderDoneIntent
            | SlackReminderClearIntent
        ),
    ) -> None:
        if self._reminder_store is None:
            await self._send(
                payload.response_url,
                response_type="ephemeral",
                text="Reminder feature is temporarily unavailable. Please try again later.",
            )
            return
        if isinstance(intent, SlackReminderAddIntent):
            reminder = self._reminder_store.add(payload.user_id, intent.text)
            time_info = (
                f" :bell: I'll DM you at {reminder.due_at.isoformat()}."
                if reminder.due_at is not None
                else ""
            )
            await self._send(
                payload.response_url,
                response_type="ephemeral",
                text=f"Saved reminder #{reminder.id}: {reminder.text}{time_info}",
            )
            return
        if isinstance(intent, SlackReminderListIntent):
            reminders = self._reminder_store.list(payload.user_id)
            if not reminders:
                text = (
                    "No saved reminders. Try: "
                    f"{payload.command} remind Follow up with design review at 3pm"
                )
            else:
                items = "\n".join(f"- #{reminder.id} {reminder.text}" for reminder in reminders)
                text = f"Your reminders:\n{items}"
            await self._send(payload.response_url, response_type="ephemeral", text=text)
            return
        if isinstance(intent, SlackReminderDoneIntent):
            reminder = self._reminder_store.done(payload.user_id, intent.reminder_id)
            text = (
                f"Completed reminder #{reminder.id}: {reminder.text}"
                if reminder is not None
                else (
                    f"Reminder #{intent.reminder_id} was not found. "
                    f"Use {payload.command} remind list."
                )
            )
            await self._send(payload.response_url, response_type="ephemeral", text=text)
            return
        removed = self._reminder_store.clear(payload.user_id)
        await self._send(
            payload.response_url,
            response_type="ephemeral",
            text=f"Cleared {removed} reminder(s).",
        )


class SlackEventWorker:
    def __init__(
        self,
        *,
        run_service: Any,
        messaging_client: SlackMessagingClient,
        faq_responder: SlackFaqResponder | None = None,
        faq_metrics: SlackFaqMetrics | None = None,
        rate_limiter: SlackUserRateLimiter | None = None,
        backpressure_limiter: SlackBackpressureController | None = None,
        event_policy: SlackEventPolicy | None = None,
        thread_participation_tracker: SlackThreadParticipationTracker | None = None,
        thread_context_client: SlackThreadContextClient | None = None,
        assistant_context_store: SlackAssistantThreadContextStore | None = None,
        assistant_status_client: SlackAssistantStatusClient | None = None,
        thread_context_limit: int = 8,
        approval_store: ApprovalRequestStore | None = None,
        bot_response_tracker: BotResponseTracker | None = None,
        feedback_store: FeedbackStore | None = None,
    ) -> None:
        self._run_service = run_service
        self._messaging_client = messaging_client
        self._faq_responder = faq_responder
        self._faq_metrics = faq_metrics
        self._rate_limiter = rate_limiter
        self._backpressure_limiter = backpressure_limiter
        self._event_policy = event_policy or SlackEventPolicy()
        self._thread_participation_tracker = (
            thread_participation_tracker or InMemorySlackThreadParticipationTracker()
        )
        self._thread_context_client = thread_context_client
        self._assistant_context_store = (
            assistant_context_store or InMemorySlackAssistantThreadContextStore()
        )
        self._assistant_status_client = assistant_status_client
        self._thread_context_limit = max(1, min(thread_context_limit, 100))
        self._approval_store = approval_store
        self._bot_response_tracker = bot_response_tracker
        self._feedback_store = feedback_store

    @property
    def thread_participation_tracker(self) -> SlackThreadParticipationTracker:
        return self._thread_participation_tracker

    @property
    def bot_response_tracker(self) -> BotResponseTracker | None:
        return self._bot_response_tracker

    @property
    def feedback_store(self) -> FeedbackStore | None:
        return self._feedback_store

    async def handle_outbox_payload(
        self,
        payload: Mapping[str, object],
        *,
        tenant_id: str,
    ) -> None:
        await self.handle(SlackEventPayload.from_outbox_payload(payload, tenant_id=tenant_id))

    async def handle(self, payload: SlackEventPayload) -> None:
        if payload.event_type == "reaction_added":
            await self._record_reaction_feedback(payload)
            return
        if payload.event_type in {"assistant_thread_started", "assistant_thread_context_changed"}:
            await self._record_assistant_thread_context(payload)
            return
        if payload.event_type not in {"app_mention", "message"}:
            return
        if payload.is_bot_message:
            return
        clean_text = payload.clean_text
        if not clean_text:
            return
        thread_has_participation = await self._thread_has_participation(payload)
        if not self._event_policy.allows(
            payload,
            thread_has_participation=thread_has_participation,
        ):
            return
        if self._rate_limiter is not None and not await slack_user_rate_limit_allows(
            self._rate_limiter,
            payload.tenant_id,
            payload.user_id,
        ):
            await self._send_thread_reply(
                payload,
                mention_user(
                    payload.user_id,
                    (
                        ":no_entry: You are sending requests too quickly. "
                        "Please wait a moment and try again."
                    ),
                ),
            )
            return
        if self._backpressure_limiter is not None:
            acquired = await self._backpressure_limiter.acquire()
            if not acquired:
                await self._send_thread_reply(
                    payload,
                    mention_user(
                        payload.user_id,
                        (
                            ":hourglass_flowing_sand: Reactor is handling too many "
                            "Slack requests right now. Please try again shortly."
                        ),
                    ),
                )
                return
            try:
                await self._handle_agent_or_faq(
                    payload,
                    clean_text,
                    hydrate_thread_context=should_hydrate_thread_context(
                        payload,
                        thread_has_participation=thread_has_participation,
                    ),
                )
            finally:
                self._backpressure_limiter.release()
            return
        await self._handle_agent_or_faq(
            payload,
            clean_text,
            hydrate_thread_context=should_hydrate_thread_context(
                payload,
                thread_has_participation=thread_has_participation,
            ),
        )

    async def _handle_agent_or_faq(
        self,
        payload: SlackEventPayload,
        clean_text: str,
        *,
        hydrate_thread_context: bool = False,
    ) -> None:
        faq_reply = await self._try_faq_reply(payload, clean_text)
        if faq_reply is not None:
            send_result = await self._send_thread_reply(
                payload,
                mention_user(payload.user_id, faq_reply.text),
            )
            if send_result.ok:
                self._track_faq_reply(payload, faq_reply, send_result)
                return
        agent_input = await self._agent_input_with_thread_context(
            payload,
            clean_text,
            hydrate_thread_context=hydrate_thread_context,
        )
        assistant_context = await self._assistant_thread_context_for_payload(payload)
        await self._set_assistant_status(assistant_context, "is thinking...")
        try:
            result = await self._run_service.create_run(
                agent_input,
                tenant_id=payload.tenant_id,
                user_id=payload.user_id,
                thread_id=slack_event_thread_id(payload),
                metadata=slack_run_metadata(payload, assistant_context=assistant_context),
            )
        finally:
            await self._set_assistant_status(assistant_context, "")
        approval_blocks = await self._approval_blocks_for_result(result, payload=payload)
        reply_blocks = slack_agent_reply_blocks(
            approval=approval_blocks,
            include_feedback=self._bot_response_tracker is not None,
        )
        send_result = await self._send_thread_reply(
            payload,
            with_approval_resume_reference(
                mention_user(
                    payload.user_id,
                    format_slack_run_response(result, original_prompt=clean_text),
                ),
                result=result,
                approval=approval_blocks,
            ),
            blocks=reply_blocks,
        )
        if send_result.ok:
            self._track_agent_reply(payload, clean_text, result, send_result)

    async def _agent_input_with_thread_context(
        self,
        payload: SlackEventPayload,
        clean_text: str,
        *,
        hydrate_thread_context: bool,
    ) -> str:
        if (
            not hydrate_thread_context
            or self._thread_context_client is None
            or payload.thread_ts is None
        ):
            return clean_text
        try:
            messages = await self._thread_context_client.fetch_thread_messages(
                channel_id=payload.channel_id,
                thread_ts=payload.thread_ts,
                limit=self._thread_context_limit,
            )
        except Exception:
            return clean_text
        context = format_slack_thread_context(
            messages,
            current_message_ts=payload.ts,
        )
        if not context:
            return clean_text
        return f"{context}\n[Current Slack message]\n{clean_text}"

    async def _record_assistant_thread_context(self, payload: SlackEventPayload) -> None:
        context = assistant_thread_context_from_payload(payload)
        if context is None:
            return
        await self._assistant_context_store.save(tenant_id=payload.tenant_id, context=context)

    async def _assistant_thread_context_for_payload(
        self,
        payload: SlackEventPayload,
    ) -> SlackAssistantThreadContext | None:
        if payload.thread_ts is None:
            return None
        return await self._assistant_context_store.get(
            tenant_id=payload.tenant_id,
            assistant_channel_id=payload.channel_id,
            thread_ts=payload.thread_ts,
        )

    async def _set_assistant_status(
        self,
        context: SlackAssistantThreadContext | None,
        status: str,
    ) -> None:
        if self._assistant_status_client is None or context is None:
            return
        try:
            await self._assistant_status_client.set_status(
                channel_id=context.assistant_channel_id,
                thread_ts=context.thread_ts,
                status=status,
            )
        except Exception:
            return

    async def _try_faq_reply(
        self,
        payload: SlackEventPayload,
        clean_text: str,
    ) -> Any:
        if self._faq_responder is None:
            return None
        try:
            return await self._faq_responder.try_auto_reply(
                tenant_id=payload.tenant_id,
                channel_id=payload.channel_id,
                user_id=payload.user_id,
                user_query=clean_text,
                is_mention=payload.is_mention,
            )
        except Exception:
            return None

    async def _send_thread_reply(
        self,
        payload: SlackEventPayload,
        text: str,
        attachments: list[Mapping[str, object]] | None = None,
        blocks: list[Mapping[str, object]] | None = None,
    ) -> SlackMessageSendResult:
        result = await self._messaging_client.send_message(
            channel_id=payload.channel_id,
            text=text,
            thread_ts=payload.target_thread_ts,
            attachments=attachments,
            blocks=blocks,
        )
        if result.error == "rate_limited":
            raise SlackRetryableSendError(
                "rate_limited",
                retry_after_seconds=result.retry_after_seconds,
            )
        if result.ok:
            await self._thread_participation_tracker.record_participation(
                tenant_id=payload.tenant_id,
                channel_id=payload.channel_id,
                thread_ts=payload.target_thread_ts,
            )
        return result

    async def _approval_blocks_for_result(
        self,
        result: Any,
        *,
        payload: SlackEventPayload,
    ) -> SlackApprovalRender | None:
        if self._approval_store is None:
            return None
        approval_request = approval_request_from_result(result)
        if approval_request is None:
            return None
        tool_id = string_value(approval_request, "tool_id")
        requested_by = string_value(approval_request, "requested_by") or payload.user_id
        if tool_id is None:
            return None
        request_payload = {
            **approval_request,
            "slack_channel_id": payload.channel_id,
            "slack_thread_ts": payload.target_thread_ts,
        }
        approval_id = await self._approval_store.request_approval(
            ApprovalRequest(
                tenant_id=payload.tenant_id,
                run_id=result.run_id,
                tool_id=tool_id,
                requested_by=requested_by,
                request_payload=request_payload,
            )
        )
        return SlackApprovalRender(
            approval_id=approval_id,
            blocks=approval_blocks(
                approval_id=approval_id,
                result=result,
                tool_id=tool_id,
                requested_by=requested_by,
                channel_id=payload.channel_id,
                thread_ts=payload.target_thread_ts,
            ),
        )

    async def _thread_has_participation(self, payload: SlackEventPayload) -> bool:
        if payload.thread_ts is None:
            return False
        return await self._thread_participation_tracker.has_participated(
            tenant_id=payload.tenant_id,
            channel_id=payload.channel_id,
            thread_ts=payload.thread_ts,
        )

    def _track_faq_reply(
        self,
        payload: SlackEventPayload,
        faq_reply: Any,
        send_result: SlackMessageSendResult,
    ) -> None:
        if self._faq_metrics is None or send_result.ts is None:
            return
        doc_ids = getattr(faq_reply, "matched_document_ids", None)
        if not isinstance(doc_ids, list):
            return
        string_doc_ids = [item for item in cast(list[object], doc_ids) if isinstance(item, str)]
        self._faq_metrics.track_reply(
            payload.channel_id,
            send_result.ts,
            string_doc_ids,
        )

    def _track_agent_reply(
        self,
        payload: SlackEventPayload,
        user_prompt: str,
        result: Any,
        send_result: SlackMessageSendResult,
    ) -> None:
        if self._bot_response_tracker is None or send_result.ts is None:
            return
        self._bot_response_tracker.track(
            TrackedBotResponse(
                channel_id=payload.channel_id,
                message_ts=send_result.ts,
                session_id=str(getattr(result, "thread_id", slack_event_thread_id(payload))),
                user_prompt=user_prompt,
                user_id=payload.user_id,
                response=str(getattr(result, "response", "")),
                run_id=getattr(result, "run_id", None),
                tags=["slack", "agent-run"],
                template_id="slack-agent-run",
                model=optional_string_attr(result, "model"),
                prompt_version=optional_int_metadata(result, "prompt_version", "promptVersion"),
                tools_used=optional_string_list_metadata(
                    result,
                    "toolsUsed",
                    "toolNames",
                    "tools_used",
                    "tool_names",
                ),
            )
        )

    async def _record_reaction_feedback(self, payload: SlackEventPayload) -> None:
        if payload.reaction is None:
            return
        rating = reaction_rating(payload.reaction)
        if rating is None:
            return
        if self._faq_metrics is not None:
            doc_ids = self._faq_metrics.doc_ids_for_reply(payload.channel_id, payload.ts)
            if doc_ids:
                self._faq_metrics.record_feedback(
                    payload.channel_id,
                    doc_ids,
                    rating,
                    event_id=slack_reaction_feedback_id(payload),
                )
        await self._record_agent_reaction_feedback(payload, rating)

    async def _record_agent_reaction_feedback(
        self,
        payload: SlackEventPayload,
        rating: bool,
    ) -> None:
        if self._feedback_store is None or self._bot_response_tracker is None:
            return
        tracked = self._bot_response_tracker.lookup(payload.channel_id, payload.ts)
        if tracked is None:
            return
        await self._feedback_store.save(
            feedback_with_workflow_tags(
                Feedback(
                    feedback_id=slack_reaction_feedback_id(payload),
                    query=tracked.user_prompt,
                    response=tracked.response,
                    rating=FeedbackRating.THUMBS_UP if rating else FeedbackRating.THUMBS_DOWN,
                    session_id=tracked.session_id,
                    user_id=tracked.user_id or payload.user_id,
                    tenant_id=payload.tenant_id,
                    source="slack_reaction",
                    run_id=tracked.run_id,
                    tags=tracked.tags,
                    template_id=tracked.template_id,
                    model=tracked.model,
                    prompt_version=tracked.prompt_version,
                    tools_used=tracked.tools_used,
                )
            )
        )


def slack_reaction_feedback_id(payload: SlackEventPayload) -> str:
    fingerprint = hashlib.sha256(
        "\x1f".join(
            [
                payload.tenant_id,
                payload.channel_id,
                payload.ts,
                payload.user_id,
                payload.reaction or "",
            ]
        ).encode("utf-8")
    ).hexdigest()[:32]
    return f"slack-reaction:{fingerprint}"


class ChannelFaqIngestWorker:
    def __init__(
        self,
        *,
        registration_store: Any,
        ingestion_service: ChannelFaqIngestionService,
    ) -> None:
        self._registration_store = registration_store
        self._ingestion_service = ingestion_service

    async def handle_outbox_payload(
        self,
        payload: Mapping[str, object],
        *,
        tenant_id: str,
    ) -> ChannelFaqIngestResult:
        return await self.handle(
            ChannelFaqIngestPayload.from_outbox_payload(payload, tenant_id=tenant_id)
        )

    async def handle(self, payload: ChannelFaqIngestPayload) -> ChannelFaqIngestResult:
        registration = await maybe_await(
            self._registration_store.get(
                tenant_id=payload.tenant_id,
                channel_id=payload.channel_id,
            )
        )
        if registration is None:
            return ChannelFaqIngestResult(
                channel_id=payload.channel_id,
                messages_scanned=0,
                document_count=0,
                chunk_count=0,
                api_calls=0,
                status=IngestStatus.FAILED.value,
                error=f"Slack channel FAQ registration not found: {payload.channel_id}",
            )

        await maybe_await(
            self._registration_store.update_ingest_result(
                tenant_id=payload.tenant_id,
                channel_id=payload.channel_id,
                status=IngestStatus.RUNNING.value,
                message_count=None,
                chunk_count=None,
                error=None,
            )
        )
        try:
            result = await self._ingestion_service.ingest_recent(
                tenant_id=payload.tenant_id,
                channel_id=payload.channel_id,
                max_messages=faq_max_messages(payload.days_back),
            )
        except Exception:
            message = SLACK_FAQ_INGESTION_FAILED
            await maybe_await(
                self._registration_store.update_ingest_result(
                    tenant_id=payload.tenant_id,
                    channel_id=payload.channel_id,
                    status=IngestStatus.FAILED.value,
                    message_count=None,
                    chunk_count=None,
                    error=message,
                )
            )
            return ChannelFaqIngestResult(
                channel_id=payload.channel_id,
                messages_scanned=0,
                document_count=0,
                chunk_count=0,
                api_calls=0,
                status=IngestStatus.FAILED.value,
                error=message,
            )

        await maybe_await(
            self._registration_store.update_ingest_result(
                tenant_id=payload.tenant_id,
                channel_id=payload.channel_id,
                status=IngestStatus.OK.value,
                message_count=result.messages_scanned,
                chunk_count=result.chunk_count,
                error=None,
            )
        )
        return result


def mention_user(user_id: str, text: str) -> str:
    stripped = text.strip()
    mention = f"<@{user_id}>"
    if stripped.startswith(mention):
        return stripped
    return f"{mention} {stripped}"


def question_attachment(payload: SlackSlashCommandPayload) -> dict[str, object]:
    return {
        "color": "#36a64f",
        "text": f"*<@{payload.user_id}> 님의 질문*\n{payload.text.strip()}",
        "mrkdwn_in": ["text"],
    }


def approval_request_from_result(result: Any) -> dict[str, object] | None:
    raw_response_metadata = getattr(result, "response_metadata", None)
    if not isinstance(raw_response_metadata, Mapping):
        return None
    response_metadata = cast(Mapping[str, object], raw_response_metadata)
    if response_metadata.get("approval_status") != "pending":
        return None
    approval_request = response_metadata.get("approval_request")
    if not isinstance(approval_request, Mapping):
        return None
    return dict(cast(Mapping[str, object], approval_request))


def approval_blocks(
    *,
    approval_id: str,
    result: Any,
    tool_id: str,
    requested_by: str,
    channel_id: str,
    thread_ts: str,
) -> list[Mapping[str, object]]:
    risk_level = string_value(getattr(result, "response_metadata", {}), "tool_risk_level")
    approval_request = approval_request_from_result(result) or {}
    risk_level = string_value(approval_request, "tool_risk_level") or risk_level or "unknown"
    value = {
        "approvalId": approval_id,
        "runId": result.run_id,
        "threadId": result.thread_id,
        "checkpointNs": result.checkpoint_ns,
        "channelId": channel_id,
        "threadTs": thread_ts,
    }
    reject_value = {**value, "reason": "Rejected from Slack"}
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Approval required*\n"
                    f"Tool: `{tool_id}`\n"
                    f"Risk: `{risk_level}`\n"
                    f"Requested by: <@{requested_by}>"
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
                    "value": json.dumps(value, separators=(",", ":")),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Reject"},
                    "style": "danger",
                    "action_id": "approval.reject",
                    "value": json.dumps(reject_value, separators=(",", ":")),
                },
            ],
        },
    ]


def feedback_blocks() -> list[Mapping[str, object]]:
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


def slack_agent_reply_blocks(
    *,
    approval: SlackApprovalRender | None,
    include_feedback: bool,
) -> list[Mapping[str, object]] | None:
    blocks: list[Mapping[str, object]] = []
    if approval is not None:
        blocks.extend(approval.blocks)
    if include_feedback:
        blocks.extend(feedback_blocks())
    return blocks or None


def with_approval_resume_reference(
    text: str,
    *,
    result: Any,
    approval: SlackApprovalRender | None,
) -> str:
    if approval is None:
        return text
    run_id = getattr(result, "run_id", None)
    if not isinstance(run_id, str) or not run_id.strip():
        return text
    return (
        f"{text}\n"
        f"_Resume: `reactor-runs resume {run_id} --approval-id "
        f"{approval.approval_id} --output table`_"
    )


def string_value(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value.strip() else None


def optional_string_attr(value: object, name: str) -> str | None:
    raw = getattr(value, name, None)
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    return stripped or None


def optional_int_metadata(value: object, *keys: str) -> int | None:
    metadata = result_response_metadata(value)
    for key in keys:
        raw = metadata.get(key)
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            stripped = raw.strip()
            if stripped.isdigit():
                return int(stripped)
    return None


def optional_string_list_metadata(value: object, *keys: str) -> list[str] | None:
    metadata = result_response_metadata(value)
    for key in keys:
        raw = metadata.get(key)
        if isinstance(raw, list):
            values = [
                item.strip()
                for item in cast(list[object], raw)
                if isinstance(item, str) and item.strip()
            ]
            if values:
                return list(dict.fromkeys(values))
    return None


def result_response_metadata(value: object) -> Mapping[str, object]:
    raw = getattr(value, "response_metadata", None)
    if isinstance(raw, Mapping):
        return cast(Mapping[str, object], raw)
    return {}


def slack_target_channel_id(payload: SlackSlashCommandPayload) -> str:
    if payload.channel_id.startswith("D"):
        return payload.user_id
    return payload.channel_id


def slack_thread_id(payload: SlackSlashCommandPayload, thread_ts: str | None) -> str:
    if thread_ts is not None:
        return f"slack-{payload.channel_id}-{thread_ts}"
    return f"slack-cmd-{payload.channel_id}-{payload.user_id}"


def slack_event_thread_id(payload: SlackEventPayload) -> str:
    return slack_thread_id_from_parts(
        channel_id=payload.channel_id,
        thread_ts=payload.target_thread_ts,
    )


def slack_run_metadata(
    payload: SlackEventPayload,
    *,
    assistant_context: SlackAssistantThreadContext | None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "source": "slack",
        "channel": "slack",
        "entrypoint": payload.entrypoint,
        "slackEventType": payload.event_type,
        "slackChannelId": payload.channel_id,
        "slackChannelType": payload.channel_type,
        "slackUserId": payload.user_id,
        "slackMessageTs": payload.ts,
        "slackThreadTs": payload.thread_ts,
    }
    if assistant_context is not None:
        metadata["slackAssistantContext"] = assistant_context.to_metadata()
    return metadata


def slack_thread_id_from_parts(*, channel_id: str, thread_ts: str) -> str:
    return f"slack-{channel_id}-{thread_ts}"


def assistant_thread_context_from_payload(
    payload: SlackEventPayload,
) -> SlackAssistantThreadContext | None:
    if payload.thread_ts is None:
        return None
    return SlackAssistantThreadContext(
        assistant_channel_id=payload.channel_id,
        thread_ts=payload.thread_ts,
        user_id=payload.user_id,
        channel_id=payload.assistant_context_channel_id,
        team_id=payload.assistant_context_team_id,
        enterprise_id=payload.assistant_context_enterprise_id,
    )


def should_hydrate_thread_context(
    payload: SlackEventPayload,
    *,
    thread_has_participation: bool,
) -> bool:
    return (
        payload.thread_ts is not None
        and payload.thread_ts != payload.ts
        and payload.is_mention
        and not thread_has_participation
    )


def slack_thread_message_from_payload(
    payload: Mapping[str, object],
) -> SlackThreadMessage | None:
    ts = _optional_str(payload, "ts")
    text = _optional_str(payload, "text")
    user_id = _optional_str(payload, "user") or _optional_str(payload, "bot_id")
    if ts is None or text is None or user_id is None:
        return None
    return SlackThreadMessage(ts=ts, user_id=user_id, text=strip_slack_mentions(text).strip())


def format_slack_thread_context(
    messages: list[SlackThreadMessage],
    *,
    current_message_ts: str,
    max_chars: int = 4000,
) -> str:
    lines = [
        f"- <@{message.user_id}>: {message.text}"
        for message in messages
        if message.ts != current_message_ts and message.text.strip()
    ]
    if not lines:
        return ""
    rendered = "[Slack thread context]\n" + "\n".join(lines)
    if len(rendered) <= max_chars:
        return rendered
    return rendered[: max(0, max_chars - 3)].rstrip() + "..."


def slack_assistant_thread_channel_id(event_payload: Mapping[str, object]) -> str:
    assistant_thread = mapping_value(event_payload, "assistant_thread")
    context = mapping_value(assistant_thread, "context") or mapping_value(event_payload, "context")
    return first_required_str(
        "assistant_thread.channel_id",
        (assistant_thread, ("channel_id",)),
        (event_payload, ("channel",)),
        (context, ("channel_id",)),
    )


def slack_assistant_thread_ts(event_payload: Mapping[str, object]) -> str:
    assistant_thread = mapping_value(event_payload, "assistant_thread")
    return first_required_str(
        "assistant_thread.thread_ts",
        (assistant_thread, ("thread_ts",)),
        (event_payload, ("thread_ts", "message_ts", "ts")),
    )


def slack_assistant_thread_user_id(event_payload: Mapping[str, object]) -> str:
    assistant_thread = mapping_value(event_payload, "assistant_thread")
    context = mapping_value(assistant_thread, "context") or mapping_value(event_payload, "context")
    return first_required_str(
        "assistant_thread.user_id",
        (assistant_thread, ("user_id",)),
        (event_payload, ("user",)),
        (context, ("user_id",)),
    )


def slack_assistant_context_channel_id(event_payload: Mapping[str, object]) -> str | None:
    return _optional_str(slack_assistant_context_payload(event_payload), "channel_id")


def slack_assistant_context_team_id(event_payload: Mapping[str, object]) -> str | None:
    return _optional_str(slack_assistant_context_payload(event_payload), "team_id")


def slack_assistant_context_enterprise_id(event_payload: Mapping[str, object]) -> str | None:
    return _optional_str(slack_assistant_context_payload(event_payload), "enterprise_id")


def slack_assistant_context_payload(event_payload: Mapping[str, object]) -> Mapping[str, object]:
    assistant_thread = mapping_value(event_payload, "assistant_thread")
    return mapping_value(assistant_thread, "context") or mapping_value(event_payload, "context")


def mapping_value(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload.get(key)
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    return {}


def first_required_str(
    label: str,
    *sources_and_keys: tuple[Mapping[str, object], tuple[str, ...]],
) -> str:
    for source_mapping, keys in sources_and_keys:
        for key in keys:
            value = _optional_str(source_mapping, key)
            if value is not None:
                return value
    raise ValueError(f"Slack assistant event field is required: {label}")


def strip_slack_mentions(text: str) -> str:
    parts = text.split()
    filtered = [part for part in parts if not part.startswith(SLACK_MENTION_PATTERN)]
    return " ".join(filtered).strip()


def reaction_rating(reaction: str) -> bool | None:
    normalized = reaction.strip().lower()
    if normalized in {"+1", "thumbsup"}:
        return True
    if normalized in {"-1", "thumbsdown"}:
        return False
    return None


def _required_str(source: Mapping[str, object], key: str) -> str:
    value = source.get(key)
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError(f"Slack slash command field is required: {key}")


def _optional_str(source: Mapping[str, object], key: str) -> str | None:
    value = source.get(key)
    return value if isinstance(value, str) else None


def _optional_int(source: Mapping[str, object], key: str) -> int | None:
    value = source.get(key)
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return int(value)
    return None


def faq_max_messages(days_back: int) -> int:
    return max(50, min(days_back * 10, 1000))


async def maybe_await(value: Any) -> Any:
    if isawaitable(value):
        return await value
    return value


async def slack_user_rate_limit_allows(
    limiter: SlackUserRateLimiter,
    tenant_id: str,
    user_id: str,
) -> bool:
    return bool(await maybe_await(limiter.try_acquire(tenant_id, user_id)))
