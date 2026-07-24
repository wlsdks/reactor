from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse, Response


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, reactor_http_exception_handler)


async def reactor_http_exception_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, HTTPException):
        raise exc
    if exc.status_code != status.HTTP_403_FORBIDDEN:
        return await http_exception_handler(request, exc)
    detail = exc.detail
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "detail": detail,
            "error": error_text(detail),
            "statusCode": exc.status_code,
            "code": "forbidden",
        },
    )


def error_text(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        detail_mapping = cast(Mapping[object, object], detail)
        value = (
            detail_mapping.get("error")
            or detail_mapping.get("message")
            or detail_mapping.get("detail")
        )
        if isinstance(value, str):
            return value
    return "Forbidden"
