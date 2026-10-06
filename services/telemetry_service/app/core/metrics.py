from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

REGISTRY = CollectorRegistry(auto_describe=True)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=("method", "path", "status"),
    registry=REGISTRY,
)

HTTP_REQUEST_LATENCY_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    labelnames=("method", "path"),
    registry=REGISTRY,
)

HTTP_REQUESTS_FAILED_TOTAL = Counter(
    "http_requests_failed_total",
    "Total failed HTTP requests",
    labelnames=("method", "path", "status"),
    registry=REGISTRY,
)

ACTIVE_REQUESTS = Gauge("active_requests", "Current active requests", registry=REGISTRY)
SERVICE_UP = Gauge("service_up", "Service availability state", registry=REGISTRY)
SERVICE_UP.set(1)

DEPENDENCY_REQUEST_TOTAL = Counter(
    "dependency_request_total",
    "Total dependency requests",
    labelnames=("dependency", "status"),
    registry=REGISTRY,
)
DEPENDENCY_REQUEST_FAILURES_TOTAL = Counter(
    "dependency_request_failures_total",
    "Dependency request failures",
    labelnames=("dependency",),
    registry=REGISTRY,
)
DEPENDENCY_REQUEST_DURATION_SECONDS = Histogram(
    "dependency_request_duration_seconds",
    "Dependency request latency in seconds",
    labelnames=("dependency",),
    registry=REGISTRY,
)


def get_metrics_payload() -> bytes:
    return generate_latest(REGISTRY)
