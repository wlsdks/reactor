from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import httpx
import respx

from reactor.slack.faq_ingestion import (
    ChannelFaqIngestionService,
    FaqDocument,
    HttpSlackHistoryClient,
    SlackHistoryPage,
    SlackMessage,
)

SLACK_TEST_BOT_TOKEN = "xoxb-test"  # noqa: S105


async def test_faq_ingestion_filters_noise_and_writes_normalized_documents() -> None:
    history_client = RecordingSlackHistoryClient(
        pages=[
            SlackHistoryPage(
                ok=True,
                messages=[
                    SlackMessage(text="안녕하세요", ts="1.0", user="U001"),
                    SlackMessage(
                        text=(
                            "Reactor 연동은 <@U0987654321>에게 물어보고 "
                            "<https://example.com/guide|설정 문서>를 보면 됩니다 :smile:"
                        ),
                        ts="2.0",
                        user="U002",
                    ),
                    SlackMessage(
                        text="자동 봇 메시지는 충분히 길어도 제외되어야 합니다",
                        ts="3.0",
                        user="B001",
                    ),
                    SlackMessage(
                        text="시스템 subtype 메시지도 충분히 길어도 제외되어야 합니다",
                        ts="4.0",
                        user="U003",
                        subtype="channel_join",
                    ),
                    SlackMessage(
                        text="FAQ로 저장할 만큼 충분히 긴 두 번째 사용자 질문입니다",
                        ts="5.0",
                        user="U004",
                    ),
                ],
            )
        ]
    )
    sink = RecordingFaqDocumentSink()
    service = ChannelFaqIngestionService(history_client=history_client, document_sink=sink)

    result = await service.ingest_recent(tenant_id="tenant_1", channel_id="C001", max_messages=10)

    assert result.messages_scanned == 2
    assert result.document_count == 2
    assert result.chunk_count == 2
    assert result.api_calls == 1
    assert history_client.calls == [("C001", 10, None)]
    assert [document.metadata["source"] for document in sink.documents] == [
        "slack-faq",
        "slack-faq",
    ]
    first = sink.documents[0]
    assert first.document_id == "slack-faq:C001:2.0"
    assert first.metadata["channel_id"] == "C001"
    assert first.metadata["ts"] == "2.0"
    assert first.metadata["user"] == "U002"
    assert first.metadata["source_key"] == "slack-faq:C001:2.0"
    assert "@user" in first.content
    assert "설정 문서" in first.content
    assert "U0987654321" not in first.content
    assert "example.com" not in first.content
    assert ":smile:" not in first.content


async def test_faq_ingestion_paginates_until_limit_or_cursor_exhaustion() -> None:
    history_client = RecordingSlackHistoryClient(
        pages=[
            SlackHistoryPage(
                ok=True,
                messages=[
                    SlackMessage(
                        text="첫 번째 페이지에서 수집할 충분히 긴 질문입니다", ts="1.0", user="U1"
                    )
                ],
                next_cursor="cursor_2",
            ),
            SlackHistoryPage(
                ok=True,
                messages=[
                    SlackMessage(
                        text="두 번째 페이지에서 수집할 충분히 긴 답변입니다", ts="2.0", user="U2"
                    )
                ],
            ),
        ]
    )
    sink = RecordingFaqDocumentSink()
    service = ChannelFaqIngestionService(history_client=history_client, document_sink=sink)

    result = await service.ingest_recent(tenant_id="tenant_1", channel_id="C001", max_messages=2)

    assert result.messages_scanned == 2
    assert result.api_calls == 2
    assert history_client.calls == [("C001", 2, None), ("C001", 1, "cursor_2")]
    assert [document.document_id for document in sink.documents] == [
        "slack-faq:C001:1.0",
        "slack-faq:C001:2.0",
    ]


async def test_faq_ingestion_stops_on_slack_api_failure_with_partial_counts() -> None:
    history_client = RecordingSlackHistoryClient(
        pages=[
            SlackHistoryPage(ok=False, messages=[], error="channel_not_found"),
        ]
    )
    sink = RecordingFaqDocumentSink()
    service = ChannelFaqIngestionService(history_client=history_client, document_sink=sink)

    result = await service.ingest_recent(
        tenant_id="tenant_1",
        channel_id="C404",
        max_messages=100,
    )

    assert result.messages_scanned == 0
    assert result.document_count == 0
    assert result.chunk_count == 0
    assert result.api_calls == 1
    assert sink.documents == []


@respx.mock
async def test_http_slack_history_client_maps_slack_response() -> None:
    route = respx.post("https://slack.com/api/conversations.history").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "messages": [
                    {
                        "text": "Reactor FAQ로 저장할 충분히 긴 Slack 메시지입니다",
                        "ts": "1710000000.000100",
                        "user": "U1",
                        "thread_ts": "1710000000.000100",
                    }
                ],
                "response_metadata": {"next_cursor": "next_1"},
            },
        )
    )
    client = HttpSlackHistoryClient(bot_token=SLACK_TEST_BOT_TOKEN)

    page = await client.conversation_history(
        channel_id="C123",
        limit=50,
        cursor="cursor_1",
    )

    assert page.ok is True
    assert page.next_cursor == "next_1"
    assert page.messages == [
        SlackMessage(
            text="Reactor FAQ로 저장할 충분히 긴 Slack 메시지입니다",
            ts="1710000000.000100",
            user="U1",
            thread_ts="1710000000.000100",
        )
    ]
    request = cast(httpx.Request, route.calls[0].request)
    assert request is not None
    assert request.headers["Authorization"] == f"Bearer {SLACK_TEST_BOT_TOKEN}"
    assert request.headers["Content-Type"] == "application/json"
    assert b'"channel":"C123"' in request.content
    assert b'"limit":50' in request.content
    assert b'"cursor":"cursor_1"' in request.content


@respx.mock
async def test_http_slack_history_client_maps_http_failure() -> None:
    respx.post("https://slack.com/api/conversations.history").mock(
        return_value=httpx.Response(429, json={"ok": False, "error": "ratelimited"})
    )
    client = HttpSlackHistoryClient(bot_token=SLACK_TEST_BOT_TOKEN)

    page = await client.conversation_history(channel_id="C123", limit=50)

    assert page.ok is False
    assert page.error == "http_429"
    assert page.messages == []


class RecordingSlackHistoryClient:
    def __init__(self, *, pages: Sequence[SlackHistoryPage]) -> None:
        self._pages = list(pages)
        self.calls: list[tuple[str, int, str | None]] = []

    async def conversation_history(
        self,
        *,
        channel_id: str,
        limit: int,
        cursor: str | None = None,
    ) -> SlackHistoryPage:
        self.calls.append((channel_id, limit, cursor))
        return self._pages.pop(0)


class RecordingFaqDocumentSink:
    def __init__(self) -> None:
        self.documents: list[FaqDocument] = []

    async def add_documents(self, documents: Sequence[FaqDocument], *, tenant_id: str) -> int:
        assert tenant_id == "tenant_1"
        self.documents.extend(documents)
        return len(documents)
