from __future__ import annotations

from fastapi import APIRouter, Response, status

from reactor.core.settings import get_settings
from reactor.persistence.database import check_database
from reactor.persistence.redis_check import check_redis

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/actuator/health")
async def actuator_health() -> dict[str, str]:
    """Retained admin-console liveness boundary during the Python replatform."""
    return {"status": "UP"}


@router.get("/readyz")
async def readyz(response: Response) -> dict[str, object]:
    settings = get_settings()
    database = await check_database(settings.database_url, settings.database_required)
    redis = await check_redis(settings.redis_url, settings.effective_redis_required())
    ready = database.ok and redis.ok
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready else "not_ready",
        "checks": {
            "database": database.__dict__,
            "redis": redis.__dict__,
        },
    }
