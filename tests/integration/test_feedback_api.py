from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app
from reactor.feedback.workflow import feedback_matches_eval_case_id
from reactor.memory.lifecycle_actions import MEMORY_LIFECYCLE_GATE_ACTION
from reactor.release.readiness_actions import release_readiness_command_for_reports
from reactor.slack.feedback import (
    Feedback,
    FeedbackRating,
    feedback_analytics_payload,
    feedback_review_matches,
)

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}

USER_HEADERS = {
    "X-Reactor-User-Id": "user_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "USER",
}

RAG_CANDIDATE_REQUIRED_REVIEW_NOTE = (
    "Promoted to regression eval and reviewed in hardening/LangSmith. "
    "Required readiness reports: hardening_suite, langsmith_eval_sync."
)
RAG_CANDIDATE_C1_BULK_REVIEW_ACTION = (
    "reactor-admin feedback-bulk-review --candidate-tag rag-candidate:c1 "
    "--status done --tag promoted --tag langsmith "
    "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 "
    "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
    "--output table"
)
RAG_CANDIDATE_C1_SLACK_BULK_REVIEW_ACTION = (
    "reactor-admin feedback-bulk-review --candidate-tag rag-candidate:c1 "
    "--source slack_button --status done --tag promoted --tag langsmith "
    "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 "
    "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
    "--output table"
)
RAG_CANDIDATE_C1_API_BULK_REVIEW_ACTION = (
    "reactor-admin feedback-bulk-review --candidate-tag rag-candidate:c1 "
    "--source api --status done --tag promoted --tag langsmith "
    "--tag expected-citation:candidate-runbook.md "
    "--tag collection:rag-ingestion-candidate --tag rag-candidate:c1 "
    "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
    "--output table"
)
RAG_CANDIDATE_C1_READINESS_COMMAND = release_readiness_command_for_reports(
    required_reports=("hardening_suite", "langsmith_eval_sync"),
    report_files={
        "hardening_suite": "reports/hardening-suite.json",
        "langsmith_eval_sync": (
            "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
        ),
    },
)
DOC_ASK_LANGSMITH_READINESS_COMMAND = release_readiness_command_for_reports(
    required_reports=("hardening_suite", "langsmith_eval_sync"),
    report_files={
        "hardening_suite": "reports/hardening-suite.json",
        "langsmith_eval_sync": "reports/langsmith-eval-sync-dry-run.json",
    },
)


async def test_feedback_api_submit_list_get_and_delete_contract() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "원래 질문",
                "response": "틀린 답변",
                "comment": "틀렸어요",
                "sessionId": "session_1",
                "runId": "run_1",
                "intent": "support",
                "domain": "auth",
                "model": "gpt-4.1-mini",
                "promptVersion": 2,
                "toolsUsed": ["rag.search"],
                "durationMs": 321,
                "source": "admin_cli",
                "tags": ["accuracy"],
                "templateId": "tmpl-1",
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        forbidden_list = await client.get("/api/feedback", headers=USER_HEADERS)
        listed = await client.get(
            "/v1/feedback",
            headers=ADMIN_HEADERS,
            params={"rating": "thumbs_down", "limit": 10},
        )
        fetched = await client.get(f"/api/feedback/{feedback_id}", headers=ADMIN_HEADERS)
        deleted = await client.delete(f"/v1/feedback/{feedback_id}", headers=ADMIN_HEADERS)
        missing = await client.get(f"/api/feedback/{feedback_id}", headers=ADMIN_HEADERS)

    assert submitted.status_code == 201
    assert submitted.json()["rating"] == "thumbs_down"
    assert submitted.json()["source"] == "admin_cli"
    assert submitted.json()["query"] == "원래 질문"
    assert submitted.json()["userId"] == "user_1"
    assert submitted.json()["intent"] == "support"
    assert submitted.json()["domain"] == "auth"
    assert submitted.json()["model"] == "gpt-4.1-mini"
    assert submitted.json()["promptVersion"] == 2
    assert submitted.json()["toolsUsed"] == ["rag.search"]
    assert submitted.json()["durationMs"] == 321
    assert submitted.json()["tags"] == ["accuracy", "rag", "grounding"]
    assert submitted.json()["templateId"] == "tmpl-1"
    assert "nextActions" not in submitted.json()
    assert forbidden_list.status_code == 403
    assert listed.status_code == 200
    assert listed.json()["approximateTotal"] == 1
    assert listed.json()["items"][0]["feedbackId"] == feedback_id
    assert listed.json()["items"][0]["source"] == "admin_cli"
    assert listed.json()["items"][0]["readyNextActionIds"] == ["promote-eval"]
    assert listed.json()["items"][0]["blockedNextActionIds"] == [
        "persist-eval-suite",
        "summarize-langsmith",
        "preflight-langsmith",
        "sync-langsmith",
        "refresh-readiness",
        "review-done",
    ]
    assert listed.json()["items"][0]["nextActionStates"] == {
        "promote-eval": "ready",
        "persist-eval-suite": "blocked",
        "summarize-langsmith": "blocked",
        "preflight-langsmith": "blocked",
        "sync-langsmith": "blocked",
        "refresh-readiness": "blocked",
        "review-done": "blocked",
    }
    assert fetched.json()["source"] == "admin_cli"
    listed_actions = {action["id"]: action for action in listed.json()["items"][0]["nextActions"]}
    assert list(listed_actions) == [
        "promote-eval",
        "persist-eval-suite",
        "summarize-langsmith",
        "preflight-langsmith",
        "sync-langsmith",
        "refresh-readiness",
        "review-done",
    ]
    promote_action = listed_actions["promote-eval"]
    assert promote_action["evalCaseId"] == "case_run_1"
    assert promote_action["sourceRunId"] == "run_1"
    assert promote_action["feedbackSource"] == "admin_cli"
    assert promote_action["caseFile"] == "promoted-case.json"
    assert promote_action["runFile"] == "promoted-run.json"
    assert promote_action["requiredReadinessReports"] == ["langsmith_eval_sync"]
    assert (
        f"--tag feedback:{feedback_id} --tag feedback-rating:thumbs_down"
        in promote_action["command"]
    )
    assert "--feedback-source admin_cli" in promote_action["command"]
    required_env_any_of = listed_actions["preflight-langsmith"]["requiredEnvAnyOf"]
    assert ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"] in (required_env_any_of)
    assert listed_actions["sync-langsmith"]["recommendedEnv"] == ["LANGSMITH_ENDPOINT"]
    assert listed_actions["persist-eval-suite"]["dependsOnActionIds"] == ["promote-eval"]
    assert listed_actions["summarize-langsmith"]["dependsOnActionIds"] == ["persist-eval-suite"]
    assert listed_actions["preflight-langsmith"]["dependsOnActionIds"] == ["summarize-langsmith"]
    assert listed_actions["sync-langsmith"]["dependsOnActionIds"] == ["preflight-langsmith"]
    assert listed_actions["refresh-readiness"]["dependsOnActionIds"] == ["sync-langsmith"]
    assert listed_actions["review-done"]["dependsOnActionIds"] == ["refresh-readiness"]
    assert (
        listed_actions["refresh-readiness"]["releaseReadinessFile"]
        == "reports/release-readiness.json"
    )
    assert (
        "--tag promoted --tag langsmith --tag rag --tag grounding"
        in (listed_actions["review-done"]["command"])
    )
    assert fetched.status_code == 200
    assert fetched.json()["comment"] == "틀렸어요"
    assert fetched.json()["readyNextActionIds"] == ["promote-eval"]
    assert fetched.json()["blockedNextActionIds"] == [
        "persist-eval-suite",
        "summarize-langsmith",
        "preflight-langsmith",
        "sync-langsmith",
        "refresh-readiness",
        "review-done",
    ]
    assert fetched.json()["nextActionStates"] == {
        "promote-eval": "ready",
        "persist-eval-suite": "blocked",
        "summarize-langsmith": "blocked",
        "preflight-langsmith": "blocked",
        "sync-langsmith": "blocked",
        "refresh-readiness": "blocked",
        "review-done": "blocked",
    }
    assert fetched.json()["nextActions"][0]["id"] == "promote-eval"
    assert "VERIFY_TIMESTAMP" not in str(fetched.json()["nextActions"])
    assert fetched.json()["templateId"] == "tmpl-1"
    assert deleted.status_code == 204
    assert missing.status_code == 404


async def test_feedback_api_admin_submit_returns_review_next_actions() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/v1/feedback",
            headers=ADMIN_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "Evaluate candidate answer",
                "response": "Answer still misses citation.",
                "comment": "Operator submitted weak answer from candidate review",
                "runId": "run_rag_candidate_1",
                "tags": ["collection:rag-ingestion-candidate"],
            },
        )

    assert submitted.status_code == 201
    action_items = {action["id"]: action for action in submitted.json()["nextActions"]}
    actions = {action_id: action["command"] for action_id, action in action_items.items()}
    for action in action_items.values():
        assert "recommendedVersionBump" not in action
        assert "recommendedTagPattern" not in action
        if action["id"] != "refresh-readiness":
            assert "minorBoundaryReports" not in action
    assert "promote-eval" in actions
    assert "persist-eval-suite" in actions
    assert "sync-langsmith" in actions
    assert "refresh-readiness" in actions
    assert "inspect-candidate-feedback" in actions
    assert "export-candidate-feedback" in actions
    assert "review-done" in actions
    assert (
        "--apply-suite-file evals/regression/rag-ingestion-candidate.json"
        in actions["promote-eval"]
    )
    assert (
        "reactor-runs promote-eval run_rag_candidate_1 --case-id case_rag_candidate_1"
        in actions["promote-eval"]
    )
    assert "case_run_rag_candidate_1" not in actions["promote-eval"]
    assert "--tag rag-candidate:1" in actions["promote-eval"]
    assert "--tag rag-candidate:1" in actions["review-done"]
    feedback_id = submitted.json()["feedbackId"]
    assert action_items["promote-eval"]["feedbackTags"] == [
        f"feedback:{feedback_id}",
        "feedback-rating:thumbs_down",
        "rag",
        "grounding",
        "citation-failure",
        "collection:rag-ingestion-candidate",
        "rag-candidate:1",
    ]
    assert action_items["promote-eval"]["workflowTags"] == [
        "rag",
        "grounding",
        "citation-failure",
        "collection:rag-ingestion-candidate",
        "rag-candidate:1",
    ]
    assert action_items["review-done"]["workflowTags"] == [
        "rag",
        "grounding",
        "citation-failure",
        "collection:rag-ingestion-candidate",
        "rag-candidate:1",
    ]
    assert action_items["refresh-readiness"]["label"] == (
        "Refresh release readiness with candidate LangSmith and hardening reports"
    )
    assert action_items["refresh-readiness"]["requiredReadinessReports"] == [
        "hardening_suite",
        "langsmith_eval_sync",
    ]
    assert action_items["refresh-readiness"]["readinessReports"] == {
        "hardening_suite": "reports/hardening-suite.json",
        "langsmith_eval_sync": (
            "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_1.json"
        ),
    }
    assert action_items["refresh-readiness"]["minorBoundaryReports"] == [
        "hardening_suite",
        "langsmith_eval_sync",
    ]
    assert (
        action_items["refresh-readiness"]["recommendedTagSource"]
        == "release_readiness.tagRecommendation.recommendedTag"
    )
    assert action_items["refresh-readiness"]["latestTagCommand"] == (
        "git describe --tags --abbrev=0"
    )
    assert "--required-readiness-report hardening_suite" in actions["refresh-readiness"]
    assert "--required-readiness-report langsmith_eval_sync" in actions["refresh-readiness"]
    assert (
        "--readiness-report hardening_suite=reports/hardening-suite.json"
        in actions["refresh-readiness"]
    )
    assert (
        "--readiness-report "
        "langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_1.json"
        in actions["refresh-readiness"]
    )
    assert actions["inspect-candidate-feedback"] == (
        "reactor-admin feedback --rating thumbs_down "
        "--source api "
        "--review-status inbox "
        "--tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:1 --limit 10 --output table"
    )
    assert actions["export-candidate-feedback"] == (
        "reactor-admin feedback-export --rating thumbs_down "
        "--source api "
        "--review-status inbox "
        "--tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:1 --limit 10 --output json"
    )
    assert (
        f"reactor-admin feedback-review {submitted.json()['feedbackId']}" in actions["review-done"]
    )


