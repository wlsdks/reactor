from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import Response

from reactor.observability.metrics import metrics_response

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics() -> Response:
    return metrics_response()
