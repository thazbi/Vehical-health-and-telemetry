from collections import defaultdict

from services.telemetry_service.app.models.telemetry import TelemetryRecord

telemetry_store: dict[str, list[TelemetryRecord]] = defaultdict(list)


def store_telemetry(record: TelemetryRecord) -> TelemetryRecord:
    telemetry_store[record.vehicle_id].append(record)
    return record


def list_telemetry(vehicle_id: str) -> list[TelemetryRecord]:
    return list(telemetry_store.get(vehicle_id, []))
