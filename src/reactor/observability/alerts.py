from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from reactor.kernel.ids import new_id

logger = logging.getLogger(__name__)


class AlertSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertType(StrEnum):
    STATIC_THRESHOLD = "STATIC_THRESHOLD"
    BASELINE_ANOMALY = "BASELINE_ANOMALY"
    ERROR_BUDGET_BURN_RATE = "ERROR_BUDGET_BURN_RATE"


class AlertStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


@dataclass(frozen=True)
class Baseline:
    mean: float
    std_dev: float
    sample_count: int

    @property
    def usable(self) -> bool:
        return self.sample_count >= 24


@dataclass(frozen=True)
class ErrorBudget:
    slo_target: float
    total_requests: int
    failed_requests: int
    current_availability: float
    budget_total: int
    budget_consumed: int
    budget_remaining: float
    burn_rate: float


@dataclass(frozen=True)
class AlertRule:
    name: str
    metric: str
    id: str = field(default_factory=lambda: new_id("alert_rule"))
    tenant_id: str | None = None
    description: str = ""
    type: AlertType = AlertType.STATIC_THRESHOLD
    severity: AlertSeverity = AlertSeverity.WARNING
    threshold: float = 0.0
    window_minutes: int = 15
    enabled: bool = True
    platform_only: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("id is required")
        if not self.name.strip():
            raise ValueError("name is required")
        if not self.metric.strip():
            raise ValueError("metric is required")
        if self.window_minutes <= 0:
            raise ValueError("window_minutes must be > 0")


@dataclass(frozen=True)
class AlertInstance:
    rule_id: str
    severity: AlertSeverity
    message: str
    id: str = field(default_factory=lambda: new_id("alert"))
    tenant_id: str | None = None
    status: AlertStatus = AlertStatus.ACTIVE
    metric_value: float = 0.0
    threshold: float = 0.0
    fired_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    acknowledged_by: str | None = None

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("id is required")
        if not self.rule_id.strip():
            raise ValueError("rule_id is required")
        if not self.message.strip():
            raise ValueError("message is required")


class AlertMetricSource(Protocol):
    def metric_value(self, rule: AlertRule) -> float | None: ...

    def baseline(self, tenant_id: str, metric: str) -> Baseline | None: ...

    def error_budget(self, tenant_id: str) -> ErrorBudget | None: ...


class AlertNotificationDispatcher(Protocol):
    def dispatch(self, alert: AlertInstance) -> object: ...


@dataclass(frozen=True)
class AlertMetricSnapshot:
    metrics: dict[str, dict[str, float]]
    baselines: dict[str, dict[str, Baseline]]
    error_budgets: dict[str, ErrorBudget]

    def metric_value(self, rule: AlertRule) -> float | None:
        scope = "platform" if rule.platform_only or rule.tenant_id is None else rule.tenant_id
        return self.metrics.get(scope, {}).get(rule.metric)

    def baseline(self, tenant_id: str, metric: str) -> Baseline | None:
        return self.baselines.get(tenant_id, {}).get(metric)

    def error_budget(self, tenant_id: str) -> ErrorBudget | None:
        return self.error_budgets.get(tenant_id)


