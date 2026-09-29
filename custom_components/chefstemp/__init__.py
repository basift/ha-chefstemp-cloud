"""The ChefsTemp integration."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ChefsTempApi, ChefsTempAuthError, ChefsTempError
from .coordinator import ChefsTempConfigEntry, ChefsTempCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.FAN, Platform.NUMBER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ChefsTempConfigEntry) -> bool:
    """Set up one ChefsTemp stand."""
    api = ChefsTempApi(
        async_get_clientsession(hass),
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
    )
    coordinator = ChefsTempCoordinator(hass, entry, api)

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        raise
    except ChefsTempAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except ChefsTempError as err:
        raise ConfigEntryNotReady(str(err)) from err

    entry.runtime_data = coordinator
    started = False
    try:
        try:
            await coordinator.async_start_push()
        except OSError as err:
            raise ConfigEntryNotReady(str(err)) from err

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        entry.async_on_unload(entry.add_update_listener(_async_update_listener))
        started = True
        return True
    finally:
        if not started:
            await coordinator.async_shutdown()


async def async_unload_entry(hass: HomeAssistant, entry: ChefsTempConfigEntry) -> bool:
    """Unload a ChefsTemp stand."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return bool(unloaded)


async def _async_update_listener(
    hass: HomeAssistant, entry: ChefsTempConfigEntry
) -> None:
    """Reload when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)
