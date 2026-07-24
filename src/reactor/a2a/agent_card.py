from __future__ import annotations

from urllib.parse import urlsplit

from a2a.types.a2a_pb2 import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from google.protobuf.json_format import MessageToDict

from reactor import __version__
from reactor.core.settings import Settings


def build_sdk_agent_card(settings: Settings | None = None) -> AgentCard:
    supported_interfaces = []
    endpoint = canonical_a2a_endpoint(settings)
    if endpoint is not None:
        supported_interfaces.extend(
            [
                AgentInterface(
                    url=endpoint,
                    protocol_binding="JSONRPC",
                    protocol_version="1.0",
                ),
                AgentInterface(
                    url=endpoint,
                    protocol_binding="REST",
                    protocol_version="1.0",
                ),
            ]
        )
    return AgentCard(
        name="Reactor",
        description="Python/LangGraph Reactor agent runtime.",
        version=__version__,
        supported_interfaces=supported_interfaces,
        capabilities=AgentCapabilities(streaming=True, push_notifications=True),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="reactor-agent-run",
                name="Reactor agent run",
                description="Run Reactor's LangGraph-backed agent runtime.",
                tags=["langgraph", "agent"],
                input_modes=["text/plain"],
                output_modes=["text/plain"],
            )
        ],
    )


def default_agent_card(settings: Settings | None = None) -> dict[str, object]:
    payload = MessageToDict(build_sdk_agent_card(settings), preserving_proto_field_name=False)
    return dict(payload.items())


def canonical_a2a_endpoint(settings: Settings | None) -> str | None:
    if settings is None:
        return None
    base_url = settings.external_base_url.strip().rstrip("/")
    if not base_url:
        return None
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{base_url}/a2a"
