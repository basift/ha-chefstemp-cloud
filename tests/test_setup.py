"""Exercise entry startup without importing the Home Assistant runtime."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import ClassVar

import pytest


def _load_setup(monkeypatch):
    class ConfigEntryAuthFailed(Exception):
        pass

    class ConfigEntryNotReady(Exception):
        pass

    class ChefsTempAuthError(Exception):
        pass

    class ChefsTempError(Exception):
        pass

    def stub(name, **attrs):
        module = ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
        return module

    stub("homeassistant", __path__=[])
    stub("homeassistant.const", CONF_EMAIL="email", CONF_PASSWORD="password", Platform=SimpleNamespace(FAN="fan", NUMBER="number", SENSOR="sensor"))
    stub("homeassistant.core", HomeAssistant=object)
    stub("homeassistant.exceptions", ConfigEntryAuthFailed=ConfigEntryAuthFailed, ConfigEntryNotReady=ConfigEntryNotReady)
    stub("homeassistant.helpers", __path__=[])
    stub("homeassistant.helpers.aiohttp_client", async_get_clientsession=lambda hass: None)
    stub("custom_components", __path__=[])
    stub("custom_components.chefstemp", __path__=[])
    stub("custom_components.chefstemp.api", ChefsTempApi=lambda *args, **kwargs: None, ChefsTempAuthError=ChefsTempAuthError, ChefsTempError=ChefsTempError)

    class Coordinator:
        refresh_error = None
        push_error = None
        instances: ClassVar[list] = []

        def __init__(self, hass, entry, api):
            self.shutdowns = 0
            self.instances.append(self)

        async def async_config_entry_first_refresh(self):
            if self.refresh_error:
                raise self.refresh_error

        async def async_start_push(self):
            if self.push_error:
                raise self.push_error

        async def async_shutdown(self):
            self.shutdowns += 1

    stub("custom_components.chefstemp.coordinator", ChefsTempConfigEntry=object, ChefsTempCoordinator=Coordinator)
    path = Path(__file__).resolve().parent.parent / "custom_components" / "chefstemp" / "__init__.py"
    spec = importlib.util.spec_from_file_location("custom_components.chefstemp", path, submodule_search_locations=[str(path.parent)])
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module, Coordinator, ConfigEntryAuthFailed, ConfigEntryNotReady, ChefsTempAuthError


@pytest.mark.parametrize("stage", ["push", "forward", "success"])
def test_setup_cleans_partial_start_and_retries_broker(monkeypatch, stage):
    module, coordinator, _, not_ready, _ = _load_setup(monkeypatch)
    if stage == "push":
        coordinator.push_error = OSError("broker unavailable")

    class Entries:
        async def async_forward_entry_setups(self, entry, platforms):
            if stage == "forward":
                raise RuntimeError("platform failed")

    hass = SimpleNamespace(config_entries=Entries())
    entry = SimpleNamespace(data={"email": "test@example.com", "password": "unused"}, async_on_unload=lambda listener: None, add_update_listener=lambda listener: listener)
    if stage != "success":
        with pytest.raises(not_ready if stage == "push" else RuntimeError):
            asyncio.run(module.async_setup_entry(hass, entry))
    else:
        assert asyncio.run(module.async_setup_entry(hass, entry)) is True
    assert coordinator.instances[-1].shutdowns == (0 if stage == "success" else 1)


@pytest.mark.parametrize("error_kind", ["auth", "other"])
def test_refresh_error_semantics_unchanged(monkeypatch, error_kind):
    module, coordinator, auth_failed, not_ready, auth_error = _load_setup(monkeypatch)
    api_module = sys.modules["custom_components.chefstemp.api"]
    coordinator.refresh_error = (
        auth_error("invalid") if error_kind == "auth" else api_module.ChefsTempError("offline")
    )
    entry = SimpleNamespace(data={"email": "test@example.com", "password": "unused"})
    hass = SimpleNamespace()
    with pytest.raises(auth_failed if error_kind == "auth" else not_ready):
        asyncio.run(module.async_setup_entry(hass, entry))
    assert coordinator.instances[-1].shutdowns == 0
