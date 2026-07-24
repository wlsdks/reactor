from __future__ import annotations

from datetime import UTC, datetime

from reactor.memory.policy import MemoryNamespaceKey
from reactor.memory.service import (
    MemoryItemRecord,
    MemoryProposalRecord,
    MemoryTombstoneResult,
)
from reactor.persistence.memory_store import (
    build_active_memory_items_query,
    build_memory_embedding_delete,
    build_memory_item_insert,
    build_memory_namespace_insert,
    build_memory_namespace_lookup,
    build_memory_proposal_insert,
    build_memory_proposal_status_update,
    build_memory_supersede_update,
    build_memory_tombstone_update,
    require_memory_rows_changed,
)
from reactor.persistence.repositories.rag_postgres import compile_postgres_sql


def test_memory_namespace_insert_uses_identity_conflict_constraint() -> None:
    statement = build_memory_namespace_insert(memory_namespace(), "namespace_1")
    sql = compile_postgres_sql(statement)

    assert "INSERT INTO memory_namespaces" in sql
    assert "ON CONFLICT ON CONSTRAINT uq_memory_namespaces_identity DO NOTHING" in sql
    assert "RETURNING memory_namespaces.id" in sql


def test_memory_namespace_lookup_filters_full_namespace_identity() -> None:
    statement = build_memory_namespace_lookup(memory_namespace())
    compiled = statement.compile()
    sql = str(compiled)

    assert "memory_namespaces.tenant_id =" in sql
    assert "memory_namespaces.subject_type =" in sql
    assert "memory_namespaces.subject_id =" in sql
    assert "memory_namespaces.memory_type =" in sql
    assert "memory_namespaces.visibility =" in sql
    assert compiled.params["tenant_id_1"] == "tenant_1"
    assert compiled.params["subject_id_1"] == "user_1"


def test_memory_proposal_insert_preserves_extraction_metadata() -> None:
    statement = build_memory_proposal_insert(memory_proposal(), namespace_id="namespace_1")
    compiled = statement.compile()

    assert "memory_proposals" in str(compiled)
    assert compiled.params["id"] == "proposal_1"
    assert compiled.params["status"] == "proposed"
    assert compiled.params["extraction_model"] == "langmem"
    assert compiled.params["source_payload"] == {"run_id": "run_1"}


def test_memory_promotion_updates_proposal_and_inserts_active_item() -> None:
    proposal_statement = build_memory_proposal_status_update(approved_memory_proposal())
    item_statement = build_memory_item_insert(memory_item(), namespace_id="namespace_1")

    proposal_sql = str(proposal_statement.compile())
    item_compiled = item_statement.compile()

    assert "UPDATE memory_proposals" in proposal_sql
    assert "memory_proposals.status =" in proposal_sql
    assert item_compiled.params["id"] == "memory_1"
    assert item_compiled.params["status"] == "active"
    assert item_compiled.params["metadata"] == {"proposal_id": "proposal_1"}


def test_memory_tombstone_updates_item_and_deletes_embedding() -> None:
    tombstoned_item = tombstoned_memory_item()
    update_statement = build_memory_tombstone_update(tombstoned_item)
    delete_statement = build_memory_embedding_delete(memory_id="memory_1", tenant_id="tenant_1")

    update_sql = str(update_statement.compile())
    delete_sql = str(delete_statement.compile())

    assert "UPDATE memory_items" in update_sql
    assert "memory_items.status =" in update_sql
    assert "DELETE FROM memory_embeddings" in delete_sql
    assert "memory_embeddings.memory_id =" in delete_sql


def test_memory_supersede_update_filters_active_tenant_memory() -> None:
    superseded_item = superseded_memory_item()
    statement = build_memory_supersede_update(superseded_item)
    compiled = statement.compile()
    sql = str(compiled)

    assert "UPDATE memory_items" in sql
    assert "memory_items.id =" in sql
    assert "memory_items.tenant_id =" in sql
    assert "memory_items.status =" in sql
    assert compiled.params["id_1"] == "memory_old"
    assert compiled.params["tenant_id_1"] == "tenant_1"
    assert compiled.params["status_1"] == "active"
    assert compiled.params["status"] == "superseded"
    assert compiled.params["metadata"]["superseded_by_proposal_id"] == "proposal_2"


