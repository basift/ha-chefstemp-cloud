"""Diagnostics for ChefsTemp."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICE_MAC
from .coordinator import ChefsTempConfigEntry

# The device MAC is the MQTT topic key and effectively a shared secret on this
# vendor's broker, so it is redacted along with the account credentials.
REDACT = {CONF_EMAIL, CONF_PASSWORD, CONF_DEVICE_MAC, "device_mac"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ChefsTempConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry_data": async_redact_data(dict(entry.data), REDACT),
        "push_connected": coordinator.push_connected,
        "update_success": coordinator.last_update_success,
        "fan_target": coordinator.fan_target,
        "state": coordinator.data,
    }
