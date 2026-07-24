from __future__ import annotations

from reactor.release.readiness_actions import release_readiness_command

MEMORY_LIFECYCLE_GATE_ACTION = (
    "uv run reactor-hardening-suite --report-file reports/hardening-suite.json "
    "&& uv run pytest "
    "tests/unit/test_rag_memory.py "
    "tests/unit/test_prompt_assembler.py "
    "tests/unit/test_context_manifest.py "
    "tests/integration/test_admin_api.py "
    "tests/integration/test_feedback_api.py "
    "-q -k memory "
    "&& uv run pytest "
    "tests/unit/test_memory_cli.py "
    "tests/unit/test_memory_lifecycle_actions.py "
    "-q -k 'memory_lifecycle or sensitive_recovery_actions or structured_error_body' "
    "&& REACTOR_TEST_POSTGRES=1 uv run pytest "
    "tests/integration/test_memory_postgres_lifecycle.py -q "
    "&& "
    + release_readiness_command(
        required_report="hardening_suite",
        report_file="reports/hardening-suite.json",
    )
)
