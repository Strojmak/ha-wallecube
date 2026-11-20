# WalleCube UPS for Home Assistant

Unofficial Home Assistant integration for **WalleCube** DC mini-UPS units (W150, W120).
It reads live telemetry from the WalleCube cloud, the same data the WalleCube mobile app shows.

> This project is not affiliated with or endorsed by WalleCube.
> The cloud API is undocumented; it was studied from the official app and may change without notice.

## What you get

Every UPS in your WalleCube account becomes a device in Home Assistant. Units added to the account later show up automatically.

| Entity | Notes |
|---|---|
| Battery | State of charge, % |
| Input voltage / current / power | Power is calculated from voltage × current |
| Output voltage / current / power | |
| Battery voltage / current | |
| Battery power | **Positive while discharging, negative while charging**, ready for power-flow cards |
| Time left | Runtime estimate from the UPS. It tends to be optimistic |
| Temperature | Battery temperature |
| Energy delivered | Total output energy, kWh. Works with the Energy dashboard |
| Input power, Charging, Discharging, Overload | Binary sensors |
| Online | Diagnostic: the cloud sees the unit and its data is fresh |
| Battery health, cycles, cell voltage spread, last report | Diagnostic |
| Cell 1–4 voltage, adapter voltage / current settings | Diagnostic, disabled by default |

The cloud is polled once a minute with one request for all units. A unit whose last report is older than 10 minutes is shown as unavailable. The **Online** and **Last report** entities stay available, so you can alert on them.

## Requirements

- The UPS is connected to Wi-Fi and added to an account in the **WalleCube** app.
- You know the e-mail of that account and can read its mail. Login is by a one-time code; the app has no password.

## Installation

### HACS

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/Strojmak/ha-wallecube`, type **Integration**.
2. Install **WalleCube UPS** and restart Home Assistant.

### Manual

Copy `custom_components/wallecube` into `<config>/custom_components/` and restart Home Assistant.

## Setup

**Settings → Devices & services → Add integration → WalleCube UPS**, then either:

- **Sign in with a code sent by e-mail**: enter the account e-mail and type in the code from the letter.
- **Enter an access token**: paste a bearer token you already have.

When the cloud stops accepting the token, Home Assistant shows a **Reconfigure / re-authenticate** prompt for the integration. Sign in again the same way; entities and history are kept.

## Known quirks

- The cloud updates roughly every 30 seconds; Home Assistant shows values up to about a minute old.
- *Time left* comes from the UPS firmware and is usually longer than the real runtime.
- *Battery* (%) from the cloud is real. The USB HID / NUT driver of the same UPS reports a fixed 100 %.

## Local alternative

The UPS also has a USB port that works with Network UPS Tools (`usbhid-ups`, VID `04d8`, PID `d005`). That path works without the cloud, but several fields are wrong on current firmware.

## Diagnostics

**Settings → Devices & services → WalleCube UPS → ⋮ → Download diagnostics** gives the raw cloud data with the token, e-mail, IMEI, MAC and IP addresses removed. Please attach it to bug reports.

## License

MIT
