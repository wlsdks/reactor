from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from reactor.a2a.urls import require_absolute_http_url
from reactor.kernel.ids import new_id


def dict_payload() -> dict[str, Any]:
    return {}


class A2APeerCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(default="local", alias="tenantId")
    name: str = Field(min_length=1)
    endpoint_url: str = Field(alias="endpointUrl", min_length=1)
    agent_card: dict[str, Any] = Field(default_factory=dict, alias="agentCard")
    enabled: bool = True

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint_url(cls, value: str) -> str:
        return require_absolute_http_url(value, field_name="endpointUrl")

    def to_draft(self) -> A2APeerDraft:
        return A2APeerDraft.from_request(self)


class A2APeerResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    peer_agent_id: str = Field(alias="peerAgentId")
    tenant_id: str = Field(alias="tenantId")
    name: str
    endpoint_url: str = Field(alias="endpointUrl")
    agent_card: dict[str, Any] = Field(alias="agentCard")
    enabled: bool


@dataclass(frozen=True)
class A2APeerDraft:
    tenant_id: str
    name: str
    endpoint_url: str
    agent_card: Mapping[str, Any] = field(default_factory=dict_payload)
    enabled: bool = True
    peer_agent_id: str = field(default_factory=lambda: new_id("a2apeer"))

    @classmethod
    def from_request(cls, request: A2APeerCreateRequest) -> A2APeerDraft:
        return cls(
            tenant_id=request.tenant_id,
            name=request.name,
            endpoint_url=request.endpoint_url,
            agent_card=request.agent_card,
            enabled=request.enabled,
        )


@dataclass(frozen=True)
class A2APeerRecord:
    peer_agent_id: str
    tenant_id: str
    name: str
    endpoint_url: str
    agent_card: Mapping[str, Any]
    enabled: bool

    def to_response(self) -> A2APeerResponse:
        return A2APeerResponse(
            peerAgentId=self.peer_agent_id,
            tenantId=self.tenant_id,
            name=self.name,
            endpointUrl=self.endpoint_url,
            agentCard=dict(self.agent_card),
            enabled=self.enabled,
        )
