# Home Assistant EDF Energy

![installation_badge](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.edf_energy.total)

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/stevekirtley)

A fork of [BottlecapDave's HomeAssistant-OctopusEnergy](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy) (MIT licensed), adapted for EDF Energy customers. EDF Energy uses the same underlying Kraken platform as Octopus Energy, so the core API integration carries over with minimal changes.

This integration is not affiliated with EDF Energy, Kraken, or BottlecapDave.

If you find this useful and are planning on switching to EDF Energy, you're welcome to use my [referral link](https://edfenergy.com/quote/refer-a-friend/massive-sun-7007).

---

## Differences from the upstream OctopusEnergy integration

The following features present in the upstream integration have been **removed** as they are specific to Octopus Energy and are not available on EDF Energy's Kraken platform:

| Feature | Reason removed |
|---|---|
| Home Mini / Home Pro | Octopus-specific hardware |
| OctoPlus points & saving sessions | Octopus-specific loyalty scheme |
| Free electricity sessions | Octopus-specific promotion |
| Wheel of Fortune | Octopus-specific promotion |
| Heat pump control | Octopus-specific (Cosy Octopus tariff) |
| Greenness forecast | Octopus-specific API |

The following features have been **renamed** to match EDF Energy terminology:

| Upstream name | EDF Energy name |
|---|---|
| Intelligent dispatching | Smart Charging |
| Intelligent settings | Smart Charging settings |

Everything else — electricity and gas sensors, rates, standing charges, consumption history, cost trackers, tariff comparison, and Smart Charging (EV dispatch) — is carried over and adapted for the EDF Energy API endpoint (`api.edfgb-kraken.energy`).

---

## Features

- Electricity current, previous, and next rate sensors
- Gas current, previous, and next rate sensors
- Electricity and gas standing charge sensors
- Previous consumption and cost (daily, weekly, monthly)
- Cost tracker sensors (track cost of any energy-based entity)
- Tariff comparison sensors
- Smart Charging (EV dispatch) sensors, switches, and controls — including charge target %, ready-by time, and smart charge toggle
- Long-term statistics for HA energy dashboard

## How to install

### HACS (recommended)

Add this repository as a custom HACS repository:

1. In HACS, go to **Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/stevekirtley/HomeAssistant-EDFEnergy` with category **Integration**
3. Search for **EDF Energy** and click **Download**
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/edf_energy` folder into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.

## How to setup

Go to **Settings → Devices & Services → Add Integration → EDF Energy**.

You will need:

- Your EDF Energy **email address** and **password** (the same credentials you use to log in to the EDF Energy app or website)
- Your EDF Energy **account number** (format `A-AAAA1111`) — found in the EDF Energy app under **Account**, or at the top of any bill

The integration authenticates with the EDF Energy Kraken API using your email and password, and stores a refresh token for ongoing access. Your password is not stored.

## FAQ

See the `_docs/` folder, or the upstream [OctopusEnergy FAQ](https://bottlecapdave.github.io/HomeAssistant-OctopusEnergy/faq/) — most answers apply equally here since the underlying Kraken API is the same.

## Sponsorship 

If you find this useful and are planning on switching to EDF Energy, you're welcome to use my [referral link](https://edfenergy.com/quote/refer-a-friend/massive-sun-7007).

We'll each get £50 credited to our account. Until the 24th of May, if you switch to their EV tariff you'll get a further £50 credit [EV tariff Offer Details](https://www.edfenergy.com/electric-cars/ev-tariffs)


[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/stevekirtley)
