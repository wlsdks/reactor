from __future__ import annotations

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from reactor.agents.runner import public_run_metadata
from reactor.api.auth import principal_from_headers
from reactor.auth.rbac import AuthPrincipal
from reactor.core.container import AppContainer
from reactor.persistence.run_store import SessionRunRecord, SessionStore

router = APIRouter(tags=["sessions"])


class SessionResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    thread_id: str = Field(alias="threadId")
    status: str
    preview: str
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class SessionDetailResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    thread_id: str = Field(alias="threadId")
    status: str
    messages: list[dict[str, object]]
    metadata: dict[str, object]


class PaginatedSessionsResponse(BaseModel):
    items: list[SessionResponse]
    total: int
    offset: int
    limit: int


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


def require_authenticated(principal: AuthPrincipal) -> AuthPrincipal:
    if principal.user_id == "anonymous":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authenticated user context",
        )
    return principal


def run_store_or_503(container: AppContainer) -> SessionStore:
    run_store = container.run_store()
    if run_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="session persistence is not configured",
        )
    return run_store


@router.get(
    "/api/sessions",
    response_model=PaginatedSessionsResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/sessions",
    response_model=PaginatedSessionsResponse,
    response_model_by_alias=True,
)
async def list_sessions(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> PaginatedSessionsResponse:
    principal = require_authenticated(principal)
    result = await run_store_or_503(get_container(request)).list_sessions(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedSessionsResponse(
        items=[session_response(item) for item in result.items],
        total=result.total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/api/sessions/{session_id}",
    response_model=SessionDetailResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/sessions/{session_id}",
    response_model=SessionDetailResponse,
    response_model_by_alias=True,
)
async def get_session(
    request: Request,
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> SessionDetailResponse:
    session = await load_owned_session(request, session_id, require_authenticated(principal))
    return session_detail_response(session)


@router.get("/api/sessions/{session_id}/export", response_model=None)
@router.get("/v1/sessions/{session_id}/export", response_model=None)
async def export_session(
    request: Request,
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
    format: Literal["json", "markdown"] = "json",
) -> Response | dict[str, object]:
    session = await load_owned_session(request, session_id, require_authenticated(principal))
    if format == "markdown":
        body = session_markdown(session)
        return Response(
            content=body,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_filename(session_id)}.md"'
            },
        )
    return {
        "sessionId": session.run_id,
        "exportedAt": session.updated_at,
        "messages": session_messages(session),
    }


@router.delete("/api/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/v1/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    request: Request,
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> Response:
    await load_owned_session(request, session_id, require_authenticated(principal))
    await run_store_or_503(get_container(request)).delete_session(run_id=session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def load_owned_session(
    request: Request,
    session_id: str,
    principal: AuthPrincipal,
) -> SessionRunRecord:
    session = await run_store_or_503(get_container(request)).find_session(run_id=session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to session"
        )
    if session.user_id != principal.user_id and not principal.is_any_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to session"
        )
    return session


def session_response(session: SessionRunRecord) -> SessionResponse:
    return SessionResponse(
        sessionId=session.run_id,
        threadId=session.thread_id,
        status=session.status,
        preview=session.input_text[:160],
        createdAt=session.created_at,
        updatedAt=session.updated_at,
    )


def session_detail_response(session: SessionRunRecord) -> SessionDetailResponse:
    return SessionDetailResponse(
        sessionId=session.run_id,
        threadId=session.thread_id,
        status=session.status,
        messages=session_messages(session),
        metadata=public_run_metadata(session.metadata),
    )


def session_messages(session: SessionRunRecord) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = [
        {"role": "user", "content": session.input_text, "timestamp": session.created_at}
    ]
    if session.response_text:
        messages.append(
            {"role": "assistant", "content": session.response_text, "timestamp": session.updated_at}
        )
    return messages


def session_markdown(session: SessionRunRecord) -> str:
    lines = [f"# Conversation: {session.run_id}", ""]
    for message in session_messages(session):
        lines.extend([f"## {message['role']}", "", str(message["content"]), ""])
    return "\n".join(lines)


def safe_filename(name: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in name)[:100]
