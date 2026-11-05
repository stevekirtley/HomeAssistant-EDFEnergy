# Home Assistant EDF Energy

## Features

Below are the main features of the integration

* [Electricity](./entities/electricity.md) and [gas](./entities/gas.md) meter support including consumption data and rate information
* [Custom sensor support for tracking costs of other entities](#cost-tracker-sensors)
* [Custom sensor support for comparing to other tariffs](#tariff-comparison-sensors)
* [Smart Charging tariff settings support](#smart-charging)
* [Sunday Saver](./entities/sunday_saver.md) free electricity window sensors with automatic enrolment

## How to install

There are multiple ways of installing the integration. Once you've installed the integration, you'll need to [setup your account](#how-to-setup) before you can use the integration.

### HACS

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

This integration can be installed directly via HACS. To install:

* In HACS, search for **EDF Energy (UK)**
* Click `Download`, then restart Home Assistant

If it doesn't come up in the search, [add the repository](https://my.home-assistant.io/redirect/hacs_repository/?owner=stevekirtley&repository=HomeAssistant-EDFEnergy&category=integration) to HACS first and then download it.

### Alongside another EDF integration

[HomeAssistant-EDF-UK](https://github.com/Bobby5291/HomeAssistant-EDF-UK) is a separate integration that installs as `edf_energy`, the domain this one used before version 21. The two can be installed side by side, and this integration doesn't touch the other one's folder, entries or notices.

They can't share an account. Both write the same Energy dashboard statistics, so on a shared account each would overwrite the other's history. If both have the same account set up, this integration stops writing those statistics and raises a repair explaining why. Keep each account in one integration only.

### Manual

You should take the latest [published release](https://github.com/stevekirtley/HomeAssistant-EDFEnergy/releases). The current state of `develop` will be in flux and therefore possibly subject to change.

To install, place the contents of `custom_components` into the `<config directory>/custom_components` folder of your Home Assistant installation. Once installed, don't forget to restart your home assistant instance for the integration to be picked up.

## How to setup

Please follow the [setup guide](./setup/account.md) to setup your initial account. This guide details the configuration, along with the entities that will be available to you.

## Entities

### Electricity Entities

[Full list of electricity entities](./entities/electricity.md).

### Gas Entities

[Full list of gas entities](./entities/gas.md).

### Smart Charging

If you are on an EDF Energy Smart Charging tariff, then you'll get a few additional entities when you install the integration.

[List of Smart Charging entities](./entities/intelligent.md).

!!! warning
    
    If you switch to a Smart Charging tariff after you have installed the integration, you will need to reload the integration or restart your Home Assistant instance.

## Cost Tracker Sensors

These sensors track the consumption of other existing sensors and provide a daily cost of those sensors.

Please follow the [setup guide](./setup/cost_tracker.md).

## Tariff Comparison Sensors

These sensors compare the cost of the previous consumption to another tariff to see if you're on the best tariff.

Please follow the [setup guide](./setup/tariff_comparison.md).

## Events

This integration raises several events, which can be used for various tasks like automations. For more information, please see the [events docs](./events.md).

## Services

This integration includes several services. Please review them in the [services doc](./services.md).

## Energy Dashboard

The core sensors have been designed to work with the energy dashboard. Please see the [energy dashboard guide](./setup/energy_dashboard.md) for instructions on how to set this up.

## Blueprints

A selection of [blueprints](./blueprints.md) are available to help get you up and running quickly with the integration.

## FAQ

Before raising anything, please read through the [faq](./faq.md). If you have questions, then you can raise a [discussion](https://github.com/stevekirtley/HomeAssistant-EDFEnergy/discussions). If you have found a bug or have a feature request please [raise it](https://github.com/stevekirtley/HomeAssistant-EDFEnergy/issues) using the appropriate report template.