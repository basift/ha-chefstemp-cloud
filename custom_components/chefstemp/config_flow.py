"""Config flow for ChefsTemp."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ChefsTempApi, ChefsTempAuthError, ChefsTempError
from .const import CONF_DEVICE_MAC, CONF_DEVICE_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class ChefsTempConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Sign in to ChefsTemp and pick a stand."""

    VERSION = 1

    def __init__(self) -> None:
        """Start with nothing signed in."""
        self._email: str | None = None
        self._password: str | None = None
        self._devices: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect ChefsTemp credentials and load the account's stands."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api = ChefsTempApi(async_get_clientsession(self.hass))
            try:
                await api.async_login(
                    user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
                )
                devices = await api.async_get_devices()
            except ChefsTempAuthError:
                errors["base"] = "invalid_auth"
            except ChefsTempError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error signing in to ChefsTemp")
                errors["base"] = "unknown"
            else:
                if not devices:
                    errors["base"] = "no_devices"
                else:
                    self._email = user_input[CONF_EMAIL]
                    self._password = user_input[CONF_PASSWORD]
                    self._devices = devices
                    return await self.async_step_device()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose which stand to add, if the account has more than one."""
        if len(self._devices) == 1:
            return await self._async_create(self._devices[0])

        if user_input is not None:
            chosen = next(
                (d for d in self._devices if d["mac"] == user_input[CONF_DEVICE_MAC]),
                None,
            )
            if chosen is not None:
                return await self._async_create(chosen)

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_MAC): vol.In(
                        {d["mac"]: d["name"] for d in self._devices}
                    )
                }
            ),
        )

    async def _async_create(self, device: dict[str, Any]) -> ConfigFlowResult:
        """Create the entry for one stand."""
        await self.async_set_unique_id(device["mac"])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=device["name"],
            data={
                CONF_EMAIL: self._email,
                CONF_PASSWORD: self._password,
                CONF_DEVICE_MAC: device["mac"],
                CONF_DEVICE_NAME: device["name"],
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """The cloud rejected the stored credentials; ask again."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-authenticate an existing entry."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            api = ChefsTempApi(async_get_clientsession(self.hass))
            try:
                await api.async_login(
                    user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
                )
                devices = await api.async_get_devices()
            except ChefsTempAuthError:
                errors["base"] = "invalid_auth"
            except ChefsTempError:
                errors["base"] = "cannot_connect"
            else:
                known = {d["mac"] for d in devices}
                if entry.data[CONF_DEVICE_MAC] not in known:
                    errors["base"] = "wrong_account"
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={
                            CONF_EMAIL: user_input[CONF_EMAIL],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                        },
                    )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders={"account": entry.title},
        )
