"""Publishing to MQTT is not itself confirmation from the stand."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


@pytest.mark.parametrize("result", ["disconnected", "timeout", "error", "dropped", "published"])
def test_send_requires_live_session_and_successful_publish(monkeypatch, result):
    root = Path(__file__).resolve().parent.parent / "custom_components" / "chefstemp"
    package = ModuleType("custom_components.chefstemp")
    package.__path__ = [str(root)]
    monkeypatch.setitem(sys.modules, "custom_components", ModuleType("custom_components"))
    monkeypatch.setitem(sys.modules, "custom_components.chefstemp", package)
    constants = ModuleType("custom_components.chefstemp.const")
    constants.MQTT_HOST = "unused.invalid"
    constants.MQTT_PASSWORD = "unused"
    constants.MQTT_PORT = 1883
    constants.MQTT_USERNAME_PREFIX = "unused_"
    monkeypatch.setitem(sys.modules, constants.__name__, constants)
    spec = importlib.util.spec_from_file_location("custom_components.chefstemp.mqtt", root / "mqtt.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    transport = module.CloudMqttTransport("test@example.com", "test-device", lambda frame: None)
    info = SimpleNamespace(
        wait_for_publish=lambda timeout: None,
        is_published=lambda: result in ("published", "dropped"),
        rc=module.mqtt.MQTT_ERR_SUCCESS if result != "error" else module.mqtt.MQTT_ERR_NO_CONN,
    )
    transport._client = SimpleNamespace(publish=lambda *args, **kwargs: info)
    transport._connected = result != "disconnected"
    if result == "dropped":
        info.wait_for_publish = lambda timeout: setattr(transport, "_connected", False)
    if result == "published":
        transport.send(b"command")
    else:
        with pytest.raises(RuntimeError, match=r"not connected|failed or timed out"):
            transport.send(b"command")
