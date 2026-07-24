from __future__ import annotations

import json
from dataclasses import replace
from inspect import isawaitable
from typing import Annotated, Any, cast
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.api.auth import require_permission
from reactor.api.schemas.slack import (
    AddProactiveChannelRequest,
    CreateSlackBotRequest,
    ProactiveChannelResponse,
    SlackBotResponse,
    SlackCommandAckResponse,
    SlackFaqDryRunRequest,
    SlackFaqIngestTriggerResponse,
    SlackFaqProbeRequest,
    SlackFaqRegistrationListResponse,
    SlackFaqRegistrationPatch,
    SlackFaqRegistrationRequest,
    SlackFaqRegistrationResponse,
    UpdateSlackBotRequest,
)
from reactor.auth.rbac import AuthPrincipal, current_actor
from reactor.core.container import AppContainer
from reactor.persistence.durable_store import OutboxRequest
from reactor.slack.faq import AutoReplyMode, ChannelFaqRegistration, IngestStatus
from reactor.slack.inbound import (
    InMemorySlackEventDeduplicator,
    SlackSignatureVerifier,
    build_slack_command_idempotency_key,
    build_slack_event_idempotency_key,
)
from reactor.slack.models import (
    ProactiveChannelRecord,
    SlackBotInstanceRecord,
    mask_slack_token,
)

router = APIRouter(tags=["slack"])
_event_deduplicators: dict[int, InMemorySlackEventDeduplicator] = {}


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.reactor)


