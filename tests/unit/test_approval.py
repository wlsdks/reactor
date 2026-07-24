from __future__ import annotations

import pytest

from reactor.tools.approval import (
    ApprovalDecision,
    ApprovalRequest,
    approval_status_from_decision,
)


def test_approval_request_requires_identity_fields() -> None:
    request = ApprovalRequest(
        tenant_id="tenant_1",
        run_id="",
        tool_id="tool_1",
        requested_by="user_1",
        request_payload={"input": "value"},
    )

    with pytest.raises(ValueError, match="run_id is required"):
        request.validate()


def test_approval_decision_maps_to_terminal_status() -> None:
    assert approval_status_from_decision(True) == "approved"
    assert approval_status_from_decision(False) == "rejected"


def test_rejected_approval_requires_reason() -> None:
    decision = ApprovalDecision(
        tenant_id="tenant_1",
        approval_id="approval_1",
        decided_by="admin_1",
        approved=False,
    )

    with pytest.raises(ValueError, match="require a reason"):
        decision.validate()
