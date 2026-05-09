# Home Assistant EDF Energy

> **Work in progress — not yet ready for production use.**

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
- Smart Charging (EV dispatch) sensors, switches, and controls
- Long-term statistics for HA energy dashboard

## How to install

Not ready for general use yet. Manual installation only.

### Manual

1. Copy `custom_components/edf_energy` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration via **Settings → Devices & Services → Add Integration → EDF Energy**.

### HACS

Not yet published to HACS.

## How to setup

You will need:
- Your EDF Energy **account ID** (format `A-AAAA1111`, shown in your account dashboard)
- An **API key** from the EDF Energy / Kraken developer portal (`https://api.edfgb-kraken.energy/v1/graphql/`)

## FAQ

See the upstream [OctopusEnergy FAQ](https://bottlecapdave.github.io/HomeAssistant-OctopusEnergy/faq/) — most answers apply equally here since the underlying Kraken API is the same.
