import os
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class VehicleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    MAINTENANCE = "MAINTENANCE"


class MonitoringPreferences(BaseModel):
    model_config = ConfigDict(validate_default=True)

    speed_limit_kmh: float = Field(
        default_factory=lambda: float(os.getenv("SPEED_THRESHOLD", "140")),
        gt=0,
        le=500,
    )
    rpm_limit: float = Field(
        default_factory=lambda: float(os.getenv("RPM_THRESHOLD", "5000")),
        gt=0,
        le=30000,
    )
    battery_temperature_limit_c: float = Field(
        default_factory=lambda: float(os.getenv("BATTERY_TEMPERATURE_THRESHOLD", "50")),
        ge=-40,
        le=150,
    )
    speed_duration_seconds: int = Field(default=0, ge=0, le=86400)
    rpm_duration_seconds: int = Field(default=0, ge=0, le=86400)
    battery_temperature_duration_seconds: int = Field(default=3600, ge=0, le=86400)


class Vehicle(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    vehicle_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    model: str = Field(..., min_length=1, max_length=100)
    status: VehicleStatus = VehicleStatus.ACTIVE
    preferences: MonitoringPreferences = Field(default_factory=MonitoringPreferences)
