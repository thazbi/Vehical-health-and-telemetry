# SAJIVITA | Vehicle Telemetry & Health Monitoring Platform

A locally runnable, production-oriented reference stack for vehicle registry, telemetry validation, threshold alerts, health checks, metrics, and logs. It is intended for SRE/backend learning and integration prototyping. It is **not** a certified vehicle-control system and must not be used to make safety-critical decisions or control a real vehicle.

> New to SAJIVITA? Open the [SAJIVITA platform guide](docs/guide/index.html) for the architecture, setup, interactive dashboard, monitoring tour, and troubleshooting steps.

## Components

- **Vehicle Service**: in-memory vehicle registry with validated user registration and per-vehicle monitoring limits/durations. The two seeded vehicles remain as examples.
- **Telemetry Service**: validates readings, verifies the vehicle through a time-bounded HTTP request to Vehicle Service, and stores readings in memory.
- **Alert Service**: fetches the selected vehicle's preferences, tracks sustained threshold conditions, keeps active alerts visible, and records recovery/cleared events.
- **Prometheus**: scrapes service metrics and evaluates availability and HTTP-failure alert rules.
- **Grafana**: provisions Prometheus and Loki data sources and an overview dashboard.
- **Loki + Grafana Alloy**: receives container stdout/stderr logs for local exploration.

Telemetry ingestion and alert evaluation are separate API calls coordinated by the local dashboard. This avoids coupling successful telemetry acceptance to the alerting service. A durable asynchronous event/outbox path is not implemented.

## Quick Start: Docker Compose

Prerequisites: Docker Desktop (or Docker Engine) with the Compose plugin. From PowerShell at the repository root:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set `GRAFANA_ADMIN_PASSWORD` in `.env` to a unique local password, then start the stack:

```powershell
docker compose up --build -d
docker compose ps
```

All published ports bind to `127.0.0.1` by default:

- Vehicle API docs: http://127.0.0.1:8001/docs
- Telemetry API docs: http://127.0.0.1:8002/docs
- Alert API docs: http://127.0.0.1:8003/docs
- Prometheus: http://127.0.0.1:9090
- Grafana: http://127.0.0.1:3000 (username/password from `.env`)
- Loki readiness: http://127.0.0.1:3100/ready

Stop the stack and remove containers with `docker compose down`. Named volumes keep local Grafana, Prometheus, and Loki data; `docker compose down -v` deletes those volumes.

## One-Click Local Project Demo (Windows)

For the simplest walkthrough, double-click `START-DEMO.bat` in the repository folder. On first use it creates `.venv` with Python 3.11 if necessary and installs the pinned dependencies. It starts the Vehicle, Telemetry, and Alert APIs, waits for health checks, and opens the live dashboard at `http://127.0.0.1:8787/demo.html`.

The demo dashboard lets you register a vehicle, select it, save its speed/RPM/temperature limits and persistence durations, submit one reading, or start a repeating synthetic telemetry simulator. It displays pending timers, active alert notices, alert history, and recovery after readings return below limits, alongside service health and performance metrics. Its dedicated service ports are `8811`, `8812`, and `8813`, avoiding manual-run ports `8001` through `8003`. A terminal window must remain open while the demo runs; press `Ctrl+C` there to stop services launched by the demo. Logs are written under the ignored `.runtime-logs/` folder.

For temperature persistence testing, set the selected vehicle's temperature hold to a short value such as `3` seconds, enter a temperature above that vehicle's limit, and start **Live simulation**. The UI shows the pending time, then an active advisory alert; lower the temperature below the limit and send another reading to clear it. The default seeded temperature hold is one hour. The simulator samples every three seconds and uses invented local readings only.

Limits are saved per vehicle: changing `VW-1001` does not change `VW-1002`. Select the vehicle first and confirm its ID beside **Monitoring preferences**. The alert list is filtered to that selected vehicle. **Acknowledge / close** dismisses the notice after review but does not clear an unresolved active alert; only a later reading under the saved limit clears it.

This Python-only quick demo does not start Docker, Prometheus, Grafana, or Loki. Use Docker Compose above when you want to explore those monitoring services. Opening `docs/guide/index.html` directly cannot start backend processes because browsers do not permit web pages to execute local commands; use `START-DEMO.bat` to prepare the project, then the browser opens the live demo automatically.

## Try the API Flow

