import os

import httpx

from services.alert_service.app.models.alert import MonitoringPreferences

VEHICLE_SERVICE_URL = os.getenv("VEHICLE_SERVICE_URL", "http://vehicle-service:8000")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("SERVICE_TIMEOUT_SECONDS", "2"))


def get_monitoring_preferences(
    vehicle_id: str,
    request_id: str | None = None,
) -> MonitoringPreferences:
    headers = {"X-Request-ID": request_id} if request_id else {}
    try:
        response = httpx.get(
            f"{VEHICLE_SERVICE_URL}/vehicles/{vehicle_id}",
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code == 404:
            raise KeyError(vehicle_id)
        response.raise_for_status()
        vehicle = response.json()
        return MonitoringPreferences.model_validate(vehicle.get("preferences", {}))
    except httpx.HTTPError as exc:
        raise RuntimeError("Vehicle Service is unavailable") from exc
