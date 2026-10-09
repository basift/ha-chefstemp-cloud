"""Fan coordinator behavior with an isolated Home Assistant runtime."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


def _load(monkeypatch):
    def stub(name, **attrs):
        module = ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)

    class BaseCoordinator:
        def __init__(self, *args, **kwargs):
            self.hass = args[0]
            self.data = {}

        def async_set_updated_data(self, data):
            self.data = data

        async def async_shutdown(self):
            pass

    stub("homeassistant", __path__=[])
    stub("homeassistant.config_entries", ConfigEntry=type("ConfigEntry", (), {"__class_getitem__": classmethod(lambda cls, item: cls)}))
    stub("homeassistant.core", HomeAssistant=object, callback=lambda func: func)
    stub("homeassistant.exceptions", ConfigEntryAuthFailed=type("AuthFailed", (Exception,), {}))
    stub("homeassistant.helpers", __path__=[])
    stub("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=type("GenericCoordinator", (BaseCoordinator,), {"__class_getitem__": classmethod(lambda cls, item: cls)}), UpdateFailed=type("UpdateFailed", (Exception,), {}))
    stub("custom_components", __path__=[])
    stub("custom_components.chefstemp", __path__=[])
    root = Path(__file__).resolve().parent.parent / "custom_components" / "chefstemp"
    spec = importlib.util.spec_from_file_location("custom_components.chefstemp.frames", root / "frames.py")
    frames = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, frames)
    spec.loader.exec_module(frames)
    stub("custom_components.chefstemp.api", ChefsTempApi=object, ChefsTempAuthError=type("AuthError", (Exception,), {}), ChefsTempError=type("ApiError", (Exception,), {}))
    stub("custom_components.chefstemp.const", CONF_DEVICE_MAC="mac", DEFAULT_SCAN_INTERVAL=60, DOMAIN="chefstemp")
    stub("custom_components.chefstemp.mqtt", CloudMqttTransport=object)
    spec = importlib.util.spec_from_file_location("custom_components.chefstemp.coordinator", root / "coordinator.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_valid_probe_frames_route_to_their_own_temperature_sensors(monkeypatch):
    module = _load(monkeypatch)
    root = Path(__file__).resolve().parent.parent / "custom_components" / "chefstemp"

    def stub(name, **attrs):
        fake = ModuleType(name)
        fake.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, fake)

    @dataclass(frozen=True, kw_only=True)
    class Description:
        key: str
        translation_key: str
        translation_placeholders: dict | None = None
        device_class: str | None = None
        native_unit_of_measurement: str | None = None
        state_class: str | None = None
        entity_category: str | None = None
        entity_registry_enabled_default: bool = True

    stub("homeassistant.components", __path__=[])
    stub("homeassistant.components.sensor", SensorDeviceClass=SimpleNamespace(TEMPERATURE="temperature", BATTERY="battery", SIGNAL_STRENGTH="signal"), SensorEntity=object, SensorEntityDescription=Description, SensorStateClass=SimpleNamespace(MEASUREMENT="measurement"))
    stub("homeassistant.const", PERCENTAGE="%", SIGNAL_STRENGTH_DECIBELS_MILLIWATT="dBm", EntityCategory=SimpleNamespace(DIAGNOSTIC="diagnostic"), UnitOfTemperature=SimpleNamespace(CELSIUS="°C"))
    stub("homeassistant.helpers.entity_registry")
    stub("homeassistant.helpers.entity_platform", AddConfigEntryEntitiesCallback=object)

    class BaseEntity:
        def __init__(self, coordinator, key):
            self.coordinator = coordinator

    stub("custom_components.chefstemp.entity", ChefsTempEntity=BaseEntity)
    spec = importlib.util.spec_from_file_location("custom_components.chefstemp.sensor", root / "sensor.py")
    sensor = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, sensor)
    spec.loader.exec_module(sensor)

    loop = asyncio.new_event_loop()
    try:
        coordinator = module.ChefsTempCoordinator(SimpleNamespace(loop=loop), SimpleNamespace(data={"mac": "unused"}, title="stand"), SimpleNamespace())
        uplink = b"\x57\xa2\x06"
        coordinator._handle_frame(module.frames.build(0x20, b"\x00\x32\x00\x78\x3c\xaf", header=uplink))
        coordinator._handle_frame(module.frames.build(0x20, b"\x01\x32\x02\x58\x50\xb0", header=uplink))
        first = sensor.ChefsTempSensor(coordinator, sensor._probe_descriptions(0)[0])
        second = sensor.ChefsTempSensor(coordinator, sensor._probe_descriptions(1)[0])
        assert first.native_value == 12.0
        assert second.native_value == 60.0
        assert coordinator.data["probes"][0]["battery"] == 60
        assert coordinator.data["probes"][1]["battery"] == 80
    finally:
        loop.close()


def test_ambient_updates_do_not_refresh_or_clear_cached_probe(monkeypatch):
    module = _load(monkeypatch)
    loop = asyncio.new_event_loop()
    try:
        coordinator = module.ChefsTempCoordinator(
            SimpleNamespace(loop=loop), SimpleNamespace(data={"mac": "unused"}, title="stand"), SimpleNamespace(),
        )
        uplink = b"\x57\xa2\x06"
        coordinator._handle_frame(module.frames.build(0x20, b"\x00\x32\x00\x78\x3c\xaf", header=uplink))
        coordinator._handle_frame(module.frames.build(0x71, b"\x00\x21", header=uplink))
        assert coordinator.data["ambient"] == 33
        assert coordinator.data["probes"][0]["celsius"] == 12.0
    finally:
        loop.close()


def test_off_reconciles_stale_on_then_fresh_on_and_observed_off(monkeypatch):
    module = _load(monkeypatch)
    monkeypatch.setattr(module, "FAN_RECONCILE_SECONDS", 0.02)

    async def scenario():
        hass = SimpleNamespace(loop=asyncio.get_running_loop())
        coordinator = module.ChefsTempCoordinator(hass, SimpleNamespace(data={"mac": "unused"}, title="stand"), SimpleNamespace())
        coordinator.push_connected = True
        coordinator._transport = SimpleNamespace()

        async def send(frame):
            assert frame[8] == module.frames.FAN_OFF

        coordinator._async_send = send
        coordinator._apply_event({"type": "fan", "on": True, "strength": 2}, coordinator.data)
        coordinator.data["fan_on"] = True
        await coordinator.async_set_fan(False)
        assert coordinator.data["fan_on"] is False
        assert coordinator.data["fan_command_status"] == "pending"
        coordinator._handle_frame(module.frames.build(0x73, b"\x04\x01\x09\x02\x02", header=b"\x57\xa2\x06"))
        assert coordinator.data["fan_on"] is False
        await asyncio.sleep(0.04)
        assert coordinator.data["fan_on"] is True
        assert coordinator.data["fan_command_status"] == "unconfirmed"
        coordinator._handle_frame(module.frames.build(0x73, b"\x04\x01\x09\x00\x00", header=b"\x57\xa2\x06"))
        assert coordinator.data["fan_on"] is False
        await coordinator.async_set_fan(False)
        coordinator._handle_frame(module.frames.build(0x73, b"\x04\x01\x09\x00\x00", header=b"\x57\xa2\x06"))
        await asyncio.sleep(0.04)
        assert coordinator.data["fan_command_status"] == "observed"
        assert coordinator.data["fan_running"] is False

    asyncio.run(scenario())


def test_matching_fan_telemetry_during_send_is_observed(monkeypatch):
    module = _load(monkeypatch)
    monkeypatch.setattr(module, "FAN_RECONCILE_SECONDS", 0.02)

    async def scenario():
        coordinator = module.ChefsTempCoordinator(SimpleNamespace(loop=asyncio.get_running_loop()), SimpleNamespace(data={"mac": "unused"}, title="stand"), SimpleNamespace())
        coordinator.push_connected = True
        coordinator._transport = SimpleNamespace()
        started = asyncio.Event()
        release = asyncio.Event()

        async def send(frame):
            assert frame[8] == module.frames.FAN_OFF
            started.set()
            await release.wait()

        coordinator._async_send = send
        task = asyncio.create_task(coordinator.async_set_fan(False))
        await started.wait()
        coordinator._handle_frame(module.frames.build(0x73, b"\x04\x01\x09\x00\x00", header=b"\x57\xa2\x06"))
        assert coordinator.data["fan_command_status"] == "pending"
        release.set()
        await task
        await asyncio.sleep(0.04)
        assert coordinator.data["fan_on"] is False
        assert coordinator.data["fan_command_status"] == "observed"

    asyncio.run(scenario())


@pytest.mark.parametrize("disconnect", [False, True])
def test_failed_or_disconnected_publish_does_not_claim_success(monkeypatch, disconnect):
    module = _load(monkeypatch)

    async def scenario():
        coordinator = module.ChefsTempCoordinator(SimpleNamespace(loop=asyncio.get_running_loop()), SimpleNamespace(data={"mac": "unused"}, title="stand"), SimpleNamespace())
        coordinator.push_connected = True
        coordinator._transport = SimpleNamespace()

        async def send(frame):
            if disconnect:
                coordinator._handle_connect_change(False)
            else:
                raise RuntimeError("publish failed")

        coordinator._async_send = send
        if disconnect:
            await coordinator.async_set_fan(True)
        else:
            with pytest.raises(RuntimeError, match="publish failed"):
                await coordinator.async_set_fan(True)
        assert coordinator.data["fan_on"] is False
        assert coordinator.data["fan_command_status"] == "unconfirmed"

    asyncio.run(scenario())


def test_latest_command_wins_and_idle_thermostat_is_enabled(monkeypatch):
    module = _load(monkeypatch)
    monkeypatch.setattr(module, "FAN_RECONCILE_SECONDS", 0.02)

    async def scenario():
        coordinator = module.ChefsTempCoordinator(SimpleNamespace(loop=asyncio.get_running_loop()), SimpleNamespace(data={"mac": "unused"}, title="stand"), SimpleNamespace())
        coordinator.push_connected = True
        coordinator._transport = SimpleNamespace()
        sent = []
        first = asyncio.Event()
        release = asyncio.Event()

        async def send(frame):
            sent.append(frame[8])
            if len(sent) == 1:
                first.set()
                await release.wait()

        coordinator._async_send = send
        on = asyncio.create_task(coordinator.async_set_fan(True))
        await first.wait()
        off = asyncio.create_task(coordinator.async_set_fan(False))
        release.set()
        await asyncio.gather(on, off)
        assert sent == [module.frames.FAN_ON, module.frames.FAN_OFF]
        assert coordinator.data["fan_on"] is False
        coordinator._handle_frame(module.frames.build(0x73, b"\x04\x01\x09\x00\x00", header=b"\x57\xa2\x06"))
        await asyncio.sleep(0.04)
        assert coordinator.data["fan_command_status"] == "observed"
        await coordinator.async_set_fan(True)
        coordinator._handle_frame(module.frames.build(0x73, b"\x04\x01\x09\x02\x00", header=b"\x57\xa2\x06"))
        assert coordinator.data["fan_on"] is True
        assert coordinator.data["fan_running"] is False

    asyncio.run(scenario())


def test_cloud_setpoints_are_adopted_only_when_the_official_app_changes_them(monkeypatch):
    module = _load(monkeypatch)

    async def scenario():
        coordinator = module.ChefsTempCoordinator(SimpleNamespace(loop=asyncio.get_running_loop()), SimpleNamespace(data={"mac": "unused"}, title="stand"), SimpleNamespace())
        sent = []

        async def send(frame):
            sent.append(frame)

        coordinator._async_send = send

        def poll(fan, high, low):
            device = {"fan": {"temperature": fan}, "alarm_high": high, "alarm_low": low}
            data = dict(coordinator.data)
            coordinator._sync_from_cloud(device, data)
            coordinator.async_set_updated_data(data)

        poll(115.0, 130.0, 95.0)
        assert (coordinator.data["fan_target"], coordinator.data["alarm_high"], coordinator.data["alarm_low"]) == (115, 130, 95)

        await coordinator.async_set_high_alarm(150)
        await coordinator.async_set_fan_target(120)
        poll(115.0, 130.0, 95.0)
        assert coordinator.data["alarm_high"] == 150
        assert coordinator.data["fan_target"] == 120
        assert coordinator.fan_target == 120

        sent.clear()
        poll(200.4273732319118, 220.0, 180.0)
        assert (coordinator.data["fan_target"], coordinator.data["alarm_high"], coordinator.data["alarm_low"]) == (200, 220, 180)
        assert coordinator.fan_target == 200
        assert sent == []

        poll(200.4273732319118, None, "bad")
        assert (coordinator.data["alarm_high"], coordinator.data["alarm_low"]) == (220, 180)

    asyncio.run(scenario())


def test_probe_counts_are_batched_reset_and_do_not_retain_payload(monkeypatch):
    module = _load(monkeypatch)
    monkeypatch.setattr(module, "PROBE_DIAGNOSTICS_SECONDS", 0.02)

    async def scenario():
        loop = asyncio.get_running_loop()
        coordinator = module.ChefsTempCoordinator(
            SimpleNamespace(loop=loop),
            SimpleNamespace(data={"mac": "unused"}, title="stand"),
            SimpleNamespace(),
        )
        writes = []
        original = coordinator.async_set_updated_data

        def record(data):
            writes.append(data)
            original(data)

        coordinator.async_set_updated_data = record
        up = b"\x57\xa2\x06"
        good = module.frames.build(0x20, b"\x00\x32\x00\xc8\x3c\xaf", header=up)
        other = module.frames.build(0x20, b"\x01\x32\x01\x18\x50\xb0", header=up)
        bad = good[:-1] + bytes((good[-1] ^ 1,))
        coordinator._handle_frame(bad + other)
        coordinator._handle_frame(bad + good)
        coordinator._handle_frame(b"\xaa\x55" + up + b"\x20\x06")
        assert len(writes) == 2  # only the two accepted probe events, not rejects
        assert coordinator.data["probe_frame_counts"]["probe_1"]["received"] == 0
        await asyncio.sleep(0.04)
        assert len(writes) == 3  # one aggregate publication
        assert coordinator.data["probe_frame_counts"] == {
            "probe_1": {"received": 3, "accepted": 1, "rejected": 2},
            "probe_2": {"received": 1, "accepted": 1, "rejected": 0},
            "unindexed": {"received": 1, "accepted": 0, "rejected": 1},
        }
        assert "unused" not in repr(coordinator.data["probe_frame_counts"])
        assert good.hex() not in repr(coordinator.data["probe_frame_counts"])
        fresh = module.ChefsTempCoordinator(
            SimpleNamespace(loop=loop),
            SimpleNamespace(data={"mac": "unused"}, title="stand"),
            SimpleNamespace(),
        )
        assert fresh.data["probe_frame_counts"] == {
            "probe_1": {"received": 0, "accepted": 0, "rejected": 0}
        }
        coordinator._handle_frame(bad)
        assert coordinator._probe_diagnostics_timer is not None
        await coordinator.async_shutdown()
        assert coordinator._probe_diagnostics_timer is None
        await asyncio.sleep(0.04)
        assert len(writes) == 3  # cancelled timer cannot publish after unload

    asyncio.run(scenario())


def test_repeated_equal_ambient_frames_advance_only_mqtt_sample_timestamp(monkeypatch):
    module = _load(monkeypatch)
    times = iter((datetime(2026, 9, 29, 12, 0, tzinfo=UTC),
                  datetime(2026, 9, 29, 12, 1, tzinfo=UTC)))

    class Clock:
        @staticmethod
        def now(_timezone):
            return next(times)

    monkeypatch.setattr(module, "datetime", Clock)
    coordinator = module.ChefsTempCoordinator(
        SimpleNamespace(), SimpleNamespace(data={"mac": "unused"}, title="stand"),
        SimpleNamespace(),
    )
    ambient_frame = bytes.fromhex("aa5557a2067102002293")
    coordinator._handle_frame(ambient_frame)
    first = coordinator.data["ambient_sample_at"]
    assert coordinator.data["ambient"] == 34
    coordinator._handle_frame(ambient_frame)
    assert coordinator.data["ambient"] == 34
    assert coordinator.data["ambient_sample_at"] > first
    coordinator._apply_event({"type": "stand_battery", "percent": 50}, coordinator.data)
    assert coordinator.data["ambient_sample_at"] == "2026-09-29T12:01:00+00:00"
