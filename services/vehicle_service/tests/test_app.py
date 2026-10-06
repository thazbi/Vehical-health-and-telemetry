from fastapi.testclient import TestClient

from services.vehicle_service.app.main import app

client = TestClient(app)


def test_liveness_endpoint() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "UP"}


def test_readiness_endpoint() -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "UP"
    assert "dependencies" in payload


def test_list_vehicles() -> None:
    response = client.get("/vehicles")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 1
    assert payload[0]["vehicle_id"] == "VW-1001"


def test_get_vehicle_by_id() -> None:
    response = client.get("/vehicles/VW-1001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["vehicle_id"] == "VW-1001"
    assert payload["model"] == "ID.4"
    assert payload["status"] == "ACTIVE"


def test_register_vehicle_with_custom_monitoring_preferences() -> None:
    response = client.post(
        "/vehicles",
        json={
            "vehicle_id": "TEST-VEH-901",
            "model": "Touring EV",
            "status": "ACTIVE",
            "preferences": {
                "speed_limit_kmh": 110,
                "rpm_limit": 4200,
                "battery_temperature_limit_c": 44,
                "speed_duration_seconds": 0,
                "rpm_duration_seconds": 15,
                "battery_temperature_duration_seconds": 3600,
            },
        },
    )

    assert response.status_code == 201
    assert response.json()["preferences"]["speed_limit_kmh"] == 110
    assert client.get("/vehicles/TEST-VEH-901").status_code == 200


def test_duplicate_vehicle_registration_returns_conflict() -> None:
    vehicle = {
        "vehicle_id": "DUPLICATE-1",
        "model": "Test Model",
        "status": "ACTIVE",
    }
    assert client.post("/vehicles", json=vehicle).status_code == 201
    assert client.post("/vehicles", json=vehicle).status_code == 409


def test_update_vehicle_monitoring_preferences() -> None:
    response = client.put(
        "/vehicles/VW-1001/preferences",
        json={
            "speed_limit_kmh": 105,
            "rpm_limit": 4600,
            "battery_temperature_limit_c": 48,
            "speed_duration_seconds": 5,
            "rpm_duration_seconds": 10,
            "battery_temperature_duration_seconds": 30,
        },
    )
    assert response.status_code == 200
    assert response.json()["preferences"]["speed_limit_kmh"] == 105


def test_update_preferences_for_unknown_vehicle_returns_404() -> None:
    response = client.put(
        "/vehicles/MISSING-VEH/preferences",
        json={"speed_limit_kmh": 100},
    )
    assert response.status_code == 404


def test_metrics_endpoint() -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    text = response.text
    assert "service_up" in text
    assert "http_requests_total" in text


def test_request_id_header_is_reused() -> None:
    request_id = "test-request-id-123"
    response = client.get("/health/live", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
