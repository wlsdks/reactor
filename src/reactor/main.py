from __future__ import annotations

import uvicorn

from reactor.api.app import create_app
from reactor.core.settings import Settings

app = create_app()


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "reactor.api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


__all__ = ["app", "create_app", "main"]
