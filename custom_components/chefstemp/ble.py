"""Local BLE transport to a ChefsTemp stand.

The stand speaks the same ``AA55`` frames over a BLE GATT connection as it does
over the cloud (see docs/PROTOCOL.md §4b): telemetry streams from the notify
characteristic and commands are written to the write characteristic, with no
pairing or handshake. This manager keeps a persistent connection open through
Home Assistant's Bluetooth stack (a local adapter or an ESPHome proxy near the
grill) and reconnects on its own when the link drops, so the integration can
prefer this fast, cloud-independent path whenever the stand is reachable.

Unlike the cloud transport (paho on its own thread), bleak runs on the event
loop, so this class is async and its callbacks already fire on the loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback

from .const import BLE_NOTIFY_UUID, BLE_WRITE_UUID

_LOGGER = logging.getLogger(__name__)

# Delay between reconnection attempts. The stand only advertises (and so is only
# connectable) while its single external BLE slot is free — e.g. once the phone
# app lets go of it. So the loop polls at a short, steady cadence to grab the
# link within seconds of it becoming available, rather than backing off for a
# minute. A missed advert makes async_ble_device_from_address return at once, so
# this poll is cheap and does not hammer the adapter.
_RETRY_MIN = 5.0
_RETRY_MAX = 15.0


class BleManager:
    """Maintains one persistent GATT connection to the stand."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        name: str,
        on_frame: Callable[[bytes], None],
        on_connect_change: Callable[[bool], None],
    ) -> None:
        """Set up the manager; no I/O until async_start()."""
        self.hass = hass
        self._address = address.upper()
        self._name = name
        self._on_frame = on_frame
        self._on_connect_change = on_connect_change
        self._client: BleakClientWithServiceCache | None = None
        self._connected = False
        self._closing = False
        self._runner: asyncio.Task | None = None
        self._wake = asyncio.Event()

    @property
    def connected(self) -> bool:
        """Whether the GATT link is currently up and subscribed."""
        return self._connected

    def async_start(self) -> None:
        """Begin the connect/reconnect loop as a background task."""
        if self._runner is None:
            self._closing = False
            self._runner = self.hass.async_create_background_task(
                self._run(), name=f"chefstemp-ble-{self._address}"
            )

    async def async_stop(self) -> None:
        """Stop the loop and close any open connection."""
        self._closing = True
        self._wake.set()
        if self._runner is not None:
            self._runner.cancel()
            try:
                await self._runner
            except asyncio.CancelledError:
                pass
            self._runner = None
        await self._async_close_client()

    async def async_send(self, frame: bytes) -> None:
        """Write one command frame to the stand (raises if not connected)."""
        client = self._client
        if not self._connected or client is None:
            raise BleakError("BLE transport is not connected")
        await client.write_gatt_char(BLE_WRITE_UUID, frame, response=False)

    # ------------------------------------------------------------------
    # Internal connect / reconnect loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Connect, stay connected, and reconnect with backoff on failure."""
        delay = _RETRY_MIN
        while not self._closing:
            try:
                await self._async_connect_once()
                delay = _RETRY_MIN
                # Hold the connection until the disconnect callback wakes us.
                self._wake.clear()
                await self._wake.wait()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.debug("ChefsTemp BLE connect to %s failed: %s", self._address, err)
            await self._async_close_client()
            self._set_connected(False)
            if self._closing:
                break
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, _RETRY_MAX)

    async def _async_connect_once(self) -> None:
        """Establish the connection and subscribe to telemetry."""
        device = bluetooth.async_ble_device_from_address(
            self.hass, self._address, connectable=True
        )
        if device is None:
            raise BleakError(f"{self._address} not seen by any Bluetooth adapter yet")
        client = await establish_connection(
            BleakClientWithServiceCache,
            device,
            self._name,
            disconnected_callback=self._on_disconnected,
            ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                self.hass, self._address, connectable=True
            )
            or device,
        )
        self._client = client
        await client.start_notify(BLE_NOTIFY_UUID, self._on_notify)
        self._set_connected(True)
        _LOGGER.debug("ChefsTemp BLE connected to %s", self._address)

    @callback
    def _on_notify(self, _char: object, data: bytearray) -> None:
        """Forward a telemetry notification (already on the event loop)."""
        self._on_frame(bytes(data))

    def _on_disconnected(self, _client: BLEDevice | object) -> None:
        """bleak's disconnect callback: wake the loop to reconnect."""
        self._set_connected(False)
        self._wake.set()

    async def _async_close_client(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        try:
            await client.disconnect()
        except Exception:
            _LOGGER.debug("Ignoring error while closing BLE", exc_info=True)

    def _set_connected(self, value: bool) -> None:
        if value != self._connected:
            self._connected = value
            self._on_connect_change(value)
