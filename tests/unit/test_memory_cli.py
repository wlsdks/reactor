from __future__ import annotations

import json
from io import StringIO

from reactor.cli.memory import (
    MemoryCliHttpResult,
    memory_proposal_next_action_rows,
    memory_review_next_action,
    result_from_response,
    run_cli,
)
from reactor.memory.lifecycle_actions import MEMORY_LIFECYCLE_GATE_ACTION


class FakeMemoryProbe:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get_json(self, path: str, headers: dict[str, str]) -> MemoryCliHttpResult:
        self.calls.append({"method": "GET", "path": path, "headers": headers})
        if path == "/api/user-memory/user_1":
            return MemoryCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "facts": {"team": "platform"},
                    "preferences": {"language": "Korean"},
                    "recentTopics": ["release"],
                    "updatedAt": "2026-07-02T00:00:00+00:00",
                },
            )
        if path == "/api/admin/memory/proposals?status=proposed&limit=25":
            return MemoryCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "status": "proposed",
                    "count": 1,
                    "items": [
                        {
                            "id": "proposal_1",
                            "status": "proposed",
                            "subjectType": "user",
                            "subjectId": "user_1",
                            "memoryType": "preference",
                            "visibility": "private",
                            "confidence": 0.93,
                            "proposedContent": "User prefers Korean status updates.",
                            "createdAt": "2026-07-02T00:00:00+00:00",
                        }
                    ],
                },
            )
        if path == "/api/admin/memory/proposals?status=proposed&limit=25&subject_id=user_1":
            return MemoryCliHttpResult(ok=True, status_code=200, body={"items": []})
        return MemoryCliHttpResult(ok=False, status_code=404, error="not found")

    def put_json(
        self,
        path: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> MemoryCliHttpResult:
        self.calls.append(
            {
                "method": "PUT",
                "path": path,
                "headers": headers,
                "payload": payload,
            }
        )
        if path == "/api/user-memory/user_1/preferences":
            return MemoryCliHttpResult(ok=True, status_code=200, body={"updated": True})
        return MemoryCliHttpResult(ok=False, status_code=404, error="not found")

    def post_json(
        self,
        path: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> MemoryCliHttpResult:
        self.calls.append(
            {
                "method": "POST",
                "path": path,
                "headers": headers,
                "payload": payload,
            }
        )
        if path == "/api/admin/memory/proposals/proposal_1/approve":
            return MemoryCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "proposal": {
                        "id": "proposal_1",
                        "status": "approved",
                        "subjectId": "user_1",
                        "memoryType": "preference",
                        "visibility": "private",
                        "confidence": 0.93,
                        "proposedContent": "User prefers Korean status updates.",
                    },
                    "item": {
                        "id": "memory_1",
                        "status": "active",
                        "content": "User prefers Korean status updates.",
                    },
                },
            )
        if path == "/api/admin/memory/proposals/proposal_1/reject":
            return MemoryCliHttpResult(
                ok=True,
                status_code=200,
                body={
                    "id": "proposal_1",
                    "status": "rejected",
                    "subjectId": "user_1",
                    "memoryType": "preference",
                    "visibility": "private",
                    "confidence": 0.93,
                    "decisionReason": "not stable enough",
                    "proposedContent": "User prefers Korean status updates.",
                },
            )
        return MemoryCliHttpResult(ok=False, status_code=404, error="not found")

    def delete_json(self, path: str, headers: dict[str, str]) -> MemoryCliHttpResult:
        self.calls.append({"method": "DELETE", "path": path, "headers": headers})
        if path == "/api/user-memory/user_1":
            return MemoryCliHttpResult(ok=True, status_code=204, body={"deleted": True})
        return MemoryCliHttpResult(ok=False, status_code=404, error="not found")


