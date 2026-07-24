from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, StringConstraints

from reactor.agents.runner import public_approval_request
from reactor.api.auth import require_any_admin
from reactor.api.routers.runs import require_run_access
from reactor.auth.rbac import AuthPrincipal, current_actor
from reactor.core.container import AppContainer
from reactor.persistence.approval_store import ApprovalRecord
from reactor.persistence.run_store import SessionStore
from reactor.runs.lifecycle import RunLifecyclePublisher, publish_run_lifecycle_event
from reactor.tools.approval import ApprovalDecision, ApprovalRequest

router = APIRouter(tags=["approvals"])


class CreateApprovalRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=64)
    tool_id: str = Field(min_length=1, max_length=64)
    request_payload: dict[str, object] = Field(default_factory=dict)


class ApprovalDecisionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2_000)


class ApprovalRejectionRequest(BaseModel):
    reason: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000),
    ]


class ApprovalResponse(BaseModel):
    approval_id: str
    status: str


class ApprovalListItem(BaseModel):
    approval_id: str
    run_id: str
    tool_id: str
    status: str
    requested_by: str
    request_payload: dict[str, object]
    requested_at: str
    decided_at: str | None
    decided_by: str | None
    decision_reason: str | None


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def require_approval_store(request: Request):
    approval_store = get_container(request).approval_store()
    if approval_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="approval persistence is not configured",
        )
    return approval_store


def require_run_store(request: Request) -> SessionStore:
    run_store = get_container(request).run_store()
    if run_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="run persistence is not configured",
        )
    return cast(SessionStore, run_store)


def get_run_lifecycle_publisher(container: object) -> RunLifecyclePublisher | None:
    accessor = getattr(container, "run_lifecycle_publisher", None)
    if accessor is None:
        return None
    return cast(RunLifecyclePublisher | None, accessor())


@router.post("/api/approvals", response_model=ApprovalResponse, status_code=status.HTTP_201_CREATED)
@router.post("/v1/approvals", response_model=ApprovalResponse, status_code=status.HTTP_201_CREATED)
async def create_approval(
    request: Request,
    body: CreateApprovalRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> ApprovalResponse:
    container = get_container(request)
    approval_store = require_approval_store(request)
    run_store = require_run_store(request)
    await require_run_access(run_store, run_id=body.run_id, principal=principal)
    requested_by = current_actor(principal)
    approval_id = await approval_store.request_approval(
        ApprovalRequest(
            tenant_id=principal.tenant_id,
            run_id=body.run_id,
            tool_id=body.tool_id,
            requested_by=requested_by,
            request_payload=body.request_payload,
        )
    )
    await publish_run_lifecycle_event(
        get_run_lifecycle_publisher(container),
        {
            "event_type": "approval.requested",
            "approval_id": approval_id,
            "tenant_id": principal.tenant_id,
            "run_id": body.run_id,
            "tool_id": body.tool_id,
            "requested_by": requested_by,
            "status": "pending",
        },
    )
    return ApprovalResponse(approval_id=approval_id, status="pending")


@router.get("/api/approvals", response_model=list[ApprovalListItem])
@router.get("/v1/approvals", response_model=list[ApprovalListItem])
async def list_pending_approvals(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[ApprovalListItem]:
    approval_store = require_approval_store(request)
    list_approvals = getattr(approval_store, "list_approvals", None)
    if list_approvals is None:
        records = await approval_store.list_pending(principal.tenant_id, limit)
    else:
        records = await list_approvals(principal.tenant_id, limit, status_filter)
    return [
        ApprovalListItem(
            approval_id=record.id,
            run_id=record.run_id,
            tool_id=record.tool_id,
            status=record.status,
            requested_by=record.requested_by,
            request_payload=public_approval_request(record.request_payload),
            requested_at=record.created_at.isoformat() if record.created_at is not None else "",
            decided_at=record.decided_at.isoformat() if record.decided_at is not None else None,
            decided_by=record.decided_by,
            decision_reason=record.decision_reason,
        )
        for record in records
    ]


@router.post("/api/approvals/{approval_id}/approve", response_model=ApprovalResponse)
@router.post("/v1/approvals/{approval_id}/approve", response_model=ApprovalResponse)
async def approve_approval(
    request: Request,
    approval_id: str,
    body: ApprovalDecisionRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> ApprovalResponse:
    container = get_container(request)
    approval_store = require_approval_store(request)
    decided_by = current_actor(principal)
    updated = await approval_store.decide_approval(
        ApprovalDecision(
            tenant_id=principal.tenant_id,
            approval_id=approval_id,
            decided_by=decided_by,
            approved=True,
            reason=body.reason,
        )
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="approval is not pending or does not exist",
        )
    approval = await approval_record_after_decision(
        approval_store,
        tenant_id=principal.tenant_id,
        approval_id=approval_id,
    )
    await publish_run_lifecycle_event(
        get_run_lifecycle_publisher(container),
        approval_decided_event(
            approval=approval,
            tenant_id=principal.tenant_id,
            approval_id=approval_id,
            decided_by=decided_by,
            approved=True,
            status_value="approved",
            reason=body.reason,
        ),
    )
    return ApprovalResponse(approval_id=approval_id, status="approved")


@router.post("/api/approvals/{approval_id}/reject", response_model=ApprovalResponse)
@router.post("/v1/approvals/{approval_id}/reject", response_model=ApprovalResponse)
async def reject_approval(
    request: Request,
    approval_id: str,
    body: ApprovalRejectionRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> ApprovalResponse:
    container = get_container(request)
    approval_store = require_approval_store(request)
    decided_by = current_actor(principal)
    updated = await approval_store.decide_approval(
        ApprovalDecision(
            tenant_id=principal.tenant_id,
            approval_id=approval_id,
            decided_by=decided_by,
            approved=False,
            reason=body.reason,
        )
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="approval is not pending or does not exist",
        )
    approval = await approval_record_after_decision(
        approval_store,
        tenant_id=principal.tenant_id,
        approval_id=approval_id,
    )
    await publish_run_lifecycle_event(
        get_run_lifecycle_publisher(container),
        approval_decided_event(
            approval=approval,
            tenant_id=principal.tenant_id,
            approval_id=approval_id,
            decided_by=decided_by,
            approved=False,
            status_value="rejected",
            reason=body.reason,
        ),
    )
    return ApprovalResponse(approval_id=approval_id, status="rejected")


async def approval_record_after_decision(
    approval_store: object,
    *,
    tenant_id: str,
    approval_id: str,
) -> ApprovalRecord | None:
    finder = getattr(approval_store, "find_approval", None)
    if finder is None:
        return None
    return cast(
        ApprovalRecord | None,
        await finder(tenant_id=tenant_id, approval_id=approval_id),
    )


def approval_decided_event(
    *,
    approval: ApprovalRecord | None,
    tenant_id: str,
    approval_id: str,
    decided_by: str,
    approved: bool,
    status_value: str,
    reason: str | None,
) -> dict[str, object]:
    event: dict[str, object] = {
        "event_type": "approval.decided",
        "approval_id": approval_id,
        "tenant_id": tenant_id,
        "decided_by": decided_by,
        "approved": approved,
        "status": status_value,
        "reason": reason,
    }
    if approval is not None:
        event["run_id"] = approval.run_id
        event["tool_id"] = approval.tool_id
    return event
