from __future__ import annotations

from sqlalchemy.dialects import postgresql

from reactor.persistence.mcp_store import build_mcp_status_upsert_statement


def test_mcp_status_upsert_records_protocol_and_error_state() -> None:
    statement = build_mcp_status_upsert_statement(
        server_id="mcp_1",
        tenant_id="tenant_1",
        status="degraded",
        negotiated_protocol_version="2024-11-05",
        last_error="unsupported protocol",
    )

    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "INSERT INTO mcp_server_status" in sql
    assert "ON CONFLICT" in sql
    assert "negotiated_protocol_version" in sql
    assert "last_error" in sql
