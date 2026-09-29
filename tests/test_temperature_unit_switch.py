"""Tests for identifying temperature sensors for the per-entry unit override."""

from custom_components.chefstemp.temperature_units import (
    is_temperature_sensor,
    temperature_entity_platform,
)


def test_temperature_sensor_unique_ids_are_selected() -> None:
    assert is_temperature_sensor("stand_ambient")
    assert is_temperature_sensor("stand_probe0_temperature")
    assert is_temperature_sensor("stand_probe11_temperature")


def test_non_temperature_entities_are_not_selected() -> None:
    assert not is_temperature_sensor("stand_stand_battery")
    assert not is_temperature_sensor("stand_probe0_battery")
    assert not is_temperature_sensor("stand_probe0_signal")
    assert not is_temperature_sensor("stand_temperature_celsius")


def test_unit_override_includes_sensor_and_temperature_number_entities() -> None:
    assert temperature_entity_platform("sensor", "stand_ambient") == "sensor"
    assert temperature_entity_platform("sensor", "stand_probe0_temperature") == "sensor"
    assert temperature_entity_platform("number", "stand_fan_target") == "number"
    assert temperature_entity_platform("number", "stand_alarm_high") == "number"
    assert temperature_entity_platform("number", "stand_alarm_low") == "number"


def test_unit_override_ignores_non_temperature_entities() -> None:
    assert temperature_entity_platform("sensor", "stand_stand_battery") is None
    assert temperature_entity_platform("number", "stand_unrelated") is None
    assert temperature_entity_platform("fan", "stand_fan") is None
