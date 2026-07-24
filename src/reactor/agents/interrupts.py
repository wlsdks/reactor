from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from langgraph.types import Command

APPROVAL_RESUME_SCHEMA_VERSION = "reactor.approval_resume.v1"


@dataclass(frozen=True)
class ApprovalResumePayload:
    approval_id: str
    approved: bool
    decided_by: str
    reason: str | None

    def as_state_payload(self) -> dict[str, object]:
        return {
            "schema_version": APPROVAL_RESUME_SCHEMA_VERSION,
            "approval_id": self.approval_id,
            "approved": self.approved,
            "decided_by": self.decided_by,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ApprovalResumeDecision:
    approval_id: str
    approved: bool
    decided_by: str
    reason: str | None = None

    def validate(self) -> None:
        for field_name, value in (
            ("approval_id", self.approval_id),
            ("decided_by", self.decided_by),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")
        if not self.approved and not (self.reason and self.reason.strip()):
            raise ValueError("rejected approval decisions require a reason")

    def as_resume_payload(self) -> dict[str, object]:
        self.validate()
        return ApprovalResumePayload(
            approval_id=self.approval_id,
            approved=self.approved,
            decided_by=self.decided_by,
            reason=self.reason,
        ).as_state_payload()

    def as_langgraph_command(self) -> Command[Any]:
        return Command(resume=self.as_resume_payload())

    def as_langchain_hitl_command(self) -> Command[Any]:
        self.validate()
        decision: dict[str, object]
        if self.approved:
            decision = {"type": "approve"}
        else:
            decision = {
                "type": "reject",
                "message": self.reason,
            }
        return Command(resume={"decisions": [decision]})


def approval_resume_from_raw(raw_resume: object) -> ApprovalResumePayload:
    if not isinstance(raw_resume, dict):
        raise ValueError("approval resume payload must be an object")
    typed_resume = cast(dict[object, object], raw_resume)
    schema_version = typed_resume.get("schema_version")
    if schema_version is not None and schema_version != APPROVAL_RESUME_SCHEMA_VERSION:
        raise ValueError(f"unsupported approval_resume schema_version: {schema_version!r}")
    allowed_fields = {
        "schema_version",
        "approval_id",
        "approved",
        "decided_by",
        "reason",
    }
    unexpected_fields = set(typed_resume).difference(allowed_fields)
    if unexpected_fields:
        raise ValueError("approval_resume contains unsupported fields")
    approval_id = typed_resume.get("approval_id")
    approved = typed_resume.get("approved")
    decided_by = typed_resume.get("decided_by")
    reason = typed_resume.get("reason")
    if not isinstance(approval_id, str) or not approval_id.strip():
        raise ValueError("approval_resume.approval_id is required")
    if not isinstance(approved, bool):
        raise ValueError("approval_resume.approved must be boolean")
    if not isinstance(decided_by, str) or not decided_by.strip():
        raise ValueError("approval_resume.decided_by is required")
    if reason is not None and not isinstance(reason, str):
        raise ValueError("approval_resume.reason must be a string")
    if not approved and not (isinstance(reason, str) and reason.strip()):
        raise ValueError("rejected approval decisions require a reason")
    return ApprovalResumePayload(
        approval_id=approval_id,
        approved=approved,
        decided_by=decided_by,
        reason=reason,
    )


def approval_resume_to_state_payload(raw_resume: object) -> dict[str, object]:
    return approval_resume_from_raw(raw_resume).as_state_payload()


def validate_langchain_hitl_resume_command(command: Command[Any]) -> None:
    if command.graph is not None or command.update is not None or command.goto:
        raise ValueError(
            "invalid LangChain HITL resume command: external control fields are forbidden"
        )
    if not isinstance(command.resume, dict):
        raise ValueError("invalid LangChain HITL resume command: decisions payload is required")
    resume = cast(dict[object, object], command.resume)
    if set(resume) != {"decisions"}:
        raise ValueError("invalid LangChain HITL resume command: decisions payload is required")
    decisions = resume.get("decisions")
    if not isinstance(decisions, list):
        raise ValueError("invalid LangChain HITL resume command: exactly one decision is required")
    typed_decisions = cast(list[object], decisions)
    if len(typed_decisions) != 1:
        raise ValueError("invalid LangChain HITL resume command: exactly one decision is required")
    decision = typed_decisions[0]
    if not isinstance(decision, dict):
        raise ValueError("invalid LangChain HITL resume command: decision must be an object")
    typed_decision = cast(dict[object, object], decision)
    decision_type = typed_decision.get("type")
    if decision_type == "approve":
        if set(typed_decision) != {"type"}:
            raise ValueError("invalid LangChain HITL resume command: approve fields are invalid")
        return
    if decision_type == "reject":
        message = typed_decision.get("message")
        if (
            set(typed_decision) != {"type", "message"}
            or not isinstance(message, str)
            or not message.strip()
        ):
            raise ValueError("invalid LangChain HITL resume command: reject message is required")
        return
    raise ValueError("invalid LangChain HITL resume command: only approve or reject is supported")
