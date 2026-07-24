from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Any, Protocol

from reactor.rag.retriever import RankedChunk, RetrievalQuery
from reactor.slack.faq import AutoReplyMode, ChannelFaqRegistration
from reactor.slack.faq_ingestion import SLACK_FAQ_COLLECTION
from reactor.slack.worker import maybe_await

DEFAULT_TOP_K = 3
DEFAULT_ALWAYS_COOLDOWN_SECONDS = 60
MAX_REPLY_CHARS = 2500


class ChannelFaqRegistrationReader(Protocol):
    def get(self, *, tenant_id: str, channel_id: str) -> Any: ...


class FaqRetriever(Protocol):
    async def retrieve(self, query: RetrievalQuery) -> list[RankedChunk]: ...


@dataclass(frozen=True)
class FaqAutoReply:
    text: str
    score: float
    threshold: float
    matched_document_ids: list[str]


@dataclass(frozen=True)
class FaqCandidate:
    document_id: str
    chunk_index: int
    score: float
    text: str
    metadata: dict[str, Any]


class SlackChannelFaqResponder:
    def __init__(
        self,
        *,
        registration_store: ChannelFaqRegistrationReader,
        retriever: FaqRetriever,
        top_k: int = DEFAULT_TOP_K,
        always_mode_cooldown_seconds: int = DEFAULT_ALWAYS_COOLDOWN_SECONDS,
        clock_millis: Any | None = None,
    ) -> None:
        self._registration_store = registration_store
        self._retriever = retriever
        self._top_k = top_k
        self._always_mode_cooldown_seconds = always_mode_cooldown_seconds
        self._clock_millis = clock_millis or (lambda: int(time() * 1000))
        self._cooldown: dict[tuple[str, str, str], int] = {}

    async def try_auto_reply(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        user_id: str,
        user_query: str,
        is_mention: bool,
    ) -> FaqAutoReply | None:
        if not user_query.strip():
            return None
        try:
            registration = await maybe_await(
                self._registration_store.get(tenant_id=tenant_id, channel_id=channel_id)
            )
        except Exception:
            return None
        if not isinstance(registration, ChannelFaqRegistration):
            return None
        if not registration.enabled:
            return None
        if not should_trigger(registration.auto_reply_mode, is_mention):
            return None
        if self._is_in_cooldown(registration, tenant_id, channel_id, user_id):
            return None

        try:
            ranked = await self._retriever.retrieve(
                RetrievalQuery(
                    tenant_id=tenant_id,
                    collection=SLACK_FAQ_COLLECTION,
                    query=user_query,
                    principal_id=user_id,
                    limit=self._top_k,
                )
            )
        except Exception:
            return None
        if not ranked:
            return None

        top = ranked[0]
        score = score_from_ranked_chunk(top)
        if score < registration.confidence_threshold:
            return None
        self._mark_cooldown(registration, tenant_id, channel_id, user_id)
        return FaqAutoReply(
            text=format_reply(top, score=score, threshold=registration.confidence_threshold),
            score=score,
            threshold=registration.confidence_threshold,
            matched_document_ids=[item.chunk.document_id for item in ranked],
        )

    async def probe_top_k(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[FaqCandidate]:
        del channel_id
        limit = max(1, min(top_k, 20))
        ranked = await self._retriever.retrieve(
            RetrievalQuery(
                tenant_id=tenant_id,
                collection=SLACK_FAQ_COLLECTION,
                query=query,
                principal_id="admin",
                limit=limit,
            )
        )
        return [faq_candidate_from_ranked_chunk(item) for item in ranked[:limit]]

    async def dry_run_auto_reply(
        self,
        *,
        tenant_id: str,
        channel_id: str,
        user_id: str,
        user_query: str,
        is_mention: bool,
    ) -> FaqAutoReply | None:
        return await self.try_auto_reply(
            tenant_id=tenant_id,
            channel_id=channel_id,
            user_id=user_id,
            user_query=user_query,
            is_mention=is_mention,
        )

    def _is_in_cooldown(
        self,
        registration: ChannelFaqRegistration,
        tenant_id: str,
        channel_id: str,
        user_id: str,
    ) -> bool:
        if (
            registration.auto_reply_mode != AutoReplyMode.ALWAYS
            or self._always_mode_cooldown_seconds <= 0
        ):
            return False
        key = (tenant_id, channel_id, user_id)
        last = self._cooldown.get(key)
        if last is None:
            return False
        elapsed = self._clock_millis() - last
        return elapsed < self._always_mode_cooldown_seconds * 1000

    def _mark_cooldown(
        self,
        registration: ChannelFaqRegistration,
        tenant_id: str,
        channel_id: str,
        user_id: str,
    ) -> None:
        if (
            registration.auto_reply_mode == AutoReplyMode.ALWAYS
            and self._always_mode_cooldown_seconds > 0
        ):
            self._cooldown[(tenant_id, channel_id, user_id)] = self._clock_millis()


def should_trigger(mode: AutoReplyMode, is_mention: bool) -> bool:
    if mode == AutoReplyMode.MENTION:
        return is_mention
    if mode == AutoReplyMode.ALWAYS:
        return True
    return False


def score_from_ranked_chunk(ranked: RankedChunk) -> float:
    distance = ranked.chunk.metadata.get("distance")
    if isinstance(distance, int | float):
        return max(0.0, min(1.0, 1.0 - (float(distance) / 2.0)))
    score = ranked.chunk.metadata.get("score")
    if isinstance(score, int | float):
        return float(score)
    return ranked.score


def faq_candidate_from_ranked_chunk(ranked: RankedChunk) -> FaqCandidate:
    chunk = ranked.chunk
    return FaqCandidate(
        document_id=chunk.document_id,
        chunk_index=chunk.chunk_index,
        score=score_from_ranked_chunk(ranked),
        text=chunk.content,
        metadata=dict(chunk.metadata),
    )


def format_reply(ranked: RankedChunk, *, score: float, threshold: float) -> str:
    chunk = ranked.chunk
    body = chunk.content.strip()[:MAX_REPLY_CHARS]
    lines = ["*FAQ 매칭*", body]
    source_user = chunk.metadata.get("user")
    source_ts = chunk.metadata.get("ts")
    source_parts: list[str] = []
    if isinstance(source_user, str) and source_user.strip():
        source_parts.append(f"게시자: <@{source_user}>")
    if isinstance(source_ts, str) and source_ts.strip():
        source_parts.append(f"ts={source_ts}")
    if source_parts:
        lines.append("_" + " · ".join(source_parts) + "_")
    lines.append(f"_신뢰도 {score:.2f} (임계값 {threshold:.2f})_")
    return "\n\n".join(lines)
