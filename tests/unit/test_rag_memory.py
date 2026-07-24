from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from langmem.knowledge.extraction import ExtractedMemory, Memory

from reactor.memory.langmem_jobs import (
    ExtractedMemoryCandidate,
    LangMemMemoryExtractor,
    LangMemProposalJob,
    create_langmem_memory_manager,
)
from reactor.memory.policy import MemoryNamespaceKey, langmem_available
from reactor.memory.service import (
    MemoryItemRecord,
    MemoryProposalDraft,
    MemoryProposalService,
)
from reactor.rag.documents import RagChunkCandidate, build_tenant_acl_filter


def test_rag_chunk_candidate_requires_non_negative_index() -> None:
    candidate = RagChunkCandidate(
        tenant_id="tenant_1",
        collection="docs",
        document_id="doc_1",
        chunk_index=-1,
        content="content",
        content_hash="hash",
        metadata={},
    )

    with pytest.raises(ValueError, match="non-negative"):
        candidate.validate()


def test_retrieval_filter_keeps_tenant_and_collection_before_ranking() -> None:
    assert build_tenant_acl_filter("tenant_1", "docs") == {
        "tenant_id": "tenant_1",
        "collection": "docs",
    }


def test_memory_namespace_rejects_raw_colon_delimited_user_input() -> None:
    key = MemoryNamespaceKey(
        tenant_id="tenant_1",
        subject_type="user",
        subject_id="bad:user",
        memory_type="semantic",
        visibility="user",
    )

    with pytest.raises(ValueError, match="must not contain"):
        key.as_tuple()


def test_langmem_dependency_is_available() -> None:
    assert langmem_available() is True


def test_langmem_jobs_import_does_not_load_deprecated_langgraph_dependency() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import warnings; "
                "from langgraph.warnings import LangGraphDeprecatedSinceV10; "
                "warnings.simplefilter('error', LangGraphDeprecatedSinceV10); "
                "import reactor.memory.langmem_jobs"
            ),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_langmem_manager_factory_explicitly_applies_lifecycle_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    expected_manager = object()

    def fake_create_memory_manager(model: str, **kwargs: object) -> object:
        calls.append((model, kwargs))
        return expected_manager

    monkeypatch.setattr("langmem.create_memory_manager", fake_create_memory_manager)

    manager = create_langmem_memory_manager("openai:gpt-5.2-mini")

    assert manager is expected_manager
    assert calls == [
        (
            "openai:gpt-5.2-mini",
            {
                "enable_inserts": True,
                "enable_updates": True,
                "enable_deletes": False,
            },
        )
    ]


def test_memory_extraction_creates_proposal_not_active_fact() -> None:
    service = MemoryProposalService(id_factory=IdSequence(), clock=fixed_clock)

    proposal = service.propose(
        MemoryProposalDraft(
            namespace=memory_namespace(),
            content="User prefers short Korean status updates.",
            source_payload={"run_id": "run_1"},
            extraction_model="langmem",
            extraction_prompt_version="memory-v1",
            confidence=0.82,
        )
    )

    assert proposal.id == "id_1"
    assert proposal.status == "proposed"
    assert proposal.tenant_id == "tenant_1"
    assert proposal.proposed_content == "User prefers short Korean status updates."
    assert proposal.source_payload == {"run_id": "run_1"}


def test_sensitive_memory_proposal_records_review_policy_evidence() -> None:
    service = MemoryProposalService(id_factory=IdSequence(), clock=fixed_clock)

    proposal = service.propose(
        MemoryProposalDraft(
            namespace=memory_namespace(),
            content="User password is correct horse battery staple.",
            source_payload={"run_id": "run_1"},
            extraction_model="langmem",
            extraction_prompt_version="memory-v1",
            confidence=0.91,
        )
    )

    assert proposal.source_payload == {
        "run_id": "run_1",
        "sensitivity": {
            "status": "flagged",
            "policy": "reject_or_redact_before_promotion",
            "markers": ["password"],
        },
    }


