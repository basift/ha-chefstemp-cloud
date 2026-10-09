# Notes for AI assistants working in this repository

## What this is

An unofficial Home Assistant integration for ChefsTemp BBQ hardware (S1 stand +
probes + Breezo fan), over the vendor's undocumented cloud API. The protocol was
reverse-engineered from the official app and confirmed on real hardware. The
public protocol reference lives in this repository's `docs/PROTOCOL.md` — read it before
changing anything that builds or parses frames.

## Rules that matter here

- **Never commit captured traffic, tokens, credentials, or the device MAC.** The
  MAC is the MQTT topic key on a broker with no per-user ACL — treat it as a
  secret. See `.gitignore`.
- **Do not add unverified device support.** Every opcode and field in `frames.py`
  was seen on the wire. Do not add a plausible-looking command or a second-probe
  path that nobody has run against hardware.
- **State comes only from the device** — a pushed MQTT frame or a command echo.
  Setpoints HA writes (fan target, alarms) are *not* reflected back in telemetry
  and are *not* synced to the cloud copy. The official app *does* save its edits
  to the cloud copy, so the poll adopts a cloud setpoint only when it changed
  since the previous poll; never overwrite HA's value with an unchanged cloud copy.
- **The fan is a thermostat, not a variable-speed fan.** It runs when the target
  is above ambient and picks its own strength; commanded strength does nothing
  (verified by ear). Keep the fan entity on/off only.

## Layout

| Path | Purpose |
|---|---|
| `custom_components/chefstemp/frames.py` | `AA55` frame codec — dependency-free, testable on its own |
| `custom_components/chefstemp/api.py` | cloud REST: login + device discovery |
| `custom_components/chefstemp/transport.py` | transport seam (BLE can drop in behind it) |
| `custom_components/chefstemp/mqtt.py` | cloud transport (paho MQTT) |
| `custom_components/chefstemp/coordinator.py` | state, MQTT lifecycle, command dispatch |
| `custom_components/chefstemp/{sensor,fan,number}.py` | entities |

## Checks

```bash
ruff check . && mypy custom_components/chefstemp && pytest
```