async def test_feedback_api_openapi_names_next_action_contract() -> None:
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=FakeFeedbackStore())
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/openapi.json")

    schemas = response.json()["components"]["schemas"]
    assert schemas["FeedbackNextAction"]["required"] == ["id", "label", "command"]
    assert schemas["FeedbackNextAction"]["properties"] == {
        "id": {"type": "string", "minLength": 1, "title": "Id"},
        "label": {"type": "string", "minLength": 1, "title": "Label"},
        "command": {"type": "string", "minLength": 1, "title": "Command"},
        "feedbackId": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Feedbackid",
        },
        "evalCaseId": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Evalcaseid",
        },
        "sourceRunId": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Sourcerunid",
        },
        "subjectUserId": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Subjectuserid",
        },
        "candidateTag": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Candidatetag",
        },
        "reportFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Reportfile",
        },
        "caseFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Casefile",
        },
        "runFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Runfile",
        },
        "suiteFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Suitefile",
        },
        "datasetName": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Datasetname",
        },
        "preflightFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Preflightfile",
        },
        "preflightEnvTemplate": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Preflightenvtemplate",
        },
        "replatformReadinessFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Replatformreadinessfile",
        },
        "smokePlanFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Smokeplanfile",
        },
        "releaseEvidenceFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Releaseevidencefile",
        },
        "releaseReadinessFile": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Releasereadinessfile",
        },
        "releaseReadinessCommand": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Releasereadinesscommand",
        },
        "remediationCommand": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Remediationcommand",
        },
        "envFileCommand": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Envfilecommand",
        },
        "readinessReportArg": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Readinessreportarg",
        },
        "requiredReadinessReports": {
            "anyOf": [
                {"items": {"type": "string"}, "type": "array", "minItems": 1},
                {"type": "null"},
            ],
            "title": "Requiredreadinessreports",
        },
        "readinessReports": {
            "anyOf": [
                {
                    "additionalProperties": {"type": "string"},
                    "type": "object",
                    "minProperties": 1,
                },
                {"type": "null"},
            ],
            "title": "Readinessreports",
        },
        "requiredEnvAnyOf": {
            "anyOf": [
                {
                    "items": {"items": {"type": "string"}, "type": "array"},
                    "type": "array",
                    "minItems": 1,
                },
                {"type": "null"},
            ],
            "title": "Requiredenvanyof",
        },
        "dependsOnActionIds": {
            "anyOf": [
                {"items": {"type": "string"}, "type": "array", "minItems": 1},
                {"type": "null"},
            ],
            "title": "Dependsonactionids",
        },
        "missingEnvAnyOf": {
            "anyOf": [
                {"items": {"type": "string"}, "type": "array", "minItems": 1},
                {"type": "null"},
            ],
            "title": "Missingenvanyof",
        },
        "recommendedEnv": {
            "anyOf": [
                {"items": {"type": "string"}, "type": "array", "minItems": 1},
                {"type": "null"},
            ],
            "title": "Recommendedenv",
        },
        "recommendedVersionBump": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Recommendedversionbump",
        },
        "recommendedTagPattern": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Recommendedtagpattern",
        },
        "latestTagCommand": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Latesttagcommand",
        },
        "recommendedTagSource": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Recommendedtagsource",
        },
        "minorBoundaryReports": {
            "anyOf": [
                {"items": {"type": "string"}, "type": "array", "minItems": 1},
                {"type": "null"},
            ],
            "title": "Minorboundaryreports",
        },
        "feedbackTags": {
            "anyOf": [
                {"items": {"type": "string"}, "type": "array", "minItems": 1},
                {"type": "null"},
            ],
            "title": "Feedbacktags",
        },
        "feedbackSource": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Feedbacksource",
        },
        "workflowTags": {
            "anyOf": [
                {"items": {"type": "string"}, "type": "array", "minItems": 1},
                {"type": "null"},
            ],
            "title": "Workflowtags",
        },
        "expectedAnswers": {
            "anyOf": [
                {"items": {"type": "string"}, "type": "array", "minItems": 1},
                {"type": "null"},
            ],
            "title": "Expectedanswers",
        },
        "requiredReviewNote": {
            "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
            "title": "Requiredreviewnote",
        },
    }
    feedback_response = schemas["FeedbackResponse"]
    next_actions = feedback_response["properties"]["nextActions"]
    assert next_actions["anyOf"][0]["items"] == {"$ref": "#/components/schemas/FeedbackNextAction"}
    feedback_export = schemas["FeedbackExportResponse"]
    assert feedback_export["properties"]["items"]["items"] == {
        "$ref": "#/components/schemas/FeedbackExportItem"
    }
    assert "source" in schemas["FeedbackExportItem"]["required"]
    assert schemas["FeedbackExportItem"]["properties"]["source"] == {
        "type": "string",
        "title": "Source",
    }
    assert "version" in schemas["FeedbackExportItem"]["required"]
    assert schemas["FeedbackExportItem"]["properties"]["version"] == {
        "type": "integer",
        "title": "Version",
    }
    assert "updatedAt" in schemas["FeedbackExportItem"]["required"]
    assert schemas["FeedbackExportItem"]["properties"]["updatedAt"] == {
        "type": "string",
        "title": "Updatedat",
    }
    export_next_actions = schemas["FeedbackExportItem"]["properties"]["nextActions"]
    assert export_next_actions["items"] == {"$ref": "#/components/schemas/FeedbackNextAction"}
    bulk_response_ref = response.json()["paths"]["/api/feedback/bulk-update"]["post"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]
    assert bulk_response_ref == {"$ref": "#/components/schemas/BulkFeedbackReviewUpdateResponse"}
    bulk_response = schemas["BulkFeedbackReviewUpdateResponse"]
    assert bulk_response["required"] == ["updated", "failed"]
    assert bulk_response["properties"]["updated"] == {
        "items": {"type": "string"},
        "type": "array",
        "title": "Updated",
    }
    assert bulk_response["properties"]["updatedDetails"]["anyOf"][0]["items"] == {
        "$ref": "#/components/schemas/FeedbackReviewHandoffDetail"
    }
    handoff_detail = schemas["FeedbackReviewHandoffDetail"]
    assert handoff_detail["required"] == ["feedbackId"]
    assert handoff_detail["properties"]["readinessReportArg"] == {
        "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
        "title": "Readinessreportarg",
    }
    assert handoff_detail["properties"]["readinessReports"]["anyOf"][0] == {
        "additionalProperties": {"type": "string"},
        "type": "object",
        "minProperties": 1,
    }
    assert handoff_detail["properties"]["requiredEnvAnyOf"] == {
        "anyOf": [
            {
                "items": {"items": {"type": "string"}, "type": "array"},
                "type": "array",
                "minItems": 1,
            },
            {"type": "null"},
        ],
        "title": "Requiredenvanyof",
    }
    assert handoff_detail["properties"]["missingEnvAnyOf"] == {
        "anyOf": [
            {"items": {"type": "string"}, "type": "array", "minItems": 1},
            {"type": "null"},
        ],
        "title": "Missingenvanyof",
    }
    assert handoff_detail["properties"]["recommendedEnv"] == {
        "anyOf": [
            {"items": {"type": "string"}, "type": "array", "minItems": 1},
            {"type": "null"},
        ],
        "title": "Recommendedenv",
    }
    bulk_failure = schemas["BulkFeedbackReviewFailure"]
    assert bulk_failure["properties"]["requiredReviewNote"] == {
        "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}],
        "title": "Requiredreviewnote",
    }
    assert bulk_failure["properties"]["nextActions"]["anyOf"][0]["items"] == {
        "$ref": "#/components/schemas/FeedbackNextAction"
    }
    assert bulk_failure["properties"]["requiredEnvAnyOf"] == {
        "anyOf": [
            {
                "items": {"items": {"type": "string"}, "type": "array"},
                "type": "array",
                "minItems": 1,
            },
            {"type": "null"},
        ],
        "title": "Requiredenvanyof",
    }
    assert bulk_failure["properties"]["recommendedEnv"] == {
        "anyOf": [
            {"items": {"type": "string"}, "type": "array", "minItems": 1},
            {"type": "null"},
        ],
        "title": "Recommendedenv",
    }
    export_workflow = schemas["FeedbackExportItem"]["properties"]["workflow"]
    assert export_workflow["anyOf"][0] == {"$ref": "#/components/schemas/FeedbackExportWorkflow"}
    assert schemas["FeedbackExportWorkflow"]["required"] == [
        "type",
        "candidateId",
        "collection",
        "sourceUri",
        "evalCaseId",
        "runId",
        "sourceRunId",
        "feedbackSource",
        "feedbackTag",
    ]
    assert schemas["FeedbackExportWorkflow"]["properties"]["feedbackSource"] == {
        "type": "string",
        "minLength": 1,
        "title": "Feedbacksource",
    }


async def test_feedback_next_action_tags_rag_citation_failures_for_eval_promotion() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "VectorStore rollback 절차 알려줘",
                "response": "출처 없이 답했어요",
                "comment": "RAG citation missing; expected [vectorstore-runbook.md]",
                "runId": "run_rag_1",
                "toolsUsed": ["Rag:hybrid_search"],
                "tags": ["missing_sources"],
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        fetched = await client.get(f"/api/feedback/{feedback_id}", headers=ADMIN_HEADERS)

    assert fetched.status_code == 200
    action_items = {action["id"]: action for action in fetched.json()["nextActions"]}
    next_actions = {action_id: action["command"] for action_id, action in action_items.items()}
    promotion_command = next_actions["promote-eval"]
    review_command = next_actions["review-done"]
    assert "--apply-require-source-run-id" in promotion_command
    for command in [promotion_command, review_command]:
        assert "--tag rag" in command
        assert "--tag grounding" in command
        assert "--tag citation-failure" in command
        assert "--tag documents-ask" in command
    assert "sync-langsmith" in next_actions
    assert "refresh-readiness" in next_actions
    assert action_items["sync-langsmith"]["feedbackId"] == feedback_id
    assert action_items["refresh-readiness"]["feedbackId"] == feedback_id
    assert "--expected-answer '[vectorstore-runbook.md]'" in promotion_command


async def test_feedback_next_action_tags_documents_ask_citation_failures() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "How should document answers cite sources?",
                "response": "It mentioned the runbook but did not cite it.",
                "comment": "Missing citation marker [runbook.md] in documents ask answer",
                "runId": "run_doc_ask_1",
                "tags": ["documents-ask"],
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        fetched = await client.get(f"/api/feedback/{feedback_id}", headers=ADMIN_HEADERS)

    assert fetched.status_code == 200
    next_actions = {action["id"]: action["command"] for action in fetched.json()["nextActions"]}
    promotion_command = next_actions["promote-eval"]
    review_command = next_actions["review-done"]
    for command in [promotion_command, review_command]:
        assert "--tag rag" in command
        assert "--tag grounding" in command
        assert "--tag citation-failure" in command
        assert "--tag documents-ask" in command
    assert "sync-langsmith" in next_actions
    assert "refresh-readiness" in next_actions
    assert "--expected-answer '[runbook.md]'" in promotion_command


async def test_feedback_next_action_applies_rag_candidate_suite() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "How should this candidate cite the ingested runbook?",
                "response": "It answered without [candidate-runbook.md].",
                "comment": "Missing citation marker [candidate-runbook.md]",
                "runId": "run_rag_candidate_1",
                "tags": [
                    "collection:rag-ingestion-candidate",
                    "rag-candidate:c1",
                    "documents-ask",
                ],
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        fetched = await client.get(f"/api/feedback/{feedback_id}", headers=ADMIN_HEADERS)

    assert fetched.status_code == 200
    next_actions = fetched.json()["nextActions"]
    assert [action["id"] for action in next_actions] == [
        "promote-eval",
        "persist-eval-suite",
        "summarize-langsmith",
        "preflight-langsmith",
        "sync-langsmith",
        "generate-hardening-suite",
        "refresh-readiness",
        "inspect-candidate-feedback",
        "export-candidate-feedback",
        "bulk-review-candidate-feedback",
        "review-done",
    ]
    promotion_command = next_actions[0]["command"]
    persist_command = next_actions[1]["command"]
    summary_command = next_actions[2]["command"]
    preflight_command = next_actions[3]["command"]
    langsmith_command = next_actions[4]["command"]
    hardening_command = next_actions[5]["command"]
    readiness_command = next_actions[6]["command"]
    candidate_review_command = next_actions[7]["command"]
    candidate_export_command = next_actions[8]["command"]
    candidate_bulk_review_command = next_actions[9]["command"]
    review_command = next_actions[10]["command"]
    for action in next_actions[:7]:
        assert action["evalCaseId"] == "case_rag_candidate_c1"
        assert action["sourceRunId"] == "run_rag_candidate_1"
        assert action["suiteFile"] == "evals/regression/rag-ingestion-candidate.json"
        assert action["datasetName"] == "reactor-rag-ingestion-candidate"
    for action in [*next_actions[:5], next_actions[6]]:
        assert action["readinessReportArg"] == (
            "--readiness-report hardening_suite=reports/hardening-suite.json "
            "--readiness-report "
            "langsmith_eval_sync=artifacts/langsmith/"
            "rag-ingestion-candidate-case_rag_candidate_c1.json"
        )
        assert action["requiredReadinessReports"] == ["hardening_suite", "langsmith_eval_sync"]
        assert action["readinessReports"] == {
            "hardening_suite": "reports/hardening-suite.json",
            "langsmith_eval_sync": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
            ),
        }
    assert next_actions[5]["readinessReportArg"] == (
        "--readiness-report hardening_suite=reports/hardening-suite.json"
    )
    assert next_actions[5]["releaseReadinessCommand"] == RAG_CANDIDATE_C1_READINESS_COMMAND
    assert "--apply-suite-file evals/regression/rag-ingestion-candidate.json" in promotion_command
    assert "--apply-dataset-name reactor-rag-ingestion-candidate" in promotion_command
    assert "--apply-dry-run" not in promotion_command
    assert (
        "--langsmith-dry-run-report-file "
        "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
    ) in promotion_command
    assert "reactor-runs promote-eval run_rag_candidate_1 --case-id case_rag_candidate_c1" in (
        promotion_command
    )
    assert (
        "--case-file evals/cases/case_rag_candidate_c1.json "
        "--run-file evals/runs/run_rag_candidate_1.json"
    ) in promotion_command
    assert (
        "reactor-agent-eval-apply --case-file evals/cases/case_rag_candidate_c1.json "
        "--run-file evals/runs/run_rag_candidate_1.json "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate "
        "--require-source-run-id --require-run-file --require-context-diagnostics "
        "--langsmith-dry-run-report-file "
        "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json "
        "--output table"
    ) == persist_command
    assert (
        "reactor-agent-eval-apply "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate "
        "--summary "
        "--langsmith-dry-run-report-file "
        "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json "
        "--feedback-review-status done "
        "--feedback-review-tag promoted "
        "--feedback-review-tag langsmith "
        "--feedback-review-tag rag "
        "--feedback-review-tag grounding "
        "--feedback-review-tag citation-failure "
        "--feedback-review-tag documents-ask "
        "--feedback-review-tag collection:rag-ingestion-candidate "
        "--feedback-review-tag rag-candidate:c1 "
        "--feedback-review-note 'Promoted to regression eval and reviewed in hardening/LangSmith. "
        "Required readiness reports: hardening_suite, langsmith_eval_sync.' "
        "--output table"
    ) == summary_command
    assert (
        "uv run reactor-langsmith-eval-sync "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate "
        "--report-file artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json "
        "--preflight-only --output table"
    ) == preflight_command
    assert next_actions[3]["remediationCommand"] == preflight_command
    assert (
        "uv run reactor-langsmith-eval-sync "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate "
        "--report-file artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json "
        "--output table"
    ) == langsmith_command
    assert next_actions[4]["remediationCommand"] == langsmith_command
    assert hardening_command == (
        "uv run reactor-hardening-suite --report-file reports/hardening-suite.json"
    )
    assert (
        "uv run reactor-replatform-readiness --output "
        "reports/release/replatform-readiness.local.json "
        "--allow-deferred-release-gates "
        "&& uv run reactor-release-smoke-plan "
        "--readiness reports/release/replatform-readiness.local.json "
        "--output reports/release/release-smoke-plan.local.json "
        "&& uv run reactor-release-smoke-run "
        "--plan reports/release/release-smoke-plan.local.json "
        "--preflight-file reports/release/release-smoke-preflight.local.json "
        "--env-file reports/release/release-smoke-preflight.local.env "
        "--report-file reports/release-smoke-run.json "
        "--evidence-output reports/release-evidence.json "
        "--verified-at $(date -u +%Y-%m-%dT%H:%M:%SZ) "
        "--latest-tag $(git describe --tags --abbrev=0) "
        "--readiness-output reports/release-readiness.json "
        "--required-readiness-report hardening_suite "
        "--required-readiness-report langsmith_eval_sync "
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report "
        "langsmith_eval_sync=artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
    ) in readiness_command
    assert candidate_review_command == (
        "reactor-admin feedback --rating thumbs_down "
        "--source api "
        "--review-status inbox "
        "--tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:c1 --limit 10 --output table"
    )
    assert candidate_export_command == (
        "reactor-admin feedback-export --rating thumbs_down "
        "--source api "
        "--review-status inbox "
        "--tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:c1 --limit 10 --output json"
    )
    assert next_actions[9]["candidateTag"] == "rag-candidate:c1"
    assert next_actions[9]["workflowTags"] == [
        "collection:rag-ingestion-candidate",
        "rag-candidate:c1",
        "expected-citation:candidate-runbook.md",
    ]
    assert next_actions[9]["feedbackTags"] == [
        "collection:rag-ingestion-candidate",
        "rag-candidate:c1",
        "expected-citation:candidate-runbook.md",
    ]
    assert candidate_bulk_review_command == (RAG_CANDIDATE_C1_API_BULK_REVIEW_ACTION)
    assert "VERIFY_TIMESTAMP" not in readiness_command
    for command in [promotion_command, review_command]:
        assert "--tag collection:rag-ingestion-candidate" in command
        assert "--tag rag-candidate:c1" in command
        assert "--tag documents-ask" in command
        assert "--tag citation-failure" in command


