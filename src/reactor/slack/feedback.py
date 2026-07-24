from __future__ import annotations

import json
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from shlex import quote
from typing import Protocol, cast
from uuid import uuid4

from reactor.feedback.workflow import feedback_matches_eval_case_id, feedback_with_workflow_tags
from reactor.rag.ingestion_candidate_actions import RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE
from reactor.tools.approval import ApprovalDecision


class FeedbackRating(StrEnum):
    THUMBS_UP = "THUMBS_UP"
    THUMBS_DOWN = "THUMBS_DOWN"


@dataclass(frozen=True)
class Feedback:
    query: str
    response: str
    rating: FeedbackRating
    session_id: str
    user_id: str
    tenant_id: str
    feedback_id: str = field(default_factory=lambda: new_feedback_id())
    source: str = "slack_button"
    comment: str | None = None
    run_id: str | None = None
    intent: str | None = None
    domain: str | None = None
    model: str | None = None
    prompt_version: int | None = None
    tools_used: list[str] | None = None
    duration_ms: int | None = None
    tags: list[str] | None = None
    template_id: str | None = None
    review_status: str = "inbox"
    review_tags: list[str] = field(default_factory=lambda: [])
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TrackedBotResponse:
    channel_id: str
    message_ts: str
    session_id: str
    user_prompt: str
    user_id: str = ""
    response: str = ""
    run_id: str | None = None
    tags: list[str] | None = None
    template_id: str | None = None
    model: str | None = None
    prompt_version: int | None = None
    tools_used: list[str] | None = None


class FeedbackStore(Protocol):
    async def save(self, feedback: Feedback) -> Feedback: ...

    async def get(self, *, tenant_id: str, feedback_id: str) -> Feedback | None: ...

    async def list(
        self,
        *,
        tenant_id: str,
        rating: FeedbackRating | None = None,
        template_id: str | None = None,
        source: str | None = None,
        review_status: str | None = None,
        tags: list[str] | None = None,
        case_id: str | None = None,
        limit: int = 50,
    ) -> list[Feedback]: ...

    async def update_review(
        self,
        *,
        tenant_id: str,
        feedback_id: str,
        expected_version: int,
        status: str | None,
        tags: list[str] | None,
        note: str | None,
        actor: str,
    ) -> Feedback: ...

    async def unreviewed_count(self, *, tenant_id: str) -> int: ...

    async def delete(self, *, tenant_id: str, feedback_id: str) -> None: ...

    async def stats(self, *, tenant_id: str) -> dict[str, object]: ...

    async def analytics(
        self,
        *,
        tenant_id: str,
        group_by: str,
        limit: int = 20,
    ) -> dict[str, object]: ...

    async def bulk_update_review(
        self,
        *,
        tenant_id: str,
        ids: list[str],
        status: str | None,
        tags: list[str] | None,
        note: str | None,
        actor: str,
    ) -> dict[str, object]: ...


class BotResponseTracker(Protocol):
    def track(self, response: TrackedBotResponse) -> None: ...

    def lookup(self, channel_id: str, message_ts: str) -> TrackedBotResponse | None: ...


class ApprovalDecisionStore(Protocol):
    async def decide_approval(self, decision: ApprovalDecision) -> bool: ...


class RunResumeService(Protocol):
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
    ) -> object: ...


class InteractionResponseClient(Protocol):
    async def send(self, response_url: str, payload: Mapping[str, object]) -> bool: ...


