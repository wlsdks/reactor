from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Protocol, cast

from reactor.memory.policy import MemoryNamespaceKey
from reactor.memory.service import (
    MemoryProposalDraft,
    MemoryProposalRecord,
    MemoryProposalService,
)

DEFAULT_MAX_LANGMEM_EXTRACTION_CANDIDATES = 20

LANGMEM_MANAGER_CONTRACT: Mapping[str, object] = {
    "factory": "langmem.create_memory_manager",
    "store_factory": "langmem.create_memory_store_manager",
    "invoke_api": "ainvoke",
    "input_messages_key": "messages",
    "max_steps": 1,
    "processing_mode": "background",
    "enable_inserts": True,
    "enable_updates": True,
    "enable_deletes": False,
    "application_owns_deletes": True,
    "memory_id_required": True,
    "memory_content_required": True,
    "max_candidates": DEFAULT_MAX_LANGMEM_EXTRACTION_CANDIDATES,
    "candidate_overflow_policy": "reject_all",
}


def create_langmem_memory_manager(model: str) -> Any:
    langmem_module: Any = import_module("langmem")
    return langmem_module.create_memory_manager(
        model,
        enable_inserts=True,
        enable_updates=True,
        enable_deletes=False,
    )


@dataclass(frozen=True)
class ExtractedMemoryCandidate:
    content: str
    confidence: float
    source_payload: Mapping[str, Any]


class MemoryExtractor(Protocol):
    async def extract(self, text: str) -> Sequence[ExtractedMemoryCandidate]: ...


class LangMemMemoryExtractor:
    def __init__(
        self,
        model: str,
        *,
        manager: Any | None = None,
        default_confidence: float = 0.5,
        max_candidates: int = DEFAULT_MAX_LANGMEM_EXTRACTION_CANDIDATES,
    ) -> None:
        if not 0.0 <= default_confidence <= 1.0:
            raise ValueError("default_confidence must be between 0.0 and 1.0")
        if isinstance(max_candidates, bool) or max_candidates <= 0:
            raise ValueError("max_candidates must be positive")
        self._manager = manager or create_langmem_memory_manager(model)
        self._default_confidence = default_confidence
        self._max_candidates = max_candidates

    async def extract(self, text: str) -> list[ExtractedMemoryCandidate]:
        if not text.strip():
            raise ValueError("text is required")
        memories = await self._manager.ainvoke(
            {
                "messages": [{"role": "user", "content": text}],
                "max_steps": 1,
            }
        )
        if len(memories) > self._max_candidates:
            raise ValueError("LangMem extraction exceeded candidate limit")
        return [self._candidate_from_memory(memory) for memory in memories]

    def _candidate_from_memory(self, memory: Any) -> ExtractedMemoryCandidate:
        memory_id_value = getattr(memory, "id", None)
        if not isinstance(memory_id_value, str) or not memory_id_value.strip():
            raise ValueError("LangMem memory id is required")
        memory_id = memory_id_value.strip()
        content = getattr(memory, "content", memory)
        manager_contract = dict(LANGMEM_MANAGER_CONTRACT)
        manager_contract["max_candidates"] = self._max_candidates
        source_payload: dict[str, Any] = {
            "extractor": "langmem",
            "langmem_manager_contract": manager_contract,
        }
        source_payload["langmem_memory_id"] = memory_id
        if hasattr(content, "model_dump"):
            dumped_value = content.model_dump(mode="json")
            if not isinstance(dumped_value, Mapping):
                raise ValueError("LangMem memory content is required")
            dumped = cast(Mapping[str, Any], dumped_value)
            content_value = dumped.get("content")
            source_payload["langmem_content"] = dumped
        elif isinstance(content, Mapping):
            mapped = cast(Mapping[str, Any], content)
            content_value = mapped.get("content")
            source_payload["langmem_content"] = dict(mapped)
        else:
            content_value = content
        if not isinstance(content_value, str) or not content_value.strip():
            raise ValueError("LangMem memory content is required")
        content_text = content_value.strip()
        return ExtractedMemoryCandidate(
            content=content_text,
            confidence=self._default_confidence,
            source_payload=source_payload,
        )


class LangMemProposalJob:
    def __init__(
        self,
        *,
        extractor: MemoryExtractor,
        proposal_service: MemoryProposalService,
        extraction_model: str = "langmem",
        extraction_prompt_version: str = "memory-v1",
    ) -> None:
        self._extractor = extractor
        self._proposal_service = proposal_service
        self._extraction_model = extraction_model
        self._extraction_prompt_version = extraction_prompt_version

    async def propose_from_text(
        self,
        *,
        namespace: MemoryNamespaceKey,
        text: str,
    ) -> list[MemoryProposalRecord]:
        namespace.validate()
        if not text.strip():
            raise ValueError("text is required")

        candidates = await self._extractor.extract(text)
        return [
            self._proposal_service.propose(
                MemoryProposalDraft(
                    namespace=namespace,
                    content=candidate.content,
                    source_payload=candidate.source_payload,
                    extraction_model=self._extraction_model,
                    extraction_prompt_version=self._extraction_prompt_version,
                    confidence=candidate.confidence,
                )
            )
            for candidate in candidates
        ]