def test_memory_review_actions_quote_shell_arguments() -> None:
    proposal_rows = [
        (
            "proposal needs quoting",
            "proposed",
            "user",
            "user needs quoting",
            "preference",
            "private",
            "0.93",
            "2026-07-02T00:00:00+00:00",
            "content",
            "",
            "",
            "",
            "",
            "",
        )
    ]

    assert memory_proposal_next_action_rows(proposal_rows) == [
        "nextAction  reactor-memory get --target-user-id 'user needs quoting' --output table"
    ]
    review_action = memory_review_next_action(
        {"status": "approved", "subjectId": "user needs quoting"}
    )
    assert review_action is not None
    assert review_action == (
        "reactor-memory get --target-user-id 'user needs quoting' --output table"
    )
    rejected_review_action = memory_review_next_action(
        {"status": "rejected", "subjectId": "user needs quoting"}
    )
    assert rejected_review_action is not None
    assert rejected_review_action == (
        "reactor-memory proposals --status proposed --subject-id 'user needs quoting' "
        "--output table"
    )


def test_memory_cli_gets_and_updates_user_preference_with_self_headers() -> None:
    probe = FakeMemoryProbe()
    update_stdout = StringIO()
    get_stdout = StringIO()

    update_exit = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "user_1",
            "set-preference",
            "--key",
            "language",
            "--value",
            "Korean",
        ],
        http_probe=probe,
        stdout=update_stdout,
        stderr=StringIO(),
        environ={},
    )
    get_exit = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "user_1",
            "get",
        ],
        http_probe=probe,
        stdout=get_stdout,
        stderr=StringIO(),
        environ={},
    )

    assert update_exit == 0
    assert json.loads(update_stdout.getvalue()) == {"updated": True}
    assert get_exit == 0
    assert json.loads(get_stdout.getvalue()) == {
        "facts": {"team": "platform"},
        "preferences": {"language": "Korean"},
        "recentTopics": ["release"],
        "updatedAt": "2026-07-02T00:00:00+00:00",
    }
    expected_headers = {
        "Content-Type": "application/json",
        "X-Reactor-Tenant-Id": "tenant_1",
        "X-Reactor-User-Id": "user_1",
    }
    assert probe.calls == [
        {
            "method": "PUT",
            "path": "/api/user-memory/user_1/preferences",
            "headers": expected_headers,
            "payload": {"key": "language", "value": "Korean"},
        },
        {
            "method": "GET",
            "path": "/api/user-memory/user_1",
            "headers": expected_headers,
        },
    ]


def test_memory_cli_get_can_render_operator_table_output() -> None:
    probe = FakeMemoryProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "user_1",
            "get",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "SECTION       KEY       VALUE\n"
        "facts         team      platform\n"
        "preferences   language  Korean\n"
        "recentTopics  0         release\n"
        "updatedAt     -         2026-07-02T00:00:00+00:00\n"
    )
    assert probe.calls[-1]["path"] == "/api/user-memory/user_1"


def test_memory_cli_proposals_can_render_review_queue_table() -> None:
    probe = FakeMemoryProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "manager_1",
            "--role",
            "admin",
            "proposals",
            "--limit",
            "25",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "ID          STATUS    SUBJECT_TYPE  SUBJECT  TYPE        VISIBILITY  CONFIDENCE  "
        "CREATED                    CONTENT\n"
        "proposal_1  proposed  user          user_1   preference  private     0.93        "
        "2026-07-02T00:00:00+00:00  "
        "User prefers Korean status updates.\n"
        "nextAction  reactor-memory get --target-user-id user_1 --output table\n"
    )
    assert probe.calls[-1] == {
        "method": "GET",
        "path": "/api/admin/memory/proposals?status=proposed&limit=25",
        "headers": {
            "Content-Type": "application/json",
            "X-Reactor-Tenant-Id": "tenant_1",
            "X-Reactor-User-Id": "manager_1",
            "X-Reactor-Role": "admin",
        },
    }


