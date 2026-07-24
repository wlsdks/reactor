from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

PENDING_APPROVAL_STATUS = "pending"
APPROVED_APPROVAL_STATUS = "approved"
REJECTED_APPROVAL_STATUS = "rejected"
CANCELLED_APPROVAL_STATUS = "cancelled"
TERMINAL_APPROVAL_STATUSES = {
    APPROVED_APPROVAL_STATUS,
    REJECTED_APPROVAL_STATUS,
    "expired",
    CANCELLED_APPROVAL_STATUS,
}


@dataclass(frozen=True)
class ApprovalRequest:
    tenant_id: str
    run_id: str
    tool_id: str
    requested_by: str
    request_payload: Mapping[str, Any]

    def validate(self) -> None:
        for field_name, value in (
            ("tenant_id", self.tenant_id),
            ("run_id", self.run_id),
            ("tool_id", self.tool_id),
            ("requested_by", self.requested_by),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")


@dataclass(frozen=True)
class ApprovalDecision:
    tenant_id: str
    approval_id: str
    decided_by: str
    approved: bool
    reason: str | None = None

    @property
    def status(self) -> str:
        return approval_status_from_decision(self.approved)

    def validate(self) -> None:
        for field_name, value in (
            ("tenant_id", self.tenant_id),
            ("approval_id", self.approval_id),
            ("decided_by", self.decided_by),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")
        if not self.approved and not (self.reason and self.reason.strip()):
            raise ValueError("rejected approval decisions require a reason")


def approval_status_from_decision(approved: bool) -> str:
    return APPROVED_APPROVAL_STATUS if approved else REJECTED_APPROVAL_STATUS
