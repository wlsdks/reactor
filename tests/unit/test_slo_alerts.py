from __future__ import annotations

import pytest

from reactor.observability.alerts import (
    AlertEvaluationResult,
    AlertEvaluator,
    AlertInstance,
    AlertMetricSnapshot,
    AlertRule,
    AlertScheduler,
    AlertSchedulerConfig,
    AlertSeverity,
    AlertStatus,
    AlertType,
    AsyncAlertEvaluator,
    Baseline,
    ErrorBudget,
    InMemoryAlertRuleStore,
)


def test_static_threshold_evaluator_creates_active_alert_once() -> None:
    store = InMemoryAlertRuleStore(
        metrics={"tenant_1": {"error_rate": 0.12}},
        rules=[
            AlertRule(
                id="rule_1",
                tenant_id="tenant_1",
                name="High error rate",
                type=AlertType.STATIC_THRESHOLD,
                severity=AlertSeverity.CRITICAL,
                metric="error_rate",
                threshold=0.05,
            )
        ],
    )

    first = AlertEvaluator(store).evaluate_all()
    second = AlertEvaluator(store).evaluate_all()

    assert len(first) == 1
    assert second == []
    assert store.find_active_alerts()[0].message == (
        "High error rate: error_rate = 0.1200 (threshold: 0.05)"
    )


def test_alert_store_resolves_alert_and_filters_tenant_rules() -> None:
    store = InMemoryAlertRuleStore(
        rules=[
            AlertRule(id="tenant_rule", tenant_id="tenant_1", name="Tenant", metric="latency_p99"),
            AlertRule(
                id="platform_rule",
                tenant_id=None,
                name="Platform",
                metric="pipeline_buffer_usage",
                platform_only=True,
            ),
        ]
    )
    alert = store.save_alert(
        AlertEvaluator(store).alert_for_rule(
            store.find_rules_for_tenant("tenant_1")[0],
            metric_value=100,
        )
    )

    assert [rule.id for rule in store.find_rules_for_tenant("tenant_1")] == ["tenant_rule"]
    assert [rule.id for rule in store.find_platform_rules()] == ["platform_rule"]
    assert store.resolve_alert(alert.id, tenant_id="tenant_2", actor="admin_2") is False
    assert store.find_active_alerts(tenant_id="tenant_1") == [alert]
    assert store.resolve_alert(alert.id, tenant_id="tenant_1", actor="admin_1") is True
    assert store.find_active_alerts(tenant_id="tenant_1") == []
    assert store.alerts[alert.id].status == AlertStatus.RESOLVED
    assert store.alerts[alert.id].acknowledged_by == "admin_1"
    assert store.delete_rule("tenant_rule", tenant_id="tenant_2") is False
    assert "tenant_rule" in store.rules
    assert store.delete_rule("tenant_rule", tenant_id="tenant_1") is True
    assert "tenant_rule" not in store.rules


def test_baseline_anomaly_fires_when_current_value_exceeds_sigma_threshold() -> None:
    store = InMemoryAlertRuleStore(
        baselines={"tenant_1": {"hourly_cost": Baseline(mean=10.0, std_dev=2.0, sample_count=168)}},
        metrics={"tenant_1": {"hourly_cost": 25.0}},
        rules=[
            AlertRule(
                id="rule_anomaly",
                tenant_id="tenant_1",
                name="Cost anomaly",
                type=AlertType.BASELINE_ANOMALY,
                metric="hourly_cost",
                threshold=3.0,
                window_minutes=60,
            )
        ],
    )

    created = AlertEvaluator(store).evaluate_all()

    assert len(created) == 1
    assert created[0].metric_value == 25.0
    assert created[0].threshold == 16.0
    assert "baseline" in created[0].message


def test_baseline_anomaly_does_not_fire_without_baseline() -> None:
    store = InMemoryAlertRuleStore(
        metrics={"tenant_1": {"hourly_cost": 25.0}},
        rules=[
            AlertRule(
                id="rule_anomaly",
                tenant_id="tenant_1",
                name="Cost anomaly",
                type=AlertType.BASELINE_ANOMALY,
                metric="hourly_cost",
                threshold=3.0,
            )
        ],
    )

    assert AlertEvaluator(store).evaluate_all() == []


def test_error_budget_burn_rate_fires_when_burn_rate_exceeds_threshold() -> None:
    store = InMemoryAlertRuleStore(
        error_budgets={
            "tenant_1": ErrorBudget(
                slo_target=0.995,
                total_requests=10_000,
                failed_requests=200,
                current_availability=0.98,
                budget_total=50,
                budget_consumed=200,
                budget_remaining=0.0,
                burn_rate=4.0,
            )
        },
        rules=[
            AlertRule(
                id="rule_burn",
                tenant_id="tenant_1",
                name="Fast burn",
                type=AlertType.ERROR_BUDGET_BURN_RATE,
                metric="burn_rate",
                threshold=2.0,
                window_minutes=60,
            )
        ],
    )

    created = AlertEvaluator(store).evaluate_all()

    assert len(created) == 1
    assert created[0].metric_value == 4.0
    assert created[0].threshold == 2.0
    assert "burn_rate" in created[0].message


def test_metric_snapshot_supports_static_threshold_sources() -> None:
    snapshot = AlertMetricSnapshot(
        metrics={"tenant_1": {"mcp_consecutive_failures": 5.0}},
        baselines={},
        error_budgets={},
    )
    rule = AlertRule(
        tenant_id="tenant_1",
        name="MCP failures",
        metric="mcp_consecutive_failures",
        threshold=3.0,
    )

    assert snapshot.metric_value(rule) == 5.0


