from __future__ import annotations

import pytest

from reactor.sandbox.policy import SandboxPolicy, normalize_tool_name
from reactor.tools.catalog import ToolSpec


def test_sandbox_policy_requires_isolation_for_shell_browser_file_and_destructive_tools() -> None:
    policy = SandboxPolicy()

    assert policy.admission_failure_reason(tool(namespace="Shell", name="exec")) == (
        "sandbox_required"
    )
    assert policy.admission_failure_reason(tool(namespace="Browser", name="open")) == (
        "sandbox_required"
    )
    assert policy.admission_failure_reason(tool(namespace="builtin", name="write_file")) == (
        "sandbox_required"
    )
    assert (
        policy.admission_failure_reason(
            tool(namespace="builtin", name="delete_index", risk_level="destructive")
        )
        == "sandbox_required"
    )


def test_sandbox_policy_allows_registered_sandboxed_tools() -> None:
    policy = SandboxPolicy.from_names(["Shell:exec"])

    assert policy.admission_failure_reason(tool(namespace="Shell", name="exec")) is None


def test_sandbox_tool_names_must_be_qualified() -> None:
    with pytest.raises(ValueError, match="qualified"):
        normalize_tool_name("exec")


def tool(*, namespace: str, name: str, risk_level: str = "read") -> ToolSpec:
    return ToolSpec(
        tenant_id="tenant_1",
        namespace=namespace,
        name=name,
        description="Test tool.",
        risk_level=risk_level,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        requires_approval=False,
    )
