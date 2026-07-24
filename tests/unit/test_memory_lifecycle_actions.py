from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from reactor.memory.lifecycle_actions import MEMORY_LIFECYCLE_GATE_ACTION
from reactor.release.readiness_actions import release_readiness_command


def test_memory_lifecycle_gate_action_is_shared_across_harness_surfaces() -> None:
    from reactor.api.routers.feedback import MEMORY_LIFECYCLE_ACTION as feedback_action
    from reactor.evals.hardening_suite import memory_maintenance_lifecycle_evidence
    from reactor.evals.langsmith_dataset import MEMORY_LIFECYCLE_ACTION as langsmith_action
    from reactor.release.readiness_contracts import feedback_review_queue_memory_lifecycle_action

    lifecycle = memory_maintenance_lifecycle_evidence()
    review_surface = cast(Mapping[str, object], lifecycle["reviewSurface"])

    assert MEMORY_LIFECYCLE_GATE_ACTION == feedback_action
    assert MEMORY_LIFECYCLE_GATE_ACTION == langsmith_action
    assert MEMORY_LIFECYCLE_GATE_ACTION == review_surface["lifecycleGateAction"]
    assert MEMORY_LIFECYCLE_GATE_ACTION == feedback_review_queue_memory_lifecycle_action(
        {"memory": 1}
    )
    assert "# check memoryMaintenanceLifecycle" not in MEMORY_LIFECYCLE_GATE_ACTION
    assert "uv run pytest tests/unit/test_rag_memory.py" in MEMORY_LIFECYCLE_GATE_ACTION
    assert "tests/unit/test_prompt_assembler.py" in MEMORY_LIFECYCLE_GATE_ACTION
    assert "tests/unit/test_context_manifest.py" in MEMORY_LIFECYCLE_GATE_ACTION
    assert "tests/integration/test_admin_api.py" in MEMORY_LIFECYCLE_GATE_ACTION
    assert "tests/integration/test_feedback_api.py" in MEMORY_LIFECYCLE_GATE_ACTION
    assert (
        "REACTOR_TEST_POSTGRES=1 uv run pytest "
        "tests/integration/test_memory_postgres_lifecycle.py -q" in MEMORY_LIFECYCLE_GATE_ACTION
    )
    assert (
        "uv run pytest tests/unit/test_memory_cli.py "
        "tests/unit/test_memory_lifecycle_actions.py "
        "-q -k 'memory_lifecycle or sensitive_recovery_actions or structured_error_body'"
        in MEMORY_LIFECYCLE_GATE_ACTION
    )
    assert "--preflight-file reports/release/release-smoke-preflight.local.json" in (
        MEMORY_LIFECYCLE_GATE_ACTION
    )
    assert "--env-file reports/release/release-smoke-preflight.local.env" in (
        MEMORY_LIFECYCLE_GATE_ACTION
    )
    assert (
        "uv run reactor-replatform-readiness --output "
        "reports/release/replatform-readiness.local.json "
        "--allow-deferred-release-gates "
        "&& uv run reactor-release-smoke-plan "
        "--readiness reports/release/replatform-readiness.local.json "
        "--output reports/release/release-smoke-plan.local.json "
        "&& uv run reactor-release-smoke-run"
    ) in MEMORY_LIFECYCLE_GATE_ACTION
    assert "--evidence-output reports/release-evidence.json" in MEMORY_LIFECYCLE_GATE_ACTION
    assert "--skip-release-evidence-readiness" not in MEMORY_LIFECYCLE_GATE_ACTION
    assert "--verified-at $(date -u +%Y-%m-%dT%H:%M:%SZ)" in MEMORY_LIFECYCLE_GATE_ACTION
    assert (
        release_readiness_command(
            required_report="hardening_suite",
            report_file="reports/hardening-suite.json",
        )
        in MEMORY_LIFECYCLE_GATE_ACTION
    )
