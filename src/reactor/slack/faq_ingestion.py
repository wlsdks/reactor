from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, cast

import httpx

from reactor.slack.worker import ChannelFaqIngestResult

DEFAULT_MAX_MESSAGES = 200
MAX_PER_CALL = 200
MAX_API_CALLS = 5
MIN_TEXT_LEN = 20
SLACK_FAQ_COLLECTION = "slack-faq"

SYSTEM_MESSAGE_SUBTYPES = {
    "channel_join",
    "channel_leave",
    "channel_topic",
    "channel_purpose",
    "channel_name",
    "channel_archive",
    "channel_unarchive",
    "group_join",
    "group_leave",
    "group_topic",
    "group_purpose",
    "group_name",
    "group_archive",
    "group_unarchive",
    "bot_message",
    "bot_add",
    "bot_remove",
    "reminder_add",
    "pinned_item",
    "unpinned_item",
    "channel_convert_to_private",
    "channel_convert_to_public",
}

SLACK_USER_MENTION = re.compile(r"<@[UW][A-Z0-9]+(?:\|[^>]+)?>")
SLACK_SPECIAL_MENTION = re.compile(r"<!(channel|here|everyone)(?:\|[^>]+)?>")
SLACK_CHANNEL_REF = re.compile(r"<#[CG][A-Z0-9]+\|([^>]+)>")
SLACK_URL_WITH_LABEL = re.compile(r"<https?://[^|>]+\|([^>]+)>")
SLACK_URL_ONLY = re.compile(r"<https?://[^>]+>")
EMOJI_SHORTCODE = re.compile(r":[a-zA-Z][a-zA-Z0-9_+\-]*:")
CODE_FENCE = re.compile(r"```")
INLINE_CODE = re.compile(r"`")
MULTI_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class SlackMessage:
    text: str | None
    ts: str | None
    user: str | None
    subtype: str | None = None
    thread_ts: str | None = None


@dataclass(frozen=True)
class SlackHistoryPage:
    ok: bool
    messages: Sequence[SlackMessage]
    next_cursor: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class FaqDocument:
    document_id: str
    content: str
    metadata: dict[str, object] = field(default_factory=lambda: {})


class SlackHistoryClient(Protocol):
    async def conversation_history(
        self,
        *,
        channel_id: str,
        limit: int,
        cursor: str | None = None,
    ) -> SlackHistoryPage: ...


class HttpSlackHistoryClient:
    def __init__(
        self,
        *,
        bot_token: str,
        timeout_seconds: float = 10.0,
        api_base_url: str = "https://slack.com/api",
    ) -> None:
        self._bot_token = bot_token
        self._timeout_seconds = timeout_seconds
        self._api_base_url = api_base_url.rstrip("/")

    async def conversation_history(
        self,
        *,
        channel_id: str,
        limit: int,
        cursor: str | None = None,
    ) -> SlackHistoryPage:
        payload: dict[str, object] = {
            "channel": channel_id,
            "limit": limit,
        }
        if cursor is not None:
            payload["cursor"] = cursor
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                f"{self._api_base_url}/conversations.history",
                content=json.dumps(payload, separators=(",", ":")),
                headers={
                    "Authorization": f"Bearer {self._bot_token}",
                    "Content-Type": "application/json",
                },
            )
        if response.status_code >= 400:
            return SlackHistoryPage(
                ok=False,
                messages=[],
                error=f"http_{response.status_code}",
            )
        body = response.json()
        if not isinstance(body, dict):
            return SlackHistoryPage(ok=False, messages=[], error="invalid_response")
        response_body = cast(dict[str, object], body)
        if response_body.get("ok") is not True:
            error = response_body.get("error")
            return SlackHistoryPage(
                ok=False,
                messages=[],
                error=error if isinstance(error, str) else "slack_api_error",
            )
        return SlackHistoryPage(
            ok=True,
            messages=slack_messages_from_response(response_body.get("messages")),
            next_cursor=next_cursor_from_response(response_body.get("response_metadata")),
        )


class FaqDocumentSink(Protocol):
    async def add_documents(
        self,
        documents: Sequence[FaqDocument],
        *,
        tenant_id: str,
    ) -> int: ...


