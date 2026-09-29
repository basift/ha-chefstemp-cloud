"""Pure helpers for selecting ChefsTemp temperature entities."""

from __future__ import annotations

import re


def is_temperature_sensor(unique_id: str) -> bool:
    """Recognize the grill ambient sensor and dynamically created probe temperatures."""
    return re.search(r"(?:^|_)(?:ambient|probe\d+_temperature)$", unique_id) is not None


def temperature_entity_platform(domain: str, unique_id: str) -> str | None:
    """Return the options namespace for a temperature sensor or setpoint entity."""
    if domain == "sensor" and is_temperature_sensor(unique_id):
        return "sensor"
    if domain == "number" and re.search(
        r"(?:^|_)(?:fan_target|alarm_high|alarm_low)$", unique_id
    ):
        return "number"
    return None