async def test_async_alert_evaluator_dispatches_new_alerts_once() -> None:
    store = InMemoryAlertRuleStore(
        metrics={"tenant_1": {"error_rate": 0.12}},
        rules=[
            AlertRule(
                id="rule_1",
                tenant_id="tenant_1",
                name="High error rate",
                type=AlertType.STATIC_THRESHOLD,
                severity=AlertSeverity.CRITICAL,
                metric="error_rate",
                threshold=0.05,
            )
        ],
    )
    dispatcher = RecordingAlertDispatcher()
    evaluator = AsyncAlertEvaluator(store, dispatcher=dispatcher)

    first = await evaluator.evaluate_all()
    second = await evaluator.evaluate_all()

    assert len(first.created_alerts) == 1
    assert len(first.dispatched_alerts) == 1
    assert second.created_alerts == []
    assert second.dispatched_alerts == []
    assert [alert.rule_id for alert in dispatcher.alerts] == ["rule_1"]


async def test_async_alert_evaluator_keeps_alert_and_logs_safely_when_dispatch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warning_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def record_warning(*args: object, **kwargs: object) -> None:
        warning_calls.append((args, kwargs))

    monkeypatch.setattr("reactor.observability.alerts.logger.warning", record_warning)
    store = InMemoryAlertRuleStore(
        metrics={"tenant_1": {"error_rate": 0.12}},
        rules=[
            AlertRule(
                id="rule_1",
                tenant_id="tenant_1",
                name="High error rate",
                type=AlertType.STATIC_THRESHOLD,
                severity=AlertSeverity.CRITICAL,
                metric="error_rate",
                threshold=0.05,
            )
        ],
    )
    evaluator = AsyncAlertEvaluator(store, dispatcher=FailingAlertDispatcher())

    result = await evaluator.evaluate_all()

    assert [alert.rule_id for alert in result.created_alerts] == ["rule_1"]
    assert result.dispatched_alerts == []
    assert [alert.rule_id for alert in store.find_active_alerts()] == ["rule_1"]
    assert warning_calls == [
        (
            ("alert_notification_dispatch_failed",),
            {
                "extra": {
                    "alert_id": result.created_alerts[0].id,
                    "rule_id": "rule_1",
                }
            },
        )
    ]
    assert "private-storage-detail" not in repr(warning_calls)


async def test_async_alert_evaluator_supports_async_store_methods() -> None:
    store = AsyncAlertStore(
        metrics={"tenant_1": {"hourly_cost": 25.0}},
        baselines={"tenant_1": {"hourly_cost": Baseline(mean=10.0, std_dev=2.0, sample_count=168)}},
        rules=[
            AlertRule(
                id="rule_anomaly",
                tenant_id="tenant_1",
                name="Cost anomaly",
                type=AlertType.BASELINE_ANOMALY,
                metric="hourly_cost",
                threshold=3.0,
            )
        ],
    )

    result = await AsyncAlertEvaluator(store).evaluate_all()

    assert len(result.created_alerts) == 1
    assert result.created_alerts[0].threshold == 16.0
    assert store.saved_count == 1


async def test_alert_scheduler_run_once_resets_and_tracks_failures() -> None:
    failing = AlertScheduler(FailingAlertEvaluator())

    try:
        await failing.run_once()
    except RuntimeError:
        pass

    assert failing.consecutive_failures == 1
    assert failing.last_error == "RuntimeError: boom"

    successful = AlertScheduler(
        StaticAlertEvaluator(),
        config=AlertSchedulerConfig(interval_seconds=0.01, initial_delay_seconds=0),
    )
    result = await successful.run_once()

    assert isinstance(result, AlertEvaluationResult)
    assert successful.consecutive_failures == 0
    assert successful.last_result == result


class RecordingAlertDispatcher:
    def __init__(self) -> None:
        self.alerts: list[AlertInstance] = []

    async def dispatch(self, alert: AlertInstance) -> None:
        self.alerts.append(alert)


class FailingAlertDispatcher:
    async def dispatch(self, alert: AlertInstance) -> None:
        del alert
        raise RuntimeError("pager unavailable: private-storage-detail")


class AsyncAlertStore:
    def __init__(
        self,
        *,
        rules: list[AlertRule],
        metrics: dict[str, dict[str, float]] | None = None,
        baselines: dict[str, dict[str, Baseline]] | None = None,
        error_budgets: dict[str, ErrorBudget] | None = None,
    ) -> None:
        self.store = InMemoryAlertRuleStore(
            rules=rules,
            metrics=metrics,
            baselines=baselines,
            error_budgets=error_budgets,
        )
        self.saved_count = 0

    async def find_all_rules(self) -> list[AlertRule]:
        return self.store.find_all_rules()

    async def find_active_alerts(self) -> list[AlertInstance]:
        return self.store.find_active_alerts()

    async def save_alert(self, alert: AlertInstance) -> AlertInstance:
        self.saved_count += 1
        return self.store.save_alert(alert)

    async def metric_value(self, rule: AlertRule) -> float | None:
        return self.store.metric_value(rule)

    async def baseline(self, tenant_id: str, metric: str) -> Baseline | None:
        return self.store.baseline(tenant_id, metric)

    async def error_budget(self, tenant_id: str) -> ErrorBudget | None:
        return self.store.error_budget(tenant_id)


class FailingAlertEvaluator:
    async def evaluate_all(self) -> AlertEvaluationResult:
        raise RuntimeError("boom")


class StaticAlertEvaluator:
    async def evaluate_all(self) -> AlertEvaluationResult:
        return AlertEvaluationResult(
            created_alerts=[],
            active_alerts=[],
            dispatched_alerts=[],
        )