class ChannelFaqIngestionService:
    def __init__(
        self,
        *,
        history_client: SlackHistoryClient,
        document_sink: FaqDocumentSink,
    ) -> None:
        self._history_client = history_client
        self._document_sink = document_sink

    async def ingest_recent(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        max_messages: int = DEFAULT_MAX_MESSAGES,
    ) -> ChannelFaqIngestResult:
        documents: list[FaqDocument] = []
        cursor: str | None = None
        api_calls = 0

        while len(documents) < max_messages and api_calls < MAX_API_CALLS:
            limit = min(MAX_PER_CALL, max_messages - len(documents))
            page = await self._history_client.conversation_history(
                channel_id=channel_id,
                limit=limit,
                cursor=cursor,
            )
            api_calls += 1
            if not page.ok:
                break
            for message in page.messages:
                document = document_from_slack_message(channel_id=channel_id, message=message)
                if document is not None:
                    documents.append(document)
                if len(documents) >= max_messages:
                    break
            cursor = page.next_cursor
            if cursor is None:
                break

        chunk_count = (
            await self._document_sink.add_documents(documents, tenant_id=tenant_id)
            if documents
            else 0
        )
        return ChannelFaqIngestResult(
            channel_id=channel_id,
            messages_scanned=len(documents),
            document_count=len(documents),
            chunk_count=chunk_count,
            api_calls=api_calls,
        )


def document_from_slack_message(
    *,
    channel_id: str,
    message: SlackMessage,
) -> FaqDocument | None:
    if should_skip(message):
        return None
    text = normalize_for_embedding(message.text or "")
    ts = message.ts or ""
    source_key = f"slack-faq:{channel_id}:{ts}"
    metadata: dict[str, object] = {
        "source": "slack-faq",
        "collection": SLACK_FAQ_COLLECTION,
        "channel_id": channel_id,
        "ts": ts,
        "user": message.user or "",
        "source_key": source_key,
        "thread_aggregated": False,
    }
    if message.thread_ts is not None:
        metadata["thread_ts"] = message.thread_ts
    return FaqDocument(
        document_id=source_key,
        content=text,
        metadata=metadata,
    )


def should_skip(message: SlackMessage) -> bool:
    if message.subtype is not None and message.subtype in SYSTEM_MESSAGE_SUBTYPES:
        return True
    text = message.text or ""
    if not text.strip():
        return True
    if len(text.strip()) < MIN_TEXT_LEN:
        return True
    return bool(message.user and message.user.startswith("B"))


def normalize_for_embedding(text: str) -> str:
    if not text.strip():
        return text
    normalized = SLACK_USER_MENTION.sub("@user", text)
    normalized = SLACK_SPECIAL_MENTION.sub(r"@\1", normalized)
    normalized = SLACK_CHANNEL_REF.sub(r"#\1", normalized)
    normalized = SLACK_URL_WITH_LABEL.sub(r"\1", normalized)
    normalized = SLACK_URL_ONLY.sub("link", normalized)
    normalized = EMOJI_SHORTCODE.sub(" ", normalized)
    normalized = CODE_FENCE.sub(" ", normalized)
    normalized = INLINE_CODE.sub(" ", normalized)
    return MULTI_WHITESPACE.sub(" ", normalized).strip()


def slack_messages_from_response(value: object) -> list[SlackMessage]:
    if not isinstance(value, list):
        return []
    messages: list[SlackMessage] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            continue
        raw = cast(dict[str, object], item)
        messages.append(
            SlackMessage(
                text=optional_str(raw, "text"),
                ts=optional_str(raw, "ts"),
                user=optional_str(raw, "user"),
                subtype=optional_str(raw, "subtype"),
                thread_ts=optional_str(raw, "thread_ts"),
            )
        )
    return messages


def optional_str(source: dict[str, object], key: str) -> str | None:
    value = source.get(key)
    return value if isinstance(value, str) else None


def next_cursor_from_response(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    cursor = cast(dict[str, object], value).get("next_cursor")
    if isinstance(cursor, str) and cursor.strip():
        return cursor
    return None