async def test_feedback_next_action_keeps_candidate_inspection_when_marker_missing() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "How should this candidate cite the ingested runbook?",
                "response": "It answered without a citation marker.",
                "comment": "Missing citation marker in candidate answer",
                "runId": "run_rag_candidate_1",
                "tags": [
                    "collection:rag-ingestion-candidate",
                    "rag-candidate:c1",
                    "documents-ask",
                ],
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        fetched = await client.get(f"/api/feedback/{feedback_id}", headers=ADMIN_HEADERS)

    assert fetched.status_code == 200
    next_actions = {action["id"]: action for action in fetched.json()["nextActions"]}
    assert "add-citation-marker" in next_actions
    assert "inspect-candidate-feedback" in next_actions
    assert "export-candidate-feedback" in next_actions
    assert "promote-eval" not in next_actions
    for action in next_actions.values():
        assert action["evalCaseId"] == "case_rag_candidate_c1"
        assert action["sourceRunId"] == "run_rag_candidate_1"
    assert next_actions["inspect-candidate-feedback"]["command"] == (
        "reactor-admin feedback --rating thumbs_down "
        "--source api "
        "--review-status inbox "
        "--tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:c1 --limit 10 --output table"
    )
    assert next_actions["export-candidate-feedback"]["command"] == (
        "reactor-admin feedback-export --rating thumbs_down "
        "--source api "
        "--review-status inbox "
        "--tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:c1 --limit 10 --output json"
    )


async def test_feedback_export_projects_rag_candidate_workflow_identifiers() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "How should this candidate cite the ingested runbook?",
                "response": "It answered without [candidate-runbook.md].",
                "comment": "Missing citation marker [candidate-runbook.md]",
                "runId": "run_rag_candidate_1",
                "tags": [
                    "collection:rag-ingestion-candidate",
                    "rag-candidate:c1",
                    "documents-ask",
                ],
            },
        )
        exported = await client.get(
            "/api/feedback/export",
            headers=ADMIN_HEADERS,
            params=[
                ("rating", "thumbs_down"),
                ("source", "api"),
                ("reviewStatus", "inbox"),
                ("tag", "collection:rag-ingestion-candidate"),
                ("tag", "rag-candidate:c1"),
            ],
        )

    assert submitted.status_code == 201
    assert exported.status_code == 200
    item = exported.json()["items"][0]
    assert item["workflow"] == {
        "type": "rag_ingestion_candidate",
        "candidateId": "c1",
        "collection": "rag-ingestion-candidate",
        "sourceUri": "rag-ingestion-candidate:c1",
        "evalCaseId": "case_rag_candidate_c1",
        "runId": "run_rag_candidate_1",
        "sourceRunId": "run_rag_candidate_1",
        "feedbackSource": "api",
        "feedbackTag": "rag-candidate:c1",
    }
    assert "query" not in item["workflow"]
    assert "response" not in item["workflow"]
    for action in item["nextActions"]:
        assert "recommendedVersionBump" not in action
        assert "recommendedTagPattern" not in action
        if action["id"] != "refresh-readiness":
            assert "minorBoundaryReports" not in action
    refresh_action = {action["id"]: action for action in item["nextActions"]}["refresh-readiness"]
    assert refresh_action["minorBoundaryReports"] == ["hardening_suite", "langsmith_eval_sync"]
    assert (
        refresh_action["recommendedTagSource"]
        == "release_readiness.tagRecommendation.recommendedTag"
    )


async def test_feedback_next_action_preserves_rag_candidate_tag_without_citation_signal() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "Evaluate this candidate answer",
                "response": "The answer is incomplete.",
                "comment": "Weak candidate answer",
                "runId": "run_rag_candidate_weak",
                "tags": ["collection:rag-ingestion-candidate"],
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        fetched = await client.get(f"/api/feedback/{feedback_id}", headers=ADMIN_HEADERS)

    assert fetched.status_code == 200
    next_actions = {action["id"]: action["command"] for action in fetched.json()["nextActions"]}
    promotion_command = next_actions["promote-eval"]
    review_command = next_actions["review-done"]
    assert "--apply-suite-file evals/regression/rag-ingestion-candidate.json" in promotion_command
    for command in [promotion_command, review_command]:
        assert "--tag collection:rag-ingestion-candidate" in command
        assert "--tag citation-failure" not in command
    assert "sync-langsmith" in next_actions
    assert "refresh-readiness" in next_actions


async def test_feedback_next_action_tags_rag_tool_failures_for_grounding_eval() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "How should rollback work?",
                "response": "The answer missed the runbook details.",
                "comment": "Weak answer after retrieval.",
                "runId": "run_rag_tool_weak",
                "toolsUsed": ["Rag:hybrid_search"],
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        fetched = await client.get(f"/api/feedback/{feedback_id}", headers=ADMIN_HEADERS)

    assert submitted.status_code == 201
    assert submitted.json()["tags"] == ["rag", "grounding"]
    assert fetched.status_code == 200
    next_actions = {action["id"]: action["command"] for action in fetched.json()["nextActions"]}
    promotion_command = next_actions["promote-eval"]
    review_command = next_actions["review-done"]
    for command in [promotion_command, review_command]:
        assert "--tag rag" in command
        assert "--tag grounding" in command
        assert "--tag citation-failure" not in command
        assert "--tag documents-ask" not in command
    assert "--apply-suite-file tests/fixtures/agent-eval/regression-suite.json" in promotion_command
    assert "sync-langsmith" in next_actions
    assert "refresh-readiness" in next_actions


async def test_feedback_next_action_infers_rag_candidate_collection_from_candidate_tag() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "Evaluate this candidate answer",
                "response": "The answer is incomplete.",
                "comment": "Weak candidate answer",
                "runId": "run_rag_candidate_weak",
                "tags": ["rag-candidate:c1"],
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        fetched = await client.get(f"/api/feedback/{feedback_id}", headers=ADMIN_HEADERS)

    assert fetched.status_code == 200
    next_actions = {action["id"]: action["command"] for action in fetched.json()["nextActions"]}
    promotion_command = next_actions["promote-eval"]
    review_command = next_actions["review-done"]
    assert "--apply-suite-file evals/regression/rag-ingestion-candidate.json" in promotion_command
    assert "--apply-dataset-name reactor-rag-ingestion-candidate" in promotion_command
    assert "reactor-runs promote-eval run_rag_candidate_weak --case-id case_rag_candidate_c1" in (
        promotion_command
    )
    for command in [promotion_command, review_command]:
        assert "--tag collection:rag-ingestion-candidate" in command
        assert "--tag rag-candidate:c1" in command


async def test_feedback_next_action_normalizes_candidate_eval_run_artifact_slug() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "Evaluate this candidate answer",
                "response": "The answer is incomplete.",
                "comment": "Weak candidate answer",
                "runId": "run rag candidate; retry / 1",
                "tags": ["collection:rag-ingestion-candidate", "rag-candidate:c1"],
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        fetched = await client.get(f"/api/feedback/{feedback_id}", headers=ADMIN_HEADERS)

    assert fetched.status_code == 200
    next_actions = {action["id"]: action for action in fetched.json()["nextActions"]}
    promotion = next_actions["promote-eval"]
    assert promotion["runFile"] == "evals/runs/run_rag_candidate_retry_1.json"
    assert "--run-file evals/runs/run_rag_candidate_retry_1.json" in promotion["command"]


async def test_feedback_next_action_ignores_unslugged_rag_candidate_tag() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "Evaluate this candidate answer",
                "response": "The answer is incomplete.",
                "comment": "Weak candidate answer",
                "runId": "run_rag_candidate_bad",
                "tags": ["rag-candidate:bad/path"],
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        fetched = await client.get(f"/api/feedback/{feedback_id}", headers=ADMIN_HEADERS)

    assert submitted.status_code == 201
    assert submitted.json()["tags"] == ["rag-candidate:bad/path"]
    assert fetched.status_code == 200
    next_actions = {action["id"]: action["command"] for action in fetched.json()["nextActions"]}
    promotion_command = next_actions["promote-eval"]
    review_command = next_actions["review-done"]
    assert "--apply-suite-file evals/regression/rag-ingestion-candidate.json" not in (
        promotion_command
    )
    assert "case_rag_candidate_bad_path" not in promotion_command
    assert "--tag rag-candidate:bad/path" not in review_command


async def test_feedback_next_action_preserves_memory_workflow_and_lifecycle_gate() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "Did the memory supersession policy work?",
                "response": "It reused a tombstoned memory.",
                "comment": "Memory lifecycle regression: tombstoned memory appeared again",
                "runId": "run_memory_1",
                "tags": ["memory"],
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        fetched = await client.get(f"/api/feedback/{feedback_id}", headers=ADMIN_HEADERS)

    assert fetched.status_code == 200
    next_actions = {action["id"]: action["command"] for action in fetched.json()["nextActions"]}
    action_items = {action["id"]: action for action in fetched.json()["nextActions"]}
    promotion_command = next_actions["promote-eval"]
    review_command = next_actions["review-done"]
    for command in [promotion_command, review_command]:
        assert "--tag memory" in command
    assert action_items["review-memory"]["subjectUserId"] == "user_1"
    assert next_actions["review-memory"] == (
        "reactor-memory get --target-user-id user_1 --output table; "
        "reactor-memory proposals --status proposed --subject-id user_1 --output table"
    )
    assert next_actions["verify-memory-lifecycle"] == MEMORY_LIFECYCLE_GATE_ACTION
    assert action_items["verify-memory-lifecycle"]["readinessReportArg"] == (
        "--readiness-report hardening_suite=reports/hardening-suite.json"
    )
    assert action_items["verify-memory-lifecycle"]["requiredReadinessReports"] == [
        "hardening_suite"
    ]
    assert action_items["verify-memory-lifecycle"]["readinessReports"] == {
        "hardening_suite": "reports/hardening-suite.json"
    }


async def test_feedback_next_action_detects_plain_memory_preference_language() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "What should you remember about me?",
                "response": "You said I prefer long English updates.",
                "comment": (
                    "It forgot my Korean language preference and should delete the old "
                    "answer style."
                ),
                "runId": "run_memory_preference_1",
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        fetched = await client.get(f"/api/feedback/{feedback_id}", headers=ADMIN_HEADERS)

    assert submitted.status_code == 201
    assert "memory" in submitted.json()["tags"]
    assert fetched.status_code == 200
    next_actions = {action["id"]: action["command"] for action in fetched.json()["nextActions"]}
    assert next_actions["review-memory"] == (
        "reactor-memory get --target-user-id user_1 --output table; "
        "reactor-memory proposals --status proposed --subject-id user_1 --output table"
    )
    assert next_actions["verify-memory-lifecycle"] == MEMORY_LIFECYCLE_GATE_ACTION


async def test_feedback_next_action_detects_plain_prefer_language_as_memory() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "How should you reply to me?",
                "response": "I will answer in detailed English.",
                "comment": "I said I prefer Korean updates, but it answered in English.",
                "runId": "run_memory_prefer_1",
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        fetched = await client.get(f"/api/feedback/{feedback_id}", headers=ADMIN_HEADERS)

    assert submitted.status_code == 201
    assert "memory" in submitted.json()["tags"]
    assert fetched.status_code == 200
    next_actions = {action["id"]: action["command"] for action in fetched.json()["nextActions"]}
    assert next_actions["verify-memory-lifecycle"] == MEMORY_LIFECYCLE_GATE_ACTION


async def test_feedback_next_action_detects_korean_memory_preference_language() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "내 응답 선호를 기억하고 있어?",
                "response": "영어로 자세히 답변하겠습니다.",
                "comment": "내 한국어 응답 선호를 기억하지 못했고 예전 기억은 삭제해야 해.",
                "runId": "run_memory_korean_preference_1",
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        fetched = await client.get(f"/api/feedback/{feedback_id}", headers=ADMIN_HEADERS)

    assert submitted.status_code == 201
    assert "memory" in submitted.json()["tags"]
    assert fetched.status_code == 200
    next_actions = {action["id"]: action["command"] for action in fetched.json()["nextActions"]}
    assert next_actions["review-memory"] == (
        "reactor-memory get --target-user-id user_1 --output table; "
        "reactor-memory proposals --status proposed --subject-id user_1 --output table"
    )
    assert next_actions["verify-memory-lifecycle"] == MEMORY_LIFECYCLE_GATE_ACTION


async def test_feedback_next_action_does_not_tag_generic_recall_as_memory() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "How should document answers cite sources?",
                "response": "It mentioned the runbook but did not cite it.",
                "comment": "I do not remember seeing a source marker in the answer.",
                "runId": "run_recall_citation_1",
                "tags": ["documents-ask"],
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        fetched = await client.get(f"/api/feedback/{feedback_id}", headers=ADMIN_HEADERS)

    assert submitted.status_code == 201
    assert "memory" not in submitted.json()["tags"]
    assert fetched.status_code == 200
    next_action_ids = {action["id"] for action in fetched.json()["nextActions"]}
    assert "verify-memory-lifecycle" not in next_action_ids
    assert "review-memory" not in next_action_ids


