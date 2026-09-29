"""Fan entity for ChefsTemp.

The Breezo fan is a thermostat on the device: with it enabled the stand runs it
whenever the fan target is above the grill ambient and idles it otherwise, and it
picks its own strength (commanded strength has no audible effect — verified). So
this entity is a plain on/off switch with no speed: "on" enables the thermostat,
"off" force-stops it regardless of target. The setpoint is the ``Fan target``
number, which is where Home Assistant automations do the smart control.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ChefsTempConfigEntry
from .entity import ChefsTempEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChefsTempConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the fan for the stand."""
    async_add_entities([ChefsTempFan(entry.runtime_data)])


class ChefsTempFan(ChefsTempEntity, FanEntity):
    """The stand's Breezo fan, as an on/off thermostat enable."""

    _attr_translation_key = "fan"
    _attr_supported_features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF

    def __init__(self, coordinator) -> None:
        """Initialise the fan entity."""
        super().__init__(coordinator, "fan")

    @property
    def is_on(self) -> bool:
        """Whether the fan thermostat is enabled (not necessarily running)."""
        return bool(self.coordinator.data.get("fan_on"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the device-chosen strength and the active setpoint."""
        return {
            "strength": self.coordinator.data.get("fan_strength"),
            "target": self.coordinator.data.get("fan_target"),
            "motor_running": self.coordinator.data.get("fan_running"),
            "thermostat_enabled_observed": self.coordinator.data.get("fan_enabled"),
            "command_status": self.coordinator.data.get("fan_command_status"),
        }

    async def async_turn_on(self, *args: Any, **kwargs: Any) -> None:
        """Enable the fan thermostat."""
        await self.coordinator.async_set_fan(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Force the fan off."""
        await self.coordinator.async_set_fan(False)
