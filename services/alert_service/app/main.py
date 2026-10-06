import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from services.alert_service.app.core.logging_config import configure_logger
from services.alert_service.app.core.metrics import (
    ACTIVE_REQUESTS,
    ALERTS_CREATED_TOTAL,
    HTTP_REQUEST_LATENCY_SECONDS,
    HTTP_REQUESTS_FAILED_TOTAL,
    HTTP_REQUESTS_TOTAL,
    SERVICE_UP,
    get_metrics_payload,
)
from services.alert_service.app.core.store import (
    acknowledge_alert,
    evaluate_event,
    list_active_alerts,
    list_alerts,
)
from services.alert_service.app.models.alert import Alert, EvaluationResult, TelemetryEvent
from services.alert_service.app.services.vehicle_client import get_monitoring_preferences

logger = configure_logger()
app = FastAPI(title="Alert Service", version="0.1.0")


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
        started_at = time.perf_counter()
        ACTIVE_REQUESTS.inc()
        try:
            response = await call_next(request)
        except Exception:
            self._record_request(request.method, route_path, "500", started_at)
            raise
        finally:
            ACTIVE_REQUESTS.dec()

        response.headers["X-Request-ID"] = request_id
        self._record_request(request.method, route_path, str(response.status_code), started_at)
        logger.info(
            "request_processed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": route_path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        return response

    @staticmethod
    def _record_request(method: str, path: str, status: str, started_at: float) -> None:
        HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
        HTTP_REQUEST_LATENCY_SECONDS.labels(method=method, path=path).observe(
            time.perf_counter() - started_at
        )
        if status.startswith("5"):
            HTTP_REQUESTS_FAILED_TOTAL.labels(method=method, path=path, status=status).inc()


app.add_middleware(RequestIDMiddleware)


@app.post("/alerts/evaluate", response_model=EvaluationResult, status_code=200)
def evaluate_telemetry_event(event: TelemetryEvent, request: Request) -> EvaluationResult:
    try:
        preferences = get_monitoring_preferences(
            event.vehicle_id,
            request.state.request_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Vehicle is not registered") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    result = evaluate_event(event, preferences)
    for alert in result.new_alerts:
        ALERTS_CREATED_TOTAL.labels(severity=alert.severity).inc()
    logger.info(
        "telemetry_evaluated",
        extra={
            "vehicle_id": event.vehicle_id,
            "alert_count": len(result.new_alerts),
            "active_alert_count": len(result.active_alerts),
            "pending_condition_count": len(result.pending_conditions),
        },
    )
    return result


@app.get("/alerts", response_model=list[Alert])
def get_alerts(vehicle_id: str | None = None) -> list[Alert]:
    return list_alerts(vehicle_id)


@app.get("/alerts/active", response_model=list[Alert])
def get_active_alerts(vehicle_id: str | None = None) -> list[Alert]:
    return list_active_alerts(vehicle_id)


@app.post("/alerts/{alert_id}/acknowledge", response_model=Alert)
def acknowledge_active_alert(alert_id: str) -> Alert:
    alert = acknowledge_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Active alert not found")
    return alert


@app.get("/health/live")
def liveness() -> dict[str, str]:
    SERVICE_UP.set(1)
    return {"status": "UP"}


@app.get("/health/ready")
def readiness() -> dict[str, str]:
    return {"status": "UP"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(
        content=get_metrics_payload(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/", include_in_schema=False)
def root() -> JSONResponse:
    return JSONResponse({"service": "alert-service", "docs": "/docs"})
