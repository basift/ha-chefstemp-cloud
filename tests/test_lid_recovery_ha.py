"""Offline validation with Home Assistant's actual blueprint and automation schemas."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

pytest.importorskip("homeassistant")

from homeassistant.components.automation.config import (
    AUTOMATION_BLUEPRINT_SCHEMA,
    PLATFORM_SCHEMA,
)
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import HomeAssistant
from homeassistant.helpers.script import Script
from homeassistant.helpers.template import Template
from homeassistant.loader import async_setup as setup_loader
from homeassistant.util.yaml import load_yaml

PATH = (
    Path(__file__).resolve().parent.parent
    / "blueprints/automation/chefstemp/lid_open_recovery_stall.yaml"
)


def expanded_automation():
    """Parse the real !input nodes, apply defaults and expand without live HA."""
    blueprint = Blueprint(
        load_yaml(str(PATH)),
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )
    inputs = BlueprintInputs(blueprint, {"use_blueprint": {
        "path": "chefstemp/lid_open_recovery_stall.yaml",
        "input": {
            "temperature_sensor": "sensor.test_grill_ambient",
            "target_entity": "number.test_fan_target",
            "fan_entity": "fan.test_fan",
        },
    }})
    inputs.validate()
    return PLATFORM_SCHEMA(inputs.async_substitute())


def test_home_assistant_blueprint_and_expanded_script_schema():
    async def validate():
        with TemporaryDirectory(prefix="chefstemp-blueprint-") as config_dir:
            hass = HomeAssistant(config_dir)
            try:
                return expanded_automation()
            finally:
                hass.import_executor.shutdown(wait=True)

    automation = asyncio.run(validate())
    assert len(automation["triggers"]) == 1
    assert automation["mode"] == "single"
    assert automation["actions"][2]["action"] == "fan.turn_off"


def test_equal_ambient_values_with_fresh_mqtt_attributes_emit_state_events():
    async def exercise(config_dir):
        hass = HomeAssistant(config_dir)
        seen = []
        hass.bus.async_listen(EVENT_STATE_CHANGED, lambda event: seen.append(event))
        for stamp in ("2026-09-29T12:00:00+00:00", "2026-09-29T12:00:01+00:00"):
            hass.states.async_set("sensor.test_grill_ambient", "95", {
                "unit_of_measurement": "°C", "ambient_sample_at": stamp,
            })
        await hass.async_block_till_done()
        assert len(seen) == 2
        assert seen[0].data["new_state"].state == seen[1].data["new_state"].state
        hass.import_executor.shutdown(wait=True)

    with TemporaryDirectory(prefix="chefstemp-ambient-") as config_dir:
        asyncio.run(exercise(config_dir))


@pytest.mark.parametrize("unit", ["°C", "°F"])
@pytest.mark.parametrize("scenario,expected_on", [
    ("plateau", True),
    ("reversal", True),
    ("continues_rising", False),
    ("target_reached", False),
    ("target_changed", False),
    ("manual_override", False),
    ("unavailable", False),
    ("stale", False),
    ("unit_mismatch", False),
    ("unit_missing", False),
    ("timeout", False),
    ("interrupted", False),
])
def test_offline_ha_script_acts_only_after_recovery_then_stall(monkeypatch, unit, scenario, expected_on):
    """Run the real HA script on an isolated state machine with mocked service calls."""

    async def exercise(config_dir):
        hass = HomeAssistant(config_dir)
        setup_loader(hass)
        calls = []
        factor = 1.8 if unit == "°F" else 1

        def to_unit(celsius):
            return celsius * factor + (32 if unit == "°F" else 0)

        sensor = "sensor.test_grill_ambient"
        fan = "fan.test_fan"
        target = "number.test_fan_target"

        def ambient(celsius, *, available=True):
            hass.states.async_set(sensor, str(to_unit(celsius)) if available else "unavailable", {
                "unit_of_measurement": unit,
                "ambient_sample_at": datetime.now(UTC).isoformat(),
            })

        async def mocked_call(_registry, domain, service, service_data=None, **_kwargs):
            calls.append((domain, service))
            if domain == "fan":
                enabled = service == "turn_on"
                hass.states.async_set(fan, "on" if enabled else "off", {
                    "thermostat_enabled_observed": enabled,
                    "command_status": "observed",
                })

        monkeypatch.setattr(type(hass.services), "async_call", mocked_call)
        hass.states.async_set(target, str(to_unit(110)), {"unit_of_measurement": unit})
        hass.states.async_set(fan, "on", {
            "thermostat_enabled_observed": True, "command_status": "observed",
        })
        ambient(110)
        before = hass.states.get(sensor)
        await asyncio.sleep(0.01)
        ambient(95)
        after = hass.states.get(sensor)
        config = expanded_automation()
        config["variables"].variables["stall_window"] = 0.11
        config["variables"].variables["freshness_seconds"] = 1
        config["variables"].variables["max_observation_seconds"] = 2
        trigger = {"from_state": before, "to_state": after}
        assert Template(BLUEPRINT_CONDITION, hass).async_render({
            "trigger": trigger,
            "temperature_sensor": sensor,
            "target_entity": target,
            "fan_entity": fan,
            "drop_threshold": 10,
            "near_target_margin": 12,
            "target_deadband": 8,
            "freshness_seconds": 1,
        }, parse_result=True) is True
        script = Script(
            hass, config["actions"], "isolated lid recovery", "automation",
            variables=config["variables"],
        )
        run = asyncio.create_task(script.async_run({"trigger": trigger}))
        try:
            for _ in range(100):
                if ("fan", "turn_off") in calls and script.is_running:
                    break
                await asyncio.sleep(0.01)
            assert ("fan", "turn_off") in calls
            assert ("fan", "turn_on") not in calls
            await asyncio.sleep(0.35)  # let HA load/attach the state-change triggers
            if scenario == "interrupted":
                run.cancel()  # HA stops the in-flight run; never restart an off fan
                await asyncio.gather(run, return_exceptions=True)
                assert hass.states.get(fan).state == "off"
                assert ("persistent_notification", "create") in calls
                assert ("fan", "turn_on") not in calls
                return
            if scenario == "target_changed":
                hass.states.async_set(target, str(to_unit(111)), {"unit_of_measurement": unit})
            elif scenario == "manual_override":
                hass.states.async_set(fan, "on", {
                    "thermostat_enabled_observed": True, "command_status": "observed",
                })
            elif scenario == "unavailable":
                ambient(95, available=False)
            elif scenario == "stale":
                # The next event has an old timestamp despite a changed value.
                hass.states.async_set(sensor, str(to_unit(100)), {
                    "unit_of_measurement": unit,
                    "ambient_sample_at": "2020-01-01T00:00:00+00:00",
                })
            elif scenario in ("unit_mismatch", "unit_missing"):
                hass.states.async_set(sensor, str(to_unit(97)), {
                    "unit_of_measurement": None if scenario == "unit_missing" else
                    ("°F" if unit == "°C" else "°C"),
                    "ambient_sample_at": datetime.now(UTC).isoformat(),
                })
            elif scenario != "timeout":
                ambient(97)
                await asyncio.sleep(0.05)
                assert ("fan", "turn_on") not in calls  # still recovering
                ambient(100)  # third fresh recovery reading, +5 °C from trough
                await asyncio.sleep(0.06)
                assert ("fan", "turn_on") not in calls  # stall window not complete
                if scenario == "target_reached":
                    ambient(102)  # enters the deadband, independent of the stall condition
                else:
                    ambient(100.6 if scenario == "continues_rising" else 100.2)
                    await asyncio.sleep(0.12)
                    ambient(101.3 if scenario == "continues_rising" else
                            98 if scenario == "reversal" else 100.4)
            await asyncio.wait_for(run, timeout=4)
            assert (("fan", "turn_on") in calls) is expected_on, calls
            assert calls.count(("fan", "turn_on")) <= 1
            if scenario == "manual_override":
                assert ("fan", "turn_on") not in calls
            elif not expected_on:
                assert hass.states.get(fan).state == "off"
        finally:
            if not run.done():
                run.cancel()
                await asyncio.gather(run, return_exceptions=True)
            hass.import_executor.shutdown(wait=True)

    with TemporaryDirectory(prefix="chefstemp-script-") as config_dir:
        asyncio.run(exercise(config_dir))


BLUEPRINT_CONDITION = load_yaml(str(PATH))["conditions"][0]["value_template"]
