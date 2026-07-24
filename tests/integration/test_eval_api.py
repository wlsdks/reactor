from __future__ import annotations

from typing import Any, cast

from httpx import ASGITransport, AsyncClient

from reactor.agents.runner import RunResult
from reactor.api.app import create_app
from reactor.api.routers import agent_eval as agent_eval_router
from reactor.core.settings import Settings
from reactor.evals.judge import AgentEvalLlmJudgeResult
from reactor.evals.models import (
    AgentEvalCaseRecord,
    AgentEvalRunRecord,
    AgentEvalStoredResultRecord,
)
from reactor.persistence.run_store import SessionRunRecord

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


async def test_eval_case_api_crud_filters_tags_and_requires_admin() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/api/admin/agent-eval/cases", headers=MANAGER_HEADERS)
        created = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case_1",
                "name": "Grounded support answer",
                "userInput": "How do I reset MFA?",
                "expectedAnswerContains": ["MFA", "reset"],
                "forbiddenAnswerContains": ["password in plain text"],
                "expectedToolNames": ["knowledge.search"],
                "tags": ["security", "support"],
                "minScore": 0.75,
            },
        )
        listed = await client.get(
            "/api/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            params={"tags": "security", "enabledOnly": True},
        )
        fetched = await client.get("/v1/admin/agent-eval/cases/case_1", headers=ADMIN_HEADERS)
        deleted = await client.delete("/api/admin/agent-eval/cases/case_1", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "permission required: eval:read"
    assert created.status_code == 201
    assert created.json()["assertionCount"] == 4
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == "case_1"
    assert fetched.status_code == 200
    assert fetched.json()["tags"] == ["security", "support"]
    assert deleted.status_code == 204


async def test_eval_case_api_validates_domain_record_before_store_write() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case_blank",
                "name": "   ",
                "userInput": "Summarize incident",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "name is required"
    assert case_store.records == {}


async def test_eval_case_api_rejects_command_unsafe_case_id() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case bad/path",
                "name": "Eval case id should be stable in metadata",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["rollback"],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "id must be command-safe"
    assert case_store.records == {}


async def test_eval_case_api_rejects_colon_case_id() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case:bad",
                "name": "Eval case ids should stay command-safe",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["rollback"],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "id must be command-safe"
    assert case_store.records == {}


async def test_eval_case_api_rejects_documents_ask_placeholder_citation_marker() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case_documents_placeholder",
                "name": "Documents answer should cite a real source",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["[replace-with-source-id]"],
                "tags": ["rag", "documents-ask"],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "documents-ask eval cases cannot use placeholder citation marker"
    )
    assert case_store.records == {}


async def test_eval_case_api_rejects_documents_ask_embedded_placeholder_citation_marker() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case_documents_embedded_placeholder",
                "name": "Documents answer should cite a real source",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["Expected citation marker: [replace-with-source-id]"],
                "tags": ["rag", "documents-ask"],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "documents-ask eval cases cannot use placeholder citation marker"
    )
    assert case_store.records == {}


async def test_eval_case_api_rejects_documents_ask_without_bracketed_citation_marker() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case_documents_unbracketed",
                "name": "Documents answer should cite a bracketed source",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["runbook.md"],
                "tags": ["rag", "documents-ask"],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "documents-ask eval cases require bracketed citations"
    assert case_store.records == {}


async def test_eval_case_api_normalizes_tags_before_workflow_validation() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case_documents_spaced_tag",
                "name": "Documents answer should not bypass citation policy",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["rollback"],
                "tags": ["rag", " documents-ask "],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "documents-ask eval cases require bracketed citations"
    assert case_store.records == {}


async def test_eval_case_api_rejects_feedback_case_without_source_run_id() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case_feedback_missing_source",
                "name": "Feedback promoted answer should preserve source run",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["rollback"],
                "tags": ["feedback:fb_missing_source", "feedback-rating:thumbs_down"],
                "sourceRunId": "   ",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "feedback eval cases require sourceRunId"
    assert case_store.records == {}