def test_memory_supersede_update_requires_matching_active_row() -> None:
    result = FakeRowResult(rowcount=0)

    try:
        require_memory_rows_changed(result, action="supersede active memory")
    except RuntimeError as error:
        assert str(error) == "supersede active memory did not update any memory rows"
    else:
        raise AssertionError("expected stale supersede update to fail closed")


def test_memory_tombstone_result_declares_embedding_delete_intent() -> None:
    result = MemoryTombstoneResult(item=memory_item(), delete_embedding=True)

    assert result.delete_embedding is True


def test_active_memory_items_query_filters_namespace_tenant_and_status() -> None:
    statement = build_active_memory_items_query(
        namespace_id="namespace_1",
        tenant_id="tenant_1",
        limit=5,
    )
    compiled = statement.compile()
    sql = str(compiled)

    assert "FROM memory_items" in sql
    assert "memory_items.namespace_id =" in sql
    assert "memory_items.tenant_id =" in sql
    assert "memory_items.status =" in sql
    assert "memory_items.created_at DESC" in sql
    assert compiled.params["namespace_id_1"] == "namespace_1"
    assert compiled.params["tenant_id_1"] == "tenant_1"
    assert compiled.params["status_1"] == "active"
    assert 5 in compiled.params.values()


def memory_namespace() -> MemoryNamespaceKey:
    return MemoryNamespaceKey(
        tenant_id="tenant_1",
        subject_type="user",
        subject_id="user_1",
        memory_type="semantic",
        visibility="user",
    )


def memory_proposal() -> MemoryProposalRecord:
    return MemoryProposalRecord(
        id="proposal_1",
        tenant_id="tenant_1",
        namespace=memory_namespace(),
        status="proposed",
        proposed_content="User prefers concise Korean updates.",
        extraction_model="langmem",
        extraction_prompt_version="memory-v1",
        confidence=0.8,
        source_payload={"run_id": "run_1"},
        decision_reason=None,
        created_at=fixed_clock(),
    )


def approved_memory_proposal() -> MemoryProposalRecord:
    return MemoryProposalRecord(
        id="proposal_1",
        tenant_id="tenant_1",
        namespace=memory_namespace(),
        status="approved",
        proposed_content="User prefers concise Korean updates.",
        extraction_model="langmem",
        extraction_prompt_version="memory-v1",
        confidence=0.8,
        source_payload={"run_id": "run_1"},
        decision_reason="stable preference",
        created_at=fixed_clock(),
    )


def memory_item() -> MemoryItemRecord:
    return MemoryItemRecord(
        id="memory_1",
        tenant_id="tenant_1",
        namespace=memory_namespace(),
        status="active",
        content="User prefers concise Korean updates.",
        source_id="proposal_1",
        confidence=0.8,
        metadata={"proposal_id": "proposal_1"},
        created_at=fixed_clock(),
    )


def tombstoned_memory_item() -> MemoryItemRecord:
    return MemoryItemRecord(
        id="memory_1",
        tenant_id="tenant_1",
        namespace=memory_namespace(),
        status="tombstoned",
        content="User prefers concise Korean updates.",
        source_id="proposal_1",
        confidence=0.8,
        metadata={"tombstone_reason": "user requested deletion"},
        created_at=fixed_clock(),
    )


def superseded_memory_item() -> MemoryItemRecord:
    return MemoryItemRecord(
        id="memory_old",
        tenant_id="tenant_1",
        namespace=memory_namespace(),
        status="superseded",
        content="User prefers short updates.",
        source_id="proposal_1",
        confidence=0.8,
        metadata={"superseded_by_proposal_id": "proposal_2"},
        created_at=fixed_clock(),
    )


def fixed_clock() -> datetime:
    return datetime(2026, 6, 26, tzinfo=UTC)


class FakeRowResult:
    def __init__(self, *, rowcount: int) -> None:
        self.rowcount = rowcount
