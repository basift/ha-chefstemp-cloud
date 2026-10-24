"""Client for the ChefsTemp cloud REST API.

The API is undocumented; everything here was derived by observing the official
app on the wire (see docs/PROTOCOL.md §2). It is a RuoYi-style Java backend that
answers with an ``{"state","msg","data"}`` envelope, over plain HTTP. Auth is a
raw JWT placed in the ``authorization`` header (no ``Bearer`` prefix), and there
is no refresh token — the access token is short-lived, so the client re-signs in
with the stored password when it lapses.

Device inventory lives in the user record as a stringified-JSON ``probe_1``
array; this client normalises it into plain dicts. Live temperatures do NOT come
from REST — they arrive over MQTT (see mqtt.py); REST is used for discovery and
to refresh metadata (alarm setpoints, fan target, presence).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import aiohttp

from .const import API_BASE, TOKEN_REFRESH_MARGIN

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class ChefsTempError(Exception):
    """Base error for this client."""


class ChefsTempAuthError(ChefsTempError):
    """Credentials were rejected."""


class ChefsTempApiError(ChefsTempError):
    """The API was reachable but returned an error."""


def _normalise_device(raw: dict[str, Any]) -> dict[str, Any]:
    """Turn one vendor device record (``probe_1`` entry) into a plain dict."""
    return {
        "mac": str(raw.get("w") or "").replace(":", "").upper(),  # WiFi MAC = topic key
        "ble_mac": raw.get("b"),
        "name": raw.get("n") or "ChefsTemp",
        "type": raw.get("t"),
        "probes": raw.get("p") or [],
        "fan": raw.get("f") if isinstance(raw.get("f"), dict) else _maybe_json(raw.get("f")),
        "alarm_high": raw.get("abH"),
        "alarm_low": raw.get("abL"),
        "alarm_enabled": raw.get("abSW"),
    }


def _maybe_json(value: Any) -> Any:
    """Parse a value that may be a JSON string, else return it unchanged."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


class ChefsTempApi:
    """Authenticated access to the ChefsTemp cloud."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str | None = None,
        password: str | None = None,
    ) -> None:
        """Initialise the client, optionally with stored credentials."""
        self._session = session
        self._email = email
        self._password = password
        self._token: str | None = None
        self._expires_at: float = 0.0

    @property
    def email(self) -> str | None:
        """The account email, used to derive the MQTT username."""
        return self._email

    async def async_login(self, email: str, password: str) -> None:
        """Sign in and remember the credentials for later re-authentication."""
        self._email = email
        self._password = password
        await self._async_authenticate()

    async def _async_authenticate(self) -> None:
        """Exchange the stored credentials for an access token."""
        if not self._email or not self._password:
            raise ChefsTempAuthError("No credentials available")
        data = await self._async_post(
            "/api/sso/login",
            {"email": self._email, "password": self._password},
            authed=False,
        )
        token = data.get("access_token") if isinstance(data, dict) else None
        if not token:
            raise ChefsTempApiError("Login response did not contain an access token")
        self._token = token
        expires_in = float(data.get("expires_in", 259200))
        self._expires_at = time.monotonic() + expires_in - TOKEN_REFRESH_MARGIN

    async def _async_ensure_token(self) -> None:
        """Make sure a usable token is in hand, signing in again if needed."""
        if self._token and time.monotonic() < self._expires_at:
            return
        await self._async_authenticate()

    async def _async_post(
        self, path: str, body: dict[str, Any], *, authed: bool
    ) -> Any:
        """POST and unwrap the response envelope."""
        headers = {}
        if authed:
            await self._async_ensure_token()
            headers["authorization"] = self._token or ""
        return await self._async_request("POST", path, json_body=body, headers=headers)

    async def _async_request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Make one request and unwrap the ``{state,msg,data}`` envelope."""
        try:
            async with self._session.request(
                method,
                f"{API_BASE}{path}",
                json=json_body,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                payload = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise ChefsTempApiError(f"Cannot reach ChefsTemp: {err}") from err

        if not isinstance(payload, dict):
            raise ChefsTempApiError("Unexpected response shape")
        state = payload.get("state")
        if state in (401, 403):
            raise ChefsTempAuthError(payload.get("msg") or "Not authorised")
        if state != 200:
            raise ChefsTempApiError(payload.get("msg") or f"API error {state}")
        return payload.get("data")

    async def async_get_user(self) -> dict[str, Any]:
        """Fetch the full user record (devices, alarms, fan config, cook state)."""
        await self._async_ensure_token()
        data = await self._async_request(
            "GET",
            "/api/system/sys-user",
            headers={"authorization": self._token or ""},
        )
        return data if isinstance(data, dict) else {}

    async def async_get_devices(self) -> list[dict[str, Any]]:
        """List the stands on this account, normalised into plain dicts."""
        user = await self.async_get_user()
        raw = _maybe_json(user.get("probe_1")) or []
        if not isinstance(raw, list):
            return []
        return [_normalise_device(d) for d in raw if isinstance(d, dict) and d.get("w")]
