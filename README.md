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
| Probe N temperature | sensor | meat probe (°C), one set per connected probe |
| Probe N battery | sensor | % (diagnostic) |
| Probe N signal | sensor | dBm (diagnostic, disabled by default) |
| Fan | fan | on/off — see below |
| Fan target | number | the fan's setpoint (°C) |
| Grill high alarm | number | ambient high-alarm setpoint (°C) |
| Grill low alarm | number | ambient low-alarm setpoint (°C) |

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

The repository includes two optional [Home Assistant automation blueprints](blueprints/automation/chefstemp/):

- [Lid-open fan cooldown](blueprints/automation/chefstemp/lid_open_fan_cooldown.yaml) turns the thermostat off after a rapid ambient-temperature drop and restores it after a cooldown only if it was enabled beforehand and no one has turned it back on.
- [Temperature-band hysteresis](blueprints/automation/chefstemp/temperature_band_hysteresis.yaml) enables the thermostat below a lower probe-temperature threshold and disables it above an upper threshold.

Import the desired blueprint into Home Assistant, then select your grill/probe
temperature sensor and ChefsTemp fan. The sensors must report in °C; invalid or
out-of-range readings (outside 0–500 °C) are ignored. These blueprints control
thermostat enable, not actual motor speed or physical fan activity. Do not run
both against the same fan unless you intend their actions to interact.

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
