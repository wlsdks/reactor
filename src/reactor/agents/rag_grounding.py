from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from reactor.tools.sanitizer import sanitize_tool_output


def rag_tool_citation_ids(tool_results: Sequence[object]) -> list[str]:
    citation_ids: list[str] = []
    for citation in rag_tool_citations(tool_results):
        citation_id = citation_manifest_id(citation)
        if citation_id is not None and citation_id not in citation_ids:
            citation_ids.append(citation_id)
    return citation_ids


def rag_tool_source_labels(tool_results: Sequence[object]) -> list[str]:
    source_labels: list[str] = []
    for citation in rag_tool_citations(tool_results):
        source_uri = optional_string(citation.get("source_uri"))
        if source_uri is not None and source_uri not in source_labels:
            source_labels.append(source_uri)
    return source_labels


def rag_tool_citations(tool_results: Sequence[object]) -> list[Mapping[str, object]]:
    citations_by_result: list[Mapping[str, object]] = []
    for result in tool_results:
        if not isinstance(result, Mapping):
            continue
        payload = cast(Mapping[str, object], result).get("payload")
        if not isinstance(payload, Mapping):
            continue
        citations = cast(Mapping[str, object], payload).get("citations")
        if not isinstance(citations, list):
            continue
        citations_by_result.extend(
            cast(Mapping[str, object], citation)
            for citation in cast(list[object], citations)
            if isinstance(citation, Mapping)
        )
    return citations_by_result


def citation_manifest_id(citation: Mapping[str, object]) -> str | None:
    explicit = citation.get("citation_id")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    document_id = citation.get("document_id")
    chunk_index = citation.get("chunk_index")
    if isinstance(document_id, str) and document_id.strip() and isinstance(chunk_index, int):
        return f"{document_id.strip()}:{chunk_index}"
    return None


def grounded_research_fallback_response(
    latest_user_text: str,
    research_plan: object,
    *,
    tool_results: Sequence[object] = (),
) -> str | None:
    if not isinstance(research_plan, Mapping):
        return None
    plan = cast(Mapping[str, object], research_plan)
    answer_contract = mapping_from_mapping(plan, "answerContract")
    if not answer_contract:
        return None
    citation_ids = string_list_from_mapping(answer_contract, "citationIds")
    source_labels = string_list_from_mapping(answer_contract, "sourceLabels")
    if not citation_ids or not source_labels:
        return None
    cited_answers = cited_rag_answer_lines(tool_results, citation_ids)
    answer_section = "\n\n" + "\n".join(cited_answers) + "\n\n" if cited_answers else " "
    return (
        f"Research answer is grounded by cited RAG evidence.{answer_section}"
        f"Sources: {', '.join(source_labels)}. "
        f"Citations: {', '.join(citation_ids)}. "
        f"Input: {latest_user_text}"
    )


def cited_rag_answer_lines(
    tool_results: Sequence[object], citation_ids: Sequence[str]
) -> list[str]:
    citation_id_set = set(citation_ids)
    cited_hash_by_id = rag_tool_citation_content_hashes(tool_results)
    lines: list[str] = []
    for chunk in rag_tool_chunks(tool_results):
        chunk_id = chunk_manifest_id(chunk)
        if chunk_id is None or chunk_id not in citation_id_set:
            continue
        cited_hash = cited_hash_by_id.get(chunk_id)
        chunk_hash = optional_string(chunk.get("content_hash"))
        if cited_hash is not None and chunk_hash != cited_hash:
            continue
        content = optional_string(chunk.get("content"))
        if content is None:
            continue
        sanitized = " ".join(sanitize_tool_output(content).model_visible_text.split())
        if not sanitized:
            continue
        line = f"- {sanitized} [{chunk_id}]"
        if line not in lines:
            lines.append(line)
    return lines


def rag_tool_citation_content_hashes(tool_results: Sequence[object]) -> dict[str, str]:
    hash_by_id: dict[str, str] = {}
    for citation in rag_tool_citations(tool_results):
        citation_id = citation_manifest_id(citation)
        content_hash = optional_string(citation.get("content_hash"))
        if citation_id is not None and content_hash is not None:
            hash_by_id[citation_id] = content_hash
    return hash_by_id


def rag_tool_chunks(tool_results: Sequence[object]) -> list[Mapping[str, object]]:
    chunks_by_result: list[Mapping[str, object]] = []
    for result in tool_results:
        if not isinstance(result, Mapping):
            continue
        payload = cast(Mapping[str, object], result).get("payload")
        if not isinstance(payload, Mapping):
            continue
        chunks = cast(Mapping[str, object], payload).get("chunks")
        if not isinstance(chunks, list):
            continue
        chunks_by_result.extend(
            cast(Mapping[str, object], chunk)
            for chunk in cast(list[object], chunks)
            if isinstance(chunk, Mapping)
        )
    return chunks_by_result


def chunk_manifest_id(chunk: Mapping[str, object]) -> str | None:
    document_id = chunk.get("document_id")
    chunk_index = chunk.get("chunk_index")
    if isinstance(document_id, str) and document_id.strip() and isinstance(chunk_index, int):
        return f"{document_id.strip()}:{chunk_index}"
    return None


def optional_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def string_list_from_mapping(value: Mapping[str, object], key: str) -> list[str]:
    items = value.get(key)
    if not isinstance(items, list):
        return []
    return [
        item.strip() for item in cast(list[object], items) if isinstance(item, str) and item.strip()
    ]


def mapping_from_mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    nested = value.get(key)
    return dict(cast(Mapping[str, object], nested)) if isinstance(nested, Mapping) else {}
