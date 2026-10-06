from collections import deque
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from services.alert_service.app.models.alert import (
    Alert,
    EvaluationResult,
    MonitoringPreferences,
    PendingCondition,
    TelemetryEvent,
)
from services.alert_service.app.services.rules import evaluate_telemetry

MAX_ALERTS = 10000
_history: deque[Alert] = deque(maxlen=MAX_ALERTS)
_active: dict[tuple[str, str], Alert] = {}
_condition_started: dict[tuple[str, str], datetime] = {}
_lock = RLock()

RECOMMENDED_ACTIONS = {
    "speed_high": "Reduce speed when it is safe and follow local road conditions.",
    "rpm_high": "Ease off acceleration when safe and check the vehicle guidance if it persists.",
    "battery_temperature_high": (
        "Avoid heavy load; if the warning persists, stop in a safe place and follow "
        "the vehicle manufacturer's guidance."
    ),
}


def clear_state() -> None:
    with _lock:
        _history.clear()
        _active.clear()
        _condition_started.clear()


def evaluate_event(
    event: TelemetryEvent,
    preferences: MonitoringPreferences,
    observed_at: datetime | None = None,
) -> EvaluationResult:
    now = observed_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    breaches = evaluate_telemetry(event, preferences)
    breached_rules = {rule for rule, _, _, _ in breaches}
    new_alerts: list[Alert] = []
    cleared_alerts: list[Alert] = []
    pending: list[PendingCondition] = []

    with _lock:
        for rule, observed, threshold, duration in breaches:
            key = (event.vehicle_id, rule)
            started_at = _condition_started.setdefault(key, now)
            elapsed = max(0, int((now - started_at).total_seconds()))
            active = _active.get(key)
            if active is not None:
                _active[key] = active.model_copy(
                    update={"observed_value": observed, "updated_at": now}
                )
                continue
            if elapsed < duration:
                pending.append(
                    PendingCondition(
                        rule=rule,
                        vehicle_id=event.vehicle_id,
                        observed_value=observed,
                        threshold=threshold,
                        duration_seconds=duration,
                        elapsed_seconds=elapsed,
                        remaining_seconds=duration - elapsed,
                        started_at=started_at,
                    )
                )
                continue

            alert = Alert(
                alert_id=uuid4().hex,
                vehicle_id=event.vehicle_id,
                rule=rule,
                severity="critical" if observed > threshold * 1.2 else "warning",
                status="active",
                message=f"{rule.replace('_', ' ')} remains above its configured limit",
                recommended_action=RECOMMENDED_ACTIONS[rule],
                observed_value=observed,
                threshold=threshold,
                created_at=now,
                updated_at=now,
            )
            _active[key] = alert
            _history.append(alert)
            new_alerts.append(alert)

        for key in list(_condition_started):
            if key[0] != event.vehicle_id or key[1] in breached_rules:
                continue
            _condition_started.pop(key, None)
            active = _active.pop(key, None)
            if active is None:
                continue
            cleared = active.model_copy(
                update={
                    "status": "cleared",
                    "message": f"{key[1].replace('_', ' ')} returned below its configured limit",
                    "updated_at": now,
                    "cleared_at": now,
                }
            )
            _history.append(cleared)
            cleared_alerts.append(cleared)

        active_alerts = [
            alert.model_copy(deep=True)
            for (vehicle_id, _), alert in _active.items()
            if vehicle_id == event.vehicle_id
        ]

    return EvaluationResult(
        vehicle_id=event.vehicle_id,
        active_alerts=active_alerts,
        new_alerts=new_alerts,
        cleared_alerts=cleared_alerts,
        pending_conditions=pending,
    )


def list_alerts(vehicle_id: str | None = None) -> list[Alert]:
    with _lock:
        alerts = list(_history)
    if vehicle_id is not None:
        alerts = [alert for alert in alerts if alert.vehicle_id == vehicle_id]
    return [alert.model_copy(deep=True) for alert in alerts]


def list_active_alerts(vehicle_id: str | None = None) -> list[Alert]:
    with _lock:
        alerts = [
            alert.model_copy(deep=True)
            for (active_vehicle_id, _), alert in _active.items()
            if vehicle_id is None or active_vehicle_id == vehicle_id
        ]
    return alerts


def acknowledge_alert(alert_id: str) -> Alert | None:
    now = datetime.now(timezone.utc)
    with _lock:
        for key, alert in _active.items():
            if alert.alert_id != alert_id:
                continue
            acknowledged = alert.model_copy(
                update={
                    "acknowledged": True,
                    "acknowledged_at": now,
                    "updated_at": now,
                }
            )
            _active[key] = acknowledged
            history = [acknowledged if item.alert_id == alert_id else item for item in _history]
            _history.clear()
            _history.extend(history)
            return acknowledged.model_copy(deep=True)
    return None
