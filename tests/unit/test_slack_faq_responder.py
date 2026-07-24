from __future__ import annotations

from collections.abc import Sequence

from reactor.rag.documents import RagChunkCandidate
from reactor.rag.retriever import RankedChunk, RetrievalQuery
from reactor.slack.faq import (
    AutoReplyMode,
    ChannelFaqRegistration,
    InMemoryChannelFaqRegistrationStore,
)
from reactor.slack.faq_responder import SlackChannelFaqResponder


async def test_faq_responder_mention_mode_hits_and_formats_reply() -> None:
    store = InMemoryChannelFaqRegistrationStore()
    store.save(
        ChannelFaqRegistration(
            tenant_id="tenant_1",
            channel_id="C123",
            auto_reply_mode=AutoReplyMode.MENTION,
            confidence_threshold=0.5,
        )
    )
    retriever = RecordingFaqRetriever(
        chunks=[
            ranked_chunk(
                document_id="doc_1",
                content="FAQ 정답 본문입니다",
                metadata={"distance": 0.2, "user": "U555", "ts": "10.123"},
            )
        ]
    )
    responder = SlackChannelFaqResponder(registration_store=store, retriever=retriever)

    reply = await responder.try_auto_reply(
        tenant_id="tenant_1",
        channel_id="C123",
        user_id="U123",
        user_query="해야할일 검색",
        is_mention=True,
    )

    assert reply is not None
    assert "FAQ 정답 본문입니다" in reply.text
    assert "<@U555>" in reply.text
    assert "0.90" in reply.text
    assert reply.score == 0.9
    assert reply.matched_document_ids == ["doc_1"]
    assert retriever.queries[0].tenant_id == "tenant_1"
    assert retriever.queries[0].collection == "slack-faq"
    assert retriever.queries[0].principal_id == "U123"


async def test_faq_responder_falls_back_when_mode_or_threshold_does_not_match() -> None:
    store = InMemoryChannelFaqRegistrationStore()
    store.save(
        ChannelFaqRegistration(
            tenant_id="tenant_1",
            channel_id="C123",
            auto_reply_mode=AutoReplyMode.MENTION,
            confidence_threshold=0.9,
        )
    )
    retriever = RecordingFaqRetriever(
        chunks=[
            ranked_chunk(
                document_id="doc_low",
                content="낮은 점수",
                metadata={"distance": 0.8},
            )
        ]
    )
    responder = SlackChannelFaqResponder(registration_store=store, retriever=retriever)

    regular_message = await responder.try_auto_reply(
        tenant_id="tenant_1",
        channel_id="C123",
        user_id="U123",
        user_query="일반 메시지",
        is_mention=False,
    )
    low_confidence = await responder.try_auto_reply(
        tenant_id="tenant_1",
        channel_id="C123",
        user_id="U123",
        user_query="멘션 질문",
        is_mention=True,
    )

    assert regular_message is None
    assert low_confidence is None
    assert len(retriever.queries) == 1


async def test_faq_responder_always_mode_triggers_once_per_cooldown_key() -> None:
    store = InMemoryChannelFaqRegistrationStore()
    store.save(
        ChannelFaqRegistration(
            tenant_id="tenant_1",
            channel_id="C123",
            auto_reply_mode=AutoReplyMode.ALWAYS,
            confidence_threshold=0.5,
        )
    )
    retriever = RecordingFaqRetriever(
        chunks=[
            ranked_chunk(
                document_id="doc_1",
                content="ALWAYS 모드 FAQ",
                metadata={"score": 0.95},
            )
        ]
    )
    responder = SlackChannelFaqResponder(
        registration_store=store,
        retriever=retriever,
        always_mode_cooldown_seconds=60,
        clock_millis=lambda: 1000,
    )

    first = await responder.try_auto_reply(
        tenant_id="tenant_1",
        channel_id="C123",
        user_id="U123",
        user_query="일반 질문",
        is_mention=False,
    )
    second = await responder.try_auto_reply(
        tenant_id="tenant_1",
        channel_id="C123",
        user_id="U123",
        user_query="다시 질문",
        is_mention=False,
    )

    assert first is not None
    assert second is None
    assert len(retriever.queries) == 1


async def test_faq_responder_fail_open_on_store_or_retriever_error() -> None:
    responder = SlackChannelFaqResponder(
        registration_store=RaisingRegistrationStore(),
        retriever=RaisingFaqRetriever(),
    )

    reply = await responder.try_auto_reply(
        tenant_id="tenant_1",
        channel_id="C123",
        user_id="U123",
        user_query="질문",
        is_mention=True,
    )

    assert reply is None


class RecordingFaqRetriever:
    def __init__(self, *, chunks: Sequence[RankedChunk]) -> None:
        self._chunks = list(chunks)
        self.queries: list[RetrievalQuery] = []

    async def retrieve(self, query: RetrievalQuery) -> list[RankedChunk]:
        self.queries.append(query)
        return self._chunks


class RaisingRegistrationStore:
    def get(self, *, tenant_id: str, channel_id: str) -> ChannelFaqRegistration | None:
        del tenant_id, channel_id
        raise RuntimeError("store unavailable")


class RaisingFaqRetriever:
    async def retrieve(self, query: RetrievalQuery) -> list[RankedChunk]:
        del query
        raise RuntimeError("retriever unavailable")


def ranked_chunk(
    *,
    document_id: str,
    content: str,
    metadata: dict[str, object],
) -> RankedChunk:
    score_value = metadata.get("score", 0.0)
    return RankedChunk(
        chunk=RagChunkCandidate(
            tenant_id="tenant_1",
            collection="slack-faq",
            document_id=document_id,
            chunk_index=0,
            content=content,
            content_hash=f"hash_{document_id}",
            metadata=metadata,
        ),
        score=float(score_value) if isinstance(score_value, int | float) else 0.0,
    )
