from threading import RLock

from services.vehicle_service.app.models.vehicle import (
    MonitoringPreferences,
    Vehicle,
    VehicleStatus,
)


class VehicleStore:
    def __init__(self) -> None:
        self._vehicles: dict[str, Vehicle] = {
            "VW-1001": Vehicle(
                vehicle_id="VW-1001",
                model="ID.4",
                status=VehicleStatus.ACTIVE,
            ),
            "VW-1002": Vehicle(
                vehicle_id="VW-1002",
                model="ID.3",
                status=VehicleStatus.MAINTENANCE,
            ),
        }
        self._lock = RLock()

    def list_vehicles(self) -> list[Vehicle]:
        with self._lock:
            return [vehicle.model_copy(deep=True) for vehicle in self._vehicles.values()]

    def get_vehicle(self, vehicle_id: str) -> Vehicle | None:
        with self._lock:
            vehicle = self._vehicles.get(vehicle_id)
            if vehicle is None:
                return None
            return vehicle.model_copy(deep=True)

    def add_vehicle(self, vehicle: Vehicle) -> Vehicle:
        with self._lock:
            if vehicle.vehicle_id in self._vehicles:
                raise ValueError(f"Vehicle {vehicle.vehicle_id} is already registered")
            stored_vehicle = vehicle.model_copy(deep=True)
            self._vehicles[vehicle.vehicle_id] = stored_vehicle
            return stored_vehicle.model_copy(deep=True)

    def update_preferences(
        self,
        vehicle_id: str,
        preferences: MonitoringPreferences,
    ) -> Vehicle | None:
        with self._lock:
            vehicle = self._vehicles.get(vehicle_id)
            if vehicle is None:
                return None
            updated = vehicle.model_copy(update={"preferences": preferences}, deep=True)
            self._vehicles[vehicle_id] = updated
            return updated.model_copy(deep=True)
