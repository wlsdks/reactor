from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["error-report"])
logger = logging.getLogger(__name__)


class ErrorReportRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    kind: str | None = Field(default=None, max_length=128)
    source: str | None = Field(default=None, max_length=128)
    message: str | None = Field(default=None, max_length=2000)
    stack: str | None = Field(default=None, max_length=10_000)
    url: str | None = Field(default=None, max_length=2000)
    user_agent: str | None = Field(default=None, alias="userAgent", max_length=512)
    timestamp: str | None = Field(default=None, max_length=64)
    context: dict[str, Any | None] | None = None


@router.post("/api/error-report", status_code=status.HTTP_204_NO_CONTENT)
async def receive_error_report(body: ErrorReportRequest | None = None) -> Response:
    report = body or ErrorReportRequest()
    logger.warning(
        "client_error_report: kind=%s source=%s message=%s",
        safe_log_field(report.kind, 64),
        safe_log_field(report.source, 64),
        safe_log_field(report.message, 500),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/error-report", status_code=status.HTTP_405_METHOD_NOT_ALLOWED)
async def error_report_get_not_allowed() -> Response:
    return Response(status_code=status.HTTP_405_METHOD_NOT_ALLOWED)


def safe_log_field(value: str | None, limit: int) -> str:
    return (value or "")[:limit]
