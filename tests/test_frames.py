"""Tests for the ChefsTemp frame codec.

The bytes below are the real shapes seen on the wire (see docs/PROTOCOL.md §4b):
command frames the device accepted, and uplink telemetry it produced. ``frames``
is dependency-free, so it is loaded directly from its file to keep this suite
runnable without Home Assistant installed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_FRAMES_PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "chefstemp"
    / "frames.py"
)
_spec = importlib.util.spec_from_file_location("chefstemp_frames", _FRAMES_PATH)
frames = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(frames)


# --- encoding: byte-for-byte matches frames the device accepted ---------------


def test_fan_on_matches_captured_frame() -> None:
    """fan_on(230) reproduces the exact frame the device applied."""
    assert frames.fan_on(230).hex() == "aa55538107200709020dbd00e602be"


def test_high_alarm_encoding_and_checksum() -> None:
    assert frames.high_alarm(130).hex() == "aa5553810776020082d4"
    assert frames.verify(frames.high_alarm(130))


def test_every_builder_has_a_valid_checksum() -> None:
    for frame in (
        frames.fan_on(110),
        frames.fan_off(110),
        frames.high_alarm(200),
        frames.low_alarm(90),
        frames.ping(),
    ):
        assert frames.verify(frame)


def test_downlink_header_third_byte_is_07() -> None:
    """The device silently ignores frames whose third header byte is not 0x07."""
    assert frames.fan_on(110)[2:5] == bytes((0x53, 0x81, 0x07))


# --- decoding: real uplink captures ------------------------------------------


@pytest.mark.parametrize(
    ("hex_frame", "expected"),
    [
        ("aa5557a2067102002293", {"type": "ambient", "celsius": 34}),
        (
            "aa5557a2062006003200f028af1d",
            {"type": "probe", "idx": 0, "celsius": 24.0, "battery": 40, "rssi": -81},
        ),
        ("aa5558a20610016474", {"type": "stand_battery", "percent": 100}),
    ],
)
def test_decode_real_frames(hex_frame: str, expected: dict) -> None:
    assert frames.parse(bytes.fromhex(hex_frame)) == [expected]


def test_decode_fan_state_on_and_off() -> None:
    up = bytes((0x57, 0xA2, 0x06))
    on = frames.build(0x73, bytes(6) + bytes((0x04, 0x01, 0x09, 0x02, 0x02)), header=up)
    off = frames.build(0x73, bytes(6) + bytes((0x04, 0x01, 0x09, 0x00, 0x00)), header=up)
    assert frames.parse(on) == [{"type": "fan", "mode": 2, "strength": 2, "on": True}]
    assert frames.parse(off) == [{"type": "fan", "mode": 0, "strength": 0, "on": False}]


def test_concatenated_frames_and_trailing_ascii() -> None:
    """One payload may hold several frames plus keepalive text."""
    blob = (
        bytes.fromhex("aa5557a2062006003200f028af1d")
        + bytes.fromhex("aa5557a2065002000050")  # op50, ignored
        + b"ble_work\r\n"
    )
    assert frames.parse(blob) == [
        {"type": "probe", "idx": 0, "celsius": 24.0, "battery": 40, "rssi": -81}
    ]


@pytest.mark.parametrize("junk", ["", "aa55", "aa5500", "1234567890", "aa5557a206"])
def test_parse_ignores_junk(junk: str) -> None:
    assert frames.parse(bytes.fromhex(junk)) == []


def test_roundtrip_fan_command_target_survives() -> None:
    """A fan command re-decoded via the echo header carries its target back."""
    frame = frames.fan_on(175)
    # Rewrite the downlink header to the echo header the device sends back.
    echo = bytes((0xAA, 0x55, 0x57, 0xA2, 0x07)) + frame[5:]
    # It is a fan (op20) echo; the target field is bytes 11-12 of the payload.
    payload = echo[7:7 + echo[6]]
    assert int.from_bytes(payload[4:6], "big") == 175


def test_fan_echo_cannot_create_probe_but_real_probe_survives() -> None:
    """The op20 echo payload is a command, not a probe reading."""
    echo = frames.build(0x20, frames.fan_on(175)[7:-1], header=bytes((0x57, 0xA2, 0x07)))
    probe = bytes.fromhex("aa5557a2062006003200f028af1d")
    assert frames.parse(echo + probe) == [
        {"type": "probe", "idx": 0, "celsius": 24.0, "battery": 40, "rssi": -81}
    ]


@pytest.mark.parametrize("header", [b"\x57\xa2\x07", b"\x58\xa2\x07"])
def test_ping_echo_cannot_create_stand_battery(header: bytes) -> None:
    echo = frames.build(0x10, b"\x00", header=header)
    battery = bytes.fromhex("aa5558a20610016474")
    assert frames.parse(echo + battery) == [{"type": "stand_battery", "percent": 100}]
