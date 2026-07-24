from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from inspect import isawaitable
from typing import Protocol

from fastapi import FastAPI

from reactor import __version__
from reactor.a2a.server import mount_a2a_sdk_routes
from reactor.api.errors import install_error_handlers
from reactor.api.routers import (
    a2a,
    admin,
    agent_eval,
    agent_specs,
    approvals,
    auth,
    chat,
    documents,
    error_report,
    feedback,
    health,
    input_guard,
    input_guard_rules,
    intents,
    mcp,
    metrics,
    models,
    output_guard_rules,
    personas,
    prompt_lab,
    prompts,
    rag_ingestion_candidates,
    rag_ingestion_policy,
    rbac,
    runs,
    runtime_settings,
    scheduler,
    sessions,
    slack,
    tools,
    user_identities,
    user_memory,
)
from reactor.api.security import install_security_middleware
from reactor.core.container import AppContainer
from reactor.core.settings import Settings, get_settings
from reactor.observability.tracing import configure_tracing, shutdown_tracing


class SocketModeRunner(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...


class SchedulerRunnerProtocol(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...


class AlertSchedulerProtocol(Protocol):
    def start(self) -> object: ...

    async def close(self) -> None: ...


class PromptLabSchedulerRunnerProtocol(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...


class SlackReminderSchedulerRunnerProtocol(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...


class AsyncCloseable(Protocol):
    async def close(self) -> None: ...


class SocketModeContainer(Protocol):
    @property
    def settings(self) -> Settings: ...

    def slack_socket_mode_runner(self) -> SocketModeRunner | None: ...

    def scheduler_runner(self) -> SchedulerRunnerProtocol | None: ...

    def alert_scheduler(self) -> AlertSchedulerProtocol | None: ...

    def prompt_lab_scheduler_runner(self) -> PromptLabSchedulerRunnerProtocol | None: ...

    def slack_reminder_scheduler_runner(self) -> SlackReminderSchedulerRunnerProtocol | None: ...


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    configure_tracing(settings)
    container = await AppContainer.open(settings)
    app.state.reactor = container
    socket_mode_runner: SocketModeRunner | None = None
    scheduler_runner: SchedulerRunnerProtocol | None = None
    alert_scheduler: AlertSchedulerProtocol | None = None
    prompt_lab_scheduler_runner: PromptLabSchedulerRunnerProtocol | None = None
    slack_reminder_scheduler_runner: SlackReminderSchedulerRunnerProtocol | None = None
    try:
        socket_mode_runner = await start_socket_mode_if_enabled(container)
        scheduler_runner = await start_scheduler_if_enabled(container)
        alert_scheduler = await start_alert_scheduler_if_enabled(container)
        prompt_lab_scheduler_runner = await start_prompt_lab_scheduler_if_enabled(container)
        slack_reminder_scheduler_runner = await start_slack_reminder_scheduler_if_enabled(container)
        yield
    finally:
        try:
            await close_lifespan_resources(
                (
                    slack_reminder_scheduler_runner,
                    prompt_lab_scheduler_runner,
                    alert_scheduler,
                    scheduler_runner,
                    socket_mode_runner,
                    container,
                )
            )
        finally:
            shutdown_tracing()


async def close_lifespan_resources(resources: tuple[AsyncCloseable | None, ...]) -> None:
    first_error: Exception | None = None
    for resource in resources:
        if resource is None:
            continue
        try:
            await resource.close()
        except Exception as error:
            if first_error is None:
                first_error = error
    if first_error is not None:
        raise first_error


async def start_socket_mode_if_enabled(container: SocketModeContainer) -> SocketModeRunner | None:
    enabled = bool(getattr(container.settings, "slack_socket_mode_enabled", False))
    if not enabled:
        return None
    runner = container.slack_socket_mode_runner()
    if runner is None:
        return None
    await runner.start()
    return runner


async def start_scheduler_if_enabled(
    container: SocketModeContainer,
) -> SchedulerRunnerProtocol | None:
    enabled = bool(getattr(container.settings, "scheduler_enabled", False))
    if not enabled:
        return None
    runner = container.scheduler_runner()
    if runner is None:
        return None
    await runner.start()
    return runner


async def start_alert_scheduler_if_enabled(
    container: SocketModeContainer,
) -> AlertSchedulerProtocol | None:
    enabled = bool(getattr(container.settings, "alert_scheduler_enabled", False))
    if not enabled:
        return None
    runner = container.alert_scheduler()
    if runner is None:
        return None
    result = runner.start()
    if isawaitable(result):
        await result
    return runner


async def start_prompt_lab_scheduler_if_enabled(
    container: SocketModeContainer,
) -> PromptLabSchedulerRunnerProtocol | None:
    enabled = bool(getattr(container.settings, "prompt_lab_scheduler_enabled", False))
    if not enabled:
        return None
    runner = container.prompt_lab_scheduler_runner()
    if runner is None:
        return None
    await runner.start()
    return runner


async def start_slack_reminder_scheduler_if_enabled(
    container: SocketModeContainer,
) -> SlackReminderSchedulerRunnerProtocol | None:
    enabled = bool(getattr(container.settings, "slack_reminder_scheduler_enabled", False))
    if not enabled:
        return None
    runner = container.slack_reminder_scheduler_runner()
    if runner is None:
        return None
    await runner.start()
    return runner


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Reactor",
        version=__version__,
        lifespan=lifespan,
    )
    install_error_handlers(app)
    install_security_middleware(app, settings)
    app.state.reactor = AppContainer.local(settings)
    app.include_router(health.router)
    app.include_router(metrics.router)
    app.include_router(models.router)
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(agent_eval.router)
    app.include_router(agent_specs.router)
    app.include_router(chat.router)
    app.include_router(documents.router)
    app.include_router(error_report.router)
    app.include_router(feedback.router)
    app.include_router(input_guard.router)
    app.include_router(input_guard_rules.router)
    app.include_router(intents.router)
    app.include_router(output_guard_rules.router)
    app.include_router(personas.router)
    app.include_router(prompt_lab.router)
    app.include_router(prompts.router)
    app.include_router(rag_ingestion_candidates.router)
    app.include_router(rag_ingestion_policy.router)
    app.include_router(runs.router)
    app.include_router(sessions.router)
    app.include_router(user_identities.router)
    app.include_router(user_memory.router)
    app.include_router(approvals.router)
    app.include_router(mcp.router)
    app.include_router(mcp.legacy_router)
    app.include_router(a2a.router)
    app.include_router(runtime_settings.router)
    app.include_router(rbac.router)
    app.include_router(scheduler.router)
    app.include_router(slack.router)
    app.include_router(tools.router)
    mount_a2a_sdk_routes(app)
    return app
