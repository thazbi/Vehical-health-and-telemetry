import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from services.vehicle_service.app.core.logging_config import configure_logger
from services.vehicle_service.app.core.metrics import (
    ACTIVE_REQUESTS,
    HTTP_REQUEST_LATENCY_SECONDS,
    HTTP_REQUESTS_FAILED_TOTAL,
    HTTP_REQUESTS_TOTAL,
    SERVICE_UP,
    get_metrics_payload,
)
from services.vehicle_service.app.core.store import VehicleStore
from services.vehicle_service.app.models.vehicle import MonitoringPreferences, Vehicle

app = FastAPI(title="Vehicle Service", version="0.1.0")
logger = configure_logger()
store = VehicleStore()


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        start_time = time.perf_counter()
        ACTIVE_REQUESTS.inc()

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            status_code = response.status_code
        except Exception:
            duration_seconds = time.perf_counter() - start_time
            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                path=route_path,
                status="500",
            ).inc()
            HTTP_REQUESTS_FAILED_TOTAL.labels(
                method=request.method,
                path=route_path,
                status="500",
            ).inc()
            HTTP_REQUEST_LATENCY_SECONDS.labels(
                method=request.method,
                path=route_path,
            ).observe(duration_seconds)
            raise
        finally:
            ACTIVE_REQUESTS.dec()

        duration_seconds = time.perf_counter() - start_time
        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            path=route_path,
            status=str(status_code),
        ).inc()
        HTTP_REQUEST_LATENCY_SECONDS.labels(
            method=request.method,
            path=route_path,
        ).observe(duration_seconds)
        if status_code >= 500:
            HTTP_REQUESTS_FAILED_TOTAL.labels(
                method=request.method,
                path=route_path,
                status=str(status_code),
            ).inc()

        logger.info(
            "request_processed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": route_path,
                "status_code": status_code,
                "duration_ms": round(duration_seconds * 1000, 2),
            },
        )
        return response


app.add_middleware(RequestIDMiddleware)


@app.get("/vehicles", response_model=list[Vehicle])
def list_vehicles() -> list[Vehicle]:
    return store.list_vehicles()


@app.post("/vehicles", response_model=Vehicle, status_code=201)
def create_vehicle(vehicle: Vehicle) -> Vehicle:
    try:
        return store.add_vehicle(vehicle)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.put("/vehicles/{vehicle_id}/preferences", response_model=Vehicle)
def update_vehicle_preferences(
    vehicle_id: str,
    preferences: MonitoringPreferences,
) -> Vehicle:
    vehicle = store.update_preferences(vehicle_id, preferences)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return vehicle


@app.get("/vehicles/{vehicle_id}", response_model=Vehicle)
def get_vehicle(vehicle_id: str) -> Vehicle:
    vehicle = store.get_vehicle(vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return vehicle


@app.get("/health/live")
def liveness() -> dict[str, str]:
    SERVICE_UP.set(1)
    return {"status": "UP"}


@app.get("/health/ready")
def readiness() -> dict[str, object]:
    service_status = "UP"
    dependencies: dict[str, str] = {}
    return {"status": service_status, "dependencies": dependencies}


@app.get("/metrics")
def metrics() -> Response:
    payload = get_metrics_payload()
    return Response(
        content=payload,
        media_type="text/plain; version=1.0; charset=utf-8",
    )
