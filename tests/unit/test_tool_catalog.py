from __future__ import annotations

import pytest

from reactor.tools.catalog import ToolSpec


def test_tool_spec_uses_fully_qualified_name() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="builtin",
        name="search_docs",
        description="Search approved documents and return cited snippets.",
        risk_level="read",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    assert spec.qualified_name == "builtin:search_docs"
    assert spec.approval_required is False


def test_write_tool_requires_approval_by_default() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="builtin",
        name="send_webhook",
        description="Send a signed webhook after approval.",
        risk_level="external_side_effect",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    assert spec.approval_required is True


@pytest.mark.parametrize("risk_level", ["write", "external_side_effect", "destructive"])
def test_high_risk_tool_cannot_disable_approval(risk_level: str) -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="builtin",
        name="send_webhook",
        description="Send a signed webhook after approval.",
        risk_level=risk_level,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        requires_approval=False,
    )

    assert spec.approval_required is True


def test_tool_spec_rejects_ambiguous_names() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="bad:namespace",
        name="tool",
        description="Invalid namespace.",
        risk_level="read",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    with pytest.raises(ValueError, match="must not contain"):
        spec.validate()


@pytest.mark.parametrize(
    ("namespace", "name"),
    [
        ("", "search_docs"),
        ("   ", "search_docs"),
        ("builtin", ""),
        ("builtin", "   "),
    ],
)
def test_tool_spec_rejects_blank_qualified_name_parts(namespace: str, name: str) -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace=namespace,
        name=name,
        description="Search approved documents.",
        risk_level="read",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    with pytest.raises(ValueError, match="namespace and name are required"):
        spec.validate()


@pytest.mark.parametrize("timeout_ms", [0, -1, 300_001, True])
def test_tool_spec_rejects_invalid_timeout_ms(timeout_ms: int) -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="Files",
        name="write",
        description="Write a file.",
        risk_level="write",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        timeout_ms=timeout_ms,
    )

    with pytest.raises(ValueError, match="tool timeout_ms must be between 1 and 300000"):
        spec.validate()


def test_tool_spec_rejects_non_object_output_schema() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="Files",
        name="write",
        description="Write a file.",
        risk_level="write",
        input_schema={"type": "object"},
        output_schema={"type": "array"},
    )

    with pytest.raises(ValueError, match="tool output_schema must have type object"):
        spec.validate()


def test_tool_spec_rejects_non_object_output_properties() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="Files",
        name="write",
        description="Write a file.",
        risk_level="write",
        input_schema={"type": "object"},
        output_schema={"type": "object", "properties": []},
    )

    with pytest.raises(ValueError, match="tool output_schema properties must be an object"):
        spec.validate()


def test_tool_spec_rejects_non_object_input_properties() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="Files",
        name="write",
        description="Write a file.",
        risk_level="write",
        input_schema={"type": "object", "properties": []},
        output_schema={"type": "object"},
    )

    with pytest.raises(ValueError, match="tool input_schema properties must be an object"):
        spec.validate()


def test_tool_spec_rejects_non_string_required_fields() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="Files",
        name="write",
        description="Write a file.",
        risk_level="write",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path", 3],
        },
        output_schema={"type": "object"},
    )

    with pytest.raises(ValueError, match="tool input_schema required must be string names"):
        spec.validate()


def test_tool_spec_rejects_malformed_input_property_schema() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="Files",
        name="write",
        description="Write a file.",
        risk_level="write",
        input_schema={
            "type": "object",
            "properties": {"path": []},
        },
        output_schema={"type": "object"},
    )

    with pytest.raises(ValueError, match="tool input_schema properties must define objects"):
        spec.validate()


def test_tool_spec_rejects_malformed_output_property_schema() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="Files",
        name="write",
        description="Write a file.",
        risk_level="write",
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "properties": {"status": []},
        },
    )

    with pytest.raises(ValueError, match="tool output_schema properties must define objects"):
        spec.validate()


@pytest.mark.parametrize("field_name", ["config", "runtime", "tool_call_id"])
def test_tool_spec_rejects_reserved_langchain_input_fields(field_name: str) -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="Files",
        name="write",
        description="Write a file.",
        risk_level="write",
        input_schema={
            "type": "object",
            "properties": {field_name: {"type": "string"}},
        },
        output_schema={"type": "object"},
    )

    with pytest.raises(ValueError, match="reserved LangChain tool argument"):
        spec.validate()


def test_tool_spec_rejects_required_fields_missing_from_properties() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="Files",
        name="write",
        description="Write a file.",
        risk_level="write",
        input_schema={
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["path"],
        },
        output_schema={"type": "object"},
    )

    with pytest.raises(ValueError, match="tool input_schema required fields must exist"):
        spec.validate()


def test_tool_spec_rejects_required_output_fields_missing_from_properties() -> None:
    spec = ToolSpec(
        tenant_id="tenant_1",
        namespace="Files",
        name="write",
        description="Write a file.",
        risk_level="write",
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["artifact_id"],
        },
    )

    with pytest.raises(ValueError, match="tool output_schema required fields must exist"):
        spec.validate()
