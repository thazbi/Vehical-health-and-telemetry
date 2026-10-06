from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    vehicle_id: str = Field(min_length=1, max_length=64)
    speed: float = Field(ge=0, le=500)
    rpm: float = Field(ge=0, le=30000)
    battery_temperature: float = Field(ge=-40, le=200)


class MonitoringPreferences(BaseModel):
    speed_limit_kmh: float = Field(default=140, gt=0, le=500)
    rpm_limit: float = Field(default=5000, gt=0, le=30000)
    battery_temperature_limit_c: float = Field(default=50, ge=-40, le=150)
    speed_duration_seconds: int = Field(default=0, ge=0, le=86400)
    rpm_duration_seconds: int = Field(default=0, ge=0, le=86400)
    battery_temperature_duration_seconds: int = Field(default=3600, ge=0, le=86400)


class Alert(BaseModel):
    alert_id: str
    vehicle_id: str
    rule: str
    severity: Literal["warning", "critical"]
    status: Literal["active", "cleared"] = "active"
    acknowledged: bool = False
    message: str
    recommended_action: str
    observed_value: float
    threshold: float
    created_at: datetime
    updated_at: datetime
    cleared_at: datetime | None = None
    acknowledged_at: datetime | None = None


class PendingCondition(BaseModel):
    rule: str
    vehicle_id: str
    observed_value: float
    threshold: float
    duration_seconds: int
    elapsed_seconds: int
    remaining_seconds: int
    started_at: datetime


class EvaluationResult(BaseModel):
    vehicle_id: str
    active_alerts: list[Alert]
    new_alerts: list[Alert]
    cleared_alerts: list[Alert]
    pending_conditions: list[PendingCondition]