async def test_feedback_list_filters_documents_ask_citation_failures_by_workflow_tag() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "How should document answers cite sources?",
                "response": "It mentioned the runbook but did not cite it.",
                "comment": "Missing citation marker in documents ask answer",
                "runId": "run_doc_ask_1",
                "tags": ["documents-ask"],
            },
        )
        listed = await client.get(
            "/v1/feedback",
            headers=ADMIN_HEADERS,
            params={"tag": "citation-failure"},
        )
        fetched = await client.get(
            f"/api/feedback/{submitted.json()['feedbackId']}",
            headers=ADMIN_HEADERS,
        )

    assert submitted.status_code == 201
    assert submitted.json()["tags"] == [
        "documents-ask",
        "rag",
        "grounding",
        "citation-failure",
    ]
    assert listed.status_code == 200
    assert [item["feedbackId"] for item in listed.json()["items"]] == [
        submitted.json()["feedbackId"]
    ]
    assert fetched.status_code == 200
    next_actions = {action["id"]: action["command"] for action in fetched.json()["nextActions"]}
    assert "add-citation-marker" in next_actions
    assert "promote-eval" not in next_actions
    assert "persist-eval-suite" not in next_actions
    assert "sync-langsmith" not in next_actions
    assert "refresh-readiness" not in next_actions
    assert "reactor-admin feedback-review" in next_actions["add-citation-marker"]
    assert "--status inbox" in next_actions["add-citation-marker"]
    assert "--tag citation-marker-required" in next_actions["add-citation-marker"]
    assert (
        "Expected citation marker: [replace-with-source-id]" in next_actions["add-citation-marker"]
    )


async def test_feedback_citation_marker_keeps_memory_lifecycle_next_actions() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "documents-ask memory answer missed citation evidence",
                "response": "It used stale memory context without a bracketed source.",
                "comment": "memory answer still needs citation marker review",
                "runId": "run_memory_citation_1",
                "tags": ["documents-ask", "memory"],
            },
        )
        fetched = await client.get(
            f"/api/feedback/{submitted.json()['feedbackId']}",
            headers=ADMIN_HEADERS,
        )

    assert submitted.status_code == 201
    assert fetched.status_code == 200
    next_actions = {action["id"]: action for action in fetched.json()["nextActions"]}
    assert "add-citation-marker" in next_actions
    assert "promote-eval" not in next_actions
    assert next_actions["review-memory"]["command"].startswith(
        "reactor-memory get --target-user-id user_1 --output table"
    )
    assert next_actions["verify-memory-lifecycle"]["command"] == MEMORY_LIFECYCLE_GATE_ACTION


async def test_feedback_next_actions_use_review_note_citation_marker_for_eval_promotion() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "How should document answers cite sources?",
                "response": "It mentioned the runbook but did not cite it.",
                "comment": "Missing citation marker in documents ask answer",
                "runId": "run_doc_ask_1",
                "tags": ["documents-ask"],
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        updated = await client.patch(
            f"/api/feedback/{feedback_id}",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={
                "status": "inbox",
                "tags": ["citation-marker-required"],
                "note": "Expected citation marker: [runbook.md]",
            },
        )

    assert updated.status_code == 200
    action_items = {action["id"]: action for action in updated.json()["nextActions"]}
    next_actions = {action_id: action["command"] for action_id, action in action_items.items()}
    assert "add-citation-marker" not in next_actions
    assert "--expected-answer '[runbook.md]'" in next_actions["promote-eval"]
    assert action_items["sync-langsmith"]["requiredReadinessReports"] == [
        "hardening_suite",
        "langsmith_eval_sync",
    ]
    assert action_items["refresh-readiness"]["requiredReadinessReports"] == [
        "hardening_suite",
        "langsmith_eval_sync",
    ]
    assert action_items["refresh-readiness"]["readinessReports"]["hardening_suite"] == (
        "reports/hardening-suite.json"
    )
    assert "minorBoundaryReports" not in action_items["refresh-readiness"]
    assert (
        "--note 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.'"  # noqa: E501
        in action_items["review-done"]["command"]
    )


async def test_feedback_next_actions_use_expected_citation_tag_for_eval_promotion() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "How should document answers cite sources?",
                "response": "It mentioned the runbook but did not cite it.",
                "comment": "Missing citation marker in documents ask answer",
                "runId": "run_doc_ask_1",
                "tags": ["documents-ask", "expected-citation:doc_1"],
            },
        )
        fetched = await client.get(
            f"/api/feedback/{submitted.json()['feedbackId']}",
            headers=ADMIN_HEADERS,
        )

    assert fetched.status_code == 200
    next_actions = {action["id"]: action["command"] for action in fetched.json()["nextActions"]}
    assert "add-citation-marker" not in next_actions
    assert "--expected-answer '[doc_1]'" in next_actions["promote-eval"]
    assert "--tag expected-citation:doc_1" in next_actions["promote-eval"]


async def test_feedback_next_actions_preserve_chunk_expected_citation_tag() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "How should document answers cite chunk sources?",
                "response": "It mentioned the runbook but did not cite the chunk.",
                "comment": "Missing citation marker in documents ask answer",
                "runId": "run_doc_ask_chunk_1",
                "tags": ["documents-ask", "expected-citation:doc_1:0"],
            },
        )
        fetched = await client.get(
            f"/api/feedback/{submitted.json()['feedbackId']}",
            headers=ADMIN_HEADERS,
        )

    assert fetched.status_code == 200
    next_actions = {action["id"]: action["command"] for action in fetched.json()["nextActions"]}
    assert "add-citation-marker" not in next_actions
    assert "--expected-answer '[doc_1:0]'" in next_actions["promote-eval"]
    assert "--tag expected-citation:doc_1:0" in next_actions["promote-eval"]


async def test_documents_ask_expected_citation_feedback_done_requires_eval_resolution() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "How should document answers cite sources?",
                "response": "It mentioned the runbook but did not cite it.",
                "comment": "Missing citation marker in documents ask answer",
                "runId": "run_doc_ask_1",
                "tags": ["documents-ask", "expected-citation:doc_1"],
            },
        )
        premature_done = await client.patch(
            f"/api/feedback/{submitted.json()['feedbackId']}",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={"status": "done", "tags": ["triaged"], "note": "looked at it"},
        )

    assert premature_done.status_code == 400
    premature_detail = premature_done.json()["detail"]
    premature_next_actions = premature_detail.pop("nextActions")
    assert premature_detail.pop("readyNextActionIds")
    assert "review-done" in premature_detail.pop("blockedNextActionIds")
    action_states = premature_detail.pop("nextActionStates")
    assert action_states["promote-eval"] == "ready"
    assert action_states["review-done"] == "blocked"
    assert premature_detail == {
        "message": "feedback done requires eval resolution tag",
        "feedbackId": submitted.json()["feedbackId"],
        "requiredAnyReviewTag": ["deferred", "no-eval-needed", "promoted"],
        "evalCaseId": "case_run_doc_ask_1",
        "sourceRunId": "run_doc_ask_1",
        "feedbackSource": "api",
        "readinessReportArg": (
            "--readiness-report hardening_suite=reports/hardening-suite.json "
            "--readiness-report langsmith_eval_sync=reports/langsmith-eval-sync-dry-run.json"
        ),
        "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
        "readinessReports": {
            "hardening_suite": "reports/hardening-suite.json",
            "langsmith_eval_sync": "reports/langsmith-eval-sync-dry-run.json",
        },
        "releaseReadinessCommand": DOC_ASK_LANGSMITH_READINESS_COMMAND,
        "nextAction": (
            f"reactor-admin feedback --feedback-id {submitted.json()['feedbackId']} --output table"
        ),
    }
    premature_next_action_ids = {action["id"] for action in premature_next_actions}
    assert {"promote-eval", "sync-langsmith", "review-done"}.issubset(premature_next_action_ids)


async def test_feedback_next_actions_reject_placeholder_review_note_citation_marker() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "How should document answers cite sources?",
                "response": "It mentioned the runbook but did not cite it.",
                "comment": "Missing citation marker in documents ask answer",
                "runId": "run_doc_ask_1",
                "tags": ["documents-ask"],
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        updated = await client.patch(
            f"/api/feedback/{feedback_id}",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={
                "status": "inbox",
                "tags": ["citation-marker-required"],
                "note": "Expected citation marker: [replace-with-source-id]",
            },
        )

    assert updated.status_code == 200
    next_actions = {action["id"]: action["command"] for action in updated.json()["nextActions"]}
    assert "add-citation-marker" in next_actions
    assert "promote-eval" not in next_actions
    assert (
        "Expected citation marker: [replace-with-source-id]" in next_actions["add-citation-marker"]
    )


async def test_feedback_review_update_requires_admin_and_if_match_version() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    feedback = Feedback(
        feedback_id="fb_1",
        tenant_id="tenant_1",
        query="Q",
        response="A",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_1",
        user_id="user_1",
        created_at=created_at,
        updated_at=created_at,
    )
    store = FakeFeedbackStore([feedback])
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.patch(
            "/api/feedback/fb_1",
            headers={**USER_HEADERS, "If-Match": "1"},
            json={"status": "done", "tags": ["reviewed"], "note": "fixed"},
        )
        missing_match = await client.patch(
            "/api/feedback/fb_1",
            headers=ADMIN_HEADERS,
            json={"status": "done"},
        )
        updated = await client.patch(
            "/v1/feedback/fb_1",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={"status": "done", "tags": ["reviewed"], "note": "fixed"},
        )
        stale_update = await client.patch(
            "/v1/feedback/fb_1",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={"status": "inbox"},
        )
        count = await client.get("/api/feedback/unreviewed-count", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert missing_match.status_code == 400
    assert updated.status_code == 200
    assert updated.json()["reviewStatus"] == "done"
    assert updated.json()["reviewTags"] == ["reviewed"]
    assert updated.json()["reviewedBy"] == "admin_1"
    assert updated.json()["reviewNote"] == "fixed"
    assert updated.json()["nextActions"] == []
    assert updated.json()["version"] == 2
    assert stale_update.status_code == 409
    assert stale_update.json()["detail"] == {
        "message": "feedback review version conflict",
        "feedbackId": "fb_1",
        "expectedVersion": 1,
        "currentVersion": 2,
        "evalCaseId": "case_run_1",
        "sourceRunId": "run_1",
        "feedbackSource": "slack_button",
        "nextAction": "reactor-admin feedback --feedback-id fb_1 --output table",
        "reviewQueueAction": (
            "reactor-admin feedback --rating thumbs_down --source slack_button "
            "--review-status inbox --limit 10 --output table"
        ),
    }
    assert count.status_code == 200
    assert count.json() == {"count": 0}


async def test_feedback_review_stale_retry_returns_current_when_already_applied() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    feedback = Feedback(
        feedback_id="fb_1",
        tenant_id="tenant_1",
        query="Q",
        response="A",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_1",
        user_id="user_1",
        review_status="done",
        review_tags=["promoted", "langsmith"],
        review_note="Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
        reviewed_by="admin_1",
        reviewed_at=created_at,
        version=2,
        created_at=created_at,
        updated_at=created_at,
    )
    store = FakeFeedbackStore([feedback])
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.patch(
            "/v1/feedback/fb_1",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={
                "status": "done",
                "tags": ["langsmith", "promoted"],
                "note": "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
            },
        )

    assert response.status_code == 200
    assert response.json()["feedbackId"] == "fb_1"
    assert response.json()["reviewStatus"] == "done"
    assert response.json()["reviewTags"] == ["promoted", "langsmith"]
    assert response.json()["reviewNote"] == (
        "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync."  # noqa: E501
    )
    assert response.json()["version"] == 2
    assert store.records["fb_1"].version == 2


async def test_feedback_review_current_retry_does_not_increment_version() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    feedback = Feedback(
        feedback_id="fb_1",
        tenant_id="tenant_1",
        query="Q",
        response="A",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_1",
        user_id="user_1",
        review_status="done",
        review_tags=["triaged"],
        review_note="reviewed",
        reviewed_by="admin_1",
        reviewed_at=created_at,
        version=2,
        created_at=created_at,
        updated_at=created_at,
    )
    store = FakeFeedbackStore([feedback])
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.patch(
            "/v1/feedback/fb_1",
            headers={**ADMIN_HEADERS, "If-Match": "2"},
            json={
                "status": "done",
                "tags": ["triaged"],
                "note": "reviewed",
            },
        )

    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert response.json()["reviewStatus"] == "done"
    assert response.json()["reviewTags"] == ["triaged"]
    assert response.json()["reviewNote"] == "reviewed"
    assert store.records["fb_1"].version == 2


async def test_rag_candidate_feedback_done_requires_eval_resolution_tag() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    feedback = Feedback(
        feedback_id="fb_rag_candidate",
        tenant_id="tenant_1",
        query="How should this candidate cite sources?",
        response="It answered without the required citation.",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_rag_candidate_c1",
        user_id="user_1",
        source="slack_button",
        tags=["collection:rag-ingestion-candidate", "rag-candidate:c1"],
        created_at=created_at,
        updated_at=created_at,
    )
    store = FakeFeedbackStore([feedback])
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        premature_done = await client.patch(
            "/api/feedback/fb_rag_candidate",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={"status": "done", "tags": ["triaged"], "note": "looked at it"},
        )
        promoted_done = await client.patch(
            "/api/feedback/fb_rag_candidate",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={
                "status": "done",
                "tags": ["promoted", "langsmith", "rag-candidate:c1"],
                "note": "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
            },
        )

    assert premature_done.status_code == 400
    premature_detail = premature_done.json()["detail"]
    premature_next_actions = premature_detail.pop("nextActions")
    assert premature_detail.pop("readyNextActionIds")
    assert "review-done" in premature_detail.pop("blockedNextActionIds")
    action_states = premature_detail.pop("nextActionStates")
    assert action_states["promote-eval"] == "ready"
    assert action_states["review-done"] == "blocked"
    assert premature_detail == {
        "message": "feedback done requires eval resolution tag",
        "feedbackId": "fb_rag_candidate",
        "requiredAnyReviewTag": ["deferred", "no-eval-needed", "promoted"],
        "evalCaseId": "case_rag_candidate_c1",
        "sourceRunId": "run_rag_candidate_c1",
        "feedbackSource": "slack_button",
        "readinessReportArg": (
            "--readiness-report hardening_suite=reports/hardening-suite.json "
            "--readiness-report "
            "langsmith_eval_sync=artifacts/langsmith/"
            "rag-ingestion-candidate-case_rag_candidate_c1.json"
        ),
        "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
        "readinessReports": {
            "hardening_suite": "reports/hardening-suite.json",
            "langsmith_eval_sync": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
            ),
        },
        "releaseReadinessCommand": RAG_CANDIDATE_C1_READINESS_COMMAND,
        "nextAction": ("reactor-admin feedback --feedback-id fb_rag_candidate --output table"),
        "bulkReviewAction": RAG_CANDIDATE_C1_SLACK_BULK_REVIEW_ACTION,
    }
    premature_next_actions_by_id = {action["id"]: action for action in premature_next_actions}
    assert "promote-eval" in premature_next_actions_by_id
    assert "sync-langsmith" in premature_next_actions_by_id
    assert "bulk-review-candidate-feedback" in premature_next_actions_by_id
    assert "review-done" in premature_next_actions_by_id
    assert (
        premature_next_actions_by_id["bulk-review-candidate-feedback"]["command"]
        == RAG_CANDIDATE_C1_SLACK_BULK_REVIEW_ACTION
    )
    assert promoted_done.status_code == 200
    assert promoted_done.json()["reviewStatus"] == "done"
    assert promoted_done.json()["reviewTags"] == ["promoted", "langsmith", "rag-candidate:c1"]


