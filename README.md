# ChefsTemp for Home Assistant (unofficial)

[![Release](https://img.shields.io/github/v/release/basift/ha-chefstemp-cloud?display_name=tag&sort=semver)](https://github.com/basift/ha-chefstemp-cloud/releases)
[![Validate](https://github.com/basift/ha-chefstemp-cloud/actions/workflows/validate.yml/badge.svg)](https://github.com/basift/ha-chefstemp-cloud/actions/workflows/validate.yml)
[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=basift&repository=ha-chefstemp-cloud&category=integration)

Control and monitor a **ChefsTemp** BBQ system — the S1 "Stand" WiFi hub, its
temperature probes and the Breezo fan — from Home Assistant. This is an
independent, unofficial integration; it is not affiliated with ChefsTemp/Emax.

The design goal is to put the **control logic in Home Assistant**, not the
appliance. The stand's built-in fan behaviour is a blunt thermostat (it keeps
running the fan for minutes after you open the lid, burning charcoal for nothing).
This integration exposes each control separately so your own automations can be
smart about it — for example, hold the fan off for a few minutes after a lid-open
instead of chasing the temperature back up.

## Entities

Per stand (one Home Assistant device):

| Entity | Type | Notes |
|---|---|---|
| Grill temperature | sensor | ambient temperature at the stand (°C) |
| Stand battery | sensor | % (diagnostic) |
| Probe frame candidates since load | sensor | volatile diagnostics; total candidates, with per-index received/accepted/rejected attributes |
| Probe frame rejections since load | sensor | volatile diagnostic total; attributes include `checksum`, `truncated`, `payload_length`, and `payload_marker` reason counts, per-index totals, and last rejection timestamp |
| Last probe frame rejection | sensor | latest rejection reason, or unknown until a candidate is rejected |
| Probe N temperature | sensor | meat probe (°C), one set per connected probe |
| Probe N battery | sensor | % (diagnostic) |
| Probe N signal | sensor | dBm (diagnostic, disabled by default) |
| Show temperature in °C | switch | on forces °C for this stand's temperature sensors and controls; off follows HA's unit system |
| Fan | fan | on/off — see below |
| Fan target | number | the fan's setpoint (°C) |
| Grill high alarm | number | ambient high-alarm setpoint (°C) |
| Grill low alarm | number | ambient low-alarm setpoint (°C) |

The probe-frame diagnostic sensor exists even before any probe temperature entity
appears. `probe_1` is protocol index 0; other indices appear only if observed.
`unindexed` counts truncated probe candidates without an index. `received` counts
probe-shaped uplink segments, `accepted` counts checksum-valid parsed probe
events, and `rejected` counts malformed or checksum-invalid candidates. The
rejection sensor classifies candidates as `checksum`, `truncated`,
`payload_length`, or `payload_marker`; this is validation-stage evidence, not a
claim about what happened before MQTT delivery. No candidate means no
probe-shaped uplink was observed by this integration. Counts are aggregated at
most once per minute, reset on integration reload or Core restart, and never
include frame bytes, MQTT topics, or device identifiers. They cannot explain
historical readings or establish why a probe did not send.

### How fan control works

The fan is a **thermostat on the device**: while it is *on* the stand runs it
whenever **Fan target** is above the grill temperature, and idles it otherwise.
The stand chooses its own fan strength (a commanded strength has no effect — this
was verified on hardware), so there is deliberately **no speed control**.

That gives Home Assistant two clean primitives:

- **Fan target** — the setpoint the device chases while the fan is on.
- **Fan on/off** — *off* force-stops the fan immediately, regardless of target.
  This is the override your automations use to be smarter than the appliance.

A meat probe's cook target / doneness is **not** a device setting — the stand
only reports the probe temperature. Compare it to your desired target in a Home
Assistant automation.

### Example automations

The repository includes three optional [Home Assistant automation blueprints](blueprints/automation/chefstemp/):

- [Lid-open fan cooldown](blueprints/automation/chefstemp/lid_open_fan_cooldown.yaml) turns the thermostat off after a rapid ambient-temperature drop and restores it after a cooldown only if it was enabled beforehand and no one has turned it back on.
- [Temperature-band hysteresis](blueprints/automation/chefstemp/temperature_band_hysteresis.yaml) enables the thermostat below a lower probe-temperature threshold and disables it above an upper threshold.
- [Lid-open recovery then stall](blueprints/automation/chefstemp/lid_open_recovery_stall.yaml) disables an already-on thermostat after a fresh near-target ambient drop, waits for a confirmed natural rise, and re-enables only after the rise slows/plateaus or reverses over a full window while meaningfully below Fan target. On uncertainty, timeout or interruption/restart, it leaves the fan off with a persistent notification for manual review. Fan-off must be confirmed by device telemetry before observation begins.

Import the desired blueprint into Home Assistant, then select your grill/probe
temperature sensor and ChefsTemp fan. The older two blueprints require **Show
temperature in °C** and reject other units. The recovery/stall blueprint instead
requires a ChefsTemp **grill ambient sensor**, its **Fan target** number in the
same unit (°C or °F), and the new `ambient_sample_at` MQTT timestamp attribute.
It interprets configured temperature *differences* as °C and scales for °F.
Its drop threshold (5 °C) was calibrated against a 2026-10-09 live charcoal
cook: both real meat-in drops (199→147 °C and 200→156 °C in about a minute)
arrived in 4–9 °C single-sample steps, so the earlier default of 10 would never
have fired; steady-state wobble stays within ±1 °C. Ambient cadence measured
6–20 s, so the 90-second freshness default tolerates roughly 4–6 missed frames.
Each ambient MQTT frame updates the timestamp, even at an unchanged temperature;
this produces one sensor state event (and potentially a Recorder write) per
ambient frame, but unrelated polls/frames do not refresh it.
Invalid or out-of-range values are ignored. All blueprints control thermostat
enable, **not** actual motor speed or physical fan activity. **Disable both
older blueprints and any other automation controlling the same fan before
enabling recovery/stall**; competing automation can defeat the safety hold.
An already-off fan is never automatically enabled by this blueprint. Following
an interrupted run/restart, inspect its notification and fan manually; no
automatic restart/recovery latch is installed.

## Installation

Use the **Open in HACS** button above, or add the repository manually:

1. In HACS → *Custom repositories*, add `https://github.com/basift/ha-chefstemp-cloud`
   as an **Integration**.
2. Install **ChefsTemp (unofficial)** and restart Home Assistant.
3. *Settings → Devices & Services → Add Integration → ChefsTemp*.
4. Sign in with your ChefsTemp account email and password, then pick your stand.

## Transports: local BLE first, cloud fallback

The stand speaks the **same wire protocol** over local Bluetooth and over the
vendor cloud, so the integration is written to be transport-agnostic. Today only
the **cloud (MQTT)** transport is implemented and enabled — it is reliable and
needs no extra hardware. A local BLE transport can be added behind the same seam
later; it needs a Bluetooth adapter Home Assistant can reach near the grill.

## Security note

The ChefsTemp vendor backend is **entirely unencrypted** — REST login, the MQTT
telemetry/command channel and firmware downloads are all plain HTTP/TCP on a
single public host, and the MQTT password is a fixed string shared by all
devices. This integration talks to that backend as the official app does; it adds
no new exposure, but be aware your account email/password and grill telemetry
travel in the clear to the vendor. Do not publish your device's MAC address.

## Credits

Protocol reverse-engineered from the official app and confirmed on real hardware.
See the sanitized [protocol notes](docs/PROTOCOL.md) for frame and security details.
