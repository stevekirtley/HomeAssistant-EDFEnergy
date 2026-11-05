# Home Assistant EDF Energy

> [!IMPORTANT]
> ## On Home Assistant 2026.11 or later? Read this before you update
>
> 2026.11 brought HACS into Home Assistant as the **Marketplace**, and the Marketplace won't
> update an integration whose folder has changed name. Coming from 20.x or older, the update
> fails with *"changed its domain from edf_energy to edfenergy_uk"*.
>
> **Don't delete the integration or press "Delete and uninstall".** Follow
> **[Updating with the Marketplace](https://stevekirtley.github.io/HomeAssistant-EDFEnergy/migrations/version_21/#updating-with-the-marketplace-home-assistant-202611-and-later)**
> instead. It has a screenshot of every step, and your entities, history and automations
> all come across intact.

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

1. In HACS, search for **EDF Energy (UK)** and click **Download**
2. Restart Home Assistant

If it doesn't come up in the search, add it as a custom repository first: in HACS go to
**... > Custom repositories**, add `https://github.com/stevekirtley/HomeAssistant-EDFEnergy` with
type **Integration**, then search again.

### Running it alongside another EDF integration

[HomeAssistant-EDF-UK](https://github.com/Bobby5291/HomeAssistant-EDF-UK) is a separate EDF
integration that installs as `edf_energy`, which is the domain this one used before 21.0.0. The
two can be installed together, and this integration leaves the other one's folder, entries and
notices alone.

They **can't share an account**, though. Both write the same Energy dashboard statistics, so
each would overwrite the other's history. If both have the same account set up, this
integration stops writing those statistics and raises a repair saying why. Set each account
up in one integration only.

### Updating from 20.x on Home Assistant 2026.11 or later

If the Marketplace says the integration "changed its domain from edf_energy to edfenergy_uk",
don't delete it. Follow
[these steps](https://stevekirtley.github.io/HomeAssistant-EDFEnergy/migrations/version_21/)
instead, and your setup comes across intact.

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

## Power Perks session feed & urgent notifications

Some functionality relies on data from my server rather than EDF's. Both of the things below
come from one feed at `apirelay.sitetest.org.uk`, and one switch controls both of them:
**Settings > Devices & Services > EDF Energy (UK) > the three dots beside your account >
Reconfigure**, then clear **Use the Power Perks session feed**.

The integration checks that feed every 15 minutes and sends nothing but its own version
number: no account number, no meter details, no personal data of any kind. As with any web
request, the server sees the IP address it came from. Turning the switch off stops the checks
completely - no request leaves your machine.

### 1. Power Perks session feed

EDF announce Power Perks free electricity sessions by text message only - there is no API for
them - so the times are relayed through the feed and appear in your free electricity sensors
and calendar automatically.

With the feed off you can still record sessions yourself with the **Register Power Perks
session** action, and nothing else in the integration depends on it.

More detail in the [free electricity documentation](https://stevekirtley.github.io/HomeAssistant-EDFEnergy/entities/free_electricity/).

### 2. Urgent notifications

The same feed can carry a short notice from me - used only for something that needs to reach
people quickly, such as a release that breaks an upgrade path or a fault worth knowing about
before you hit it. It arrives attached to the session data rather than as a separate check, so
it costs no extra requests.

Because it travels on the same feed, the switch above turns these off as well. Worth knowing
if you turn it off: you will not see these notices.

### Previously

My server has also been used to supply World Cup fixture times, to extend EDF's football free
windows when a match went to extra time. That is no longer polled - the code is archived and
the integration makes no fixture requests.

## Sponsorship 

If you find this useful and are planning on switching to EDF Energy, you're welcome to use my [referral link](https://edfenergy.com/quote/refer-a-friend/massive-sun-7007).

We'll each get £50 credited to our account.


[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/stevekirtley)
[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor-GitHub-%23EA4AAA?logo=github)](https://github.com/sponsors/stevekirtley)

---

[![GitHub Stars](https://img.shields.io/github/stars/stevekirtley/HomeAssistant-EDFEnergy?style=flat&label=GitHub%20stars)](https://github.com/stevekirtley/HomeAssistant-EDFEnergy)
[![HA Analytics](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=active%20installs&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.edfenergy_uk.total)](https://analytics.home-assistant.io)
