# Services

There are a few services available within this integration, which are detailed here.

## Cost Trackers

The following services are available if you have set up at least one [cost tracker](./setup/cost_tracker.md).

### edf_energy.update_cost_tracker

This service allows the user to turn the tracking on/off for a given [cost tracker](./setup/cost_tracker.md) sensor.

| Attribute                | Optional | Description                                                                                                           |
| ------------------------ | -------- | --------------------------------------------------------------------------------------------------------------------- |
| `target.entity_id`       | `no`     | The name of the cost tracker sensor(s) whose configuration is to be updated. |
| `data.is_tracking_enabled`      | `no`    | Determines if tracking should be enabled (true) or disabled (false) for the specified cost trackers |

#### Automation Example

For automation examples, please refer to the available [blueprints](./blueprints.md#cost-tracker).

### edf_energy.reset_cost_tracker

Resets a given [cost tracker](./setup/cost_tracker.md) sensor back to zero before it's normal reset time.

| Attribute                | Optional | Description                                                                                                           |
| ------------------------ | -------- | --------------------------------------------------------------------------------------------------------------------- |
| `target.entity_id`       | `no`     | The name of the cost tracker sensor(s) that should be reset. |

### edf_energy.adjust_accumulative_cost_tracker

Allows you to adjust the cost/consumption for any given date recorded by an accumulative [cost tracker](./setup/cost_tracker.md) sensor (e.g. week or month).

| Attribute                | Optional | Description                                                                                                           |
| ------------------------ | -------- | --------------------------------------------------------------------------------------------------------------------- |
| `target.entity_id`       | `no`     | The name of the cost tracker sensor(s) that should be updated (e.g. `sensor.edf_energy_cost_tracker_{{COST_TRACKER_NAME}}_week` or `sensor.edf_energy_cost_tracker_{{COST_TRACKER_NAME}}_month`). |
| `data.date`              | `no`     | The date of the data within the cost tracker to be adjusted. |
| `data.consumption`       | `no`     | The new consumption recorded against the specified date. |
| `data.cost`              | `no`     | The new cost recorded against the specified date. |

### edf_energy.adjust_cost_tracker

Allows you to adjust the consumption for any given period recorded by a [cost tracker](./setup/cost_tracker.md) sensor representing today.

| Attribute                | Optional | Description                                                                                                           |
| ------------------------ | -------- | --------------------------------------------------------------------------------------------------------------------- |
| `target.entity_id`       | `no`     | The name of the cost tracker sensor(s) that should be updated (e.g. `sensor.edf_energy_cost_tracker_{{COST_TRACKER_NAME}}`). |
| `data.date`              | `no`     | The date of the data within the cost tracker to be adjusted. |
| `data.consumption`       | `no`     | The new consumption recorded against the specified date. |

## Smart Charging

The following services are available if you are on a Smart Charging tariff.

### edf_energy.refresh_intelligent_dispatches

Refreshes Smart Charging dispatches for a given account.

!!! info

    This service is only available if you have switched to [manual polling](./setup/account.md#manually-refresh-intelligent-dispatches) in your configuration.

!!! warning

    This service can only be called once every minute to a maximum of 20 times per hour.

| Attribute                | Optional | Description                                                                                                           |
| ------------------------ | -------- | --------------------------------------------------------------------------------------------------------------------- |
| `target.entity_id`       | `no`     | The [dispatching](./entities/intelligent.md#is-dispatching) entity that you want to refresh the content for (e.g. `binary_sensor.edf_energy_{{DEVICE_ID}}_intelligent_dispatching`). |

#### Automation Example

For an automation example, please refer to the available [blueprint](./blueprints.md#manual-smart-charging-dispatch-refreshes).

### edf_energy.get_point_in_time_intelligent_dispatch_history

Retrieve the Smart Charging dispatch history which was active for a given point in time based on up to the last 48 hours of dispatches that have been captured locally. This can be used to determine why [is dispatching](./entities/intelligent.md#is-dispatching) or [off peak](./entities/electricity.md#off-peak) might have turned on during a certain time period.

!!! info

    The EDF Energy API doesn't provide historic dispatch information, so this information is stored locally as it changes. Therefore depending on how often your dispatch information refreshes, it can take a while for data to become available.

!!! note

    The data that powers this service is available at `config/.storage/edf_energy.intelligent_dispatches_history_{{DEVICE_ID}}`


| Attribute                | Optional | Description                                                                                                           |
| ------------------------ | -------- | --------------------------------------------------------------------------------------------------------------------- |
| `target.entity_id`       | `no`     | The [dispatching](./entities/intelligent.md#is-dispatching) entity that you want to refresh the content for (e.g. `binary_sensor.edf_energy_{{DEVICE_ID}}_intelligent_dispatching`). |
| `data.point_in_time`     | `no`     | The point in time to get the historic dispatch information that was active at the time.


## Miscellaneous

### edf_energy.purge_invalid_external_statistic_ids

For removing all external statistics that are associated with meters that don't have an active tariff. This is useful if you've been using the integration and obtained new smart meters.

### edf_energy.refresh_previous_consumption_data

For refreshing the consumption/cost information for a given previous consumption entity. This is useful when you've just installed the integration and want old data brought in or a previous consumption sensor fails to import (e.g. data becomes available outside of the configured offset). The service will raise a notification when the refreshing starts and finishes.

This service is only available for the following sensors

- `sensor.edf_energy_electricity_{{METER_SERIAL_NUMBER}}_{{MPAN_NUMBER}}_previous_accumulative_consumption` (this will populate both consumption and cost)
- `sensor.edf_energy_gas_{{METER_SERIAL_NUMBER}}_{{MPRN_NUMBER}}_previous_accumulative_consumption_m3` (this will populate both consumption and cost for both m3 and kwh)

!!! information

    Due to limitations with Home Assistant entities, this service will only refresh data for the associated statistic ids used for the recommended approach in the [energy dashboard](./setup/energy_dashboard.md#previous-day-consumption). This will not update the history of the entities themselves.

!!! warning

    If you are on a Smart Charging tariff, the cost data will not be correct for charges outside of the normal off peak times. This is because this data isn't available.