def test_memory_proposal_source_payload_secret_markers_require_review() -> None:
    service = MemoryProposalService(id_factory=IdSequence(), clock=fixed_clock)

    proposal = service.propose(
        MemoryProposalDraft(
            namespace=memory_namespace(),
            content="User prefers concise Korean updates.",
            source_payload={
                "run_id": "run_1",
                "tool_input": {"api_key": "contains-secret-marker"},
            },
            extraction_model="langmem",
            extraction_prompt_version="memory-v1",
            confidence=0.88,
        )
    )

    assert proposal.source_payload == {
        "run_id": "run_1",
        "tool_input": {"api_key": "contains-secret-marker"},
        "sensitivity": {
            "status": "flagged",
            "policy": "reject_or_redact_before_promotion",
            "markers": ["api_key", "secret"],
            "source": "content_or_source_payload",
        },
    }


def test_memory_proposal_source_payload_camel_case_secret_keys_require_review() -> None:
    service = MemoryProposalService(id_factory=IdSequence(), clock=fixed_clock)

    proposal = service.propose(
        MemoryProposalDraft(
            namespace=memory_namespace(),
            content="User prefers concise Korean updates.",
            source_payload={
                "run_id": "run_1",
                "toolInput": {
                    "apiKey": "redacted-value",
                    "accessToken": "opaque-value",
                },
            },
            extraction_model="langmem",
            extraction_prompt_version="memory-v1",
            confidence=0.88,
        )
    )

    assert proposal.source_payload == {
        "run_id": "run_1",
        "toolInput": {
            "apiKey": "redacted-value",
            "accessToken": "opaque-value",
        },
        "sensitivity": {
            "status": "flagged",
            "policy": "reject_or_redact_before_promotion",
            "markers": ["api_key", "token"],
            "source": "content_or_source_payload",
        },
    }


def test_memory_promotion_requires_policy_and_creates_reviewed_active_item() -> None:
    service = MemoryProposalService(id_factory=IdSequence(), clock=fixed_clock)
    proposal = service.propose(
        MemoryProposalDraft(
            namespace=memory_namespace(),
            content="User prefers concise answers.",
            source_payload={"run_id": "run_1"},
            extraction_model="langmem",
            extraction_prompt_version="memory-v1",
            confidence=0.9,
        )
    )

    result = service.promote(proposal, reviewer_id=" reviewer_1 ", reason=" stable preference ")

    assert result.proposal.status == "approved"
    assert result.proposal.decision_reason == "stable preference"
    assert result.item.id == "id_2"
    assert result.item.status == "active"
    assert result.item.source_id == "id_1"
    assert result.item.metadata["reviewer_id"] == "reviewer_1"
    assert result.item.metadata["proposal_id"] == "id_1"


def test_memory_promotion_can_supersede_prior_active_memory() -> None:
    service = MemoryProposalService(id_factory=IdSequence(), clock=fixed_clock)
    proposal = service.propose(
        MemoryProposalDraft(
            namespace=memory_namespace(),
            content="User prefers detailed English status updates.",
            source_payload={"run_id": "run_2"},
            extraction_model="langmem",
            extraction_prompt_version="memory-v1",
            confidence=0.88,
        )
    )
    prior_item = MemoryItemRecord(
        id="memory_old",
        tenant_id="tenant_1",
        namespace=memory_namespace(),
        status="active",
        content="User prefers concise Korean status updates.",
        source_id="proposal_old",
        confidence=0.8,
        metadata={"proposal_id": "proposal_old"},
        created_at=fixed_clock(),
    )

    result = service.promote(
        proposal,
        reviewer_id="reviewer_1",
        reason="updated preference",
        supersedes=prior_item,
    )

    assert result.item.status == "active"
    assert result.item.metadata["supersedes_memory_id"] == "memory_old"
    assert result.superseded_items[0].status == "superseded"
    assert result.superseded_items[0].metadata["superseded_by_proposal_id"] == "id_1"
    assert result.superseded_items[0].metadata["superseded_reason"] == "updated preference"


