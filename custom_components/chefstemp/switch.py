"""Configuration switches for ChefsTemp."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import ChefsTempConfigEntry
from .entity import ChefsTempEntity
from .temperature_units import temperature_entity_platform


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChefsTempConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the temperature-unit switch."""
    async_add_entities([ChefsTempTemperatureUnitSwitch(entry.runtime_data, entry)])


class ChefsTempTemperatureUnitSwitch(ChefsTempEntity, SwitchEntity, RestoreEntity):
    """Show all ChefsTemp temperature entities in °C when on; else follow HA's default."""

    _attr_translation_key = "temperature_celsius"
    _attr_icon = "mdi:temperature-celsius"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry: ChefsTempConfigEntry) -> None:
        """Initialize the preference switch for this stand."""
        super().__init__(coordinator, "temperature_celsius")
        self._entry = entry
        self._is_celsius = False

    @property
    def is_on(self) -> bool:
        """Return whether this stand's temperature sensors are forced to Celsius."""
        return self._is_celsius

    @property
    def available(self) -> bool:
        """Keep the preference available even while the stand is offline."""
        return True

    async def async_added_to_hass(self) -> None:
        """Restore the last selection and apply it to registered temperature sensors."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        self._is_celsius = last is not None and last.state == "on"
        self._apply_unit()
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        """Force temperature sensors to Celsius."""
        self._is_celsius = True
        self._apply_unit()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Clear the override and follow Home Assistant's configured units."""
        self._is_celsius = False
        self._apply_unit()
        self.async_write_ha_state()

    def _apply_unit(self) -> None:
        """Set display-unit overrides for this entry's temperature sensors and numbers."""
        unit = UnitOfTemperature.CELSIUS if self._is_celsius else None
        self.coordinator.temperature_unit_override = unit
        registry = er.async_get(self.hass)
        for entity in er.async_entries_for_config_entry(registry, self._entry.entry_id):
            platform = temperature_entity_platform(entity.domain, entity.unique_id)
            if platform is not None:
                registry.async_update_entity_options(
                    entity.entity_id, platform, {"unit_of_measurement": unit}
                )
