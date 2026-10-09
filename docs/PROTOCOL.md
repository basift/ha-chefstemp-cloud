# ChefsTemp protocol notes

This document summarizes generic protocol observations relevant to the
unofficial Home Assistant integration. It intentionally excludes device and
account identifiers, endpoint addresses, traffic captures, and user-specific
network details. Findings were reverse-engineered from the official app and
verified against hardware; undocumented behavior may change with firmware or
service updates.

## Security considerations

The vendor cloud path observed by the integration uses unencrypted HTTP/TCP for
account REST traffic, MQTT telemetry/commands, and firmware delivery. The vendor
MQTT service uses a static password shared by devices, and topic access may not
be restricted per account. Treat device topic identifiers as secrets: disclosure
may allow others to observe telemetry. Credentials and telemetry sent through
this service may be observable in transit. This is a vendor-side security
limitation; users should consider the risk before connecting the integration.

Do not publish credentials, account identifiers, device identifiers, captured
traffic, or local configuration. The integration does not improve the security
of the vendor transport.

## Frame format

Frames use the form `AA 55 <b2> <h1> <h2> <opcode> <length> <payload...> <checksum>`.
The checksum is `(sum(bytes from b2 through the last payload byte) - 1) & 0xFF`.
Normal uplink telemetry uses header bytes `57 A2 06`; command echoes use
`57 A2 07`. Downlink commands use `53 81 07`; the final header byte is a fixed
protocol value, not a sequence counter.

## Observed telemetry

| Opcode | Meaning | Payload summary |
|---|---|---|
| `71` | Grill ambient temperature | Unsigned 16-bit big-endian whole degrees C; `0xFEFE`/`0xFF02` means the grill probe is disconnected/error, not a temperature |
| `20` | Probe reading | Probe index, marker, unsigned 16-bit tenths of °C, battery percentage, signed RSSI |
| `73` | Device/fan state | Device information followed by thermostat mode and device-selected strength |
| `10` | Stand status/battery | Status byte in the stand-status frame variant |

ASCII keepalive data can be interleaved with binary frames and should be ignored
by the frame decoder. Decode using the header and opcode rather than assuming a
single header variant for every telemetry frame.

## Observed commands

| Opcode | Purpose | Payload summary |
|---|---|---|
| `20` | Set fan thermostat mode and target | Mode, timer field, target temperature, strength field |
| `75` / `76` | Set ambient low/high alarm | Unsigned 16-bit temperature in °C |
| `10` | Ping/refresh | One zero byte |

The fan is a thermostat enable, not a speed-controlled motor: while enabled the
stand decides when to run and chooses its own strength. Turning it off force-stops
the fan. The integration exposes only on/off; Home Assistant automations should
own higher-level cooking logic.

## State and transport notes

Probe temperatures are reported in tenths of a degree Celsius; grill ambient
temperature is reported in whole degrees Celsius. Cloud-side setpoint copies may
not reflect commands sent directly to the device, so the integration retains
Home Assistant's setpoint values after initial discovery. MQTT publication or a
matching telemetry observation should not be mistaken for an authoritative
physical-device acknowledgement.
