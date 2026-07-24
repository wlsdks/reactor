# Contributing to Reactor

Reactor is a Python-first AI agent system built with FastAPI, LangGraph,
LangChain, PostgreSQL/pgvector, and Redis for ephemeral coordination.

Read `docs/architecture/python-langgraph-replatform-spec.md` before proposing
architecture, storage, security, protocol, or dependency changes.

## Reporting Issues

Include:

- Reactor version or commit
- Python version and operating system
- Exact command, request, or graph profile used
- Expected and actual behavior
- Relevant logs, traces, or HTTP responses with secrets redacted

Security issues must follow `SECURITY.md`.

## Development Setup

Prerequisites:

- Python 3.13.14
- uv 0.11.24 or newer compatible release
- Docker or another PostgreSQL/Redis local runtime for integration work

Common commands:

```bash
uv sync --all-extras --dev
uv lock --check
uv run ruff check
uv run ruff format --check
uv run pyright
uv run pytest
```

Local API smoke run:

```bash
uv run uvicorn reactor.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

## Contribution Rules

- Keep the serving path Python-only.
- Prefer framework-native LangGraph, LangChain, FastAPI, Pydantic, SQLAlchemy,
  Alembic, MCP SDK, A2A SDK, LangSmith, and OpenTelemetry behavior before adding
  custom framework layers.
- Preserve safety invariants: guards fail-close, hooks fail-open except
  cancellation, tool policy is deterministic code, and Redis is not durable state.
- Add focused tests for behavior changes.
- Add paired malicious and safe inputs for safety-sensitive changes.
- Update `AGENTS.md`, `CLAUDE.md`, and the architecture spec when commands,
  boundaries, dependencies, or safety policy change.

## Pull Requests

PRs should include:

- What changed and why
- Verification commands run
- Security impact when auth, tools, MCP, A2A, RAG, memory, sandboxing, secrets, or
  durable work are touched
- Cost impact when model calls, retries, context size, or eval volume increase
- Migration notes for schema, checkpoint, prompt, model, or state changes

Use Conventional Commits:

```text
feat: add run event replay API
fix: preserve tool-call message pairing during trimming
docs: update memory promotion policy
test: cover checkpoint resume
sec: tighten MCP tool approval policy
```

## License

By contributing, you agree that your contributions are licensed under the Apache
License 2.0.
