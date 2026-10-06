from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from services.alert_service.app.core.store import clear_state, evaluate_event
from services.alert_service.app.main import app
from services.alert_service.app.models.alert import MonitoringPreferences, TelemetryEvent

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_alert_state() -> None:
    clear_state()


@pytest.fixture(autouse=True)
def stub_vehicle_preferences(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.alert_service.app.main.get_monitoring_preferences",
        lambda vehicle_id, request_id=None: MonitoringPreferences(),
    )


def test_health_and_request_id() -> None:
    response = client.get("/health/ready", headers={"X-Request-ID": "alert-test-1"})
    assert response.status_code == 200
    assert response.json() == {"status": "UP"}
    assert response.headers["X-Request-ID"] == "alert-test-1"


def test_evaluates_over_threshold_telemetry() -> None:
    response = client.post(
        "/alerts/evaluate",
        json={
            "vehicle_id": "VW-1001",
            "speed": 150,
            "rpm": 3200,
            "battery_temperature": 38.5,
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert len(result["new_alerts"]) == 1
    assert result["new_alerts"][0]["rule"] == "speed_high"
    assert result["new_alerts"][0]["severity"] == "warning"
    assert len(result["active_alerts"]) == 1
    listed = client.get("/alerts", params={"vehicle_id": "VW-1001"})
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_extreme_telemetry_is_critical() -> None:
    response = client.post(
        "/alerts/evaluate",
        json={
            "vehicle_id": "VW-1002",
            "speed": 170,
            "rpm": 3200,
            "battery_temperature": 38.5,
        },
    )
    assert response.status_code == 200
    assert response.json()["new_alerts"][0]["severity"] == "critical"


def test_safe_telemetry_creates_no_alerts() -> None:
    response = client.post(
        "/alerts/evaluate",
        json={
            "vehicle_id": "VW-1001",
            "speed": 82,
            "rpm": 3200,
            "battery_temperature": 38.5,
        },
    )
    assert response.status_code == 200
    assert response.json()["new_alerts"] == []
    assert response.json()["active_alerts"] == []


def test_rejects_invalid_telemetry() -> None:
    response = client.post(
        "/alerts/evaluate",
        json={
            "vehicle_id": "VW-1001",
            "speed": -1,
            "rpm": 3200,
            "battery_temperature": 38.5,
        },
    )
    assert response.status_code == 422


def test_metrics_are_exposed() -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "alerts_created_total" in response.text


def test_temperature_alert_waits_for_configured_duration_then_clears() -> None:
    preferences = MonitoringPreferences(battery_temperature_duration_seconds=3600)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    hot_event = TelemetryEvent(
        vehicle_id="LONG-TEST",
        speed=80,
        rpm=3000,
        battery_temperature=60,
    )

    pending = evaluate_event(hot_event, preferences, start)
    assert pending.pending_conditions[0].remaining_seconds == 3600
    assert pending.active_alerts == []

    still_pending = evaluate_event(
        hot_event,
        preferences,
        start + timedelta(minutes=59),
    )
    assert still_pending.pending_conditions[0].remaining_seconds == 60
    assert still_pending.new_alerts == []

    triggered = evaluate_event(
        hot_event,
        preferences,
        start + timedelta(hours=1),
    )
    assert len(triggered.new_alerts) == 1
    assert triggered.new_alerts[0].rule == "battery_temperature_high"

    recovered = evaluate_event(
        TelemetryEvent(
            vehicle_id="LONG-TEST",
            speed=80,
            rpm=3000,
            battery_temperature=45,
        ),
        preferences,
        start + timedelta(hours=1, minutes=1),
    )
    assert len(recovered.cleared_alerts) == 1
    assert recovered.cleared_alerts[0].status == "cleared"
    assert recovered.active_alerts == []


def test_unknown_vehicle_returns_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def unknown_vehicle(vehicle_id: str, request_id: str | None = None) -> MonitoringPreferences:
        raise KeyError(vehicle_id)

    monkeypatch.setattr(
        "services.alert_service.app.main.get_monitoring_preferences",
        unknown_vehicle,
    )
    response = client.post(
        "/alerts/evaluate",
        json={
            "vehicle_id": "MISSING-1",
            "speed": 80,
            "rpm": 1000,
            "battery_temperature": 25,
        },
    )
    assert response.status_code == 404


def test_speed_150_is_safe_at_vehicle_limit_170_but_not_limit_140(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def preferences_for_vehicle(
        vehicle_id: str,
        request_id: str | None = None,
    ) -> MonitoringPreferences:
        return MonitoringPreferences(speed_limit_kmh=170 if vehicle_id == "FAST-LIMIT" else 140)

    monkeypatch.setattr(
        "services.alert_service.app.main.get_monitoring_preferences",
        preferences_for_vehicle,
    )
    reading = {"speed": 150, "rpm": 3000, "battery_temperature": 25}

    at_higher_limit = client.post(
        "/alerts/evaluate",
        json={"vehicle_id": "FAST-LIMIT", **reading},
    )
    at_default_limit = client.post(
        "/alerts/evaluate",
        json={"vehicle_id": "DEFAULT-LIMIT", **reading},
    )

    assert at_higher_limit.status_code == 200
    assert at_higher_limit.json()["new_alerts"] == []
    assert at_default_limit.status_code == 200
    assert at_default_limit.json()["new_alerts"][0]["threshold"] == 140


def test_acknowledge_closes_notice_but_keeps_alert_active_until_recovery() -> None:
    hot_response = client.post(
        "/alerts/evaluate",
        json={
            "vehicle_id": "ACK-TEST",
            "speed": 150,
            "rpm": 2000,
            "battery_temperature": 25,
        },
    )
    alert_id = hot_response.json()["new_alerts"][0]["alert_id"]

    acknowledged = client.post(f"/alerts/{alert_id}/acknowledge")
    assert acknowledged.status_code == 200
    assert acknowledged.json()["acknowledged"] is True
    assert len(client.get("/alerts/active", params={"vehicle_id": "ACK-TEST"}).json()) == 1

    recovered = client.post(
        "/alerts/evaluate",
        json={
            "vehicle_id": "ACK-TEST",
            "speed": 80,
            "rpm": 2000,
            "battery_temperature": 25,
        },
    )
    assert recovered.json()["cleared_alerts"][0]["status"] == "cleared"
    assert client.get("/alerts/active", params={"vehicle_id": "ACK-TEST"}).json() == []
