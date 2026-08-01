# Blueprints

[Blueprints](https://www.home-assistant.io/docs/automation/using_blueprints/) are an excellent way to get you up and running with the integration quickly. They can also be used as a guide for setting up new automations which you can tailor to your needs. 

## Rates

### Alert when rates change

[Install blueprint](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fstevekirtley%2FHomeAssistant-EDFEnergy%2Fblob%2Fdevelop%2F_docs%2Fblueprints%2Fedf_energy_rates_changed.yaml) | [Source](./blueprints/edf_energy_rates_changed.yaml)

This blueprint will raise a persistent notification within HA when a rate updates.

## Consumption

### Alert when gas anomaly detected

[Install blueprint](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fstevekirtley%2FHomeAssistant-EDFEnergy%2Fblob%2Fdevelop%2F_docs%2Fblueprints%2Fedf_energy_gas_anomaly.yaml) | [Source](./blueprints/edf_energy_gas_anomaly.yaml)

This blueprint will fire a configured action when the consumption has 24 hours worth of records and all thirty minute periods exceed the configured threshold. This can be used to alert you to _potential_ gas leaks.

!!! warning

    Like everything else with this integration, this is provided _as is_ and should be used as a guide and early warning sign. It will only trigger if all data is available. If triggered, you should use your own judgment to determine if the warning is legitimate.

### Alert when consumption data is late

[Install blueprint](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fstevekirtley%2FHomeAssistant-EDFEnergy%2Fblob%2Fdevelop%2F_docs%2Fblueprints%2Fedf_energy_late_consumption_data.yaml) | [Source](./blueprints/edf_energy_late_consumption_data.yaml)

This blueprint will fire a configured action when the latest available consumption data is x hours old, where x is configured via the blueprint.

## Smart Charging

### Manual Smart Charging Dispatch Refreshes

[Install blueprint](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fstevekirtley%2FHomeAssistant-EDFEnergy%2Fblob%2Fdevelop%2F_docs%2Fblueprints%2Fedf_energy_manual_smart_charging_refresh.yaml) | [Source](./blueprints/edf_energy_manual_smart_charging_refresh.yaml)

This blueprint will fire the [Smart Charging dispatches service](./services.md#edf_energyrefresh_intelligent_dispatches) either when a sensor from another integration determines the car has been plugged in (e.g. the plug status from the [MyEnergi integration](https://github.com/CJNE/ha-myenergi)) or when the data is stale and overdue a refresh (in case the dispatch information has changed).

!!! warning

    This blueprint requires you to be on a Smart Charging tariff and a way to determine that your car is plugged in from another integration.

## Cost Tracker

### Automatically update tracking (negative)

[Install blueprint](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fstevekirtley%2FHomeAssistant-EDFEnergy%2Fblob%2Fdevelop%2F_docs%2Fblueprints%2Fedf_energy_cost_tracker_negative.yaml) | [Source](./blueprints/edf_energy_cost_tracker_negative.yaml)

This blueprint will automatically update the tracking state for the specified [cost tracker](./setup/cost_tracker.md) sensors when the monitored sensor goes negative.

### Automatically update tracking (positive)

[Install blueprint](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fstevekirtley%2FHomeAssistant-EDFEnergy%2Fblob%2Fdevelop%2F_docs%2Fblueprints%2Fedf_energy_cost_tracker_positive.yaml) | [Source](./blueprints/edf_energy_cost_tracker_positive.yaml)

This blueprint will automatically update the tracking state for the specified [cost tracker](./setup/cost_tracker.md) sensors when the monitored sensor goes positive (including zero).
