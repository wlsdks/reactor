from __future__ import annotations

from reactor.persistence.durable_store import OutboxRequest
from reactor.slack.socket_mode import (
    SlackSocketModeGateway,
    SlackSocketModeSdkRunner,
    SocketMessageListener,
)

BLANK_SLACK_APP_TOKEN = " "  # noqa: S105
SLACK_TEST_APP_TOKEN = "xapp-test"  # noqa: S105


async def test_socket_mode_gateway_acks_and_enqueues_events_api() -> None:
    store = RecordingDurableStore()
    gateway = SlackSocketModeGateway(durable_store=store, default_tenant_id="default")

    ack = await gateway.handle_envelope(
        {
            "envelope_id": "env_1",
            "type": "events_api",
            "payload": {
                "event_id": "Ev123",
                "team_id": "T1",
                "event": {"type": "app_mention", "user": "U1", "channel": "C1"},
            },
            "retry_attempt": 2,
            "retry_reason": "http_timeout",
        }
    )

    assert ack == {"envelope_id": "env_1"}
    assert len(store.requests) == 1
    request = store.requests[0]
    assert request.tenant_id == "tenant_1"
    assert request.destination == "slack.events"
    assert request.event_type == "slack.event_callback"
    assert request.idempotency_key == "slack:event:tenant_1:Ev123"
    assert request.payload == {
        "entrypoint": "socket_mode_events",
        "payload": {
            "event_id": "Ev123",
            "team_id": "T1",
            "event": {"type": "app_mention", "user": "U1", "channel": "C1"},
        },
        "retryNum": "2",
        "retryReason": "http_timeout",
    }


async def test_socket_mode_gateway_acks_and_enqueues_slash_command() -> None:
    store = RecordingDurableStore()
    gateway = SlackSocketModeGateway(durable_store=store, default_tenant_id="default")

    ack = await gateway.handle_envelope(
        {
            "envelope_id": "env_2",
            "type": "slash_commands",
            "payload": {
                "command": "/reactor",
                "text": "status",
                "user_id": "U1",
                "user_name": "sample-user",
                "channel_id": "C1",
                "channel_name": "ops",
                "team_id": "T1",
                "response_url": "https://hooks.slack.com/commands/1",
                "trigger_id": "1337.42",
            },
        }
    )

    assert ack == {"envelope_id": "env_2"}
    assert len(store.requests) == 1
    request = store.requests[0]
    assert request.tenant_id == "tenant_1"
    assert request.destination == "slack.commands"
    assert request.event_type == "slack.slash_command"
    assert request.idempotency_key == "slack:command:tenant_1:T1:U1:1337.42"
    assert request.payload == {
        "entrypoint": "socket_mode_slash_command",
        "command": {
            "command": "/reactor",
            "text": "status",
            "userId": "U1",
            "userName": "sample-user",
            "channelId": "C1",
            "channelName": "ops",
            "teamId": "T1",
            "responseUrl": "https://hooks.slack.com/commands/1",
            "triggerId": "1337.42",
        },
    }


async def test_socket_mode_gateway_disambiguates_slash_command_without_trigger_id() -> None:
    store = RecordingDurableStore()
    gateway = SlackSocketModeGateway(durable_store=store, default_tenant_id="default")

    await gateway.handle_envelope(
        {
            "envelope_id": "env_status",
            "type": "slash_commands",
            "payload": {
                "command": "/reactor",
                "text": "status",
                "user_id": "U1",
                "channel_id": "C1",
                "team_id": "T1",
                "response_url": "https://hooks.slack.com/commands/1",
            },
        }
    )
    await gateway.handle_envelope(
        {
            "envelope_id": "env_help",
            "type": "slash_commands",
            "payload": {
                "command": "/reactor",
                "text": "help",
                "user_id": "U1",
                "channel_id": "C1",
                "team_id": "T1",
                "response_url": "https://hooks.slack.com/commands/1",
            },
        }
    )

    keys = [request.idempotency_key for request in store.requests]
    assert len(keys) == 2
    assert keys[0] != keys[1]
    assert all(key.startswith("slack:command:tenant_1:T1:U1:missing-trigger:") for key in keys)


async def test_socket_mode_gateway_acks_and_enqueues_interactive_payload() -> None:
    store = RecordingDurableStore()
    gateway = SlackSocketModeGateway(durable_store=store, default_tenant_id="default")

    ack = await gateway.handle_envelope(
        {
            "envelope_id": "env_3",
            "type": "interactive",
            "payload": {
                "type": "block_actions",
                "team": {"id": "T1"},
                "user": {"id": "U1"},
                "actions": [{"action_id": "feedback.up"}],
                "message": {"ts": "1710000000.000100"},
            },
        }
    )

    assert ack == {"envelope_id": "env_3"}
    assert len(store.requests) == 1
    request = store.requests[0]
    assert request.tenant_id == "tenant_1"
    assert request.destination == "slack.interactions"
    assert request.event_type == "slack.block_action"
    assert request.idempotency_key == (
        "slack:interaction:tenant_1:T1:U1:feedback.up:1710000000.000100"
    )
    assert request.payload == {
        "entrypoint": "socket_mode_interactive",
        "interaction": {
            "type": "block_actions",
            "team": {"id": "T1"},
            "user": {"id": "U1"},
            "actions": [{"action_id": "feedback.up"}],
            "message": {"ts": "1710000000.000100"},
        },
    }