class InMemoryFeedbackStore:
    def __init__(self) -> None:
        self.records: list[Feedback] = []

    async def save(self, feedback: Feedback) -> Feedback:
        existing = await self.get(tenant_id=feedback.tenant_id, feedback_id=feedback.feedback_id)
        if existing is not None:
            feedback = preserve_feedback_review_state(feedback, existing=existing)
        self.records = [
            record for record in self.records if record.feedback_id != feedback.feedback_id
        ]
        self.records.append(feedback)
        return feedback

    async def get(self, *, tenant_id: str, feedback_id: str) -> Feedback | None:
        for record in self.records:
            if record.tenant_id == tenant_id and record.feedback_id == feedback_id:
                return record
        return None

    async def list(
        self,
        *,
        tenant_id: str,
        rating: FeedbackRating | None = None,
        template_id: str | None = None,
        source: str | None = None,
        review_status: str | None = None,
        tags: list[str] | None = None,
        case_id: str | None = None,
        limit: int = 50,
    ) -> list[Feedback]:
        records = [record for record in self.records if record.tenant_id == tenant_id]
        if rating is not None:
            records = [record for record in records if record.rating == rating]
        if template_id is not None:
            records = [record for record in records if record.template_id == template_id]
        if source is not None:
            records = [record for record in records if record.source == source]
        if review_status is not None:
            records = [record for record in records if record.review_status == review_status]
        if tags:
            wanted = set(tags)
            records = [
                record
                for record in records
                if wanted.issubset(set(record.tags or []) | set(record.review_tags))
            ]
        if case_id:
            records = [
                record for record in records if feedback_matches_eval_case_id(record, case_id)
            ]
        return sorted(records, key=lambda item: item.created_at, reverse=True)[:limit]

    async def update_review(
        self,
        *,
        tenant_id: str,
        feedback_id: str,
        expected_version: int,
        status: str | None,
        tags: list[str] | None,
        note: str | None,
        actor: str,
    ) -> Feedback:
        record = await self.get(tenant_id=tenant_id, feedback_id=feedback_id)
        if record is None:
            raise KeyError(feedback_id)
        if record.version != expected_version:
            raise ValueError("version_conflict")
        if feedback_review_matches(record, status=status, tags=tags, note=note):
            return record
        updated = Feedback(
            feedback_id=record.feedback_id,
            tenant_id=record.tenant_id,
            query=record.query,
            response=record.response,
            rating=record.rating,
            source=record.source,
            comment=record.comment,
            session_id=record.session_id,
            run_id=record.run_id,
            user_id=record.user_id,
            intent=record.intent,
            domain=record.domain,
            model=record.model,
            prompt_version=record.prompt_version,
            tools_used=record.tools_used,
            duration_ms=record.duration_ms,
            tags=record.tags,
            template_id=record.template_id,
            review_status=status or record.review_status,
            review_tags=tags if tags is not None else record.review_tags,
            reviewed_by=actor,
            reviewed_at=datetime.now(UTC),
            review_note=note if note is not None else record.review_note,
            version=record.version + 1,
            created_at=record.created_at,
            updated_at=datetime.now(UTC),
        )
        self.records = [
            updated if item.feedback_id == feedback_id and item.tenant_id == tenant_id else item
            for item in self.records
        ]
        return updated

    async def unreviewed_count(self, *, tenant_id: str) -> int:
        return sum(
            1
            for record in self.records
            if record.tenant_id == tenant_id
            and record.rating == FeedbackRating.THUMBS_DOWN
            and record.review_status == "inbox"
        )

    async def delete(self, *, tenant_id: str, feedback_id: str) -> None:
        self.records = [
            record
            for record in self.records
            if not (record.tenant_id == tenant_id and record.feedback_id == feedback_id)
        ]

    async def stats(self, *, tenant_id: str) -> dict[str, object]:
        records = [record for record in self.records if record.tenant_id == tenant_id]
        positive = sum(1 for record in records if record.rating == FeedbackRating.THUMBS_UP)
        negative = sum(1 for record in records if record.rating == FeedbackRating.THUMBS_DOWN)
        inbox = sum(1 for record in records if record.review_status == "inbox")
        done = sum(1 for record in records if record.review_status == "done")
        with_comment = sum(1 for record in records if record.comment is not None)
        total = len(records)
        return feedback_stats_payload(
            total=total,
            positive=positive,
            negative=negative,
            with_comment=with_comment,
            inbox=inbox,
            done=done,
        )

    async def analytics(
        self,
        *,
        tenant_id: str,
        group_by: str,
        limit: int = 20,
    ) -> dict[str, object]:
        records = [record for record in self.records if record.tenant_id == tenant_id]
        return feedback_analytics_payload(records, group_by=group_by, limit=limit)

    async def bulk_update_review(
        self,
        *,
        tenant_id: str,
        ids: list[str],
        status: str | None,
        tags: list[str] | None,
        note: str | None,
        actor: str,
    ) -> dict[str, object]:
        updated: list[str] = []
        already_done: list[str] = []
        failed: list[dict[str, str]] = []
        for feedback_id in ids:
            record = await self.get(tenant_id=tenant_id, feedback_id=feedback_id)
            if record is None:
                failed.append({"id": feedback_id, "reason": "not_found"})
                continue
            if feedback_review_matches(record, status=status, tags=tags, note=note):
                already_done.append(feedback_id)
                continue
            await self.update_review(
                tenant_id=tenant_id,
                feedback_id=feedback_id,
                expected_version=record.version,
                status=status,
                tags=tags,
                note=note,
                actor=actor,
            )
            updated.append(feedback_id)
        result: dict[str, object] = {"updated": updated, "failed": failed}
        if already_done:
            result["alreadyDone"] = already_done
        return result


