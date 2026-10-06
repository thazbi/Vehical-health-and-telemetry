from pydantic import BaseModel, ConfigDict, Field


class TelemetryRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    vehicle_id: str = Field(..., min_length=1)
    speed: float = Field(..., ge=0)
    rpm: float = Field(..., ge=0)
    battery_temperature: float = Field(..., ge=-40, le=150)
