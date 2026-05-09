# Diagnostic Entities

These entities can help diagnose issues.

## Account Data Last Retrieved

`sensor.edf_energy_{{ACCOUNT_ID}}_account_data_last_retrieved`

This sensor states when account data was last retrieved.

!!! note
    This is [disabled by default](../faq.md#there-are-entities-that-are-disabled-why-are-they-disabled-and-how-do-i-enable-them). 

| Attribute | Type | Description |
|-----------|------|-------------|
| `attempts` | `integer` | The number of attempts that have been made to retrieve the data |
| `next_refresh` | `datetime` | The timestamp of when the data will next be attempted to be retrieved |
| `last_error` | `string` | The error that was raised to cause the last retrieval attempt to fail |

## Current Consumption Data Last Retrieved

`sensor.edf_energy_electricity_{{METER_SERIAL_NUMBER}}_{{MPAN_NUMBER}}_current_consumption_data_last_retrieved` or `sensor.edf_energy_gas_{{METER_SERIAL_NUMBER}}_{{MPRN_NUMBER}}_current_consumption_data_last_retrieved`

This sensor states when the current consumption data was last retrieved.

!!! note
    This is [disabled by default](../faq.md#there-are-entities-that-are-disabled-why-are-they-disabled-and-how-do-i-enable-them). 

| Attribute | Type | Description |
|-----------|------|-------------|
| `attempts` | `integer` | The number of attempts that have been made to retrieve the data |
| `next_refresh` | `datetime` | The timestamp of when the data will next be attempted to be retrieved |
| `last_error` | `string` | The error that was raised to cause the last retrieval attempt to fail |

## Intelligent Dispatches Data Last Retrieved

`sensor.edf_energy_{{DEVICE_ID}}_intelligent_dispatches_data_last_retrieved`

This sensor states when Smart Charging dispatches data was last retrieved.

!!! note
    This is [disabled by default](../faq.md#there-are-entities-that-are-disabled-why-are-they-disabled-and-how-do-i-enable-them). 

| Attribute | Type | Description |
|-----------|------|-------------|
| `attempts` | `integer` | The number of attempts that have been made to retrieve the data |
| `next_refresh` | `datetime` | The timestamp of when the data will next be attempted to be retrieved |
| `last_error` | `string` | The error that was raised to cause the last retrieval attempt to fail |
| `requests_current_hour` | `integer` | The number of requests that have been made during the current hour. The start of the hour starts when the first request is made. |
| `maximum_requests_per_hour` | `integer` | The maximum number of requests that can be made during an hour. The start of the hour starts when the first request is made. |
| `request_limits_last_reset` | `datetime` | The datetime when the request limits were last reset. This will reset when a request is made and is within the designated limits. |

## Intelligent Settings Data Last Retrieved

`sensor.edf_energy_{{DEVICE_ID}}_intelligent_settings_data_last_retrieved`

This sensor states when Smart Charging settings data was last retrieved.

!!! note
    This is [disabled by default](../faq.md#there-are-entities-that-are-disabled-why-are-they-disabled-and-how-do-i-enable-them). 

| Attribute | Type | Description |
|-----------|------|-------------|
| `attempts` | `integer` | The number of attempts that have been made to retrieve the data |
| `next_refresh` | `datetime` | The timestamp of when the data will next be attempted to be retrieved |
| `last_error` | `string` | The error that was raised to cause the last retrieval attempt to fail |

## Previous Consumption And Rates Data Last Retrieved

`sensor.edf_energy_electricity_{{METER_SERIAL_NUMBER}}_{{MPAN_NUMBER}}_previous_consumption_and_rates_data_last_retrieved` or `sensor.edf_energy_gas_{{METER_SERIAL_NUMBER}}_{{MPRN_NUMBER}}_previous_consumption_and_rates_data_last_retrieved`

This sensor states when the previous consumption and associated rate data was last retrieved.

!!! note
    This is [disabled by default](../faq.md#there-are-entities-that-are-disabled-why-are-they-disabled-and-how-do-i-enable-them). 

| Attribute | Type | Description |
|-----------|------|-------------|
| `attempts` | `integer` | The number of attempts that have been made to retrieve the data |
| `next_refresh` | `datetime` | The timestamp of when the data will next be attempted to be retrieved |
| `last_error` | `string` | The error that was raised to cause the last retrieval attempt to fail |

## Rates Data Last Retrieved

`sensor.edf_energy_electricity_{{METER_SERIAL_NUMBER}}_{{MPAN_NUMBER}}_rates_data_last_retrieved` or `sensor.edf_energy_gas_{{METER_SERIAL_NUMBER}}_{{MPRN_NUMBER}}_rates_data_last_retrieved`

This sensor states when the previous/current and next rate data was last retrieved.

!!! note
    This is [disabled by default](../faq.md#there-are-entities-that-are-disabled-why-are-they-disabled-and-how-do-i-enable-them). 

| Attribute | Type | Description |
|-----------|------|-------------|
| `attempts` | `integer` | The number of attempts that have been made to retrieve the data |
| `next_refresh` | `datetime` | The timestamp of when the data will next be attempted to be retrieved |
| `last_error` | `string` | The error that was raised to cause the last retrieval attempt to fail |

## Standing Charge Data Last Retrieved

`sensor.edf_energy_electricity_{{METER_SERIAL_NUMBER}}_{{MPAN_NUMBER}}_standing_charge_data_last_retrieved` or `sensor.edf_energy_gas_{{METER_SERIAL_NUMBER}}_{{MPRN_NUMBER}}_standing_charge_data_last_retrieved`

This sensor states when the standing charge data was last retrieved.

!!! note
    This is [disabled by default](../faq.md#there-are-entities-that-are-disabled-why-are-they-disabled-and-how-do-i-enable-them). 

| Attribute | Type | Description |
|-----------|------|-------------|
| `attempts` | `integer` | The number of attempts that have been made to retrieve the data |
| `next_refresh` | `datetime` | The timestamp of when the data will next be attempted to be retrieved |
| `last_error` | `string` | The error that was raised to cause the last retrieval attempt to fail |