def new_feedback_id() -> str:
    return str(uuid4())


def feedback_review_matches(
    feedback: Feedback,
    *,
    status: str | None,
    tags: list[str] | None,
    note: str | None,
) -> bool:
    if status is not None and feedback.review_status != status:
        return False
    if tags is not None and not normalized_review_tags(tags).issubset(
        normalized_review_tags(feedback.review_tags)
    ):
        return False
    if note is not None and feedback.review_note != note:
        return False
    return status is not None or tags is not None or note is not None


def normalized_review_tags(tags: list[str]) -> set[str]:
    return {tag.strip() for tag in tags if tag.strip()}


def feedback_stats_payload(
    *,
    total: int,
    positive: int,
    negative: int,
    with_comment: int,
    inbox: int,
    done: int,
) -> dict[str, object]:
    return {
        "total": total,
        "positive": positive,
        "negative": negative,
        "positiveRate": positive / total if total else 0.0,
        "commentRate": with_comment / total if total else 0.0,
        "inboxCount": inbox,
        "doneCount": done,
    }


FEEDBACK_ANALYTICS_GROUPS = frozenset({"model", "template", "domain", "intent"})


def feedback_analytics_payload(
    records: list[Feedback],
    *,
    group_by: str,
    limit: int = 20,
) -> dict[str, object]:
    normalized_group = normalize_analytics_group(group_by)
    capped_limit = max(1, min(limit, 50))
    buckets: dict[str, list[Feedback]] = {}
    for record in records:
        key = feedback_analytics_key(record, normalized_group)
        if key is None:
            continue
        buckets.setdefault(key, []).append(record)

    items = [
        feedback_analytics_item(key=key, records=bucket)
        for key, bucket in buckets.items()
        if bucket
    ]
    items.sort(key=feedback_analytics_sort_key)
    return {"groupBy": normalized_group, "items": items[:capped_limit]}


def feedback_analytics_sort_key(item: Mapping[str, object]) -> tuple[float, int, int, str]:
    negative_rate = item.get("negativeRate")
    negative = item.get("negative")
    total = item.get("total")
    key = item.get("key")
    return (
        -float(negative_rate) if isinstance(negative_rate, int | float) else 0.0,
        -int(negative) if isinstance(negative, int) else 0,
        -int(total) if isinstance(total, int) else 0,
        str(key or ""),
    )