async def test_rag_candidate_feedback_version_conflict_preserves_handoff_metadata() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    feedback = Feedback(
        feedback_id="fb_rag_candidate",
        tenant_id="tenant_1",
        query="How should this candidate cite sources?",
        response="It answered without the required citation.",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_rag_candidate_c1",
        user_id="user_1",
        source="slack_button",
        tags=["collection:rag-ingestion-candidate", "rag-candidate:c1"],
        version=2,
        created_at=created_at,
        updated_at=created_at,
    )
    store = FakeFeedbackStore([feedback])
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        stale_update = await client.patch(
            "/api/feedback/fb_rag_candidate",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={"status": "inbox", "tags": ["citation-marker-required"]},
        )

    assert stale_update.status_code == 409
    detail = stale_update.json()["detail"]
    next_actions = {action["id"]: action for action in detail.pop("nextActions")}
    assert detail.pop("readyNextActionIds")
    assert "review-done" in detail.pop("blockedNextActionIds")
    action_states = detail.pop("nextActionStates")
    assert action_states["promote-eval"] == "ready"
    assert action_states["review-done"] == "blocked"
    assert detail == {
        "message": "feedback review version conflict",
        "feedbackId": "fb_rag_candidate",
        "expectedVersion": 1,
        "currentVersion": 2,
        "evalCaseId": "case_rag_candidate_c1",
        "sourceRunId": "run_rag_candidate_c1",
        "feedbackSource": "slack_button",
        "nextAction": "reactor-admin feedback --feedback-id fb_rag_candidate --output table",
        "bulkReviewAction": RAG_CANDIDATE_C1_SLACK_BULK_REVIEW_ACTION,
        "readinessReportArg": (
            "--readiness-report hardening_suite=reports/hardening-suite.json "
            "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
            "rag-ingestion-candidate-case_rag_candidate_c1.json"
        ),
        "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
        "readinessReports": {
            "hardening_suite": "reports/hardening-suite.json",
            "langsmith_eval_sync": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
            ),
        },
        "releaseReadinessCommand": RAG_CANDIDATE_C1_READINESS_COMMAND,
        "reviewQueueAction": (
            "reactor-admin feedback --rating thumbs_down --source slack_button "
            "--review-status inbox --tag rag --tag grounding --tag citation-failure "
            "--tag collection:rag-ingestion-candidate "
            "--tag rag-candidate:c1 --limit 10 --output table"
        ),
    }
    assert next_actions["preflight-langsmith"]["feedbackId"] == "fb_rag_candidate"
    assert next_actions["preflight-langsmith"]["readinessReportArg"] == (
        "--readiness-report hardening_suite=reports/hardening-suite.json "
        "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
        "rag-ingestion-candidate-case_rag_candidate_c1.json"
    )
    assert next_actions["refresh-readiness"]["minorBoundaryReports"] == [
        "hardening_suite",
        "langsmith_eval_sync",
    ]
    assert (
        "reactor-admin feedback-review fb_rag_candidate" in next_actions["review-done"]["command"]
    )


async def test_rag_candidate_promoted_feedback_requires_langsmith_resolution_tag() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    feedback = Feedback(
        feedback_id="fb_rag_candidate",
        tenant_id="tenant_1",
        query="How should this candidate cite sources?",
        response="It answered without the required citation.",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_rag_candidate_c1",
        user_id="user_1",
        source="slack_button",
        tags=["collection:rag-ingestion-candidate", "rag-candidate:c1"],
        created_at=created_at,
        updated_at=created_at,
    )
    store = FakeFeedbackStore([feedback])
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        missing_langsmith = await client.patch(
            "/api/feedback/fb_rag_candidate",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={"status": "done", "tags": ["promoted"]},
        )
        weak_note = await client.patch(
            "/api/feedback/fb_rag_candidate",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={
                "status": "done",
                "tags": ["promoted", "langsmith"],
                "note": "Promoted to regression eval and LangSmith readiness.",
            },
        )
        missing_note = await client.patch(
            "/api/feedback/fb_rag_candidate",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={
                "status": "done",
                "tags": ["promoted", "langsmith"],
            },
        )
        noncanonical_note = await client.patch(
            "/api/feedback/fb_rag_candidate",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={
                "status": "done",
                "tags": ["promoted", "langsmith"],
                "note": "Reviewed hardening_suite and langsmith_eval_sync evidence.",
            },
        )
        with_langsmith = await client.patch(
            "/api/feedback/fb_rag_candidate",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={
                "status": "done",
                "tags": ["promoted", "langsmith"],
                "note": "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
            },
        )

    assert missing_langsmith.status_code == 400
    missing_langsmith_detail = missing_langsmith.json()["detail"]
    missing_langsmith_next_actions = missing_langsmith_detail.pop("nextActions")
    assert missing_langsmith_detail.pop("readyNextActionIds")
    assert "review-done" in missing_langsmith_detail.pop("blockedNextActionIds")
    action_states = missing_langsmith_detail.pop("nextActionStates")
    assert action_states["promote-eval"] == "ready"
    assert action_states["review-done"] == "blocked"
    assert missing_langsmith_detail == {
        "message": "promoted feedback requires LangSmith resolution tag",
        "feedbackId": "fb_rag_candidate",
        "requiredAllReviewTags": ["promoted", "langsmith"],
        "evalCaseId": "case_rag_candidate_c1",
        "sourceRunId": "run_rag_candidate_c1",
        "feedbackSource": "slack_button",
        "readinessReportArg": (
            "--readiness-report hardening_suite=reports/hardening-suite.json "
            "--readiness-report "
            "langsmith_eval_sync=artifacts/langsmith/"
            "rag-ingestion-candidate-case_rag_candidate_c1.json"
        ),
        "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
        "readinessReports": {
            "hardening_suite": "reports/hardening-suite.json",
            "langsmith_eval_sync": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
            ),
        },
        "releaseReadinessCommand": RAG_CANDIDATE_C1_READINESS_COMMAND,
        "nextAction": "reactor-admin feedback --feedback-id fb_rag_candidate --output table",
        "bulkReviewAction": RAG_CANDIDATE_C1_SLACK_BULK_REVIEW_ACTION,
    }
    missing_langsmith_next_actions_by_id = {
        action["id"]: action for action in missing_langsmith_next_actions
    }
    assert "sync-langsmith" in missing_langsmith_next_actions_by_id
    assert "review-done" in missing_langsmith_next_actions_by_id
    assert (
        missing_langsmith_next_actions_by_id["bulk-review-candidate-feedback"]["command"]
        == RAG_CANDIDATE_C1_SLACK_BULK_REVIEW_ACTION
    )
    assert (
        missing_langsmith_next_actions_by_id["bulk-review-candidate-feedback"]["requiredReviewNote"]
        == RAG_CANDIDATE_REQUIRED_REVIEW_NOTE
    )
    assert (
        f"--note '{RAG_CANDIDATE_REQUIRED_REVIEW_NOTE}'"
        in missing_langsmith_next_actions_by_id["bulk-review-candidate-feedback"]["command"]
    )
    assert weak_note.status_code == 400
    weak_note_detail = weak_note.json()["detail"]
    assert weak_note_detail.pop("readyNextActionIds")
    assert "review-done" in weak_note_detail.pop("blockedNextActionIds")
    assert weak_note_detail.pop("nextActionStates")["review-done"] == "blocked"
    assert weak_note_detail.pop("nextActions")
    assert weak_note_detail == {
        "message": "promoted feedback requires readiness report note",
        "feedbackId": "fb_rag_candidate",
        "requiredReviewNote": (
            "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync."  # noqa: E501
        ),
        "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
        "evalCaseId": "case_rag_candidate_c1",
        "sourceRunId": "run_rag_candidate_c1",
        "feedbackSource": "slack_button",
        "readinessReportArg": (
            "--readiness-report hardening_suite=reports/hardening-suite.json "
            "--readiness-report "
            "langsmith_eval_sync=artifacts/langsmith/"
            "rag-ingestion-candidate-case_rag_candidate_c1.json"
        ),
        "readinessReports": {
            "hardening_suite": "reports/hardening-suite.json",
            "langsmith_eval_sync": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
            ),
        },
        "releaseReadinessCommand": RAG_CANDIDATE_C1_READINESS_COMMAND,
        "nextAction": "reactor-admin feedback --feedback-id fb_rag_candidate --output table",
        "bulkReviewAction": RAG_CANDIDATE_C1_SLACK_BULK_REVIEW_ACTION,
    }
    assert missing_note.status_code == 400
    missing_note_detail = missing_note.json()["detail"]
    assert missing_note_detail["message"] == "feedback eval resolution note is required"
    assert missing_note_detail["requiredReviewNote"] == (
        "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync."  # noqa: E501
    )
    assert noncanonical_note.status_code == 400
    assert with_langsmith.status_code == 200
    assert with_langsmith.json()["reviewStatus"] == "done"
    assert with_langsmith.json()["reviewTags"] == ["promoted", "langsmith"]
    assert with_langsmith.json()["reviewNote"] == (
        "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync."  # noqa: E501
    )


async def test_rag_candidate_feedback_no_eval_resolution_requires_review_note() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    feedback = Feedback(
        feedback_id="fb_rag_candidate",
        tenant_id="tenant_1",
        query="How should this candidate cite sources?",
        response="It answered without the required citation.",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_rag_candidate_c1",
        user_id="user_1",
        source="slack_button",
        tags=["collection:rag-ingestion-candidate", "rag-candidate:c1"],
        created_at=created_at,
        updated_at=created_at,
    )
    store = FakeFeedbackStore([feedback])
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        missing_note = await client.patch(
            "/api/feedback/fb_rag_candidate",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={"status": "done", "tags": ["no-eval-needed"]},
        )
        with_note = await client.patch(
            "/api/feedback/fb_rag_candidate",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={
                "status": "done",
                "tags": ["no-eval-needed"],
                "note": "Duplicate of case_rag_candidate_c1 already covered by regression.",
            },
        )

    assert missing_note.status_code == 400
    assert missing_note.json()["detail"] == {
        "message": "feedback eval resolution note is required",
        "feedbackId": "fb_rag_candidate",
        "resolutionTagsRequiringNote": ["deferred", "no-eval-needed", "promoted"],
        "evalCaseId": "case_rag_candidate_c1",
        "sourceRunId": "run_rag_candidate_c1",
        "feedbackSource": "slack_button",
        "readinessReportArg": (
            "--readiness-report hardening_suite=reports/hardening-suite.json "
            "--readiness-report "
            "langsmith_eval_sync=artifacts/langsmith/"
            "rag-ingestion-candidate-case_rag_candidate_c1.json"
        ),
        "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
        "readinessReports": {
            "hardening_suite": "reports/hardening-suite.json",
            "langsmith_eval_sync": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
            ),
        },
        "releaseReadinessCommand": RAG_CANDIDATE_C1_READINESS_COMMAND,
        "nextAction": "reactor-admin feedback --feedback-id fb_rag_candidate --output table",
        "bulkReviewAction": RAG_CANDIDATE_C1_SLACK_BULK_REVIEW_ACTION,
    }
    assert with_note.status_code == 200
    assert with_note.json()["reviewStatus"] == "done"
    assert with_note.json()["reviewTags"] == ["no-eval-needed"]
    assert with_note.json()["reviewNote"] == (
        "Duplicate of case_rag_candidate_c1 already covered by regression."
    )


