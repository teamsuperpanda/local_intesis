<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="custom_components/local_intesis/brand/icon.png">
    <img src="custom_components/local_intesis/brand/icon.png" alt="LocalIntesis" width="128">
  </picture>
</p>

<p align="center">
  <a href="https://github.com/teamsuperpanda/local_intesis/releases"><img src="https://img.shields.io/github/v/release/teamsuperpanda/local_intesis?style=flat-square&logo=github&label=Release" alt="Release"></a>
  <img src="https://img.shields.io/badge/HACS-Integration-41BDF5?style=flat-square&logo=home-assistant&logoColor=white" alt="HACS">
  <img src="https://img.shields.io/badge/Home%20Assistant-2024.1.0-41BDF5?style=flat-square&logo=home-assistant&logoColor=white" alt="HA">
  <img src="https://img.shields.io/github/last-commit/teamsuperpanda/local_intesis?style=flat-square" alt="Last commit">
</p>

# LocalIntesis

Take control of your IntesisHome WiFi gateway. **No cloud. No internet. No flaky servers.**

This Home Assistant custom integration talks directly to the HTTP API on your local gateway. Your AC commands never leave your network.

## Why LocalIntesis?

Other IntesisHome integrations bundle cloud SDKs, external libraries, and TCP tunnels. LocalIntesis is different:

- **Zero dependencies** -- no `pyintesishome`, no pip packages, nothing to break
- **Purely local** -- your gateway has a working HTTP API on port 80. We use it. No cloud account needed, no internet required
- **Instant response** -- optimistic updates show your command results immediately, then sync in the background
- **Simple codebase** -- 4 files, easy to audit, easy to maintain

The official HA integration routes through a cloud server at `212.92.41.143:5210` that frequently drops connections, causing your AC controls to flap between available and unavailable. Your gateway is sitting on your LAN with a perfectly good API. This integration just talks to it directly.

## Features

- Power on/off
- HVAC mode (auto, heat, cool, dry, fan)
- Temperature setpoint (with min/max limits)
- Fan speed
- Vertical vane (swing)
- Current temperature
- Outdoor temperature
- Optimistic updates for instant UI response

## Hardware Support

**Tested on:** FJ-RC-WIFI-1B (Fujitsu General WiFi adapter / IntesisHome gateway)

Other IntesisHome-based gateways with `/api.cgi` on port 80 should work, but I need your help to confirm. If yours works (or doesn't), open an issue with your model number.

## Installation

### HACS (recommended)

Once approved for the [default HACS store](https://github.com/hacs/default/pull/8443):

1. Go to **HACS > Integrations**
2. Search for **LocalIntesis**
3. Click **Install**
4. Restart Home Assistant

Until then, install as a custom repository:

1. Go to **HACS > Integrations > ... > Custom Repositories**
2. Add `https://github.com/teamsuperpanda/local_intesis` (Category: Integration)
3. Click **Install** on the LocalIntesis entry
4. Restart Home Assistant

### Manual

Copy `custom_components/local_intesis/` into your Home Assistant `custom_components/` directory and restart.

## Configuration

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for **LocalIntesis**
3. Enter:
   - **Host** -- IP address of your IntesisHome gateway (e.g. `192.168.3.14`)
   - **Username** -- Gateway username (default: `admin`)
   - **Password** -- Gateway password (default: `admin`)

## Security

The default credentials on these gateways are `admin` / `admin`. **Change them.** Use your gateway's web interface to set a unique username and password. Leaving defaults exposes your AC controls to anyone on your network.

## Troubleshooting

### Can't find the integration

If you are installing before HACS default store approval, make sure you added the custom repository URL correctly.

### Gateway not responding

Verify the gateway IP is correct and reachable from your HA instance. The gateway must be on the same network or reachable via a route. Try opening `http://<gateway-ip>/api.cgi` in a browser -- if you get a response, the gateway is working.

### Cloud server timeout errors

If you previously used the official IntesisHome integration and see timeout warnings, those are from the cloud server at `212.92.41.143:5210`, not from LocalIntesis. This integration does not touch the cloud at all.

## Testing Needed

This integration is tested on exactly one gateway: the FJ-RC-WIFI-1B. Community testing is essential to build a supported hardware list. Please open an issue with your gateway model and whether the integration works for you.

## Credits

Protocol reference from [pyIntesisHome](https://github.com/jnimmo/pyIntesisHome).