async def test_eval_case_api_rejects_command_unsafe_source_run_id() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case_feedback_unsafe_source_run",
                "name": "Feedback promoted answer should preserve safe source run",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["rollback"],
                "tags": ["feedback:fb_1", "feedback-rating:thumbs_down"],
                "sourceRunId": "run bad/path",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "sourceRunId must be command-safe"
    assert case_store.records == {}


async def test_eval_case_api_rejects_blank_feedback_provenance_tag() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case_feedback_blank_tag",
                "name": "Feedback promoted answer should preserve feedback id",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["rollback"],
                "tags": ["feedback:   ", "feedback-rating:thumbs_down"],
                "sourceRunId": "run_feedback_1",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "feedback eval cases require non-empty feedback id"
    assert case_store.records == {}


async def test_eval_case_api_rejects_command_unsafe_feedback_provenance_tag() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case_feedback_unsafe_tag",
                "name": "Feedback promoted answer should preserve safe feedback id",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["rollback"],
                "tags": ["feedback:fb bad/path", "feedback-rating:thumbs_down"],
                "sourceRunId": "run_feedback_1",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "feedback eval cases require command-safe feedback id"
    assert case_store.records == {}


async def test_eval_case_api_rejects_command_unsafe_expected_citation_tag() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case_expected_citation_unsafe_tag",
                "name": "Expected citation tag should be safe",
                "userInput": "How should documents cite sources?",
                "expectedAnswerContains": ["[doc_1]"],
                "tags": ["documents-ask", "expected-citation:doc bad/path"],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "documents-ask eval cases require command-safe citation ids"
    assert case_store.records == {}


async def test_eval_case_api_accepts_chunk_expected_citation_tag() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case_expected_chunk_citation_tag",
                "name": "Expected citation tag should preserve chunk ids",
                "userInput": "How should documents cite chunked sources?",
                "expectedAnswerContains": ["[doc_1:0]"],
                "tags": ["documents-ask", "expected-citation:doc_1:0"],
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["expectedAnswerContains"] == ["[doc_1:0]"]
    assert body["tags"] == ["documents-ask", "expected-citation:doc_1:0"]


async def test_eval_case_api_rejects_expected_citation_tag_marker_mismatch() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case_expected_citation_mismatch",
                "name": "Expected citation tag should match the checked marker",
                "userInput": "How should documents cite chunked sources?",
                "expectedAnswerContains": ["[doc_2:0]"],
                "tags": ["documents-ask", "expected-citation:doc_1:0"],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "documents-ask eval cases require expected-citation tags to match citation markers"
    )
    assert case_store.records == {}


async def test_eval_case_api_rejects_blank_expected_citation_tag() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case_expected_citation_blank_tag",
                "name": "Expected citation tag should not be blank",
                "userInput": "How should documents cite sources?",
                "expectedAnswerContains": ["[doc_1]"],
                "tags": ["documents-ask", "expected-citation:   "],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "documents-ask eval cases require non-empty citation ids"
    assert case_store.records == {}


async def test_eval_case_api_rejects_blank_feedback_rating_tag() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case_feedback_blank_rating",
                "name": "Feedback promoted answer should preserve rating",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["rollback"],
                "tags": ["feedback:fb_1", "feedback-rating:   "],
                "sourceRunId": "run_feedback_1",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "feedback eval cases require non-empty feedback rating"
    assert case_store.records == {}


async def test_eval_case_api_rejects_unknown_feedback_rating_tag() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case_feedback_unknown_rating",
                "name": "Feedback promoted answer should preserve known rating",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["rollback"],
                "tags": ["feedback:fb_1", "feedback-rating:banana"],
                "sourceRunId": "run_feedback_1",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "feedback eval cases require known feedback rating"
    assert case_store.records == {}


