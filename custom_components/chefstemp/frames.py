"""ChefsTemp binary frame protocol (the ``AA55`` frames).

Kept free of Home Assistant, MQTT and Bluetooth imports so it can be exercised
on its own and reused by any transport — the frames are byte-identical over the
cloud MQTT channel and over local BLE. See ``docs/PROTOCOL.md`` for how each
field was established on the wire.

Frame layout (both directions)::

    AA 55 <b2> <h1> <h2> <op> <len> <payload...> <cksum>

* Downlink (app -> device) header is ``53 81 07``. The third byte MUST be ``07``;
  frames with ``08`` are silently ignored by the device.
* Uplink (device -> app) telemetry header is ``57 A2 06``; a command echo comes
  back with ``57 A2 07``. The ``b2`` byte is usually ``57``/``53`` but the stand
  status frame (op ``10``) uses ``58`` — so decoding keys off ``h1``/``op``, not
  ``b2``.
* ``cksum = (sum(bytes from b2 through the last payload byte) - 1) & 0xFF``.
"""

from __future__ import annotations

from typing import Any

_SYNC = bytes((0xAA, 0x55))
HEADER_DOWN = bytes((0x53, 0x81, 0x07))  # app -> device (commands)

# Uplink markers, checked as (h1, h2).
_H1 = 0xA2
_H2_TELEMETRY = 0x06
_H2_ECHO = 0x07

# Opcodes.
OP_STAND = 0x10
OP_FAN_SET = 0x20
OP_PROBE = 0x20
OP_LOW_ALARM = 0x75
OP_HIGH_ALARM = 0x76
OP_AMBIENT = 0x71
OP_FAN_STATE = 0x73

FAN_OFF = 0x00
FAN_ON = 0x02

# The app sends this fixed dwell in every fan command; it is not a usable short
# timer (a small value did not auto-stop the fan), so it is kept constant.
FAN_SECONDS = 0x0DBD
FAN_STRENGTH = 0x02  # device auto-ramps its own strength; this value is nominal.


def _checksum(body: bytes) -> int:
    """Checksum over the body (b2 through the last payload byte)."""
    return (sum(body) - 1) & 0xFF


def build(op: int, payload: bytes, header: bytes = HEADER_DOWN) -> bytes:
    """Assemble a complete frame with a valid checksum."""
    body = bytes(header) + bytes((op, len(payload))) + bytes(payload)
    return _SYNC + body + bytes((_checksum(body),))


def verify(frame: bytes) -> bool:
    """Whether a frame's trailing checksum matches its body."""
    if len(frame) < 8 or frame[:2] != _SYNC:
        return False
    op_len = frame[6]
    end = 7 + op_len
    if len(frame) < end + 1:
        return False
    return _checksum(frame[2:end]) == frame[end]


# ---------------------------------------------------------------------------
# Command builders (downlink)
# ---------------------------------------------------------------------------


def fan_command(mode: int, target_c: int, strength: int = FAN_STRENGTH,
                seconds: int = FAN_SECONDS) -> bytes:
    """Build a fan command.

    The device treats the fan as a thermostat: with ``mode`` on it runs whenever
    ``target_c`` is above the grill ambient and idles otherwise, choosing its own
    strength. ``mode`` off force-stops it regardless of target. One frame carries
    mode, target and strength together, so callers pass the whole desired state.
    """
    payload = (
        bytes((0x09, mode))
        + int(seconds).to_bytes(2, "big")
        + int(target_c).to_bytes(2, "big")
        + bytes((strength & 0xFF,))
    )
    return build(OP_FAN_SET, payload)


def fan_on(target_c: int, strength: int = FAN_STRENGTH,
           seconds: int = FAN_SECONDS) -> bytes:
    """Enable the fan thermostat at ``target_c``."""
    return fan_command(FAN_ON, target_c, strength, seconds)


def fan_off(target_c: int = 0, strength: int = FAN_STRENGTH,
            seconds: int = FAN_SECONDS) -> bytes:
    """Force the fan off."""
    return fan_command(FAN_OFF, target_c, strength, seconds)


def high_alarm(temp_c: int) -> bytes:
    """Set the ambient high alarm (deg C)."""
    return build(OP_HIGH_ALARM, int(temp_c).to_bytes(2, "big"))


def low_alarm(temp_c: int) -> bytes:
    """Set the ambient low alarm (deg C)."""
    return build(OP_LOW_ALARM, int(temp_c).to_bytes(2, "big"))


def ping() -> bytes:
    """A no-op refresh ping (the app sends this periodically)."""
    return build(OP_STAND, bytes((0x00,)))


# ---------------------------------------------------------------------------
# Telemetry parsing (uplink)
# ---------------------------------------------------------------------------


def _s8(value: int) -> int:
    """Interpret a byte as a signed 8-bit integer."""
    return value - 256 if value > 127 else value


def split_frames(data: bytes) -> list[bytes]:
    """Split a payload into ``AA55``-delimited frames.

    A single MQTT message (or BLE notification) sometimes concatenates several
    frames, and may carry trailing ASCII keepalive text; both are handled by
    slicing on the sync word and letting each decoder read only its own length.
    """
    frames: list[bytes] = []
    i = data.find(_SYNC)
    while i >= 0:
        j = data.find(_SYNC, i + 2)
        frames.append(data[i:] if j < 0 else data[i:j])
        i = j
    return frames


def _decode_one(frame: bytes) -> dict[str, Any] | None:
    """Decode a single uplink frame into an event dict, or None."""
    if len(frame) < 8 or frame[:2] != _SYNC:
        return None
    if frame[3] != _H1 or frame[4] not in (_H2_TELEMETRY, _H2_ECHO):
        return None
    op = frame[5]
    length = frame[6]
    payload = frame[7:7 + length]
    if len(payload) < length:
        return None

    if op == OP_AMBIENT and length >= 2:
        return {"type": "ambient", "celsius": int.from_bytes(payload[:2], "big")}

    if op == OP_PROBE and frame[4] == _H2_TELEMETRY and length >= 6 and payload[1] == 0x32:
        # <idx><b1=0x32 const><temp u16 BE /10><battery %><rssi int8>
        return {
            "type": "probe",
            "idx": payload[0],
            "celsius": int.from_bytes(payload[2:4], "big") / 10,
            "battery": payload[4],
            "rssi": _s8(payload[5]),
        }

    if op == OP_FAN_STATE and length >= 2:
        # <moduleMAC 6> 04 01 09 <mode> <strength>
        return {
            "type": "fan",
            "mode": payload[-2],
            "strength": payload[-1],
            "on": payload[-2] == FAN_ON,
        }

    if op == OP_STAND and frame[4] == _H2_TELEMETRY and length >= 1:
        return {"type": "stand_battery", "percent": payload[0]}

    return None


def parse(data: bytes) -> list[dict[str, Any]]:
    """Decode every understood uplink frame in a payload."""
    events: list[dict[str, Any]] = []
    for frame in split_frames(data):
        event = _decode_one(frame)
        if event is not None:
            events.append(event)
    return events