def test_memory_cli_proposals_table_shows_langmem_extraction_provenance() -> None:
    class MemoryProposalProvenanceProbe(FakeMemoryProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> MemoryCliHttpResult:
            if path == "/api/admin/memory/proposals?status=proposed&limit=25":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return MemoryCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "status": "proposed",
                        "count": 1,
                        "items": [
                            {
                                "id": "proposal_1",
                                "status": "proposed",
                                "subjectId": "user_1",
                                "memoryType": "preference",
                                "visibility": "private",
                                "confidence": 0.93,
                                "extractionModel": "langmem",
                                "extractionPromptVersion": "memory-v1",
                                "proposedContent": "User prefers Korean status updates.",
                                "createdAt": "2026-07-02T00:00:00+00:00",
                            }
                        ],
                    },
                )
            return super().get_json(path, headers)

    probe = MemoryProposalProvenanceProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "manager_1",
            "--role",
            "admin",
            "proposals",
            "--limit",
            "25",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert "EXTRACTOR" in stdout.getvalue()
    assert "PROMPT" in stdout.getvalue()
    assert "langmem" in stdout.getvalue()
    assert "memory-v1" in stdout.getvalue()


def test_memory_cli_proposals_table_shows_safe_maintenance_summary() -> None:
    class MemoryProposalMaintenanceProbe(FakeMemoryProbe):
        def get_json(self, path: str, headers: dict[str, str]) -> MemoryCliHttpResult:
            if path == "/api/admin/memory/proposals?status=proposed&limit=25":
                self.calls.append({"method": "GET", "path": path, "headers": headers})
                return MemoryCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "status": "proposed",
                        "count": 1,
                        "items": [
                            {
                                "id": "proposal_1",
                                "status": "proposed",
                                "subjectId": "user_1",
                                "memoryType": "preference",
                                "visibility": "private",
                                "confidence": 0.93,
                                "proposedContent": "User prefers Korean status updates.",
                                "createdAt": "2026-07-02T00:00:00+00:00",
                                "maintenance": {
                                    "manager": "create_memory_manager",
                                    "deletePolicy": "reactor_owned",
                                    "sensitivity": {
                                        "status": "flagged",
                                        "policy": "reject_or_redact_before_promotion",
                                        "markers": ["api_key", "secret"],
                                        "source": "content_or_source_payload",
                                    },
                                    "dependencyReviewCommand": (
                                        "uv pip show langmem trustcall langgraph"
                                    ),
                                    "dependencyRemediationCommand": (
                                        "monitor upstream trustcall/langmem compatibility; keep "
                                        "dependency warning visible until "
                                        "trustcall stops importing langgraph.constants.Send or "
                                        "Reactor replaces the dependency path"
                                    ),
                                    "sourcePayload": {"raw": "do not expose"},
                                },
                                "nextActions": [
                                    {
                                        "id": "review-memory-dependencies",
                                        "label": (
                                            "Review LangMem dependency compatibility before "
                                            "memory release"
                                        ),
                                        "command": "uv pip show langmem trustcall langgraph",
                                    },
                                    {
                                        "id": "verify-memory-lifecycle",
                                        "label": (
                                            "Verify memory lifecycle hardening before closing "
                                            "the review"
                                        ),
                                        "preflightFile": (
                                            "reports/release/release-smoke-preflight.local.json"
                                        ),
                                        "preflightEnvTemplate": (
                                            "reports/release/release-smoke-preflight.local.env"
                                        ),
                                        "replatformReadinessFile": (
                                            "reports/release/replatform-readiness.local.json"
                                        ),
                                        "smokePlanFile": (
                                            "reports/release/release-smoke-plan.local.json"
                                        ),
                                        "releaseEvidenceFile": "reports/release-evidence.json",
                                        "releaseReadinessFile": "reports/release-readiness.json",
                                        "readinessReportArg": (
                                            "--readiness-report "
                                            "hardening_suite=reports/hardening-suite.json"
                                        ),
                                        "requiredReadinessReports": ["hardening_suite"],
                                        "readinessReports": {
                                            "hardening_suite": "reports/hardening-suite.json",
                                        },
                                        "command": MEMORY_LIFECYCLE_GATE_ACTION,
                                    },
                                ],
                            }
                        ],
                    },
                )
            return super().get_json(path, headers)

    probe = MemoryProposalMaintenanceProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "manager_1",
            "--role",
            "admin",
            "proposals",
            "--limit",
            "25",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "LANGMEM_MANAGER" in output
    assert "DELETE_POLICY" in output
    assert "DEPENDENCY_REVIEW" in output
    assert "DEPENDENCY_REMEDIATION" in output
    assert "SENSITIVITY" in output
    assert "LANGMEM_AREAS" in output
    assert "create_memory_manager" in output
    assert "reactor_owned" in output
    assert "flagged:api_key,secret:content_or_source_payload" in output
    assert "uv pip show langmem trustcall langgraph" in output
    assert "monitor upstream trustcall/langmem compatibility" in output
    assert "trustcall stops importing langgraph.constants.Send" in output
    assert "manager,statuses,consolidation,review,privacy,dependencies" in output
    assert (
        "nextAction.proposal_1.review-memory-dependencies  "
        "Review LangMem dependency compatibility before memory release  "
        "uv pip show langmem trustcall langgraph"
    ) in output
    assert (
        "nextAction.proposal_1.verify-memory-lifecycle  "
        f"Verify memory lifecycle hardening before closing the review  "
        f"{MEMORY_LIFECYCLE_GATE_ACTION}"
    ) in output
    assert (
        "nextAction.proposal_1.verify-memory-lifecycle.preflightFile  "
        "reports/release/release-smoke-preflight.local.json"
    ) in output
    assert (
        "nextAction.proposal_1.verify-memory-lifecycle.preflightEnvTemplate  "
        "reports/release/release-smoke-preflight.local.env"
    ) in output
    assert (
        "nextAction.proposal_1.verify-memory-lifecycle.replatformReadinessFile  "
        "reports/release/replatform-readiness.local.json"
    ) in output
    assert (
        "nextAction.proposal_1.verify-memory-lifecycle.smokePlanFile  "
        "reports/release/release-smoke-plan.local.json"
    ) in output
    assert (
        "nextAction.proposal_1.verify-memory-lifecycle.releaseEvidenceFile  "
        "reports/release-evidence.json"
    ) in output
    assert (
        "nextAction.proposal_1.verify-memory-lifecycle.releaseReadinessFile  "
        "reports/release-readiness.json"
    ) in output
    assert (
        "nextAction.proposal_1.verify-memory-lifecycle.readinessReportArg  "
        "--readiness-report hardening_suite=reports/hardening-suite.json"
    ) in output
    assert (
        "nextAction.proposal_1.verify-memory-lifecycle.requiredReadinessReports  hardening_suite"
    ) in output
    assert (
        "nextAction.proposal_1.verify-memory-lifecycle.readinessReports.hardening_suite  "
        "reports/hardening-suite.json"
    ) in output
    assert "do not expose" not in output