def test_memory_promotion_rejects_self_supersession() -> None:
    service = MemoryProposalService(id_factory=IdSequence(), clock=fixed_clock)
    proposal = service.propose(
        MemoryProposalDraft(
            namespace=memory_namespace(),
            content="User prefers detailed English status updates.",
            source_payload={"run_id": "run_2"},
            extraction_model="langmem",
            extraction_prompt_version="memory-v1",
            confidence=0.88,
        )
    )
    existing_item_from_same_proposal = MemoryItemRecord(
        id="memory_self",
        tenant_id="tenant_1",
        namespace=memory_namespace(),
        status="active",
        content="User prefers detailed English status updates.",
        source_id=proposal.id,
        confidence=0.88,
        metadata={"proposal_id": proposal.id},
        created_at=fixed_clock(),
    )

    with pytest.raises(ValueError, match="cannot supersede memory from the same proposal"):
        service.promote(
            proposal,
            reviewer_id="reviewer_1",
            reason="duplicate approval",
            supersedes=existing_item_from_same_proposal,
        )


def test_sensitive_memory_proposal_cannot_be_promoted_without_redaction() -> None:
    service = MemoryProposalService(id_factory=IdSequence(), clock=fixed_clock)
    proposal = service.propose(
        MemoryProposalDraft(
            namespace=memory_namespace(),
            content="User API_KEY is sk-live-secret.",
            source_payload={"run_id": "run_1"},
            extraction_model="langmem",
            extraction_prompt_version="memory-v1",
            confidence=0.95,
        )
    )

    with pytest.raises(ValueError, match="sensitive memory proposals"):
        service.promote(proposal, reviewer_id="reviewer_1", reason="store it")


def test_source_payload_sensitive_memory_proposal_cannot_be_promoted_without_redaction() -> None:
    service = MemoryProposalService(id_factory=IdSequence(), clock=fixed_clock)
    proposal = service.propose(
        MemoryProposalDraft(
            namespace=memory_namespace(),
            content="User prefers concise Korean updates.",
            source_payload={"tool_input": {"api_key": "contains-secret-marker"}},
            extraction_model="langmem",
            extraction_prompt_version="memory-v1",
            confidence=0.95,
        )
    )

    with pytest.raises(ValueError, match="sensitive memory proposals"):
        service.promote(proposal, reviewer_id="reviewer_1", reason="store it")


def test_memory_deletion_tombstones_item_and_deletes_embedding() -> None:
    service = MemoryProposalService(id_factory=IdSequence(), clock=fixed_clock)
    item = MemoryItemRecord(
        id="memory_1",
        tenant_id="tenant_1",
        namespace=memory_namespace(),
        status="active",
        content="User prefers concise answers.",
        source_id="proposal_1",
        confidence=0.9,
        metadata={"proposal_id": "proposal_1"},
        created_at=fixed_clock(),
    )

    result = service.tombstone(item, actor_id=" user_1 ", reason=" user requested deletion ")

    assert result.item.status == "tombstoned"
    assert result.item.metadata["tombstone_actor_id"] == "user_1"
    assert result.item.metadata["tombstone_reason"] == "user requested deletion"
    assert result.delete_embedding is True


def test_memory_rejection_records_trimmed_review_metadata() -> None:
    service = MemoryProposalService(id_factory=IdSequence(), clock=fixed_clock)
    proposal = service.propose(
        MemoryProposalDraft(
            namespace=memory_namespace(),
            content="User prefers concise answers.",
            source_payload={"run_id": "run_1"},
            extraction_model="langmem",
            extraction_prompt_version="memory-v1",
            confidence=0.9,
        )
    )

    rejected = service.reject(proposal, reviewer_id=" reviewer_1 ", reason=" too noisy ")

    assert rejected.status == "rejected"
    assert rejected.decision_reason == "too noisy reviewer=reviewer_1"


async def test_langmem_job_converts_extracted_candidates_to_proposals() -> None:
    service = MemoryProposalService(id_factory=IdSequence(), clock=fixed_clock)
    job = LangMemProposalJob(
        extractor=FakeExtractor(
            candidates=[
                ExtractedMemoryCandidate(
                    content="User prefers Korean updates.",
                    confidence=0.8,
                    source_payload={"run_id": "run_1"},
                )
            ]
        ),
        proposal_service=service,
    )

    proposals = await job.propose_from_text(
        namespace=memory_namespace(),
        text="Please keep status updates in Korean.",
    )

    assert len(proposals) == 1
    assert proposals[0].status == "proposed"
    assert proposals[0].proposed_content == "User prefers Korean updates."
    assert proposals[0].extraction_model == "langmem"
    assert proposals[0].source_payload == {"run_id": "run_1"}