def normalize_analytics_group(group_by: str) -> str:
    normalized = group_by.strip().lower()
    aliases = {
        "template_id": "template",
        "templateid": "template",
        "prompt_template": "template",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in FEEDBACK_ANALYTICS_GROUPS:
        allowed = ", ".join(sorted(FEEDBACK_ANALYTICS_GROUPS))
        raise ValueError(f"Invalid analytics groupBy '{group_by}'. Must be one of: {allowed}")
    return normalized


def feedback_analytics_key(record: Feedback, group_by: str) -> str | None:
    if group_by == "model":
        return non_blank(record.model)
    if group_by == "template":
        return non_blank(record.template_id)
    if group_by == "domain":
        return non_blank(record.domain)
    if group_by == "intent":
        return non_blank(record.intent)
    raise ValueError(f"Unsupported analytics group: {group_by}")


def feedback_analytics_item(*, key: str, records: list[Feedback]) -> dict[str, object]:
    total = len(records)
    positive = sum(1 for record in records if record.rating == FeedbackRating.THUMBS_UP)
    negative = sum(1 for record in records if record.rating == FeedbackRating.THUMBS_DOWN)
    with_comment = sum(1 for record in records if record.comment is not None)
    return {
        "key": key,
        "total": total,
        "positive": positive,
        "negative": negative,
        "negativeRate": negative / total if total else 0.0,
        "commentRate": with_comment / total if total else 0.0,
    }


def non_blank(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class InMemoryBotResponseTracker:
    def __init__(self, *, max_entries: int = 1000) -> None:
        self._max_entries = max(1, max_entries)
        self._responses: OrderedDict[tuple[str, str], TrackedBotResponse] = OrderedDict()

    def track(self, response: TrackedBotResponse) -> None:
        key = (response.channel_id, response.message_ts)
        self._responses[key] = response
        self._responses.move_to_end(key)
        while len(self._responses) > self._max_entries:
            self._responses.popitem(last=False)

    def lookup(self, channel_id: str, message_ts: str) -> TrackedBotResponse | None:
        return self._responses.get((channel_id, message_ts))


def preserve_feedback_review_state(feedback: Feedback, *, existing: Feedback) -> Feedback:
    return replace(
        feedback,
        review_status=existing.review_status,
        review_tags=existing.review_tags,
        reviewed_by=existing.reviewed_by,
        reviewed_at=existing.reviewed_at,
        review_note=existing.review_note,
        version=existing.version,
        created_at=existing.created_at,
    )


@dataclass(frozen=True)
class SlackInteractionPayload:
    type: str
    action_id: str
    value: str | None
    user_id: str
    channel_id: str | None
    message_ts: str | None
    trigger_id: str | None
    response_url: str | None
    private_metadata: str | None = None

    @classmethod
    def from_slack_payload(cls, payload: Mapping[str, object]) -> SlackInteractionPayload:
        payload_type = _required_str(payload, "type")
        action = _first_action(payload)
        return cls(
            type=payload_type,
            action_id=_required_str(action, "action_id"),
            value=_optional_str(action, "value"),
            user_id=_required_nested_str(payload, "user", "id"),
            channel_id=_optional_nested_str(payload, "channel", "id"),
            message_ts=_optional_nested_str(payload, "message", "ts"),
            trigger_id=_optional_str(payload, "trigger_id"),
            response_url=_optional_str(payload, "response_url"),
        )

    @classmethod
    def from_outbox_payload(
        cls,
        payload: Mapping[str, object],
    ) -> SlackInteractionPayload:
        interaction = payload.get("interaction")
        if not isinstance(interaction, Mapping):
            raise ValueError("Slack interaction payload is missing interaction object")
        return cls.from_slack_payload(cast(Mapping[str, object], interaction))


class FeedbackButtonHandler:
    ACTION_ID_UP = "feedback.up"
    ACTION_ID_DOWN = "feedback.down"
    ACK_SUCCESS_UP = "🙏 피드백 감사합니다! 더 도움이 되도록 계속 개선할게요 ✨"
    ACK_SUCCESS_DOWN = "🙇 솔직한 피드백 감사합니다. 다음엔 더 정확히 답변드릴게요 💪"
    ACK_FALLBACK = "🙏 피드백을 받았으나 저장 중 오류가 발생했습니다."
    ACK_EXPIRED = "이 메시지는 만료되었거나 추적되지 않았습니다."

    def __init__(
        self,
        *,
        feedback_store: FeedbackStore,
        bot_response_tracker: BotResponseTracker | None,
        messaging_client: object,
    ) -> None:
        self._feedback_store = feedback_store
        self._bot_response_tracker = bot_response_tracker
        self._messaging_client = messaging_client

    async def handle_outbox_payload(
        self,
        payload: Mapping[str, object],
        *,
        tenant_id: str,
    ) -> object:
        return await self.handle(
            SlackInteractionPayload.from_outbox_payload(payload),
            tenant_id=tenant_id,
        )

    async def handle(self, payload: SlackInteractionPayload, *, tenant_id: str) -> bool:
        rating = feedback_rating_from_action_id(payload.action_id)
        if rating is None:
            return True
        if not payload.channel_id or not payload.message_ts:
            return True
        tracked = (
            self._bot_response_tracker.lookup(payload.channel_id, payload.message_ts)
            if self._bot_response_tracker is not None
            else None
        )
        if tracked is None:
            await self._ack_ephemeral(payload, self.ACK_EXPIRED)
            return True
        saved = await self._save_feedback(
            feedback_with_workflow_tags(
                Feedback(
                    query=tracked.user_prompt,
                    response=tracked.response,
                    rating=rating,
                    session_id=tracked.session_id,
                    user_id=tracked.user_id or payload.user_id,
                    tenant_id=tenant_id,
                    run_id=tracked.run_id,
                    tags=tracked.tags,
                    template_id=tracked.template_id,
                    model=tracked.model,
                    prompt_version=tracked.prompt_version,
                    tools_used=tracked.tools_used,
                )
            )
        )
        await self._ack_in_thread(
            payload.channel_id,
            payload.message_ts,
            ack_text(saved=saved, rating=rating),
        )
        return True

    async def _save_feedback(self, feedback: Feedback) -> Feedback | None:
        try:
            return await self._feedback_store.save(feedback)
        except Exception:
            return None

    async def _ack_in_thread(self, channel_id: str, message_ts: str, text: str) -> None:
        sender = getattr(self._messaging_client, "send_message", None)
        if sender is None:
            return
        try:
            await sender(channel_id=channel_id, text=text, thread_ts=message_ts)
        except Exception:
            return

    async def _ack_ephemeral(self, payload: SlackInteractionPayload, text: str) -> None:
        sender = getattr(self._messaging_client, "send_response_url", None)
        if sender is None or payload.response_url is None:
            return
        try:
            await sender(payload.response_url, text, response_type="ephemeral")
        except Exception:
            return


@dataclass(frozen=True)
class SlackApprovalAction:
    approval_id: str
    run_id: str
    thread_id: str
    checkpoint_ns: str
    approved: bool
    channel_id: str | None = None
    thread_ts: str | None = None
    reason: str | None = None


class SlackApprovalButtonHandler:
    ACTION_ID_APPROVE = "approval.approve"
    ACTION_ID_REJECT = "approval.reject"
    ACK_APPROVED = "Approval approved"
    ACK_REJECTED = "Approval rejected"
    ACK_INVALID = "Approval request is invalid and was not executed."
    ACK_EXPIRED = "Approval request is expired or no longer pending."

    def __init__(
        self,
        *,
        approval_store: ApprovalDecisionStore,
        run_service: RunResumeService,
        messaging_client: object,
        response_url_client: InteractionResponseClient | None = None,
    ) -> None:
        self._approval_store = approval_store
        self._run_service = run_service
        self._messaging_client = messaging_client
        self._response_url_client = response_url_client

    async def handle_outbox_payload(
        self,
        payload: Mapping[str, object],
        *,
        tenant_id: str,
    ) -> object:
        return await self.handle(
            SlackInteractionPayload.from_outbox_payload(payload),
            tenant_id=tenant_id,
        )

    async def handle(self, payload: SlackInteractionPayload, *, tenant_id: str) -> bool:
        if not slack_approval_action_id(payload.action_id):
            return False
        try:
            action = slack_approval_action_from_payload(payload)
        except ValueError:
            await self._replace_original_approval_message(payload, self.ACK_INVALID)
            await self._ack(payload, self.ACK_INVALID)
            return True
        if action is None:
            return False
        if slack_approval_channel_mismatch(payload, action):
            await self._replace_original_approval_message(payload, self.ACK_INVALID)
            await self._ack(payload, self.ACK_INVALID)
            return True
        decided = await self._approval_store.decide_approval(
            ApprovalDecision(
                tenant_id=tenant_id,
                approval_id=action.approval_id,
                decided_by=payload.user_id,
                approved=action.approved,
                reason=action.reason,
            )
        )
        if not decided:
            await self._replace_original_approval_message(payload, self.ACK_EXPIRED)
            await self._ack(payload, self.ACK_EXPIRED)
            return True
        result = await self._run_service.resume_run(
            run_id=action.run_id,
            tenant_id=tenant_id,
            user_id=payload.user_id,
            thread_id=action.thread_id,
            checkpoint_ns=action.checkpoint_ns,
            approval_id=action.approval_id,
            approved=action.approved,
            reason=action.reason,
        )
        status = self.ACK_APPROVED if action.approved else self.ACK_REJECTED
        ack_text_value = f"{status} by <@{payload.user_id}>."
        await self._replace_original_approval_message(payload, ack_text_value)
        await self._ack(payload, slack_approval_resume_ack(ack_text_value, run_id=action.run_id))
        if action.approved:
            await self._send_resume_response(payload, result)
        return True

    async def _ack(self, payload: SlackInteractionPayload, text: str) -> None:
        await self._send_interaction_message(payload, text)

    async def _send_resume_response(
        self,
        payload: SlackInteractionPayload,
        result: object,
    ) -> None:
        response = getattr(result, "response", None)
        if not isinstance(response, str) or not response.strip():
            return
        await self._send_interaction_message(payload, response.strip())

    async def _send_interaction_message(self, payload: SlackInteractionPayload, text: str) -> None:
        try:
            action = slack_approval_action_from_payload(payload)
        except ValueError:
            action = None
        if action is not None and slack_approval_channel_mismatch(payload, action):
            action = None
        channel_id = (
            action.channel_id if action is not None and action.channel_id else payload.channel_id
        )
        thread_ts = (
            action.thread_ts if action is not None and action.thread_ts else payload.message_ts
        )
        sender = getattr(self._messaging_client, "send_message", None)
        if sender is not None and channel_id is not None:
            try:
                await sender(
                    channel_id=channel_id,
                    text=text,
                    thread_ts=thread_ts,
                )
                return
            except Exception:
                sender = None
        response_sender = getattr(self._messaging_client, "send_response_url", None)
        if response_sender is None or payload.response_url is None:
            return
        try:
            await response_sender(payload.response_url, text, response_type="ephemeral")
        except Exception:
            return

    async def _replace_original_approval_message(
        self,
        payload: SlackInteractionPayload,
        text: str,
    ) -> None:
        if self._response_url_client is None or payload.response_url is None:
            return
        try:
            await self._response_url_client.send(
                payload.response_url,
                {
                    "replace_original": True,
                    "text": text,
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": text,
                            },
                        }
                    ],
                },
            )
        except Exception:
            return


