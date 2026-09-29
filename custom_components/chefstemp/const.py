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
# baked into the app; the username is derived from the account's email local part
# (e.g. user@example.com -> Android_user). Not secrets we chose.
MQTT_PASSWORD: Final = "12345678"
MQTT_USERNAME_PREFIX: Final = "Android_"

CONF_DEVICE_MAC: Final = "device_mac"
CONF_DEVICE_NAME: Final = "device_name"

# Live temperatures arrive by MQTT push; the poll only refreshes metadata
# (alarm setpoints, fan target, device presence) and re-authenticates.
DEFAULT_SCAN_INTERVAL: Final = 300

# The vendor JWT is short-lived and there is no refresh token, so the stored
# password is used to sign in again when it lapses.
TOKEN_REFRESH_MARGIN: Final = 300

# Sensible bounds for the number entities (deg C).
TEMP_MIN: Final = 0
TEMP_MAX: Final = 300

MANUFACTURER: Final = "ChefsTemp"
