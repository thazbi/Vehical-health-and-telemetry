from services.alert_service.app.models.alert import MonitoringPreferences, TelemetryEvent


def evaluate_telemetry(
    event: TelemetryEvent,
    preferences: MonitoringPreferences,
) -> list[tuple[str, float, float, int]]:
    rules = (
        (
            "battery_temperature_high",
            event.battery_temperature,
            preferences.battery_temperature_limit_c,
            preferences.battery_temperature_duration_seconds,
        ),
        ("rpm_high", event.rpm, preferences.rpm_limit, preferences.rpm_duration_seconds),
        (
            "speed_high",
            event.speed,
            preferences.speed_limit_kmh,
            preferences.speed_duration_seconds,
        ),
    )
    return [
        (rule, observed, threshold, duration)
        for rule, observed, threshold, duration in rules
        if observed > threshold
    ]
