import pytest
from fastapi.testclient import TestClient

from services.telemetry_service.app.main import app
from services.telemetry_service.app.models.telemetry import TelemetryRecord

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_store() -> None:
    from services.telemetry_service.app.core.store import telemetry_store

    telemetry_store.clear()
    telemetry_store["VW-1001"] = [
        TelemetryRecord(
            vehicle_id="VW-1001",
            speed=82,
            rpm=3200,
            battery_temperature=38.5,
        )
    ]


def test_liveness_endpoint() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "UP"}


def test_readiness_endpoint_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.telemetry_service.app.main.validate_vehicle_exists",
        lambda vehicle_id, request_id=None: True,
    )

    response = client.get("/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "UP"
    assert payload["dependencies"]["vehicle_service"] == "UP"


def test_post_telemetry_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.telemetry_service.app.main.validate_vehicle_exists",
        lambda vehicle_id, request_id=None: True,
    )

    payload = {
        "vehicle_id": "VW-1001",
        "speed": 82,
        "rpm": 3200,
        "battery_temperature": 38.5,
    }

    response = client.post("/telemetry", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["vehicle_id"] == "VW-1001"
    assert body["speed"] == 82


def test_post_telemetry_invalid_speed() -> None:
    response = client.post(
        "/telemetry",
        json={
            "vehicle_id": "VW-1001",
            "speed": -1,
            "rpm": 3200,
            "battery_temperature": 38.5,
        },
    )

    assert response.status_code == 422


def test_post_telemetry_invalid_battery_temperature() -> None:
    response = client.post(
        "/telemetry",
        json={
            "vehicle_id": "VW-1001",
            "speed": 82,
            "rpm": 3200,
            "battery_temperature": 500,
        },
    )

    assert response.status_code == 422


def test_get_telemetry_by_vehicle() -> None:
    response = client.get("/telemetry/VW-1001")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert payload[0]["vehicle_id"] == "VW-1001"


def test_dependency_failure_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def faulty(vehicle_id: str, request_id: str | None = None) -> bool:
        raise RuntimeError("dependency down")

    monkeypatch.setattr("services.telemetry_service.app.main.validate_vehicle_exists", faulty)

    response = client.post(
        "/telemetry",
        json={
            "vehicle_id": "VW-1001",
            "speed": 82,
            "rpm": 3200,
            "battery_temperature": 38.5,
        },
    )

    assert response.status_code == 503
    assert response.json()["error"] == "DEPENDENCY_UNAVAILABLE"


def test_metrics_endpoint() -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "service_up" in response.text
    assert "http_requests_total" in response.text


def test_request_id_header_is_reused() -> None:
    request_id = "telemetry-request-456"
    response = client.get("/health/live", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id


def test_request_id_is_forwarded_to_vehicle_service(monkeypatch: pytest.MonkeyPatch) -> None:
    received_request_ids: list[str | None] = []

    def vehicle_exists(vehicle_id: str, request_id: str | None = None) -> bool:
        received_request_ids.append(request_id)
        return True

    monkeypatch.setattr(
        "services.telemetry_service.app.main.validate_vehicle_exists",
        vehicle_exists,
    )
    request_id = "forwarded-request-789"
    response = client.post(
        "/telemetry",
        headers={"X-Request-ID": request_id},
        json={
            "vehicle_id": "VW-1001",
            "speed": 82,
            "rpm": 3200,
            "battery_temperature": 38.5,
        },
    )

    assert response.status_code == 201
    assert response.headers["X-Request-ID"] == request_id
    assert received_request_ids == [request_id]
