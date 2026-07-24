from __future__ import annotations

from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from reactor.a2a.access_policy import A2AAccessPolicyRequest, A2AAccessPolicyResponse
from reactor.a2a.agent_card import default_agent_card
from reactor.a2a.peers import A2APeerCreateRequest, A2APeerResponse
from reactor.a2a.server import a2a_server_status
from reactor.a2a.tasks import (
    A2ATaskCreateRequest,
    A2ATaskResponse,
    build_a2a_task_idempotency_key,
)
from reactor.api.auth import require_any_admin
from reactor.auth.rbac import AuthPrincipal, current_actor

router = APIRouter(tags=["a2a"])


class A2ATaskCancelRequest(BaseModel):
    reason: str | None = Field(default=None, min_length=1, max_length=1_000)


class A2ATaskResumeRequest(BaseModel):
    reason: str | None = Field(default=None, min_length=1, max_length=1_000)


@router.get("/.well-known/agent-card.json")
async def agent_card(request: Request) -> dict[str, object]:
    return default_agent_card(request.app.state.reactor.settings)


@router.get("/api/v1/a2a/diagnostics")
@router.get("/v1/a2a/diagnostics")
async def a2a_diagnostics(request: Request) -> dict[str, object]:
    server_status = a2a_server_status(request.app.state.reactor.settings)
    return {
        "protocolVersion": server_status.protocol_version,
        "sdkAvailable": server_status.sdk_available,
        "endpoint": server_status.endpoint,
        "detail": server_status.detail,
    }


@router.get("/v1/a2a/supported-interfaces")
async def a2a_supported_interfaces(request: Request) -> dict[str, object]:
    card = default_agent_card(request.app.state.reactor.settings)
    return {"supportedInterfaces": card.get("supportedInterfaces", [])}


@router.get("/v1/a2a/agents")
async def list_a2a_agents(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    tenant_id: str = Query(default="local"),
) -> dict[str, list[dict[str, object]]]:
    del tenant_id
    store = request.app.state.reactor.a2a_task_store()
    if store is None:
        return {"agents": []}
    peers = await store.list_peers(tenant_id=principal.tenant_id)
    return {"agents": [peer.to_response().model_dump(by_alias=True) for peer in peers]}


@router.post("/v1/a2a/agents", response_model=A2APeerResponse, response_model_by_alias=True)
async def register_a2a_agent(
    request: Request,
    payload: A2APeerCreateRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> A2APeerResponse:
    store = request.app.state.reactor.a2a_task_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A2A peer registry persistence is not configured",
        )
    record = await store.register_peer(replace(payload.to_draft(), tenant_id=principal.tenant_id))
    return record.to_response()


@router.get(
    "/v1/a2a/access-policy",
    response_model=A2AAccessPolicyResponse,
    response_model_by_alias=True,
)
async def get_a2a_access_policy(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    tenant_id: str = Query(default="local"),
    peer_agent_id: str | None = Query(default=None),
) -> A2AAccessPolicyResponse:
    del tenant_id
    store = request.app.state.reactor.a2a_task_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A2A access policy persistence is not configured",
        )
    policy = await store.get_access_policy(
        tenant_id=principal.tenant_id,
        peer_agent_id=peer_agent_id,
    )
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A2A access policy not found",
        )
    return policy.to_response()


@router.put(
    "/v1/a2a/access-policy",
    response_model=A2AAccessPolicyResponse,
    response_model_by_alias=True,
)
async def put_a2a_access_policy(
    request: Request,
    payload: A2AAccessPolicyRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> A2AAccessPolicyResponse:
    store = request.app.state.reactor.a2a_task_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A2A access policy persistence is not configured",
        )
    policy = await store.save_access_policy_draft(
        replace(payload.to_draft(), tenant_id=principal.tenant_id)
    )
    return policy.to_response()


@router.post("/v1/a2a/tasks", response_model=A2ATaskResponse, response_model_by_alias=True)
async def create_a2a_task(
    request: Request,
    payload: A2ATaskCreateRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> A2ATaskResponse:
    store = request.app.state.reactor.a2a_task_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A2A task persistence is not configured",
        )
    allowed = await store.is_outbound_allowed(
        tenant_id=principal.tenant_id,
        peer_agent_id=payload.peer_agent_id,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A2A outbound access is denied",
        )
    skill_allowed = await store.is_skill_allowed(
        tenant_id=principal.tenant_id,
        peer_agent_id=payload.peer_agent_id,
        skill_id=payload.skill_id,
    )
    if not skill_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A2A skill is not allowed",
        )
    draft = payload.to_draft()
    record = await store.create_task(
        replace(
            draft,
            tenant_id=principal.tenant_id,
            idempotency_key=build_a2a_task_idempotency_key(
                principal.tenant_id,
                draft.context_id,
                draft.message_id,
            ),
        )
    )
    return record.to_response()


@router.get(
    "/v1/a2a/tasks/{task_id}",
    response_model=A2ATaskResponse,
    response_model_by_alias=True,
)
async def get_a2a_task(
    request: Request,
    task_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    tenant_id: str = Query(default="local"),
) -> A2ATaskResponse:
    del tenant_id
    store = request.app.state.reactor.a2a_task_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A2A task persistence is not configured",
        )
    record = await store.get_task(tenant_id=principal.tenant_id, task_id=task_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="A2A task not found")
    return record.to_response()


@router.post(
    "/v1/a2a/tasks/{task_id}/cancel",
    response_model=A2ATaskResponse,
    response_model_by_alias=True,
)
async def cancel_a2a_task(
    request: Request,
    task_id: str,
    payload: A2ATaskCancelRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> A2ATaskResponse:
    store = request.app.state.reactor.a2a_task_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A2A task persistence is not configured",
        )
    record = await store.cancel_task(
        tenant_id=principal.tenant_id,
        task_id=task_id,
        cancelled_by=current_actor(principal),
        reason=payload.reason,
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="A2A task not found")
    return record.to_response()


@router.post(
    "/v1/a2a/tasks/{task_id}/resume",
    response_model=A2ATaskResponse,
    response_model_by_alias=True,
)
async def resume_a2a_task(
    request: Request,
    task_id: str,
    payload: A2ATaskResumeRequest,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
) -> A2ATaskResponse:
    store = request.app.state.reactor.a2a_task_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A2A task persistence is not configured",
        )
    record = await store.resume_task(
        tenant_id=principal.tenant_id,
        task_id=task_id,
        resumed_by=current_actor(principal),
        reason=payload.reason,
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="A2A task not found")
    return record.to_response()


@router.get("/v1/a2a/tasks/{task_id}/events")
async def list_a2a_task_events(
    request: Request,
    task_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_any_admin)],
    tenant_id: str = Query(default="local"),
) -> dict[str, object]:
    del tenant_id
    store = request.app.state.reactor.a2a_task_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A2A task persistence is not configured",
        )
    events = await store.list_task_events(tenant_id=principal.tenant_id, task_id=task_id)
    if events is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="A2A task not found")
    return {"events": events}
