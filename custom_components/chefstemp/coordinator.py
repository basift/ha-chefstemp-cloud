"""Keeps one stand's state in sync, over MQTT push with a REST safety net.

Live values (grill temp, probe temp/battery/signal, fan running state, stand
battery) arrive as pushed MQTT frames and are decoded by frames.py. The REST
poll only refreshes metadata that telemetry never carries — whether the device
is still on the account, and the initial seed for the fan target and the alarm
setpoints. Those setpoints are then owned by Home Assistant: a device command
does not update the cloud copy, so re-reading it would clobber the user's value.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import frames
from .api import ChefsTempApi, ChefsTempAuthError, ChefsTempError
from .const import CONF_DEVICE_MAC, DEFAULT_SCAN_INTERVAL, DOMAIN
from .mqtt import CloudMqttTransport

_LOGGER = logging.getLogger(__name__)

type ChefsTempConfigEntry = ConfigEntry["ChefsTempCoordinator"]

DEFAULT_FAN_TARGET = 110
FAN_RECONCILE_SECONDS = 5
PROBE_DIAGNOSTICS_SECONDS = 60


def _empty_state() -> dict[str, Any]:
    return {
        "available": False,
        "ambient": None,
        "fan_on": False,
        "fan_enabled": None,
        "fan_running": None,
        "fan_command_status": None,
        "fan_strength": 0,
        "stand_battery": None,
        "probes": {},
        "probe_frame_counts": {"probe_1": {"received": 0, "accepted": 0, "rejected": 0}},
        "alarm_high": None,
        "alarm_low": None,
        "fan_target": None,
    }


class ChefsTempCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """State, MQTT lifecycle and command dispatch for a single stand."""

    config_entry: ChefsTempConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ChefsTempConfigEntry,
        api: ChefsTempApi,
    ) -> None:
        """Initialise the coordinator for one stand."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api
        self.device_mac = entry.data[CONF_DEVICE_MAC]
        self.device_name = entry.title
        self.push_connected = False
        self.temperature_unit_override: str | None = None

        # Fan setpoint state HA owns and rebuilds full op20 frames from.
        self.fan_target = DEFAULT_FAN_TARGET
        self.fan_strength = frames.FAN_STRENGTH
        self.fan_seconds = frames.FAN_SECONDS
        self._seeded = False
        self._fan_lock = asyncio.Lock()
        self._fan_pending: bool | None = None
        self._fan_timer: asyncio.TimerHandle | None = None
        self._fan_seen_matching = False
        # Bounded by the one-byte probe index; None groups truncated candidates.
        self._probe_frame_counts: dict[int | None, list[int]] = {0: [0, 0]}
        self._probe_diagnostics_timer: asyncio.TimerHandle | None = None

        self._transport: CloudMqttTransport | None = None
        self.data = _empty_state()

    # ------------------------------------------------------------------
    # Polling (metadata only)
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Refresh device presence and seed setpoints once."""
        try:
            devices = await self.api.async_get_devices()
        except ChefsTempAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ChefsTempError as err:
            raise UpdateFailed(str(err)) from err

        device = next(
            (d for d in devices if d["mac"] == self.device_mac), None
        )
        data = dict(self.data)
        data["available"] = device is not None
        if device is not None:
            self._seed_from_cloud(device, data)
        return data

    def _seed_from_cloud(self, device: dict[str, Any], data: dict[str, Any]) -> None:
        """Take the initial fan target and alarm setpoints from the cloud copy.

        Only on first load: afterwards HA owns these, since the device does not
        echo them back over telemetry and does not sync HA's writes to the cloud.
        """
        if self._seeded:
            return
        fan = device.get("fan") or {}
        if isinstance(fan, dict) and fan.get("temperature") is not None:
            try:
                self.fan_target = round(float(fan["temperature"]))
            except (TypeError, ValueError):
                pass
        data["fan_target"] = self.fan_target
        for key, src in (("alarm_high", "alarm_high"), ("alarm_low", "alarm_low")):
            value = device.get(src)
            if value is not None:
                try:
                    data[key] = round(float(value))
                except (TypeError, ValueError):
                    pass
        self._seeded = True

    # ------------------------------------------------------------------
    # Live updates (MQTT push)
    # ------------------------------------------------------------------

    async def async_start_push(self) -> None:
        """Open the MQTT channel for this stand."""
        self._transport = CloudMqttTransport(
            email=self.api.email or "",
            device_mac=self.device_mac,
            on_frame=self._threadsafe(self._handle_frame),
            on_connect_change=self._threadsafe(self._handle_connect_change),
        )
        await self.hass.async_add_executor_job(self._transport.connect)

    def _threadsafe(self, func):
        """Wrap a callback so paho's thread can invoke it on the event loop."""

        def _wrapped(*args):
            self.hass.loop.call_soon_threadsafe(func, *args)

        return _wrapped

    @callback
    def _handle_connect_change(self, connected: bool) -> None:
        self.push_connected = connected
        if not connected and self._fan_pending is not None:
            self._finish_fan_command(False)

    @callback
    def _handle_frame(self, payload: bytes) -> None:
        """Decode a pushed payload and apply every event it carries."""
        events = frames.parse(payload, self._count_probe_candidate)
        if not events:
            return
        data = dict(self.data)
        data["probes"] = dict(data["probes"])
        changed = False
        for event in events:
            changed |= self._apply_event(event, data)
        if changed:
            data["available"] = True
            self.async_set_updated_data(data)

    @callback
    def _count_probe_candidate(self, idx: int | None, accepted: bool) -> None:
        """Accumulate only counts; never retain frame contents or identifiers."""
        counts = self._probe_frame_counts.setdefault(idx, [0, 0])
        counts[0] += 1
        counts[1] += int(accepted)
        if self._probe_diagnostics_timer is None:
            self._probe_diagnostics_timer = self.hass.loop.call_later(
                PROBE_DIAGNOSTICS_SECONDS, self._publish_probe_counts
            )

    @callback
    def _publish_probe_counts(self) -> None:
        """Publish one aggregated snapshot at most once per interval."""
        self._probe_diagnostics_timer = None
        counts = {
            "unindexed" if idx is None else f"probe_{idx + 1}": {
                "received": values[0],
                "accepted": values[1],
                "rejected": values[0] - values[1],
            }
            for idx, values in self._probe_frame_counts.items()
        }
        data = dict(self.data)
        data["probe_frame_counts"] = counts
        self.async_set_updated_data(data)

    def _apply_event(self, event: dict[str, Any], data: dict[str, Any]) -> bool:
        """Merge one decoded event into the state; return whether it changed."""
        kind = event["type"]
        if kind == "ambient":
            data["ambient"] = event["celsius"]
        elif kind == "fan":
            data["fan_enabled"] = event["on"]
            data["fan_running"] = event["on"] and event["strength"] > 0
            data["fan_strength"] = event["strength"]
            if self._fan_pending is None:
                data["fan_on"] = event["on"]
            else:
                self._fan_seen_matching = event["on"] == self._fan_pending
        elif kind == "stand_battery":
            data["stand_battery"] = event["percent"]
        elif kind == "probe":
            data["probes"][event["idx"]] = {
                "celsius": event["celsius"],
                "battery": event["battery"],
                "rssi": event["rssi"],
            }
        else:
            return False
        return True

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def _async_send(self, frame: bytes) -> None:
        """Send one command frame over the active transport."""
        if self._transport is None:
            raise UpdateFailed("No transport is connected")
        await self.hass.async_add_executor_job(self._transport.send, frame)

    async def async_set_fan(self, on: bool) -> None:
        """Enable the fan thermostat, or force it off."""
        async with self._fan_lock:
            frame = (
                frames.fan_on(self.fan_target, self.fan_strength, self.fan_seconds)
                if on
                else frames.fan_off(self.fan_target, self.fan_strength, self.fan_seconds)
            )
            self._cancel_fan_timer()
            self._fan_pending = on
            self._fan_seen_matching = False
            data = dict(self.data)
            data["fan_on"] = on
            data["fan_command_status"] = "pending"
            self.async_set_updated_data(data)
            try:
                await self._async_send(frame)
            except BaseException:
                self._finish_fan_command(False)
                raise
            if self.push_connected and self._fan_pending is on:
                self._fan_timer = self.hass.loop.call_later(
                    FAN_RECONCILE_SECONDS, self._expire_fan_command
                )
            elif self._fan_pending is not None:
                self._finish_fan_command(False)

    def _cancel_fan_timer(self) -> None:
        if self._fan_timer is not None:
            self._fan_timer.cancel()
            self._fan_timer = None

    @callback
    def _expire_fan_command(self) -> None:
        self._finish_fan_command(self._fan_seen_matching)

    @callback
    def _finish_fan_command(
        self, observed: bool, data: dict[str, Any] | None = None
    ) -> None:
        """Resolve the optimistic overlay on observation, timeout or disconnect."""
        self._cancel_fan_timer()
        desired = self._fan_pending
        self._fan_pending = None
        state = data if data is not None else dict(self.data)
        state["fan_on"] = state["fan_enabled"] if state["fan_enabled"] is not None else False
        state["fan_command_status"] = (
            "observed" if observed and state["fan_enabled"] == desired else "unconfirmed"
        )
        if data is None:
            self.async_set_updated_data(state)

    async def async_set_fan_target(self, target_c: int) -> None:
        """Change the fan setpoint; re-apply immediately if the fan is on."""
        async with self._fan_lock:
            self.fan_target = int(target_c)
            data = dict(self.data)
            data["fan_target"] = self.fan_target
            self.async_set_updated_data(data)
            if self.data.get("fan_on"):
                await self._async_send(
                    frames.fan_on(self.fan_target, self.fan_strength, self.fan_seconds)
                )

    async def async_set_high_alarm(self, temp_c: int) -> None:
        """Set the ambient high alarm."""
        await self._async_send(frames.high_alarm(int(temp_c)))
        data = dict(self.data)
        data["alarm_high"] = int(temp_c)
        self.async_set_updated_data(data)

    async def async_set_low_alarm(self, temp_c: int) -> None:
        """Set the ambient low alarm."""
        await self._async_send(frames.low_alarm(int(temp_c)))
        data = dict(self.data)
        data["alarm_low"] = int(temp_c)
        self.async_set_updated_data(data)

    async def async_shutdown(self) -> None:
        """Close the MQTT channel."""
        self._cancel_fan_timer()
        if self._probe_diagnostics_timer is not None:
            self._probe_diagnostics_timer.cancel()
            self._probe_diagnostics_timer = None
        if self._transport is not None:
            await self.hass.async_add_executor_job(self._transport.disconnect)
            self._transport = None
        await super().async_shutdown()