class InMemoryAlertRuleStore:
    def __init__(
        self,
        *,
        rules: list[AlertRule] | None = None,
        alerts: list[AlertInstance] | None = None,
        metrics: dict[str, dict[str, float]] | None = None,
        baselines: dict[str, dict[str, Baseline]] | None = None,
        error_budgets: dict[str, ErrorBudget] | None = None,
    ) -> None:
        self.rules: dict[str, AlertRule] = {}
        self.alerts: dict[str, AlertInstance] = {}
        self.metric_snapshot = AlertMetricSnapshot(
            metrics=dict(metrics or {}),
            baselines=dict(baselines or {}),
            error_budgets=dict(error_budgets or {}),
        )
        for rule in rules or []:
            self.save_rule(rule)
        for alert in alerts or []:
            self.save_alert(alert)

    def find_rules_for_tenant(self, tenant_id: str) -> list[AlertRule]:
        return sorted(
            [rule for rule in self.rules.values() if rule.tenant_id == tenant_id],
            key=lambda rule: rule.created_at,
        )

    def find_platform_rules(self) -> list[AlertRule]:
        return sorted(
            [rule for rule in self.rules.values() if rule.tenant_id is None or rule.platform_only],
            key=lambda rule: rule.created_at,
        )

    def find_all_rules(self) -> list[AlertRule]:
        return sorted(self.rules.values(), key=lambda rule: rule.created_at)

    def save_rule(self, rule: AlertRule) -> AlertRule:
        rule.validate()
        self.rules[rule.id] = rule
        return rule

    def delete_rule(self, rule_id: str, *, tenant_id: str | None = None) -> bool:
        rule = self.rules.get(rule_id)
        if rule is None:
            return False
        if tenant_id is not None and rule.tenant_id != tenant_id:
            return False
        del self.rules[rule_id]
        return True

    def find_active_alerts(self, tenant_id: str | None = None) -> list[AlertInstance]:
        return sorted(
            [
                alert
                for alert in self.alerts.values()
                if alert.status == AlertStatus.ACTIVE
                and (tenant_id is None or alert.tenant_id == tenant_id)
            ],
            key=lambda alert: alert.fired_at,
        )

    def save_alert(self, alert: AlertInstance) -> AlertInstance:
        alert.validate()
        self.alerts[alert.id] = alert
        return alert

    def resolve_alert(
        self,
        alert_id: str,
        *,
        tenant_id: str | None = None,
        actor: str | None = None,
    ) -> bool:
        alert = self.alerts.get(alert_id)
        if alert is None:
            return False
        if tenant_id is not None and alert.tenant_id != tenant_id:
            return False
        self.alerts[alert_id] = AlertInstance(
            id=alert.id,
            rule_id=alert.rule_id,
            tenant_id=alert.tenant_id,
            severity=alert.severity,
            status=AlertStatus.RESOLVED,
            message=alert.message,
            metric_value=alert.metric_value,
            threshold=alert.threshold,
            fired_at=alert.fired_at,
            resolved_at=datetime.now(UTC),
            acknowledged_by=actor,
        )
        return True

    def metric_value(self, rule: AlertRule) -> float | None:
        return self.metric_snapshot.metric_value(rule)

    def baseline(self, tenant_id: str, metric: str) -> Baseline | None:
        return self.metric_snapshot.baseline(tenant_id, metric)

    def error_budget(self, tenant_id: str) -> ErrorBudget | None:
        return self.metric_snapshot.error_budget(tenant_id)


