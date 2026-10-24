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
    """Set up the temperature-unit switch, and the Bluetooth switch when supported."""
    coordinator = entry.runtime_data
    entities: list = [ChefsTempTemperatureUnitSwitch(coordinator, entry)]
    if coordinator.ble_mac:
        entities.append(ChefsTempBluetoothSwitch(coordinator))
    async_add_entities(entities)


class ChefsTempBluetoothSwitch(ChefsTempEntity, SwitchEntity):
    """Let HA hold the stand's local BLE link (on), or release it for the phone app.

    On (the default) means HA keeps its local Bluetooth link and reconnects on its
    own. Turning it off powers HA's BLE down for a few minutes so the phone app can
    claim the stand's single BLE slot; HA then re-enables itself automatically and
    reclaims the link once the slot is free again.
    """

    _attr_translation_key = "bluetooth"
    _attr_icon = "mdi:bluetooth"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        """Initialise the Bluetooth hold/release switch for this stand."""
        super().__init__(coordinator, "bluetooth")

    @property
    def is_on(self) -> bool:
        """Whether HA is allowed to hold the stand's local BLE link."""
        return bool(self.coordinator.ble_enabled)

    @property
    def available(self) -> bool:
        """Keep the control usable even while the stand is offline."""
        return True

    @property
    def extra_state_attributes(self) -> dict:
        """Expose when HA will re-enable BLE after a release, if a release is active."""
        return {"resumes_at": self.coordinator.ble_resume_at}

    async def async_turn_on(self, **kwargs) -> None:
        """Re-enable HA's local Bluetooth link immediately."""
        await self.coordinator.async_enable_ble()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Release the stand's BLE slot for the phone app; HA returns on its own."""
        await self.coordinator.async_release_ble()
        self.async_write_ha_state()


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