def test_memory_cli_proposals_table_shows_review_next_action() -> None:
    probe = FakeMemoryProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "manager_1",
            "--role",
            "admin",
            "proposals",
            "--limit",
            "25",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert (
        "nextAction  reactor-memory get --target-user-id user_1 --output table\n"
    ) in stdout.getvalue()


def test_memory_cli_proposals_can_filter_by_subject_id() -> None:
    probe = FakeMemoryProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "manager_1",
            "--role",
            "admin",
            "proposals",
            "--limit",
            "25",
            "--subject-id",
            "user_1",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["path"] == (
        "/api/admin/memory/proposals?status=proposed&limit=25&subject_id=user_1"
    )


def test_memory_cli_approve_promotes_proposal_with_reason() -> None:
    probe = FakeMemoryProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "manager_1",
            "--role",
            "admin",
            "approve",
            "proposal_1",
            "--reason",
            "stable preference",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "FIELD                VALUE\n"
        "proposal.id          proposal_1\n"
        "proposal.status      approved\n"
        "proposal.subjectId   user_1\n"
        "proposal.confidence  0.93\n"
        "item.id              memory_1\n"
        "item.status          active\n"
        "nextAction           reactor-memory get --target-user-id user_1 --output table\n"
    )
    assert probe.calls[-1] == {
        "method": "POST",
        "path": "/api/admin/memory/proposals/proposal_1/approve",
        "headers": {
            "Content-Type": "application/json",
            "X-Reactor-Tenant-Id": "tenant_1",
            "X-Reactor-User-Id": "manager_1",
            "X-Reactor-Role": "admin",
        },
        "payload": {"reason": "stable preference"},
    }


