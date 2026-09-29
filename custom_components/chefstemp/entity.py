"""Shared base entity for ChefsTemp."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import ChefsTempCoordinator


class ChefsTempEntity(CoordinatorEntity[ChefsTempCoordinator]):
    """Common device info and availability for every ChefsTemp entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ChefsTempCoordinator, key: str) -> None:
        """Initialise for one stand, with a per-entity unique-id suffix."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_mac}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Present the stand as one device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.device_mac)},
            name=self.coordinator.device_name,
            manufacturer=MANUFACTURER,
            model="S1 Stand",
        )

    @property
    def available(self) -> bool:
        """Whether the stand is reachable."""
        return super().available and bool(self.coordinator.data.get("available"))