Check Vehicle Service and Telemetry readiness:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/vehicles
Invoke-RestMethod http://127.0.0.1:8002/health/ready
```

Submit telemetry for a known vehicle:

```powershell
$reading = @{
    vehicle_id = "VW-1001"
    speed = 82
    rpm = 3200
    battery_temperature = 38.5
} | ConvertTo-Json

Invoke-RestMethod -Uri http://127.0.0.1:8002/telemetry `
    -Method Post -ContentType "application/json" -Body $reading
```

Read its current in-memory history:

```powershell
Invoke-RestMethod http://127.0.0.1:8002/telemetry/VW-1001
```

Evaluate the reading for alerts (for example, speed 150 exceeds the selected vehicle's default 140 km/h limit):

```powershell
$highReading = @{
    vehicle_id = "VW-1001"
    speed = 150
    rpm = 3200
    battery_temperature = 38.5
} | ConvertTo-Json

Invoke-RestMethod -Uri http://127.0.0.1:8003/alerts/evaluate `
    -Method Post -ContentType "application/json" -Body $highReading
Invoke-RestMethod "http://127.0.0.1:8003/alerts?vehicle_id=VW-1001"
```

The alert endpoint returns `active_alerts`, `new_alerts`, `cleared_alerts`, and `pending_conditions`. A temperature condition defaults to a one-hour persistence window; the speed and RPM examples alert immediately unless their vehicle preferences set a hold duration. Unknown vehicles return HTTP `404` from alert evaluation; invalid telemetry returns HTTP `422`; Telemetry returns HTTP `503` when Vehicle Service is unavailable or the vehicle ID is unknown.

## Local Python Run

Use separate terminals for each API. From the repository root, run:

```powershell
.\.venv\Scripts\python -m uvicorn services.vehicle_service.app.main:app --host 127.0.0.1 --port 8001
```

In another terminal:

```powershell
$env:VEHICLE_SERVICE_URL = "http://127.0.0.1:8001"
.\.venv\Scripts\python -m uvicorn services.telemetry_service.app.main:app --host 127.0.0.1 --port 8002
```

In a third terminal:

```powershell
$env:VEHICLE_SERVICE_URL = "http://127.0.0.1:8001"
.\.venv\Scripts\python -m uvicorn services.alert_service.app.main:app --host 127.0.0.1 --port 8003
```

Local Python mode does not start Prometheus, Grafana, or Loki.

## Tests and Quality Checks

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m black --check .
.\.venv\Scripts\python -m mypy services
```

GitHub Actions runs the same Python checks on pushes and pull requests. Docker configuration can be checked with `docker compose config`; run the full stack with `docker compose up --build`.

## Configuration and Operations

Thresholds and ports are documented in `.env.example`. Copy it to `.env`; Compose reads `.env` automatically. Do not commit `.env` or real credentials. Service metrics are exposed at `/metrics`; liveness and readiness are separate at `/health/live` and `/health/ready`. Request correlation uses `X-Request-ID` at the APIs.

The local Alloy collector discovers containers through `/var/run/docker.sock`. Access to that socket can grant broad control over the local Docker daemon. Keep this stack bound to a trusted development machine; do not expose the socket, services, Grafana, Prometheus, or Loki to an untrusted network. A production deployment needs a hardened log collection strategy that avoids granting an observability container Docker-daemon control.

## Important Production Gaps

This is production-oriented scaffolding, not a production-ready vehicle platform:

- Vehicle and telemetry records and alert history are in memory and disappear on restart; there is no durable database or message broker.
- Service APIs have no authentication/authorization or TLS. Compose binds published ports to loopback, but do not change that for internet exposure without adding an authenticated gateway and network controls.
- The local dashboard explicitly sends telemetry to the Alert Service; there is no durable event delivery, deduplication, external notification channel, or incident workflow.
- The live simulator generates synthetic sample readings only; no real vehicle device is connected and no vehicle controls are sent.
- No real vehicle hardware protocol, device identity, command/control path, safety case, regulatory certification, or operational support process is included.
- Compose and single-instance Prometheus/Loki are for local development, not high availability or disaster recovery.

Before any real deployment, perform a threat model and safety review, implement identity/access control and transport security, select durable storage/event delivery, add backup/restore and HA plans, scan/pin image digests, and validate against the applicable automotive and privacy regulations.