def test_memory_cli_approve_surfaces_sensitive_recovery_actions() -> None:
    class SensitiveApprovalProbe(FakeMemoryProbe):
        def post_json(
            self,
            path: str,
            headers: dict[str, str],
            payload: dict[str, object],
        ) -> MemoryCliHttpResult:
            self.calls.append(
                {
                    "method": "POST",
                    "path": path,
                    "headers": headers,
                    "payload": payload,
                }
            )
            return MemoryCliHttpResult(
                ok=False,
                status_code=400,
                body={
                    "detail": {
                        "reason": "sensitive_memory_requires_rejection_or_redaction",
                        "message": "sensitive memory proposals require rejection or redaction",
                        "proposalId": "proposal_1",
                        "sensitivity": {
                            "status": "flagged",
                            "policy": "reject_or_redact_before_promotion",
                            "markers": ["api_key"],
                            "source": "content_or_source_payload",
                        },
                        "rejectAction": (
                            "reactor-memory reject proposal_1 "
                            "--reason 'sensitive or inaccurate memory' --output table"
                        ),
                        "reviewQueueAction": (
                            "reactor-memory proposals --status proposed "
                            "--subject-id user_1 --output table"
                        ),
                        "nextActions": [
                            {
                                "id": "reject-memory",
                                "label": "Reject this sensitive memory proposal",
                                "command": (
                                    "reactor-memory reject proposal_1 "
                                    "--reason 'sensitive or inaccurate memory' --output table"
                                ),
                            },
                            {
                                "id": "review-proposals",
                                "label": "Review remaining proposed memories for this user",
                                "command": (
                                    "reactor-memory proposals --status proposed "
                                    "--subject-id user_1 --output table"
                                ),
                            },
                        ],
                    }
                },
                error="bad request",
            )

    stderr = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "manager_1",
            "--role",
            "admin",
            "approve",
            "proposal_1",
            "--reason",
            "stable preference",
            "--output",
            "table",
        ],
        http_probe=SensitiveApprovalProbe(),
        stdout=StringIO(),
        stderr=stderr,
        environ={},
    )

    assert exit_code == 1
    assert "sensitive memory proposals require rejection or redaction" in stderr.getvalue()
    assert "reason: sensitive_memory_requires_rejection_or_redaction" in stderr.getvalue()
    assert "proposalId: proposal_1" in stderr.getvalue()
    assert "sensitivity.status: flagged" in stderr.getvalue()
    assert "sensitivity.policy: reject_or_redact_before_promotion" in stderr.getvalue()
    assert "sensitivity.markers: api_key" in stderr.getvalue()
    assert "sensitivity.source: content_or_source_payload" in stderr.getvalue()
    assert "nextActionIds: reject-memory,review-proposals" in stderr.getvalue()
    assert (
        "nextAction.reject-memory: Reject this sensitive memory proposal  "
        "reactor-memory reject proposal_1 "
        "--reason 'sensitive or inaccurate memory' --output table"
    ) in stderr.getvalue()
    assert (
        "nextAction.review-proposals: Review remaining proposed memories for this user  "
        "reactor-memory proposals --status proposed --subject-id user_1 --output table"
    ) in stderr.getvalue()
    assert (
        "reactor-memory reject proposal_1 --reason 'sensitive or inaccurate memory' --output table"
        in stderr.getvalue()
    )
    assert (
        "reactor-memory proposals --status proposed --subject-id user_1 --output table"
        in stderr.getvalue()
    )


