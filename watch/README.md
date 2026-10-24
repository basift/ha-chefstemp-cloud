# ChefsTemp watch app (Garmin Connect IQ)

A Garmin watch app that monitors and controls a **ChefsTemp** charcoal grill
through **Home Assistant**. I wear a watch everywhere, so a glance at the wrist
beats reaching for the phone: grill and probe temperature, the fan, alarms, and
a cook timer — all on the watch.

It talks to Home Assistant's REST API over the phone connection and pairs with my
[ha-chefstemp-cloud](https://github.com/basift/ha-chefstemp-cloud) Home Assistant
integration, which exposes the grill as entities.

> This is an independent, unofficial project. It is not affiliated with
> ChefsTemp/Emax.

## Screens

- **Dashboard** — grill and probe temperature, probe battery, fan state and
  target. A top bar shows how the integration currently reaches the grill
  (Bluetooth / cloud), the 24-hour time, and the stand battery.
- **Alerts** — high / low grill alarms (the watch vibrates when crossed).
- **Fan target** — the temperature the fan chases.
- **Probe target** — the probe doneness the watch alarms on.
- **Timer** — a cook timer owned by Home Assistant; the watch starts, pauses,
  resumes and cancels it, and HA announces by voice when it finishes. The
  remaining time also shows on the dashboard and the Grill & Probe screen while
  it runs.
- **Grill & Probe** — a combined readout with a one-hour history graph and the
  clock.

## Install the prebuilt app

A ready-to-use build for the **fēnix 7 Pro** is in
[`dist/ChefsTemp-fenix7pro.prg`](dist/ChefsTemp-fenix7pro.prg). It contains **no
URL and no token** — you provide those on your phone (below).

1. Connect the watch to your computer by USB (it mounts as a drive).
2. Copy `ChefsTemp-fenix7pro.prg` into the watch's `GARMIN/Apps` folder.
3. Eject and disconnect. The app appears in the activity/app list.

For another watch model, build from source with that device id (below).

## Configure it (URL + token)

Garmin watches have no on-device text entry, so you enter the connection details
**on your phone**, once:

1. Open the **Garmin Connect** app.
2. Go to **Devices** → your watch → **Connect IQ Apps** (sometimes under
   *Activities & App Management*) → **ChefsTemp** → the **Settings** (gear).
3. Fill in:
   - **Home Assistant URL** — e.g. `https://homeassistant.local:8123` or your
     external URL.
   - **Long-lived access token** — in Home Assistant: your profile → **Security**
     → *Long-lived access tokens* → **Create token**.
4. Save. The phone syncs the settings to the watch.

Until both are set, the watch shows a **Set up** screen and makes no requests.

### The settings are cached on the watch

The first time the app sees a URL and token it caches them in the watch's own
storage. That cache **survives app updates**, so installing a newer version keeps
working without re-entering anything. Changing the values on the phone updates the
cache.

## Matching your Home Assistant entities

The app currently targets the entity ids from my own setup (device name
`mllngo`, area `backyard`). If your entity ids differ, edit
[`source/Ct.mc`](source/Ct.mc) (the `ENTITY_*` constants near the top) and rebuild.
The entities it reads/controls:

| Purpose | Entity id |
|---|---|
| Grill temperature | `sensor.mllngo_grill_temperature` |
| Probe temperature / battery | `sensor.backyard_mllngo_probe_1_temperature` / `_battery` |
| Stand battery | `sensor.mllngo_stand_battery` |
| Connection source | `sensor.backyard_mllngo_connection_source` |
| Fan / fan target | `fan.mllngo_fan` / `number.mllngo_fan_target` |
| Grill high / low alarm | `number.mllngo_grill_high_alarm` / `_low_alarm` |
| Probe target / alert | `input_number.chefstemp_probe_target` / `input_boolean.chefstemp_probe_alert` |
| Max / min alert enables | `input_boolean.chefstemp_max_alert` / `_min_alert` |
| Cook timer | `timer.chefstemp_cook` |

### Cook timer (optional)

The Timer screen drives a standard Home Assistant **timer** helper named
`timer.chefstemp_cook`. Create it under *Settings → Devices & Services → Helpers
→ Timer* (enable **Restore**). To have HA announce out loud when it finishes, add
an automation on the `timer.finished` event that speaks via your media player —
for example `tts.speak` to a speaker. Without the helper the other screens still
work; the Timer screen just won't do anything.

## Build from source

Prerequisites:

- [Connect IQ SDK](https://developer.garmin.com/connect-iq/sdk/) (built with 9.2.0)
- A JDK 17 on the `PATH`
- Your own Connect IQ **developer key** (`developer_key.der`) — generate one with
  the SDK; it is personal and never committed.

Point the build at your toolchain with environment variables (or `-Sdk` / `-Key`
/ `-Jdk` parameters), then build:

```powershell
$env:CIQ_SDK = "C:\path\to\connectiq-sdk"
$env:CIQ_KEY = "C:\path\to\developer_key.der"
.\build.ps1 -Device fenix7pro
```

The output is `build/ChefsTemp.prg` (no credentials). Useful switches:

- `-Run` — build and launch the simulator.
- `-Out <path>` — write the `.prg` somewhere else.
- `-Seed` — bake your own URL + token (from `secrets/ha_token.txt` and
  `secrets/ha_url.txt`) into the build as defaults, for the simulator or a
  personal pre-filled copy. These files and everything under `build/` are
  git-ignored, so credentials never reach the repo.

### Layout

- `source/` — Monkey C source.
- `resources/` — strings, drawables, and the phone settings (`settings/settings.xml`).
- `manifest.xml`, `monkey.jungle` — app manifest and build config.
- `build.ps1` — build / run script.
- `dist/` — the prebuilt, credential-free `.prg`.

## License

MIT.
