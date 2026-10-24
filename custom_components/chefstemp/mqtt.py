"""Cloud transport: the ChefsTemp stand over the vendor MQTT broker.

The stand is a WiFi hub that bridges its probes and fan to one plaintext MQTT
broker. It publishes telemetry frames on a topic named after its WiFi MAC and
accepts command frames on ``<MAC>/down`` — the same ``AA55`` frames as BLE.

The broker allows roughly one app session per account, but a distinct client id
avoids fighting the phone for the same session, so both can be connected at once.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable

import paho.mqtt.client as mqtt

from .const import MQTT_HOST, MQTT_PASSWORD, MQTT_PORT, MQTT_USERNAME_PREFIX
from .transport import ChefsTempTransport

_LOGGER = logging.getLogger(__name__)

KEEPALIVE = 60


def mqtt_username(email: str) -> str:
    """Derive the vendor MQTT username from the account email."""
    local = email.split("@", 1)[0]
    return f"{MQTT_USERNAME_PREFIX}{local}"


class CloudMqttTransport(ChefsTempTransport):
    """Talks to one stand through the vendor's MQTT broker."""

    def __init__(
        self,
        email: str,
        device_mac: str,
        on_frame: Callable[[bytes], None],
        on_connect_change: Callable[[bool], None] | None = None,
    ) -> None:
        """Set up the transport; no network activity until connect()."""
        super().__init__(on_frame, on_connect_change)
        self._username = mqtt_username(email)
        self._mac = device_mac.replace(":", "").upper()
        self._client: mqtt.Client | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        """Whether the MQTT session is up."""
        return self._connected

    @property
    def _uplink_topic(self) -> str:
        return self._mac

    @property
    def _downlink_topic(self) -> str:
        return f"{self._mac}/down"

    def connect(self) -> None:
        """Open the MQTT session (blocking; call from an executor)."""
        self.disconnect()
        # MQTT 3.1 (MQIsdp), as the firmware speaks. A random client id keeps us
        # from evicting the phone app's session.
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="ha-" + secrets.token_hex(6),
            protocol=mqtt.MQTTv31,
            clean_session=True,
        )
        client.username_pw_set(self._username, MQTT_PASSWORD)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=KEEPALIVE)
        client.loop_start()
        self._client = client

    def disconnect(self) -> None:
        """Close the MQTT session, if any."""
        if self._client is None:
            return
        client, self._client = self._client, None
        self._connected = False
        try:
            client.disconnect()
            client.loop_stop()
        except Exception:
            _LOGGER.debug("Ignoring error while closing MQTT", exc_info=True)

    def send(self, frame: bytes) -> None:
        """Publish a command frame to the stand's downlink topic."""
        if self._client is None or not self._connected:
            raise RuntimeError("MQTT transport is not connected")
        info = self._client.publish(self._downlink_topic, frame, qos=1)
        info.wait_for_publish(timeout=10)
        if not self._connected or not info.is_published() or info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError("MQTT publish failed or timed out")

    # ------------------------------------------------------------------
    # paho callbacks (run on paho's own thread)
    # ------------------------------------------------------------------

    def _on_connect(self, client, _userdata, _flags, reason_code, _props=None) -> None:
        if reason_code != 0:
            _LOGGER.warning("ChefsTemp MQTT refused the connection: %s", reason_code)
            self._set_connected(False)
            return
        client.subscribe(self._uplink_topic, qos=0)
        self._set_connected(True)

    def _on_disconnect(self, _client, _userdata, *args) -> None:
        self._set_connected(False)

    def _on_message(self, _client, _userdata, message: mqtt.MQTTMessage) -> None:
        self._on_frame(bytes(message.payload))

    def _set_connected(self, value: bool) -> None:
        self._connected = value
        if self._on_connect_change:
            self._on_connect_change(value)