def test_memory_cli_http_result_preserves_structured_error_body() -> None:
    import httpx

    response = httpx.Response(
        400,
        json={
            "detail": {
                "message": "sensitive memory proposals require rejection or redaction",
                "rejectAction": (
                    "reactor-memory reject proposal_1 "
                    "--reason 'sensitive or inaccurate memory' --output table"
                ),
            }
        },
    )

    result = result_from_response(response)

    assert result.ok is False
    assert result.status_code == 400
    assert result.body == {
        "detail": {
            "message": "sensitive memory proposals require rejection or redaction",
            "rejectAction": (
                "reactor-memory reject proposal_1 "
                "--reason 'sensitive or inaccurate memory' --output table"
            ),
        }
    }


def test_memory_cli_approve_can_supersede_memory_item() -> None:
    probe = FakeMemoryProbe()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "manager_1",
            "--role",
            "admin",
            "approve",
            "proposal_1",
            "--reason",
            "newer reviewed preference",
            "--supersedes-memory-id",
            "memory_old",
        ],
        http_probe=probe,
        stdout=StringIO(),
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["payload"] == {
        "reason": "newer reviewed preference",
        "supersedesMemoryId": "memory_old",
    }


def test_memory_cli_approve_url_encodes_proposal_id() -> None:
    class EncodedProposalProbe(FakeMemoryProbe):
        def post_json(
            self,
            path: str,
            headers: dict[str, str],
            payload: dict[str, object],
        ) -> MemoryCliHttpResult:
            self.calls.append(
                {
                    "method": "POST",
                    "path": path,
                    "headers": headers,
                    "payload": payload,
                }
            )
            if path == "/api/admin/memory/proposals/proposal%2Fneeds%20encoding/approve":
                return MemoryCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "proposal": {
                            "id": "proposal/needs encoding",
                            "status": "approved",
                            "subjectId": "user_1",
                        }
                    },
                )
            return MemoryCliHttpResult(ok=False, status_code=404, error="not found")

    probe = EncodedProposalProbe()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "manager_1",
            "--role",
            "admin",
            "approve",
            "proposal/needs encoding",
            "--reason",
            "stable preference",
        ],
        http_probe=probe,
        stdout=StringIO(),
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert probe.calls[-1]["method"] == "POST"
    assert (
        probe.calls[-1]["path"] == "/api/admin/memory/proposals/proposal%2Fneeds%20encoding/approve"
    )
    assert probe.calls[-1]["payload"] == {"reason": "stable preference"}


