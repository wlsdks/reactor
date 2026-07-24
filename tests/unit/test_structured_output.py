from __future__ import annotations

from typing import cast

from langchain_core.messages import HumanMessage

from reactor.agents.graph import build_reactor_graph
from reactor.agents.langchain_agent import enforce_structured_response_boundary_with_metadata
from reactor.agents.runner import run_once
from reactor.agents.state import ReactorState
from reactor.core.settings import Settings
from reactor.response.filters import ResponseFilterChain, ResponseFilterContext
from reactor.response.structured import (
    ResponseFormat,
    StructuredOutputResult,
    StructuredOutputValidator,
    StructuredResponseRepairer,
    context_manifest_citation_ids,
    context_manifest_unsafe_citation_count,
    context_manifest_unsafe_citation_ids,
    merge_citation_response_schema,
)


def test_structured_output_validator_strips_markdown_fence() -> None:
    raw = """
    ```json
    {"ok": true}
    ```
    """

    assert StructuredOutputValidator().strip_markdown_code_fence(raw) == '{"ok": true}'


def test_structured_output_validator_accepts_json_and_rejects_invalid_json() -> None:
    validator = StructuredOutputValidator()

    assert validator.is_valid_format('{"name":"reactor"}', ResponseFormat.JSON)
    assert not validator.is_valid_format("{bad", ResponseFormat.JSON)


def test_structured_output_validator_applies_json_schema() -> None:
    validator = StructuredOutputValidator()
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }

    assert validator.is_valid_format('{"answer":"ok"}', ResponseFormat.JSON, schema=schema)
    assert not validator.is_valid_format('{"wrong":"shape"}', ResponseFormat.JSON, schema=schema)


def test_structured_output_validator_requires_object_json_without_schema() -> None:
    validator = StructuredOutputValidator()

    assert validator.is_valid_format('{"answer":"ok"}', ResponseFormat.JSON)
    assert not validator.is_valid_format('["answer", "ok"]', ResponseFormat.JSON)
    assert not validator.is_valid_format('"ok"', ResponseFormat.JSON)


def test_structured_output_validator_allows_explicit_array_json_schema() -> None:
    validator = StructuredOutputValidator()
    schema = {"type": "array", "items": {"type": "string"}}

    assert validator.is_valid_format('["answer", "ok"]', ResponseFormat.JSON, schema=schema)
    assert not validator.is_valid_format('[1, "ok"]', ResponseFormat.JSON, schema=schema)


def test_structured_output_validator_fails_closed_on_invalid_json_schema() -> None:
    validator = StructuredOutputValidator()
    schema = {"type": "made_up_type"}

    assert not validator.is_valid_format('{"answer":"ok"}', ResponseFormat.JSON, schema=schema)


