import json
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from services.telemetry_service.app.core.logging_config import configure_logger
from services.telemetry_service.app.core.metrics import (
    ACTIVE_REQUESTS,
    DEPENDENCY_REQUEST_FAILURES_TOTAL,
    DEPENDENCY_REQUEST_TOTAL,
    HTTP_REQUEST_LATENCY_SECONDS,
    HTTP_REQUESTS_FAILED_TOTAL,
    HTTP_REQUESTS_TOTAL,
    SERVICE_UP,
    get_metrics_payload,
)
from services.telemetry_service.app.core.store import list_telemetry, store_telemetry
from services.telemetry_service.app.models.telemetry import TelemetryRecord
from services.telemetry_service.app.services.vehicle_client import (
    validate_vehicle_exists,
)

logger = configure_logger()
app = FastAPI(title="Telemetry Service", version="0.1.0")


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

        request.state.request_id = request_id
        logger.info(
            "request_processed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": round(duration_seconds * 1000, 2),
            },
        )
        return response


app.add_middleware(RequestIDMiddleware)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    request_id = getattr(
        request.state,
        "request_id",
        request.headers.get("X-Request-ID") or uuid.uuid4().hex,
    )
    payload = {
        "error": exc.detail if isinstance(exc.detail, str) else "HTTP_ERROR",
        "message": exc.detail if isinstance(exc.detail, str) else "Request failed",
        "request_id": request_id,
    }
    if isinstance(exc.detail, dict):
        payload["error"] = exc.detail.get("error", "HTTP_ERROR")
        payload["message"] = exc.detail.get("message", "Request failed")
    response = Response(
        content=json.dumps(payload),
        media_type="application/json",
        status_code=exc.status_code,
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> Response:
    request_id = getattr(
        request.state,
        "request_id",
        request.headers.get("X-Request-ID") or uuid.uuid4().hex,
    )
    payload = {
        "error": "VALIDATION_ERROR",
        "message": "Request validation failed",
        "request_id": request_id,
    }
    response = Response(
        content=json.dumps(payload),
        media_type="application/json",
        status_code=422,
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.post("/telemetry", status_code=201)
def create_telemetry(payload: TelemetryRecord, request: Request) -> TelemetryRecord:
    try:
        vehicle_exists = validate_vehicle_exists(
            payload.vehicle_id,
            request.state.request_id,
        )
    except RuntimeError as exc:
        DEPENDENCY_REQUEST_TOTAL.labels(
            dependency="vehicle_service",
            status="failure",
        ).inc()
        DEPENDENCY_REQUEST_FAILURES_TOTAL.labels(dependency="vehicle_service").inc()
        raise HTTPException(
            status_code=503,
            detail={
                "error": "DEPENDENCY_UNAVAILABLE",
                "message": str(exc),
            },
        ) from exc

    status = "success" if vehicle_exists else "failure"
    DEPENDENCY_REQUEST_TOTAL.labels(
        dependency="vehicle_service",
        status=status,
    ).inc()
    if not vehicle_exists:
        DEPENDENCY_REQUEST_FAILURES_TOTAL.labels(dependency="vehicle_service").inc()
        raise HTTPException(
            status_code=503,
            detail={
                "error": "DEPENDENCY_UNAVAILABLE",
                "message": "Vehicle service is currently unavailable",
            },
        )

    record = store_telemetry(payload)
    logger.info(
        "telemetry_processed",
        extra={
            "request_id": getattr(payload, "request_id", None),
            "vehicle_id": payload.vehicle_id,
        },
    )
    return record


@app.get("/telemetry/{vehicle_id}")
def get_telemetry(vehicle_id: str) -> list[TelemetryRecord]:
    return list_telemetry(vehicle_id)


@app.get("/health/live")
def liveness() -> dict[str, str]:
    SERVICE_UP.set(1)
    return {"status": "UP"}


@app.get("/health/ready")
def readiness(request: Request) -> Response:
    try:
        dependency_ok = validate_vehicle_exists(
            "VW-1001",
            request.state.request_id,
        )
    except RuntimeError:
        payload = {
            "status": "DOWN",
            "dependencies": {"vehicle_service": "DOWN"},
        }
        return JSONResponse(content=payload, status_code=503)

    dependency_state = "UP" if dependency_ok else "DOWN"
    payload = {
        "status": "UP" if dependency_ok else "DOWN",
        "dependencies": {"vehicle_service": dependency_state},
    }
    status_code = 200 if dependency_ok else 503
    return JSONResponse(content=payload, status_code=status_code)


@app.get("/metrics")
def metrics() -> Response:
    payload = get_metrics_payload()
    return Response(
        content=payload,
        media_type="text/plain; version=1.0; charset=utf-8",
    )