class AlertEvaluator:
    def __init__(self, alert_store: InMemoryAlertRuleStore) -> None:
        self._alert_store = alert_store

    def evaluate_all(self) -> list[AlertInstance]:
        active_rule_ids = {alert.rule_id for alert in self._alert_store.find_active_alerts()}
        created: list[AlertInstance] = []
        for rule in self._alert_store.find_all_rules():
            alert = self.evaluate(rule, active_rule_ids=active_rule_ids)
            if alert is not None:
                created.append(alert)
                active_rule_ids.add(rule.id)
        return created

    def evaluate(
        self,
        rule: AlertRule,
        *,
        active_rule_ids: set[str] | None = None,
    ) -> AlertInstance | None:
        if not rule.enabled or rule.id in (active_rule_ids or set()):
            return None
        alert = self._evaluate_rule(rule)
        if alert is None:
            return None
        return self._alert_store.save_alert(alert)

    def _evaluate_rule(self, rule: AlertRule) -> AlertInstance | None:
        match rule.type:
            case AlertType.STATIC_THRESHOLD:
                metric_value = self._alert_store.metric_value(rule)
                if metric_value is None or metric_value <= rule.threshold:
                    return None
                return self.alert_for_rule(rule, metric_value=metric_value)
            case AlertType.BASELINE_ANOMALY:
                tenant_id = rule.tenant_id
                if tenant_id is None:
                    return None
                baseline = self._alert_store.baseline(tenant_id, rule.metric)
                metric_value = self._alert_store.metric_value(rule)
                if baseline is None or not baseline.usable or metric_value is None:
                    return None
                anomaly_threshold = baseline.mean + rule.threshold * baseline.std_dev
                if metric_value <= anomaly_threshold:
                    return None
                return AlertInstance(
                    rule_id=rule.id,
                    tenant_id=rule.tenant_id,
                    severity=rule.severity,
                    message=(
                        f"{rule.name}: {metric_value:.4f} > baseline "
                        f"{baseline.mean:.4f} + {rule.threshold:g}σ"
                    ),
                    metric_value=metric_value,
                    threshold=anomaly_threshold,
                )
            case AlertType.ERROR_BUDGET_BURN_RATE:
                tenant_id = rule.tenant_id
                if tenant_id is None:
                    return None
                budget = self._alert_store.error_budget(tenant_id)
                if budget is None or budget.burn_rate <= rule.threshold:
                    return None
                return AlertInstance(
                    rule_id=rule.id,
                    tenant_id=rule.tenant_id,
                    severity=rule.severity,
                    message=(
                        f"{rule.name}: burn_rate = {budget.burn_rate:.2f}x "
                        f"(threshold: {rule.threshold:g}x)"
                    ),
                    metric_value=budget.burn_rate,
                    threshold=rule.threshold,
                )

    def alert_for_rule(self, rule: AlertRule, *, metric_value: float) -> AlertInstance:
        return AlertInstance(
            rule_id=rule.id,
            tenant_id=rule.tenant_id,
            severity=rule.severity,
            message=(
                f"{rule.name}: {rule.metric} = {metric_value:.4f} (threshold: {rule.threshold})"
            ),
            metric_value=metric_value,
            threshold=rule.threshold,
        )


async def maybe_await[T](value: Awaitable[T] | T) -> T:
    if inspect.isawaitable(value):
        return await value
    return value


@dataclass(frozen=True)
class AlertEvaluationResult:
    created_alerts: list[AlertInstance]
    active_alerts: list[AlertInstance]
    dispatched_alerts: list[AlertInstance]


class AlertEvaluationService(Protocol):
    async def evaluate_all(self) -> AlertEvaluationResult: ...