def test_merge_citation_response_schema_requires_manifest_citations() -> None:
    schema = merge_citation_response_schema(
        {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        {
            "sections": {
                "rag_context": {
                    "metadata": {
                        "citations": [
                            {"citation_id": "rag:doc_1:0"},
                            {"citation_id": "rag:doc_2:1"},
                        ]
                    }
                }
            }
        },
    )
    validator = StructuredOutputValidator()

    assert validator.is_valid_format(
        '{"answer":"grounded","citations":["rag:doc_1:0"]}',
        ResponseFormat.JSON,
        schema=schema,
    )
    assert not validator.is_valid_format(
        '{"answer":"ungrounded","citations":["rag:unknown:0"]}',
        ResponseFormat.JSON,
        schema=schema,
    )
    assert not validator.is_valid_format(
        '{"answer":"missing citations"}',
        ResponseFormat.JSON,
        schema=schema,
    )


def test_context_manifest_citation_ids_include_single_and_citation_list_entries() -> None:
    manifest = {
        "sections": {
            "rag_context": {
                "metadata": {
                    "citation_id": "rag:doc_1:0",
                    "citations": [
                        {"citation_id": "rag:doc_1:0"},
                        {"citation_id": "rag:doc_2:1"},
                    ],
                }
            }
        }
    }
    schema = merge_citation_response_schema(
        {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        manifest,
    )
    validator = StructuredOutputValidator()

    assert context_manifest_citation_ids(manifest) == ["rag:doc_1:0", "rag:doc_2:1"]
    assert validator.is_valid_format(
        '{"answer":"grounded","citations":["rag:doc_2:1"]}',
        ResponseFormat.JSON,
        schema=schema,
    )


def test_context_manifest_citation_ids_exclude_unsafe_entries() -> None:
    manifest = {
        "sections": {
            "rag_context": {
                "metadata": {
                    "citation_id": "rag:doc_1:0",
                    "citations": [
                        {"citation_id": "rag:doc_1:0"},
                        {"citation_id": "doc bad/path"},
                        {"citation_id": " rag:doc_2:1 "},
                        {"citation_id": "   "},
                    ],
                }
            }
        }
    }
    schema = merge_citation_response_schema(
        {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        manifest,
    )
    validator = StructuredOutputValidator()

    assert context_manifest_citation_ids(manifest) == ["rag:doc_1:0"]
    assert context_manifest_unsafe_citation_ids(manifest) == [
        "doc bad/path",
        " rag:doc_2:1 ",
        "   ",
    ]
    assert context_manifest_unsafe_citation_count(manifest) == 3
    assert validator.is_valid_format(
        '{"answer":"grounded","citations":["rag:doc_1:0"]}',
        ResponseFormat.JSON,
        schema=schema,
    )
    assert not validator.is_valid_format(
        '{"answer":"unsafe","citations":["doc bad/path"]}',
        ResponseFormat.JSON,
        schema=schema,
    )


async def test_structured_boundary_rejects_noncanonical_rag_manifest_citation_ids() -> None:
    result = await enforce_structured_response_boundary_with_metadata(
        '{"answer":"grounded","citations":["rag:doc_1:0"]}',
        response_format="JSON",
        structured_output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        context_manifest={
            "sections": {
                "rag_context": {
                    "metadata": {
                        "citation_id": "rag:doc_1:0",
                        "citations": [
                            {"citation_id": "rag:doc_1:0"},
                            {"citation_id": " rag:doc_2:1 "},
                        ],
                    }
                }
            }
        },
    )

    assert result.response == "Response blocked by structured output policy."
    assert result.metadata["structured_output_error_code"] == "UNSAFE_CONTEXT_CITATION_IDS"
    assert result.metadata["structured_output_unsafe_citation_count"] == 1
    assert result.metadata["structured_output_allowed_citation_ids"] == ["rag:doc_1:0"]


def test_context_manifest_counts_orphan_and_duplicate_citation_claims_as_unsafe() -> None:
    manifest: dict[str, object] = {
        "sections": {
            "rag_context": {
                "metadata": {
                    "chunk_count": 1,
                    "orphan_citation_id_count": 2,
                    "duplicate_citation_id_count": 1,
                    "citation_metadata_mismatch_count": 2,
                    "duplicate_chunk_citation_id_count": 1,
                    "invalid_chunk_citation_id_count": 1,
                    "citations": [],
                }
            }
        }
    }

    assert context_manifest_unsafe_citation_count(manifest) == 7


def test_structured_output_validator_yaml_requires_collection_shape() -> None:
    validator = StructuredOutputValidator()

    assert validator.is_valid_format("name: reactor", ResponseFormat.YAML)
    assert validator.is_valid_format("- one\n- two", ResponseFormat.YAML)
    assert not validator.is_valid_format("just a scalar", ResponseFormat.YAML)


def test_structured_output_validator_applies_yaml_schema() -> None:
    validator = StructuredOutputValidator()
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }

    assert validator.is_valid_format("answer: ok", ResponseFormat.YAML, schema=schema)
    assert not validator.is_valid_format("wrong: shape", ResponseFormat.YAML, schema=schema)


async def test_structured_response_repairer_returns_stripped_valid_json() -> None:
    repairer = StructuredResponseRepairer()

    result = await repairer.validate_and_repair(
        '```json\n{"ok": true}\n```',
        ResponseFormat.JSON,
    )

    assert result == StructuredOutputResult(success=True, content='{"ok": true}')


async def test_structured_response_repairer_uses_repair_callback_and_bounds_input() -> None:
    seen_invalid_content = ""

    async def repair(invalid_content: str, response_format: ResponseFormat) -> str:
        nonlocal seen_invalid_content
        seen_invalid_content = invalid_content
        assert response_format == ResponseFormat.JSON
        return '{"fixed": true}'

    repairer = StructuredResponseRepairer(repair_callback=repair, max_repair_input_chars=8)

    result = await repairer.validate_and_repair(
        "{bad" + ("x" * 100),
        ResponseFormat.JSON,
    )

    assert seen_invalid_content == "{badxxxx"
    assert result == StructuredOutputResult(success=True, content='{"fixed": true}')


async def test_structured_response_repairer_fails_when_repair_is_invalid() -> None:
    async def repair(invalid_content: str, response_format: ResponseFormat) -> str:
        del invalid_content, response_format
        return "{still bad"

    repairer = StructuredResponseRepairer(repair_callback=repair)

    result = await repairer.validate_and_repair("{bad", ResponseFormat.JSON)

    assert result.success is False
    assert result.error_code == "INVALID_RESPONSE"


async def test_graph_applies_structured_response_repairer() -> None:
    async def repair(invalid_content: str, response_format: ResponseFormat) -> str:
        assert "Agent runtime is ready" in invalid_content
        assert "Reactor Python" not in invalid_content
        assert response_format == ResponseFormat.JSON
        return '{"answer": "fixed"}'

    graph = build_reactor_graph(
        structured_response_repairer=StructuredResponseRepairer(repair_callback=repair)
    )

    result = await graph.ainvoke(
        ReactorState(
            run_id="run_test",
            tenant_id="tenant_1",
            user_id="user_1",
            messages=[HumanMessage(content="return json")],
            response_format="JSON",
            tool_call_count=0,
            max_tool_calls=1,
        )
    )

    assert result["response_text"] == '{"answer": "fixed"}'
    assert result["response_metadata"]["structured_output_status"] == "repaired"


async def test_graph_marks_schema_invalid_structured_response() -> None:
    graph = build_reactor_graph(structured_response_repairer=StructuredResponseRepairer())

    result = await graph.ainvoke(
        ReactorState(
            run_id="run_test",
            tenant_id="tenant_1",
            user_id="user_1",
            messages=[HumanMessage(content="return json")],
            response_format="JSON",
            response_schema={
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            },
            tool_call_count=0,
            max_tool_calls=1,
        )
    )

    assert result["response_text"] == "Response blocked by structured output policy."
    assert result["response_metadata"]["structured_output_status"] == "invalid"
    assert result["response_metadata"]["structured_output_error_code"] == "INVALID_RESPONSE"
    assert result["response_metadata"]["stop_reason"] == "structured_output_invalid"
    assert "Reactor Python/LangGraph runtime is ready" not in result["response_text"]


async def test_graph_requires_citations_when_manifest_contains_rag_evidence() -> None:
    async def repair(invalid_content: str, response_format: ResponseFormat) -> str:
        del invalid_content
        assert response_format == ResponseFormat.JSON
        return '{"answer": "grounded but missing citations"}'

    graph = build_reactor_graph(
        structured_response_repairer=StructuredResponseRepairer(repair_callback=repair)
    )

    result = await graph.ainvoke(
        ReactorState(
            run_id="run_test",
            tenant_id="tenant_1",
            user_id="user_1",
            messages=[HumanMessage(content="return json")],
            response_format="JSON",
            response_schema={
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            },
            tool_results=[
                {
                    "tool_id": "Rag:hybrid_search",
                    "status": "succeeded",
                    "tool_call_id": "call_rag",
                    "payload": {
                        "chunks": [
                            {
                                "citation_id": "policy_doc:3",
                                "document_id": "policy_doc",
                                "chunk_index": 3,
                                "content": "Reactor requires grounded citations.",
                                "metadata": {"source_uri": "s3://tenant/policy.md"},
                            }
                        ],
                        "citations": [
                            {
                                "citation_id": "policy_doc:3",
                                "source_uri": "s3://tenant/policy.md",
                                "document_id": "policy_doc",
                                "chunk_index": 3,
                                "acl_proof": {"acl_hash": "acl_1"},
                            }
                        ],
                    },
                }
            ],
            tool_call_count=1,
            max_tool_calls=1,
        )
    )

    assert result["response_text"] == "Response blocked by structured output policy."
    assert result["response_metadata"]["structured_output_status"] == "invalid"
    assert result["response_metadata"]["structured_output_error_code"] == "INVALID_RESPONSE"
    assert result["response_metadata"]["structured_output_citation_policy"] == "required"


async def test_graph_blocks_rag_json_when_manifest_has_chunks_without_citation_ids() -> None:
    repair_called = False

    async def repair(invalid_content: str, response_format: ResponseFormat) -> str:
        nonlocal repair_called
        repair_called = True
        del invalid_content
        assert response_format == ResponseFormat.JSON
        return '{"answer": "grounded", "citations": ["policy_doc:3"]}'

    graph = build_reactor_graph(
        structured_response_repairer=StructuredResponseRepairer(repair_callback=repair)
    )

    result = await graph.ainvoke(
        ReactorState(
            run_id="run_test",
            tenant_id="tenant_1",
            user_id="user_1",
            messages=[HumanMessage(content="return json")],
            response_format="JSON",
            response_schema={
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            },
            tool_results=[
                {
                    "tool_id": "Rag:hybrid_search",
                    "status": "succeeded",
                    "tool_call_id": "call_rag",
                    "payload": {
                        "chunks": [
                            {
                                "document_id": "policy_doc",
                                "chunk_index": 3,
                                "content": "Reactor requires grounded citations.",
                                "metadata": {"source_uri": "s3://tenant/policy.md"},
                            }
                        ],
                        "citations": [],
                    },
                }
            ],
            tool_call_count=1,
            max_tool_calls=1,
        )
    )

    assert result["response_text"] == "Response blocked by structured output policy."
    assert result["response_metadata"]["structured_output_status"] == "invalid"
    assert result["response_metadata"]["structured_output_error_code"] == (
        "UNSAFE_CONTEXT_CITATION_IDS"
    )
    assert result["response_metadata"]["structured_output_citation_policy"] == "required"
    assert result["response_metadata"]["structured_output_citation_count"] == 0
    assert result["response_metadata"]["structured_output_unsafe_citation_count"] == 1
    assert result["response_metadata"]["structured_output_allowed_citation_ids"] == []
    sections = cast(list[dict[str, object]], result["context_manifest"]["sections"])
    rag_section = next(section for section in sections if section["name"] == "rag_context")
    rag_metadata = cast(dict[str, object], rag_section["metadata"])
    assert rag_metadata["invalid_chunk_citation_id_count"] == 1
    assert repair_called is False


async def test_graph_blocks_partial_rag_grounding_when_a_chunk_lacks_a_safe_id() -> None:
    repair_called = False

    async def repair(invalid_content: str, response_format: ResponseFormat) -> str:
        nonlocal repair_called
        repair_called = True
        del invalid_content
        assert response_format == ResponseFormat.JSON
        return '{"answer":"grounded","citations":["doc_valid:0"]}'

    graph = build_reactor_graph(
        structured_response_repairer=StructuredResponseRepairer(repair_callback=repair)
    )

    result = await graph.ainvoke(
        ReactorState(
            run_id="run_test",
            tenant_id="tenant_1",
            user_id="user_1",
            messages=[HumanMessage(content="return json")],
            response_format="JSON",
            response_schema={
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            },
            tool_results=[
                {
                    "tool_id": "Rag:hybrid_search",
                    "status": "succeeded",
                    "tool_call_id": "call_rag",
                    "payload": {
                        "chunks": [
                            {
                                "citation_id": "doc_valid:0",
                                "document_id": "doc_valid",
                                "chunk_index": 0,
                                "content": "Cited RAG fact.",
                            },
                            {
                                "citation_id": " doc_missing:1 ",
                                "document_id": "doc_missing",
                                "chunk_index": 1,
                                "content": "Uncited RAG fact.",
                            },
                        ],
                        "citations": [
                            {
                                "citation_id": "doc_valid:0",
                                "document_id": "doc_valid",
                                "chunk_index": 0,
                            }
                        ],
                    },
                }
            ],
            tool_call_count=1,
            max_tool_calls=1,
        )
    )

    assert result["response_text"] == "Response blocked by structured output policy."
    assert result["response_metadata"]["structured_output_error_code"] == (
        "UNSAFE_CONTEXT_CITATION_IDS"
    )
    assert result["response_metadata"]["structured_output_unsafe_citation_count"] == 1
    assert result["response_metadata"]["structured_output_allowed_citation_ids"] == ["doc_valid:0"]
    assert repair_called is False


async def test_graph_blocks_rag_json_when_manifest_has_unsafe_citation_ids() -> None:
    repair_called = False

    async def repair(invalid_content: str, response_format: ResponseFormat) -> str:
        nonlocal repair_called
        repair_called = True
        del invalid_content
        assert response_format == ResponseFormat.JSON
        return '{"answer": "grounded", "citations": ["doc_bad_path"]}'

    graph = build_reactor_graph(
        structured_response_repairer=StructuredResponseRepairer(repair_callback=repair)
    )

    result = await graph.ainvoke(
        ReactorState(
            run_id="run_test",
            tenant_id="tenant_1",
            user_id="user_1",
            messages=[HumanMessage(content="return json")],
            response_format="JSON",
            response_schema={
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            },
            tool_results=[
                {
                    "tool_id": "Rag:hybrid_search",
                    "status": "succeeded",
                    "tool_call_id": "call_rag",
                    "payload": {
                        "chunks": [
                            {
                                "citation_id": "policy_doc:3",
                                "document_id": "policy_doc",
                                "chunk_index": 3,
                                "content": "Reactor requires grounded citations.",
                                "metadata": {"source_uri": "s3://tenant/policy.md"},
                            }
                        ],
                        "citations": [
                            {
                                "citation_id": "doc bad/path",
                                "source_uri": "s3://tenant/policy.md",
                                "document_id": "policy_doc",
                                "chunk_index": 3,
                                "content_hash": "hash_doc_1",
                            }
                        ],
                    },
                }
            ],
            tool_call_count=1,
            max_tool_calls=1,
        )
    )

    assert result["response_text"] == "Response blocked by structured output policy."
    assert result["response_metadata"]["structured_output_status"] == "invalid"
    assert result["response_metadata"]["structured_output_error_code"] == (
        "UNSAFE_CONTEXT_CITATION_IDS"
    )
    assert result["response_metadata"]["structured_output_citation_policy"] == "required"
    assert result["response_metadata"]["structured_output_citation_count"] == 0
    assert result["response_metadata"]["structured_output_unsafe_citation_count"] == 1
    assert result["response_metadata"]["structured_output_allowed_citation_ids"] == []
    sections = cast(list[dict[str, object]], result["context_manifest"]["sections"])
    rag_section = next(section for section in sections if section["name"] == "rag_context")
    rag_metadata = cast(dict[str, object], rag_section["metadata"])
    assert rag_metadata["invalid_citation_id_count"] == 1
    assert rag_metadata["citation_count"] == 0
    assert rag_metadata["cited_chunk_count"] == 0
    assert rag_metadata["uncited_chunk_count"] == 1
    assert "citations" not in rag_metadata
    assert repair_called is False


async def test_graph_filters_repaired_structured_response_not_original_text() -> None:
    async def repair(invalid_content: str, response_format: ResponseFormat) -> str:
        del invalid_content
        assert response_format == ResponseFormat.JSON
        return '{"answer": "fixed"}'

    graph = build_reactor_graph(
        structured_response_repairer=StructuredResponseRepairer(repair_callback=repair),
        response_filter_chain=ResponseFilterChain([RecordingPrefixFilter()]),
    )

    result = await graph.ainvoke(
        ReactorState(
            run_id="run_test",
            tenant_id="tenant_1",
            user_id="user_1",
            messages=[HumanMessage(content="return json")],
            response_format="JSON",
            tool_call_count=0,
            max_tool_calls=1,
        )
    )

    assert result["response_text"] == 'filtered:{"answer": "fixed"}'
    assert result["response_metadata"]["structured_output_status"] == "repaired"
    assert result["response_metadata"]["response_filter_status"] == "modified"


async def test_graph_records_response_filter_unchanged_when_repair_changed_content() -> None:
    async def repair(invalid_content: str, response_format: ResponseFormat) -> str:
        del invalid_content
        assert response_format == ResponseFormat.JSON
        return '{"answer": "fixed"}'

    graph = build_reactor_graph(
        structured_response_repairer=StructuredResponseRepairer(repair_callback=repair),
        response_filter_chain=ResponseFilterChain([NoopFilter()]),
    )

    result = await graph.ainvoke(
        ReactorState(
            run_id="run_test",
            tenant_id="tenant_1",
            user_id="user_1",
            messages=[HumanMessage(content="return json")],
            response_format="JSON",
            tool_call_count=0,
            max_tool_calls=1,
        )
    )

    assert result["response_text"] == '{"answer": "fixed"}'
    assert result["response_metadata"]["structured_output_status"] == "repaired"
    assert result["response_metadata"]["response_filter_status"] == "unchanged"


async def test_run_once_passes_response_format_into_graph_state() -> None:
    graph = RecordingGraph()

    await run_once(
        "return json",
        Settings(),
        graph=graph,
        response_format="JSON",
    )

    assert graph.last_state["response_format"] == "JSON"


async def test_run_once_passes_response_schema_into_graph_state() -> None:
    graph = RecordingGraph()
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }

    await run_once(
        "return json",
        Settings(),
        graph=graph,
        response_format="JSON",
        structured_output_schema=schema,
    )

    assert graph.last_state["response_schema"] == schema


class RecordingGraph:
    def __init__(self) -> None:
        self.last_state: dict[str, object] = {}

    async def ainvoke(
        self, state: dict[str, object], *, config: dict[str, object]
    ) -> dict[str, object]:
        del config
        self.last_state = state
        return {"response_text": '{"ok": true}', "messages": []}


class RecordingPrefixFilter:
    order = 10

    async def filter(self, content: str, context: ResponseFilterContext) -> str:
        del context
        return f"filtered:{content}"


class NoopFilter:
    order = 10

    async def filter(self, content: str, context: ResponseFilterContext) -> str:
        del context
        return content
