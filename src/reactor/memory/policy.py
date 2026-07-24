from __future__ import annotations

import importlib.util
from dataclasses import dataclass

MEMORY_TYPES = {"semantic", "episodic", "procedural", "retrieval"}
VISIBILITY_SCOPES = {"user", "task", "tenant"}


@dataclass(frozen=True)
class MemoryNamespaceKey:
    tenant_id: str
    subject_type: str
    subject_id: str
    memory_type: str
    visibility: str

    def validate(self) -> None:
        for field_name, value in (
            ("tenant_id", self.tenant_id),
            ("subject_type", self.subject_type),
            ("subject_id", self.subject_id),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")
            if ":" in value:
                raise ValueError(f"{field_name} must not contain ':'")
        if self.memory_type not in MEMORY_TYPES:
            raise ValueError(f"unsupported memory_type: {self.memory_type}")
        if self.visibility not in VISIBILITY_SCOPES:
            raise ValueError(f"unsupported visibility: {self.visibility}")

    def as_tuple(self) -> tuple[str, str, str, str, str]:
        self.validate()
        return (
            self.tenant_id,
            self.subject_type,
            self.subject_id,
            self.memory_type,
            self.visibility,
        )


def langmem_available() -> bool:
    return importlib.util.find_spec("langmem") is not None
