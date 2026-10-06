# Automotive Microservice Health Monitoring System - Architecture

## Current implementation status

The repository now contains Vehicle, Telemetry, and Alert FastAPI services, Docker Compose definitions, Prometheus scrape/alert rules, Grafana provisioning, local Loki/Alloy log collection, and a Windows local demo launcher/dashboard. The APIs are designed for local SRE learning and integration prototyping, not real vehicle control or safety-critical operation.

Vehicle registry/preferences, telemetry history, and generated alerts are process-local in-memory data. The local dashboard sends readings to Telemetry and separately evaluates the same reading with Alert Service. Vehicle preferences define speed/RPM/temperature limits and persistence durations. The Alert Service tracks pending conditions, opens persistent active alerts after the duration, and clears them after a later safe reading. Durable event delivery, authentication/authorization, TLS, high availability, and safety certification are not implemented. Demo telemetry is synthetic and no hardware/control path exists.

## Phase 0: Repository inspection findings

The workspace is currently empty. There are no existing project files, source folders, dependency manifest files, Docker files, or CI workflow files to extend.

This means there is no legacy architecture, no conflicting framework choice, and no hidden configuration to preserve. The project can therefore begin from a clean baseline with the required architecture and conventions.

### Current state

- Source code: none
- Git repository: not initialized
- Python dependency files: none
- Docker configuration: none
- CI/CD configuration: none
- Monitoring configuration: none
- Application architecture: not yet present

### Risks and considerations

Because the repository is empty, the implementation should be deliberate and incremental. The first priority is to establish a clean project structure, standard Python configuration, and the observability-first architecture described in the project brief.

### Recommended architecture

The implementation should follow a simple, understandable microservice layout that is suitable for local Docker Compose development:

- Vehicle Service: manages vehicle metadata and exposes health, readiness, and metrics endpoints.
- Telemetry Service: validates incoming telemetry, checks vehicle existence via the Vehicle Service, and records operational state.
- Alert Service: reads telemetry-related conditions and generates alerts when thresholds are crossed.
- Observability stack: Prometheus for metrics, Grafana for dashboards, and Loki for aggregated logs.
- Service-to-service calls: HTTP over an internal Docker network using environment-based URLs and timeout configuration.
- Stateful data: in-memory storage only for the first version; no database is required.

## High-level service topology

```text
GitHub
  |
  v
GitHub Actions
  |
  v
Docker images
  |
  v
Docker Compose
  |
  +------------------------------+
  |                              |
  v                              v
Vehicle Service             Telemetry Service     Alert Service
  |                              |                    |
  +------------------------------+--------------------+
                               |
                               v
                     Observability Layer
                               |
             +-----------------+-----------------+
             |                                   |
             v                                   v
        Prometheus                           Loki
             |                                   |
             +-----------------+-----------------+
                               |
                               v
                            Grafana
```

## Recommended runtime design

### 1. Vehicle Service

Responsibilities:

- Maintain a small in-memory list of vehicles.
- Expose REST endpoints for listing and fetching vehicle metadata.
- Provide liveness and readiness endpoints.
- Emphasize health and metrics output for Prometheus.
- Keep dependency checks lightweight and time-bounded.

### 2. Telemetry Service

Responsibilities:

- Accept telemetry payloads from clients.
- Validate speed, RPM, and battery temperature ranges.
- Query the Vehicle Service to confirm the vehicle exists.
- Expose telemetry history per vehicle.
- Report dependency health and request error metrics.

### 3. Alert Service

Responsibilities:

- Evaluate telemetry and alert rules.
- Keep alert thresholds configurable by environment variable.
- Expose alert retrieval endpoints.
- Provide health and metrics endpoints.
- Remain independent from the Telemetry Service so the architecture remains decoupled and simpler to reason about.

## Operational concerns

### Observability model

Each service should emit structured JSON logs with at least:

- timestamp
- level
- service name
- request ID
- HTTP method
- endpoint
- status code
- duration
- message

The request ID must be reused from the incoming X-Request-ID header when supplied; otherwise a generated value should be used. The same request ID should be attached to response headers and logs.

### Metrics model

Each service should expose Prometheus-compatible endpoints with basic instrumentation for:

- total HTTP requests
- request latency histogram
- failed requests
- active requests
- service up signal
- dependency call totals
- dependency error totals
- dependency latency metrics

To avoid high-cardinality label pollution, avoid labels such as vehicle_id, request_id, and user_id in metrics.

### Health model

The project must clearly distinguish between:

- liveness: process is alive; should not fail because a dependency is down
- readiness: service can safely receive traffic; should fail when critical dependencies are unhealthy
- dependency health: upstream checks must be explicit and low-cost

## Failure simulation design

Failure simulation should not be part of the normal business workflow. It must be isolated behind a development-only admin endpoint and must be disabled by default.

Example modes:

- LATENCY
- ERROR
- DEPENDENCY_FAILURE
- SERVICE_UNAVAILABLE

This is meant for training and test scenarios only, not for production use.

## Security and reliability principles

The initial implementation should follow these rules:

- no hardcoded secrets
- no credentials committed to the repository
- no debug mode by default
- no stack traces exposed to clients
- environment-based configuration for URLs and thresholds
- timeouts for external requests
- graceful shutdown support
- consistent error payloads

## Recommended technology choices

The brief already provides sensible and consistent technology choices:

- Python
- FastAPI
- Pydantic
- Uvicorn
- Pytest
- pytest-asyncio
- HTTPX
- Ruff
- Black
- MyPy where practical
- Docker
- Docker Compose
- Prometheus
- Grafana
- Loki
- Locust
- GitHub Actions

These are a good fit for a learning project and align with the SRE/observability goals.

## Project structure to implement after Phase 0 approval

```text
automotive-microservice-monitoring/
├── services/
│   ├── vehicle-service/
│   │   ├── app/
│   │   │   ├── api/
│   │   │   ├── core/
│   │   │   ├── models/
│   │   │   ├── services/
│   │   │   ├── metrics/
│   │   │   ├── health/
│   │   │   └── main.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── telemetry-service/
│   │   ├── app/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── alert-service/
│       ├── app/
│       ├── tests/
│       ├── Dockerfile
│       └── requirements.txt
├── monitoring/
│   ├── prometheus/
│   │   ├── prometheus.yml
│   │   └── alerts/
│   ├── grafana/
│   │   ├── dashboards/
│   │   └── provisioning/
│   └── loki/
├── load_tests/
│   └── locustfile.py
├── .github/
│   └── workflows/
│       └── ci.yml
├── docs/
│   ├── architecture.md
│   ├── api.md
│   ├── monitoring.md
│   ├── failure-scenarios.md
│   └── troubleshooting.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── README.md
├── Makefile
└── .github/
```

## Original phase plan

1. Phase 1: project foundation and Python tooling
2. Phase 2: Vehicle Service implementation and tests
3. Phase 3: Telemetry Service implementation and tests
4. Phase 4: Alert Service implementation and tests
5. Phase 5: Observability foundation and request IDs
6. Phase 6: Docker and Compose setup
7. Phase 7: Prometheus configuration
8. Phase 8: Grafana dashboards
9. Phase 9: Loki centralized logging
10. Phase 10: failure simulation
11. Phase 11: alert rules
12. Phase 12: Locust load testing
13. Phase 13: GitHub Actions CI
14. Phase 14: final reliability review and documentation

This sequence records the original implementation plan. It is not a claim that every production concern is complete; see the current implementation status above and the production gaps in `README.md`.
