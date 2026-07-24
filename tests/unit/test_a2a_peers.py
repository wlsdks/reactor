from __future__ import annotations

import pytest
from pydantic import ValidationError

from reactor.a2a.peers import A2APeerCreateRequest, A2APeerRecord


def test_a2a_peer_request_maps_protocol_aliases() -> None:
    request = A2APeerCreateRequest(
        tenantId="tenant_1",
        name="peer-a",
        endpointUrl="https://peer.example/a2a",
        agentCard={"name": "Peer A", "protocolVersion": "1.0"},
        enabled=True,
    )

    draft = request.to_draft()

    assert draft.tenant_id == "tenant_1"
    assert draft.name == "peer-a"
    assert draft.endpoint_url == "https://peer.example/a2a"
    assert draft.agent_card["protocolVersion"] == "1.0"
    assert draft.peer_agent_id.startswith("a2apeer_")


def test_a2a_peer_response_uses_protocol_aliases() -> None:
    response = A2APeerRecord(
        peer_agent_id="peer_1",
        tenant_id="tenant_1",
        name="peer-a",
        endpoint_url="https://peer.example/a2a",
        agent_card={"name": "Peer A"},
        enabled=True,
    ).to_response()

    payload = response.model_dump(by_alias=True)

    assert payload["peerAgentId"] == "peer_1"
    assert payload["tenantId"] == "tenant_1"
    assert payload["endpointUrl"] == "https://peer.example/a2a"
    assert payload["agentCard"] == {"name": "Peer A"}


@pytest.mark.parametrize("endpoint_url", ["peer.example/a2a", "ftp://peer.example/a2a"])
def test_a2a_peer_request_rejects_non_http_absolute_endpoint(endpoint_url: str) -> None:
    with pytest.raises(ValidationError, match="endpointUrl must be an absolute http or https URL"):
        A2APeerCreateRequest(
            tenantId="tenant_1",
            name="peer-a",
            endpointUrl=endpoint_url,
            agentCard={"name": "Peer A", "protocolVersion": "1.0"},
        )
