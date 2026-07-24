from __future__ import annotations

from typing import Any, cast

import pytest

from reactor.api.app import (
    lifespan,
    start_alert_scheduler_if_enabled,
    start_prompt_lab_scheduler_if_enabled,
    start_scheduler_if_enabled,
    start_slack_reminder_scheduler_if_enabled,
    start_socket_mode_if_enabled,
)
from reactor.core.settings import Settings


class DefaultRunnerSentinel:
    pass


_DEFAULT_RUNNER = DefaultRunnerSentinel()
SLACK_TEST_APP_TOKEN = "xapp-test"  # noqa: S105


async def test_start_socket_mode_if_enabled_skips_disabled_setting() -> None:
    container = FakeContainer(
        Settings(slack_socket_mode_enabled=False, slack_app_token=SLACK_TEST_APP_TOKEN)
    )

    runner = await start_socket_mode_if_enabled(container)

    assert runner is None
    assert container.factory_calls == 0


async def test_start_socket_mode_if_enabled_starts_runner_when_configured() -> None:
    container = FakeContainer(
        Settings(slack_socket_mode_enabled=True, slack_app_token=SLACK_TEST_APP_TOKEN)
    )

    runner = await start_socket_mode_if_enabled(container)
    assert runner is not None
    await runner.close()

    assert isinstance(runner, FakeSocketModeRunner)
    assert container.factory_calls == 1
    assert runner.started is True
    assert runner.closed is True


async def test_start_socket_mode_if_enabled_skips_when_factory_is_unavailable() -> None:
    container = FakeContainer(
        Settings(slack_socket_mode_enabled=True, slack_app_token=SLACK_TEST_APP_TOKEN),
        runner=None,
    )

    runner = await start_socket_mode_if_enabled(container)

    assert runner is None
    assert container.factory_calls == 1


async def test_start_scheduler_if_enabled_starts_runner_when_configured() -> None:
    container = FakeContainer(
        Settings(
            scheduler_enabled=True,
            scheduler_poll_interval_seconds=0.01,
            slack_app_token=SLACK_TEST_APP_TOKEN,
        )
    )

    runner = await start_scheduler_if_enabled(container)
    assert runner is not None
    await runner.close()

    assert isinstance(runner, FakeSchedulerRunner)
    assert container.scheduler_factory_calls == 1
    assert runner.started is True
    assert runner.closed is True


async def test_start_scheduler_if_enabled_skips_disabled_setting() -> None:
    container = FakeContainer(Settings(scheduler_enabled=False))

    runner = await start_scheduler_if_enabled(container)

    assert runner is None
    assert container.scheduler_factory_calls == 0


async def test_start_alert_scheduler_if_enabled_starts_runner_when_configured() -> None:
    container = FakeContainer(
        Settings(
            alert_scheduler_enabled=True,
            alert_scheduler_interval_seconds=0.01,
        )
    )

    runner = await start_alert_scheduler_if_enabled(container)
    assert runner is not None
    await runner.close()

    assert isinstance(runner, FakeAlertSchedulerRunner)
    assert container.alert_scheduler_factory_calls == 1
    assert runner.started is True
    assert runner.closed is True


async def test_start_alert_scheduler_if_enabled_skips_disabled_setting() -> None:
    container = FakeContainer(Settings(alert_scheduler_enabled=False))

    runner = await start_alert_scheduler_if_enabled(container)

    assert runner is None
    assert container.alert_scheduler_factory_calls == 0


async def test_start_prompt_lab_scheduler_if_enabled_starts_runner_when_configured() -> None:
    container = FakeContainer(
        Settings(
            prompt_lab_scheduler_enabled=True,
            prompt_lab_scheduler_interval_seconds=0.01,
        )
    )

    runner = await start_prompt_lab_scheduler_if_enabled(container)
    assert runner is not None
    await runner.close()

    assert isinstance(runner, FakePromptLabSchedulerRunner)
    assert container.prompt_lab_scheduler_factory_calls == 1
    assert runner.started is True
    assert runner.closed is True


async def test_start_prompt_lab_scheduler_if_enabled_skips_disabled_setting() -> None:
    container = FakeContainer(Settings(prompt_lab_scheduler_enabled=False))

    runner = await start_prompt_lab_scheduler_if_enabled(container)

    assert runner is None
    assert container.prompt_lab_scheduler_factory_calls == 0


async def test_start_slack_reminder_scheduler_if_enabled_starts_runner_when_configured() -> None:
    container = FakeContainer(
        Settings(
            slack_reminder_scheduler_enabled=True,
            slack_reminder_scheduler_interval_seconds=0.01,
        )
    )

    runner = await start_slack_reminder_scheduler_if_enabled(container)
    assert runner is not None
    await runner.close()

    assert isinstance(runner, FakeSlackReminderSchedulerRunner)
    assert container.slack_reminder_scheduler_factory_calls == 1
    assert runner.started is True
    assert runner.closed is True