def test_memory_cli_approve_table_shows_superseded_memory_items() -> None:
    class SupersedingApproveProbe(FakeMemoryProbe):
        def post_json(
            self,
            path: str,
            headers: dict[str, str],
            payload: dict[str, object],
        ) -> MemoryCliHttpResult:
            if path == "/api/admin/memory/proposals/proposal_1/approve":
                self.calls.append(
                    {
                        "method": "POST",
                        "path": path,
                        "headers": headers,
                        "payload": payload,
                    }
                )
                return MemoryCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "proposal": {
                            "id": "proposal_1",
                            "status": "approved",
                            "subjectId": "user_1",
                        },
                        "item": {"id": "memory_2", "status": "active"},
                        "supersededItems": [
                            {"id": "memory_1", "status": "superseded"},
                        ],
                        "nextActions": [
                            {
                                "id": "inspect-memory",
                                "command": (
                                    "reactor-memory get --target-user-id user_1 --output table"
                                ),
                            },
                            {
                                "id": "verify-superseded-exclusion",
                                "command": (
                                    "uv run pytest tests/unit/test_prompt_assembler.py "
                                    "-q -k excludes_superseded_memory"
                                ),
                            },
                            {
                                "id": "review-memory-dependencies",
                                "command": "uv pip show langmem trustcall langgraph",
                            },
                            {
                                "id": "verify-memory-lifecycle",
                                "preflightFile": (
                                    "reports/release/release-smoke-preflight.local.json"
                                ),
                                "preflightEnvTemplate": (
                                    "reports/release/release-smoke-preflight.local.env"
                                ),
                                "replatformReadinessFile": (
                                    "reports/release/replatform-readiness.local.json"
                                ),
                                "smokePlanFile": "reports/release/release-smoke-plan.local.json",
                                "releaseEvidenceFile": "reports/release-evidence.json",
                                "releaseReadinessFile": "reports/release-readiness.json",
                                "readinessReportArg": (
                                    "--readiness-report "
                                    "hardening_suite=reports/hardening-suite.json"
                                ),
                                "requiredReadinessReports": ["hardening_suite"],
                                "readinessReports": {
                                    "hardening_suite": "reports/hardening-suite.json",
                                },
                                "command": MEMORY_LIFECYCLE_GATE_ACTION,
                            },
                        ],
                    },
                )
            return super().post_json(path, headers, payload)

    probe = SupersedingApproveProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "manager_1",
            "--role",
            "admin",
            "approve",
            "proposal_1",
            "--reason",
            "more specific preference",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    rows = dict(line.split(maxsplit=1) for line in stdout.getvalue().splitlines()[1:])
    assert rows["superseded.count"] == "1"
    assert rows["superseded.ids"] == "memory_1"
    assert rows["nextAction"] == "reactor-memory get --target-user-id user_1 --output table"
    assert (
        rows["nextActionIds"]
        == "inspect-memory,verify-superseded-exclusion,review-memory-dependencies,"
        "verify-memory-lifecycle"
    )
    assert rows["nextAction.verify-superseded-exclusion"] == (
        "uv run pytest tests/unit/test_prompt_assembler.py -q -k excludes_superseded_memory"
    )
    assert rows["nextAction.review-memory-dependencies"] == (
        "uv pip show langmem trustcall langgraph"
    )
    assert rows["nextAction.verify-memory-lifecycle"] == MEMORY_LIFECYCLE_GATE_ACTION
    assert (
        rows["nextAction.verify-memory-lifecycle.preflightFile"]
        == "reports/release/release-smoke-preflight.local.json"
    )
    assert (
        rows["nextAction.verify-memory-lifecycle.preflightEnvTemplate"]
        == "reports/release/release-smoke-preflight.local.env"
    )
    assert (
        rows["nextAction.verify-memory-lifecycle.replatformReadinessFile"]
        == "reports/release/replatform-readiness.local.json"
    )
    assert (
        rows["nextAction.verify-memory-lifecycle.smokePlanFile"]
        == "reports/release/release-smoke-plan.local.json"
    )
    assert (
        rows["nextAction.verify-memory-lifecycle.releaseEvidenceFile"]
        == "reports/release-evidence.json"
    )
    assert (
        rows["nextAction.verify-memory-lifecycle.releaseReadinessFile"]
        == "reports/release-readiness.json"
    )
    assert (
        rows["nextAction.verify-memory-lifecycle.readinessReportArg"]
        == "--readiness-report hardening_suite=reports/hardening-suite.json"
    )
    assert rows["nextAction.verify-memory-lifecycle.requiredReadinessReports"] == "hardening_suite"
    assert (
        rows["nextAction.verify-memory-lifecycle.readinessReports.hardening_suite"]
        == "reports/hardening-suite.json"
    )
    assert "&&" not in rows["nextAction"]


