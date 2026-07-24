from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from pytest import MonkeyPatch

from reactor.admin.audit import AdminAuditAction, AdminAuditLog
from reactor.admin.tenants import TenantRecord, TenantStatus
from reactor.agents.graph import build_reactor_graph
from reactor.agents.runtime_config import langgraph_durable_config
from reactor.agents.state import ReactorState
from reactor.api.app import create_app
from reactor.api.routers import admin as admin_router
from reactor.auth.models import UserRecord
from reactor.auth.rbac import UserRole
from reactor.core.settings import Settings
from reactor.evals.models import AgentEvalStoredResultRecord
from reactor.memory.lifecycle_actions import MEMORY_LIFECYCLE_GATE_ACTION
from reactor.memory.policy import MemoryNamespaceKey
from reactor.memory.service import MemoryItemRecord, MemoryPromotionResult, MemoryProposalRecord
from reactor.observability.alerts import (
    AlertInstance,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    InMemoryAlertRuleStore,
)
from reactor.observability.pricing import ModelPricing
from reactor.observability.usage_ledger import InMemoryUsageLedger, UsageLedgerRecord
from reactor.persistence.rag_ingest_store import (
    RagChunkMigrationRecord,
    RagDocumentMigrationRecord,
    RagSourceMigrationRecord,
    RagStatsRecord,
)
from reactor.persistence.run_store import RunEventRecord, SessionListRecord, SessionRunRecord
from reactor.persistence.tool_invocation_store import ToolInvocationRecord
from reactor.release.readiness import current_git_commit
from reactor.runtime_settings.service import RuntimeSettingRecord, RuntimeSettingUpdate
from reactor.scheduler.service import (
    JobExecutionStatus,
    ScheduledJobExecutionRecord,
    ScheduledJobRecord,
    ScheduledJobType,
)


async def test_admin_openapi_names_memory_next_action_contract() -> None:
    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    schemas = response.json()["components"]["schemas"]
    assert schemas["MemoryNextAction"]["required"] == ["id", "label", "command"]
    assert schemas["MemoryNextAction"]["properties"]["id"]["type"] == "string"
    assert schemas["MemoryNextAction"]["properties"]["label"]["type"] == "string"
    assert schemas["MemoryNextAction"]["properties"]["command"]["type"] == "string"
    for field in [
        "preflightFile",
        "preflightEnvTemplate",
        "replatformReadinessFile",
        "smokePlanFile",
        "releaseEvidenceFile",
        "releaseReadinessFile",
        "readinessReportArg",
    ]:
        assert schemas["MemoryNextAction"]["properties"][field] == {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "".join(part.capitalize() for part in field.split("_")),
        }
    assert schemas["MemoryNextAction"]["properties"]["requiredReadinessReports"] == {
        "anyOf": [
            {"items": {"type": "string"}, "type": "array"},
            {"type": "null"},
        ],
        "title": "Requiredreadinessreports",
    }
    assert schemas["MemoryNextAction"]["properties"]["readinessReports"] == {
        "anyOf": [
            {"additionalProperties": {"type": "string"}, "type": "object"},
            {"type": "null"},
        ],
        "title": "Readinessreports",
    }
    review_queue_item = schemas["MemoryProposalReviewQueueItemResponse"]
    assert review_queue_item["properties"]["nextActions"]["items"] == {
        "$ref": "#/components/schemas/MemoryNextAction"
    }
    approval_response = schemas["MemoryProposalApprovalResponse"]
    assert approval_response["properties"]["nextActions"]["items"] == {
        "$ref": "#/components/schemas/MemoryNextAction"
    }


ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}

MANAGER_HEADERS = {
    "X-Reactor-User-Id": "manager_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN_MANAGER",
}

USER_HEADERS = {
    "X-Reactor-User-Id": "user_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "USER",
}

EMPTY_MEMORY_NEXT_ACTION_ARTIFACTS = {
    "preflightFile": None,
    "preflightEnvTemplate": None,
    "replatformReadinessFile": None,
    "smokePlanFile": None,
    "releaseEvidenceFile": None,
    "releaseReadinessFile": None,
    "readinessReportArg": None,
    "requiredReadinessReports": None,
    "readinessReports": None,
}

MEMORY_LIFECYCLE_NEXT_ACTION_ARTIFACTS = {
    "preflightFile": "reports/release/release-smoke-preflight.local.json",
    "preflightEnvTemplate": "reports/release/release-smoke-preflight.local.env",
    "replatformReadinessFile": "reports/release/replatform-readiness.local.json",
    "smokePlanFile": "reports/release/release-smoke-plan.local.json",
    "releaseEvidenceFile": "reports/release-evidence.json",
    "releaseReadinessFile": "reports/release-readiness.json",
    "readinessReportArg": "--readiness-report hardening_suite=reports/hardening-suite.json",
    "requiredReadinessReports": ["hardening_suite"],
    "readinessReports": {"hardening_suite": "reports/hardening-suite.json"},
}
TEST_AUTH_DIGEST = "test-auth-digest"


async def test_admin_capabilities_manifest_keeps_legacy_and_v1_paths() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/v1/admin/capabilities", headers=USER_HEADERS)
        response = await client.get("/api/admin/capabilities", headers=MANAGER_HEADERS)

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "admin access required"
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "fastapi-routes"
    assert body["durable"] is False
    assert "/api/admin/capabilities" in body["paths"]
    assert "/v1/admin/capabilities" in body["paths"]
    assert "/api/chat" in body["paths"]
    assert body["paths"] == sorted(body["paths"])