async def test_start_slack_reminder_scheduler_if_enabled_skips_disabled_setting() -> None:
    container = FakeContainer(Settings(slack_reminder_scheduler_enabled=False))

    runner = await start_slack_reminder_scheduler_if_enabled(container)

    assert runner is None
    assert container.slack_reminder_scheduler_factory_calls == 0


async def test_lifespan_configures_tracing_before_opening_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    settings = Settings(observability_tracing_enabled=True, observability_trace_exporter="console")
    app = FakeApp()
    container = FakeOpenContainer(settings)

    def fake_get_settings() -> Settings:
        calls.append("settings")
        return settings

    def fake_configure_tracing(configured_settings: Settings) -> None:
        assert configured_settings is settings
        calls.append("tracing")

    async def fake_open(configured_settings: Settings) -> FakeOpenContainer:
        assert configured_settings is settings
        calls.append("open")
        return container

    monkeypatch.setattr("reactor.api.app.get_settings", fake_get_settings)
    monkeypatch.setattr("reactor.api.app.configure_tracing", fake_configure_tracing)
    monkeypatch.setattr("reactor.api.app.AppContainer.open", fake_open)

    async with lifespan(cast(Any, app)):
        assert app.state.reactor is container

    assert calls == ["settings", "tracing", "open"]
    assert container.closed is True


async def test_lifespan_shutdown_closes_tracing_after_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    settings = Settings(observability_tracing_enabled=True, observability_trace_exporter="console")
    app = FakeApp()
    container = FakeOpenContainer(settings)

    def fake_get_settings() -> Settings:
        calls.append("settings")
        return settings

    def fake_configure_tracing(configured_settings: Settings) -> None:
        assert configured_settings is settings
        calls.append("tracing_open")

    async def fake_open(configured_settings: Settings) -> FakeOpenContainer:
        assert configured_settings is settings
        calls.append("container_open")
        return container

    async def fake_close() -> None:
        calls.append("container_close")
        container.closed = True

    def fake_shutdown_tracing() -> None:
        assert container.closed is True
        calls.append("tracing_shutdown")

    monkeypatch.setattr("reactor.api.app.get_settings", fake_get_settings)
    monkeypatch.setattr("reactor.api.app.configure_tracing", fake_configure_tracing)
    monkeypatch.setattr("reactor.api.app.shutdown_tracing", fake_shutdown_tracing, raising=False)
    monkeypatch.setattr("reactor.api.app.AppContainer.open", fake_open)
    monkeypatch.setattr(container, "close", fake_close)

    async with lifespan(cast(Any, app)):
        assert app.state.reactor is container

    assert calls == [
        "settings",
        "tracing_open",
        "container_open",
        "container_close",
        "tracing_shutdown",
    ]


class FakeContainer:
    def __init__(
        self,
        settings: Settings,
        runner: FakeSocketModeRunner | None | DefaultRunnerSentinel = _DEFAULT_RUNNER,
    ) -> None:
        self.settings = settings
        self._runner: FakeSocketModeRunner | None
        self._runner = (
            FakeSocketModeRunner() if isinstance(runner, DefaultRunnerSentinel) else runner
        )
        self.factory_calls = 0
        self.scheduler_factory_calls = 0
        self.alert_scheduler_factory_calls = 0
        self.prompt_lab_scheduler_factory_calls = 0
        self.slack_reminder_scheduler_factory_calls = 0

    def slack_socket_mode_runner(self) -> FakeSocketModeRunner | None:
        self.factory_calls += 1
        return self._runner

    def scheduler_runner(self) -> FakeSchedulerRunner:
        self.scheduler_factory_calls += 1
        return FakeSchedulerRunner()

    def alert_scheduler(self) -> FakeAlertSchedulerRunner:
        self.alert_scheduler_factory_calls += 1
        return FakeAlertSchedulerRunner()

    def prompt_lab_scheduler_runner(self) -> FakePromptLabSchedulerRunner:
        self.prompt_lab_scheduler_factory_calls += 1
        return FakePromptLabSchedulerRunner()

    def slack_reminder_scheduler_runner(self) -> FakeSlackReminderSchedulerRunner:
        self.slack_reminder_scheduler_factory_calls += 1
        return FakeSlackReminderSchedulerRunner()


class FakeSocketModeRunner:
    def __init__(self) -> None:
        self.started = False
        self.closed = False

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True


class FakeSchedulerRunner:
    def __init__(self) -> None:
        self.started = False
        self.closed = False

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True


class FakeAlertSchedulerRunner:
    def __init__(self) -> None:
        self.started = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True


class FakePromptLabSchedulerRunner:
    def __init__(self) -> None:
        self.started = False
        self.closed = False

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True


class FakeSlackReminderSchedulerRunner:
    def __init__(self) -> None:
        self.started = False
        self.closed = False

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True


class FakeState:
    reactor: object | None = None


class FakeApp:
    def __init__(self) -> None:
        self.state = FakeState()


class FakeOpenContainer(FakeContainer):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.closed = False

    async def close(self) -> None:
        self.closed = True