@router.post("/api/admin/slack/prompts/reload")
@router.post("/v1/admin/slack/prompts/reload")
async def reload_slack_prompts(
    request: Request,
    _: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> dict[str, object]:
    loaded = await reload_slack_prompt_sections(request)
    sections = sorted(loaded)
    return {
        "reloaded": True,
        "sectionCount": len(sections),
        "sections": sections,
    }


@router.get(
    "/api/admin/slack-bots",
    response_model=list[SlackBotResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/slack-bots",
    response_model=list[SlackBotResponse],
    response_model_by_alias=True,
)
async def list_slack_bots(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> list[SlackBotResponse]:
    records = await require_slack_bot_store(request).list(tenant_id=principal.tenant_id)
    return [slack_bot_response(record) for record in records]


@router.get(
    "/api/admin/slack-bots/{bot_id}",
    response_model=SlackBotResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/slack-bots/{bot_id}",
    response_model=SlackBotResponse,
    response_model_by_alias=True,
)
async def get_slack_bot(
    request: Request,
    bot_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> SlackBotResponse:
    record = await require_slack_bot_store(request).get(
        tenant_id=principal.tenant_id, bot_id=bot_id
    )
    if record is None:
        raise slack_bot_not_found(bot_id)
    return slack_bot_response(record)


@router.post(
    "/api/admin/slack-bots",
    response_model=SlackBotResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/v1/admin/slack-bots",
    response_model=SlackBotResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_slack_bot(
    request: Request,
    body: CreateSlackBotRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> SlackBotResponse:
    store = require_slack_bot_store(request)
    existing = await find_bot_by_name(store, tenant_id=principal.tenant_id, name=body.name)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Slack bot name is already in use: {body.name}",
        )
    record = SlackBotInstanceRecord(
        tenant_id=principal.tenant_id,
        name=body.name,
        bot_token=body.botToken,
        app_token=body.appToken,
        persona_id=body.personaId,
        default_channel=body.defaultChannel,
        enabled=body.enabled,
    )
    try:
        saved = await store.save(record)
    except ValueError as error:
        raise invalid_request(error) from error
    return slack_bot_response(saved)


@router.put(
    "/api/admin/slack-bots/{bot_id}",
    response_model=SlackBotResponse,
    response_model_by_alias=True,
)
@router.put(
    "/v1/admin/slack-bots/{bot_id}",
    response_model=SlackBotResponse,
    response_model_by_alias=True,
)
async def update_slack_bot(
    request: Request,
    bot_id: str,
    body: UpdateSlackBotRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> SlackBotResponse:
    store = require_slack_bot_store(request)
    existing = await store.get(tenant_id=principal.tenant_id, bot_id=bot_id)
    if existing is None:
        raise slack_bot_not_found(bot_id)
    updated = existing.updated_with(
        name=body.name,
        bot_token=body.botToken,
        app_token=body.appToken,
        persona_id=body.personaId,
        default_channel=body.defaultChannel,
        enabled=body.enabled,
    )
    try:
        saved = await store.save(updated)
    except ValueError as error:
        raise invalid_request(error) from error
    return slack_bot_response(saved)


@router.delete("/api/admin/slack-bots/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/v1/admin/slack-bots/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_slack_bot(
    request: Request,
    bot_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> Response:
    deleted = await require_slack_bot_store(request).delete(
        tenant_id=principal.tenant_id, bot_id=bot_id
    )
    if not deleted:
        raise slack_bot_not_found(bot_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/api/proactive-channels",
    response_model=list[ProactiveChannelResponse],
    response_model_by_alias=True,
)
@router.get(
    "/v1/proactive-channels",
    response_model=list[ProactiveChannelResponse],
    response_model_by_alias=True,
)
async def list_proactive_channels(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> list[ProactiveChannelResponse]:
    records = await require_proactive_channel_store(request).list(tenant_id=principal.tenant_id)
    return [proactive_channel_response(record) for record in records]


@router.post(
    "/api/proactive-channels",
    response_model=ProactiveChannelResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/v1/proactive-channels",
    response_model=ProactiveChannelResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def add_proactive_channel(
    request: Request,
    body: AddProactiveChannelRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> ProactiveChannelResponse:
    store = require_proactive_channel_store(request)
    if await store.is_enabled(tenant_id=principal.tenant_id, channel_id=body.channelId):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Channel already in proactive list",
        )
    record = await store.add(
        tenant_id=principal.tenant_id,
        channel_id=body.channelId,
        channel_name=body.channelName,
    )
    await record_slack_admin_audit(
        request,
        principal=principal,
        action=AdminAuditAction.ADD,
        channel_id=body.channelId,
        detail=f"channelName={body.channelName or ''}",
    )
    return proactive_channel_response(record)


@router.delete("/api/proactive-channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/v1/proactive-channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_proactive_channel(
    request: Request,
    channel_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> Response:
    removed = await require_proactive_channel_store(request).remove(
        tenant_id=principal.tenant_id, channel_id=channel_id
    )
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found in proactive list",
        )
    await record_slack_admin_audit(
        request,
        principal=principal,
        action=AdminAuditAction.REMOVE,
        channel_id=channel_id,
        detail="removed",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/api/admin/slack/channels/faq",
    response_model=SlackFaqRegistrationListResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/slack/channels/faq",
    response_model=SlackFaqRegistrationListResponse,
    response_model_by_alias=True,
)
async def list_slack_faq_registrations(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> SlackFaqRegistrationListResponse:
    records = await maybe_await(
        require_channel_faq_registration_store(request).list(
            tenant_id=principal.tenant_id,
            enabled_only=False,
        )
    )
    return SlackFaqRegistrationListResponse(
        registrations=[slack_faq_registration_response(record) for record in records]
    )


@router.get("/api/admin/slack/channels/faq/stats")
@router.get("/v1/admin/slack/channels/faq/stats")
async def get_slack_faq_overall_stats(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> dict[str, object]:
    del principal
    return channel_faq_stats_response(slack_faq_metrics(request).overall_snapshot())


@router.get("/api/admin/slack/channels/faq/scheduler/health")
@router.get("/v1/admin/slack/channels/faq/scheduler/health")
async def get_slack_faq_scheduler_health(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> dict[str, object]:
    del principal
    scheduler = slack_faq_scheduler(request)
    if scheduler is None:
        return {"enabled": False}
    tick_count = await maybe_await(scheduler.tick_count())
    last_tick_at = await maybe_await(scheduler.last_tick_at())
    interval_ms_accessor = getattr(scheduler, "interval_ms", None)
    interval_ms = (
        await maybe_await(interval_ms_accessor())
        if interval_ms_accessor is not None
        else getattr(scheduler, "SCHEDULE_INTERVAL_MS", None)
    )
    return {
        "enabled": True,
        "tickCount": tick_count,
        "lastTickAt": last_tick_at if last_tick_at else None,
        "intervalMs": interval_ms,
    }


@router.get(
    "/api/admin/slack/channels/faq/{channel_id}",
    response_model=SlackFaqRegistrationResponse,
    response_model_by_alias=True,
)
@router.get(
    "/v1/admin/slack/channels/faq/{channel_id}",
    response_model=SlackFaqRegistrationResponse,
    response_model_by_alias=True,
)
async def get_slack_faq_registration(
    request: Request,
    channel_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> SlackFaqRegistrationResponse:
    record = await get_slack_faq_record(
        request, tenant_id=principal.tenant_id, channel_id=channel_id
    )
    return slack_faq_registration_response(record)


@router.get("/api/admin/slack/channels/faq/{channel_id}/stats")
@router.get("/v1/admin/slack/channels/faq/{channel_id}/stats")
async def get_slack_faq_channel_stats(
    request: Request,
    channel_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> dict[str, object]:
    del principal
    validate_slack_channel_id(channel_id)
    return channel_faq_stats_response(slack_faq_metrics(request).snapshot(channel_id))


@router.get("/api/admin/slack/channels/faq/{channel_id}/events")
@router.get("/v1/admin/slack/channels/faq/{channel_id}/events")
async def get_slack_faq_channel_events(
    request: Request,
    channel_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> dict[str, object]:
    del principal
    validate_slack_channel_id(channel_id)
    events = slack_faq_metrics(request).recent_events(channel_id, limit=50)
    return {"events": [faq_event_response(event) for event in events]}


@router.post("/api/admin/slack/channels/faq/{channel_id}/probe")
@router.post("/v1/admin/slack/channels/faq/{channel_id}/probe")
async def probe_slack_faq_channel(
    request: Request,
    channel_id: str,
    body: SlackFaqProbeRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> dict[str, object]:
    validate_slack_channel_id(channel_id)
    responder = require_slack_faq_responder(request)
    candidates = await responder.probe_top_k(
        tenant_id=principal.tenant_id,
        channel_id=channel_id,
        query=body.query,
        top_k=body.topK or 5,
    )
    return {
        "channelId": channel_id,
        "query": body.query,
        "candidates": [faq_candidate_response(candidate) for candidate in candidates],
    }


@router.get("/api/admin/slack/channels/faq/{channel_id}/feedback")
@router.get("/v1/admin/slack/channels/faq/{channel_id}/feedback")
async def get_slack_faq_channel_feedback(
    request: Request,
    channel_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> dict[str, object]:
    del principal
    validate_slack_channel_id(channel_id)
    feedback = slack_faq_metrics(request).feedback_snapshot(channel_id)
    return {
        "feedback": {
            doc_id: faq_feedback_response(doc_feedback) for doc_id, doc_feedback in feedback.items()
        }
    }


@router.post("/api/admin/slack/channels/faq/{channel_id}/dry-run")
@router.post("/v1/admin/slack/channels/faq/{channel_id}/dry-run")
async def dry_run_slack_faq_channel(
    request: Request,
    channel_id: str,
    body: SlackFaqDryRunRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> dict[str, object]:
    validate_slack_channel_id(channel_id)
    responder = require_slack_faq_responder(request)
    reply = await responder.dry_run_auto_reply(
        tenant_id=principal.tenant_id,
        channel_id=channel_id,
        user_id=body.userId or "U-dry-run",
        user_query=body.query,
        is_mention=True if body.asMention is None else body.asMention,
    )
    if reply is None:
        return {
            "matched": False,
            "reason": "Responder returned no FAQ match",
            "channelId": channel_id,
            "query": body.query,
        }
    return {
        "matched": True,
        "channelId": channel_id,
        "query": body.query,
        "reply": {
            "text": reply.text,
            "score": reply.score,
            "matchedDocIds": reply.matched_document_ids,
        },
    }


@router.post(
    "/api/admin/slack/channels/faq",
    response_model=SlackFaqRegistrationResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/admin/slack/channels/faq",
    response_model=SlackFaqRegistrationResponse,
    response_model_by_alias=True,
)
async def register_slack_faq_channel(
    request: Request,
    body: SlackFaqRegistrationRequest,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> SlackFaqRegistrationResponse:
    record = ChannelFaqRegistration(
        tenant_id=principal.tenant_id,
        channel_id=body.channelId,
        channel_name=body.channelName,
        enabled=body.enabled,
        auto_reply_mode=parse_auto_reply_mode(body.autoReplyMode),
        confidence_threshold=body.confidenceThreshold
        if body.confidenceThreshold is not None
        else 0.75,
        days_back=body.daysBack if body.daysBack is not None else 30,
        re_ingest_interval_hours=body.reIngestIntervalHours
        if body.reIngestIntervalHours is not None
        else 24,
        registered_by=principal.user_id,
    )
    try:
        saved = await maybe_await(require_channel_faq_registration_store(request).save(record))
    except ValueError as error:
        raise invalid_request(error) from error
    return slack_faq_registration_response(saved)


@router.patch(
    "/api/admin/slack/channels/faq/{channel_id}",
    response_model=SlackFaqRegistrationResponse,
    response_model_by_alias=True,
)
@router.patch(
    "/v1/admin/slack/channels/faq/{channel_id}",
    response_model=SlackFaqRegistrationResponse,
    response_model_by_alias=True,
)
async def update_slack_faq_registration(
    request: Request,
    channel_id: str,
    body: SlackFaqRegistrationPatch,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> SlackFaqRegistrationResponse:
    existing = await get_slack_faq_record(
        request,
        tenant_id=principal.tenant_id,
        channel_id=channel_id,
    )
    updated = replace(
        existing,
        channel_name=body.channelName if body.channelName is not None else existing.channel_name,
        enabled=body.enabled if body.enabled is not None else existing.enabled,
        auto_reply_mode=parse_auto_reply_mode(body.autoReplyMode)
        if body.autoReplyMode is not None
        else existing.auto_reply_mode,
        confidence_threshold=body.confidenceThreshold
        if body.confidenceThreshold is not None
        else existing.confidence_threshold,
        days_back=body.daysBack if body.daysBack is not None else existing.days_back,
        re_ingest_interval_hours=body.reIngestIntervalHours
        if body.reIngestIntervalHours is not None
        else existing.re_ingest_interval_hours,
    )
    try:
        saved = await maybe_await(require_channel_faq_registration_store(request).save(updated))
    except ValueError as error:
        raise invalid_request(error) from error
    return slack_faq_registration_response(saved)


@router.post(
    "/api/admin/slack/channels/faq/{channel_id}/ingest",
    response_model=SlackFaqIngestTriggerResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_202_ACCEPTED,
)
@router.post(
    "/v1/admin/slack/channels/faq/{channel_id}/ingest",
    response_model=SlackFaqIngestTriggerResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_slack_faq_ingest(
    request: Request,
    channel_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> SlackFaqIngestTriggerResponse:
    record = await get_slack_faq_record(
        request,
        tenant_id=principal.tenant_id,
        channel_id=channel_id,
    )
    await maybe_await(
        require_channel_faq_registration_store(request).update_ingest_result(
            tenant_id=principal.tenant_id,
            channel_id=channel_id,
            status=IngestStatus.RUNNING.value,
            message_count=None,
            chunk_count=None,
            error=None,
        )
    )
    outbox_id = await require_durable_store(request).enqueue_outbox(
        OutboxRequest(
            tenant_id=principal.tenant_id,
            destination="slack.faq_ingest",
            event_type="slack.channel_faq_ingest",
            idempotency_key=build_slack_faq_ingest_idempotency_key(
                principal.tenant_id,
                channel_id,
            ),
            payload={
                "entrypoint": "manual_admin",
                "channelId": channel_id,
                "daysBack": record.days_back,
            },
        )
    )
    return SlackFaqIngestTriggerResponse(
        channelId=channel_id,
        status=IngestStatus.RUNNING.value,
        outboxId=outbox_id,
    )


@router.delete("/api/admin/slack/channels/faq/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/v1/admin/slack/channels/faq/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_slack_faq_registration(
    request: Request,
    channel_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_permission("slack:write"))],
) -> Response:
    deleted = await maybe_await(
        require_channel_faq_registration_store(request).delete(
            tenant_id=principal.tenant_id,
            channel_id=channel_id,
        )
    )
    if not deleted:
        raise slack_faq_registration_not_found(channel_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/slack/events")
@router.post("/v1/slack/events")
async def handle_slack_event(request: Request) -> dict[str, object]:
    raw_body = await request.body()
    body_text = raw_body.decode()
    verify_slack_signature(request, body_text)
    payload = parse_slack_json(body_text)
    challenge = payload.get("challenge")
    if isinstance(challenge, str) and challenge:
        return {"challenge": challenge}

    tenant_id = slack_tenant_id(request, payload)
    event_id = str(payload.get("event_id") or "")
    if not event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack event_id is required",
        )
    deduplicator = event_deduplicator(request)
    if deduplicator.is_duplicate(event_id):
        return {"ok": True, "duplicate": True}

    store = require_durable_store(request)
    idempotency_key = build_slack_event_idempotency_key(tenant_id, event_id)
    outbox_id = await store.enqueue_outbox(
        OutboxRequest(
            tenant_id=tenant_id,
            destination="slack.events",
            event_type="slack.event_callback",
            idempotency_key=idempotency_key,
            payload={
                "entrypoint": "events_api",
                "payload": payload,
                "retryNum": request.headers.get("X-Slack-Retry-Num"),
                "retryReason": request.headers.get("X-Slack-Retry-Reason"),
            },
        )
    )
    await record_slack_gateway_audit(
        request,
        tenant_id=tenant_id,
        payload=payload,
        event_id=event_id,
        idempotency_key=idempotency_key,
        outbox_id=outbox_id,
    )
    deduplicator.mark(event_id)
    return {"ok": True, "duplicate": False}


@router.post(
    "/api/slack/commands",
    response_model=SlackCommandAckResponse,
    response_model_by_alias=True,
)
@router.post(
    "/v1/slack/commands",
    response_model=SlackCommandAckResponse,
    response_model_by_alias=True,
)
async def handle_slack_command(
    request: Request,
) -> SlackCommandAckResponse | JSONResponse:
    body_text = (await request.body()).decode()
    verify_slack_signature(request, body_text)
    form = parse_slack_form(body_text)
    command = form.get("command")
    text = form.get("text") or ""
    user_id = form.get("user_id")
    user_name = form.get("user_name")
    channel_id = form.get("channel_id")
    channel_name = form.get("channel_name")
    team_id = form.get("team_id")
    response_url = form.get("response_url")
    trigger_id = form.get("trigger_id")
    if (
        command is None
        or not command.strip()
        or user_id is None
        or not user_id.strip()
        or channel_id is None
        or not channel_id.strip()
        or response_url is None
        or not response_url.strip()
    ):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=SlackCommandAckResponse.invalid().model_dump(by_alias=True),
        )

    tenant_id = slack_tenant_id(request, {"team_id": team_id})
    command_payload = {
        "command": command,
        "text": text or "",
        "userId": user_id,
        "userName": user_name,
        "channelId": channel_id,
        "channelName": channel_name,
        "teamId": team_id,
        "responseUrl": response_url,
        "triggerId": trigger_id,
    }
    await require_durable_store(request).enqueue_outbox(
        OutboxRequest(
            tenant_id=tenant_id,
            destination="slack.commands",
            event_type="slack.slash_command",
            idempotency_key=build_slack_command_idempotency_key(
                tenant_id,
                team_id or "unknown-team",
                user_id,
                trigger_id,
                command=command,
                channel_id=channel_id,
                text=text,
            ),
            payload={
                "entrypoint": "slash_command",
                "command": command_payload,
            },
        )
    )
    return SlackCommandAckResponse.processing()


@router.post("/api/slack/interactions")
@router.post("/v1/slack/interactions")
async def handle_slack_interaction(request: Request) -> dict[str, object]:
    body_text = (await request.body()).decode()
    verify_slack_signature(request, body_text)
    form = parse_slack_form(body_text)
    payload_text = form.get("payload")
    if payload_text is None or not payload_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack interaction payload is required",
        )
    payload = parse_slack_json(payload_text)
    action_id = slack_interaction_action_id(payload)
    user_id = slack_interaction_user_id(payload)
    team_id = slack_interaction_team_id(payload)
    tenant_id = slack_tenant_id(request, {"team_id": team_id})
    await require_durable_store(request).enqueue_outbox(
        OutboxRequest(
            tenant_id=tenant_id,
            destination="slack.interactions",
            event_type="slack.block_action",
            idempotency_key=build_slack_interaction_idempotency_key(
                tenant_id,
                team_id or "unknown-team",
                user_id or "unknown-user",
                action_id,
                slack_interaction_message_ts(payload),
            ),
            payload={
                "entrypoint": "interactivity",
                "interaction": payload,
            },
        )
    )
    return {"ok": True}


def slack_bot_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "slack_bot_store", None)
    return accessor() if accessor is not None else None


def proactive_channel_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "proactive_channel_store", None)
    return accessor() if accessor is not None else None


def admin_audit_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "admin_audit_store", None)
    return accessor() if accessor is not None else None


def durable_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "durable_store", None)
    return accessor() if accessor is not None else None


def channel_faq_registration_store(request: Request):
    container = get_container(request)
    accessor = getattr(container, "channel_faq_registration_store", None)
    return accessor() if accessor is not None else None


def slack_faq_metrics(request: Request):
    container = get_container(request)
    accessor = getattr(container, "slack_faq_metrics", None)
    if accessor is not None:
        metrics = accessor()
        if metrics is not None:
            return metrics
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="slack FAQ metrics are not configured",
    )


def slack_faq_responder(request: Request):
    container = get_container(request)
    accessor = getattr(container, "slack_faq_responder", None)
    return accessor() if accessor is not None else None


def slack_faq_scheduler(request: Request):
    container = get_container(request)
    accessor = getattr(container, "slack_faq_scheduler", None)
    return accessor() if accessor is not None else None


def require_durable_store(request: Request):
    store = durable_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="durable queue persistence is not configured",
        )
    return store


def require_slack_bot_store(request: Request):
    store = slack_bot_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="slack bot persistence is not configured",
        )
    return store


def require_proactive_channel_store(request: Request):
    store = proactive_channel_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="proactive channel persistence is not configured",
        )
    return store


def require_channel_faq_registration_store(request: Request):
    store = channel_faq_registration_store(request)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="slack channel FAQ persistence is not configured",
        )
    return store


def require_slack_faq_responder(request: Request):
    responder = slack_faq_responder(request)
    if responder is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="slack FAQ responder is not configured",
        )
    return responder


async def find_bot_by_name(store: Any, *, tenant_id: str, name: str):
    finder = getattr(store, "find_by_name", None)
    if finder is not None:
        return await finder(tenant_id=tenant_id, name=name)
    for record in await store.list(tenant_id=tenant_id):
        if record.name == name:
            return record
    return None


async def record_slack_admin_audit(
    request: Request,
    *,
    principal: AuthPrincipal,
    action: AdminAuditAction,
    channel_id: str,
    detail: str,
) -> None:
    store = admin_audit_store(request)
    if store is None:
        return
    try:
        await store.save(
            AdminAuditLog(
                category="proactive_channel",
                action=action,
                actor=current_actor(principal),
                resource_type="proactive_channel",
                resource_id=channel_id,
                detail=detail,
            ),
            tenant_id=principal.tenant_id,
        )
    except Exception:
        return


async def record_slack_gateway_audit(
    request: Request,
    *,
    tenant_id: str,
    payload: dict[str, object],
    event_id: str,
    idempotency_key: str,
    outbox_id: str,
) -> None:
    store = admin_audit_store(request)
    if store is None:
        return
    event = payload.get("event")
    event_payload: dict[str, object] = (
        cast(dict[str, object], event) if isinstance(event, dict) else {}
    )
    team_id = payload.get("team_id")
    event_type = event_payload.get("type")
    channel_id = event_payload.get("channel")
    user_id = event_payload.get("user")
    detail = {
        "channelId": channel_id if isinstance(channel_id, str) else None,
        "entrypoint": "events_api",
        "eventId": event_id,
        "eventType": event_type if isinstance(event_type, str) else None,
        "idempotencyKey": idempotency_key,
        "outboxId": outbox_id,
        "teamId": team_id if isinstance(team_id, str) else None,
        "userId": user_id if isinstance(user_id, str) else None,
    }
    actor_team = team_id if isinstance(team_id, str) and team_id else tenant_id
    try:
        await store.save(
            AdminAuditLog(
                category="slack_gateway",
                action=AdminAuditAction.CREATE,
                actor=f"slack:{actor_team}",
                resource_type="slack_event",
                resource_id=event_id,
                detail=json.dumps(detail, sort_keys=True, separators=(",", ":")),
            ),
            tenant_id=tenant_id,
        )
    except Exception:
        return


def verify_slack_signature(request: Request, body_text: str) -> None:
    container = get_container(request)
    settings = getattr(container, "settings", None)
    signing_secret = str(getattr(settings, "slack_signing_secret", ""))
    raw_previous_signing_secrets = getattr(settings, "slack_previous_signing_secrets", [])
    previous_secret_values = (
        cast(list[object], raw_previous_signing_secrets)
        if isinstance(raw_previous_signing_secrets, list)
        else []
    )
    previous_signing_secrets = [value for value in previous_secret_values if isinstance(value, str)]
    tolerance = int(getattr(settings, "slack_signature_tolerance_seconds", 300))
    verifier = SlackSignatureVerifier(
        signing_secret=signing_secret,
        previous_signing_secrets=previous_signing_secrets,
        timestamp_tolerance_seconds=tolerance,
        now_seconds=getattr(container, "slack_now_seconds", None),
    )
    result = verifier.verify(
        timestamp=request.headers.get("X-Slack-Request-Timestamp"),
        signature=request.headers.get("X-Slack-Signature"),
        body=body_text,
    )
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result.error_message,
        )


def event_deduplicator(request: Request) -> InMemorySlackEventDeduplicator:
    container = get_container(request)
    key = id(container)
    deduplicator = _event_deduplicators.get(key)
    if deduplicator is not None:
        return deduplicator
    settings = getattr(container, "settings", None)
    deduplicator = InMemorySlackEventDeduplicator(
        ttl_seconds=int(getattr(settings, "slack_event_dedup_ttl_seconds", 600)),
        now_seconds=getattr(container, "slack_now_seconds", None),
    )
    _event_deduplicators[key] = deduplicator
    return deduplicator


def parse_slack_json(body_text: str) -> dict[str, object]:
    try:
        payload = json.loads(body_text)
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Slack JSON payload",
        ) from error
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack payload must be an object",
        )
    return cast(dict[str, object], payload)


def parse_slack_form(body_text: str) -> dict[str, str]:
    parsed = parse_qs(body_text, keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items() if values}


def slack_tenant_id(request: Request, payload: dict[str, object]) -> str:
    team_id = payload.get("team_id")
    if isinstance(team_id, str) and team_id.strip():
        return "tenant_1" if team_id == "T1" else team_id
    settings = getattr(get_container(request), "settings", None)
    return str(getattr(settings, "auth_default_tenant_id", "default"))


def slack_bot_response(record: SlackBotInstanceRecord) -> SlackBotResponse:
    return SlackBotResponse(
        id=record.id,
        name=record.name,
        botTokenMasked=mask_slack_token(record.bot_token),
        appTokenMasked=mask_slack_token(record.app_token),
        personaId=record.persona_id,
        defaultChannel=record.default_channel,
        enabled=record.enabled,
        createdAt=record.created_at.isoformat(),
        updatedAt=record.updated_at.isoformat(),
    )


def proactive_channel_response(record: ProactiveChannelRecord) -> ProactiveChannelResponse:
    return ProactiveChannelResponse(
        channelId=record.channel_id,
        channelName=record.channel_name,
        addedAt=int(record.added_at.timestamp() * 1000),
    )


def slack_faq_registration_response(record: ChannelFaqRegistration) -> SlackFaqRegistrationResponse:
    return SlackFaqRegistrationResponse(
        channelId=record.channel_id,
        channelName=record.channel_name,
        enabled=record.enabled,
        autoReplyMode=record.auto_reply_mode.value,
        confidenceThreshold=record.confidence_threshold,
        daysBack=record.days_back,
        reIngestIntervalHours=record.re_ingest_interval_hours,
        lastIngestedAt=record.last_ingested_at.isoformat()
        if record.last_ingested_at is not None
        else None,
        lastMessageCount=record.last_message_count,
        lastChunkCount=record.last_chunk_count,
        lastStatus=record.last_status,
        lastError=record.last_error,
        registeredBy=record.registered_by,
        registeredAt=record.registered_at.isoformat(),
        updatedAt=record.updated_at.isoformat(),
    )


def validate_slack_channel_id(channel_id: str) -> None:
    if not channel_id.strip() or len(channel_id) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="channelId is invalid",
        )


def channel_faq_stats_response(stats: Any) -> dict[str, object]:
    return {
        "hits": stats.hits,
        "skipsByReason": stats.skips_by_reason,
        "errors": stats.errors,
        "lastHitAt": stats.last_hit_at,
        "avgHitScore": stats.avg_hit_score,
        "total": stats.total,
        "hitRatio": stats.hit_ratio,
    }


def faq_event_response(event: Any) -> dict[str, object]:
    return {
        "timestamp": event.timestamp,
        "outcome": event.outcome,
        "score": event.score,
        "query": event.query,
        "matchedDocId": event.matched_document_id,
    }


def faq_feedback_response(feedback: Any) -> dict[str, object]:
    return {
        "docId": feedback.doc_id,
        "thumbsUp": feedback.thumbs_up,
        "thumbsDown": feedback.thumbs_down,
        "total": feedback.total,
        "negativeRatio": feedback.negative_ratio,
    }


def faq_candidate_response(candidate: Any) -> dict[str, object]:
    return {
        "documentId": candidate.document_id,
        "chunkIndex": candidate.chunk_index,
        "score": candidate.score,
        "text": candidate.text,
        "metadata": candidate.metadata,
    }


async def get_slack_faq_record(
    request: Request,
    *,
    tenant_id: str,
    channel_id: str,
) -> ChannelFaqRegistration:
    record = await maybe_await(
        require_channel_faq_registration_store(request).get(
            tenant_id=tenant_id,
            channel_id=channel_id,
        )
    )
    if record is None:
        raise slack_faq_registration_not_found(channel_id)
    return record


def parse_auto_reply_mode(value: str | None) -> AutoReplyMode:
    if value is None:
        return AutoReplyMode.MENTION
    try:
        return AutoReplyMode(value.lower())
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported autoReplyMode: {value}",
        ) from error


async def maybe_await(value: Any) -> Any:
    if isawaitable(value):
        return await value
    return value


async def reload_slack_prompt_sections(request: Request) -> list[str]:
    container = get_container(request)
    accessor = getattr(container, "slack_prompt_reloader", None)
    reloader = accessor() if accessor is not None else None
    if reloader is None:
        return []
    reload_fn = getattr(reloader, "reload", None)
    if reload_fn is None:
        return []
    loaded = await maybe_await(reload_fn())
    if isinstance(loaded, dict):
        loaded_dict = cast(dict[Any, Any], loaded)
        return [str(key) for key in loaded_dict.keys()]
    if isinstance(loaded, list | tuple | set):
        loaded_items = cast(list[Any] | tuple[Any, ...] | set[Any], loaded)
        return [str(item) for item in loaded_items]
    return []


def build_slack_faq_ingest_idempotency_key(tenant_id: str, channel_id: str) -> str:
    return f"slack:faq-ingest:{tenant_id}:{channel_id}"


def build_slack_interaction_idempotency_key(
    tenant_id: str,
    team_id: str,
    user_id: str,
    action_id: str,
    message_ts: str | None,
) -> str:
    return f"slack:interaction:{tenant_id}:{team_id}:{user_id}:{action_id}:{message_ts or 'no-ts'}"


def slack_interaction_action_id(payload: dict[str, object]) -> str:
    actions = payload.get("actions")
    if not isinstance(actions, list) or not actions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack interaction action is required",
        )
    first = cast(list[object], actions)[0]
    if not isinstance(first, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack interaction action must be an object",
        )
    action = cast(dict[str, object], first)
    action_id = action.get("action_id")
    if not isinstance(action_id, str) or not action_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack interaction action_id is required",
        )
    return action_id


def slack_interaction_user_id(payload: dict[str, object]) -> str | None:
    user = payload.get("user")
    if isinstance(user, dict):
        user_id = cast(dict[str, object], user).get("id")
        if isinstance(user_id, str) and user_id.strip():
            return user_id
    return None


def slack_interaction_team_id(payload: dict[str, object]) -> str | None:
    team = payload.get("team")
    if isinstance(team, dict):
        team_id = cast(dict[str, object], team).get("id")
        if isinstance(team_id, str) and team_id.strip():
            return team_id
    return None


def slack_interaction_message_ts(payload: dict[str, object]) -> str | None:
    message = payload.get("message")
    if isinstance(message, dict):
        message_ts = cast(dict[str, object], message).get("ts")
        if isinstance(message_ts, str) and message_ts.strip():
            return message_ts
    return None


def invalid_request(error: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


def slack_bot_not_found(bot_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Slack bot instance not found: {bot_id}",
    )


def slack_faq_registration_not_found(channel_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Slack channel FAQ registration not found: {channel_id}",
    )
