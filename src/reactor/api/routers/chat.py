from __future__ import annotations

import json
from collections.abc import Mapping
from time import perf_counter
from typing import Annotated, Any, cast
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from sse_starlette.sse import EventSourceResponse

from reactor.agents.runner import PUBLIC_RUN_METADATA_KEYS, public_run_metadata
from reactor.api.auth import principal_from_headers
from reactor.api.schemas.chat import ChatRequest, ChatResponse, ChatTokenUsage, MediaUrlRequest
from reactor.auth.rbac import AuthPrincipal
from reactor.core.container import AppContainer
from reactor.core.settings import Settings
from reactor.observability.metrics import RUNS_CREATED
from reactor.runs.service import RunService

router = APIRouter(tags=["chat"])
UPLOAD_READ_CHUNK_SIZE = 1024 * 1024
CHAT_METADATA_RESERVED_KEYS = {
    "channel",
    "tenantId",
    "userId",
    "runId",
    "threadId",
    "source",
    "checkpointId",
    "checkpoint_id",
    "checkpointNs",
    "checkpoint_ns",
    "forkedFromRunId",
    "forkedFromThreadId",
    "forkedFromCheckpointNs",
    "forkedFromCheckpointId",
    "forkTargetThreadId",
    "forkTargetCheckpointNs",
    "runtime",
    "graphProfile",
    "model",
    "modelProvider",
    "systemPrompt",
    "responseFormat",
    "responseSchema",
    "contextManifest",
    "context_manifest",
    "fallbackModels",
    "middlewarePolicy",
    "personaId",
    "promptTemplateId",
    "groups",
    "trustedUserGroups",
    "mediaUrls",
    *PUBLIC_RUN_METADATA_KEYS,
}


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


@router.post("/api/chat", response_model=ChatResponse, response_model_by_alias=True)
@router.post("/v1/chat", response_model=ChatResponse, response_model_by_alias=True)
async def chat(
    request: Request,
    body: ChatRequest,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> ChatResponse:
    started = perf_counter()
    validate_media_urls(body.media_urls or [])
    result = await run_chat_request(request, body, principal)
    RUNS_CREATED.labels(status=result.status).inc()
    result_metadata = public_run_metadata(result.response_metadata)
    grounded, verified_source_count, block_reason = chat_grounding_summary(result_metadata)
    return ChatResponse(
        content=result.response,
        success=result.status == "completed",
        model=result.model,
        grounded=grounded,
        verifiedSourceCount=verified_source_count,
        blockReason=block_reason,
        durationMs=int((perf_counter() - started) * 1000),
        metadata={
            **user_chat_metadata(body.metadata),
            **result_metadata,
            "channel": "web",
            "runId": result.run_id,
            "tenantId": result.tenant_id,
            "userId": result.user_id,
            "threadId": result.thread_id,
            "checkpointNs": result.checkpoint_ns,
        },
        tokenUsage=chat_token_usage(result),
    )


@router.post("/api/chat/stream", response_model=None)
@router.post("/v1/chat/stream", response_model=None)
async def chat_stream(
    request: Request,
    body: ChatRequest,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
) -> EventSourceResponse:
    validate_media_urls(body.media_urls or [])

    async def events():
        try:
            container = get_container(request)
            service = chat_run_service(request)
            metadata = chat_metadata(body, principal)
            thread_id = str(metadata.get("sessionId") or container.settings.default_thread_id)
            async for event in service.stream_run(
                body.message,
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                trusted_user_groups=principal.groups,
                thread_id=thread_id,
                checkpoint_ns=body.checkpoint_ns,
                metadata=metadata,
            ):
                yield {"event": event.event_type, "data": json.dumps(event.as_payload())}
        except Exception as error:
            _ = error
            yield {"event": "error", "data": json.dumps({"error": "stream failed"})}

    return EventSourceResponse(events())


@router.post("/api/chat/multipart", response_model=ChatResponse, response_model_by_alias=True)
@router.post("/v1/chat/multipart", response_model=ChatResponse, response_model_by_alias=True)
async def chat_multipart(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(principal_from_headers)],
    message: Annotated[str, Form(min_length=1, max_length=50_000)],
    files: list[UploadFile],
    model: Annotated[str | None, Form()] = None,
    system_prompt: Annotated[str | None, Form(alias="systemPrompt")] = None,
    persona_id: Annotated[str | None, Form(alias="personaId")] = None,
    user_id: Annotated[str | None, Form(alias="userId")] = None,
    session_id: Annotated[str | None, Form(alias="sessionId")] = None,
) -> ChatResponse:
    started = perf_counter()
    container = get_container(request)
    media = await read_multipart_media(files, container.settings)
    metadata: dict[str, Any] = {"multipart": True, "media": media}
    if session_id:
        metadata["sessionId"] = session_id
    body = ChatRequest(
        message=message,
        model=model,
        systemPrompt=system_prompt,
        personaId=persona_id,
        userId=user_id,
        metadata=metadata,
    )
    result = await run_chat_request(request, body, principal)
    RUNS_CREATED.labels(status=result.status).inc()
    return ChatResponse(
        content=result.response,
        success=result.status == "completed",
        model=result.model,
        durationMs=int((perf_counter() - started) * 1000),
        metadata={
            "runId": result.run_id,
            "tenantId": result.tenant_id,
            "userId": result.user_id,
            "threadId": result.thread_id,
            "checkpointNs": result.checkpoint_ns,
            "media": media,
        },
        tokenUsage=chat_token_usage(result),
    )


