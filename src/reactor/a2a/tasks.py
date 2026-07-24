from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from reactor.a2a.urls import require_absolute_http_url
from reactor.kernel.ids import new_id
from reactor.persistence.durable_store import OutboxRequest


def dict_metadata() -> dict[str, Any]:
    return {}


A2A_TASK_METADATA_RESERVED_KEYS = frozenset(
    {
        "tenantId",
        "tenant_id",
        "peerAgentId",
        "peer_agent_id",
        "contextId",
        "context_id",
        "messageId",
        "message_id",
        "skillId",
        "skill_id",
        "userId",
        "user_id",
        "taskId",
        "task_id",
        "runId",
        "run_id",
        "threadId",
        "thread_id",
        "sessionId",
        "session_id",
        "idempotencyKey",
        "idempotency_key",
        "outboxEventId",
        "outbox_event_id",
        "eventSequence",
        "event_sequence",
        "status",
        "runtime",
        "model",
        "modelProvider",
        "model_provider",
        "systemPrompt",
        "system_prompt",
        "responseFormat",
        "response_format",
        "responseSchema",
        "response_schema",
        "fallbackModels",
        "fallback_models",
        "groups",
        "trustedUserGroups",
        "trusted_user_groups",
    }
)


def user_a2a_task_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        key: value
        for key, value in (metadata or {}).items()
        if key not in A2A_TASK_METADATA_RESERVED_KEYS
    }


class A2ATaskCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(default="local", alias="tenantId")
    peer_agent_id: str | None = Field(default=None, alias="peerAgentId")
    context_id: str = Field(alias="contextId")
    message_id: str = Field(alias="messageId")
    skill_id: str | None = Field(default=None, alias="skillId")
    user_id: str = Field(default="anonymous", alias="userId")
    input_text: str = Field(alias="inputText", min_length=1)
    push_destination: str | None = Field(default=None, alias="pushDestination")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("push_destination")
    @classmethod
    def validate_push_destination(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return require_absolute_http_url(value, field_name="pushDestination")

    def to_draft(self) -> A2ATaskDraft:
        return A2ATaskDraft.from_request(self)


class A2ATaskResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: str = Field(alias="taskId")
    tenant_id: str = Field(alias="tenantId")
    run_id: str = Field(alias="runId")
    thread_id: str = Field(alias="threadId")
    session_id: str = Field(alias="sessionId")
    context_id: str = Field(alias="contextId")
    message_id: str = Field(alias="messageId")
    status: str
    event_sequence: int = Field(alias="eventSequence")
    outbox_event_id: str | None = Field(default=None, alias="outboxEventId")


@dataclass(frozen=True)
class A2ATaskDraft:
    tenant_id: str
    peer_agent_id: str | None
    context_id: str
    message_id: str
    user_id: str
    input_text: str
    skill_id: str | None = None
    push_destination: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict_metadata)
    task_id: str = field(default_factory=lambda: new_id("a2atask"))
    run_id: str = field(default_factory=lambda: new_id("run"))
    thread_id: str = field(default_factory=lambda: new_id("thread"))
    session_id: str = field(default_factory=lambda: new_id("session"))
    idempotency_key: str | None = None

    @classmethod
    def from_request(cls, request: A2ATaskCreateRequest) -> A2ATaskDraft:
        return cls(
            tenant_id=request.tenant_id,
            peer_agent_id=request.peer_agent_id,
            context_id=request.context_id,
            message_id=request.message_id,
            skill_id=request.skill_id,
            user_id=request.user_id,
            input_text=request.input_text,
            push_destination=request.push_destination,
            metadata=user_a2a_task_metadata(request.metadata),
            idempotency_key=build_a2a_task_idempotency_key(
                request.tenant_id,
                request.context_id,
                request.message_id,
            ),
        )


@dataclass(frozen=True)
class A2ATaskRecord:
    task_id: str
    tenant_id: str
    run_id: str
    thread_id: str
    session_id: str
    context_id: str
    message_id: str
    status: str
    event_sequence: int
    outbox_event_id: str | None = None

    def to_response(self) -> A2ATaskResponse:
        return A2ATaskResponse(
            taskId=self.task_id,
            tenantId=self.tenant_id,
            runId=self.run_id,
            threadId=self.thread_id,
            sessionId=self.session_id,
            contextId=self.context_id,
            messageId=self.message_id,
            status=self.status,
            eventSequence=self.event_sequence,
            outboxEventId=self.outbox_event_id,
        )


def build_a2a_task_idempotency_key(tenant_id: str, context_id: str, message_id: str) -> str:
    return f"a2a:{tenant_id}:{context_id}:{message_id}"


def build_a2a_push_outbox_request(
    *,
    record: A2ATaskRecord,
    destination: str,
    draft: A2ATaskDraft | None = None,
    event_type: str = "a2a.task.created",
) -> OutboxRequest:
    payload: dict[str, Any] = {
        "task_id": record.task_id,
        "run_id": record.run_id,
        "thread_id": record.thread_id,
        "session_id": record.session_id,
        "context_id": record.context_id,
        "message_id": record.message_id,
        "status": record.status,
        "event_sequence": record.event_sequence,
    }
    if draft is not None:
        payload.update(
            {
                "peer_agent_id": draft.peer_agent_id,
                "skill_id": draft.skill_id,
                "user_id": draft.user_id,
                "metadata": dict(draft.metadata),
            }
        )
    return OutboxRequest(
        tenant_id=record.tenant_id,
        run_id=None,
        destination=destination,
        event_type=event_type,
        idempotency_key=f"{record.task_id}:{event_type}:{record.event_sequence}",
        payload=payload,
    )