async def test_socket_mode_gateway_acks_unsupported_payload_without_enqueue() -> None:
    store = RecordingDurableStore()
    gateway = SlackSocketModeGateway(durable_store=store, default_tenant_id="default")

    ack = await gateway.handle_envelope({"envelope_id": "env_4", "type": "hello"})

    assert ack == {"envelope_id": "env_4"}
    assert store.requests == []


async def test_socket_mode_sdk_runner_rejects_blank_app_token() -> None:
    store = RecordingDurableStore()
    gateway = SlackSocketModeGateway(durable_store=store, default_tenant_id="default")
    runner = SlackSocketModeSdkRunner(
        app_token=BLANK_SLACK_APP_TOKEN,
        gateway=gateway,
        client_factory=FakeSocketModeClient,
    )

    try:
        await runner.start()
    except ValueError as error:
        assert str(error) == "Slack Socket Mode app token is required"
    else:
        raise AssertionError("expected ValueError")


async def test_socket_mode_sdk_runner_registers_listener_connects_and_closes() -> None:
    store = RecordingDurableStore()
    gateway = SlackSocketModeGateway(durable_store=store, default_tenant_id="default")
    runner = SlackSocketModeSdkRunner(
        app_token=SLACK_TEST_APP_TOKEN,
        gateway=gateway,
        client_factory=FakeSocketModeClient,
    )

    await runner.start()
    client = runner.client
    await runner.close()

    assert isinstance(client, FakeSocketModeClient)
    assert client.app_token == SLACK_TEST_APP_TOKEN
    assert len(client.message_listeners) == 1
    assert client.connected is True
    assert client.closed is True


async def test_socket_mode_sdk_runner_sends_gateway_ack_response() -> None:
    store = RecordingDurableStore()
    gateway = SlackSocketModeGateway(durable_store=store, default_tenant_id="default")
    runner = SlackSocketModeSdkRunner(
        app_token=SLACK_TEST_APP_TOKEN,
        gateway=gateway,
        client_factory=FakeSocketModeClient,
    )

    await runner.start()
    client = runner.client
    assert isinstance(client, FakeSocketModeClient)
    await client.message_listeners[0](
        client,
        {
            "envelope_id": "env_5",
            "type": "events_api",
            "payload": {"event_id": "Ev999", "team_id": "T1"},
        },
        "{}",
    )

    assert client.sent_responses == [{"envelope_id": "env_5"}]
    assert store.requests[0].idempotency_key == "slack:event:tenant_1:Ev999"


class FakeSocketModeClient:
    def __init__(self, app_token: str) -> None:
        self.app_token = app_token
        self.message_listeners: list[SocketMessageListener] = []
        self.sent_responses: list[dict[str, str]] = []
        self.connected = False
        self.closed = False

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.closed = True

    async def send_socket_mode_response(self, response: dict[str, str]) -> None:
        self.sent_responses.append(response)


class RecordingDurableStore:
    def __init__(self) -> None:
        self.requests: list[OutboxRequest] = []

    async def enqueue_outbox(self, request: OutboxRequest) -> str:
        self.requests.append(request)
        return f"outbox_{len(self.requests)}"

    async def start_idempotency(
        self,
        *,
        key: str,
        tenant_id: str,
        scope: str,
        request_checksum: str,
    ) -> bool:
        del key, tenant_id, scope, request_checksum
        return True

    async def claim_outbox(
        self,
        *,
        tenant_id: str,
        lease_owner: str,
        limit: int = 10,
    ) -> list[object]:
        del tenant_id, lease_owner, limit
        return []

    async def mark_outbox_dispatched(self, *, event_id: str, lease_owner: str) -> None:
        del event_id, lease_owner

    async def mark_outbox_failed(
        self,
        *,
        event_id: str,
        lease_owner: str,
        status: str,
        error: str,
        retry_after_seconds: int | None = None,
    ) -> None:
        del event_id, lease_owner, status, error, retry_after_seconds

    async def claim_run_queue(
        self,
        *,
        tenant_id: str,
        lease_owner: str,
        lease_seconds: int,
        limit: int = 1,
    ) -> list[object]:
        del tenant_id, lease_owner, lease_seconds, limit
        return []

    async def heartbeat_run_queue(
        self,
        *,
        queue_id: str,
        lease_owner: str,
        fencing_token: int,
        lease_seconds: int,
    ) -> bool:
        del queue_id, lease_owner, fencing_token, lease_seconds
        return True

    async def release_expired_run_queue(self, *, tenant_id: str) -> int:
        del tenant_id
        return 0
