from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from reactor.tools.catalog import ToolSpec

SANDBOX_REQUIRED_NAMESPACES = frozenset(
    {
        "browser",
        "code",
        "computer",
        "filesystem",
        "file",
        "python",
        "shell",
    }
)
SANDBOX_REQUIRED_NAME_MARKERS = (
    "browser",
    "exec",
    "execute",
    "file_write",
    "shell",
    "write_file",
)
SANDBOX_REQUIRED_RISKS = frozenset({"destructive"})


@dataclass(frozen=True)
class SandboxPolicy:
    sandboxed_tool_names: frozenset[str] = field(default_factory=lambda: frozenset[str]())

    @classmethod
    def from_names(cls, names: Iterable[str]) -> SandboxPolicy:
        return cls(frozenset(normalize_tool_name(name) for name in names if name.strip()))

    def is_sandboxed(self, tool: ToolSpec) -> bool:
        return tool.qualified_name in self.sandboxed_tool_names

    def requires_sandbox(self, tool: ToolSpec) -> bool:
        namespace = tool.namespace.strip().lower()
        name = tool.name.strip().lower()
        if namespace in SANDBOX_REQUIRED_NAMESPACES:
            return True
        if tool.risk_level in SANDBOX_REQUIRED_RISKS:
            return True
        return any(marker in name for marker in SANDBOX_REQUIRED_NAME_MARKERS)

    def admission_failure_reason(self, tool: ToolSpec) -> str | None:
        if self.requires_sandbox(tool) and not self.is_sandboxed(tool):
            return "sandbox_required"
        return None


def normalize_tool_name(name: str) -> str:
    normalized = name.strip()
    if ":" not in normalized:
        raise ValueError("sandboxed tool names must be qualified as Namespace:name")
    namespace, tool_name = normalized.split(":", 1)
    if not namespace.strip() or not tool_name.strip():
        raise ValueError("sandboxed tool names must include namespace and name")
    return f"{namespace.strip()}:{tool_name.strip()}"