async def test_bulk_feedback_done_does_not_bypass_rag_candidate_eval_resolution() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    feedback_action = "reactor-admin feedback --feedback-id fb_rag_candidate --output table"
    records = [
        Feedback(
            feedback_id="fb_rag_candidate",
            tenant_id="tenant_1",
            query="How should this candidate cite sources?",
            response="It answered without the required citation.",
            rating=FeedbackRating.THUMBS_DOWN,
            session_id="session_1",
            run_id="run_rag_candidate_c1",
            user_id="user_1",
            source="slack_button",
            tags=["collection:rag-ingestion-candidate", "rag-candidate:c1"],
            created_at=created_at,
            updated_at=created_at,
        ),
        Feedback(
            feedback_id="fb_generic",
            tenant_id="tenant_1",
            query="Generic bad answer",
            response="Weak but not tied to RAG candidate ingestion.",
            rating=FeedbackRating.THUMBS_DOWN,
            session_id="session_2",
            run_id="run_generic",
            user_id="user_1",
            source="slack_button",
            created_at=created_at,
            updated_at=created_at,
        ),
    ]
    store = FakeFeedbackStore(records)
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/feedback/bulk-update",
            headers=ADMIN_HEADERS,
            json={
                "ids": ["fb_rag_candidate", "fb_generic"],
                "status": "done",
                "tags": ["triaged"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    [failure] = payload["failed"]
    next_actions = failure.pop("nextActions")
    ready_action_ids = failure.pop("readyNextActionIds")
    blocked_action_ids = failure.pop("blockedNextActionIds")
    action_states = failure.pop("nextActionStates")
    assert payload == {
        "updated": ["fb_generic"],
        "failed": [
            {
                "id": "fb_rag_candidate",
                "reason": "eval_resolution_required",
                "evalCaseId": "case_rag_candidate_c1",
                "sourceRunId": "run_rag_candidate_c1",
                "feedbackSource": "slack_button",
                "requiredReviewNote": (
                    "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync."  # noqa: E501
                ),
                "nextAction": feedback_action,
                "bulkReviewAction": RAG_CANDIDATE_C1_SLACK_BULK_REVIEW_ACTION,
                "readinessReportArg": (
                    "--readiness-report hardening_suite=reports/hardening-suite.json "
                    "--readiness-report "
                    "langsmith_eval_sync=artifacts/langsmith/"
                    "rag-ingestion-candidate-case_rag_candidate_c1.json"
                ),
                "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                "requiredEnvAnyOf": [
                    ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                ],
                "recommendedEnv": ["LANGSMITH_ENDPOINT"],
                "readinessReports": {
                    "hardening_suite": "reports/hardening-suite.json",
                    "langsmith_eval_sync": (
                        "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                    ),
                },
                "releaseReadinessCommand": RAG_CANDIDATE_C1_READINESS_COMMAND,
            }
        ],
    }
    assert "promote-eval" in ready_action_ids
    assert "bulk-review-candidate-feedback" not in ready_action_ids
    assert "bulk-review-candidate-feedback" in blocked_action_ids
    assert action_states["promote-eval"] == "ready"
    assert action_states["bulk-review-candidate-feedback"] == "blocked"
    next_actions_by_id = {action["id"]: action for action in next_actions}
    assert set(next_actions_by_id) >= {"promote-eval", "bulk-review-candidate-feedback"}
    assert next_actions_by_id["promote-eval"]["feedbackId"] == "fb_rag_candidate"
    assert next_actions_by_id["promote-eval"]["evalCaseId"] == "case_rag_candidate_c1"
    assert next_actions_by_id["promote-eval"]["sourceRunId"] == "run_rag_candidate_c1"
    assert next_actions_by_id["promote-eval"]["feedbackSource"] == "slack_button"
    assert next_actions_by_id["promote-eval"]["command"].startswith(
        "reactor-runs promote-eval run_rag_candidate_c1 "
    )
    promote_eval_command = next_actions_by_id["promote-eval"]["command"]
    assert "--feedback-review-status done" in promote_eval_command
    assert "--feedback-review-tag promoted" in promote_eval_command
    assert "--feedback-review-tag langsmith" in promote_eval_command
    assert "--feedback-review-tag rag-candidate:c1" in promote_eval_command
    assert (
        "--feedback-review-note 'Promoted to regression eval and reviewed in hardening/LangSmith. "
        "Required readiness reports: hardening_suite, langsmith_eval_sync.'" in promote_eval_command
    )
    summarize_command = next_actions_by_id["summarize-langsmith"]["command"]
    assert "--feedback-review-status done" in summarize_command
    assert "--feedback-review-tag promoted" in summarize_command
    assert "--feedback-review-tag langsmith" in summarize_command
    assert "--feedback-review-tag rag-candidate:c1" in summarize_command
    assert (
        "--feedback-review-note 'Promoted to regression eval and reviewed in hardening/LangSmith. "
        "Required readiness reports: hardening_suite, langsmith_eval_sync.'" in summarize_command
    )
    assert (
        next_actions_by_id["bulk-review-candidate-feedback"]["command"]
        == RAG_CANDIDATE_C1_SLACK_BULK_REVIEW_ACTION
    )
    assert store.records["fb_rag_candidate"].review_status == "inbox"
    assert store.records["fb_generic"].review_status == "done"


async def test_bulk_feedback_done_rejects_no_eval_resolution_without_note() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    feedback_action = "reactor-admin feedback --feedback-id fb_rag_candidate --output table"
    feedback = Feedback(
        feedback_id="fb_rag_candidate",
        tenant_id="tenant_1",
        query="How should this candidate cite sources?",
        response="It answered without the required citation.",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_rag_candidate_c1",
        user_id="user_1",
        source="slack_button",
        tags=["collection:rag-ingestion-candidate", "rag-candidate:c1"],
        created_at=created_at,
        updated_at=created_at,
    )
    store = FakeFeedbackStore([feedback])
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/feedback/bulk-update",
            headers=ADMIN_HEADERS,
            json={
                "ids": ["fb_rag_candidate"],
                "status": "done",
                "tags": ["no-eval-needed"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    [failure] = payload["failed"]
    assert failure.pop("nextActions")
    assert failure.pop("readyNextActionIds")
    assert failure.pop("blockedNextActionIds")
    assert failure.pop("nextActionStates")["promote-eval"] == "ready"
    assert payload == {
        "updated": [],
        "failed": [
            {
                "id": "fb_rag_candidate",
                "reason": "eval_resolution_note_required",
                "evalCaseId": "case_rag_candidate_c1",
                "sourceRunId": "run_rag_candidate_c1",
                "feedbackSource": "slack_button",
                "requiredReviewNote": (
                    "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync."  # noqa: E501
                ),
                "nextAction": feedback_action,
                "bulkReviewAction": RAG_CANDIDATE_C1_SLACK_BULK_REVIEW_ACTION,
                "readinessReportArg": (
                    "--readiness-report hardening_suite=reports/hardening-suite.json "
                    "--readiness-report "
                    "langsmith_eval_sync=artifacts/langsmith/"
                    "rag-ingestion-candidate-case_rag_candidate_c1.json"
                ),
                "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                "requiredEnvAnyOf": [
                    ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                ],
                "recommendedEnv": ["LANGSMITH_ENDPOINT"],
                "readinessReports": {
                    "hardening_suite": "reports/hardening-suite.json",
                    "langsmith_eval_sync": (
                        "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                    ),
                },
                "releaseReadinessCommand": RAG_CANDIDATE_C1_READINESS_COMMAND,
            }
        ],
    }
    assert store.records["fb_rag_candidate"].review_status == "inbox"


async def test_bulk_feedback_done_rejects_promoted_without_langsmith_resolution() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    feedback_action = "reactor-admin feedback --feedback-id fb_rag_candidate --output table"
    feedback = Feedback(
        feedback_id="fb_rag_candidate",
        tenant_id="tenant_1",
        query="How should this candidate cite sources?",
        response="It answered without the required citation.",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_rag_candidate_c1",
        user_id="user_1",
        source="slack_button",
        tags=["collection:rag-ingestion-candidate", "rag-candidate:c1"],
        created_at=created_at,
        updated_at=created_at,
    )
    store = FakeFeedbackStore([feedback])
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/feedback/bulk-update",
            headers=ADMIN_HEADERS,
            json={
                "ids": ["fb_rag_candidate"],
                "status": "done",
                "tags": ["promoted"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    [failure] = payload["failed"]
    assert failure.pop("nextActions")
    assert failure.pop("readyNextActionIds")
    assert failure.pop("blockedNextActionIds")
    assert failure.pop("nextActionStates")["promote-eval"] == "ready"
    assert payload == {
        "updated": [],
        "failed": [
            {
                "id": "fb_rag_candidate",
                "reason": "langsmith_resolution_required",
                "evalCaseId": "case_rag_candidate_c1",
                "sourceRunId": "run_rag_candidate_c1",
                "feedbackSource": "slack_button",
                "requiredReviewNote": (
                    "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync."  # noqa: E501
                ),
                "nextAction": feedback_action,
                "bulkReviewAction": RAG_CANDIDATE_C1_SLACK_BULK_REVIEW_ACTION,
                "readinessReportArg": (
                    "--readiness-report hardening_suite=reports/hardening-suite.json "
                    "--readiness-report "
                    "langsmith_eval_sync=artifacts/langsmith/"
                    "rag-ingestion-candidate-case_rag_candidate_c1.json"
                ),
                "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                "requiredEnvAnyOf": [
                    ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                ],
                "recommendedEnv": ["LANGSMITH_ENDPOINT"],
                "readinessReports": {
                    "hardening_suite": "reports/hardening-suite.json",
                    "langsmith_eval_sync": (
                        "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                    ),
                },
                "releaseReadinessCommand": RAG_CANDIDATE_C1_READINESS_COMMAND,
            }
        ],
    }
    assert store.records["fb_rag_candidate"].review_status == "inbox"


async def test_bulk_feedback_done_rejects_langsmith_resolution_without_review_note() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    feedback_action = "reactor-admin feedback --feedback-id fb_rag_candidate --output table"
    feedback = Feedback(
        feedback_id="fb_rag_candidate",
        tenant_id="tenant_1",
        query="How should this candidate cite sources?",
        response="It answered without the required citation.",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_rag_candidate_c1",
        user_id="user_1",
        source="slack_button",
        tags=["collection:rag-ingestion-candidate", "rag-candidate:c1"],
        created_at=created_at,
        updated_at=created_at,
    )
    store = FakeFeedbackStore([feedback])
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/feedback/bulk-update",
            headers=ADMIN_HEADERS,
            json={
                "ids": ["fb_rag_candidate"],
                "status": "done",
                "tags": ["promoted", "langsmith"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    [failure] = payload["failed"]
    assert failure.pop("nextActions")
    assert failure.pop("readyNextActionIds")
    assert failure.pop("blockedNextActionIds")
    assert failure.pop("nextActionStates")["promote-eval"] == "ready"
    assert payload == {
        "updated": [],
        "failed": [
            {
                "id": "fb_rag_candidate",
                "reason": "eval_resolution_note_required",
                "evalCaseId": "case_rag_candidate_c1",
                "sourceRunId": "run_rag_candidate_c1",
                "feedbackSource": "slack_button",
                "requiredReviewNote": (
                    "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync."  # noqa: E501
                ),
                "nextAction": feedback_action,
                "bulkReviewAction": RAG_CANDIDATE_C1_SLACK_BULK_REVIEW_ACTION,
                "readinessReportArg": (
                    "--readiness-report hardening_suite=reports/hardening-suite.json "
                    "--readiness-report "
                    "langsmith_eval_sync=artifacts/langsmith/"
                    "rag-ingestion-candidate-case_rag_candidate_c1.json"
                ),
                "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                "requiredEnvAnyOf": [
                    ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                ],
                "recommendedEnv": ["LANGSMITH_ENDPOINT"],
                "readinessReports": {
                    "hardening_suite": "reports/hardening-suite.json",
                    "langsmith_eval_sync": (
                        "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                    ),
                },
                "releaseReadinessCommand": RAG_CANDIDATE_C1_READINESS_COMMAND,
            }
        ],
    }
    assert store.records["fb_rag_candidate"].review_status == "inbox"


async def test_bulk_feedback_done_preserves_review_note_for_langsmith_resolution() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    feedback = Feedback(
        feedback_id="fb_rag_candidate",
        tenant_id="tenant_1",
        query="How should this candidate cite sources?",
        response="It answered without the required citation.",
        rating=FeedbackRating.THUMBS_DOWN,
        session_id="session_1",
        run_id="run_rag_candidate_c1",
        user_id="user_1",
        source="slack_button",
        tags=["collection:rag-ingestion-candidate", "rag-candidate:c1"],
        created_at=created_at,
        updated_at=created_at,
    )
    store = FakeFeedbackStore([feedback])
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/feedback/bulk-update",
            headers=ADMIN_HEADERS,
            json={
                "ids": ["fb_rag_candidate"],
                "status": "done",
                "tags": ["promoted", "langsmith"],
                "note": "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "updated": ["fb_rag_candidate"],
        "updatedDetails": [
            {
                "feedbackId": "fb_rag_candidate",
                "evalCaseId": "case_rag_candidate_c1",
                "sourceRunId": "run_rag_candidate_c1",
                "feedbackSource": "slack_button",
                "reviewTags": ["promoted", "langsmith"],
                "reviewNote": (
                    "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync."  # noqa: E501
                ),
                "nextAction": RAG_CANDIDATE_C1_READINESS_COMMAND,
                "bulkReviewAction": RAG_CANDIDATE_C1_SLACK_BULK_REVIEW_ACTION,
                "readinessReportArg": (
                    "--readiness-report hardening_suite=reports/hardening-suite.json "
                    "--readiness-report "
                    "langsmith_eval_sync=artifacts/langsmith/"
                    "rag-ingestion-candidate-case_rag_candidate_c1.json"
                ),
                "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                "readinessReports": {
                    "hardening_suite": "reports/hardening-suite.json",
                    "langsmith_eval_sync": (
                        "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
                    ),
                },
                "requiredEnvAnyOf": [
                    ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                ],
                "recommendedEnv": ["LANGSMITH_ENDPOINT"],
                "releaseReadinessCommand": RAG_CANDIDATE_C1_READINESS_COMMAND,
            }
        ],
        "failed": [],
    }
    assert "How should this candidate cite sources?" not in response.text
    assert "It answered without the required citation." not in response.text
    assert store.records["fb_rag_candidate"].review_status == "done"
    assert store.records["fb_rag_candidate"].review_tags == ["promoted", "langsmith"]
    assert store.records["fb_rag_candidate"].review_note == (
        "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync."  # noqa: E501
    )


async def test_bulk_feedback_update_skips_already_matching_review_state() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    records = [
        Feedback(
            feedback_id="fb_done",
            tenant_id="tenant_1",
            query="Already triaged",
            response="Already reviewed",
            rating=FeedbackRating.THUMBS_DOWN,
            session_id="session_1",
            run_id="run_done",
            user_id="user_1",
            source="slack_button",
            review_status="done",
            review_tags=["triaged"],
            reviewed_by="operator_1",
            reviewed_at=created_at,
            version=3,
            created_at=created_at,
            updated_at=created_at,
        ),
        Feedback(
            feedback_id="fb_open",
            tenant_id="tenant_1",
            query="Needs triage",
            response="Needs review",
            rating=FeedbackRating.THUMBS_UP,
            session_id="session_2",
            user_id="user_1",
            source="slack_button",
            created_at=created_at,
            updated_at=created_at,
        ),
    ]
    store = FakeFeedbackStore(records)
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/feedback/bulk-update",
            headers=ADMIN_HEADERS,
            json={
                "ids": ["fb_done", "fb_open"],
                "status": "done",
                "tags": ["triaged"],
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "updated": ["fb_open"],
        "alreadyDone": ["fb_done"],
        "failed": [],
    }
    assert store.records["fb_done"].version == 3
    assert store.records["fb_done"].review_status == "done"
    assert store.records["fb_done"].review_tags == ["triaged"]
    assert store.records["fb_open"].version == 2
    assert store.records["fb_open"].review_status == "done"
    assert store.records["fb_open"].review_tags == ["triaged"]


async def test_bulk_feedback_update_treats_review_tags_as_idempotent_set() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    feedback = Feedback(
        feedback_id="fb_done",
        tenant_id="tenant_1",
        query="Already promoted",
        response="Already reviewed",
        rating=FeedbackRating.THUMBS_UP,
        session_id="session_1",
        user_id="user_1",
        source="slack_button",
        review_status="done",
        review_tags=["promoted", "langsmith"],
        review_note="Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
        version=3,
        created_at=created_at,
        updated_at=created_at,
    )
    store = FakeFeedbackStore([feedback])
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/feedback/bulk-update",
            headers=ADMIN_HEADERS,
            json={
                "ids": ["fb_done"],
                "status": "done",
                "tags": ["langsmith", "promoted"],
                "note": "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "updated": [],
        "alreadyDone": ["fb_done"],
        "failed": [],
    }
    assert store.records["fb_done"].version == 3
    assert store.records["fb_done"].review_tags == ["promoted", "langsmith"]


async def test_bulk_feedback_update_treats_review_tag_superset_as_done() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    feedback = Feedback(
        feedback_id="fb_done",
        tenant_id="tenant_1",
        query="Already promoted",
        response="Already reviewed",
        rating=FeedbackRating.THUMBS_UP,
        session_id="session_1",
        user_id="user_1",
        source="slack_button",
        review_status="done",
        review_tags=[
            "promoted",
            "langsmith",
            "collection:rag-ingestion-candidate",
            "rag-candidate:c1",
            "operator-reviewed",
        ],
        review_note="Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
        version=3,
        created_at=created_at,
        updated_at=created_at,
    )
    store = FakeFeedbackStore([feedback])
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/feedback/bulk-update",
            headers=ADMIN_HEADERS,
            json={
                "ids": ["fb_done"],
                "status": "done",
                "tags": [
                    "promoted",
                    "langsmith",
                    "collection:rag-ingestion-candidate",
                    "rag-candidate:c1",
                ],
                "note": "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "updated": [],
        "alreadyDone": ["fb_done"],
        "failed": [],
    }
    assert store.records["fb_done"].version == 3
    assert store.records["fb_done"].review_tags == [
        "promoted",
        "langsmith",
        "collection:rag-ingestion-candidate",
        "rag-candidate:c1",
        "operator-reviewed",
    ]


async def test_unresolved_rag_candidate_feedback_cannot_be_deleted_before_eval_resolution() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    records = [
        Feedback(
            feedback_id="fb_unresolved",
            tenant_id="tenant_1",
            query="How should this candidate cite sources?",
            response="It answered without the required citation.",
            rating=FeedbackRating.THUMBS_DOWN,
            session_id="session_1",
            run_id="run_rag_candidate_c1",
            user_id="user_1",
            source="slack_button",
            tags=["collection:rag-ingestion-candidate", "rag-candidate:c1"],
            created_at=created_at,
            updated_at=created_at,
        ),
        Feedback(
            feedback_id="fb_resolved",
            tenant_id="tenant_1",
            query="Resolved candidate feedback",
            response="Already promoted.",
            rating=FeedbackRating.THUMBS_DOWN,
            session_id="session_2",
            run_id="run_rag_candidate_c2",
            user_id="user_1",
            source="slack_button",
            tags=["collection:rag-ingestion-candidate", "rag-candidate:c2"],
            review_status="done",
            review_tags=["promoted", "langsmith"],
            review_note="Promoted to regression eval.",
            created_at=created_at,
            updated_at=created_at,
        ),
    ]
    store = FakeFeedbackStore(records)
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        unresolved_delete = await client.delete(
            "/api/feedback/fb_unresolved",
            headers=ADMIN_HEADERS,
        )
        resolved_delete = await client.delete(
            "/api/feedback/fb_resolved",
            headers=ADMIN_HEADERS,
        )

    assert unresolved_delete.status_code == 409
    unresolved_delete_detail = unresolved_delete.json()["detail"]
    unresolved_delete_next_actions = unresolved_delete_detail.pop("nextActions")
    assert unresolved_delete_detail.pop("readyNextActionIds")
    assert "review-done" in unresolved_delete_detail.pop("blockedNextActionIds")
    action_states = unresolved_delete_detail.pop("nextActionStates")
    assert action_states["promote-eval"] == "ready"
    assert action_states["review-done"] == "blocked"
    assert unresolved_delete_detail == {
        "message": "feedback delete requires eval resolution first",
        "feedbackId": "fb_unresolved",
        "evalCaseId": "case_rag_candidate_c1",
        "sourceRunId": "run_rag_candidate_c1",
        "feedbackSource": "slack_button",
        "readinessReportArg": (
            "--readiness-report hardening_suite=reports/hardening-suite.json "
            "--readiness-report "
            "langsmith_eval_sync=artifacts/langsmith/"
            "rag-ingestion-candidate-case_rag_candidate_c1.json"
        ),
        "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
        "readinessReports": {
            "hardening_suite": "reports/hardening-suite.json",
            "langsmith_eval_sync": (
                "artifacts/langsmith/rag-ingestion-candidate-case_rag_candidate_c1.json"
            ),
        },
        "releaseReadinessCommand": RAG_CANDIDATE_C1_READINESS_COMMAND,
        "nextAction": "reactor-admin feedback --feedback-id fb_unresolved --output table",
        "bulkReviewAction": RAG_CANDIDATE_C1_SLACK_BULK_REVIEW_ACTION,
    }
    unresolved_delete_next_actions_by_id = {
        action["id"]: action for action in unresolved_delete_next_actions
    }
    assert "promote-eval" in unresolved_delete_next_actions_by_id
    assert "review-done" in unresolved_delete_next_actions_by_id
    assert (
        unresolved_delete_next_actions_by_id["bulk-review-candidate-feedback"]["command"]
        == RAG_CANDIDATE_C1_SLACK_BULK_REVIEW_ACTION
    )
    assert "fb_unresolved" in store.records
    assert resolved_delete.status_code == 204
    assert "fb_resolved" not in store.records


async def test_feedback_list_filters_by_feedback_or_review_tag() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        rag_feedback = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "VectorStore rollback 절차 알려줘",
                "response": "출처 없이 답했어요",
                "runId": "run_rag_1",
                "tags": ["rag"],
            },
        )
        generic_feedback = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "일반 질문",
                "response": "일반 답변",
                "runId": "run_generic_1",
            },
        )
        await client.patch(
            f"/api/feedback/{rag_feedback.json()['feedbackId']}",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={"status": "done", "tags": ["citation-failure"]},
        )
        filtered = await client.get(
            "/api/feedback",
            headers=ADMIN_HEADERS,
            params={"tag": "citation-failure"},
        )

    assert generic_feedback.status_code == 201
    assert filtered.status_code == 200
    assert filtered.json()["approximateTotal"] == 1
    assert filtered.json()["items"][0]["feedbackId"] == rag_feedback.json()["feedbackId"]


async def test_feedback_list_and_export_filter_by_review_status() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        inbox_feedback = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "Needs review",
                "response": "Weak answer",
                "runId": "run_inbox",
                "source": "admin_cli",
            },
        )
        done_feedback = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "Already handled",
                "response": "Weak answer",
                "runId": "run_done",
                "source": "admin_cli",
            },
        )
        await client.patch(
            f"/api/feedback/{done_feedback.json()['feedbackId']}",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={"status": "done", "tags": ["promoted"]},
        )
        listed = await client.get(
            "/api/feedback",
            headers=ADMIN_HEADERS,
            params={"rating": "thumbs_down", "reviewStatus": "inbox"},
        )
        exported = await client.get(
            "/api/feedback/export",
            headers=ADMIN_HEADERS,
            params={"rating": "thumbs_down", "reviewStatus": "inbox"},
        )

    assert listed.status_code == 200
    assert [item["feedbackId"] for item in listed.json()["items"]] == [
        inbox_feedback.json()["feedbackId"]
    ]
    assert exported.status_code == 200
    assert [item["feedbackId"] for item in exported.json()["items"]] == [
        inbox_feedback.json()["feedbackId"]
    ]