async def test_admin_memory_proposals_lists_review_queue_without_source_payload() -> None:
    store = FakeMemoryProposalStore(
        [
            MemoryProposalRecord(
                id="proposal_1",
                tenant_id="tenant_1",
                namespace=MemoryNamespaceKey(
                    tenant_id="tenant_1",
                    subject_type="user",
                    subject_id="user_1",
                    memory_type="semantic",
                    visibility="user",
                ),
                status="proposed",
                proposed_content="User prefers concise Korean updates.",
                extraction_model="langmem",
                extraction_prompt_version="memory-v1",
                confidence=0.82,
                source_payload={
                    "run_id": "run_1",
                    "raw": "do not expose",
                    "sensitivity": {
                        "status": "flagged",
                        "policy": "reject_or_redact_before_promotion",
                        "markers": ["api_key", "secret"],
                        "source": "content_or_source_payload",
                    },
                    "langmem_manager_contract": {
                        "factory": "langmem.create_memory_manager",
                        "invoke_api": "ainvoke",
                        "input_messages_key": "messages",
                        "max_steps": 1,
                        "enable_deletes": False,
                        "application_owns_deletes": True,
                        "storeFactory": "langmem.create_memory_store_manager",
                    },
                },
                decision_reason=None,
                created_at=datetime(2026, 7, 2, 0, 0, tzinfo=UTC),
            ),
            MemoryProposalRecord(
                id="proposal_2",
                tenant_id="tenant_1",
                namespace=MemoryNamespaceKey(
                    tenant_id="tenant_1",
                    subject_type="user",
                    subject_id="user_2",
                    memory_type="semantic",
                    visibility="user",
                ),
                status="approved",
                proposed_content="Already reviewed.",
                extraction_model="langmem",
                extraction_prompt_version="memory-v1",
                confidence=0.9,
                source_payload={"run_id": "run_2"},
                decision_reason="approved",
                created_at=datetime(2026, 7, 2, 0, 1, tzinfo=UTC),
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(memory_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/memory/proposals", headers=USER_HEADERS)
        response = await client.get("/api/admin/memory/proposals", headers=MANAGER_HEADERS)

    assert forbidden.status_code == 403
    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": "proposal_1",
                "tenantId": "tenant_1",
                "status": "proposed",
                "proposedContent": "User prefers concise Korean updates.",
                "subjectType": "user",
                "subjectId": "user_1",
                "memoryType": "semantic",
                "visibility": "user",
                "extractionModel": "langmem",
                "extractionPromptVersion": "memory-v1",
                "confidence": 0.82,
                "decisionReason": None,
                "maintenance": {
                    "manager": "create_memory_manager",
                    "storeManager": "create_memory_store_manager",
                    "operation": "ainvoke",
                    "maxSteps": 1,
                    "deletePolicy": "reactor_owned",
                    "dependencyReviewCommand": "uv pip show langmem trustcall langgraph",
                    "dependencyRemediationCommand": (
                        "monitor upstream trustcall/langmem compatibility; keep "
                        "dependency warning visible until "
                        "trustcall stops importing langgraph.constants.Send or "
                        "Reactor replaces the dependency path"
                    ),
                    "sensitivity": {
                        "status": "flagged",
                        "policy": "reject_or_redact_before_promotion",
                        "markers": ["api_key", "secret"],
                        "source": "content_or_source_payload",
                    },
                },
                "nextAction": ("reactor-memory get --target-user-id user_1 --output table"),
                "nextActions": [
                    {
                        "id": "inspect-memory",
                        "label": "Inspect this user's active memory before review",
                        "command": "reactor-memory get --target-user-id user_1 --output table",
                        **EMPTY_MEMORY_NEXT_ACTION_ARTIFACTS,
                    },
                    {
                        "id": "approve-memory",
                        "label": "Approve this proposed memory",
                        "command": (
                            "reactor-memory approve proposal_1 "
                            "--reason 'reviewed and approved memory' --output table"
                        ),
                        **EMPTY_MEMORY_NEXT_ACTION_ARTIFACTS,
                    },
                    {
                        "id": "reject-memory",
                        "label": "Reject this proposed memory",
                        "command": (
                            "reactor-memory reject proposal_1 "
                            "--reason 'sensitive or inaccurate memory' --output table"
                        ),
                        **EMPTY_MEMORY_NEXT_ACTION_ARTIFACTS,
                    },
                    {
                        "id": "review-memory-dependencies",
                        "label": "Review LangMem dependency compatibility before memory release",
                        "command": "uv pip show langmem trustcall langgraph",
                        **EMPTY_MEMORY_NEXT_ACTION_ARTIFACTS,
                    },
                    {
                        "id": "verify-memory-lifecycle",
                        "label": "Verify memory lifecycle hardening before closing the review",
                        **MEMORY_LIFECYCLE_NEXT_ACTION_ARTIFACTS,
                        "command": MEMORY_LIFECYCLE_GATE_ACTION,
                    },
                ],
                "createdAt": "2026-07-02T00:00:00+00:00",
            }
        ],
        "count": 1,
        "status": "proposed",
        "subjectIdFilter": None,
    }


async def test_admin_memory_proposals_can_filter_review_queue_by_subject_id() -> None:
    store = FakeMemoryProposalStore(
        [
            MemoryProposalRecord(
                id="proposal_1",
                tenant_id="tenant_1",
                namespace=MemoryNamespaceKey(
                    tenant_id="tenant_1",
                    subject_type="user",
                    subject_id="user_1",
                    memory_type="semantic",
                    visibility="user",
                ),
                status="proposed",
                proposed_content="User prefers concise Korean updates.",
                extraction_model="langmem",
                extraction_prompt_version="memory-v1",
                confidence=0.82,
                source_payload={"run_id": "run_1"},
                decision_reason=None,
                created_at=datetime(2026, 7, 2, 0, 0, tzinfo=UTC),
            ),
            MemoryProposalRecord(
                id="proposal_2",
                tenant_id="tenant_1",
                namespace=MemoryNamespaceKey(
                    tenant_id="tenant_1",
                    subject_type="user",
                    subject_id="user_2",
                    memory_type="semantic",
                    visibility="user",
                ),
                status="proposed",
                proposed_content="User prefers verbose English updates.",
                extraction_model="langmem",
                extraction_prompt_version="memory-v1",
                confidence=0.79,
                source_payload={"run_id": "run_2"},
                decision_reason=None,
                created_at=datetime(2026, 7, 2, 0, 1, tzinfo=UTC),
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(memory_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/admin/memory/proposals?status=proposed&subject_id=user_1",
            headers=MANAGER_HEADERS,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["subjectIdFilter"] == "user_1"
    assert body["items"][0]["id"] == "proposal_1"
    assert body["items"][0]["subjectId"] == "user_1"


async def test_admin_memory_proposal_approve_promotes_active_item() -> None:
    proposal = MemoryProposalRecord(
        id="proposal_1",
        tenant_id="tenant_1",
        namespace=MemoryNamespaceKey(
            tenant_id="tenant_1",
            subject_type="user",
            subject_id="user_1",
            memory_type="semantic",
            visibility="user",
        ),
        status="proposed",
        proposed_content="User prefers concise Korean updates.",
        extraction_model="langmem",
        extraction_prompt_version="memory-v1",
        confidence=0.82,
        source_payload={
            "run_id": "run_1",
            "raw": "do not expose",
            "langmem_manager_contract": {
                "factory": "langmem.create_memory_manager",
                "storeFactory": "langmem.create_memory_store_manager",
                "invoke_api": "ainvoke",
                "max_steps": 1,
                "enable_deletes": False,
                "application_owns_deletes": True,
            },
        },
        decision_reason=None,
        created_at=datetime(2026, 7, 2, 0, 0, tzinfo=UTC),
    )
    store = FakeMemoryProposalStore([proposal])
    app = create_app()
    app.state.reactor = FakeContainer(memory_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.post(
            "/api/admin/memory/proposals/proposal_1/approve",
            headers=USER_HEADERS,
            json={"reason": "stable preference"},
        )
        response = await client.post(
            "/api/admin/memory/proposals/proposal_1/approve",
            headers=MANAGER_HEADERS,
            json={"reason": "stable preference"},
        )

    assert forbidden.status_code == 403
    assert response.status_code == 200
    body = response.json()
    assert "sourcePayload" not in body
    item_id = body["item"]["id"]
    assert isinstance(item_id, str) and item_id
    assert body == {
        "proposal": {
            "id": "proposal_1",
            "tenantId": "tenant_1",
            "status": "approved",
            "proposedContent": "User prefers concise Korean updates.",
            "subjectType": "user",
            "subjectId": "user_1",
            "memoryType": "semantic",
            "visibility": "user",
            "extractionModel": "langmem",
            "extractionPromptVersion": "memory-v1",
            "confidence": 0.82,
            "decisionReason": "stable preference",
            "createdAt": "2026-07-02T00:00:00+00:00",
        },
        "item": {
            "id": item_id,
            "tenantId": "tenant_1",
            "status": "active",
            "content": "User prefers concise Korean updates.",
            "sourceId": "proposal_1",
            "subjectType": "user",
            "subjectId": "user_1",
            "memoryType": "semantic",
            "visibility": "user",
            "confidence": 0.82,
        },
        "supersededItems": [],
        "maintenance": {
            "manager": "create_memory_manager",
            "storeManager": "create_memory_store_manager",
            "operation": "ainvoke",
            "maxSteps": 1,
            "deletePolicy": "reactor_owned",
            "dependencyReviewCommand": "uv pip show langmem trustcall langgraph",
            "dependencyRemediationCommand": (
                "monitor upstream trustcall/langmem compatibility; keep "
                "dependency warning visible until "
                "trustcall stops importing langgraph.constants.Send or "
                "Reactor replaces the dependency path"
            ),
            "sensitivity": None,
        },
        "nextAction": "reactor-memory get --target-user-id user_1 --output table",
        "nextActions": [
            {
                "id": "inspect-memory",
                "label": "Inspect the approved user's active memory",
                "command": "reactor-memory get --target-user-id user_1 --output table",
                **EMPTY_MEMORY_NEXT_ACTION_ARTIFACTS,
            },
            {
                "id": "review-proposals",
                "label": "Review remaining proposed memories for this user",
                "command": (
                    "reactor-memory proposals --status proposed --subject-id user_1 --output table"
                ),
                **EMPTY_MEMORY_NEXT_ACTION_ARTIFACTS,
            },
            {
                "id": "review-memory-dependencies",
                "label": "Review LangMem dependency compatibility before memory release",
                "command": "uv pip show langmem trustcall langgraph",
                **EMPTY_MEMORY_NEXT_ACTION_ARTIFACTS,
            },
            {
                "id": "verify-memory-lifecycle",
                "label": "Verify memory lifecycle hardening before closing the review",
                **MEMORY_LIFECYCLE_NEXT_ACTION_ARTIFACTS,
                "command": MEMORY_LIFECYCLE_GATE_ACTION,
            },
        ],
    }
    assert "VERIFY_TIMESTAMP" not in body["nextAction"]
    assert "VERIFY_TIMESTAMP" not in str(body["nextActions"])
    assert store.saved_promotions


async def test_admin_memory_proposal_approve_can_supersede_prior_active_memory() -> None:
    namespace = MemoryNamespaceKey(
        tenant_id="tenant_1",
        subject_type="user",
        subject_id="user_1",
        memory_type="semantic",
        visibility="user",
    )
    proposal = MemoryProposalRecord(
        id="proposal_1",
        tenant_id="tenant_1",
        namespace=namespace,
        status="proposed",
        proposed_content="User prefers detailed English updates.",
        extraction_model="langmem",
        extraction_prompt_version="memory-v1",
        confidence=0.88,
        source_payload={"run_id": "run_2"},
        decision_reason=None,
        created_at=datetime(2026, 7, 2, 0, 0, tzinfo=UTC),
    )
    prior_item = MemoryItemRecord(
        id="memory_old",
        tenant_id="tenant_1",
        namespace=namespace,
        status="active",
        content="User prefers concise Korean updates.",
        source_id="proposal_old",
        confidence=0.8,
        metadata={"proposal_id": "proposal_old"},
        created_at=datetime(2026, 7, 1, 0, 0, tzinfo=UTC),
    )
    store = FakeMemoryProposalStore([proposal], items=[prior_item])
    app = create_app()
    app.state.reactor = FakeContainer(memory_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/admin/memory/proposals/proposal_1/approve",
            headers=MANAGER_HEADERS,
            json={
                "reason": "newer reviewed preference",
                "supersedesMemoryId": "memory_old",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["item"]["status"] == "active"
    assert body["supersededItems"] == [
        {
            "id": "memory_old",
            "tenantId": "tenant_1",
            "status": "superseded",
            "content": "User prefers concise Korean updates.",
            "sourceId": "proposal_old",
            "subjectType": "user",
            "subjectId": "user_1",
            "memoryType": "semantic",
            "visibility": "user",
            "confidence": 0.8,
        }
    ]
    promotion = store.saved_promotions[-1]
    assert promotion.item.metadata["supersedes_memory_id"] == "memory_old"
    assert promotion.superseded_items[0].metadata["superseded_by_proposal_id"] == "proposal_1"
    assert promotion.superseded_items[0].metadata["superseded_reason"] == (
        "newer reviewed preference"
    )
    assert body["nextAction"] == "reactor-memory get --target-user-id user_1 --output table"
    next_actions = {action["id"]: action["command"] for action in body["nextActions"]}
    assert next_actions["verify-superseded-exclusion"] == (
        "uv run pytest tests/unit/test_prompt_assembler.py -q -k excludes_superseded_memory"
    )
    assert next_actions["verify-memory-lifecycle"] == MEMORY_LIFECYCLE_GATE_ACTION
    assert store.saved_promotions[0].proposal.status == "approved"
    assert store.saved_promotions[0].item.status == "active"
    assert store.saved_promotions[0].item.id == body["item"]["id"]


async def test_admin_memory_proposal_approve_requires_supersession_store_contract() -> None:
    proposal = MemoryProposalRecord(
        id="proposal_1",
        tenant_id="tenant_1",
        namespace=MemoryNamespaceKey(
            tenant_id="tenant_1",
            subject_type="user",
            subject_id="user_1",
            memory_type="semantic",
            visibility="user",
        ),
        status="proposed",
        proposed_content="User prefers detailed English updates.",
        extraction_model="langmem",
        extraction_prompt_version="memory-v1",
        confidence=0.88,
        source_payload={"run_id": "run_2"},
        decision_reason=None,
        created_at=datetime(2026, 7, 2, 0, 0, tzinfo=UTC),
    )
    store = FakeMemoryProposalStoreWithoutItemLookup([proposal])
    app = create_app()
    app.state.reactor = FakeContainer(memory_store=store)
    transport = ASGITransport(app=app, raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/admin/memory/proposals/proposal_1/approve",
            headers=MANAGER_HEADERS,
            json={
                "reason": "newer reviewed preference",
                "supersedesMemoryId": "memory_old",
            },
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "memory proposal review persistence is not configured"}
    assert store.saved_promotions == []


async def test_admin_memory_proposal_approve_sensitive_block_returns_recovery_actions() -> None:
    proposal = MemoryProposalRecord(
        id="proposal_1",
        tenant_id="tenant_1",
        namespace=MemoryNamespaceKey(
            tenant_id="tenant_1",
            subject_type="user",
            subject_id="user_1",
            memory_type="semantic",
            visibility="user",
        ),
        status="proposed",
        proposed_content="User prefers concise Korean updates.",
        extraction_model="langmem",
        extraction_prompt_version="memory-v1",
        confidence=0.82,
        source_payload={
            "run_id": "run_1",
            "raw": "do not expose",
            "sensitivity": {
                "status": "flagged",
                "policy": "reject_or_redact_before_promotion",
                "markers": ["api_key"],
            },
        },
        decision_reason=None,
        created_at=datetime(2026, 7, 2, 0, 0, tzinfo=UTC),
    )
    store = FakeMemoryProposalStore([proposal])
    app = create_app()
    app.state.reactor = FakeContainer(memory_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/admin/memory/proposals/proposal_1/approve",
            headers=MANAGER_HEADERS,
            json={"reason": "stable preference"},
        )

    assert response.status_code == 400
    assert response.json() == {
        "detail": {
            "reason": "sensitive_memory_requires_rejection_or_redaction",
            "message": "sensitive memory proposals require rejection or redaction",
            "proposalId": "proposal_1",
            "sensitivity": {
                "status": "flagged",
                "policy": "reject_or_redact_before_promotion",
                "markers": ["api_key"],
                "source": None,
            },
            "rejectAction": (
                "reactor-memory reject proposal_1 "
                "--reason 'sensitive or inaccurate memory' --output table"
            ),
            "reviewQueueAction": (
                "reactor-memory proposals --status proposed --subject-id user_1 --output table"
            ),
            "nextActions": [
                {
                    "id": "reject-memory",
                    "label": "Reject this sensitive memory proposal",
                    "command": (
                        "reactor-memory reject proposal_1 "
                        "--reason 'sensitive or inaccurate memory' --output table"
                    ),
                    **EMPTY_MEMORY_NEXT_ACTION_ARTIFACTS,
                },
                {
                    "id": "review-proposals",
                    "label": "Review remaining proposed memories for this user",
                    "command": (
                        "reactor-memory proposals --status proposed "
                        "--subject-id user_1 --output table"
                    ),
                    **EMPTY_MEMORY_NEXT_ACTION_ARTIFACTS,
                },
                {
                    "id": "verify-memory-lifecycle",
                    "label": "Verify memory lifecycle hardening before closing the review",
                    **MEMORY_LIFECYCLE_NEXT_ACTION_ARTIFACTS,
                    "command": MEMORY_LIFECYCLE_GATE_ACTION,
                },
            ],
        }
    }
    assert "sourcePayload" not in str(response.json())
    assert "do not expose" not in str(response.json())
    assert store.saved_promotions == []


async def test_admin_memory_proposal_reject_marks_reviewed_without_source_payload() -> None:
    proposal = MemoryProposalRecord(
        id="proposal_1",
        tenant_id="tenant_1",
        namespace=MemoryNamespaceKey(
            tenant_id="tenant_1",
            subject_type="user",
            subject_id="user_1",
            memory_type="semantic",
            visibility="user",
        ),
        status="proposed",
        proposed_content="User prefers concise Korean updates.",
        extraction_model="langmem",
        extraction_prompt_version="memory-v1",
        confidence=0.82,
        source_payload={"run_id": "run_1", "raw": "do not expose"},
        decision_reason=None,
        created_at=datetime(2026, 7, 2, 0, 0, tzinfo=UTC),
    )
    store = FakeMemoryProposalStore([proposal])
    app = create_app()
    app.state.reactor = FakeContainer(memory_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.post(
            "/api/admin/memory/proposals/proposal_1/reject",
            headers=USER_HEADERS,
            json={"reason": "not stable enough"},
        )
        response = await client.post(
            "/api/admin/memory/proposals/proposal_1/reject",
            headers=MANAGER_HEADERS,
            json={"reason": "not stable enough"},
        )

    assert forbidden.status_code == 403
    assert response.status_code == 200
    body = response.json()
    assert "sourcePayload" not in body
    assert body == {
        "id": "proposal_1",
        "tenantId": "tenant_1",
        "status": "rejected",
        "proposedContent": "User prefers concise Korean updates.",
        "subjectType": "user",
        "subjectId": "user_1",
        "memoryType": "semantic",
        "visibility": "user",
        "extractionModel": "langmem",
        "extractionPromptVersion": "memory-v1",
        "confidence": 0.82,
        "decisionReason": "not stable enough reviewer=manager_1",
        "createdAt": "2026-07-02T00:00:00+00:00",
    }
    assert store.saved_rejections
    assert store.saved_rejections[0].status == "rejected"
    assert store.proposals[0].status == "rejected"


async def test_admin_doctor_ports_legacy_report_and_summary_content_negotiation() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(
        runtime_settings_store=FakeRuntimeSettingsStore(),
        rag_document_sink=FakeRagDocumentSink(
            [
                RagStatsRecord(
                    collection="docs",
                    source_count=1,
                    document_count=2,
                    chunk_count=4,
                    embedded_chunk_count=3,
                )
            ]
        ),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/doctor", headers=USER_HEADERS)
        report = await client.get("/api/admin/doctor", headers=MANAGER_HEADERS)
        summary = await client.get(
            "/v1/admin/doctor/summary",
            headers={**MANAGER_HEADERS, "Accept": "text/plain"},
        )

    assert forbidden.status_code == 403
    assert report.status_code == 200
    assert report.headers["x-doctor-status"] == "OK"
    body = report.json()
    assert body["status"] == "OK"
    assert body["allHealthy"] is True
    assert [section["name"] for section in body["sections"]] == [
        "FastAPI Runtime",
        "Runtime Settings",
        "RAG Store",
    ]
    assert body["sections"][2]["checks"][0]["detail"] == "documents=2, chunks=4"
    assert summary.status_code == 200
    assert summary.headers["x-doctor-status"] == "OK"
    assert summary.headers["content-type"].startswith("text/plain")
    assert "OK" in summary.text
    assert "3 sections" in summary.text


async def test_admin_observability_smoke_diagnostics_exposes_secret_free_target() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(
        settings=Settings(
            observability_trace_exporter="langsmith",
            observability_langsmith_project="reactor-prod",
            observability_langsmith_endpoint="https://api.smith.langchain.com",
            observability_langsmith_api_key="lsv2_secret_value",
        )
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get(
            "/v1/admin/observability/smoke/diagnostics",
            headers=USER_HEADERS,
        )
        response = await client.get(
            "/v1/admin/observability/smoke/diagnostics",
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["status"] == "ready"
    assert body["scope"] == "local_contract_diagnostics"
    assert body["evidence"]["observabilityTarget"] == {
        "traceProvider": "langsmith",
        "project": "reactor-prod",
        "endpoint": "https://api.smith.langchain.com",
        "spanName": "reactor.release.observability_smoke",
        "secretFree": True,
    }
    assert body["evidence"]["privacy"]["redactionCoverage"] == [
        "reactor.api_key",
        "reactor.payload.password",
        "reactor.payload.query",
        "reactor.payload.actor_email",
        "reactor.metadata.user_email",
        "reactor.metadata.nested.authorization",
    ]
    assert body["checks"]["required_env"]["status"] == "passed"
    assert body["releaseGate"] == {
        "status": "ready",
        "blocksReleaseReadiness": False,
        "reason": None,
        "requiredReport": "observability_smoke",
        "remediation": [],
    }
    assert "lsv2_secret_value" not in response.text


async def test_admin_provider_smoke_executes_configured_model_and_records_audit(
    monkeypatch: MonkeyPatch,
) -> None:
    calls: list[Settings] = []

    def fake_run(settings: Settings) -> dict[str, object]:
        calls.append(settings)
        return {
            "ok": True,
            "status": "passed",
            "scope": "live",
            "provider": "ollama",
            "model": "qwen3:8b",
            "evidence": {
                "backendProviderIntegration": {
                    "provider": "ollama",
                    "model": "qwen3:8b",
                    "usageMetadata": {
                        "present": True,
                        "source": "LangChain AIMessage.usage_metadata",
                        "inputTokens": 4,
                        "outputTokens": 2,
                        "totalTokens": 6,
                        "totalMatchesBreakdown": True,
                    },
                }
            },
            "checks": {
                "chat_model_invoke": {"status": "passed", "content_length": 4},
                "usage_metadata": {"status": "passed"},
            },
        }

    monkeypatch.setattr(admin_router, "run_configured_backend_provider_smoke", fake_run)
    audit_store = FakeAdminAuditStore()
    settings = Settings(
        default_model_provider="ollama",
        default_model="qwen3:8b",
        observability_trace_exporter="langsmith",
        observability_langsmith_api_key="lsv2_secret_value",
    )
    app = create_app()
    app.state.reactor = FakeContainer(settings=settings, admin_audit_store=audit_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.post("/api/admin/provider/smoke", headers=USER_HEADERS)
        response = await client.post("/v1/admin/provider/smoke", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert response.status_code == 200
    assert calls == [settings]
    body = response.json()
    assert body["ok"] is True
    assert body["provider"] == "ollama"
    assert body["model"] == "qwen3:8b"
    assert body["evidence"]["backendProviderIntegration"]["usageMetadata"] == {
        "present": True,
        "source": "LangChain AIMessage.usage_metadata",
        "inputTokens": 4,
        "outputTokens": 2,
        "totalTokens": 6,
        "totalMatchesBreakdown": True,
    }
    assert "lsv2_secret_value" not in response.text
    assert len(audit_store.saved) == 1
    assert audit_store.saved[0].category == "release_smoke"
    assert audit_store.saved[0].action == AdminAuditAction.SIMULATE
    assert audit_store.saved[0].resource_type == "provider"
    assert audit_store.saved[0].resource_id == "ollama:qwen3:8b"
    assert audit_store.saved[0].detail == "status=passed ok=true"


async def test_admin_external_smokes_require_confirmation_and_record_secret_free_audits(
    monkeypatch: MonkeyPatch,
) -> None:
    slack_calls: list[Settings] = []
    a2a_calls: list[None] = []

    def fake_slack_run(settings: Settings) -> dict[str, object]:
        slack_calls.append(settings)
        return {
            "ok": True,
            "status": "passed",
            "scope": "live",
            "evidence": {
                "slackGatewaySmoke": {
                    "status": "verified",
                    "gateway": "native_slack_gateway",
                }
            },
            "checks": {
                "thread_message": {"status": "passed", "channel_id": "C123"},
            },
            "liveTarget": {
                "workspaceId": "T123",
                "channelId": "C123",
                "botUserId": "U123",
            },
        }

    def fake_a2a_run() -> dict[str, object]:
        a2a_calls.append(None)
        return {
            "ok": True,
            "status": "passed",
            "scope": "live",
            "base_url": "https://reactor.example",
            "evidence": {
                "a2aProtocol": {
                    "status": "verified",
                    "taskApi": {"status": "passed", "taskStatus": "completed"},
                    "secretFree": True,
                }
            },
            "checks": {"task_api": {"status": "passed", "task_id": "task_123"}},
        }

    monkeypatch.setattr(admin_router, "run_configured_slack_smoke", fake_slack_run)
    monkeypatch.setattr(admin_router, "run_configured_a2a_smoke", fake_a2a_run)
    audit_store = FakeAdminAuditStore()
    signing_value = f"signing_{UUID(int=1)}"
    bot_value = f"xoxb_{UUID(int=2)}"
    app_value = f"xapp_{UUID(int=3)}"
    settings = Settings(
        slack_signing_secret=signing_value,
        slack_bot_token=bot_value,
        slack_app_token=app_value,
    )
    app = create_app()
    app.state.reactor = FakeContainer(settings=settings, admin_audit_store=audit_store)
    transport = ASGITransport(app=app)
    confirmation = {"confirmExternalSideEffects": True}

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        slack_unconfirmed = await client.post(
            "/api/admin/slack/smoke",
            headers=ADMIN_HEADERS,
            json={"confirmExternalSideEffects": False},
        )
        a2a_unconfirmed = await client.post(
            "/api/admin/a2a/smoke",
            headers=ADMIN_HEADERS,
            json={},
        )
        forbidden = await client.post(
            "/api/admin/slack/smoke",
            headers=USER_HEADERS,
            json=confirmation,
        )
        slack_response = await client.post(
            "/v1/admin/slack/smoke",
            headers=ADMIN_HEADERS,
            json=confirmation,
        )
        a2a_response = await client.post(
            "/v1/admin/a2a/smoke",
            headers=ADMIN_HEADERS,
            json=confirmation,
        )

    assert slack_unconfirmed.status_code == 422
    assert a2a_unconfirmed.status_code == 422
    assert forbidden.status_code == 403
    assert slack_calls == [settings]
    assert a2a_calls == [None]
    assert slack_response.status_code == 200
    assert a2a_response.status_code == 200
    assert slack_response.json()["liveTarget"] == {
        "workspaceId": "T123",
        "channelId": "C123",
        "botUserId": "U123",
    }
    assert a2a_response.json()["evidence"]["a2aProtocol"]["secretFree"] is True
    for credential in [signing_value, bot_value, app_value]:
        assert credential not in slack_response.text
        assert credential not in a2a_response.text
    assert [(log.resource_type, log.resource_id, log.detail) for log in audit_store.saved] == [
        ("slack", "C123", "status=passed ok=true external_side_effects=confirmed"),
        ("a2a", "reactor.example", "status=passed ok=true external_side_effects=confirmed"),
    ]
    assert all(log.category == "release_smoke" for log in audit_store.saved)
    assert all(log.action == AdminAuditAction.SIMULATE for log in audit_store.saved)


async def test_admin_context_manifest_diagnostics_reports_memory_and_rag_contracts() -> None:
    transport = ASGITransport(app=create_app())
    memory_checksum = "sha256:" + ("a" * 64)
    rag_checksum = "sha256:" + ("b" * 64)
    context_manifest = {
        "sections": [
            {
                "name": "session_memory",
                "content_checksum": memory_checksum,
                "metadata": {
                    "memoryAdmissionPolicy": {
                        "activeOnly": True,
                        "missingStatusExcluded": True,
                        "tombstonedExcluded": True,
                        "supersededExcluded": True,
                    },
                    "memory_count": 1,
                    "skipped_memory_count": 1,
                    "status_counts": {"active": 1, "tombstoned": 1},
                },
            },
            {
                "name": "rag_context",
                "content_checksum": rag_checksum,
                "metadata": {
                    "ragGroundingPolicy": {
                        "citationTracking": "required",
                        "uncitedChunksTracked": True,
                        "aclEvidence": "acl_hash_only",
                        "rawAclMetadataVisible": False,
                    },
                    "citation_count": 1,
                    "acl_hash": "acl_1",
                    "citations": [
                        {
                            "citation_id": "doc_1:0",
                            "source_uri": "docs/doc-1.md",
                            "content_hash": "sha256:" + ("c" * 64),
                            "acl": {"visibility": "private"},
                        }
                    ],
                },
            },
        ]
    }

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.post(
            "/v1/admin/context-manifest/diagnostics",
            headers=USER_HEADERS,
            json={"contextManifest": context_manifest},
        )
        response = await client.post(
            "/v1/admin/context-manifest/diagnostics",
            headers=ADMIN_HEADERS,
            json={"contextManifest": context_manifest},
        )

    assert forbidden.status_code == 403
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["status"] == "failed"
    assert body["sectionCount"] == 2
    assert body["memoryAdmissionPolicy"] == {
        "activeOnly": True,
        "missingStatusExcluded": True,
        "tombstonedExcluded": True,
        "supersededExcluded": True,
    }
    assert body["memoryCount"] == 1
    assert body["skippedMemoryCount"] == 1
    assert body["memoryStatusCounts"] == {"active": 1, "tombstoned": 1}
    assert body["ragGroundingPolicy"] == {
        "citationTracking": "required",
        "uncitedChunksTracked": True,
        "aclEvidence": "acl_hash_only",
        "rawAclMetadataVisible": False,
    }
    assert body["citationCount"] == 1
    assert body["rawAclMetadataVisible"] is True
    assert body["findings"] == [
        {
            "code": "raw_acl_metadata",
            "section": "rag_context",
            "path": "metadata.citations[0].acl",
        },
        {
            "code": "raw_rag_citation_acl_metadata",
            "section": "rag_context",
            "path": "metadata.citations[0].acl",
            "expected": "acl_hash",
        },
    ]


async def test_admin_graph_topology_endpoint_exposes_subgraph_runtime_contract() -> None:
    transport = ASGITransport(app=create_app())

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/v1/admin/graph/topology", headers=USER_HEADERS)
        response = await client.get("/v1/admin/graph/topology", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert response.status_code == 200
    body = response.json()
    assert body["composition"] == "stage_subgraphs"
    assert body["stageOrder"] == ["preflight", "generation", "tool_policy", "completion"]
    assert body["subgraphOrder"] == ["preflight", "generation", "tool_policy", "completion"]
    assert body["subgraphEdges"] == [
        {"source": "__start__", "target": "preflight"},
        {"source": "preflight", "target": "generation"},
        {"source": "generation", "target": "tool_policy"},
        {"source": "tool_policy", "target": "completion"},
        {"source": "completion", "target": "__end__"},
    ]
    assert body["subgraphs"][0] == {
        "name": "preflight",
        "entryNode": "guard",
        "exitNode": "context",
        "checkpointMode": "inherited_parent",
        "nodes": ["guard", "context"],
        "nodeCount": 2,
    }


async def test_admin_checkpoint_diagnostics_exposes_fork_replay_contract() -> None:
    transport = ASGITransport(app=create_app())

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get(
            "/v1/admin/checkpoints/diagnostics",
            headers=USER_HEADERS,
        )
        response = await client.get(
            "/api/admin/checkpoints/diagnostics",
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "checkpoint_fork"
    assert body["forkApiPaths"] == ["/v1/runs/{run_id}/fork"]
    assert body["stateHistoryApiPaths"] == [
        "/api/admin/debug/state-history/{run_id}",
        "/v1/admin/debug/state-history/{run_id}",
    ]
    assert body["trustedMetadataKeys"] == [
        "source",
        "forkedFromRunId",
        "forkedFromThreadId",
        "forkedFromCheckpointNs",
        "forkedFromCheckpointId",
        "forkTargetThreadId",
        "forkTargetCheckpointNs",
        "forkedFromExecutionContract",
    ]
    assert body["userMetadataStrippedKeys"] == [
        "source",
        "checkpointId",
        "checkpoint_id",
        "forkedFromRunId",
        "forkedFromThreadId",
        "forkedFromCheckpointNs",
        "forkedFromCheckpointId",
        "forkTargetThreadId",
        "forkTargetCheckpointNs",
        "forkedFromExecutionContract",
    ]
    assert body["replayCoverage"] == {
        "status": "verified",
        "runtimes": [
            "langgraph",
            "langchain_agent",
            "langgraph_stream",
            "langchain_agent_stream",
        ],
        "configurableKeys": ["thread_id", "checkpoint_ns", "checkpoint_id"],
        "ignoredReasons": ["missing_checkpoint_id", "fork_target_mismatch"],
        "appliedMetadataFields": [
            "status",
            "source",
            "requestedCheckpointId",
            "checkpointId",
            "materialization",
            "targetThreadId",
            "targetCheckpointNs",
        ],
    }
    assert body["storageSemantics"] == {
        "status": "verified",
        "logicalIdentity": ["tenant_id", "thread_id", "checkpoint_ns"],
        "physicalThreadKey": "sha256_v1",
        "rootCheckpointNs": "",
        "sourceRead": "BaseCheckpointSaver.aget_tuple",
        "targetWrite": "BaseCheckpointSaver.aput",
        "tenantScoped": True,
        "targetMustBeEmpty": True,
        "pendingWritesRejected": True,
        "sourceReadIdentityVerified": True,
        "sourcePayloadIdentityVerified": True,
        "targetWriteScopeVerified": True,
        "trustedCapability": "TrustedCheckpointFork",
        "userMetadataCannotAuthorizeReplay": True,
        "typedChatNamespaceAccepted": True,
        "userMetadataCannotOverrideNamespace": True,
        "profileMetadataUsesDurableNamespace": True,
        "profileCannotOverrideDurableNamespace": True,
        "profileNamespaceStateField": "profile_checkpoint_ns",
        "profileNamespaceSource": "resolved_durable_checkpoint_ns",
        "streamingNamespaceTargets": [
            "run_store",
            "checkpoint_fork",
            "langgraph_config",
            "langchain_agent",
            "run_result",
            "terminal_actions",
        ],
        "executionContractFields": ["runtime", "graphProfile"],
        "executionContractMatchRequired": True,
        "materializationModes": ["pinned_source_scope", "copied_to_target_scope"],
        "failClosedReasons": [
            "invalid_fork_provenance",
            "checkpointer_unavailable",
            "source_checkpoint_not_found",
            "source_checkpoint_scope_mismatch",
            "source_checkpoint_id_mismatch",
            "source_checkpoint_payload_id_mismatch",
            "invalid_source_checkpoint",
            "source_checkpoint_has_pending_writes",
            "target_checkpoint_scope_not_empty",
            "target_checkpoint_write_scope_mismatch",
            "target_checkpoint_write_failed",
            "checkpoint_store_error",
            "fork_execution_contract_mismatch",
        ],
    }


async def test_admin_durable_queue_diagnostics_reports_tenant_scoped_backlog() -> None:
    durable_store = FakeDurableStore(
        rows=[
            {
                "queue_status": "queued",
                "queue_count": 2,
                "dead_letter_count": 0,
            },
            {
                "queue_status": "leased",
                "queue_count": 1,
                "dead_letter_count": 0,
            },
            {
                "queue_status": "retryable_failed",
                "queue_count": 3,
                "dead_letter_count": 0,
            },
            {
                "queue_status": "dead_lettered",
                "queue_count": 0,
                "dead_letter_count": 4,
            },
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(durable_store=durable_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get(
            "/v1/admin/durable-queue/diagnostics",
            headers=USER_HEADERS,
        )
        response = await client.get(
            "/api/admin/durable-queue/diagnostics",
            headers=ADMIN_HEADERS,
        )
    missing_transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=missing_transport, base_url="http://testserver") as client:
        missing_store = await client.get(
            "/v1/admin/durable-queue/diagnostics",
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert missing_store.status_code == 503
    assert missing_store.json()["detail"] == "durable queue persistence is not configured"
    assert response.status_code == 200
    body = response.json()
    assert durable_store.calls == ["tenant_1"]
    assert body == {
        "status": "ready",
        "tenantId": "tenant_1",
        "queueStatusCounts": {
            "queued": 2,
            "leased": 1,
            "retryable_failed": 3,
            "dead_lettered": 4,
        },
        "queueBacklog": 6,
        "leasedCount": 1,
        "deadLetterCount": 4,
        "leaseRecovery": {
            "retryableStatuses": ["queued", "retryable_failed"],
            "expiredLeaseAction": "retry_or_dead_letter",
            "deadLetterReason": "run_queue_lease_attempts_exhausted",
            "fencingTokenRequired": True,
        },
    }


async def test_admin_durable_queue_release_expired_leases_records_audit() -> None:
    durable_store = FakeDurableStore(rows=[])
    durable_store.expired_release_count = 5
    audit_store = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        admin_audit_store=audit_store,
        durable_store=durable_store,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.post(
            "/v1/admin/durable-queue/release-expired",
            headers=USER_HEADERS,
        )
        response = await client.post(
            "/api/admin/durable-queue/release-expired",
            headers=ADMIN_HEADERS,
        )
    missing_transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=missing_transport, base_url="http://testserver") as client:
        missing_store = await client.post(
            "/v1/admin/durable-queue/release-expired",
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert missing_store.status_code == 503
    assert missing_store.json()["detail"] == "durable queue persistence is not configured"
    assert response.status_code == 200
    assert response.json() == {
        "status": "released",
        "tenantId": "tenant_1",
        "released": 5,
        "actor": "admin_1",
    }
    assert durable_store.release_calls == ["tenant_1"]
    assert len(audit_store.saved) == 1
    assert audit_store.saved[0].category == "durable_queue"
    assert audit_store.saved[0].action == AdminAuditAction.UPDATE
    assert audit_store.saved[0].resource_type == "run_queue"
    assert audit_store.saved[0].resource_id == "release_expired"
    assert audit_store.saved[0].detail == "released=5"


async def test_metric_ingestion_api_ports_legacy_single_and_batch_events() -> None:
    buffer = FakeMetricIngestionBuffer()
    app = create_app()
    app.state.reactor = FakeContainer(metric_ingestion_buffer=buffer)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.post(
            "/api/admin/metrics/ingest/mcp-health",
            headers=MANAGER_HEADERS,
            json={"tenantId": "tenant_1", "serverName": "jira", "status": "CONNECTED"},
        )
        mcp = await client.post(
            "/api/admin/metrics/ingest/mcp-health",
            headers=ADMIN_HEADERS,
            json={
                "tenantId": "tenant_2",
                "serverName": "jira",
                "status": "CONNECTED",
                "responseTimeMs": 25,
                "toolCount": 3,
            },
        )
        tool = await client.post(
            "/v1/admin/metrics/ingest/tool-call",
            headers=ADMIN_HEADERS,
            json={
                "tenantId": "tenant_2",
                "runId": "run_1",
                "toolName": "jira_search",
                "success": False,
                "durationMs": 120,
                "errorClass": "timeout",
            },
        )
        eval_result = await client.post(
            "/api/admin/metrics/ingest/eval-result",
            headers=ADMIN_HEADERS,
            json={
                "tenantId": "tenant_2",
                "evalRunId": "eval_run_1",
                "testCaseId": "case_1",
                "pass": False,
                "score": 0.25,
                "failureDetail": "x" * 700,
            },
        )
        batch = await client.post(
            "/api/admin/metrics/ingest/batch",
            headers=ADMIN_HEADERS,
            json=[
                {"tenantId": "tenant_2", "serverName": "jira"},
                {"tenantId": "tenant_2", "serverName": "confluence"},
            ],
        )
        eval_batch = await client.post(
            "/v1/admin/metrics/ingest/eval-results",
            headers=ADMIN_HEADERS,
            json={
                "tenantId": "tenant_2",
                "evalRunId": "eval_run_2",
                "results": [
                    {"testCaseId": "case_2", "pass": True, "score": 1.0},
                    {"testCaseId": "case_3", "pass": False, "score": 0.1},
                ],
            },
        )
        empty_eval_batch = await client.post(
            "/api/admin/metrics/ingest/eval-results",
            headers=ADMIN_HEADERS,
            json={"tenantId": "tenant_1", "evalRunId": "eval_run_3", "results": []},
        )

    assert forbidden.status_code == 403
    assert mcp.status_code == 202
    assert mcp.json() == {"status": "accepted"}
    assert tool.status_code == 202
    assert eval_result.status_code == 202
    assert batch.status_code == 200
    assert batch.json() == {"accepted": 2, "dropped": 0}
    assert eval_batch.status_code == 200
    assert eval_batch.json() == {"evalRunId": "eval_run_2", "accepted": 2, "dropped": 0}
    assert empty_eval_batch.status_code == 400
    assert empty_eval_batch.json()["detail"] == "Results list must not be empty"
    assert [event["type"] for event in buffer.events] == [
        "mcp_health",
        "tool_call",
        "eval_result",
        "mcp_health",
        "mcp_health",
        "eval_result",
        "eval_result",
    ]
    assert {event["tenantId"] for event in buffer.events} == {"tenant_1"}
    assert buffer.events[2]["failureDetail"] == "x" * 500


async def test_admin_audit_list_masks_actor_filters_and_paginates() -> None:
    store = FakeAdminAuditStore(
        [
            AdminAuditLog(
                id="audit_1",
                category="mcp",
                action=AdminAuditAction.UPDATE,
                actor="admin@example.com",
                resource_type="mcp_server",
                resource_id="server_1",
                detail="updated server",
                created_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
            ),
            AdminAuditLog(
                id="audit_2",
                category="guard",
                action=AdminAuditAction.DELETE,
                actor="other@example.com",
                created_at=datetime(2026, 6, 26, 0, 0, tzinfo=UTC),
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(admin_audit_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/admin/audits",
            params={"category": "mcp", "action": "UPDATE", "offset": 0, "pageLimit": 1},
            headers=MANAGER_HEADERS,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == "audit_1"
    assert body["items"][0]["actor"].startswith("admin-account:")
    assert body["items"][0]["actor"] != "admin@example.com"
    assert body["items"][0]["createdAt"] == 1782435600000


async def test_admin_audit_export_requires_export_permission_and_records_audit() -> None:
    store = FakeAdminAuditStore(
        [
            AdminAuditLog(
                id="audit_1",
                category="audit",
                action=AdminAuditAction.READ,
                actor="admin@example.com",
                detail='contains, "quotes"',
                created_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
            )
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(admin_audit_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        manager = await client.get("/api/admin/audits/export", headers=MANAGER_HEADERS)
        admin = await client.get("/v1/admin/audits/export", headers=ADMIN_HEADERS)

    assert manager.status_code == 403
    assert manager.json()["detail"] == "permission required: audit:export"
    assert admin.status_code == 200
    assert admin.headers["content-type"].startswith("text/csv")
    assert "id,timestamp,category,action,actor,resource_type,resource_id,detail" in admin.text
    assert 'contains, ""quotes""' in admin.text
    assert store.saved[-1].action == AdminAuditAction.EXPORT
    assert store.saved[-1].actor == "admin_1"


async def test_admin_audit_rollback_preview_returns_manual_boundary() -> None:
    store = FakeAdminAuditStore(
        [
            AdminAuditLog(
                id="audit_1",
                category="mcp",
                action=AdminAuditAction.UPDATE,
                actor="admin@example.com",
                resource_type="mcp_server",
                resource_id="server_1",
                detail="updated server",
                created_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
            )
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(admin_audit_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/v1/admin/audits/audit_1/rollback-preview",
            headers=MANAGER_HEADERS,
        )
        missing = await client.get(
            "/api/admin/audits/audit_missing/rollback-preview",
            headers=MANAGER_HEADERS,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["resourceLabel"] == "mcp_server:server_1"
    assert body["changes"] == []
    assert body["warnings"] == [
        "Automatic audit rollback is not registered for this entry.",
        "Use the owning admin console or stored resource history for manual recovery.",
    ]
    assert "audit_1 requires manual recovery" in body["summary"]
    assert missing.status_code == 404


async def test_admin_audit_rollback_execution_fails_closed() -> None:
    store = FakeAdminAuditStore(
        [
            AdminAuditLog(
                id="audit_1",
                category="mcp",
                action=AdminAuditAction.DELETE,
                actor="admin@example.com",
                resource_type="mcp_server",
                resource_id="server_1",
                detail="deleted server",
                created_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
            )
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(admin_audit_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        manager = await client.post(
            "/api/admin/audits/audit_1/rollback",
            headers=MANAGER_HEADERS,
        )
        admin = await client.post(
            "/v1/admin/audits/audit_1/rollback",
            headers=ADMIN_HEADERS,
        )

    assert manager.status_code == 403
    assert manager.json()["detail"] == "permission required: audit:export"
    assert admin.status_code == 409
    assert admin.json()["detail"] == (
        "automatic audit rollback is not available; use rollback preview for manual recovery"
    )


async def test_ops_dashboard_summarizes_scheduler_approvals_and_metrics() -> None:
    recent_tool_started_at = datetime.now(UTC) - timedelta(hours=1)
    job = ScheduledJobRecord(
        id="job_1",
        tenant_id="tenant_1",
        name="Daily agent",
        cron_expression="0 0 9 * * *",
        job_type=ScheduledJobType.AGENT,
        agent_prompt="Summarize",
        enabled=True,
        last_status=JobExecutionStatus.FAILED,
    )
    execution = ScheduledJobExecutionRecord(
        id="exec_1",
        tenant_id="tenant_1",
        job_id="job_1",
        job_name="Daily agent",
        job_type=ScheduledJobType.AGENT,
        status=JobExecutionStatus.FAILED,
        result="Job 'Daily agent' failed: tool timeout",
        duration_ms=42,
        started_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
        completed_at=datetime(2026, 6, 26, 1, 1, tzinfo=UTC),
    )
    app = create_app()
    app.state.reactor = FakeContainer(
        scheduler_store=FakeSchedulerStore([job]),
        scheduled_job_execution_store=FakeExecutionStore([execution]),
        approval_store=FakeApprovalStore(pending_count=2),
        durable_store=FakeDurableStore(
            rows=[
                {"queue_status": "queued", "queue_count": 4, "dead_letter_count": 0},
                {"queue_status": "leased", "queue_count": 2, "dead_letter_count": 0},
                {"queue_status": "retryable_failed", "queue_count": 1, "dead_letter_count": 0},
                {"queue_status": "dead_lettered", "queue_count": 0, "dead_letter_count": 3},
            ]
        ),
        tool_invocation_store=FakeToolInvocationStore(
            [
                tool_invocation(
                    "tool_ok",
                    tool_id="search",
                    status="succeeded",
                    duration_ms=80,
                    started_at=recent_tool_started_at,
                ),
                tool_invocation(
                    "tool_failed",
                    tool_id="search",
                    status="failed",
                    duration_ms=120,
                    started_at=recent_tool_started_at,
                ),
                tool_invocation(
                    "tool_reconcile",
                    tool_id="notify",
                    status="requires_reconciliation",
                    duration_ms=200,
                    started_at=recent_tool_started_at,
                ),
                tool_invocation(
                    "tool_started",
                    tool_id="browser",
                    status="started",
                    duration_ms=0,
                    started_at=recent_tool_started_at,
                ),
                tool_invocation(
                    "tool_other",
                    tenant_id="tenant_2",
                    tool_id="other",
                    status="failed",
                    duration_ms=999,
                    started_at=recent_tool_started_at,
                ),
            ]
        ),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/v1/ops/dashboard", headers=USER_HEADERS)
        response = await client.get(
            "/api/ops/dashboard",
            params=[("names", "reactor.agent.executions"), ("names", "reactor.agent.errors")],
            headers=MANAGER_HEADERS,
        )
        metric_names = await client.get("/v1/ops/metrics/names", headers=MANAGER_HEADERS)

    assert forbidden.status_code == 403
    assert response.status_code == 200
    body = response.json()
    assert body["scheduler"] == {
        "totalJobs": 1,
        "enabledJobs": 1,
        "runningJobs": 0,
        "failedJobs": 1,
        "attentionBacklog": 1,
        "agentJobs": 1,
    }
    assert body["approvals"] == {"pendingCount": 2}
    assert body["durableQueue"] == {
        "status": "ready",
        "tenantId": "tenant_1",
        "queueStatusCounts": {
            "queued": 4,
            "leased": 2,
            "retryable_failed": 1,
            "dead_lettered": 3,
        },
        "queueBacklog": 7,
        "leasedCount": 2,
        "deadLetterCount": 3,
        "leaseRecovery": {
            "retryableStatuses": ["queued", "retryable_failed"],
            "expiredLeaseAction": "retry_or_dead_letter",
            "deadLetterReason": "run_queue_lease_attempts_exhausted",
            "fencingTokenRequired": True,
        },
    }
    assert body["toolLifecycleStatusCounts"] == {
        "failed": 1,
        "requires_reconciliation": 1,
        "started": 1,
        "succeeded": 1,
    }
    assert body["toolLifecycleAttentionCount"] == 3
    assert body["recentSchedulerExecutions"][0]["failureReason"] == "tool timeout"
    assert [metric["name"] for metric in body["metrics"]] == [
        "reactor.agent.executions",
        "reactor.agent.errors",
    ]
    assert metric_names.status_code == 200
    assert "reactor.agent.executions" in metric_names.json()
    assert "reactor_runs_total" in metric_names.json()
    assert "reactor_model_tokens_total" in metric_names.json()


async def test_ops_dashboard_exposes_secret_free_release_readiness_summary(tmp_path: Path) -> None:
    report_path = tmp_path / "release-readiness.json"
    current_commit = current_git_commit()
    assert current_commit
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    provenance = {
        "commitSha": current_commit,
        "expectedCommitSha": current_commit,
        "generatedAt": generated_at,
        "inputHash": "a" * 64,
    }
    report_path.write_text(
        json.dumps(
            {
                "status": "passed",
                "ok": True,
                "provenance": provenance,
                "requiredReports": ["smoke_run", "release_evidence", "langsmith_eval_sync"],
                "missingReports": [],
                "blockingReports": [],
                "warningReports": ["hardening_suite"],
                "requiredEnvAnyOf": [
                    ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"],
                    ["REACTOR_A2A_BASE_URL"],
                ],
                "missingEnvAnyOf": ["REACTOR_A2A_BASE_URL"],
                "recommendedEnv": ["REACTOR_SLACK_BOT_TOKEN", "REACTOR_SLACK_SIGNING_SECRET"],
                "tagRecommendation": {
                    "status": "passed",
                    "eligible": True,
                    "latestTag": "v1.1.0",
                    "recommendedTag": "v1.1.1",
                    "recommendedVersionBump": "patch",
                    "minorEligible": True,
                    "minorBoundaryReports": ["langsmith_eval_sync"],
                    "passedReports": ["smoke_run", "release_evidence", "langsmith_eval_sync"],
                    "warningReports": ["hardening_suite"],
                    "warningReviewRequired": False,
                    "missingEnv": [
                        "REACTOR_A2A_API_KEY",
                        "REACTOR_A2A_BASE_URL",
                        "REACTOR_SLACK_BOT_TOKEN",
                        "REACTOR_SLACK_SIGNING_SECRET",
                    ],
                    "preflightEnvFileCommand": (
                        "uv run reactor-release-smoke-run --env-file "
                        "reports/release/release-smoke-preflight.local.env --preflight-only"
                    ),
                    "releaseSmokeEnvFileCommand": (
                        "uv run reactor-release-smoke-run --env-file "
                        "reports/release/release-smoke-preflight.local.env --report-file "
                        "reports/release-smoke-run.json"
                    ),
                    "releaseReadinessCommand": (
                        "uv run reactor-release-smoke-run --readiness-output "
                        "reports/release-readiness.json"
                    ),
                },
                "items": [
                    {
                        "name": "rag_ingestion_lifecycle",
                        "status": "passed",
                        "ragIngestionLifecycle": {
                            "status": "verified",
                            "framework": "langchain-postgres",
                            "vectorStore": "PGVector",
                            "embeddingBoundary": "LangChainEmbeddings",
                            "sourceAllowlistRequired": True,
                            "mimeAllowlistRequired": True,
                            "sizeLimitRequired": True,
                            "aclMetadataRequired": True,
                            "aclBeforeRanking": True,
                            "rawAclRedactedFromModelContext": True,
                            "humanReviewRequiredForCapturedCandidates": True,
                            "quarantineBeforeIndex": True,
                            "backgroundRetries": True,
                            "checksumIdempotency": True,
                            "reindexAuditRequired": True,
                            "poisoningEvalCaseIds": ["rag-poisoning-retrieval-is-labeled"],
                            "diagnosticsSurface": {
                                "status": "verified",
                                "apiPaths": [
                                    "/api/admin/rag/ingestion-jobs/{job_id}",
                                    "/v1/rag/ingestion-jobs/{job_id}",
                                ],
                                "releaseReviewFields": [
                                    "sourceAllowlist",
                                    "mimeAllowlist",
                                    "aclHash",
                                    "poisoningFindings",
                                ],
                                "rawContextPayload": "must not pass through",
                            },
                            "verificationSensors": {
                                "covers": [
                                    "managed_document_ingest_requires_acl",
                                    "weak_documents_ask_answers_promote_to_eval_with_citation_markers",
                                ],
                                "focusedTests": [
                                    "uv run pytest tests/unit/test_rag_document_management.py -q",
                                ],
                                "releaseReadinessContracts": [
                                    "ragIngestionLifecycle",
                                    "researchAnswerContract",
                                ],
                                "rawEvidencePayload": "must not pass through",
                            },
                            "rawAcl": "acl-secret-must-not-pass-through",
                        },
                        "researchAnswerContract": {
                            "profile": "research",
                            "citationStyle": "manifest_ids",
                            "requiresCitationIds": True,
                            "requiresSourceLabels": True,
                            "fallbackResponseIncludesSources": True,
                            "uncitedClaimsAllowed": False,
                            "tracksMissingChunks": True,
                            "tracksContentHashMismatches": True,
                            "rawAnswer": "must not pass through",
                        },
                    },
                    {
                        "name": "langsmith_eval_sync",
                        "status": "passed",
                        "productCapabilityBoundary": {
                            "capability": "rag_ingest_to_feedback_eval_langsmith_readiness",
                            "evidence": [
                                "rag_ingestion_lifecycle",
                                "rag_ingestion_candidate_feedback_queue",
                                "feedback_promotion.reviewed_feedback",
                                "langsmith_trace_grading",
                                "release_readiness_command",
                            ],
                            "missingEvidence": [],
                            "minorEligible": True,
                            "rawTraceUrl": "https://smith.langchain.com/?api_key=secret",
                        },
                        "datasetName": "reactor-regression",
                        "exampleIds": ["example-1", "example-2"],
                        "caseIds": ["case-1", "case-2"],
                        "metadataCaseIds": ["case-1", "case-2"],
                        "splitCounts": {"regression": 2},
                        "exampleContract": {
                            "secretScan": {
                                "enabled": True,
                                "scansKeys": True,
                                "scansValues": True,
                                "beforeCreateExamples": True,
                            },
                            "rawExampleValuesIncluded": False,
                        },
                        "sdkContract": {
                            "client": "langsmith.Client",
                            "datasetApi": "create_dataset",
                            "exampleApi": "create_examples",
                            "lookupApi": "has_dataset",
                            "deterministicExampleIds": True,
                            "maxConcurrency": 1,
                        },
                        "feedbackReviewQueue": {
                            "reviewStatus": "done",
                            "reviewNote": "Promoted to regression eval and reviewed.",
                            "candidateTag": "rag-candidate:grounded_citation",
                            "caseIds": ["case_rag_candidate_grounded_citation"],
                            "reviewTags": ["promoted", "langsmith"],
                            "feedbackRatingCounts": {"thumbs_down": 1},
                            "feedbackSourceCounts": {"slack_button": 1},
                            "workflowTagCounts": {"documents-ask": 1, "rag": 1},
                            "expectedCitationCounts": {"candidate-runbook.md": 1},
                            "rawSlackPayload": "xoxb-secret-must-not-pass-through",
                        },
                    },
                    {
                        "name": "live_slack_workspace_smoke",
                        "status": "passed",
                        "slackGatewaySmoke": {
                            "status": "verified",
                            "gateway": "native_slack_gateway",
                            "ingress": "slash_command_or_socket_mode",
                            "currentThreadReplyRoute": "native_gateway",
                            "signatureVerificationRequired": True,
                            "responseUrlRouteSupported": True,
                            "mcpWriteOverlapForbidden": True,
                            "requiredChecks": [
                                "required_env",
                                "signed_request",
                                "auth_test",
                                "approval_block_contract",
                            ],
                            "botToken": "xoxb-secret-must-not-pass-through",
                        },
                    },
                    {
                        "name": "live_peer_network_interoperability_smoke",
                        "status": "passed",
                        "a2aProtocol": {
                            "status": "verified",
                            "agentCard": {
                                "name": "Reactor",
                                "interfaceCount": 1,
                                "interfaceProtocolBindings": ["JSONRPC"],
                                "interfaceProtocolVersions": ["1.0"],
                                "interfaceUrls": ["https://peer.example/a2a?api_key=secret"],
                                "wellKnownPath": "/.well-known/agent-card.json",
                            },
                            "diagnostics": {
                                "sdkAvailable": True,
                                "protocolVersion": "1.0",
                                "endpoint": "https://peer.example/a2a?api_key=secret",
                                "path": "/v1/a2a/diagnostics",
                            },
                            "protocolNegotiation": {
                                "requestHeader": "A2A-Version",
                                "requestedVersion": "1.0",
                                "responseVersion": "1.0",
                                "majorMinorOnly": True,
                                "agentCardVersionsChecked": True,
                                "serverGeneratedTaskIds": True,
                                "sdkFastApiSurface": True,
                                "telemetryInstrumentation": "a2a-sdk[telemetry]",
                            },
                            "taskApi": {
                                "status": "passed",
                                "taskStatus": "completed",
                                "path": "/v1/a2a/tasks",
                            },
                            "operationalEvidence": {
                                "auditRecorded": True,
                                "idempotencyEnforced": True,
                                "telemetryEnabled": True,
                                "pushOutboxRouted": True,
                            },
                            "secretFree": True,
                            "tlsRequired": True,
                            "apiKey": "a2a-secret-must-not-pass-through",
                        },
                    },
                    {
                        "name": "live_backend_provider_integration",
                        "status": "passed",
                        "backendProviderIntegration": {
                            "status": "verified",
                            "provider": "ollama",
                            "model": "gemma4:12b",
                            "requiredChecks": [
                                "required_env",
                                "tracing_config",
                                "chat_model_invoke",
                                "usage_metadata",
                            ],
                            "usageMetadata": {
                                "source": "LangChain AIMessage.usage_metadata",
                                "present": True,
                                "inputTokens": 20,
                                "outputTokens": 63,
                                "totalTokens": 83,
                                "totalMatchesBreakdown": True,
                                "rawSecretBearingField": "must not pass through",
                            },
                            "apiKey": "sk-live-secret-must-not-pass-through",
                        },
                    },
                    {
                        "name": "hardening_suite",
                        "status": "warning",
                        "memoryMaintenanceLifecycle": {
                            "dependencyWarnings": {
                                "status": "review_required",
                                "checkedPackages": ["langmem", "trustcall", "langgraph"],
                                "installedVersions": {
                                    "langmem": "0.0.30",
                                    "trustcall": "0.0.39",
                                    "langgraph": "1.2.7",
                                },
                                "directPins": {
                                    "langmem": "==0.0.30",
                                    "langgraph": "==1.2.7",
                                },
                                "pinSource": "pyproject.toml",
                                "findings": [
                                    {
                                        "package": "trustcall",
                                        "module": "trustcall._base",
                                        "deprecatedImport": "langgraph.constants.Send",
                                        "replacement": "langgraph.types.Send",
                                        "severity": "warning",
                                        "rawStack": "secret-must-not-pass-through",
                                    }
                                ],
                                "reviewCommand": "uv pip show langmem trustcall langgraph",
                                "remediationCommand": (
                                    "monitor upstream trustcall/langmem compatibility; "
                                    "keep dependency warning visible"
                                ),
                                "resolverCheck": {
                                    "status": "no_lockfile_changes",
                                    "command": (
                                        "uv lock --upgrade-package langmem "
                                        "--upgrade-package trustcall "
                                        "--upgrade-package langgraph --dry-run"
                                    ),
                                    "latestKnownFrom": "resolver",
                                    "rawSolverOutput": "secret-must-not-pass-through",
                                },
                            },
                            "rawSourcePayload": "secret-must-not-pass-through",
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    app = create_app()
    app.state.reactor = FakeContainer(
        settings=Settings(release_readiness_report_path=str(report_path))
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/ops/dashboard", headers=MANAGER_HEADERS)

    assert response.status_code == 200
    release = response.json()["releaseReadiness"]
    assert release["status"] == "passed"
    assert release["provenance"] == {
        "status": "verified",
        **provenance,
        "verifiedCurrentHead": True,
        "reason": None,
    }
    assert release["requiredReports"] == ["smoke_run", "release_evidence", "langsmith_eval_sync"]
    assert release["warningReports"] == ["hardening_suite"]
    assert release["requiredEnvAnyOf"] == [
        ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"],
        ["REACTOR_A2A_BASE_URL"],
    ]
    assert release["missingEnvAnyOf"] == ["REACTOR_A2A_BASE_URL"]
    assert release["recommendedEnv"] == [
        "REACTOR_SLACK_BOT_TOKEN",
        "REACTOR_SLACK_SIGNING_SECRET",
    ]
    assert release["tagRecommendation"]["recommendedTag"] == "v1.1.1"
    assert release["tagRecommendation"]["missingEnv"] == [
        "REACTOR_A2A_API_KEY",
        "REACTOR_A2A_BASE_URL",
        "REACTOR_SLACK_BOT_TOKEN",
        "REACTOR_SLACK_SIGNING_SECRET",
    ]
    assert release["tagRecommendation"]["preflightEnvFileCommand"].endswith("--preflight-only")
    assert (
        "--report-file reports/release-smoke-run.json"
        in release["tagRecommendation"]["releaseSmokeEnvFileCommand"]
    )
    assert release["productCapabilityBoundary"] == {
        "capability": "rag_ingest_to_feedback_eval_langsmith_readiness",
        "minorEligible": True,
        "evidence": [
            "rag_ingestion_lifecycle",
            "rag_ingestion_candidate_feedback_queue",
            "feedback_promotion.reviewed_feedback",
            "langsmith_trace_grading",
            "release_readiness_command",
        ],
        "missingEvidence": [],
        "sourceReport": "langsmith_eval_sync",
        "status": "passed",
    }
    assert "rawTraceUrl" not in release["productCapabilityBoundary"]
    assert release["gates"] == [
        {"id": "rag", "status": "passed", "label": None},
        {"id": "feedback", "status": "passed", "label": None},
        {"id": "langsmith", "status": "passed", "label": None},
        {"id": "slack", "status": "passed", "label": None},
        {"id": "a2a", "status": "passed", "label": None},
        {"id": "provider", "status": "passed", "label": None},
    ]
    assert release["langsmithSync"] == {
        "datasetName": "reactor-regression",
        "exampleCount": 2,
        "caseCount": 2,
        "exampleIds": ["example-1", "example-2"],
        "caseIds": ["case-1", "case-2"],
        "metadataCaseIds": ["case-1", "case-2"],
        "splitCounts": {"regression": 2},
        "secretFree": True,
        "sdkContract": "langsmith.Client.create_dataset/create_examples",
        "sdkContractFields": {
            "client": "langsmith.Client",
            "datasetApi": "create_dataset",
            "deterministicExampleIds": True,
            "exampleApi": "create_examples",
            "lookupApi": "has_dataset",
            "maxConcurrency": 1,
        },
        "exampleContract": {
            "rawExampleValuesIncluded": False,
            "secretScan": {
                "beforeCreateExamples": True,
                "enabled": True,
                "scansKeys": True,
                "scansValues": True,
            },
        },
    }
    assert release["ragIngestionLifecycle"] == {
        "status": "verified",
        "framework": "langchain-postgres",
        "vectorStore": "PGVector",
        "embeddingBoundary": "LangChainEmbeddings",
        "sourceAllowlistRequired": True,
        "mimeAllowlistRequired": True,
        "sizeLimitRequired": True,
        "aclMetadataRequired": True,
        "aclBeforeRanking": True,
        "rawAclRedactedFromModelContext": True,
        "humanReviewRequiredForCapturedCandidates": True,
        "quarantineBeforeIndex": True,
        "backgroundRetries": True,
        "checksumIdempotency": True,
        "reindexAuditRequired": True,
        "poisoningEvalCaseIds": ["rag-poisoning-retrieval-is-labeled"],
        "diagnosticsSurface": {
            "status": "verified",
            "apiPaths": [
                "/api/admin/rag/ingestion-jobs/{job_id}",
                "/v1/rag/ingestion-jobs/{job_id}",
            ],
            "releaseReviewFields": [
                "sourceAllowlist",
                "mimeAllowlist",
                "aclHash",
                "poisoningFindings",
            ],
        },
        "verificationSensors": {
            "covers": [
                "managed_document_ingest_requires_acl",
                "weak_documents_ask_answers_promote_to_eval_with_citation_markers",
            ],
            "focusedTests": [
                "uv run pytest tests/unit/test_rag_document_management.py -q",
            ],
            "releaseReadinessContracts": [
                "ragIngestionLifecycle",
                "researchAnswerContract",
            ],
        },
        "researchAnswerContract": {
            "profile": "research",
            "citationStyle": "manifest_ids",
            "requiresCitationIds": True,
            "requiresSourceLabels": True,
            "fallbackResponseIncludesSources": True,
            "uncitedClaimsAllowed": False,
            "tracksMissingChunks": True,
            "tracksContentHashMismatches": True,
        },
    }
    assert release["feedbackReviewQueue"] == {
        "status": "passed",
        "reviewStatus": "done",
        "reviewNote": "Promoted to regression eval and reviewed.",
        "candidateTag": "rag-candidate:grounded_citation",
        "caseIds": ["case_rag_candidate_grounded_citation"],
        "reviewTags": ["promoted", "langsmith"],
        "feedbackRatingCounts": {"thumbs_down": 1},
        "feedbackSourceCounts": {"slack_button": 1},
        "workflowTagCounts": {"documents-ask": 1, "rag": 1},
        "expectedCitationCounts": {"candidate-runbook.md": 1},
    }
    assert release["backendProviderIntegration"] == {
        "status": "verified",
        "provider": "ollama",
        "model": "gemma4:12b",
        "requiredChecks": [
            "required_env",
            "tracing_config",
            "chat_model_invoke",
            "usage_metadata",
        ],
        "usageMetadata": {
            "source": "LangChain AIMessage.usage_metadata",
            "present": True,
            "inputTokens": 20,
            "outputTokens": 63,
            "totalTokens": 83,
            "totalMatchesBreakdown": True,
        },
    }
    assert release["slackGatewaySmoke"] == {
        "status": "verified",
        "gateway": "native_slack_gateway",
        "ingress": "slash_command_or_socket_mode",
        "currentThreadReplyRoute": "native_gateway",
        "signatureVerificationRequired": True,
        "responseUrlRouteSupported": True,
        "mcpWriteOverlapForbidden": True,
        "requiredChecks": [
            "required_env",
            "signed_request",
            "auth_test",
            "approval_block_contract",
        ],
    }
    assert release["a2aProtocol"] == {
        "status": "verified",
        "agentCard": {
            "name": "Reactor",
            "interfaceCount": 1,
            "interfaceProtocolBindings": ["JSONRPC"],
            "interfaceProtocolVersions": ["1.0"],
            "wellKnownPath": "/.well-known/agent-card.json",
        },
        "diagnostics": {
            "sdkAvailable": True,
            "protocolVersion": "1.0",
            "path": "/v1/a2a/diagnostics",
        },
        "protocolNegotiation": {
            "requestHeader": "A2A-Version",
            "requestedVersion": "1.0",
            "responseVersion": "1.0",
            "majorMinorOnly": True,
            "agentCardVersionsChecked": True,
            "serverGeneratedTaskIds": True,
            "sdkFastApiSurface": True,
            "telemetryInstrumentation": "a2a-sdk[telemetry]",
        },
        "taskApi": {
            "status": "passed",
            "taskStatus": "completed",
            "path": "/v1/a2a/tasks",
        },
        "operationalEvidence": {
            "auditRecorded": True,
            "idempotencyEnforced": True,
            "telemetryEnabled": True,
            "pushOutboxRouted": True,
        },
        "secretFree": True,
        "tlsRequired": True,
    }
    assert release["dependencyWarnings"] == {
        "status": "review_required",
        "source": "memoryMaintenanceLifecycle.dependencyWarnings",
        "warningReports": ["hardening_suite"],
        "warningReviewRequired": False,
        "checkedPackages": ["langmem", "trustcall", "langgraph"],
        "installedVersions": {
            "langmem": "0.0.30",
            "trustcall": "0.0.39",
            "langgraph": "1.2.7",
        },
        "directPins": {
            "langmem": "==0.0.30",
            "langgraph": "==1.2.7",
        },
        "pinSource": "pyproject.toml",
        "findings": [
            {
                "package": "trustcall",
                "module": "trustcall._base",
                "deprecatedImport": "langgraph.constants.Send",
                "replacement": "langgraph.types.Send",
                "severity": "warning",
            }
        ],
        "findingCount": 1,
        "reviewCommand": "uv pip show langmem trustcall langgraph",
        "remediationCommand": (
            "monitor upstream trustcall/langmem compatibility; keep dependency warning visible"
        ),
        "resolverCheck": {
            "status": "no_lockfile_changes",
            "command": (
                "uv lock --upgrade-package langmem --upgrade-package trustcall "
                "--upgrade-package langgraph --dry-run"
            ),
            "latestKnownFrom": "resolver",
        },
    }
    assert "sk-live-secret-must-not-pass-through" not in response.text
    assert "xoxb-secret-must-not-pass-through" not in response.text
    assert "a2a-secret-must-not-pass-through" not in response.text
    assert "apiKey" not in response.text
    assert "botToken" not in response.text
    assert "interfaceUrls" not in response.text
    assert "endpoint" not in response.text
    assert "rawSecretBearingField" not in response.text
    assert "acl-secret-must-not-pass-through" not in response.text
    assert '"rawAcl":' not in response.text
    assert "rawContextPayload" not in response.text
    assert "rawEvidencePayload" not in response.text
    assert "rawAnswer" not in response.text
    assert "rawSlackPayload" not in response.text
    assert "rawStack" not in response.text
    assert "rawSolverOutput" not in response.text
    assert "rawSourcePayload" not in response.text


def test_release_readiness_summary_fails_closed_without_provenance(tmp_path: Path) -> None:
    report_path = tmp_path / "release-readiness.json"
    report_path.write_text(
        json.dumps({"status": "passed", "blockingReports": []}),
        encoding="utf-8",
    )

    summary = admin_router.ops_release_readiness_summary(
        Settings(release_readiness_report_path=str(report_path))
    )

    assert summary is not None
    assert summary.status == "blocked"
    assert summary.blockingReports == ["readiness_provenance"]
    assert summary.provenance is not None
    assert summary.provenance.status == "missing"
    assert summary.provenance.reason == "missing_provenance"
    assert summary.provenance.verifiedCurrentHead is False


def test_release_readiness_summary_fails_closed_when_provenance_is_stale(tmp_path: Path) -> None:
    report_path = tmp_path / "release-readiness.json"
    current_commit = current_git_commit()
    assert current_commit
    report_path.write_text(
        json.dumps(
            {
                "status": "passed",
                "provenance": {
                    "commitSha": current_commit,
                    "expectedCommitSha": current_commit,
                    "generatedAt": (
                        datetime.now(UTC)
                        - timedelta(seconds=admin_router.MAX_RELEASE_READINESS_AGE_SECONDS + 1)
                    )
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "inputHash": "a" * 64,
                },
            }
        ),
        encoding="utf-8",
    )

    summary = admin_router.ops_release_readiness_summary(
        Settings(release_readiness_report_path=str(report_path))
    )

    assert summary is not None
    assert summary.status == "blocked"
    assert summary.provenance is not None
    assert summary.provenance.status == "blocked"
    assert summary.provenance.reason == "stale_readiness_evidence"
    assert summary.provenance.verifiedCurrentHead is False


def test_release_readiness_summary_fails_closed_when_input_hash_is_invalid(tmp_path: Path) -> None:
    report_path = tmp_path / "release-readiness.json"
    current_commit = current_git_commit()
    assert current_commit
    report_path.write_text(
        json.dumps(
            {
                "status": "passed",
                "provenance": {
                    "commitSha": current_commit,
                    "expectedCommitSha": current_commit,
                    "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "inputHash": "not-a-sha256",
                },
            }
        ),
        encoding="utf-8",
    )

    summary = admin_router.ops_release_readiness_summary(
        Settings(release_readiness_report_path=str(report_path))
    )

    assert summary is not None
    assert summary.status == "blocked"
    assert summary.provenance is not None
    assert summary.provenance.reason == "invalid_input_hash"


async def test_admin_token_cost_queries_session_daily_and_top_expensive_runs() -> None:
    ledger = InMemoryUsageLedger(
        records=[
            UsageLedgerRecord(
                id="usage_1",
                tenant_id="tenant_1",
                run_id="session-a-turn-1",
                provider="openai",
                model="gpt-5-mini",
                step_type="model",
                prompt_tokens=1000,
                completion_tokens=200,
                total_tokens=1200,
                estimated_cost_usd=Decimal("0.00027000"),
                occurred_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
            ),
            UsageLedgerRecord(
                id="usage_2",
                tenant_id="tenant_1",
                run_id="session-b-turn-1",
                provider="anthropic",
                model="claude-sonnet-4",
                step_type="model",
                prompt_tokens=5000,
                completion_tokens=1000,
                total_tokens=6000,
                estimated_cost_usd=Decimal("0.02000000"),
                occurred_at=datetime(2026, 6, 26, 2, 0, tzinfo=UTC),
            ),
            UsageLedgerRecord(
                id="usage_3",
                tenant_id="tenant_2",
                run_id="session-a-turn-tenant-2",
                provider="openai",
                model="gpt-5-mini",
                step_type="model",
                prompt_tokens=9000,
                completion_tokens=9000,
                total_tokens=18000,
                estimated_cost_usd=Decimal("9.00000000"),
                occurred_at=datetime(2026, 6, 26, 3, 0, tzinfo=UTC),
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(usage_ledger=ledger)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get(
            "/api/admin/token-cost/by-session",
            params={"sessionId": "session-a"},
            headers=USER_HEADERS,
        )
        by_session = await client.get(
            "/api/admin/token-cost/by-session",
            params={"sessionId": "session-a"},
            headers=MANAGER_HEADERS,
        )
        daily = await client.get(
            "/v1/admin/token-cost/daily",
            params={"days": 30},
            headers=MANAGER_HEADERS,
        )
        top = await client.get(
            "/api/admin/token-cost/top-expensive",
            params={"days": 30, "limit": 1},
            headers=MANAGER_HEADERS,
        )

    assert forbidden.status_code == 403
    assert by_session.status_code == 200
    assert by_session.json() == [
        {
            "runId": "session-a-turn-1",
            "provider": "openai",
            "model": "gpt-5-mini",
            "stepType": "model",
            "promptTokens": 1000,
            "completionTokens": 200,
            "totalTokens": 1200,
            "estimatedCostUsd": "0.00027000",
            "occurredAt": 1782435600000,
        }
    ]
    assert daily.status_code == 200
    assert daily.json() == [
        {
            "day": "2026-06-26",
            "model": "claude-sonnet-4",
            "promptTokens": 5000,
            "completionTokens": 1000,
            "totalTokens": 6000,
            "totalCostUsd": "0.02000000",
        },
        {
            "day": "2026-06-26",
            "model": "gpt-5-mini",
            "promptTokens": 1000,
            "completionTokens": 200,
            "totalTokens": 1200,
            "totalCostUsd": "0.00027000",
        },
    ]
    assert top.status_code == 200
    assert top.json() == [
        {
            "runId": "session-b-turn-1",
            "totalTokens": 6000,
            "totalCostUsd": "0.02000000",
            "model": "claude-sonnet-4",
            "occurredAt": 1782439200000,
        }
    ]


async def test_admin_users_usage_ports_top_cost_daily_and_model_breakdowns() -> None:
    run_store = FakeTraceRunStore(
        runs=[
            trace_run(
                "run_1",
                tenant_id="tenant_1",
                status="completed",
                trace_id="trace_1",
                duration_ms=100,
                user_id="user_a",
                channel="api",
            ),
            trace_run(
                "run_2",
                tenant_id="tenant_1",
                status="completed",
                trace_id="trace_2",
                duration_ms=300,
                user_id="user_a",
                channel="api",
            ),
            trace_run(
                "run_3",
                tenant_id="tenant_1",
                status="failed",
                trace_id="trace_3",
                duration_ms=500,
                user_id="user_b",
                channel="slack",
            ),
            trace_run(
                "run_other",
                tenant_id="tenant_2",
                status="completed",
                trace_id="trace_other",
                duration_ms=999,
                user_id="user_other",
                channel="api",
            ),
        ],
        events={},
    )
    ledger = InMemoryUsageLedger(
        records=[
            UsageLedgerRecord(
                id="usage_1",
                tenant_id="tenant_1",
                run_id="run_1",
                provider="openai",
                model="gpt-5-mini",
                step_type="model",
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
                estimated_cost_usd=Decimal("0.0100"),
                occurred_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
            ),
            UsageLedgerRecord(
                id="usage_2",
                tenant_id="tenant_1",
                run_id="run_2",
                provider="anthropic",
                model="claude-sonnet-4",
                step_type="model",
                prompt_tokens=200,
                completion_tokens=40,
                total_tokens=240,
                estimated_cost_usd=Decimal("0.0200"),
                occurred_at=datetime(2026, 6, 26, 2, 0, tzinfo=UTC),
            ),
            UsageLedgerRecord(
                id="usage_3",
                tenant_id="tenant_1",
                run_id="run_3",
                provider="openai",
                model="gpt-5-mini",
                step_type="model",
                prompt_tokens=300,
                completion_tokens=60,
                total_tokens=360,
                estimated_cost_usd=Decimal("0.0300"),
                occurred_at=datetime(2026, 6, 25, 1, 0, tzinfo=UTC),
            ),
            UsageLedgerRecord(
                id="usage_other",
                tenant_id="tenant_2",
                run_id="run_other",
                provider="openai",
                model="gpt-5-mini",
                step_type="model",
                prompt_tokens=999,
                completion_tokens=999,
                total_tokens=1998,
                estimated_cost_usd=Decimal("9.9900"),
                occurred_at=datetime(2026, 6, 26, 3, 0, tzinfo=UTC),
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(run_store=run_store, usage_ledger=ledger)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/users/usage/top", headers=USER_HEADERS)
        top = await client.get(
            "/api/admin/users/usage/top",
            params={"days": 30, "limit": 2},
            headers=MANAGER_HEADERS,
        )
        cost = await client.get(
            "/v1/admin/users/usage/cost",
            params={"days": 30, "limit": 2},
            headers=MANAGER_HEADERS,
        )
        daily = await client.get(
            "/api/admin/users/usage/daily",
            params={"days": 30},
            headers=MANAGER_HEADERS,
        )
        by_model = await client.get(
            "/v1/admin/users/usage/by-model",
            params={"days": 30},
            headers=MANAGER_HEADERS,
        )

    assert forbidden.status_code == 403
    assert top.status_code == 200
    assert top.json() == [
        {
            "userLabel": "user_a",
            "requests": 2,
            "tokens": 360,
            "costUsd": 0.03,
            "lastActivity": 1782435600300,
        },
        {
            "userLabel": "user_b",
            "requests": 1,
            "tokens": 360,
            "costUsd": 0.03,
            "lastActivity": 1782435600500,
        },
    ]
    assert cost.status_code == 200
    assert cost.json() == [
        {
            "user_id": "user_a",
            "session_count": 2,
            "total_tokens": 360,
            "total_cost_usd": "0.0300",
            "avg_latency_ms": 200,
            "last_activity": "2026-06-26T01:00:00.300+00:00",
        },
        {
            "user_id": "user_b",
            "session_count": 1,
            "total_tokens": 360,
            "total_cost_usd": "0.0300",
            "avg_latency_ms": 500,
            "last_activity": "2026-06-26T01:00:00.500+00:00",
        },
    ]
    assert daily.status_code == 200
    assert daily.json() == [
        {
            "day": "2026-06-26",
            "session_count": 3,
            "total_tokens": 720,
            "total_cost_usd": "0.0600",
            "unique_users": 2,
        }
    ]
    assert by_model.status_code == 200
    assert by_model.json() == [
        {
            "model": "gpt-5-mini",
            "provider": "openai",
            "call_count": 2,
            "prompt_tokens": 400,
            "completion_tokens": 80,
            "total_tokens": 480,
            "total_cost_usd": "0.0400",
            "last_activity": "2026-06-26T01:00:00+00:00",
        },
        {
            "model": "claude-sonnet-4",
            "provider": "anthropic",
            "call_count": 1,
            "prompt_tokens": 200,
            "completion_tokens": 40,
            "total_tokens": 240,
            "total_cost_usd": "0.0200",
            "last_activity": "2026-06-26T02:00:00+00:00",
        },
    ]


async def test_admin_sessions_manage_tenant_sessions_without_owner_filter() -> None:
    recent_session_created_at = datetime.now(UTC) - timedelta(hours=1)
    run_1 = trace_run(
        "run_1",
        tenant_id="tenant_1",
        status="completed",
        trace_id="trace_1",
        duration_ms=100,
        user_id="user_1",
        created_at=recent_session_created_at,
    )
    run_2 = trace_run(
        "run_2",
        tenant_id="tenant_1",
        status="failed",
        trace_id="trace_2",
        duration_ms=200,
        user_id="user_2",
        created_at=recent_session_created_at,
    )
    store = FakeTraceRunStore(runs=[run_1, run_2], events={})
    app = create_app()
    app.state.reactor = FakeContainer(run_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/sessions", headers=USER_HEADERS)
        overview = await client.get("/api/admin/sessions/overview", headers=MANAGER_HEADERS)
        listed = await client.get("/api/admin/sessions", headers=MANAGER_HEADERS)
        detail = await client.get("/api/admin/sessions/run_2", headers=MANAGER_HEADERS)
        exported = await client.get(
            "/api/admin/sessions/run_1/export",
            params={"format": "markdown"},
            headers=ADMIN_HEADERS,
        )
        users = await client.get("/api/admin/users", headers=MANAGER_HEADERS)
        user_sessions = await client.get(
            "/api/admin/users/user_2/sessions",
            headers=MANAGER_HEADERS,
        )
        tag = await client.post(
            "/api/admin/sessions/run_1/tags",
            headers=ADMIN_HEADERS,
            json={"label": "important", "comment": "review"},
        )
        deleted = await client.delete("/api/admin/sessions/run_1", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert overview.status_code == 200
    assert overview.json()["totalSessions"] == 2
    assert overview.json()["statusCounts"] == {"completed": 1, "failed": 1}
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    assert detail.status_code == 200
    assert detail.json()["sessionId"] == "run_2"
    assert exported.status_code == 200
    assert "## assistant" in exported.text
    assert users.status_code == 200
    assert users.json()["total"] == 2
    assert user_sessions.status_code == 200
    assert user_sessions.json()["items"][0]["sessionId"] == "run_2"
    assert tag.status_code == 200
    assert tag.json()["label"] == "important"
    assert deleted.status_code == 204
    assert store.deleted == {"run_1"}


async def test_platform_pricing_api_lists_and_upserts_model_pricing_with_audit() -> None:
    pricing_store = FakeModelPricingStore(
        [
            ModelPricing(
                id="pricing_old",
                provider="openai",
                model="gpt-5-mini",
                prompt_price_per_1m=Decimal("1.25"),
                completion_price_per_1m=Decimal("10.00"),
                effective_from=datetime(2026, 6, 1, tzinfo=UTC),
            )
        ]
    )
    audit_store = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        model_pricing_store=pricing_store,
        admin_audit_store=audit_store,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/platform/pricing", headers=USER_HEADERS)
        listed = await client.get("/api/admin/platform/pricing", headers=MANAGER_HEADERS)
        saved = await client.post(
            "/v1/admin/platform/pricing",
            headers=ADMIN_HEADERS,
            json={
                "id": "pricing_new",
                "provider": "anthropic",
                "model": "claude-sonnet-4",
                "promptPricePer1m": "3.00",
                "completionPricePer1m": "15.00",
                "cachedInputPricePer1m": "0.30",
                "reasoningPricePer1m": "1.00",
                "batchPromptPricePer1m": "1.50",
                "batchCompletionPricePer1m": "7.50",
                "effectiveFrom": "2026-06-26T00:00:00+00:00",
                "effectiveTo": None,
            },
        )

    assert forbidden.status_code == 403
    assert listed.status_code == 200
    assert listed.json() == [
        {
            "id": "pricing_old",
            "provider": "openai",
            "model": "gpt-5-mini",
            "promptPricePer1m": "1.25",
            "completionPricePer1m": "10.00",
            "cachedInputPricePer1m": "0",
            "reasoningPricePer1m": "0",
            "batchPromptPricePer1m": "0",
            "batchCompletionPricePer1m": "0",
            "effectiveFrom": "2026-06-01T00:00:00+00:00",
            "effectiveTo": None,
        }
    ]
    assert saved.status_code == 200
    assert saved.json()["id"] == "pricing_new"
    assert saved.json()["promptPricePer1m"] == "3.00"
    assert pricing_store.records["pricing_new"].model == "claude-sonnet-4"
    assert audit_store.saved[0].category == "platform_pricing"
    assert audit_store.saved[0].resource_type == "model_pricing"
    assert audit_store.saved[0].resource_id == "pricing_new"


async def test_admin_model_registry_lists_effective_pricing_and_default_model() -> None:
    pricing_store = FakeModelPricingStore(
        [
            ModelPricing(
                id="pricing_default",
                provider="openai",
                model="gpt-5-mini",
                prompt_price_per_1m=Decimal("1.25"),
                completion_price_per_1m=Decimal("10.00"),
                effective_from=datetime(2026, 6, 1, tzinfo=UTC),
            ),
            ModelPricing(
                id="pricing_future",
                provider="openai",
                model="gpt-5-mini",
                prompt_price_per_1m=Decimal("9.99"),
                completion_price_per_1m=Decimal("99.99"),
                effective_from=datetime.now(UTC) + timedelta(days=30),
            ),
            ModelPricing(
                id="pricing_alt",
                provider="anthropic",
                model="claude-sonnet-5",
                prompt_price_per_1m=Decimal("3.00"),
                completion_price_per_1m=Decimal("15.00"),
                effective_from=datetime(2026, 6, 1, tzinfo=UTC),
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(model_pricing_store=pricing_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/models", headers=USER_HEADERS)
        response = await client.get("/v1/admin/models", headers=MANAGER_HEADERS)

    assert forbidden.status_code == 403
    assert response.status_code == 200
    assert response.json() == [
        {
            "name": "claude-sonnet-5",
            "provider": "anthropic",
            "inputPricePerMillionTokens": "3.00",
            "outputPricePerMillionTokens": "15.00",
            "isDefault": False,
        },
        {
            "name": "gpt-5-mini",
            "provider": "openai",
            "inputPricePerMillionTokens": "1.25",
            "outputPricePerMillionTokens": "10.00",
            "isDefault": True,
        },
    ]


async def test_platform_alert_api_ports_rules_evaluate_list_and_resolve() -> None:
    alert_store = InMemoryAlertRuleStore(metrics={"tenant_1": {"error_rate": 0.12}})
    alert_store.save_rule(
        AlertRule(
            id="rule_other",
            tenant_id="tenant_2",
            name="Other tenant rule",
            metric="error_rate",
            threshold=0.5,
        )
    )
    alert_store.save_alert(
        AlertInstance(
            id="alert_other",
            rule_id="rule_other",
            tenant_id="tenant_2",
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.ACTIVE,
            message="other tenant alert",
            metric_value=0.9,
            threshold=0.5,
            fired_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
        )
    )
    app = create_app()
    app.state.reactor = FakeContainer(alert_rule_store=alert_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/platform/alerts/rules", headers=USER_HEADERS)
        created = await client.post(
            "/api/admin/platform/alerts/rules",
            headers=ADMIN_HEADERS,
            json={
                "id": "rule_1",
                "tenantId": "tenant_2",
                "name": "High error rate",
                "description": "Error budget risk",
                "type": "STATIC_THRESHOLD",
                "severity": "CRITICAL",
                "metric": "error_rate",
                "threshold": 0.05,
                "windowMinutes": 15,
                "enabled": True,
                "platformOnly": False,
            },
        )
        listed = await client.get("/v1/admin/platform/alerts/rules", headers=ADMIN_HEADERS)
        evaluated = await client.post("/api/admin/platform/alerts/evaluate", headers=ADMIN_HEADERS)
        active = await client.get("/v1/admin/platform/alerts", headers=ADMIN_HEADERS)
        alert_id = active.json()[0]["id"]
        resolved = await client.post(
            f"/api/admin/platform/alerts/{alert_id}/resolve",
            headers=ADMIN_HEADERS,
        )
        cross_tenant_resolve = await client.post(
            "/api/admin/platform/alerts/alert_other/resolve",
            headers=ADMIN_HEADERS,
        )
        cross_tenant_delete_rule = await client.delete(
            "/api/admin/platform/alerts/rules/rule_other",
            headers=ADMIN_HEADERS,
        )
        active_after_resolve = await client.get("/api/admin/platform/alerts", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert created.status_code == 200
    assert created.json()["id"] == "rule_1"
    assert created.json()["tenantId"] == "tenant_1"
    assert listed.status_code == 200
    assert [rule["id"] for rule in listed.json()] == ["rule_1"]
    assert evaluated.status_code == 200
    assert evaluated.json() == {"status": "evaluation complete", "createdAlerts": 1}
    assert active.status_code == 200
    assert active.json()[0]["ruleId"] == "rule_1"
    assert active.json()[0]["severity"] == "CRITICAL"
    assert active.json()[0]["status"] == "ACTIVE"
    assert active.json()[0]["metricValue"] == 0.12
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"
    assert cross_tenant_resolve.status_code == 404
    assert alert_store.alerts["alert_other"].status == AlertStatus.ACTIVE
    assert cross_tenant_delete_rule.status_code == 404
    assert "rule_other" in alert_store.rules
    assert active_after_resolve.json() == []


async def test_platform_alert_rule_rejects_invalid_severity_as_bad_request() -> None:
    alert_store = InMemoryAlertRuleStore()
    app = create_app()
    app.state.reactor = FakeContainer(alert_rule_store=alert_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/admin/platform/alerts/rules",
            headers=ADMIN_HEADERS,
            json={
                "id": "rule_bad",
                "name": "Bad severity",
                "type": "STATIC_THRESHOLD",
                "severity": "PAGE_EVERYONE",
                "metric": "error_rate",
                "threshold": 0.05,
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid alert severity: PAGE_EVERYONE"
    assert alert_store.rules == {}


async def test_platform_alert_delete_returns_404_for_missing_rule() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(alert_rule_store=InMemoryAlertRuleStore())
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.delete(
            "/v1/admin/platform/alerts/rules/missing",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Alert rule not found: missing"


async def test_admin_rag_stats_requires_persistence_and_returns_collection_stats() -> None:
    unavailable_transport = ASGITransport(app=create_app())
    async with AsyncClient(
        transport=unavailable_transport,
        base_url="http://testserver",
    ) as client:
        unavailable = await client.get("/v1/admin/rag/stats", headers=ADMIN_HEADERS)

    app = create_app()
    app.state.reactor = FakeContainer(
        rag_document_sink=FakeRagDocumentSink(
            [
                RagStatsRecord(
                    collection="docs",
                    source_count=2,
                    document_count=3,
                    chunk_count=9,
                    embedded_chunk_count=7,
                )
            ]
        )
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/admin/rag/stats", headers=ADMIN_HEADERS)

    assert unavailable.status_code == 503
    assert unavailable.json()["detail"] == "RAG diagnostics persistence is not configured"
    assert response.status_code == 200
    assert response.json() == {
        "tenantId": "tenant_1",
        "collections": [
            {
                "collection": "docs",
                "sourceCount": 2,
                "documentCount": 3,
                "chunkCount": 9,
                "embeddedChunkCount": 7,
                "embeddingCoveragePercent": 77,
            }
        ],
        "totalSources": 2,
        "totalDocuments": 3,
        "totalChunks": 9,
        "embeddedChunks": 7,
        "embeddingCoveragePercent": 77,
    }


async def test_policy_rag_seed_ports_legacy_bulk_seed_contract() -> None:
    sink = FakeRagDocumentSink([])
    app = create_app()
    app.state.reactor = FakeContainer(rag_document_sink=sink)
    transport = ASGITransport(app=app)
    body = {
        "entries": [
            {
                "key": "leave-90-days",
                "title": "출산휴가 규정",
                "content": "출산휴가는 사내 인사규정 제 3조에 따라 총 90일을 보장합니다.",
                "category": "hr",
                "spaceKey": "HR",
                "url": "https://wiki.example/policies/leave-90-days",
            }
        ]
    }

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.post(
            "/api/admin/rag/seed-policy",
            headers=MANAGER_HEADERS,
            json=body,
        )
        seeded = await client.post(
            "/v1/admin/rag/seed-policy",
            headers=ADMIN_HEADERS,
            json=body,
        )

    assert forbidden.status_code == 403
    assert seeded.status_code == 200
    assert seeded.json()["documentCount"] == 1
    assert seeded.json()["chunkCount"] == 1
    assert seeded.json()["keys"] == ["leave-90-days"]
    assert seeded.json()["durationMs"] >= 0
    assert sink.sources[0].collection == "policy-seed"
    assert sink.sources[0].source_type == "policy-seed"
    assert sink.sources[0].metadata["key"] == "leave-90-days"
    assert sink.documents[0].title == "출산휴가 규정"
    assert sink.chunks[0].content == body["entries"][0]["content"]
    assert sink.chunks[0].metadata["space_key"] == "HR"


async def test_admin_rag_analytics_ports_legacy_status_and_channel_queries() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(
        rag_document_sink=FakeRagDocumentSink(
            [
                RagStatsRecord(
                    collection="slack-faq",
                    source_count=3,
                    document_count=3,
                    chunk_count=5,
                    embedded_chunk_count=4,
                )
            ],
            status_rows=[
                {
                    "status": "INGESTED",
                    "count": 3,
                    "latest_captured": "2026-06-26T03:00:00+00:00",
                }
            ],
            channel_rows=[
                {
                    "channel": "C123",
                    "candidate_count": 2,
                    "ingested": 2,
                    "pending": 0,
                    "rejected": 0,
                },
                {
                    "channel": "unknown",
                    "candidate_count": 1,
                    "ingested": 1,
                    "pending": 0,
                    "rejected": 0,
                },
            ],
        )
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/rag-analytics/status", headers=USER_HEADERS)
        status_response = await client.get("/api/admin/rag-analytics/status", headers=ADMIN_HEADERS)
        channel_response = await client.get(
            "/v1/admin/rag-analytics/by-channel",
            params={"days": 30},
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert status_response.status_code == 200
    assert status_response.json() == [
        {"status": "INGESTED", "count": 3, "latest_captured": "2026-06-26T03:00:00+00:00"}
    ]
    assert channel_response.status_code == 200
    assert channel_response.json() == [
        {
            "channel": "C123",
            "candidate_count": 2,
            "ingested": 2,
            "pending": 0,
            "rejected": 0,
        },
        {
            "channel": "unknown",
            "candidate_count": 1,
            "ingested": 1,
            "pending": 0,
            "rejected": 0,
        },
    ]


async def test_platform_cache_api_ports_stats_and_invalidation() -> None:
    unavailable_transport = ASGITransport(app=create_app())
    async with AsyncClient(
        transport=unavailable_transport,
        base_url="http://testserver",
    ) as client:
        unavailable = await client.get("/api/admin/platform/cache/stats", headers=ADMIN_HEADERS)

    cache = FakeResponseCache()
    cache.put("tenant_1:chat:one", "cached response")
    cache.put("tenant_1:chat:two", "cached response")
    cache.record_exact_hit()
    cache.record_semantic_hit()
    cache.record_miss()
    audit_store = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(response_cache=cache, admin_audit_store=audit_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.post("/api/admin/platform/cache/invalidate", headers=USER_HEADERS)
        stats = await client.get("/api/admin/platform/cache/stats", headers=MANAGER_HEADERS)
        key_result = await client.post(
            "/v1/admin/platform/cache/invalidate-key",
            headers=ADMIN_HEADERS,
            json={"key": "tenant_1:chat:one"},
        )
        pattern_result = await client.post(
            "/api/admin/platform/cache/invalidate-by-pattern",
            headers=ADMIN_HEADERS,
            json={"pattern": "tenant_1:chat:*"},
        )
        all_result = await client.post(
            "/v1/admin/platform/cache/invalidate",
            headers=ADMIN_HEADERS,
        )

    assert unavailable.status_code == 200
    assert unavailable.json()["enabled"] is False
    assert unavailable.json()["cacheEnabled"] is False
    assert forbidden.status_code == 403
    assert stats.status_code == 200
    assert stats.json() == {
        "enabled": True,
        "semanticEnabled": False,
        "totalExactHits": 1,
        "totalSemanticHits": 1,
        "totalMisses": 1,
        "hitRate": 0.666667,
        "config": {
            "ttlMinutes": 0,
            "maxSize": 2,
            "similarityThreshold": 0.0,
            "maxCandidates": 0,
            "cacheableTemperature": 0.0,
        },
        "cacheEnabled": True,
    }
    assert key_result.status_code == 200
    assert key_result.json() == {"invalidated": True, "cacheEnabled": True}
    assert pattern_result.status_code == 200
    assert pattern_result.json() == {"invalidatedCount": 1, "cacheEnabled": True}
    assert all_result.status_code == 200
    assert all_result.json() == {
        "invalidated": True,
        "cacheEnabled": True,
        "message": "Response cache invalidated",
    }
    assert [log.action for log in audit_store.saved] == [
        AdminAuditAction.INVALIDATE_KEY,
        AdminAuditAction.INVALIDATE_PATTERN,
        AdminAuditAction.INVALIDATE_ALL,
    ]


async def test_platform_health_and_vectorstore_stats_port_legacy_dashboard() -> None:
    cache = FakeResponseCache()
    cache.put("tenant_1:chat:one", "cached response")
    cache.record_exact_hit()
    cache.record_miss()
    alert_store = InMemoryAlertRuleStore()
    alert_store.save_alert(
        AlertInstance(
            id="alert_1",
            rule_id="rule_1",
            tenant_id="tenant_1",
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.ACTIVE,
            message="error rate above threshold",
            metric_value=0.15,
            threshold=0.1,
            fired_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
        )
    )
    app = create_app()
    app.state.reactor = FakeContainer(
        alert_rule_store=alert_store,
        response_cache=cache,
        rag_document_sink=FakeRagDocumentSink(
            [
                RagStatsRecord(
                    collection="docs",
                    source_count=2,
                    document_count=3,
                    chunk_count=9,
                    embedded_chunk_count=7,
                )
            ]
        ),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/platform/health", headers=USER_HEADERS)
        health = await client.get("/api/admin/platform/health", headers=MANAGER_HEADERS)
        vector_stats = await client.get(
            "/v1/admin/platform/vectorstore/stats",
            headers=MANAGER_HEADERS,
        )

    assert forbidden.status_code == 403
    assert health.status_code == 200
    assert health.json() == {
        "pipelineBufferUsage": 0.0,
        "pipelineDropRate": 0.0,
        "pipelineWriteLatencyMs": 0.0,
        "pipelineMetricsAvailable": False,
        "responseCacheEnabled": True,
        "activeAlerts": 1,
        "cacheExactHits": 1,
        "cacheSemanticHits": 0,
        "cacheMisses": 1,
    }
    assert vector_stats.status_code == 200
    assert vector_stats.json() == {"available": True, "documentCount": 3}


async def test_retention_policy_ports_legacy_defaults_update_and_audit() -> None:
    settings_store = FakeRuntimeSettingsStore(
        {
            "retention.session.days": "45",
            "retention.audit.days": "365",
            "retention.checkpoint.days": "21",
        }
    )
    audit_store = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        runtime_settings_store=settings_store,
        admin_audit_store=audit_store,
    )
    missing_store_app = create_app()
    transport = ASGITransport(app=app)
    missing_transport = ASGITransport(app=missing_store_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/retention", headers=MANAGER_HEADERS)
        current = await client.get("/api/admin/retention", headers=ADMIN_HEADERS)
        invalid = await client.put(
            "/v1/admin/retention",
            headers=ADMIN_HEADERS,
            json={"sessionRetentionDays": 0},
        )
        updated = await client.put(
            "/v1/admin/retention",
            headers=ADMIN_HEADERS,
            json={
                "sessionRetentionDays": 30,
                "conversationRetentionDays": 180,
                "metricRetentionDays": 60,
                "checkpointRetentionDays": 14,
            },
        )
    async with AsyncClient(transport=missing_transport, base_url="http://testserver") as client:
        missing_store = await client.put(
            "/api/admin/retention",
            headers=ADMIN_HEADERS,
            json={"sessionRetentionDays": 30},
        )

    assert forbidden.status_code == 403
    assert current.status_code == 200
    assert current.json() == {
        "sessionRetentionDays": 45,
        "conversationRetentionDays": 365,
        "auditRetentionDays": 365,
        "metricRetentionDays": 180,
        "checkpointRetentionDays": 21,
    }
    assert invalid.status_code == 422
    assert missing_store.status_code == 400
    assert missing_store.json()["detail"] == "RuntimeSettingsService is not configured"
    assert updated.status_code == 200
    assert updated.json() == {
        "sessionRetentionDays": 30,
        "conversationRetentionDays": 180,
        "auditRetentionDays": 365,
        "metricRetentionDays": 60,
        "checkpointRetentionDays": 14,
    }
    assert settings_store.values["retention.session.days"] == "30"
    assert settings_store.values["retention.conversation.days"] == "180"
    assert settings_store.values["retention.metric.days"] == "60"
    assert settings_store.values["retention.checkpoint.days"] == "14"
    assert audit_store.saved[-1].category == "retention"
    assert audit_store.saved[-1].action == AdminAuditAction.UPDATE


async def test_task_memory_maintenance_ports_legacy_purge_operations_and_audit() -> None:
    maintenance = FakeTaskMemoryMaintenance(expired_deleted=3, terminal_deleted=5)
    audit_store = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        task_memory_maintenance=maintenance,
        admin_audit_store=audit_store,
    )
    missing_service_app = create_app()
    transport = ASGITransport(app=app)
    missing_transport = ASGITransport(app=missing_service_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.post(
            "/api/admin/task-memory/maintenance/purge-expired",
            headers=MANAGER_HEADERS,
        )
        expired = await client.post(
            "/api/admin/task-memory/maintenance/purge-expired",
            headers=ADMIN_HEADERS,
        )
        invalid_days = await client.post(
            "/v1/admin/task-memory/maintenance/purge-terminal",
            params={"olderThanDays": 0},
            headers=ADMIN_HEADERS,
        )
        terminal = await client.post(
            "/v1/admin/task-memory/maintenance/purge-terminal",
            params={"olderThanDays": 7},
            headers=ADMIN_HEADERS,
        )
    async with AsyncClient(transport=missing_transport, base_url="http://testserver") as client:
        unavailable = await client.post(
            "/api/admin/task-memory/maintenance/purge-expired",
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert expired.status_code == 200
    assert expired.json() == {"deleted": 3, "actor": "admin_1"}
    assert invalid_days.status_code == 400
    assert invalid_days.json()["detail"] == "olderThanDays must be >= 1"
    assert terminal.status_code == 200
    terminal_body = terminal.json()
    assert terminal_body["deleted"] == 5
    assert terminal_body["cutoff"].endswith("+00:00")
    assert maintenance.expired_calls == 1
    assert len(maintenance.terminal_cutoffs) == 1
    assert unavailable.status_code == 400
    assert unavailable.json()["detail"] == "TaskMemoryMaintenance is not configured"
    assert [log.category for log in audit_store.saved] == [
        "task_memory_maintenance",
        "task_memory_maintenance",
    ]
    assert [log.action for log in audit_store.saved] == [
        AdminAuditAction.DELETE,
        AdminAuditAction.DELETE,
    ]
    assert audit_store.saved[0].resource_id == "purge_expired"
    assert audit_store.saved[1].resource_id == "purge_terminal"


async def test_platform_tenant_admin_lifecycle_requires_admin_and_records_audit() -> None:
    store = FakeTenantStore()
    audit_store = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(tenant_store=store, admin_audit_store=audit_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.post(
            "/api/admin/platform/tenants",
            json={"name": "Acme", "slug": "acme", "plan": "BUSINESS"},
            headers=MANAGER_HEADERS,
        )
        created = await client.post(
            "/api/admin/platform/tenants",
            json={"name": "Acme", "slug": "acme", "plan": "BUSINESS"},
            headers=ADMIN_HEADERS,
        )
        listed = await client.get("/v1/admin/platform/tenants", headers=ADMIN_HEADERS)
        tenant_id = created.json()["id"]
        fetched = await client.get(
            f"/api/admin/platform/tenants/{tenant_id}",
            headers=ADMIN_HEADERS,
        )
        suspended = await client.post(
            f"/v1/admin/platform/tenants/{tenant_id}/suspend",
            headers=ADMIN_HEADERS,
        )
        activated = await client.post(
            f"/api/admin/platform/tenants/{tenant_id}/activate",
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "permission required: tenant:write"
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Acme"
    assert body["slug"] == "acme"
    assert body["plan"] == "BUSINESS"
    assert body["status"] == "ACTIVE"
    assert body["quota"]["maxRequestsPerMonth"] == 100_000
    assert body["quota"]["maxMcpServers"] == 30
    assert listed.status_code == 200
    assert [item["slug"] for item in listed.json()] == ["acme"]
    assert fetched.status_code == 200
    assert fetched.json()["id"] == tenant_id
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "SUSPENDED"
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"
    assert [log.action for log in audit_store.saved] == [
        AdminAuditAction.CREATE,
        AdminAuditAction.SUSPEND,
        AdminAuditAction.ACTIVATE,
    ]
    assert audit_store.saved[0].category == "platform_tenant"
    assert audit_store.saved[0].resource_id == tenant_id


async def test_platform_tenant_analytics_summarizes_current_month_usage() -> None:
    tenant_store = FakeTenantStore()
    await tenant_store.save(
        TenantRecord(
            id="tenant_1",
            name="Acme",
            slug="acme",
            created_at=datetime(2026, 6, 27, 1, 0, tzinfo=UTC),
        )
    )
    await tenant_store.save(
        TenantRecord(
            id="tenant_2",
            name="Beta",
            slug="beta",
            created_at=datetime(2026, 6, 27, 2, 0, tzinfo=UTC),
        )
    )
    usage_ledger = InMemoryUsageLedger(
        records=[
            UsageLedgerRecord(
                tenant_id="tenant_1",
                run_id="run_1",
                provider="openai",
                model="gpt-5",
                step_type="model",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                estimated_cost_usd=Decimal("1.25"),
            ),
            UsageLedgerRecord(
                tenant_id="tenant_1",
                run_id="run_2",
                provider="openai",
                model="gpt-5",
                step_type="model",
                prompt_tokens=20,
                completion_tokens=10,
                total_tokens=30,
                estimated_cost_usd=Decimal("2.75"),
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(tenant_store=tenant_store, usage_ledger=usage_ledger)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get(
            "/api/admin/platform/tenants/analytics",
            headers=USER_HEADERS,
        )
        response = await client.get(
            "/v1/admin/platform/tenants/analytics",
            headers=MANAGER_HEADERS,
        )

    assert forbidden.status_code == 403
    assert response.status_code == 200
    assert response.json() == [
        {
            "tenantId": "tenant_2",
            "tenantName": "Beta",
            "plan": "FREE",
            "requests": 0,
            "cost": "0.00000000",
            "quotaUsagePercent": 0.0,
        },
        {
            "tenantId": "tenant_1",
            "tenantName": "Acme",
            "plan": "FREE",
            "requests": 2,
            "cost": "4.00000000",
            "quotaUsagePercent": 0.2,
        },
    ]


async def test_platform_user_admin_ports_lookup_role_update_and_self_downgrade_guard() -> None:
    users = FakeUserStore()
    audits = FakeAdminAuditStore()
    await users.save(
        UserRecord(
            id="admin_1",
            email="admin@example.com",
            name="Admin",
            password_hash=TEST_AUTH_DIGEST,
            role=UserRole.ADMIN,
            tenant_id="tenant_1",
            created_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
        )
    )
    await users.save(
        UserRecord(
            id="user_1",
            email="user@example.com",
            name="User One",
            password_hash=TEST_AUTH_DIGEST,
            role=UserRole.USER,
            tenant_id="tenant_1",
            created_at=datetime(2026, 6, 26, 2, 0, tzinfo=UTC),
        )
    )
    app = create_app()
    app.state.reactor = FakeContainer(user_store=users, admin_audit_store=audits)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get(
            "/api/admin/platform/users/by-email",
            params={"email": "user@example.com"},
            headers=MANAGER_HEADERS,
        )
        blank = await client.get(
            "/api/admin/platform/users/by-email",
            params={"email": "   "},
            headers=ADMIN_HEADERS,
        )
        missing = await client.get(
            "/api/admin/platform/users/by-email",
            params={"email": "missing@example.com"},
            headers=ADMIN_HEADERS,
        )
        found = await client.get(
            "/v1/admin/platform/users/by-email",
            params={"email": " user@example.com "},
            headers=ADMIN_HEADERS,
        )
        invalid_role = await client.post(
            "/api/admin/platform/users/user_1/role",
            headers=ADMIN_HEADERS,
            json={"role": "OWNER"},
        )
        updated = await client.post(
            "/v1/admin/platform/users/user_1/role",
            headers=ADMIN_HEADERS,
            json={"role": "ADMIN_DEVELOPER"},
        )
        self_downgrade = await client.post(
            "/api/admin/platform/users/admin_1/role",
            headers=ADMIN_HEADERS,
            json={"role": "USER"},
        )

    assert forbidden.status_code == 403
    assert blank.status_code == 400
    assert blank.json()["detail"] == "email is required"
    assert missing.status_code == 404
    assert missing.json()["detail"] == "User not found: missing@example.com"
    assert found.status_code == 200
    assert found.json() == {
        "id": "user_1",
        "email": "user@example.com",
        "name": "User One",
        "role": "USER",
        "adminScope": None,
        "createdAt": "2026-06-26T02:00:00+00:00",
    }
    assert invalid_role.status_code == 400
    assert invalid_role.json()["detail"] == "invalid role: OWNER"
    assert updated.status_code == 200
    assert updated.json()["role"] == "ADMIN_DEVELOPER"
    assert updated.json()["adminScope"] == "DEVELOPER"
    updated_user = await users.find_by_id("user_1")
    assert updated_user is not None
    assert updated_user.role == UserRole.ADMIN_DEVELOPER
    assert self_downgrade.status_code == 400
    assert self_downgrade.json()["detail"] == "cannot remove developer scope from current actor"
    assert audits.saved[-1].category == "platform_user"
    assert audits.saved[-1].action == AdminAuditAction.ROLE_UPDATE
    assert audits.saved[-1].detail == "role:USER->ADMIN_DEVELOPER"


async def test_platform_tenant_admin_validates_slug_plan_and_missing_store() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(tenant_store=FakeTenantStore())
    missing_store_app = create_app()
    transport = ASGITransport(app=app)
    missing_transport = ASGITransport(app=missing_store_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        invalid_slug = await client.post(
            "/api/admin/platform/tenants",
            json={"name": "Bad Slug", "slug": "Bad Slug", "plan": "FREE"},
            headers=ADMIN_HEADERS,
        )
        invalid_plan = await client.post(
            "/api/admin/platform/tenants",
            json={"name": "Bad Plan", "slug": "bad-plan", "plan": "GOLD"},
            headers=ADMIN_HEADERS,
        )
        ok = await client.post(
            "/api/admin/platform/tenants",
            json={"name": "Dup", "slug": "dup", "plan": "FREE"},
            headers=ADMIN_HEADERS,
        )
        duplicate = await client.post(
            "/api/admin/platform/tenants",
            json={"name": "Dup 2", "slug": "dup", "plan": "STARTER"},
            headers=ADMIN_HEADERS,
        )
    async with AsyncClient(transport=missing_transport, base_url="http://testserver") as client:
        missing = await client.get("/api/admin/platform/tenants", headers=ADMIN_HEADERS)

    assert invalid_slug.status_code == 400
    assert invalid_slug.json()["detail"] == "invalid tenant slug"
    assert invalid_plan.status_code == 400
    assert invalid_plan.json()["detail"] == "invalid tenant plan: GOLD"
    assert ok.status_code == 201
    assert duplicate.status_code == 400
    assert duplicate.json()["detail"] == "tenant slug already exists: dup"
    assert missing.status_code == 503
    assert missing.json()["detail"] == "tenant persistence is not configured"


async def test_tenant_admin_quota_slo_and_alerts_are_scoped_to_current_tenant() -> None:
    tenant_store = FakeTenantStore()
    tenant = await tenant_store.save(
        TenantRecord(
            id="tenant_1",
            name="Acme",
            slug="acme",
            slo_availability=0.999,
            slo_latency_p99_ms=5000,
        )
    )
    await tenant_store.save(TenantRecord(id="tenant_2", name="Other", slug="other"))
    ledger = InMemoryUsageLedger(
        records=[
            UsageLedgerRecord(
                tenant_id="tenant_1",
                run_id="run_1",
                provider="openai",
                model="gpt-5-mini",
                step_type="model",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                estimated_cost_usd=Decimal("0.001"),
                occurred_at=datetime.now(UTC),
            ),
            UsageLedgerRecord(
                tenant_id="tenant_2",
                run_id="run_2",
                provider="openai",
                model="gpt-5-mini",
                step_type="model",
                prompt_tokens=900,
                completion_tokens=900,
                total_tokens=1800,
                estimated_cost_usd=Decimal("9"),
                occurred_at=datetime.now(UTC),
            ),
        ]
    )
    alert_store = InMemoryAlertRuleStore(
        alerts=[
            AlertInstance(
                id="alert_1",
                rule_id="rule_1",
                tenant_id="tenant_1",
                severity=AlertSeverity.WARNING,
                message="Latency high",
                metric_value=5200,
                threshold=tenant.slo_latency_p99_ms,
                fired_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
            ),
            AlertInstance(
                id="alert_2",
                rule_id="rule_2",
                tenant_id="tenant_2",
                severity=AlertSeverity.CRITICAL,
                message="Other tenant",
                fired_at=datetime(2026, 6, 26, 2, 0, tzinfo=UTC),
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(
        tenant_store=tenant_store,
        usage_ledger=ledger,
        alert_rule_store=alert_store,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/tenant/quota", headers=USER_HEADERS)
        quota = await client.get("/api/admin/tenant/quota", headers=MANAGER_HEADERS)
        slo = await client.get(
            "/v1/admin/tenant/slo",
            headers={**MANAGER_HEADERS, "X-Reactor-Tenant-Id": "acme"},
        )
        alerts = await client.get("/api/admin/tenant/alerts", headers=MANAGER_HEADERS)

    assert forbidden.status_code == 403
    assert quota.status_code == 200
    assert quota.json() == {
        "tenantId": "tenant_1",
        "quota": {
            "maxRequestsPerMonth": 1000,
            "maxTokensPerMonth": 1000000,
            "maxUsers": 5,
            "maxAgents": 3,
            "maxMcpServers": 5,
        },
        "usage": {
            "requests": 1,
            "tokens": 150,
            "costUsd": "0.00100000",
        },
        "requestUsagePercent": 0.1,
        "tokenUsagePercent": 0.015,
    }
    assert slo.status_code == 200
    assert slo.json() == {
        "tenantId": "tenant_1",
        "sloAvailability": 0.999,
        "sloLatencyP99Ms": 5000,
        "currentAvailability": 1.0,
        "latencyP99Ms": 0,
        "errorBudgetRemaining": 1.0,
    }
    assert alerts.status_code == 200
    assert [alert["id"] for alert in alerts.json()] == ["alert_1"]
    assert alerts.json()[0]["message"] == "Latency high"


async def test_tenant_admin_dashboards_aggregate_runs_usage_and_tools() -> None:
    tenant_store = FakeTenantStore()
    await tenant_store.save(TenantRecord(id="tenant_1", name="Acme", slug="acme"))
    current_month = datetime.now(UTC)
    run_store = FakeTraceRunStore(
        runs=[
            trace_run(
                "run_1",
                tenant_id="tenant_1",
                status="completed",
                trace_id="trace_1",
                duration_ms=120,
                user_id="user_a",
                channel="slack",
                model="gpt-5-mini",
            ),
            trace_run(
                "run_2",
                tenant_id="tenant_1",
                status="failed",
                trace_id="trace_2",
                duration_ms=360,
                user_id="user_b",
                channel="api",
                model="claude-sonnet-4",
                error_class="tool_timeout",
            ),
            trace_run(
                "run_other",
                tenant_id="tenant_2",
                status="completed",
                trace_id="trace_other",
                duration_ms=999,
            ),
        ],
        events={},
    )
    ledger = InMemoryUsageLedger(
        records=[
            UsageLedgerRecord(
                tenant_id="tenant_1",
                run_id="run_1",
                provider="openai",
                model="gpt-5-mini",
                step_type="model",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                estimated_cost_usd=Decimal("0.001"),
                occurred_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
            ),
            UsageLedgerRecord(
                tenant_id="tenant_1",
                run_id="run_2",
                provider="anthropic",
                model="claude-sonnet-4",
                step_type="model",
                prompt_tokens=200,
                completion_tokens=100,
                total_tokens=300,
                estimated_cost_usd=Decimal("0.002"),
                occurred_at=datetime(2026, 6, 26, 1, 30, tzinfo=UTC),
            ),
            UsageLedgerRecord(
                tenant_id="tenant_2",
                run_id="run_other",
                provider="openai",
                model="gpt-5-mini",
                step_type="model",
                prompt_tokens=999,
                completion_tokens=999,
                total_tokens=1998,
                estimated_cost_usd=Decimal("9"),
                occurred_at=datetime(2026, 6, 26, 2, 0, tzinfo=UTC),
            ),
            UsageLedgerRecord(
                tenant_id="tenant_1",
                run_id="run_current_1",
                provider="openai",
                model="gpt-5-mini",
                step_type="model",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                estimated_cost_usd=Decimal("0.001"),
                occurred_at=current_month,
            ),
            UsageLedgerRecord(
                tenant_id="tenant_1",
                run_id="run_current_2",
                provider="anthropic",
                model="claude-sonnet-4",
                step_type="model",
                prompt_tokens=20,
                completion_tokens=10,
                total_tokens=30,
                estimated_cost_usd=Decimal("0.002"),
                occurred_at=current_month,
            ),
        ]
    )
    tool_store = FakeToolInvocationStore(
        [
            tool_invocation("tool_1", tool_id="search", status="succeeded", duration_ms=80),
            tool_invocation("tool_2", tool_id="search", status="failed", duration_ms=200),
            tool_invocation("tool_3", tool_id="notify", status="succeeded", duration_ms=40),
            tool_invocation(
                "tool_other",
                tenant_id="tenant_2",
                tool_id="other",
                status="succeeded",
                duration_ms=999,
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(
        tenant_store=tenant_store,
        run_store=run_store,
        usage_ledger=ledger,
        tool_invocation_store=tool_store,
    )
    transport = ASGITransport(app=app)

    params = {"fromMs": 1782432000000, "toMs": 1782518400000}
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        overview = await client.get(
            "/api/admin/tenant/overview", params=params, headers=MANAGER_HEADERS
        )
        usage = await client.get("/v1/admin/tenant/usage", params=params, headers=MANAGER_HEADERS)
        quality = await client.get(
            "/api/admin/tenant/quality", params=params, headers=MANAGER_HEADERS
        )
        tools = await client.get("/v1/admin/tenant/tools", params=params, headers=MANAGER_HEADERS)
        cost = await client.get("/api/admin/tenant/cost", params=params, headers=MANAGER_HEADERS)

    assert overview.status_code == 200
    assert overview.json()["totalRequests"] == 2
    assert overview.json()["successRate"] == 0.5
    assert overview.json()["avgResponseTimeMs"] == 240
    assert overview.json()["monthlyCost"] == "0.00300000"
    assert usage.status_code == 200
    assert usage.json()["channelDistribution"] == {"slack": 1, "api": 1}
    assert [user["userLabel"] for user in usage.json()["topUsers"]] == ["user_b", "user_a"]
    assert usage.json()["timeSeries"] == [{"time": "2026-06-26T01:00:00+00:00", "value": 2.0}]
    assert quality.status_code == 200
    assert quality.json()["latencyP50"] == 120
    assert quality.json()["latencyP95"] == 360
    assert quality.json()["errorDistribution"] == {"tool_timeout": 1}
    assert tools.status_code == 200
    assert [tool["toolName"] for tool in tools.json()["toolRanking"]] == ["search", "notify"]
    assert tools.json()["toolRanking"][0]["calls"] == 2
    assert tools.json()["toolRanking"][0]["successRate"] == 0.5
    assert tools.json()["statusCounts"] == {"failed": 1, "succeeded": 2}
    assert cost.status_code == 200
    assert cost.json()["costByModel"] == {
        "claude-sonnet-4": "0.00200000",
        "gpt-5-mini": "0.00100000",
    }


async def test_tenant_admin_csv_exports_executions_and_tool_calls() -> None:
    tenant_store = FakeTenantStore()
    await tenant_store.save(TenantRecord(id="tenant_1", name="Acme", slug="acme"))
    run_store = FakeTraceRunStore(
        runs=[
            trace_run(
                "run_1",
                tenant_id="tenant_1",
                status="completed",
                trace_id="trace_1",
                duration_ms=120,
                error_class=None,
            ),
            trace_run(
                "run_2",
                tenant_id="tenant_1",
                status="failed",
                trace_id="trace_2",
                duration_ms=360,
                error_class='timeout,"quoted"',
            ),
            trace_run(
                "run_other",
                tenant_id="tenant_2",
                status="failed",
                trace_id="trace_other",
                duration_ms=999,
            ),
        ],
        events={},
    )
    tool_store = FakeToolInvocationStore(
        [
            tool_invocation("tool_1", tool_id="search", status="succeeded", duration_ms=80),
            tool_invocation(
                "tool_2",
                tool_id='notify,"team"',
                status="failed",
                duration_ms=200,
                error_class="tool_error",
            ),
            tool_invocation(
                "tool_other",
                tenant_id="tenant_2",
                tool_id="other",
                status="succeeded",
                duration_ms=999,
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(
        tenant_store=tenant_store,
        run_store=run_store,
        tool_invocation_store=tool_store,
    )
    transport = ASGITransport(app=app)
    params = {"fromMs": 1782432000000, "toMs": 1782518400000}

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get(
            "/api/admin/tenant/export/executions",
            params=params,
            headers=MANAGER_HEADERS,
        )
        executions = await client.get(
            "/api/admin/tenant/export/executions",
            params=params,
            headers=ADMIN_HEADERS,
        )
        tools = await client.get(
            "/v1/admin/tenant/export/tools",
            params=params,
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert executions.status_code == 200
    assert executions.headers["content-type"].startswith("text/csv")
    assert executions.headers["content-disposition"] == 'attachment; filename="executions.csv"'
    assert executions.text.splitlines() == [
        "time,run_id,success,duration_ms,error_code,tool_count",
        "2026-06-26T01:00:00+00:00,run_1,true,120,,2",
        '2026-06-26T01:00:00+00:00,run_2,false,360,"timeout,""quoted""",0',
    ]
    assert tools.status_code == 200
    assert tools.headers["content-disposition"] == 'attachment; filename="tool_calls.csv"'
    assert tools.text.splitlines() == [
        "time,run_id,tool_name,success,duration_ms,error_class",
        "2026-06-26T01:00:00+00:00,run_1,search,true,80,",
        '2026-06-26T01:00:00+00:00,run_1,"notify,""team""",false,200,tool_error',
    ]


async def test_tool_stats_api_ports_legacy_outcome_summary_and_accuracy() -> None:
    store = FakeToolInvocationStore(
        [
            tool_invocation(
                "tool_1",
                tool_id="atlassian:jira_search",
                status="completed",
                duration_ms=120,
            ),
            tool_invocation(
                "tool_2",
                tool_id="atlassian:jira_search",
                status="failed",
                duration_ms=90,
            ),
            tool_invocation(
                "tool_3",
                tool_id="local:search_docs",
                status="timeout",
                duration_ms=15000,
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(tool_invocation_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/tools/stats", headers=USER_HEADERS)
        stats = await client.get("/api/admin/tools/stats", headers=ADMIN_HEADERS)
        filtered = await client.get(
            "/v1/admin/tools/stats",
            params={"server": "atlassian"},
            headers=ADMIN_HEADERS,
        )
        accuracy = await client.get("/api/admin/tools/accuracy", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert stats.status_code == 200
    assert stats.json() == {
        "total": 3.0,
        "accuracy": 1 / 3,
        "byOutcome": {"failed": 1.0, "ok": 1.0, "timeout": 1.0},
        "byServer": {"atlassian": 2.0, "local": 1.0},
        "byTool": [
            {"tool": "jira_search", "server": "atlassian", "outcome": "failed", "count": 1.0},
            {"tool": "jira_search", "server": "atlassian", "outcome": "ok", "count": 1.0},
            {"tool": "search_docs", "server": "local", "outcome": "timeout", "count": 1.0},
        ],
    }
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 2.0
    assert filtered.json()["byServer"] == {"atlassian": 2.0}
    assert accuracy.status_code == 200
    assert accuracy.json() == {
        "total": 3.0,
        "ok": 1.0,
        "accuracy": 1 / 3,
        "invalidCallRate": 1 / 3,
        "timeoutRate": 1 / 3,
        "notFoundRate": 0.0,
    }


async def test_tool_calls_api_ports_legacy_history_and_ranking_queries() -> None:
    store = FakeToolInvocationStore(
        [
            tool_invocation(
                "tool_1",
                tool_id="search",
                status="succeeded",
                duration_ms=80,
                input_payload={"query": "alpha"},
                output_payload={"count": 2},
            ),
            tool_invocation(
                "tool_2",
                run_id="run_2",
                tool_id="search",
                status="failed",
                duration_ms=200,
                error_class="timeout",
            ),
            tool_invocation(
                "tool_3",
                run_id="run_2",
                tool_id="notify",
                status="succeeded",
                duration_ms=40,
            ),
            tool_invocation(
                "tool_other",
                tenant_id="tenant_2",
                tool_id="other",
                status="succeeded",
                duration_ms=999,
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(tool_invocation_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/tool-calls", headers=MANAGER_HEADERS)
        by_run = await client.get(
            "/api/admin/tool-calls",
            params={"runId": "run_2", "days": 999, "limit": 999},
            headers=ADMIN_HEADERS,
        )
        failed_only = await client.get(
            "/v1/admin/tool-calls",
            params={"status": "failed", "days": 999},
            headers=ADMIN_HEADERS,
        )
        invalid_status = await client.get(
            "/v1/admin/tool-calls",
            params={"status": "pending", "days": 999},
            headers=ADMIN_HEADERS,
        )
        ranking = await client.get(
            "/v1/admin/tool-calls/ranking",
            params={"days": 999},
            headers=ADMIN_HEADERS,
        )
        failed_ranking = await client.get(
            "/v1/admin/tool-calls/ranking",
            params={"days": 999, "status": "failed"},
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert by_run.status_code == 200
    assert by_run.json() == [
        {
            "id": "tool_2",
            "runId": "run_2",
            "toolName": "search",
            "status": "failed",
            "success": False,
            "durationMs": 200,
            "approvalId": None,
            "idempotencyKey": "idem_tool_2",
            "requestChecksum": "req_tool_2",
            "resultChecksum": "res_tool_2",
            "input": {},
            "output": {},
            "error": {"error_class": "timeout"},
            "startedAt": "2026-06-26T01:00:00+00:00",
            "completedAt": "2026-06-26T01:00:00.200000+00:00",
        },
        {
            "id": "tool_3",
            "runId": "run_2",
            "toolName": "notify",
            "status": "succeeded",
            "success": True,
            "durationMs": 40,
            "approvalId": None,
            "idempotencyKey": "idem_tool_3",
            "requestChecksum": "req_tool_3",
            "resultChecksum": "res_tool_3",
            "input": {},
            "output": {},
            "error": None,
            "startedAt": "2026-06-26T01:00:00+00:00",
            "completedAt": "2026-06-26T01:00:00.040000+00:00",
        },
    ]
    assert failed_only.status_code == 200
    assert [item["id"] for item in failed_only.json()] == ["tool_2"]
    assert invalid_status.status_code == 400
    assert (
        invalid_status.json()["detail"]
        == "status must be one of: cancelled, failed, requires_reconciliation, started, succeeded"
    )
    assert ranking.status_code == 200
    assert ranking.json() == [
        {
            "toolName": "search",
            "calls": 2,
            "successRate": 0.5,
            "avgDurationMs": 140,
            "p95DurationMs": 200,
            "mcpServerName": None,
        },
        {
            "toolName": "notify",
            "calls": 1,
            "successRate": 1.0,
            "avgDurationMs": 40,
            "p95DurationMs": 40,
            "mcpServerName": None,
        },
    ]
    assert store.calls[0]["limit"] == 500
    assert store.calls[1]["status"] == "failed"
    assert failed_ranking.status_code == 200
    assert failed_ranking.json() == [
        {
            "toolName": "search",
            "calls": 1,
            "successRate": 0.0,
            "avgDurationMs": 200,
            "p95DurationMs": 200,
            "mcpServerName": None,
        }
    ]
    assert store.calls[2]["status"] is None
    assert store.calls[3]["status"] == "failed"


async def test_tool_call_reconciliation_marks_only_stale_tenant_started_claims() -> None:
    now = datetime.now(UTC)
    store = FakeToolInvocationStore(
        [
            replace(
                tool_invocation(
                    "tool_stale",
                    tool_id="Webhook:send",
                    status="started",
                    duration_ms=0,
                    started_at=now - timedelta(hours=2),
                ),
                completed_at=None,
            ),
            replace(
                tool_invocation(
                    "tool_recent",
                    tool_id="Webhook:send",
                    status="started",
                    duration_ms=0,
                    started_at=now - timedelta(seconds=30),
                ),
                completed_at=None,
            ),
            replace(
                tool_invocation(
                    "tool_other_tenant",
                    tenant_id="tenant_2",
                    tool_id="Webhook:send",
                    status="started",
                    duration_ms=0,
                    started_at=now - timedelta(hours=2),
                ),
                completed_at=None,
            ),
        ]
    )
    audit_store = FakeAdminAuditStore()
    app = create_app()
    app.state.reactor = FakeContainer(
        tool_invocation_store=store,
        admin_audit_store=audit_store,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.post(
            "/v1/admin/tool-calls/reconcile-stale",
            headers=USER_HEADERS,
        )
        response = await client.post(
            "/v1/admin/tool-calls/reconcile-stale",
            params={"olderThanSeconds": 900, "limit": 10},
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert response.status_code == 200
    assert response.json() == {
        "status": "marked_for_reconciliation",
        "tenantId": "tenant_1",
        "marked": 1,
        "olderThanSeconds": 900,
    }
    records = {record.id: record for record in store.records}
    assert records["tool_stale"].status == "requires_reconciliation"
    assert records["tool_stale"].error_payload == {
        "error": {
            "code": "stale_started_claim",
            "message": "tool invocation outcome requires operator reconciliation",
        }
    }
    assert records["tool_recent"].status == "started"
    assert records["tool_other_tenant"].status == "started"
    assert audit_store.records[-1].category == "tool_invocation_reconciliation"
    assert audit_store.records[-1].detail == "marked=1 older_than_seconds=900"


async def test_tool_calls_api_redacts_secret_shaped_payload_values() -> None:
    store = FakeToolInvocationStore(
        [
            tool_invocation(
                "tool_secret",
                tool_id="search",
                status="failed",
                duration_ms=80,
                input_payload={
                    "query": "investigate api_key=sk-live-1234567890abcdef",
                    "nested": {"github": "ghp_1234567890abcdef1234567890abcdef1234"},
                },
                output_payload={"summary": "provider returned sk-live-1234567890abcdef"},
                error_payload={"message": "denied token ghp_1234567890abcdef1234567890abcdef1234"},
            )
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(tool_invocation_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/admin/tool-calls",
            params={"days": 999},
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 200
    encoded = response.text
    assert "sk-live-1234567890abcdef" not in encoded
    assert "ghp_1234567890abcdef1234567890abcdef1234" not in encoded
    item = response.json()[0]
    assert item["input"]["query"] == "investigate api_key=[REDACTED]"
    assert item["input"]["nested"]["github"] == "[REDACTED]"
    assert item["output"]["summary"] == "provider returned [REDACTED]"
    assert item["error"]["message"] == "denied token [REDACTED]"


async def test_admin_eval_dashboard_aggregates_runs_and_pass_rate() -> None:
    eval_store = FakeEvalResultStore(
        [
            eval_result(
                "result_1",
                tenant_id="tenant_1",
                case_id="case_1",
                run_id="eval_run_1",
                passed=True,
                score=0.9,
                evaluated_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
            ),
            eval_result(
                "result_2",
                tenant_id="tenant_1",
                case_id="case_2",
                run_id="eval_run_1",
                passed=False,
                score=0.4,
                evaluated_at=datetime(2026, 6, 26, 1, 1, tzinfo=UTC),
            ),
            eval_result(
                "result_3",
                tenant_id="tenant_1",
                case_id="case_3",
                run_id="eval_run_2",
                passed=True,
                score=1.0,
                evaluated_at=datetime(2026, 6, 25, 2, 0, tzinfo=UTC),
            ),
            eval_result(
                "result_other",
                tenant_id="tenant_2",
                case_id="case_4",
                run_id="eval_run_other",
                passed=True,
                score=1.0,
                evaluated_at=datetime(2026, 6, 26, 3, 0, tzinfo=UTC),
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(eval_result_store=eval_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/evals/runs", headers=MANAGER_HEADERS)
        runs = await client.get("/api/admin/evals/runs", params={"days": 30}, headers=ADMIN_HEADERS)
        pass_rate = await client.get(
            "/v1/admin/evals/pass-rate",
            params={"days": 30},
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert runs.status_code == 200
    assert runs.json() == [
        {
            "eval_run_id": "eval_run_1",
            "total_cases": 2,
            "pass_count": 1,
            "avg_score": 0.65,
            "avg_latency_ms": 0,
            "total_tokens": 0,
            "total_cost": 0,
            "started_at": "2026-06-26T01:00:00+00:00",
            "ended_at": "2026-06-26T01:01:00+00:00",
        },
        {
            "eval_run_id": "eval_run_2",
            "total_cases": 1,
            "pass_count": 1,
            "avg_score": 1.0,
            "avg_latency_ms": 0,
            "total_tokens": 0,
            "total_cost": 0,
            "started_at": "2026-06-25T02:00:00+00:00",
            "ended_at": "2026-06-25T02:00:00+00:00",
        },
    ]
    assert pass_rate.status_code == 200
    assert pass_rate.json() == [
        {"day": "2026-06-26", "total": 2, "passed": 1, "avg_score": 0.65},
        {"day": "2026-06-25", "total": 1, "passed": 1, "avg_score": 1.0},
    ]


async def test_admin_slack_activity_aggregates_channel_and_daily_usage() -> None:
    run_store = FakeTraceRunStore(
        runs=[
            slack_run(
                "run_1",
                tenant_id="tenant_1",
                status="completed",
                slack_channel_id="C123",
                slack_user_id="U1",
                duration_ms=120,
                created_at="2026-06-26T01:00:00+00:00",
            ),
            slack_run(
                "run_2",
                tenant_id="tenant_1",
                status="failed",
                slack_channel_id="C123",
                slack_user_id="U2",
                duration_ms=360,
                created_at="2026-06-26T02:00:00+00:00",
            ),
            slack_run(
                "run_3",
                tenant_id="tenant_1",
                status="completed",
                slack_channel_id="C999",
                slack_user_id="U1",
                duration_ms=240,
                created_at="2026-06-25T03:00:00+00:00",
            ),
            slack_run(
                "run_other",
                tenant_id="tenant_2",
                status="completed",
                slack_channel_id="C123",
                slack_user_id="U3",
                duration_ms=999,
                created_at="2026-06-26T04:00:00+00:00",
            ),
        ],
        events={},
    )
    ledger = InMemoryUsageLedger(
        records=[
            usage_record("usage_1", run_id="run_1", total_tokens=100, cost="0.0100"),
            usage_record("usage_2", run_id="run_2", total_tokens=50, cost="0.0050"),
            usage_record("usage_3", run_id="run_3", total_tokens=25, cost="0.0025"),
            usage_record(
                "usage_other",
                tenant_id="tenant_2",
                run_id="run_other",
                total_tokens=999,
                cost="0.9990",
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(run_store=run_store, usage_ledger=ledger)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/slack-activity/channels", headers=MANAGER_HEADERS)
        channels = await client.get(
            "/api/admin/slack-activity/channels",
            params={"days": 30},
            headers=ADMIN_HEADERS,
        )
        daily = await client.get(
            "/v1/admin/slack-activity/daily",
            params={"days": 30},
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert channels.status_code == 200
    assert channels.json() == [
        {
            "channel": "C123",
            "session_count": 2,
            "unique_users": 2,
            "total_tokens": 150,
            "total_cost_usd": "0.0150",
            "avg_latency_ms": 240,
        },
        {
            "channel": "C999",
            "session_count": 1,
            "unique_users": 1,
            "total_tokens": 25,
            "total_cost_usd": "0.0025",
            "avg_latency_ms": 240,
        },
    ]
    assert daily.status_code == 200
    assert daily.json() == [
        {
            "day": "2026-06-26",
            "message_count": 2,
            "unique_users": 2,
            "success_count": 1,
            "failure_count": 1,
        },
        {
            "day": "2026-06-25",
            "message_count": 1,
            "unique_users": 1,
            "success_count": 1,
            "failure_count": 0,
        },
    ]


async def test_admin_conversation_analytics_ports_channel_failure_and_latency_queries() -> None:
    run_store = FakeTraceRunStore(
        runs=[
            trace_run(
                "run_api_ok",
                tenant_id="tenant_1",
                status="completed",
                trace_id="trace_api_ok",
                duration_ms=800,
                channel="api",
            ),
            trace_run(
                "run_api_failed",
                tenant_id="tenant_1",
                status="failed",
                trace_id="trace_api_failed",
                duration_ms=2400,
                channel="api",
                error_class="timeout",
            ),
            trace_run(
                "run_slack_ok",
                tenant_id="tenant_1",
                status="completed",
                trace_id="trace_slack_ok",
                duration_ms=6200,
                channel="slack",
            ),
            trace_run(
                "run_other",
                tenant_id="tenant_2",
                status="failed",
                trace_id="trace_other",
                duration_ms=12000,
                channel="api",
                error_class="other",
            ),
        ],
        events={},
    )
    app = create_app()
    app.state.reactor = FakeContainer(run_store=run_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get(
            "/api/admin/conversation-analytics/by-channel",
            headers=USER_HEADERS,
        )
        by_channel = await client.get(
            "/api/admin/conversation-analytics/by-channel",
            params={"days": 30},
            headers=ADMIN_HEADERS,
        )
        failures = await client.get(
            "/v1/admin/conversation-analytics/failure-patterns",
            params={"days": 30},
            headers=ADMIN_HEADERS,
        )
        latency = await client.get(
            "/api/admin/conversation-analytics/latency-distribution",
            params={"days": 30},
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert by_channel.status_code == 200
    assert by_channel.json() == [
        {
            "channel": "api",
            "total": 2,
            "success": 1,
            "failure": 1,
            "success_rate": 50.0,
            "avg_duration_ms": 1600,
        },
        {
            "channel": "slack",
            "total": 1,
            "success": 1,
            "failure": 0,
            "success_rate": 100.0,
            "avg_duration_ms": 6200,
        },
    ]
    assert failures.status_code == 200
    assert failures.json() == [
        {"error_class": "timeout", "count": 1, "latest": "2026-06-26T01:00:02.400+00:00"}
    ]
    assert latency.status_code == 200
    assert latency.json() == [
        {"bucket": "< 1s", "count": 1},
        {"bucket": "1-3s", "count": 1},
        {"bucket": "5-10s", "count": 1},
    ]


async def test_admin_followup_suggestion_stats_clamps_window_and_returns_ctr() -> None:
    followup_store = FakeFollowupSuggestionStore(
        {
            "totalImpressions": 5,
            "totalClicks": 2,
            "ctr": 0.4,
            "byCategory": [
                {"category": "jira", "impressions": 3, "clicks": 2, "ctr": 0.666667},
                {"category": "docs", "impressions": 2, "clicks": 0, "ctr": 0.0},
            ],
        }
    )
    app = create_app()
    app.state.reactor = FakeContainer(followup_suggestion_store=followup_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/followup-suggestions/stats", headers=USER_HEADERS)
        response = await client.get(
            "/v1/admin/followup-suggestions/stats",
            params={"hours": 999},
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert response.status_code == 200
    assert followup_store.windows == [168]
    assert response.json() == {
        "windowHours": 168,
        "totalImpressions": 5,
        "totalClicks": 2,
        "ctr": 0.4,
        "byCategory": [
            {"category": "jira", "impressions": 3, "clicks": 2, "ctr": 0.666667},
            {"category": "docs", "impressions": 2, "clicks": 0, "ctr": 0.0},
        ],
    }


async def test_admin_trace_and_latency_api_uses_run_store_events_and_metadata() -> None:
    run_store = FakeTraceRunStore(
        runs=[
            trace_run(
                "run_1",
                tenant_id="tenant_1",
                status="completed",
                trace_id="trace_1",
                duration_ms=120,
            ),
            trace_run(
                "run_2",
                tenant_id="tenant_1",
                status="failed",
                trace_id="trace_2",
                duration_ms=360,
            ),
            trace_run(
                "run_other",
                tenant_id="tenant_2",
                status="completed",
                trace_id="trace_other",
                duration_ms=999,
            ),
        ],
        events={
            "run_1": [
                RunEventRecord(
                    sequence=1,
                    event_type="run.stream.started",
                    payload={"trace_id": "trace_1", "graph_node": "guard"},
                ),
                RunEventRecord(
                    sequence=2,
                    event_type="run.stream.completed",
                    payload={
                        "trace_id": "trace_1",
                        "graph_node": "hooks",
                        "tool_results": [
                            {
                                "tool_id": "builtin:send_webhook",
                                "status": "succeeded",
                                "payload": {"api_key": "sk-test-secret"},
                                "raw_output": "sk-test-secret",
                            }
                        ],
                    },
                ),
            ]
        },
    )
    app = create_app()
    app.state.reactor = FakeContainer(run_store=run_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/traces", headers=USER_HEADERS)
        traces = await client.get(
            "/api/admin/traces",
            params={"days": 7, "limit": 10, "status": "completed"},
            headers=MANAGER_HEADERS,
        )
        spans = await client.get("/v1/admin/traces/trace_1/spans", headers=MANAGER_HEADERS)
        summary = await client.get(
            "/api/admin/metrics/latency/summary",
            headers=MANAGER_HEADERS,
        )
        timeseries = await client.get(
            "/v1/admin/metrics/latency/timeseries",
            headers=MANAGER_HEADERS,
        )

    assert forbidden.status_code == 403
    assert traces.status_code == 200
    assert traces.json() == [
        {
            "traceId": "trace_1",
            "runId": "run_1",
            "status": "completed",
            "userId": "user_1",
            "threadId": "thread_1",
            "model": "gpt-5-mini",
            "durationMs": 120,
            "createdAt": 1782435600000,
            "updatedAt": 1782435600120,
        }
    ]
    assert spans.status_code == 200
    assert run_store.list_event_calls == [("run_1", "tenant_1", 0)]
    assert spans.json() == [
        {
            "traceId": "trace_1",
            "runId": "run_1",
            "sequence": 1,
            "eventType": "run.stream.started",
            "graphNode": "guard",
            "payload": {"trace_id": "trace_1", "graph_node": "guard"},
        },
        {
            "traceId": "trace_1",
            "runId": "run_1",
            "sequence": 2,
            "eventType": "run.stream.completed",
            "graphNode": "hooks",
            "payload": {
                "trace_id": "trace_1",
                "graph_node": "hooks",
                "tool_results": [
                    {
                        "tool_id": "builtin:send_webhook",
                        "status": "succeeded",
                    }
                ],
            },
        },
    ]
    assert summary.status_code == 200
    assert summary.json() == {
        "count": 2,
        "p50Ms": 120,
        "p95Ms": 360,
        "p99Ms": 360,
        "maxMs": 360,
    }
    assert timeseries.status_code == 200
    assert timeseries.json() == [
        {"bucket": "2026-06-26T01:00:00+00:00", "averageMs": 240, "count": 2}
    ]


async def test_debug_replay_api_ports_legacy_optional_store_contract() -> None:
    capture_id = "123e4567-e89b-12d3-a456-426614174000"
    cross_tenant_id = "123e4567-e89b-12d3-a456-426614174001"
    missing_id = "123e4567-e89b-12d3-a456-426614174099"
    store = FakeDebugReplayStore(
        [
            {
                "id": capture_id,
                "tenantId": "tenant_1",
                "userHash": "user_hash",
                "capturedAt": "2026-06-26T01:00:00+00:00",
                "userPrompt": "please replay",
                "errorCode": "tool_timeout",
                "errorMessage": "Tool timed out",
                "modelId": "gpt-5-mini",
                "toolsAttempted": ["search", "notify"],
                "expiresAt": "2026-06-27T01:00:00+00:00",
            },
            {
                "id": cross_tenant_id,
                "tenantId": "tenant_2",
                "userHash": "other",
                "capturedAt": "2026-06-26T01:00:00+00:00",
                "userPrompt": "other",
                "errorCode": "other",
                "errorMessage": "Other",
                "modelId": "gpt-5-mini",
                "toolsAttempted": [],
                "expiresAt": "2026-06-27T01:00:00+00:00",
            },
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(debug_replay_store=store)
    missing_store_app = create_app()
    transport = ASGITransport(app=app)
    missing_transport = ASGITransport(app=missing_store_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/debug/replay", headers=MANAGER_HEADERS)
        listed = await client.get(
            "/api/admin/debug/replay",
            params={"tenantId": "tenant_1", "limit": 999},
            headers=ADMIN_HEADERS,
        )
        cross_tenant_list = await client.get(
            "/api/admin/debug/replay",
            params={"tenantId": "tenant_2", "limit": 10},
            headers=ADMIN_HEADERS,
        )
        fetched = await client.get(
            f"/v1/admin/debug/replay/{capture_id}",
            headers=ADMIN_HEADERS,
        )
        cross_tenant_get = await client.get(
            f"/v1/admin/debug/replay/{cross_tenant_id}",
            headers=ADMIN_HEADERS,
        )
        missing_capture = await client.get(
            f"/api/admin/debug/replay/{missing_id}",
            headers=ADMIN_HEADERS,
        )
    async with AsyncClient(transport=missing_transport, base_url="http://testserver") as client:
        missing_store_list = await client.get(
            "/api/admin/debug/replay",
            headers=ADMIN_HEADERS,
        )
        missing_store_get = await client.get(
            f"/api/admin/debug/replay/{capture_id}",
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert listed.status_code == 200
    assert listed.json() == [
        {
            "id": capture_id,
            "tenantId": "tenant_1",
            "userHash": "user_hash",
            "capturedAt": "2026-06-26T01:00:00+00:00",
            "userPrompt": "please replay",
            "errorCode": "tool_timeout",
            "errorMessage": "Tool timed out",
            "modelId": "gpt-5-mini",
            "toolsAttempted": ["search", "notify"],
            "expiresAt": "2026-06-27T01:00:00+00:00",
        }
    ]
    assert cross_tenant_list.status_code == 200
    assert [item["tenantId"] for item in cross_tenant_list.json()] == ["tenant_1"]
    assert store.list_calls == [("tenant_1", 200), ("tenant_1", 10)]
    assert fetched.status_code == 200
    assert fetched.json()["id"] == capture_id
    assert cross_tenant_get.status_code == 404
    assert cross_tenant_get.json()["detail"] == f"replay capture not found: {cross_tenant_id}"
    assert missing_capture.status_code == 404
    assert missing_capture.json()["detail"] == f"replay capture not found: {missing_id}"
    assert missing_store_list.status_code == 200
    assert missing_store_list.json() == []
    assert missing_store_get.status_code == 404
    assert missing_store_get.json()["detail"] == "DebugReplayStore not configured"


async def test_debug_state_history_api_reads_langgraph_checkpoints() -> None:
    checkpointer = InMemorySaver()
    graph = build_reactor_graph(checkpointer=checkpointer)
    await graph.ainvoke(
        ReactorState(
            run_id="run_history",
            tenant_id="tenant_1",
            user_id="user_1",
            messages=[HumanMessage(content="history please")],
            max_tool_calls=1,
            tool_call_count=0,
        ),
        config=langgraph_durable_config(
            tenant_id="tenant_1",
            thread_id="thread_history",
            checkpoint_ns="reactor",
        ),
    )
    run_store = FakeTraceRunStore(
        runs=[
            trace_run(
                "run_history",
                tenant_id="tenant_1",
                status="completed",
                trace_id="trace_history",
                duration_ms=120,
            ),
            trace_run(
                "run_other",
                tenant_id="tenant_2",
                status="completed",
                trace_id="trace_other",
                duration_ms=120,
            ),
        ],
        events={},
    )
    run_store.runs[0] = replace(run_store.runs[0], thread_id="thread_history")
    app = create_app()
    app.state.reactor = FakeContainer(run_store=run_store, checkpointer=checkpointer)
    missing_checkpointer_app = create_app()
    missing_checkpointer_app.state.reactor = FakeContainer(run_store=run_store)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        forbidden = await client.get(
            "/api/admin/debug/state-history/run_history",
            headers=MANAGER_HEADERS,
        )
        fetched = await client.get(
            "/api/admin/debug/state-history/run_history",
            params={"limit": 2},
            headers=ADMIN_HEADERS,
        )
        cross_tenant = await client.get(
            "/api/admin/debug/state-history/run_other",
            headers=ADMIN_HEADERS,
        )
    async with AsyncClient(
        transport=ASGITransport(app=missing_checkpointer_app),
        base_url="http://testserver",
    ) as client:
        missing_checkpointer = await client.get(
            "/v1/admin/debug/state-history/run_history",
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["runId"] == "run_history"
    assert body["threadId"] == "thread_history"
    assert body["checkpointNs"] == "reactor"
    assert body["resolvedCheckpointNs"] == ""
    assert body["namespaceFallbackUsed"] is False
    assert len(body["entries"]) == 2
    assert body["entries"][0]["checkpointId"]
    assert body["nextActions"][0] == {
        "id": "diagnose-run",
        "label": "Inspect this run's current diagnostics",
        "command": "reactor-runs diagnose run_history --output table",
    }
    assert body["nextActions"][1] == {
        "id": "replay-stream",
        "label": "Replay this run's persisted stream events",
        "command": "reactor-runs replay run_history --output table",
    }
    assert body["nextActions"][2]["id"] == "fork-latest-checkpoint"
    assert body["nextActions"][2]["command"].startswith(
        "reactor-runs fork run_history --checkpoint-ns reactor --checkpoint-id "
    )
    assert "response_metadata" in body["entries"][0]["stateKeys"]
    assert "messages" not in body["entries"][0]
    assert cross_tenant.status_code == 404
    assert missing_checkpointer.status_code == 503
    assert missing_checkpointer.json()["detail"] == "graph checkpoint history is not configured"


class FakeContainer:
    def __init__(
        self,
        *,
        admin_audit_store: FakeAdminAuditStore | None = None,
        scheduler_store: FakeSchedulerStore | None = None,
        scheduled_job_execution_store: FakeExecutionStore | None = None,
        approval_store: FakeApprovalStore | None = None,
        usage_ledger: InMemoryUsageLedger | None = None,
        alert_rule_store: InMemoryAlertRuleStore | None = None,
        rag_document_sink: FakeRagDocumentSink | None = None,
        response_cache: FakeResponseCache | None = None,
        run_store: FakeTraceRunStore | None = None,
        tenant_store: FakeTenantStore | None = None,
        tool_invocation_store: FakeToolInvocationStore | None = None,
        eval_result_store: FakeEvalResultStore | None = None,
        followup_suggestion_store: FakeFollowupSuggestionStore | None = None,
        model_pricing_store: FakeModelPricingStore | None = None,
        runtime_settings_store: FakeRuntimeSettingsStore | None = None,
        metric_ingestion_buffer: FakeMetricIngestionBuffer | None = None,
        durable_store: FakeDurableStore | None = None,
        user_store: FakeUserStore | None = None,
        debug_replay_store: FakeDebugReplayStore | None = None,
        task_memory_maintenance: FakeTaskMemoryMaintenance | None = None,
        memory_store: object | None = None,
        checkpointer: object | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self._admin_audit_store = admin_audit_store
        self._scheduler_store = scheduler_store
        self._scheduled_job_execution_store = scheduled_job_execution_store
        self._approval_store = approval_store
        self._usage_ledger = usage_ledger
        self._alert_rule_store = alert_rule_store
        self._rag_document_sink = rag_document_sink
        self._response_cache = response_cache
        self._run_store = run_store
        self._tenant_store = tenant_store
        self._tool_invocation_store = tool_invocation_store
        self._eval_result_store = eval_result_store
        self._followup_suggestion_store = followup_suggestion_store
        self._model_pricing_store = model_pricing_store
        self._runtime_settings_store = runtime_settings_store
        self._metric_ingestion_buffer = metric_ingestion_buffer
        self._durable_store = durable_store
        self._user_store = user_store
        self._debug_replay_store = debug_replay_store
        self._task_memory_maintenance = task_memory_maintenance
        self._memory_store = memory_store
        self.checkpointer = checkpointer

    def admin_audit_store(self) -> FakeAdminAuditStore | None:
        return self._admin_audit_store

    def scheduler_store(self) -> FakeSchedulerStore | None:
        return self._scheduler_store

    def scheduled_job_execution_store(self) -> FakeExecutionStore | None:
        return self._scheduled_job_execution_store

    def approval_store(self) -> FakeApprovalStore | None:
        return self._approval_store

    def usage_ledger(self) -> InMemoryUsageLedger | None:
        return self._usage_ledger

    def alert_rule_store(self) -> InMemoryAlertRuleStore | None:
        return self._alert_rule_store

    def faq_document_sink(self) -> FakeRagDocumentSink | None:
        return self._rag_document_sink

    def response_cache(self) -> FakeResponseCache | None:
        return self._response_cache

    def run_store(self) -> FakeTraceRunStore | None:
        return self._run_store

    def tenant_store(self) -> FakeTenantStore | None:
        return self._tenant_store

    def tool_invocation_store(self) -> FakeToolInvocationStore | None:
        return self._tool_invocation_store

    def eval_result_store(self) -> FakeEvalResultStore | None:
        return self._eval_result_store

    def followup_suggestion_store(self) -> FakeFollowupSuggestionStore | None:
        return self._followup_suggestion_store

    def model_pricing_store(self) -> FakeModelPricingStore | None:
        return self._model_pricing_store

    def runtime_settings_store(self) -> FakeRuntimeSettingsStore | None:
        return self._runtime_settings_store

    def metric_ingestion_buffer(self) -> FakeMetricIngestionBuffer | None:
        return self._metric_ingestion_buffer

    def durable_store(self) -> FakeDurableStore | None:
        return self._durable_store

    def user_store(self) -> FakeUserStore | None:
        return self._user_store

    def debug_replay_store(self) -> FakeDebugReplayStore | None:
        return self._debug_replay_store

    def task_memory_maintenance(self) -> FakeTaskMemoryMaintenance | None:
        return self._task_memory_maintenance

    def memory_store(self) -> object | None:
        return self._memory_store


class FakeTenantStore:
    def __init__(self) -> None:
        self.records: dict[str, TenantRecord] = {}

    async def find_by_id(self, tenant_id: str) -> TenantRecord | None:
        return self.records.get(tenant_id)

    async def find_by_slug(self, slug: str) -> TenantRecord | None:
        return next((tenant for tenant in self.records.values() if tenant.slug == slug), None)

    async def find_all(self, status: TenantStatus | None = None) -> list[TenantRecord]:
        rows = [
            tenant for tenant in self.records.values() if status is None or tenant.status == status
        ]
        return sorted(rows, key=lambda tenant: tenant.created_at, reverse=True)

    async def save(self, tenant: TenantRecord) -> TenantRecord:
        self.records[tenant.id] = tenant
        return tenant

    async def delete(self, tenant_id: str) -> bool:
        return self.records.pop(tenant_id, None) is not None


class FakeMemoryProposalStore:
    def __init__(
        self,
        proposals: list[MemoryProposalRecord],
        *,
        items: list[MemoryItemRecord] | None = None,
    ) -> None:
        self.proposals = proposals
        self.items = items or []
        self.saved_promotions: list[MemoryPromotionResult] = []
        self.saved_rejections: list[MemoryProposalRecord] = []

    async def list_proposals(
        self,
        *,
        tenant_id: str,
        status: str = "proposed",
        limit: int = 50,
        subject_id: str | None = None,
    ) -> list[MemoryProposalRecord]:
        rows = [
            proposal
            for proposal in self.proposals
            if proposal.tenant_id == tenant_id
            and proposal.status == status
            and (subject_id is None or proposal.namespace.subject_id == subject_id)
        ]
        return rows[:limit]

    async def get_proposal(
        self,
        *,
        tenant_id: str,
        proposal_id: str,
    ) -> MemoryProposalRecord | None:
        return next(
            (
                proposal
                for proposal in self.proposals
                if proposal.tenant_id == tenant_id and proposal.id == proposal_id
            ),
            None,
        )

    async def get_memory_item(
        self,
        *,
        tenant_id: str,
        item_id: str,
    ) -> MemoryItemRecord | None:
        return next(
            (item for item in self.items if item.tenant_id == tenant_id and item.id == item_id),
            None,
        )

    async def save_promotion(self, result: MemoryPromotionResult) -> str:
        self.saved_promotions.append(result)
        self.proposals = [
            result.proposal if proposal.id == result.proposal.id else proposal
            for proposal in self.proposals
        ]
        superseded_ids = {item.id for item in result.superseded_items}
        self.items = [
            next(
                (
                    superseded_item
                    for superseded_item in result.superseded_items
                    if superseded_item.id == item.id
                ),
                item,
            )
            for item in self.items
            if item.id in superseded_ids or item.status == "active"
        ]
        self.items.append(result.item)
        return result.item.id

    async def save_rejection(self, proposal: MemoryProposalRecord) -> str:
        self.saved_rejections.append(proposal)
        self.proposals = [
            proposal if candidate.id == proposal.id else candidate for candidate in self.proposals
        ]
        return proposal.id


class FakeMemoryProposalStoreWithoutItemLookup:
    def __init__(self, proposals: list[MemoryProposalRecord]) -> None:
        self.proposals = proposals
        self.saved_promotions: list[MemoryPromotionResult] = []
        self.saved_rejections: list[MemoryProposalRecord] = []

    async def list_proposals(
        self,
        *,
        tenant_id: str,
        status: str = "proposed",
        limit: int = 50,
        subject_id: str | None = None,
    ) -> list[MemoryProposalRecord]:
        rows = [
            proposal
            for proposal in self.proposals
            if proposal.tenant_id == tenant_id
            and proposal.status == status
            and (subject_id is None or proposal.namespace.subject_id == subject_id)
        ]
        return rows[:limit]

    async def get_proposal(
        self,
        *,
        tenant_id: str,
        proposal_id: str,
    ) -> MemoryProposalRecord | None:
        return next(
            (
                proposal
                for proposal in self.proposals
                if proposal.tenant_id == tenant_id and proposal.id == proposal_id
            ),
            None,
        )

    async def save_promotion(self, result: MemoryPromotionResult) -> str:
        self.saved_promotions.append(result)
        return result.item.id

    async def save_rejection(self, proposal: MemoryProposalRecord) -> str:
        self.saved_rejections.append(proposal)
        return proposal.id


class FakeUserStore:
    def __init__(self) -> None:
        self.users_by_id: dict[str, UserRecord] = {}
        self.users_by_email: dict[str, UserRecord] = {}

    async def find_by_email(self, email: str) -> UserRecord | None:
        return self.users_by_email.get(email)

    async def find_by_id(self, user_id: str) -> UserRecord | None:
        return self.users_by_id.get(user_id)

    async def save(self, user: UserRecord) -> UserRecord:
        self.users_by_id[user.id] = user
        self.users_by_email[user.email] = user
        return user

    async def update(self, user: UserRecord) -> UserRecord:
        return await self.save(user)


class FakeToolInvocationStore:
    def __init__(self, records: list[ToolInvocationRecord]) -> None:
        self.records = records
        self.calls: list[dict[str, object]] = []

    async def list_between(
        self,
        *,
        tenant_id: str,
        from_time: datetime,
        to_time: datetime,
        limit: int = 500,
        status: str | None = None,
    ) -> list[ToolInvocationRecord]:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "from_time": from_time,
                "to_time": to_time,
                "limit": limit,
                "status": status,
            }
        )
        return [
            record
            for record in self.records
            if record.tenant_id == tenant_id
            and from_time <= record.started_at < to_time
            and (status is None or record.status == status)
        ][:limit]

    async def mark_stale_started_for_reconciliation(
        self,
        *,
        tenant_id: str,
        older_than: datetime,
        limit: int = 100,
    ) -> list[str]:
        marked: list[str] = []
        for index, record in enumerate(self.records):
            if len(marked) >= limit:
                break
            if (
                record.tenant_id != tenant_id
                or record.status != "started"
                or record.started_at >= older_than
            ):
                continue
            self.records[index] = replace(
                record,
                status="requires_reconciliation",
                error_payload={
                    "error": {
                        "code": "stale_started_claim",
                        "message": "tool invocation outcome requires operator reconciliation",
                    }
                },
                completed_at=datetime.now(UTC),
            )
            marked.append(record.id)
        return marked


class FakeResponseCache:
    def __init__(self) -> None:
        self.entries: dict[str, str] = {}
        self.exact_hits = 0
        self.semantic_hits = 0
        self.misses = 0

    def put(self, key: str, value: str) -> None:
        self.entries[key] = value

    def record_exact_hit(self) -> None:
        self.exact_hits += 1

    def record_semantic_hit(self) -> None:
        self.semantic_hits += 1

    def record_miss(self) -> None:
        self.misses += 1

    def stats(self) -> dict[str, object]:
        return {
            "enabled": True,
            "semantic_enabled": False,
            "total_exact_hits": self.exact_hits,
            "total_semantic_hits": self.semantic_hits,
            "total_misses": self.misses,
            "ttl_minutes": 0,
            "max_size": len(self.entries),
            "similarity_threshold": 0.0,
            "max_candidates": 0,
            "cacheable_temperature": 0.0,
        }

    def invalidate_all(self) -> bool:
        self.entries.clear()
        return True

    def invalidate(self, key: str) -> bool:
        return self.entries.pop(key, None) is not None

    def invalidate_by_pattern(self, pattern: str) -> int:
        prefix = pattern.split("*", 1)[0]
        keys = [key for key in self.entries if key.startswith(prefix)]
        for key in keys:
            self.entries.pop(key, None)
        return len(keys)


class FakeTraceRunStore:
    def __init__(
        self,
        *,
        runs: list[SessionRunRecord],
        events: dict[str, list[RunEventRecord]],
    ) -> None:
        self.runs = runs
        self.events = events
        self.deleted: set[str] = set()
        self.list_event_calls: list[tuple[str, str | None, int]] = []

    async def list_sessions(
        self,
        *,
        tenant_id: str,
        user_id: str | None,
        limit: int,
        offset: int,
    ) -> SessionListRecord:
        rows = [
            run
            for run in self.runs
            if run.tenant_id == tenant_id and (user_id is None or run.user_id == user_id)
        ]
        return SessionListRecord(items=rows[offset : offset + limit], total=len(rows))

    async def find_session(self, *, run_id: str) -> SessionRunRecord | None:
        return next((run for run in self.runs if run.run_id == run_id), None)

    async def delete_session(self, *, run_id: str) -> bool:
        found = await self.find_session(run_id=run_id)
        if found is None:
            return False
        self.deleted.add(run_id)
        self.runs = [run for run in self.runs if run.run_id != run_id]
        return True

    async def list_recent_runs(self, *, tenant_id: str, limit: int) -> list[SessionRunRecord]:
        return [run for run in self.runs if run.tenant_id == tenant_id][:limit]

    async def list_events(
        self,
        *,
        run_id: str,
        tenant_id: str | None = None,
        after_sequence: int = 0,
    ) -> list[RunEventRecord]:
        self.list_event_calls.append((run_id, tenant_id, after_sequence))
        return [event for event in self.events.get(run_id, []) if event.sequence > after_sequence]


def trace_run(
    run_id: str,
    *,
    tenant_id: str,
    status: str,
    trace_id: str,
    duration_ms: int,
    user_id: str = "user_1",
    channel: str = "api",
    model: str = "gpt-5-mini",
    error_class: str | None = None,
    created_at: datetime | None = None,
) -> SessionRunRecord:
    started_at = created_at or datetime(2026, 6, 26, 1, 0, tzinfo=UTC)
    return SessionRunRecord(
        run_id=run_id,
        tenant_id=tenant_id,
        user_id=user_id,
        thread_id="thread_1",
        checkpoint_ns="reactor",
        status=status,
        input_text="hello",
        response_text="response",
        created_at=started_at.isoformat(),
        updated_at=(started_at + timedelta(milliseconds=duration_ms)).isoformat(),
        metadata={
            "trace_id": trace_id,
            "model": model,
            "channel": channel,
            "durationMs": duration_ms,
            "error_class": error_class,
        },
    )


def slack_run(
    run_id: str,
    *,
    tenant_id: str,
    status: str,
    slack_channel_id: str,
    slack_user_id: str,
    duration_ms: int,
    created_at: str,
) -> SessionRunRecord:
    created = datetime.fromisoformat(created_at)
    return SessionRunRecord(
        run_id=run_id,
        tenant_id=tenant_id,
        user_id=slack_user_id,
        thread_id=f"slack-{slack_channel_id}",
        checkpoint_ns="reactor",
        status=status,
        input_text="slack message",
        response_text="response",
        created_at=created.isoformat(),
        updated_at=(created + timedelta(milliseconds=duration_ms)).isoformat(),
        metadata={
            "channel": "slack",
            "slackChannelId": slack_channel_id,
            "slackUserId": slack_user_id,
            "durationMs": duration_ms,
        },
    )


def usage_record(
    record_id: str,
    *,
    run_id: str,
    total_tokens: int,
    cost: str,
    tenant_id: str = "tenant_1",
) -> UsageLedgerRecord:
    return UsageLedgerRecord(
        id=record_id,
        tenant_id=tenant_id,
        run_id=run_id,
        provider="openai",
        model="gpt-5-mini",
        step_type="chat",
        prompt_tokens=total_tokens,
        completion_tokens=0,
        total_tokens=total_tokens,
        estimated_cost_usd=Decimal(cost),
        occurred_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
    )


def tool_invocation(
    record_id: str,
    *,
    tenant_id: str = "tenant_1",
    run_id: str = "run_1",
    tool_id: str,
    status: str,
    duration_ms: int,
    error_class: str | None = None,
    input_payload: dict[str, object] | None = None,
    output_payload: dict[str, object] | None = None,
    error_payload: dict[str, object] | None = None,
    started_at: datetime | None = None,
) -> ToolInvocationRecord:
    invocation_started_at = started_at or datetime(2026, 6, 26, 1, 0, tzinfo=UTC)
    return ToolInvocationRecord(
        id=record_id,
        tenant_id=tenant_id,
        run_id=run_id,
        tool_id=tool_id,
        approval_id=None,
        status=status,
        idempotency_key=f"idem_{record_id}",
        request_checksum=f"req_{record_id}",
        result_checksum=f"res_{record_id}",
        input_payload=input_payload or {},
        output_payload=output_payload or {},
        error_payload=error_payload
        if error_payload is not None
        else {"error_class": error_class}
        if error_class is not None
        else None,
        started_at=invocation_started_at,
        completed_at=invocation_started_at + timedelta(milliseconds=duration_ms),
    )


def eval_result(
    record_id: str,
    *,
    tenant_id: str,
    case_id: str,
    run_id: str,
    passed: bool,
    score: float,
    evaluated_at: datetime,
) -> AgentEvalStoredResultRecord:
    return AgentEvalStoredResultRecord(
        id=record_id,
        tenant_id=tenant_id,
        case_id=case_id,
        run_id=run_id,
        passed=passed,
        score=score,
        evaluated_at=evaluated_at,
    )


class FakeEvalResultStore:
    def __init__(self, records: list[AgentEvalStoredResultRecord]) -> None:
        self.records = records

    async def analytics_runs(
        self, *, tenant_id: str, from_time: datetime
    ) -> list[dict[str, object]]:
        grouped: dict[str, list[AgentEvalStoredResultRecord]] = {}
        for record in self._matching_records(tenant_id=tenant_id, from_time=from_time):
            grouped.setdefault(record.run_id or "unknown", []).append(record)
        rows: list[dict[str, object]] = []
        for run_id, records in grouped.items():
            rows.append(
                {
                    "eval_run_id": run_id,
                    "total_cases": len(records),
                    "pass_count": sum(1 for record in records if record.passed),
                    "avg_score": round(
                        sum(record.score for record in records) / len(records),
                        6,
                    ),
                    "avg_latency_ms": 0,
                    "total_tokens": 0,
                    "total_cost": 0,
                    "started_at": min(record.evaluated_at for record in records).isoformat(),
                    "ended_at": max(record.evaluated_at for record in records).isoformat(),
                }
            )
        return sorted(rows, key=lambda row: str(row["ended_at"]), reverse=True)

    async def analytics_pass_rate(
        self, *, tenant_id: str, from_time: datetime
    ) -> list[dict[str, object]]:
        grouped: dict[str, list[AgentEvalStoredResultRecord]] = {}
        for record in self._matching_records(tenant_id=tenant_id, from_time=from_time):
            grouped.setdefault(record.evaluated_at.date().isoformat(), []).append(record)
        rows: list[dict[str, object]] = []
        for day, records in grouped.items():
            rows.append(
                {
                    "day": day,
                    "total": len(records),
                    "passed": sum(1 for record in records if record.passed),
                    "avg_score": round(
                        sum(record.score for record in records) / len(records),
                        6,
                    ),
                }
            )
        return sorted(rows, key=lambda row: str(row["day"]), reverse=True)

    def _matching_records(
        self, *, tenant_id: str, from_time: datetime
    ) -> list[AgentEvalStoredResultRecord]:
        return [
            record
            for record in self.records
            if record.tenant_id == tenant_id and record.evaluated_at >= from_time
        ]


class FakeFollowupSuggestionStore:
    def __init__(self, stats: dict[str, object]) -> None:
        self.stats = stats
        self.windows: list[int] = []

    def aggregate_stats(self, *, window_hours: int) -> dict[str, object]:
        self.windows.append(window_hours)
        return dict(self.stats)


class FakeModelPricingStore:
    def __init__(self, records: list[ModelPricing]) -> None:
        self.records = {record.id: record for record in records}

    async def find_all(self) -> list[ModelPricing]:
        return sorted(
            self.records.values(),
            key=lambda record: record.effective_from,
            reverse=True,
        )

    async def save(self, pricing: ModelPricing) -> ModelPricing:
        pricing.validate()
        self.records[pricing.id] = pricing
        return pricing


class FakeRuntimeSettingsStore:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})

    async def list(self, *, tenant_id: str) -> list[object]:
        del tenant_id
        return []

    async def find(self, key: str, *, tenant_id: str) -> RuntimeSettingRecord | None:
        del tenant_id
        value = self.values.get(key)
        if value is None:
            return None
        return RuntimeSettingRecord(key=key, value=value, category="retention")

    async def set(self, update: RuntimeSettingUpdate) -> RuntimeSettingRecord:
        self.values[update.key] = update.value
        return RuntimeSettingRecord(
            tenant_id=update.tenant_id,
            key=update.key,
            value=update.value,
            value_type=update.value_type,
            category=update.category,
            updated_by=update.updated_by,
            metadata=update.metadata,
        )


class FakeMetricIngestionBuffer:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def publish(self, event: dict[str, object]) -> bool:
        self.events.append(event)
        return True


class FakeDurableStore:
    def __init__(self, *, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[str] = []
        self.release_calls: list[str] = []
        self.expired_release_count = 0

    async def durable_queue_diagnostics(self, *, tenant_id: str) -> list[dict[str, object]]:
        self.calls.append(tenant_id)
        return self.rows

    async def release_expired_run_queue(self, *, tenant_id: str) -> int:
        self.release_calls.append(tenant_id)
        return self.expired_release_count


class FakeDebugReplayStore:
    def __init__(self, captures: list[dict[str, object]]) -> None:
        self.captures = captures
        self.list_calls: list[tuple[str, int]] = []

    async def list(self, tenant_id: str, limit: int) -> list[dict[str, object]]:
        self.list_calls.append((tenant_id, limit))
        return [item for item in self.captures if item["tenantId"] == tenant_id][:limit]

    async def find_by_id(self, capture_id: UUID) -> dict[str, object] | None:
        expected = str(capture_id)
        return next((item for item in self.captures if item["id"] == expected), None)


class FakeTaskMemoryMaintenance:
    def __init__(self, *, expired_deleted: int, terminal_deleted: int) -> None:
        self.expired_deleted = expired_deleted
        self.terminal_deleted = terminal_deleted
        self.expired_calls = 0
        self.terminal_cutoffs: list[datetime] = []

    async def purge_expired(self) -> int:
        self.expired_calls += 1
        return self.expired_deleted

    async def purge_terminal_older_than(self, cutoff: datetime) -> int:
        self.terminal_cutoffs.append(cutoff)
        return self.terminal_deleted


class FakeRagDocumentSink:
    def __init__(
        self,
        records: list[RagStatsRecord],
        *,
        status_rows: list[dict[str, object]] | None = None,
        channel_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self._records = records
        self._status_rows = list(status_rows or [])
        self._channel_rows = list(channel_rows or [])
        self.sources: list[RagSourceMigrationRecord] = []
        self.documents: list[RagDocumentMigrationRecord] = []
        self.chunks: list[RagChunkMigrationRecord] = []

    async def stats_by_collection(self, *, tenant_id: str) -> list[RagStatsRecord]:
        del tenant_id
        return self._records

    async def rag_analytics_status_summary(self, *, tenant_id: str) -> list[dict[str, object]]:
        del tenant_id
        return self._status_rows

    async def rag_analytics_by_channel(
        self, *, tenant_id: str, from_time: datetime
    ) -> list[dict[str, object]]:
        del tenant_id, from_time
        return self._channel_rows

    async def save_source(self, record: RagSourceMigrationRecord) -> str:
        self.sources.append(record)
        return record.id

    async def save_document(self, record: RagDocumentMigrationRecord) -> str:
        self.documents.append(record)
        return record.id

    async def save_chunk(self, record: RagChunkMigrationRecord) -> str:
        self.chunks.append(record)
        return record.id


class FakeAdminAuditStore:
    def __init__(self, records: list[AdminAuditLog] | None = None) -> None:
        self.records = list(records or [])
        self.saved: list[AdminAuditLog] = []

    async def list(
        self,
        *,
        tenant_id: str = "tenant_1",
        limit: int = 100,
        category: str | None = None,
        action: str | None = None,
    ) -> list[AdminAuditLog]:
        del tenant_id
        category_filter = category.strip().lower() if category else None
        action_filter = action.strip().upper() if action else None
        rows = [
            record
            for record in self.records
            if (category_filter is None or record.category.lower() == category_filter)
            and (action_filter is None or record.action.value == action_filter)
        ]
        return rows[:limit]

    async def save(self, log: AdminAuditLog, *, tenant_id: str = "tenant_1") -> AdminAuditLog:
        del tenant_id
        self.saved.append(log)
        self.records.insert(0, log)
        return log

    async def find_by_id(
        self, *, tenant_id: str = "tenant_1", audit_id: str
    ) -> AdminAuditLog | None:
        del tenant_id
        return next((record for record in self.records if record.id == audit_id), None)


class FakeSchedulerStore:
    def __init__(self, jobs: list[ScheduledJobRecord]) -> None:
        self.jobs = jobs

    async def list(self, *, tenant_id: str) -> list[ScheduledJobRecord]:
        return [job for job in self.jobs if job.tenant_id == tenant_id]


class FakeExecutionStore:
    def __init__(self, executions: list[ScheduledJobExecutionRecord]) -> None:
        self.executions = executions

    async def find_recent(
        self, *, tenant_id: str, limit: int = 50
    ) -> list[ScheduledJobExecutionRecord]:
        return [execution for execution in self.executions if execution.tenant_id == tenant_id][
            :limit
        ]


class FakeApprovalStore:
    def __init__(self, pending_count: int) -> None:
        self.pending_count = pending_count

    async def list_pending(self, *, tenant_id: str) -> list[object]:
        return [object() for _ in range(self.pending_count) if tenant_id == "tenant_1"]
