FROM python:3.13.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANGGRAPH_STRICT_MSGPACK=true

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin reactor

COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md .python-version ./
COPY src/ src/
COPY langgraph.json ./

RUN uv sync --frozen --no-dev

USER reactor

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD /app/.venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"

CMD ["/app/.venv/bin/uvicorn", "reactor.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