async def test_feedback_review_tag_memory_enables_lifecycle_next_actions() -> None:
    store = FakeFeedbackStore()
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        submitted = await client.post(
            "/api/feedback",
            headers=USER_HEADERS,
            json={
                "rating": "thumbs_down",
                "query": "Why was this answer wrong?",
                "response": "It used stale context.",
                "runId": "run_review_memory_1",
            },
        )
        feedback_id = submitted.json()["feedbackId"]
        reviewed = await client.patch(
            f"/api/feedback/{feedback_id}",
            headers={**ADMIN_HEADERS, "If-Match": "1"},
            json={"tags": ["memory"]},
        )

    assert submitted.status_code == 201
    assert reviewed.status_code == 200
    next_actions = {action["id"]: action for action in reviewed.json()["nextActions"]}
    assert next_actions["review-memory"] == (
        {
            "id": "review-memory",
            "label": "Inspect memory state and proposed memory review queue",
            "feedbackId": feedback_id,
            "subjectUserId": "user_1",
            "command": (
                "reactor-memory get --target-user-id user_1 --output table; "
                "reactor-memory proposals --status proposed --subject-id user_1 --output table"
            ),
        }
    )
    assert next_actions["verify-memory-lifecycle"] == {
        "id": "verify-memory-lifecycle",
        "label": "Verify memory lifecycle hardening before closing the feedback",
        "feedbackId": feedback_id,
        "preflightFile": "reports/release/release-smoke-preflight.local.json",
        "preflightEnvTemplate": "reports/release/release-smoke-preflight.local.env",
        "replatformReadinessFile": "reports/release/replatform-readiness.local.json",
        "smokePlanFile": "reports/release/release-smoke-plan.local.json",
        "releaseEvidenceFile": "reports/release-evidence.json",
        "releaseReadinessFile": "reports/release-readiness.json",
        "readinessReportArg": "--readiness-report hardening_suite=reports/hardening-suite.json",
        "requiredReadinessReports": ["hardening_suite"],
        "readinessReports": {"hardening_suite": "reports/hardening-suite.json"},
        "command": MEMORY_LIFECYCLE_GATE_ACTION,
    }