async def test_eval_case_api_rejects_feedback_case_without_rating_tag() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/cases",
            headers=ADMIN_HEADERS,
            json={
                "id": "case_feedback_missing_rating",
                "name": "Feedback promoted answer should preserve rating",
                "userInput": "How should rollback work?",
                "expectedAnswerContains": ["rollback"],
                "tags": ["feedback:fb_1"],
                "sourceRunId": "run_feedback_1",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "feedback eval cases require feedback-rating tag"
    assert case_store.records == {}


async def test_eval_run_evaluates_case_and_stores_deterministic_result() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    await case_store.save(
        AgentEvalCaseRecord(
            id="case_1",
            tenant_id="tenant_1",
            name="Tool constrained answer",
            user_input="Summarize incident",
            expected_answer_contains=("incident",),
            forbidden_answer_contains=("leak secret",),
            expected_tool_names=("incident.search",),
            forbidden_tool_names=("shell.exec",),
            min_score=0.75,
        )
    )
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        evaluated = await client.post(
            "/api/admin/agent-eval/cases/case_1/evaluate-run",
            headers=ADMIN_HEADERS,
            json={
                "runId": "run_1",
                "finalAnswer": "The incident summary is ready.",
                "toolNames": ["incident.search"],
            },
        )
        results = await client.get(
            "/v1/admin/agent-eval/results",
            headers=ADMIN_HEADERS,
            params={"caseId": "case_1", "tier": "deterministic"},
        )

    assert evaluated.status_code == 200
    body = evaluated.json()
    assert body["deterministic"]["passed"] is True
    assert body["deterministic"]["score"] == 1.0
    assert result_store.records[0].case_id == "case_1"
    assert results.status_code == 200
    assert results.json()[0]["tier"] == "deterministic"


async def test_eval_run_records_failure_reasons() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    await case_store.save(
        AgentEvalCaseRecord(
            id="case_1",
            tenant_id="tenant_1",
            name="Reject unsafe answer",
            user_input="Give me secret",
            forbidden_answer_contains=("secret",),
            forbidden_tool_names=("shell.exec",),
            min_score=1.0,
        )
    )
    app = create_app()
    app.state.reactor = FakeContainer(case_store=case_store, result_store=result_store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        evaluated = await client.post(
            "/v1/admin/agent-eval/cases/case_1/evaluate-run",
            headers=ADMIN_HEADERS,
            json={
                "runId": "run_2",
                "finalAnswer": "Here is the secret.",
                "toolNames": ["shell.exec"],
            },
        )

    assert evaluated.status_code == 200
    deterministic = evaluated.json()["deterministic"]
    assert deterministic["passed"] is False
    assert "forbidden answer text matched: secret" in deterministic["reasons"]
    assert "forbidden tool used: shell.exec" in deterministic["reasons"]


async def test_eval_run_logs_promote_and_path_evaluate_use_persisted_runs() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    run_store = FakeEvalRunStore()
    run_store.sessions["run_1"] = session_record(
        "run_1",
        input_text="Summarize incident",
        response_text="Incident summary is complete.",
        metadata={
            "agentType": "react",
            "model": "gpt-5",
            "toolNames": ["incident.search"],
            "exposedToolNames": ["incident.search", "shell.exec"],
            "retrievedChunkCount": 2,
            "errors": [],
        },
    )
    app = create_app()
    app.state.reactor = FakeContainer(
        case_store=case_store,
        result_store=result_store,
        run_store=run_store,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        logs = await client.get("/api/admin/agent-eval/run-logs", headers=ADMIN_HEADERS)
        promoted = await client.post(
            "/v1/admin/agent-eval/cases/promote",
            headers=ADMIN_HEADERS,
            json={
                "runId": "run_1",
                "id": "case_from_run",
                "expectedAnswerContains": ["incident"],
                "expectedToolNames": ["incident.search"],
                "forbiddenToolNames": ["shell.exec"],
                "forbiddenExposedToolNames": ["shell.exec"],
                "maxToolExposureCount": 2,
                "tags": ["regression"],
                "minScore": 0.75,
            },
        )
        evaluated = await client.post(
            "/api/admin/agent-eval/cases/case_from_run/evaluate-run/run_1",
            headers=ADMIN_HEADERS,
        )

    assert logs.status_code == 200
    assert logs.json()[0]["runId"] == "run_1"
    assert logs.json()[0]["toolExposureCount"] == 2
    assert logs.json()[0]["finalAnswerPreview"] == "Incident summary is complete."
    assert promoted.status_code == 200
    assert promoted.json()["sourceRunId"] == "run_1"
    assert promoted.json()["assertionCount"] == 7
    assert evaluated.status_code == 200
    assert evaluated.json()["deterministic"]["passed"] is False
    assert "forbidden exposed tool: shell.exec" in evaluated.json()["deterministic"]["reasons"]


async def test_eval_promote_documents_ask_run_preserves_context_manifest_citations() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    run_store = FakeEvalRunStore()
    run_store.sessions["run_rag_answer"] = session_record(
        "run_rag_answer",
        input_text="How should rollback work?",
        response_text="Use the approved rollback runbook. [doc_1]",
        metadata={
            "agentType": "documents-ask",
            "model": "gpt-5",
            "contextManifest": {
                "sections": [
                    {
                        "name": "rag_context",
                        "metadata": {
                            "citation_id": "doc_1",
                            "citations": [
                                {
                                    "citation_id": "doc_1",
                                    "source_uri": "kb://rollback",
                                    "document_id": "doc_1",
                                    "chunk_index": 0,
                                    "content_hash": "hash_doc_1",
                                },
                            ],
                        },
                    },
                ],
            },
        },
    )
    app = create_app()
    app.state.reactor = FakeContainer(
        case_store=case_store,
        result_store=result_store,
        run_store=run_store,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        promoted = await client.post(
            "/v1/admin/agent-eval/cases/promote",
            headers=ADMIN_HEADERS,
            json={
                "runId": "run_rag_answer",
                "id": "case_rag_answer",
                "tags": ["rag", "documents-ask"],
            },
        )

    assert promoted.status_code == 200
    body = promoted.json()
    assert body["sourceRunId"] == "run_rag_answer"
    assert body["expectedAnswerContains"] == ["[doc_1]"]
    assert body["tags"] == ["rag", "documents-ask", "expected-citation:doc_1", "grounding"]
    assert body["assertionCount"] == 3
    assert body["nextActions"] == [
        {
            "id": "apply-to-regression-suite",
            "label": "Apply this promoted case and source run to the regression suite",
            "command": (
                "reactor-runs promote-eval run_rag_answer --case-id case_rag_answer "
                "--case-file promoted-case.json --run-file promoted-run.json "
                "--apply-suite-file tests/fixtures/agent-eval/regression-suite.json "
                "--apply-dry-run --apply-require-source-run-id "
                "--apply-require-run-file --apply-require-context-diagnostics "
                "--apply-suite-summary "
                "--langsmith-dry-run-report-file reports/langsmith-eval-sync-dry-run.json "
                "--output table"
            ),
        }
    ]


async def test_eval_promote_rejects_unsafe_context_manifest_citation_ids() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    run_store = FakeEvalRunStore()
    run_store.sessions["run_rag_unsafe_citation"] = session_record(
        "run_rag_unsafe_citation",
        input_text="How should rollback work?",
        response_text="Use the approved rollback runbook.",
        metadata={
            "agentType": "documents-ask",
            "model": "gpt-5",
            "contextManifest": {
                "sections": [
                    {
                        "name": "rag_context",
                        "metadata": {
                            "citations": [
                                {
                                    "citation_id": "doc bad/path",
                                    "source_uri": "kb://rollback",
                                    "document_id": "doc_1",
                                    "chunk_index": 0,
                                    "content_hash": "hash_doc_1",
                                },
                            ],
                        },
                    },
                ],
            },
        },
    )
    app = create_app()
    app.state.reactor = FakeContainer(
        case_store=case_store,
        result_store=result_store,
        run_store=run_store,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        promoted = await client.post(
            "/v1/admin/agent-eval/cases/promote",
            headers=ADMIN_HEADERS,
            json={
                "runId": "run_rag_unsafe_citation",
                "id": "case_rag_unsafe_citation",
            },
        )

    assert promoted.status_code == 400
    assert promoted.json()["detail"] == (
        "documents-ask eval promotion requires citation-safe context manifest citation ids"
    )
    assert case_store.records == {}


async def test_eval_promote_infers_documents_ask_tags_from_run_context_manifest() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    run_store = FakeEvalRunStore()
    run_store.sessions["run_rag_answer"] = session_record(
        "run_rag_answer",
        input_text="How should rollback work?",
        response_text="Use the approved rollback runbook. [doc_1]",
        metadata={
            "agentType": "documents-ask",
            "model": "gpt-5",
            "contextManifest": {
                "sections": [
                    {
                        "name": "rag_context",
                        "metadata": {
                            "citation_id": "doc_1",
                            "citations": [
                                {
                                    "citation_id": "doc_1",
                                    "source_uri": "kb://rollback",
                                    "document_id": "doc_1",
                                    "chunk_index": 0,
                                    "content_hash": "hash_doc_1",
                                },
                            ],
                        },
                    },
                ],
            },
        },
    )
    app = create_app()
    app.state.reactor = FakeContainer(
        case_store=case_store,
        result_store=result_store,
        run_store=run_store,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        promoted = await client.post(
            "/v1/admin/agent-eval/cases/promote",
            headers=ADMIN_HEADERS,
            json={
                "runId": "run_rag_answer",
                "id": "case_rag_answer",
            },
        )

    assert promoted.status_code == 200
    body = promoted.json()
    assert body["sourceRunId"] == "run_rag_answer"
    assert body["expectedAnswerContains"] == ["[doc_1]"]
    assert body["tags"] == ["rag", "documents-ask", "expected-citation:doc_1", "grounding"]
    assert body["assertionCount"] == 3


async def test_eval_promote_failed_run_preserves_failure_context_without_raw_secrets() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    run_store = FakeEvalRunStore()
    run_store.sessions["run_failed"] = session_record(
        "run_failed",
        status="failed",
        input_text="Investigate provider outage",
        response_text="Provider failed with api_key=sk-live-1234567890abcdef",
        metadata={
            "agentType": "standard",
            "model": "test-model",
            "toolNames": ["Provider:call"],
            "exposedToolNames": ["Provider:call"],
            "errors": ["provider_timeout"],
        },
    )
    app = create_app()
    app.state.reactor = FakeContainer(
        case_store=case_store,
        result_store=result_store,
        run_store=run_store,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        promoted = await client.post(
            "/v1/admin/agent-eval/cases/promote",
            headers=ADMIN_HEADERS,
            json={
                "runId": "run_failed",
                "id": "case_failed_provider",
                "expectedAnswerContains": ["provider outage"],
                "tags": ["regression"],
            },
        )

    assert promoted.status_code == 200
    body = promoted.json()
    assert body["sourceRunId"] == "run_failed"
    assert body["userInput"] == "Investigate provider outage"
    assert body["expectedAnswerContains"] == ["provider outage"]
    assert body["forbiddenAnswerContains"] == [
        "Provider failed with api_key=[REDACTED]",
    ]
    assert body["tags"] == [
        "regression",
        "promoted-from-failed-run",
        "failure-reason:provider_timeout",
    ]
    assert "sk-live-1234567890abcdef" not in promoted.text


async def test_eval_replay_executes_graph_and_stores_llm_judge_tier() -> None:
    case_store = FakeEvalCaseStore()
    result_store = FakeEvalResultStore()
    run_store = FakeEvalRunStore()
    await case_store.save(
        AgentEvalCaseRecord(
            id="case_1",
            tenant_id="tenant_1",
            name="Replay case",
            user_input="Summarize incident",
            expected_answer_contains=("incident",),
            agent_type="react",
            model="gpt-5",
        )
    )
    graph = FakeReplayGraph(response="The incident replay is complete.")
    judge = FakeLlmJudge(passed=True, score=0.9, reason="grounded replay")
    app = create_app()
    app.state.reactor = FakeContainer(
        case_store=case_store,
        result_store=result_store,
        run_store=run_store,
        graph=graph,
        judge=judge,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        replayed = await client.post(
            "/api/admin/agent-eval/cases/case_1/replay",
            headers=ADMIN_HEADERS,
            params={"llmJudge": True},
        )

    assert replayed.status_code == 200
    body = replayed.json()
    assert body["deterministic"]["passed"] is True
    assert [result["tier"] for result in body["storedResults"]] == ["deterministic", "llm_judge"]
    assert result_store.records[0].tier == "llm_judge"
    assert result_store.records[1].tier == "deterministic"
    assert graph.messages == ["Summarize incident"]
    assert run_store.started is not None
    started_metadata = cast(dict[str, object], run_store.started["metadata"])
    assert started_metadata["agentEval.replay"] is True
    assert started_metadata["evalCaseId"] == "case_1"
    assert judge.seen_case_id == "case_1"


async def test_eval_replay_uses_reactor_policy_and_usage_components(
    monkeypatch: Any,
) -> None:
    case_store = FakeEvalCaseStore()
    await case_store.save(
        AgentEvalCaseRecord(
            id="case_policy",
            tenant_id="tenant_1",
            name="Policy-aligned replay",
            user_input="Summarize incident",
            expected_answer_contains=("incident",),
        )
    )
    captured: dict[str, object] = {}
    usage_ledger = object()
    tool_provider = object()
    tool_handler = object()
    tool_invocation_store = object()

    def builtin_tool_specs(_tenant_id: str) -> list[object]:
        return []

    class RecordingRunService:
        def __init__(self, *_args: object, **kwargs: object) -> None:
            captured.update(kwargs)

        async def create_run(self, _message: str, **kwargs: object) -> RunResult:
            return RunResult(
                run_id="run_policy",
                tenant_id=str(kwargs["tenant_id"]),
                user_id=str(kwargs["user_id"]),
                thread_id=str(kwargs["thread_id"]),
                checkpoint_ns="reactor",
                status="completed",
                response="The incident replay is policy aligned.",
                provider="openai",
                model="gpt-5-mini",
            )

    monkeypatch.setattr(agent_eval_router, "RunService", RecordingRunService)
    app = create_app()
    app.state.reactor = FakeContainer(
        case_store=case_store,
        result_store=FakeEvalResultStore(),
        run_store=FakeEvalRunStore(),
        usage_ledger=usage_ledger,
        tool_provider=tool_provider,
        tool_handler=tool_handler,
        tool_invocation_store=tool_invocation_store,
        builtin_tool_specs=builtin_tool_specs,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        replayed = await client.post(
            "/v1/admin/agent-eval/cases/case_policy/replay",
            headers=ADMIN_HEADERS,
        )

    assert replayed.status_code == 200
    assert captured["usage_ledger"] is usage_ledger
    assert captured["tool_provider"] is tool_provider
    assert captured["tool_handler"] is tool_handler
    assert captured["tool_invocation_store"] is tool_invocation_store
    assert captured["builtin_tool_specs"] is builtin_tool_specs


async def test_langsmith_sync_api_exports_tenant_persisted_cases_with_safe_contract(
    monkeypatch: Any,
) -> None:
    case_store = FakeEvalCaseStore()
    case_store.records["case_feedback_1"] = AgentEvalCaseRecord(
        id="case_feedback_1",
        tenant_id="tenant_1",
        name="Weak RAG answer",
        user_input="What is the deployment policy?",
        expected_answer_contains=("[policy:0]",),
        tags=(
            "feedback:fb_1",
            "feedback-rating:thumbs_down",
            "documents-ask",
            "expected-citation:policy:0",
        ),
        source_run_id="run_feedback_1",
    )
    result_store = FakeEvalResultStore()
    container = FakeContainer(case_store=case_store, result_store=result_store)
    container.settings = Settings(observability_langsmith_api_key="test-langsmith-key")
    captured: dict[str, object] = {}

    def fake_export_langsmith_cases(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "datasetName": "reactor-admin-regression",
            "created": False,
            "examples": 1,
            "exampleIds": ["example-1"],
            "caseIds": ["case_feedback_1"],
            "metadataCaseIds": ["case_feedback_1"],
            "sourceRunIds": ["run_feedback_1"],
            "caseSourceRunIds": {"case_feedback_1": "run_feedback_1"},
            "splitCounts": {"regression": 1},
            "exampleContract": {"secretScan": {"enabled": True}},
            "sdkContract": {"sdk": "langsmith", "sourceControlledCases": True},
        }

    monkeypatch.setattr(
        "reactor.api.routers.agent_eval.export_langsmith_cases",
        fake_export_langsmith_cases,
    )
    app = create_app()
    app.state.reactor = container
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/admin/agent-eval/langsmith/sync",
            headers=ADMIN_HEADERS,
            json={
                "datasetName": "reactor-admin-regression",
                "caseIds": ["case_feedback_1"],
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["status"] == "passed"
    assert body["scope"] == "langsmith_persisted_eval_dataset_sync"
    assert body["caseIds"] == ["case_feedback_1"]
    assert body["metadataCaseIds"] == ["case_feedback_1"]
    assert body["sourceRunIds"] == ["run_feedback_1"]
    assert body["secretFree"] is True
    assert body["sdkContract"]["source"] == "persisted_tenant_eval_cases"
    assert body["sdkContract"]["sourceControlledCases"] is False
    assert "test-langsmith-key" not in str(body)
    synced_cases = cast(list[AgentEvalCaseRecord], captured["cases"])
    assert [case.id for case in synced_cases] == ["case_feedback_1"]


async def test_langsmith_sync_api_fails_closed_without_configured_key() -> None:
    case_store = FakeEvalCaseStore()
    case_store.records["case_1"] = AgentEvalCaseRecord(
        id="case_1",
        tenant_id="tenant_1",
        name="Eval case",
        user_input="Question",
    )
    app = create_app()
    app.state.reactor = FakeContainer(
        case_store=case_store,
        result_store=FakeEvalResultStore(),
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/admin/agent-eval/langsmith/sync",
            headers=ADMIN_HEADERS,
            json={"datasetName": "reactor-admin-regression", "caseIds": ["case_1"]},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "LangSmith API key is not configured"


class FakeContainer:
    def __init__(
        self,
        *,
        case_store: FakeEvalCaseStore,
        result_store: FakeEvalResultStore,
        run_store: FakeEvalRunStore | None = None,
        graph: FakeReplayGraph | None = None,
        judge: FakeLlmJudge | None = None,
        usage_ledger: object | None = None,
        tool_provider: object | None = None,
        tool_handler: object | None = None,
        tool_invocation_store: object | None = None,
        builtin_tool_specs: Any | None = None,
    ) -> None:
        self._case_store = case_store
        self._result_store = result_store
        self._run_store = run_store
        self.settings = Settings()
        self.graph = graph
        self._judge = judge
        self._usage_ledger = usage_ledger
        self._tool_provider = tool_provider
        self._tool_handler = tool_handler
        self._tool_invocation_store = tool_invocation_store
        self.builtin_tool_specs = builtin_tool_specs

    def eval_case_store(self) -> FakeEvalCaseStore:
        return self._case_store

    def eval_result_store(self) -> FakeEvalResultStore:
        return self._result_store

    def run_store(self) -> FakeEvalRunStore | None:
        return self._run_store

    def eval_llm_judge(self) -> FakeLlmJudge | None:
        return self._judge

    def usage_ledger(self) -> object | None:
        return self._usage_ledger

    def tool_store(self) -> object | None:
        return self._tool_provider

    def agent_tool_handler(self) -> object | None:
        return self._tool_handler

    def tool_invocation_store(self) -> object | None:
        return self._tool_invocation_store


class FakeEvalCaseStore:
    def __init__(self) -> None:
        self.records: dict[str, AgentEvalCaseRecord] = {}

    async def save(self, record: AgentEvalCaseRecord) -> AgentEvalCaseRecord:
        self.records[record.id] = record
        return record

    async def find_by_id(self, *, tenant_id: str, case_id: str) -> AgentEvalCaseRecord | None:
        record = self.records.get(case_id)
        return record if record is not None and record.tenant_id == tenant_id else None

    async def list(
        self,
        *,
        tenant_id: str,
        enabled_only: bool = True,
        tags: set[str] | None = None,
        limit: int = 100,
    ) -> list[AgentEvalCaseRecord]:
        rows = [record for record in self.records.values() if record.tenant_id == tenant_id]
        if enabled_only:
            rows = [record for record in rows if record.enabled]
        if tags:
            rows = [record for record in rows if set(record.tags).issuperset(tags)]
        return rows[:limit]

    async def delete(self, *, tenant_id: str, case_id: str) -> bool:
        record = await self.find_by_id(tenant_id=tenant_id, case_id=case_id)
        if record is None:
            return False
        self.records.pop(case_id)
        return True


class FakeEvalResultStore:
    def __init__(self) -> None:
        self.records: list[AgentEvalStoredResultRecord] = []

    async def save(self, record: AgentEvalStoredResultRecord) -> AgentEvalStoredResultRecord:
        self.records.insert(0, record)
        return record

    async def list(
        self,
        *,
        tenant_id: str,
        case_id: str | None = None,
        tier: str | None = None,
        limit: int = 100,
    ) -> list[AgentEvalStoredResultRecord]:
        rows = [record for record in self.records if record.tenant_id == tenant_id]
        if case_id is not None:
            rows = [record for record in rows if record.case_id == case_id]
        if tier is not None:
            rows = [record for record in rows if record.tier == tier]
        return rows[:limit]

    async def delete_by_case_id(self, *, tenant_id: str, case_id: str) -> int:
        matching = [
            record
            for record in self.records
            if record.tenant_id == tenant_id and record.case_id == case_id
        ]
        self.records = [record for record in self.records if record not in matching]
        return len(matching)


class FakeEvalRunStore:
    def __init__(self) -> None:
        self.sessions: dict[str, SessionRunRecord] = {}
        self.started: dict[str, Any] | None = None

    async def list_recent_runs(
        self,
        *,
        tenant_id: str,
        limit: int = 50,
    ) -> list[SessionRunRecord]:
        rows = [record for record in self.sessions.values() if record.tenant_id == tenant_id]
        return rows[:limit]

    async def find_session(self, *, run_id: str) -> SessionRunRecord | None:
        return self.sessions.get(run_id)

    async def record_started(
        self,
        *,
        run_id: str,
        tenant_id: str,
        user_id: str,
        thread_id: str,
        checkpoint_ns: str,
        input_text: str,
        metadata: dict[str, object],
    ) -> str:
        self.started = {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "input_text": input_text,
            "metadata": metadata,
        }
        self.sessions[run_id] = session_record(
            run_id,
            input_text=input_text,
            response_text="",
            metadata=metadata,
        )
        return "queue_1"

    async def record_completed(self, *, result: RunResult, metadata: dict[str, object]) -> None:
        existing = self.sessions[result.run_id]
        self.sessions[result.run_id] = session_record(
            result.run_id,
            input_text=existing.input_text,
            response_text=result.response,
            metadata=metadata,
        )

    async def record_event(self, **_: object) -> None:
        return None

    async def list_events(self, **_: object) -> list[object]:
        return []


class FakeReplayGraph:
    def __init__(self, *, response: str) -> None:
        self._response = response
        self.messages: list[str] = []

    async def ainvoke(self, state: dict[str, object], config: dict[str, object]) -> dict[str, str]:
        del config
        messages = state.get("messages")
        if isinstance(messages, list) and messages:
            first = cast(list[object], messages)[0]
            self.messages.append(str(getattr(first, "content", "")))
        return {"response_text": self._response}


class FakeLlmJudge:
    def __init__(self, *, passed: bool, score: float, reason: str) -> None:
        self._result = AgentEvalLlmJudgeResult(passed=passed, score=score, reason=reason)
        self.seen_case_id: str | None = None

    async def judge(
        self, case: AgentEvalCaseRecord, run: AgentEvalRunRecord
    ) -> AgentEvalLlmJudgeResult:
        del run
        self.seen_case_id = case.id
        return self._result


def session_record(
    run_id: str,
    *,
    status: str = "completed",
    input_text: str,
    response_text: str,
    metadata: dict[str, object],
) -> SessionRunRecord:
    return SessionRunRecord(
        run_id=run_id,
        tenant_id="tenant_1",
        user_id="user_1",
        thread_id=f"thread_{run_id}",
        checkpoint_ns="",
        status=status,
        input_text=input_text,
        response_text=response_text,
        created_at="2026-06-26T00:00:00+00:00",
        updated_at="2026-06-26T00:00:00+00:00",
        metadata=metadata,
    )