class SlackInteractionHandler:
    def __init__(
        self,
        *,
        feedback_handler: FeedbackButtonHandler,
        approval_handler: SlackApprovalButtonHandler | None = None,
    ) -> None:
        self._feedback_handler = feedback_handler
        self._approval_handler = approval_handler

    async def handle_outbox_payload(
        self,
        payload: Mapping[str, object],
        *,
        tenant_id: str,
    ) -> object:
        interaction = SlackInteractionPayload.from_outbox_payload(payload)
        if feedback_rating_from_action_id(interaction.action_id) is not None:
            return await self._feedback_handler.handle(interaction, tenant_id=tenant_id)
        if self._approval_handler is not None and slack_approval_action_id(interaction.action_id):
            return await self._approval_handler.handle(interaction, tenant_id=tenant_id)
        return True


def feedback_rating_from_action_id(action_id: str) -> FeedbackRating | None:
    if action_id == FeedbackButtonHandler.ACTION_ID_UP:
        return FeedbackRating.THUMBS_UP
    if action_id == FeedbackButtonHandler.ACTION_ID_DOWN:
        return FeedbackRating.THUMBS_DOWN
    return None


def ack_text(*, saved: Feedback | None, rating: FeedbackRating) -> str:
    if saved is None:
        return FeedbackButtonHandler.ACK_FALLBACK
    if rating == FeedbackRating.THUMBS_UP:
        return FeedbackButtonHandler.ACK_SUCCESS_UP
    review_tag_args = slack_feedback_review_tag_args(saved)
    run_action_text = slack_feedback_run_action_text(saved)
    return (
        f"{FeedbackButtonHandler.ACK_SUCCESS_DOWN}\n\n"
        f"_Review: `reactor-admin feedback --feedback-id {quote(saved.feedback_id)} "
        "--output table`_\n"
        f"{run_action_text}"
        f"_Close: `reactor-admin feedback-review {quote(saved.feedback_id)} "
        f"--if-match {saved.version} --status done "
        f"--tag promoted --tag langsmith {review_tag_args} "
        f"--note {quote(RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE)} "
        "--output table`_"
    )


