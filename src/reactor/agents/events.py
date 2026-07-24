from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

STREAM_EVENT_TYPES = {
    "run.stream.started",
    "run.stream.token",
    "run.stream.tool",
    "run.stream.approval",
    "run.stream.completed",
}


def empty_payload() -> dict[str, Any]:
    return {}


@dataclass(frozen=True)
class AgentStreamEvent:
    run_id: str
    sequence: int
    event_type: str
    graph_node: str
    trace_id: str
    payload: Mapping[str, Any] = field(default_factory=empty_payload)

    def validate(self) -> None:
        if self.event_type not in STREAM_EVENT_TYPES:
            raise ValueError(f"unsupported stream event_type: {self.event_type}")
        if self.sequence <= 0:
            raise ValueError("stream event sequence must be positive")
        for field_name, value in (
            ("run_id", self.run_id),
            ("graph_node", self.graph_node),
            ("trace_id", self.trace_id),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")

    def as_payload(self) -> dict[str, Any]:
        self.validate()
        return {
            "run_id": self.run_id,
            "sequence": self.sequence,
            "graph_node": self.graph_node,
            "trace_id": self.trace_id,
            **dict(self.payload),
        }
