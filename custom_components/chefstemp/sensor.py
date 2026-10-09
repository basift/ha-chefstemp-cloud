"""Sensor entities for ChefsTemp."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ChefsTempConfigEntry, ChefsTempCoordinator
from .entity import ChefsTempEntity


@dataclass(frozen=True, kw_only=True)
class ChefsTempSensorDescription(SensorEntityDescription):
    """Describes a ChefsTemp sensor and how to read its value from state."""

    value_fn: Callable[[dict[str, Any]], Any]


STAND_SENSORS: tuple[ChefsTempSensorDescription, ...] = (
    ChefsTempSensorDescription(
        key="ambient",
        translation_key="ambient",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("ambient"),
    ),
    ChefsTempSensorDescription(
        key="stand_battery",
        translation_key="stand_battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("stand_battery"),
    ),
    ChefsTempSensorDescription(
        key="probe_frames",
        translation_key="probe_frames",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: sum(
            counts["received"] for counts in data["probe_frame_counts"].values()
        ),
    ),
)


def _probe_descriptions(idx: int) -> tuple[ChefsTempSensorDescription, ...]:
    """The three sensors for one probe index."""
    return (
        ChefsTempSensorDescription(
            key=f"probe{idx}_temperature",
            translation_key="probe_temperature",
            translation_placeholders={"idx": str(idx + 1)},
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda data, i=idx: (data["probes"].get(i) or {}).get("celsius"),  # type: ignore[misc]
        ),
        ChefsTempSensorDescription(
            key=f"probe{idx}_battery",
            translation_key="probe_battery",
            translation_placeholders={"idx": str(idx + 1)},
            device_class=SensorDeviceClass.BATTERY,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda data, i=idx: (data["probes"].get(i) or {}).get("battery"),  # type: ignore[misc]
        ),
        ChefsTempSensorDescription(
            key=f"probe{idx}_signal",
            translation_key="probe_signal",
            translation_placeholders={"idx": str(idx + 1)},
            device_class=SensorDeviceClass.SIGNAL_STRENGTH,
            native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_fn=lambda data, i=idx: (data["probes"].get(i) or {}).get("rssi"),  # type: ignore[misc]
        ),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChefsTempConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the stand sensors and add probe sensors as probes appear."""
    coordinator = entry.runtime_data
    async_add_entities(
        ChefsTempSensor(coordinator, desc) for desc in STAND_SENSORS
    )

    known_probes: set[int] = set()

    @callback
    def _add_probes() -> None:
        new: list[ChefsTempSensor] = []
        for idx in coordinator.data.get("probes", {}):
            if idx in known_probes:
                continue
            known_probes.add(idx)
            new.extend(
                ChefsTempSensor(coordinator, desc) for desc in _probe_descriptions(idx)
            )
        if new:
            async_add_entities(new)

    _add_probes()
    entry.async_on_unload(coordinator.async_add_listener(_add_probes))


class ChefsTempSensor(ChefsTempEntity, SensorEntity):
    """A single ChefsTemp sensor value."""

    entity_description: ChefsTempSensorDescription

    def __init__(
        self, coordinator: ChefsTempCoordinator, description: ChefsTempSensorDescription
    ) -> None:
        """Initialise the sensor from its description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_added_to_hass(self) -> None:
        """Apply the selected Celsius override to probes discovered after startup."""
        await super().async_added_to_hass()
        unit = self.coordinator.temperature_unit_override
        if (
            unit is not None
            and self.entity_description.native_unit_of_measurement
            == UnitOfTemperature.CELSIUS
        ):
            er.async_get(self.hass).async_update_entity_options(
                self.entity_id, "sensor", {"unit_of_measurement": unit}
            )

    @property
    def native_value(self) -> Any:
        """The current sensor reading."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose bounded, aggregated counts without raw frame metadata."""
        if self.entity_description.key == "probe_frames":
            return {
                "period": "since integration load (volatile)",
                **self.coordinator.data["probe_frame_counts"],
            }
        if self.entity_description.key == "ambient":
            return {"ambient_sample_at": self.coordinator.data.get("ambient_sample_at")}
        return None