async def test_langmem_extractor_uses_langmem_memory_manager_shape() -> None:
    manager = FakeLangMemManager(
        [
            FakeLangMemResult(
                id="memory_1",
                content=FakeLangMemContent("User prefers Korean updates."),
            )
        ]
    )
    extractor = LangMemMemoryExtractor(
        "openai:gpt-5.2-mini",
        manager=manager,
        default_confidence=0.7,
        max_candidates=3,
    )

    candidates = await extractor.extract("Please keep status updates in Korean.")

    assert manager.inputs == [
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Please keep status updates in Korean.",
                }
            ],
            "max_steps": 1,
        }
    ]
    assert candidates == [
        ExtractedMemoryCandidate(
            content="User prefers Korean updates.",
            confidence=0.7,
            source_payload={
                "extractor": "langmem",
                "langmem_manager_contract": {
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
                    "max_candidates": 3,
                    "candidate_overflow_policy": "reject_all",
                },
                "langmem_memory_id": "memory_1",
                "langmem_content": {"content": "User prefers Korean updates."},
            },
        )
    ]


async def test_langmem_extractor_rejects_missing_sdk_memory_id() -> None:
    manager = FakeLangMemManager(
        [
            ExtractedMemory(
                id=" ",
                content=Memory(content="User prefers Korean updates."),
            )
        ]
    )
    extractor = LangMemMemoryExtractor(
        "openai:gpt-5.2-mini",
        manager=manager,
    )

    with pytest.raises(ValueError, match="LangMem memory id is required"):
        await extractor.extract("Please keep status updates in Korean.")


async def test_langmem_extractor_rejects_blank_sdk_memory_content() -> None:
    manager = FakeLangMemManager(
        [
            ExtractedMemory(
                id="memory_1",
                content=Memory(content=" "),
            )
        ]
    )
    extractor = LangMemMemoryExtractor(
        "openai:gpt-5.2-mini",
        manager=manager,
    )

    with pytest.raises(ValueError, match="LangMem memory content is required"):
        await extractor.extract("Please keep status updates in Korean.")


async def test_langmem_extractor_rejects_candidate_count_over_budget() -> None:
    manager = FakeLangMemManager(
        [
            ExtractedMemory(
                id=f"memory_{index}",
                content=Memory(content=f"Memory {index}."),
            )
            for index in range(1, 4)
        ]
    )
    extractor = LangMemMemoryExtractor(
        "openai:gpt-5.2-mini",
        manager=manager,
        max_candidates=2,
    )

    with pytest.raises(ValueError, match="LangMem extraction exceeded candidate limit"):
        await extractor.extract("Remember these facts.")


def memory_namespace() -> MemoryNamespaceKey:
    return MemoryNamespaceKey(
        tenant_id="tenant_1",
        subject_type="user",
        subject_id="user_1",
        memory_type="semantic",
        visibility="user",
    )


def fixed_clock() -> datetime:
    return datetime(2026, 6, 26, tzinfo=UTC)


class IdSequence:
    def __init__(self) -> None:
        self._next = 1

    def __call__(self) -> str:
        value = f"id_{self._next}"
        self._next += 1
        return value


class FakeExtractor:
    def __init__(self, candidates: list[ExtractedMemoryCandidate]) -> None:
        self._candidates = candidates

    async def extract(self, text: str) -> list[ExtractedMemoryCandidate]:
        if not text.strip():
            raise ValueError("text is required")
        return self._candidates


@dataclass(frozen=True)
class FakeLangMemContent:
    content: str

    def model_dump(self, *, mode: str) -> dict[str, str]:
        assert mode == "json"
        return {"content": self.content}


@dataclass(frozen=True)
class FakeLangMemResult:
    id: str
    content: FakeLangMemContent


class FakeLangMemManager:
    def __init__(self, results: list[object]) -> None:
        self._results = results
        self.inputs: list[object] = []

    async def ainvoke(self, input_payload: object) -> list[object]:
        self.inputs.append(input_payload)
        return self._results
