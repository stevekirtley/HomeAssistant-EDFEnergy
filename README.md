# Home Assistant EDF Energy

> ## Updating to 21.0.0? There is one step to finish by hand
>
> Version 21 moves the integration into a new folder and nothing moves across on its own.
> What you do depends on the version you are coming from, so follow the guide - it has
> screenshots of every prompt:
>
> **[Updating To Version 21](https://stevekirtley.github.io/HomeAssistant-EDFEnergy/migrations/version_21/)**
>
> On **20.1.0**, update to **20.1.1 first** and restart. Going straight to version 21 stops the
> integration loading and every entity goes unavailable until the move is finished by hand.

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/stevekirtley)
[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor-GitHub-%23EA4AAA?logo=github)](https://github.com/sponsors/stevekirtley)

A fork based on [BottlecapDave's HomeAssistant-OctopusEnergy](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy) (MIT licensed), adapted for EDF Energy customers. EDF Energy uses the same underlying Kraken platform as Octopus Energy, so the core API integration carries over with minimal changes.
No longer listed as a fork as code has deviated significantly from the original library, and to facilitate adding to HACS. 

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

### HACS

1. In HACS, go to **Integrations > ... > Custom repositories**
2. Add `https://github.com/stevekirtley/HomeAssistant-EDFEnergy` with category **Integration**
3. Search for **EDF Energy (UK)** and click **Download**
4. Restart Home Assistant

### Manual

Copy the `custom_components/edfenergy_uk` folder into your Home Assistant `custom_components`
directory and restart.

## How to set up

Go to **Settings > Devices & Services > Add Integration > EDF Energy (UK)**. You will need your
EDF Energy email address and password, and your account number (format `A-AAAA1111`), which is in
the EDF Energy app under **Account** or at the top of any bill.

Your password is used once to generate an API key and is never stored. Everything else - the
Energy dashboard, cost trackers, tariff comparison, the account tab and the rest - is covered in
the documentation:

**[Documentation](https://stevekirtley.github.io/HomeAssistant-EDFEnergy/)**

## Sponsorship 

If you find this useful and are planning on switching to EDF Energy, you're welcome to use my [referral link](https://edfenergy.com/quote/refer-a-friend/massive-sun-7007).

We'll each get £50 credited to our account.


[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/stevekirtley)
[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor-GitHub-%23EA4AAA?logo=github)](https://github.com/sponsors/stevekirtley)

---

[![GitHub Stars](https://img.shields.io/github/stars/stevekirtley/HomeAssistant-EDFEnergy?style=flat&label=GitHub%20stars)](https://github.com/stevekirtley/HomeAssistant-EDFEnergy)
[![HA Analytics](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=active%20installs&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.edfenergy_uk.total)](https://analytics.home-assistant.io)
