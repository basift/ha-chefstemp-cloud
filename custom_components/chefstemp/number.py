"""Number entities for ChefsTemp: fan target and the ambient alarms."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import TEMP_MAX, TEMP_MIN
from .coordinator import ChefsTempConfigEntry, ChefsTempCoordinator
from .entity import ChefsTempEntity


@dataclass(frozen=True, kw_only=True)
class ChefsTempNumberDescription(NumberEntityDescription):
    """Describes a ChefsTemp number and how it reads and writes state."""

    value_fn: Callable[[dict[str, Any]], Any]
    set_fn: Callable[[ChefsTempCoordinator, int], Awaitable[None]]


NUMBERS: tuple[ChefsTempNumberDescription, ...] = (
    ChefsTempNumberDescription(
        key="fan_target",
        translation_key="fan_target",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=TEMP_MIN,
        native_max_value=TEMP_MAX,
        native_step=1,
        mode=NumberMode.BOX,
        value_fn=lambda data: data.get("fan_target"),
        set_fn=lambda coord, value: coord.async_set_fan_target(value),
    ),
    ChefsTempNumberDescription(
        key="alarm_high",
        translation_key="alarm_high",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=TEMP_MIN,
        native_max_value=TEMP_MAX,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda data: data.get("alarm_high"),
        set_fn=lambda coord, value: coord.async_set_high_alarm(value),
    ),
    ChefsTempNumberDescription(
        key="alarm_low",
        translation_key="alarm_low",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=TEMP_MIN,
        native_max_value=TEMP_MAX,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda data: data.get("alarm_low"),
        set_fn=lambda coord, value: coord.async_set_low_alarm(value),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChefsTempConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number entities for the stand."""
    coordinator = entry.runtime_data
    async_add_entities(ChefsTempNumber(coordinator, desc) for desc in NUMBERS)


class ChefsTempNumber(ChefsTempEntity, NumberEntity):
    """A settable temperature value on the stand."""

    entity_description: ChefsTempNumberDescription

    def __init__(
        self, coordinator: ChefsTempCoordinator, description: ChefsTempNumberDescription
    ) -> None:
        """Initialise the number from its description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        """The current value."""
        value = self.entity_description.value_fn(self.coordinator.data)
        return None if value is None else float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Write a new value to the device."""
        await self.entity_description.set_fn(self.coordinator, round(value))