class AsyncAlertEvaluator:
    def __init__(
        self,
        alert_store: object,
        *,
        dispatcher: AlertNotificationDispatcher | None = None,
    ) -> None:
        self._alert_store = alert_store
        self._dispatcher = dispatcher

    async def evaluate_all(self) -> AlertEvaluationResult:
        before_alerts = await self._find_active_alerts()
        before_ids = {alert.id for alert in before_alerts}
        active_rule_ids = {alert.rule_id for alert in before_alerts}
        created: list[AlertInstance] = []
        for rule in await self._find_all_rules():
            alert = await self.evaluate(rule, active_rule_ids=active_rule_ids)
            if alert is not None:
                created.append(alert)
                active_rule_ids.add(rule.id)
        after_alerts = await self._find_active_alerts()
        dispatch_candidates = [alert for alert in after_alerts if alert.id not in before_ids]
        dispatched: list[AlertInstance] = []
        if self._dispatcher is not None:
            for alert in dispatch_candidates:
                try:
                    await maybe_await(self._dispatcher.dispatch(alert))
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.warning(
                        "alert_notification_dispatch_failed",
                        extra={"alert_id": alert.id, "rule_id": alert.rule_id},
                    )
                    continue
                dispatched.append(alert)
        else:
            dispatched = dispatch_candidates
        return AlertEvaluationResult(
            created_alerts=created,
            active_alerts=after_alerts,
            dispatched_alerts=dispatched,
        )

    async def evaluate(
        self,
        rule: AlertRule,
        *,
        active_rule_ids: set[str] | None = None,
    ) -> AlertInstance | None:
        if not rule.enabled or rule.id in (active_rule_ids or set()):
            return None
        alert = await self._evaluate_rule(rule)
        if alert is None:
            return None
        return await self._save_alert(alert)

    async def _evaluate_rule(self, rule: AlertRule) -> AlertInstance | None:
        match rule.type:
            case AlertType.STATIC_THRESHOLD:
                metric_value = await self._metric_value(rule)
                if metric_value is None or metric_value <= rule.threshold:
                    return None
                return AlertEvaluator(InMemoryAlertRuleStore()).alert_for_rule(
                    rule,
                    metric_value=metric_value,
                )
            case AlertType.BASELINE_ANOMALY:
                tenant_id = rule.tenant_id
                if tenant_id is None:
                    return None
                baseline = await self._baseline(tenant_id, rule.metric)
                metric_value = await self._metric_value(rule)
                if baseline is None or not baseline.usable or metric_value is None:
                    return None
                anomaly_threshold = baseline.mean + rule.threshold * baseline.std_dev
                if metric_value <= anomaly_threshold:
                    return None
                return AlertInstance(
                    rule_id=rule.id,
                    tenant_id=rule.tenant_id,
                    severity=rule.severity,
                    message=(
                        f"{rule.name}: {metric_value:.4f} > baseline "
                        f"{baseline.mean:.4f} + {rule.threshold:g}σ"
                    ),
                    metric_value=metric_value,
                    threshold=anomaly_threshold,
                )
            case AlertType.ERROR_BUDGET_BURN_RATE:
                tenant_id = rule.tenant_id
                if tenant_id is None:
                    return None
                budget = await self._error_budget(tenant_id)
                if budget is None or budget.burn_rate <= rule.threshold:
                    return None
                return AlertInstance(
                    rule_id=rule.id,
                    tenant_id=rule.tenant_id,
                    severity=rule.severity,
                    message=(
                        f"{rule.name}: burn_rate = {budget.burn_rate:.2f}x "
                        f"(threshold: {rule.threshold:g}x)"
                    ),
                    metric_value=budget.burn_rate,
                    threshold=rule.threshold,
                )

    async def _find_all_rules(self) -> list[AlertRule]:
        return await maybe_await(self._call_store("find_all_rules"))

    async def _find_active_alerts(self) -> list[AlertInstance]:
        return await maybe_await(self._call_store("find_active_alerts"))

    async def _save_alert(self, alert: AlertInstance) -> AlertInstance:
        return await maybe_await(self._call_store("save_alert", alert))

    async def _metric_value(self, rule: AlertRule) -> float | None:
        return await maybe_await(self._call_store("metric_value", rule))

    async def _baseline(self, tenant_id: str, metric: str) -> Baseline | None:
        return await maybe_await(self._call_store("baseline", tenant_id, metric))

    async def _error_budget(self, tenant_id: str) -> ErrorBudget | None:
        return await maybe_await(self._call_store("error_budget", tenant_id))

    def _call_store(self, name: str, *args: object) -> Any:
        method = getattr(self._alert_store, name)
        return method(*args)


@dataclass(frozen=True)
class AlertSchedulerConfig:
    interval_seconds: float = 60.0
    initial_delay_seconds: float | None = None


class AlertScheduler:
    def __init__(
        self,
        evaluator: AlertEvaluationService,
        *,
        config: AlertSchedulerConfig | None = None,
    ) -> None:
        self._evaluator = evaluator
        self._config = config or AlertSchedulerConfig()
        self._task: asyncio.Task[None] | None = None
        self.consecutive_failures = 0
        self.last_result: AlertEvaluationResult | None = None
        self.last_error: str | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._task = None

    async def close(self) -> None:
        await self.stop()

    async def run_once(self) -> AlertEvaluationResult:
        try:
            result = await self._evaluator.evaluate_all()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.consecutive_failures += 1
            self.last_error = f"{error.__class__.__name__}: {error}"
            raise
        self.consecutive_failures = 0
        self.last_error = None
        self.last_result = result
        return result

    async def _run_loop(self) -> None:
        delay = self._config.initial_delay_seconds
        if delay is None:
            delay = self._config.interval_seconds
        if delay > 0:
            await asyncio.sleep(delay)
        while True:
            with contextlib.suppress(Exception):
                await self.run_once()
            await asyncio.sleep(self._config.interval_seconds)