def test_memory_cli_approve_table_shows_langmem_consolidation_metadata() -> None:
    class LangMemApproveProbe(FakeMemoryProbe):
        def post_json(
            self,
            path: str,
            headers: dict[str, str],
            payload: dict[str, object],
        ) -> MemoryCliHttpResult:
            if path == "/api/admin/memory/proposals/proposal_1/approve":
                self.calls.append(
                    {
                        "method": "POST",
                        "path": path,
                        "headers": headers,
                        "payload": payload,
                    }
                )
                return MemoryCliHttpResult(
                    ok=True,
                    status_code=200,
                    body={
                        "proposal": {
                            "id": "proposal_1",
                            "status": "approved",
                            "subjectId": "user_1",
                            "extractionModel": "langmem",
                            "extractionPromptVersion": "memory-v1",
                        },
                        "item": {"id": "memory_2", "status": "active"},
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
                        },
                    },
                )
            return super().post_json(path, headers, payload)

    probe = LangMemApproveProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "manager_1",
            "--role",
            "admin",
            "approve",
            "proposal_1",
            "--reason",
            "stable preference",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    rows = dict(line.split(maxsplit=1) for line in stdout.getvalue().splitlines()[1:])
    assert rows["langmem.manager"] == "create_memory_manager"
    assert rows["langmem.storeManager"] == "create_memory_store_manager"
    assert rows["langmem.operation"] == "ainvoke"
    assert rows["langmem.maxSteps"] == "1"
    assert rows["langmem.deletePolicy"] == "reactor_owned"
    assert rows["langmem.dependencyReview"] == "uv pip show langmem trustcall langgraph"
    assert rows["langmem.dependencyRemediation"] == (
        "monitor upstream trustcall/langmem compatibility; keep "
        "dependency warning visible until "
        "trustcall stops importing langgraph.constants.Send or "
        "Reactor replaces the dependency path"
    )
    assert (
        rows["langmem.contractAreas"]
        == "manager,statuses,consolidation,review,privacy,dependencies"
    )
    assert rows["proposal.extractionModel"] == "langmem"
    assert rows["proposal.extractionPromptVersion"] == "memory-v1"


def test_memory_cli_approve_table_next_action_is_single_step() -> None:
    probe = FakeMemoryProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "manager_1",
            "--role",
            "admin",
            "approve",
            "proposal_1",
            "--reason",
            "stable preference",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    rows = dict(line.split(maxsplit=1) for line in stdout.getvalue().splitlines()[1:])
    assert rows["nextAction"] == "reactor-memory get --target-user-id user_1 --output table"
    assert "&&" not in rows["nextAction"]


def test_memory_cli_approve_table_next_action_omits_lifecycle_chain() -> None:
    probe = FakeMemoryProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "manager_1",
            "--role",
            "admin",
            "approve",
            "proposal_1",
            "--reason",
            "stable preference",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    rows = dict(line.split(maxsplit=1) for line in stdout.getvalue().splitlines()[1:])
    assert "VERIFY_TIMESTAMP" not in rows["nextAction"]
    assert "--skip-release-evidence-readiness" not in rows["nextAction"]
    assert MEMORY_LIFECYCLE_GATE_ACTION not in rows["nextAction"]


def test_memory_cli_reject_marks_proposal_reviewed_with_reason() -> None:
    probe = FakeMemoryProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "manager_1",
            "--role",
            "admin",
            "reject",
            "proposal_1",
            "--reason",
            "not stable enough",
            "--output",
            "table",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        "FIELD                    VALUE\n"
        "proposal.id              proposal_1\n"
        "proposal.status          rejected\n"
        "proposal.subjectId       user_1\n"
        "proposal.confidence      0.93\n"
        "proposal.decisionReason  not stable enough\n"
        "nextAction               reactor-memory proposals --status proposed --subject-id user_1 "
        "--output table\n"
    )
    assert probe.calls[-1] == {
        "method": "POST",
        "path": "/api/admin/memory/proposals/proposal_1/reject",
        "headers": {
            "Content-Type": "application/json",
            "X-Reactor-Tenant-Id": "tenant_1",
            "X-Reactor-User-Id": "manager_1",
            "X-Reactor-Role": "admin",
        },
        "payload": {"reason": "not stable enough"},
    }


def test_memory_cli_deletes_current_user_memory_with_self_headers() -> None:
    probe = FakeMemoryProbe()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "--base-url",
            "http://reactor.local",
            "--tenant-id",
            "tenant_1",
            "--user-id",
            "user_1",
            "delete",
        ],
        http_probe=probe,
        stdout=stdout,
        stderr=StringIO(),
        environ={},
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == {"deleted": True}
    assert probe.calls == [
        {
            "method": "DELETE",
            "path": "/api/user-memory/user_1",
            "headers": {
                "Content-Type": "application/json",
                "X-Reactor-Tenant-Id": "tenant_1",
                "X-Reactor-User-Id": "user_1",
            },
        }
    ]
