from __future__ import annotations

from typing import cast

from google.protobuf.json_format import MessageToDict

from reactor import __version__
from reactor.a2a.agent_card import build_sdk_agent_card, canonical_a2a_endpoint, default_agent_card
from reactor.core.settings import Settings


def test_default_agent_card_is_serialized_from_sdk_agent_card() -> None:
    sdk_payload = MessageToDict(build_sdk_agent_card(), preserving_proto_field_name=False)

    assert default_agent_card() == sdk_payload
    assert sdk_payload["name"] == "Reactor"
    assert sdk_payload["version"] == __version__
    assert sdk_payload["capabilities"]["streaming"] is True
    assert sdk_payload["skills"][0]["id"] == "reactor-agent-run"


def test_default_agent_card_includes_canonical_supported_interface_when_configured() -> None:
    payload = default_agent_card(Settings(external_base_url="https://api.reactor.example/"))
    interfaces = payload["supportedInterfaces"]
    assert isinstance(interfaces, list)
    interface = cast(dict[str, object], interfaces[0])

    assert interface["url"] == "https://api.reactor.example/a2a"
    assert interface["protocolBinding"] == "JSONRPC"
    assert interface["protocolVersion"] == "1.0"


def test_canonical_a2a_endpoint_ignores_missing_or_invalid_external_base_url() -> None:
    assert canonical_a2a_endpoint(Settings(external_base_url="")) is None
    assert canonical_a2a_endpoint(Settings(external_base_url="api.reactor.example")) is None
