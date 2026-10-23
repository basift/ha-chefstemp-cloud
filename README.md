# ChefsTemp for Home Assistant (unofficial)

[![Release](https://img.shields.io/github/v/release/basift/ha-chefstemp-cloud?display_name=tag&sort=semver)](https://github.com/basift/ha-chefstemp-cloud/releases)
[![Validate](https://github.com/basift/ha-chefstemp-cloud/actions/workflows/validate.yml/badge.svg)](https://github.com/basift/ha-chefstemp-cloud/actions/workflows/validate.yml)
[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=basift&repository=ha-chefstemp-cloud&category=integration)

Control and monitor a **ChefsTemp** BBQ system — the S1 "Stand" WiFi hub, its
temperature probes and the Breezo fan — from Home Assistant. This is an
independent, unofficial integration; it is not affiliated with ChefsTemp/Emax.

## Why this exists

I built this for **two** reasons:

1. **To monitor and control the grill from Home Assistant, conveniently.** One
   place for grill ambient, probe temperature and battery, stand battery, the fan,
   its target setpoint and the high/low alarms — watch it and drive it without
   reaching for the phone app, and wire it into your own automations, dashboards
   and notifications. It talks to the stand over **local Bluetooth when reachable
   and falls back to the vendor cloud**, so monitoring and control keep working.
   The dashboard I actually use is in [`examples/dashboard.yaml`](examples/dashboard.yaml).

2. **To fix the fan behaviour that bugged me.** The Breezo fan is a blunt on/off
   thermostat with no idea the lid is open: open it to load food and the ambient
   drops below target, so the fan immediately **blasts at full tilt** — oversmoking
   the food and burning through charcoal for nothing. Putting the control logic in
   Home Assistant lets an automation hold the fan off through a lid-open dip and
   resume only once the grill has genuinely stalled — see the
   [lid-open recovery automation](examples/automation-lid-open-recovery.yaml).

To make the second goal possible, the integration deliberately exposes each
control (fan on/off, fan target, alarms) as its own entity, so **your** automations
decide the policy, not the appliance.

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
| Connection source | sensor | which channel is live now — Bluetooth / Cloud / Disconnected (diagnostic) |
| Bluetooth | switch | on = Home Assistant holds the stand's local BLE link; off releases it for ~5 minutes so the phone app can take the stand's single BLE slot, then re-enables itself |
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

The repository includes several optional [Home Assistant automation blueprints](blueprints/automation/chefstemp/). The newest one is a full controller; the others are narrower, single-behaviour recipes. Run **only one** automation on the fan at a time.

- [Grill setpoint controller](blueprints/automation/chefstemp/grill_setpoint_controller.yaml) — the recommended all-in-one. On every fresh ambient sample it computes a rate and manages the fan around Fan target: a lid-open guard (any fast drop forces the fan off, so opening the lid never blasts smoke onto the food), anti-overshoot (cuts early while climbing so inertia coasts onto target), a hysteresis hold, and a stall escape (re-enables once the grill settles below target, a natural rise is left alone). Thresholds are inputs with defaults calibrated on a real cook; tune them over a few cooks. Disable the three recipes below when you use this.
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

A ready-to-paste instance of the recovery automation, wired to example entity
IDs, is in [`examples/automation-lid-open-recovery.yaml`](examples/automation-lid-open-recovery.yaml).

### Example dashboard

The [`examples/`](examples/) folder also contains the Lovelace view I use to
monitor and drive the grill — [`examples/dashboard.yaml`](examples/dashboard.yaml).
It needs the HACS **frontend** cards `button-card` and `card-mod`; edit the entity
IDs to match your stand.

## Installation

Use the **Open in HACS** button above, or add the repository manually:

1. In HACS → *Custom repositories*, add `https://github.com/basift/ha-chefstemp-cloud`
   as an **Integration**.
2. Install **ChefsTemp (unofficial)** and restart Home Assistant.
3. *Settings → Devices & Services → Add Integration → ChefsTemp*.
4. Sign in with your ChefsTemp account email and password, then pick your stand.

## Transports: local BLE first, cloud fallback

The stand speaks the **same wire protocol** over local Bluetooth and over the
vendor cloud, so the integration runs both and prefers whichever is better. When
the stand is reachable over **BLE** (a Bluetooth adapter or an ESPHome proxy near
the grill), the integration holds that link and uses it for telemetry and commands
— fast and independent of WiFi/internet — and falls back to the **cloud (MQTT)**
automatically when BLE is unavailable. The live channel is shown by the
**Connection source** sensor.

The stand exposes a **single external BLE slot**: whoever connects first owns it,
so Home Assistant and the phone app cannot both hold it at once. The **Bluetooth**
switch (on by default) releases Home Assistant's link for ~5 minutes — long enough
to open the phone app and let it claim the slot — then re-enables itself, and Home
Assistant reclaims BLE within seconds once the slot is free again. The probe stays
connected to the stand throughout; it is the stand's own internal link, unaffected
by which central holds the external slot.

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
