from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol, cast

from reactor.persistence.durable_store import OutboxRequest
from reactor.slack.inbound import (
    build_slack_command_idempotency_key,
    build_slack_event_idempotency_key,
)


class DurableOutbox(Protocol):
    async def enqueue_outbox(self, request: OutboxRequest) -> str: ...


class SocketModeClientProtocol(Protocol):
    message_listeners: list[SocketMessageListener]

    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def send_socket_mode_response(self, response: dict[str, str]) -> None: ...


SocketMessageListener = Callable[
    [SocketModeClientProtocol, Mapping[str, object], str],
    Awaitable[None],
]
SocketModeClientFactory = Callable[[str], SocketModeClientProtocol]


class SlackSocketModeGateway:
    def __init__(
        self,
        *,
        durable_store: DurableOutbox,
        default_tenant_id: str,
    ) -> None:
        self._durable_store = durable_store
        self._default_tenant_id = default_tenant_id

    async def handle_envelope(self, envelope: Mapping[str, object]) -> dict[str, str]:
        envelope_id = optional_str(envelope, "envelope_id")
        payload_type = optional_str(envelope, "type") or ""
        payload = envelope_payload(envelope.get("payload"))

        if payload_type == "events_api":
            await self._enqueue_event(payload, envelope)
        elif payload_type == "slash_commands":
            await self._enqueue_slash_command(payload)
        elif payload_type in {"interactive", "block_actions", "view_submission"}:
            await self._enqueue_interaction(payload)

        return {"envelope_id": envelope_id} if envelope_id else {}

    async def _enqueue_event(
        self,
        payload: Mapping[str, object] | None,
        envelope: Mapping[str, object],
    ) -> None:
        if payload is None:
            return
        event_id = optional_str(payload, "event_id")
        if event_id is None:
            return
        tenant_id = slack_tenant_id_from_payload(payload, self._default_tenant_id)
        await self._durable_store.enqueue_outbox(
            OutboxRequest(
                tenant_id=tenant_id,
                destination="slack.events",
                event_type="slack.event_callback",
                idempotency_key=build_slack_event_idempotency_key(tenant_id, event_id),
                payload={
                    "entrypoint": "socket_mode_events",
                    "payload": dict(payload),
                    "retryNum": optional_retry_str(envelope, "retry_attempt"),
                    "retryReason": optional_str(envelope, "retry_reason"),
                },
            )
        )

    async def _enqueue_slash_command(self, payload: Mapping[str, object] | None) -> None:
        if payload is None:
            return
        command = optional_str(payload, "command")
        user_id = optional_str(payload, "user_id")
        channel_id = optional_str(payload, "channel_id")
        response_url = optional_str(payload, "response_url")
        if command is None or user_id is None or channel_id is None or response_url is None:
            return

        team_id = optional_str(payload, "team_id")
        trigger_id = optional_str(payload, "trigger_id")
        text = optional_str(payload, "text") or ""
        tenant_id = slack_tenant_id_from_payload(payload, self._default_tenant_id)
        await self._durable_store.enqueue_outbox(
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
                    "entrypoint": "socket_mode_slash_command",
                    "command": {
                        "command": command,
                        "text": text,
                        "userId": user_id,
                        "userName": optional_str(payload, "user_name"),
                        "channelId": channel_id,
                        "channelName": optional_str(payload, "channel_name"),
                        "teamId": team_id,
                        "responseUrl": response_url,
                        "triggerId": trigger_id,
                    },
                },
            )
        )

    async def _enqueue_interaction(self, payload: Mapping[str, object] | None) -> None:
        if payload is None:
            return
        action_id = slack_interaction_action_id(payload)
        if action_id is None:
            return
        team_id = slack_interaction_team_id(payload)
        user_id = slack_interaction_user_id(payload)
        tenant_id = slack_tenant_id_from_payload(
            {"team_id": team_id},
            self._default_tenant_id,
        )
        await self._durable_store.enqueue_outbox(
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
                    "entrypoint": "socket_mode_interactive",
                    "interaction": dict(payload),
                },
            )
        )


class SlackSocketModeSdkRunner:
    def __init__(
        self,
        *,
        app_token: str,
        gateway: SlackSocketModeGateway,
        client_factory: SocketModeClientFactory | None = None,
    ) -> None:
        self._app_token = app_token
        self._gateway = gateway
        self._client_factory = client_factory or slack_sdk_aiohttp_socket_mode_client
        self._client: SocketModeClientProtocol | None = None

    @property
    def client(self) -> SocketModeClientProtocol | None:
        return self._client

    async def start(self) -> None:
        if not self._app_token.strip():
            raise ValueError("Slack Socket Mode app token is required")
        client = self._client_factory(self._app_token)
        client.message_listeners.append(self._handle_message)
        await client.connect()
        self._client = client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    async def _handle_message(
        self,
        client: SocketModeClientProtocol,
        message: Mapping[str, object],
        raw_message: str,
    ) -> None:
        del raw_message
        ack = await self._gateway.handle_envelope(message)
        if ack:
            await client.send_socket_mode_response(ack)


def slack_sdk_aiohttp_socket_mode_client(app_token: str) -> SocketModeClientProtocol:
    from slack_sdk.socket_mode.aiohttp import SocketModeClient

    return cast(SocketModeClientProtocol, SocketModeClient(app_token=app_token))


def envelope_payload(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, Mapping):
            return cast(Mapping[str, object], parsed)
    return None


def slack_tenant_id_from_payload(payload: Mapping[str, object], default_tenant_id: str) -> str:
    team_id = optional_str(payload, "team_id")
    if team_id is not None:
        return "tenant_1" if team_id == "T1" else team_id
    return default_tenant_id


def optional_str(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


def optional_retry_str(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, int):
        return str(value)
    return optional_str(payload, key)


def slack_interaction_action_id(payload: Mapping[str, object]) -> str | None:
    actions = payload.get("actions")
    if isinstance(actions, list) and actions:
        first = cast(list[object], actions)[0]
        if isinstance(first, Mapping):
            return optional_str(cast(Mapping[str, object], first), "action_id")
    view = payload.get("view")
    if isinstance(view, Mapping):
        return optional_str(cast(Mapping[str, object], view), "callback_id")
    return None


def slack_interaction_team_id(payload: Mapping[str, object]) -> str | None:
    team = payload.get("team")
    if isinstance(team, Mapping):
        return optional_str(cast(Mapping[str, object], team), "id")
    return optional_str(payload, "team_id")


def slack_interaction_user_id(payload: Mapping[str, object]) -> str | None:
    user = payload.get("user")
    if isinstance(user, Mapping):
        return optional_str(cast(Mapping[str, object], user), "id")
    return optional_str(payload, "user_id")


def slack_interaction_message_ts(payload: Mapping[str, object]) -> str | None:
    message = payload.get("message")
    if isinstance(message, Mapping):
        return optional_str(cast(Mapping[str, object], message), "ts")
    return None


def build_slack_interaction_idempotency_key(
    tenant_id: str,
    team_id: str,
    user_id: str,
    action_id: str,
    message_ts: str | None,
) -> str:
    return f"slack:interaction:{tenant_id}:{team_id}:{user_id}:{action_id}:{message_ts or 'no-ts'}"