async def test_feedback_list_filters_by_source() -> None:
    store = FakeFeedbackStore(
        [
            Feedback(
                feedback_id="fb_slack",
                tenant_id="tenant_1",
                query="Slack question",
                response="Wrong Slack answer",
                rating=FeedbackRating.THUMBS_DOWN,
                session_id="session_1",
                run_id="run_slack",
                user_id="user_1",
                source="slack_button",
                created_at=datetime(2026, 6, 26, 0, 1, tzinfo=UTC),
                updated_at=datetime(2026, 6, 26, 0, 1, tzinfo=UTC),
            ),
            Feedback(
                feedback_id="fb_api",
                tenant_id="tenant_1",
                query="API question",
                response="Wrong API answer",
                rating=FeedbackRating.THUMBS_DOWN,
                session_id="session_2",
                run_id="run_api",
                user_id="user_1",
                source="api",
                created_at=datetime(2026, 6, 26, 0, 2, tzinfo=UTC),
                updated_at=datetime(2026, 6, 26, 0, 2, tzinfo=UTC),
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/feedback",
            headers=ADMIN_HEADERS,
            params={"rating": "thumbs_down", "source": "slack_button"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["approximateTotal"] == 1
    assert body["items"][0]["feedbackId"] == "fb_slack"
    assert body["items"][0]["source"] == "slack_button"
    assert "--feedback-source slack_button" in body["items"][0]["nextActions"][0]["command"]
    assert "--tag feedback-source:slack_button" not in body["items"][0]["nextActions"][0]["command"]


async def test_feedback_next_actions_tag_slack_feedback_workflow() -> None:
    store = FakeFeedbackStore(
        [
            Feedback(
                feedback_id="fb_slack",
                tenant_id="tenant_1",
                query="Slack question",
                response="Wrong Slack answer",
                rating=FeedbackRating.THUMBS_DOWN,
                session_id="session_1",
                run_id="run_slack",
                user_id="user_1",
                source="slack_button",
                created_at=datetime(2026, 6, 26, 0, 1, tzinfo=UTC),
                updated_at=datetime(2026, 6, 26, 0, 1, tzinfo=UTC),
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/feedback/fb_slack",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 200
    next_actions = {action["id"]: action["command"] for action in response.json()["nextActions"]}
    assert "--feedback-source slack_button" in next_actions["promote-eval"]
    assert "--tag slack" in next_actions["promote-eval"]
    assert "--tag slack" in next_actions["review-done"]


async def test_feedback_next_actions_omit_blank_source_provenance_tag() -> None:
    store = FakeFeedbackStore(
        [
            Feedback(
                feedback_id="fb_blank_source",
                tenant_id="tenant_1",
                query="API question",
                response="Wrong API answer",
                rating=FeedbackRating.THUMBS_DOWN,
                session_id="session_1",
                run_id="run_blank_source",
                user_id="user_1",
                source="",
                tags=["rag"],
                created_at=datetime(2026, 6, 26, 0, 1, tzinfo=UTC),
                updated_at=datetime(2026, 6, 26, 0, 1, tzinfo=UTC),
            ),
        ]
    )
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/feedback/fb_blank_source",
            headers=ADMIN_HEADERS,
        )

    assert response.status_code == 200
    next_actions = {action["id"]: action["command"] for action in response.json()["nextActions"]}
    assert "--tag feedback-source:" not in next_actions["promote-eval"]
    assert "--tag feedback-source:run" not in next_actions["promote-eval"]


async def test_feedback_stats_export_and_bulk_update_admin_contract() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    records = [
        Feedback(
            feedback_id="fb_up",
            tenant_id="tenant_1",
            query="좋은 질문",
            response="좋은 답변",
            rating=FeedbackRating.THUMBS_UP,
            session_id="session_1",
            user_id="user_1",
            source="slack_button",
            created_at=created_at,
            updated_at=created_at,
        ),
        Feedback(
            feedback_id="fb_down",
            tenant_id="tenant_1",
            query="나쁜 질문",
            response="나쁜 답변",
            rating=FeedbackRating.THUMBS_DOWN,
            session_id="session_2",
            run_id="run_export_down",
            user_id="user_2",
            source="admin_cli",
            tags=["collection:rag-ingestion-candidate"],
            comment="bad",
            created_at=created_at,
            updated_at=created_at,
        ),
    ]
    store = FakeFeedbackStore(records)
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden_stats = await client.get("/api/feedback/stats", headers=USER_HEADERS)
        stats = await client.get("/api/feedback/stats", headers=ADMIN_HEADERS)
        exported = await client.get(
            "/v1/feedback/export",
            headers=ADMIN_HEADERS,
            params={
                "rating": "thumbs_down",
                "source": "admin_cli",
                "tag": "collection:rag-ingestion-candidate",
            },
        )
        bulk = await client.post(
            "/api/feedback/bulk-update",
            headers=ADMIN_HEADERS,
            json={
                "ids": ["fb_down", "missing"],
                "status": "done",
                "tags": ["promoted", "langsmith"],
                "note": "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.",  # noqa: E501
            },
        )

    assert forbidden_stats.status_code == 403
    assert stats.status_code == 200
    assert stats.json()["total"] == 2
    assert stats.json()["positive"] == 1
    assert stats.json()["negative"] == 1
    assert stats.json()["positiveRate"] == 0.5
    assert stats.json()["commentRate"] == 0.5
    assert stats.json()["inboxCount"] == 2
    assert exported.status_code == 200
    assert exported.json()["source"] == "reactor"
    assert [item["feedbackId"] for item in exported.json()["items"]] == ["fb_down"]
    exported_sources = {item["feedbackId"]: item["source"] for item in exported.json()["items"]}
    assert exported_sources == {"fb_down": "admin_cli"}
    exported_versions = {item["feedbackId"]: item["version"] for item in exported.json()["items"]}
    assert exported_versions == {"fb_down": 1}
    exported_updated_at = {
        item["feedbackId"]: item["updatedAt"] for item in exported.json()["items"]
    }
    assert exported_updated_at == {
        "fb_down": created_at.isoformat(),
    }
    exported_workflows = {item["feedbackId"]: item["workflow"] for item in exported.json()["items"]}
    assert exported_workflows == {
        "fb_down": {
            "type": "rag_ingestion_candidate",
            "candidateId": "run_export_down",
            "collection": "rag-ingestion-candidate",
            "sourceUri": "rag-ingestion-candidate:run_export_down",
            "evalCaseId": "case_rag_candidate_run_export_down",
            "runId": "run_export_down",
            "sourceRunId": "run_export_down",
            "feedbackSource": "admin_cli",
            "feedbackTag": "rag-candidate:run_export_down",
        }
    }
    exported_next_actions = {
        item["feedbackId"]: item["nextActions"] for item in exported.json()["items"]
    }
    assert exported_next_actions["fb_down"][0]["id"] == "promote-eval"
    assert (
        "reactor-runs promote-eval run_export_down --case-id case_rag_candidate_run_export_down"
        in exported_next_actions["fb_down"][0]["command"]
    )
    assert "--tag rag-candidate:run_export_down" in exported_next_actions["fb_down"][0]["command"]
    exported_action_commands = {
        action["id"]: action["command"] for action in exported_next_actions["fb_down"]
    }
    assert exported_action_commands["inspect-candidate-feedback"] == (
        "reactor-admin feedback --rating thumbs_down "
        "--source admin_cli "
        "--review-status inbox "
        "--tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:run_export_down --limit 10 --output table"
    )
    assert exported_action_commands["export-candidate-feedback"] == (
        "reactor-admin feedback-export --rating thumbs_down "
        "--source admin_cli "
        "--review-status inbox "
        "--tag collection:rag-ingestion-candidate "
        "--tag rag-candidate:run_export_down --limit 10 --output json"
    )
    assert exported_next_actions["fb_down"][-1]["id"] == "review-done"
    assert (
        "reactor-admin feedback-review fb_down --if-match 1 --status done"
        in exported_next_actions["fb_down"][-1]["command"]
    )
    assert "--tag rag-candidate:run_export_down" in exported_next_actions["fb_down"][-1]["command"]
    assert bulk.status_code == 200
    assert bulk.json() == {
        "updated": ["fb_down"],
        "updatedDetails": [
            {
                "feedbackId": "fb_down",
                "evalCaseId": "case_rag_candidate_run_export_down",
                "sourceRunId": "run_export_down",
                "feedbackSource": "admin_cli",
                "reviewTags": ["promoted", "langsmith"],
                "reviewNote": (
                    "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync."  # noqa: E501
                ),
                "nextAction": release_readiness_command_for_reports(
                    required_reports=("hardening_suite", "langsmith_eval_sync"),
                    report_files={
                        "hardening_suite": "reports/hardening-suite.json",
                        "langsmith_eval_sync": (
                            "artifacts/langsmith/"
                            "rag-ingestion-candidate-case_rag_candidate_run_export_down.json"
                        ),
                    },
                ),
                "bulkReviewAction": (
                    "reactor-admin feedback-bulk-review --candidate-tag "
                    "rag-candidate:run_export_down --source admin_cli --status done "
                    "--tag promoted --tag langsmith --tag collection:rag-ingestion-candidate "
                    "--tag rag-candidate:run_export_down --note "
                    "'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.' "  # noqa: E501
                    "--output table"
                ),
                "readinessReportArg": (
                    "--readiness-report hardening_suite=reports/hardening-suite.json "
                    "--readiness-report langsmith_eval_sync=artifacts/langsmith/"
                    "rag-ingestion-candidate-case_rag_candidate_run_export_down.json"
                ),
                "requiredReadinessReports": ["hardening_suite", "langsmith_eval_sync"],
                "readinessReports": {
                    "hardening_suite": "reports/hardening-suite.json",
                    "langsmith_eval_sync": (
                        "artifacts/langsmith/"
                        "rag-ingestion-candidate-case_rag_candidate_run_export_down.json"
                    ),
                },
                "requiredEnvAnyOf": [
                    ["LANGSMITH_API_KEY", "REACTOR_OBSERVABILITY_LANGSMITH_API_KEY"]
                ],
                "recommendedEnv": ["LANGSMITH_ENDPOINT"],
                "releaseReadinessCommand": release_readiness_command_for_reports(
                    required_reports=("hardening_suite", "langsmith_eval_sync"),
                    report_files={
                        "hardening_suite": "reports/hardening-suite.json",
                        "langsmith_eval_sync": (
                            "artifacts/langsmith/"
                            "rag-ingestion-candidate-case_rag_candidate_run_export_down.json"
                        ),
                    },
                ),
            }
        ],
        "failed": [{"id": "missing", "reason": "not_found"}],
    }
    assert store.records["fb_down"].review_status == "done"
    assert store.records["fb_down"].review_tags == ["promoted", "langsmith"]
    assert store.records["fb_down"].review_note == (
        "Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync."  # noqa: E501
    )


async def test_feedback_analytics_groups_negative_rate_by_model() -> None:
    created_at = datetime(2026, 6, 26, tzinfo=UTC)
    records = [
        Feedback(
            feedback_id="fb_gpt5_down",
            tenant_id="tenant_1",
            query="Q1",
            response="A1",
            rating=FeedbackRating.THUMBS_DOWN,
            session_id="session_1",
            user_id="user_1",
            model="openai:gpt-5-mini",
            comment="incorrect",
            created_at=created_at,
            updated_at=created_at,
        ),
        Feedback(
            feedback_id="fb_gpt5_up",
            tenant_id="tenant_1",
            query="Q2",
            response="A2",
            rating=FeedbackRating.THUMBS_UP,
            session_id="session_2",
            user_id="user_2",
            model="openai:gpt-5-mini",
            created_at=created_at,
            updated_at=created_at,
        ),
        Feedback(
            feedback_id="fb_claude_down",
            tenant_id="tenant_1",
            query="Q3",
            response="A3",
            rating=FeedbackRating.THUMBS_DOWN,
            session_id="session_3",
            user_id="user_3",
            model="anthropic:claude-sonnet-4",
            created_at=created_at,
            updated_at=created_at,
        ),
        Feedback(
            feedback_id="fb_other_tenant",
            tenant_id="tenant_2",
            query="Q4",
            response="A4",
            rating=FeedbackRating.THUMBS_DOWN,
            session_id="session_4",
            user_id="user_4",
            model="openai:gpt-5-mini",
            created_at=created_at,
            updated_at=created_at,
        ),
    ]
    store = FakeFeedbackStore(records)
    app = create_app()
    app.state.reactor = FakeContainer(feedback_store=store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get(
            "/api/feedback/analytics",
            headers=USER_HEADERS,
            params={"groupBy": "model"},
        )
        analytics = await client.get(
            "/v1/feedback/analytics",
            headers=ADMIN_HEADERS,
            params={"groupBy": "model", "limit": 5},
        )

    assert forbidden.status_code == 403
    assert analytics.status_code == 200
    assert analytics.json() == {
        "groupBy": "model",
        "items": [
            {
                "key": "anthropic:claude-sonnet-4",
                "total": 1,
                "positive": 0,
                "negative": 1,
                "negativeRate": 1.0,
                "commentRate": 0.0,
            },
            {
                "key": "openai:gpt-5-mini",
                "total": 2,
                "positive": 1,
                "negative": 1,
                "negativeRate": 0.5,
                "commentRate": 0.5,
            },
        ],
    }


class FakeContainer:
    def __init__(self, *, feedback_store: FakeFeedbackStore) -> None:
        self._feedback_store = feedback_store

    def feedback_store(self) -> FakeFeedbackStore:
        return self._feedback_store


class FakeFeedbackStore:
    def __init__(self, records: list[Feedback] | None = None) -> None:
        self.records = {record.feedback_id: record for record in records or []}

    async def save(self, feedback: Feedback) -> Feedback:
        self.records[feedback.feedback_id] = feedback
        return feedback

    async def get(self, *, tenant_id: str, feedback_id: str) -> Feedback | None:
        record = self.records.get(feedback_id)
        return record if record is not None and record.tenant_id == tenant_id else None

    async def list(
        self,
        *,
        tenant_id: str,
        rating: FeedbackRating | None = None,
        template_id: str | None = None,
        source: str | None = None,
        review_status: str | None = None,
        tags: list[str] | None = None,
        case_id: str | None = None,
        limit: int = 50,
    ) -> list[Feedback]:
        records = [record for record in self.records.values() if record.tenant_id == tenant_id]
        if rating is not None:
            records = [record for record in records if record.rating == rating]
        if template_id is not None:
            records = [record for record in records if record.template_id == template_id]
        if source is not None:
            records = [record for record in records if record.source == source]
        if review_status is not None:
            records = [record for record in records if record.review_status == review_status]
        if tags:
            wanted = set(tags)
            records = [
                record
                for record in records
                if wanted.issubset(set(record.tags or []) | set(record.review_tags))
            ]
        if case_id is not None:
            records = [
                record for record in records if feedback_matches_eval_case_id(record, case_id)
            ]
        return sorted(records, key=lambda item: item.created_at, reverse=True)[:limit]

    async def update_review(
        self,
        *,
        tenant_id: str,
        feedback_id: str,
        expected_version: int,
        status: str | None,
        tags: list[str] | None,
        note: str | None,
        actor: str,
    ) -> Feedback:
        record = await self.get(tenant_id=tenant_id, feedback_id=feedback_id)
        if record is None:
            raise KeyError(feedback_id)
        if record.version != expected_version:
            raise ValueError("version_conflict")
        if feedback_review_matches(record, status=status, tags=tags, note=note):
            return record
        updated = replace(
            record,
            review_status=status or record.review_status,
            review_tags=tags if tags is not None else record.review_tags,
            review_note=note if note is not None else record.review_note,
            reviewed_by=actor,
            reviewed_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
            version=record.version + 1,
            updated_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
        )
        self.records[feedback_id] = updated
        return updated

    async def unreviewed_count(self, *, tenant_id: str) -> int:
        return sum(
            1
            for record in self.records.values()
            if record.tenant_id == tenant_id
            and record.rating == FeedbackRating.THUMBS_DOWN
            and record.review_status == "inbox"
        )

    async def delete(self, *, tenant_id: str, feedback_id: str) -> None:
        record = await self.get(tenant_id=tenant_id, feedback_id=feedback_id)
        if record is not None:
            self.records.pop(feedback_id)

    async def stats(self, *, tenant_id: str) -> dict[str, object]:
        records = [record for record in self.records.values() if record.tenant_id == tenant_id]
        positive = sum(1 for record in records if record.rating == FeedbackRating.THUMBS_UP)
        negative = sum(1 for record in records if record.rating == FeedbackRating.THUMBS_DOWN)
        inbox = sum(1 for record in records if record.review_status == "inbox")
        done = sum(1 for record in records if record.review_status == "done")
        with_comment = sum(1 for record in records if record.comment is not None)
        total = len(records)
        return {
            "total": total,
            "positive": positive,
            "negative": negative,
            "positiveRate": positive / total if total else 0.0,
            "commentRate": with_comment / total if total else 0.0,
            "inboxCount": inbox,
            "doneCount": done,
        }

    async def analytics(
        self,
        *,
        tenant_id: str,
        group_by: str,
        limit: int = 20,
    ) -> dict[str, object]:
        records = [record for record in self.records.values() if record.tenant_id == tenant_id]
        return feedback_analytics_payload(records, group_by=group_by, limit=limit)

    async def bulk_update_review(
        self,
        *,
        tenant_id: str,
        ids: list[str],
        status: str | None,
        tags: list[str] | None,
        note: str | None,
        actor: str,
    ) -> dict[str, object]:
        updated: list[str] = []
        already_done: list[str] = []
        failed: list[dict[str, str]] = []
        for feedback_id in ids:
            record = await self.get(tenant_id=tenant_id, feedback_id=feedback_id)
            if record is None:
                failed.append({"id": feedback_id, "reason": "not_found"})
                continue
            if feedback_review_matches(record, status=status, tags=tags, note=note):
                already_done.append(feedback_id)
                continue
            next_record = replace(
                record,
                review_status=status or record.review_status,
                review_tags=tags if tags is not None else record.review_tags,
                review_note=note if note is not None else record.review_note,
                reviewed_by=actor,
                reviewed_at=datetime(2026, 6, 26, 1, 0, tzinfo=UTC),
                version=record.version + 1,
            )
            self.records[feedback_id] = next_record
            updated.append(feedback_id)
        result: dict[str, object] = {"updated": updated, "failed": failed}
        if already_done:
            result["alreadyDone"] = already_done
        return result