def slack_feedback_run_action_text(saved: Feedback) -> str:
    run_id = (saved.run_id or "").strip()
    if not run_id:
        return ""
    quoted_run_id = quote(run_id)
    return (
        f"_Diagnose: `reactor-runs diagnose {quoted_run_id} --output table`_\n"
        f"_Replay events: `reactor-runs replay {quoted_run_id} --output table`_\n"
        f"_State history: `reactor-admin state-history {quoted_run_id} --output table`_\n"
    )


def slack_feedback_review_tag_args(saved: Feedback) -> str:
    tags: list[str] = []
    for tag in ["slack", *(saved.tags or [])]:
        if tag not in tags:
            tags.append(tag)
    return " ".join(f"--tag {quote(tag)}" for tag in tags if tag.strip())


def slack_approval_resume_ack(message: str, *, run_id: str) -> str:
    if not run_id:
        return message
    quoted_run_id = quote(run_id)
    return (
        f"{message}\n\n"
        f"_Diagnose: `reactor-runs diagnose {quoted_run_id} --output table`_\n"
        f"_State history: `reactor-admin state-history {quoted_run_id} --output table`_\n"
        f"_Replay events: `reactor-runs replay {quoted_run_id} --output table`_\n"
        "_Feedback review: `reactor-admin feedback --rating thumbs_down "
        "--review-status inbox --limit 10 --output table`_"
    )


