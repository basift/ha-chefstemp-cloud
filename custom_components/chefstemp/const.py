"""Constants for the ChefsTemp integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "chefstemp"

# The entire vendor backend is one plaintext Linode host. REST, MQTT and OTA all
# live here; there is no TLS anywhere (see docs/PROTOCOL.md §2).
API_BASE: Final = "http://198.58.114.115:8000"
MQTT_HOST: Final = "198.58.114.115"
MQTT_PORT: Final = 1883

# The MQTT credentials the vendor firmware uses. The password is a static string
# shared across all devices; the username is derived from the account's email local
# part (e.g. user@example.com -> Android_user). Not secrets we chose.
MQTT_PASSWORD: Final = "12345678"
MQTT_USERNAME_PREFIX: Final = "Android_"

CONF_DEVICE_MAC: Final = "device_mac"
CONF_DEVICE_NAME: Final = "device_name"
CONF_BLE_MAC: Final = "ble_mac"

# Local BLE (GATT) to the stand. Same AA55 frames as the cloud, byte-identical.
# The stand advertises a random-static address; its fff0 service carries the
# telemetry notify characteristic and the command write characteristic.
BLE_SERVICE_UUID: Final = "0000fff0-0000-1000-8000-00805f9b34fb"
BLE_NOTIFY_UUID: Final = "0783b03e-8535-b5a0-7140-a304d2495cb8"
BLE_WRITE_UUID: Final = "0783b03e-8535-b5a0-7140-a304d2495cba"

# Live temperatures arrive by MQTT push; the poll only refreshes metadata
# (alarm setpoints, fan target, device presence) and re-authenticates. It is
# also how edits made in the vendor app reach HA, so it stays short.
DEFAULT_SCAN_INTERVAL: Final = 60

# The vendor JWT is short-lived and there is no refresh token, so the stored
# password is used to sign in again when it lapses.
TOKEN_REFRESH_MARGIN: Final = 300

# Sensible bounds for the number entities (deg C).
TEMP_MIN: Final = 0
TEMP_MAX: Final = 300

MANUFACTURER: Final = "ChefsTemp"