async def run_chat_request(request: Request, body: ChatRequest, principal: AuthPrincipal):
    container = get_container(request)
    metadata = chat_metadata(body, principal)
    thread_id = str(metadata.get("sessionId") or container.settings.default_thread_id)
    service = chat_run_service(request)
    return await service.create_run(
        body.message,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        trusted_user_groups=principal.groups,
        thread_id=thread_id,
        checkpoint_ns=body.checkpoint_ns,
        metadata=metadata,
    )


def chat_metadata(body: ChatRequest, principal: AuthPrincipal) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        **user_chat_metadata(body.metadata),
        "channel": "web",
        "tenantId": principal.tenant_id,
        "userId": principal.user_id,
    }
    if body.system_prompt:
        metadata["systemPrompt"] = body.system_prompt
    if body.model:
        metadata["model"] = body.model
    if body.model_provider:
        metadata["modelProvider"] = body.model_provider
    if body.runtime:
        metadata["runtime"] = body.runtime
    if body.graph_profile:
        metadata["graphProfile"] = body.graph_profile
    if body.persona_id:
        metadata["personaId"] = body.persona_id
    if body.prompt_template_id:
        metadata["promptTemplateId"] = body.prompt_template_id
    if body.response_format:
        metadata["responseFormat"] = body.response_format
    if body.response_schema:
        metadata["responseSchema"] = body.response_schema
    fallback_models = [model.strip() for model in body.fallback_models if model.strip()]
    if fallback_models:
        metadata["fallbackModels"] = fallback_models
    if body.media_urls:
        metadata["mediaUrls"] = [
            {"url": media.url.strip(), "mimeType": media.mime_type.strip()}
            for media in body.media_urls
        ]
    return metadata


def user_chat_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    return {
        key: value
        for key, value in (metadata or {}).items()
        if key not in CHAT_METADATA_RESERVED_KEYS
    }


def chat_run_service(request: Request) -> RunService:
    container = get_container(request)
    run_lifecycle_publisher_factory = getattr(container, "run_lifecycle_publisher", None)
    runtime_settings_store_factory = getattr(container, "runtime_settings_store", None)
    service = RunService(
        container.settings,
        container.run_store(),
        container.graph,
        usage_ledger(container),
        checkpointer=getattr(container, "checkpointer", None),
        graph_store=getattr(container, "graph_store", None),
        tool_provider=getattr(container, "tool_store", lambda: None)(),
        tool_handler=getattr(container, "agent_tool_handler", lambda: None)(),
        tool_invocation_store=getattr(container, "tool_invocation_store", lambda: None)(),
        builtin_tool_specs=getattr(container, "builtin_tool_specs", None),
        run_lifecycle_publisher=run_lifecycle_publisher_factory()
        if run_lifecycle_publisher_factory is not None
        else None,
        runtime_settings_store=runtime_settings_store_factory()
        if runtime_settings_store_factory is not None
        else None,
        approval_store=getattr(container, "approval_store", lambda: None)(),
    )
    return service


def usage_ledger(container: AppContainer):
    accessor = getattr(container, "usage_ledger", None)
    return accessor() if accessor is not None else None


def chat_token_usage(result: Any) -> ChatTokenUsage | None:
    usage = getattr(result, "token_usage", None)
    if usage is None:
        return None
    return ChatTokenUsage(
        inputTokens=usage.input_tokens,
        outputTokens=usage.output_tokens,
        totalTokens=usage.total_tokens,
    )


def chat_grounding_summary(
    metadata: Mapping[str, object],
) -> tuple[bool | None, int | None, str | None]:
    research_plan = metadata.get("research_plan")
    if not isinstance(research_plan, Mapping):
        return None, None, None
    research_plan_mapping = cast(Mapping[str, object], research_plan)
    evidence_status = research_plan_mapping.get("evidenceStatus")
    source_count = research_plan_mapping.get("sourceCount")
    verified_source_count = source_count if isinstance(source_count, int) else None
    if evidence_status == "grounded":
        return True, verified_source_count, None
    if evidence_status != "missing":
        return None, verified_source_count, None
    missing_evidence = research_plan_mapping.get("missingEvidence")
    if isinstance(missing_evidence, list):
        missing = [
            item
            for item in cast(list[object], missing_evidence)
            if isinstance(item, str) and item.strip()
        ]
        if missing:
            return False, verified_source_count, f"missing_research_evidence:{','.join(missing)}"
    return False, verified_source_count, "missing_research_evidence"


def validate_media_urls(media_urls: list[MediaUrlRequest]) -> None:
    for media in media_urls:
        url = media.url.strip()
        mime_type = media.mime_type.strip()
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid media URL")
        if "/" not in mime_type or mime_type.startswith("/") or mime_type.endswith("/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid media mimeType",
            )


async def read_multipart_media(files: list[UploadFile], settings: Settings) -> list[dict[str, Any]]:
    if not settings.multimodal_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Multimodal file upload is disabled",
        )
    if len(files) > settings.multimodal_max_files_per_request:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Too many files: {len(files)} exceeds limit of "
                f"{settings.multimodal_max_files_per_request}"
            ),
        )
    media: list[dict[str, Any]] = []
    for upload in files:
        size = await read_upload_size_with_limit(upload, settings.multimodal_max_file_size_bytes)
        media.append(
            {
                "name": upload.filename or "upload",
                "mimeType": upload.content_type or "application/octet-stream",
                "sizeBytes": size,
            }
        )
    return media


async def read_upload_size_with_limit(upload: UploadFile, max_bytes: int) -> int:
    accumulated = 0
    while True:
        chunk = await upload.read(UPLOAD_READ_CHUNK_SIZE)
        if not chunk:
            break
        accumulated += len(chunk)
        if accumulated > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{upload.filename or 'upload'}' exceeds size limit of {max_bytes}B",
            )
    await upload.seek(0)
    return accumulated
