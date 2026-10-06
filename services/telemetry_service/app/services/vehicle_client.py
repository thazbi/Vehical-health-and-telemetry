import os
import time

import httpx

from services.telemetry_service.app.core.metrics import DEPENDENCY_REQUEST_DURATION_SECONDS

VEHICLE_SERVICE_URL = os.getenv("VEHICLE_SERVICE_URL", "http://vehicle-service:8000")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("SERVICE_TIMEOUT_SECONDS", "5"))


def validate_vehicle_exists(vehicle_id: str, request_id: str | None = None) -> bool:
    target_url = f"{VEHICLE_SERVICE_URL}/vehicles/{vehicle_id}"
    headers = {"X-Request-ID": request_id} if request_id else {}
    started_at = time.perf_counter()
    try:
        response = httpx.get(
            target_url,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code == 200:
            return True
        return False
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Vehicle service unavailable for {vehicle_id}") from exc
    finally:
        DEPENDENCY_REQUEST_DURATION_SECONDS.labels(dependency="vehicle_service").observe(
            time.perf_counter() - started_at
        )


def check_vehicle_service() -> str:
    try:
        response = httpx.get(f"{VEHICLE_SERVICE_URL}/vehicles", timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code == 200:
            return "UP"
        return "DOWN"
    except httpx.HTTPError:
        return "DOWN"