def slack_approval_action_id(action_id: str) -> bool:
    return action_id in {
        SlackApprovalButtonHandler.ACTION_ID_APPROVE,
        SlackApprovalButtonHandler.ACTION_ID_REJECT,
    }


def slack_approval_channel_mismatch(
    payload: SlackInteractionPayload,
    action: SlackApprovalAction,
) -> bool:
    return (
        action.channel_id is not None
        and payload.channel_id is not None
        and action.channel_id != payload.channel_id
    )


def slack_approval_action_from_payload(
    payload: SlackInteractionPayload,
) -> SlackApprovalAction | None:
    if not slack_approval_action_id(payload.action_id):
        return None
    value = parse_action_value(payload.value)
    approved = payload.action_id == SlackApprovalButtonHandler.ACTION_ID_APPROVE
    reason = optional_value(value, "reason")
    if not approved and reason is None:
        reason = "Rejected from Slack"
    return SlackApprovalAction(
        approval_id=required_value(value, "approvalId"),
        run_id=required_value(value, "runId"),
        thread_id=required_value(value, "threadId"),
        checkpoint_ns=optional_value(value, "checkpointNs") or "reactor",
        approved=approved,
        channel_id=optional_value(value, "channelId"),
        thread_ts=optional_value(value, "threadTs"),
        reason=reason,
    )


def parse_action_value(value: str | None) -> Mapping[str, object]:
    if value is None:
        raise ValueError("Slack approval action value is required")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("Slack approval action value must be JSON") from error
    if not isinstance(parsed, Mapping):
        raise ValueError("Slack approval action value must be an object")
    return cast(Mapping[str, object], parsed)


def required_value(payload: Mapping[str, object], key: str) -> str:
    value = optional_value(payload, key)
    if value is None:
        raise ValueError(f"Slack approval action value is missing {key}")
    return value


def optional_value(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _first_action(payload: Mapping[str, object]) -> Mapping[str, object]:
    actions = payload.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("Slack interaction payload is missing actions")
    first = cast(list[object], actions)[0]
    if not isinstance(first, Mapping):
        raise ValueError("Slack interaction action must be an object")
    return cast(Mapping[str, object], first)


def _required_str(source: Mapping[str, object], key: str) -> str:
    value = source.get(key)
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError(f"Slack interaction field is required: {key}")


def _optional_str(source: Mapping[str, object], key: str) -> str | None:
    value = source.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _required_nested_str(source: Mapping[str, object], parent: str, key: str) -> str:
    value = _optional_nested_str(source, parent, key)
    if value is None:
        raise ValueError(f"Slack interaction field is required: {parent}.{key}")
    return value


def _optional_nested_str(source: Mapping[str, object], parent: str, key: str) -> str | None:
    nested = source.get(parent)
    if not isinstance(nested, Mapping):
        return None
    return _optional_str(cast(Mapping[str, object], nested), key)
