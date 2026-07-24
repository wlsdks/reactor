from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app


async def test_error_report_ports_legacy_post_only_no_content_contract() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        get_response = await client.get("/api/error-report")
        empty = await client.post("/api/error-report")
        populated = await client.post(
            "/api/error-report",
            json={
                "kind": "ui_error",
                "source": "admin-console",
                "message": "render failed",
                "stack": "trace",
                "url": "https://reactor.local/admin",
                "userAgent": "test",
                "timestamp": "2026-06-26T00:00:00Z",
                "context": {"route": "/admin"},
            },
        )

    assert get_response.status_code == 405
    assert empty.status_code == 204
    assert empty.content == b""
    assert populated.status_code == 204
    assert populated.content == b""


async def test_error_report_rejects_oversized_legacy_fields() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/error-report",
            json={"kind": "x" * 129, "message": "ok"},
        )

    assert response.status_code == 422
