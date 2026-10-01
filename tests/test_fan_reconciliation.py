"""Fan coordinator behavior with an isolated Home Assistant runtime."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
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
