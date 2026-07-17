# Gas

You'll get the following entities for each gas meter with an active agreement:

## Current Rate

`sensor.edf_energy_gas_{{METER_SERIAL_NUMBER}}_{{MPRN_NUMBER}}_current_rate`

The current rate that energy consumption is charged at (including VAT).

| Attribute | Type | Description |
|-----------|------|-------------|
| `mprn` | `string` | The mprn for the associated meter |
| `serial_number` | `string` | The serial for the associated meter |
| `is_smart_meter` | `boolean` | Determines if the meter is considered smart by EDF Energy |
| `tariff` | `string` | The tariff the meter/rates are associated with |
| `start` | `datetime` | The date/time when the rate started |
| `end` | `datetime` | The date/time when the rate ends |
| `is_capped` | `boolean` | Indicates if the rate has been capped by a [configured price cap](../setup/account.md#pricing-caps) |
| `price_cap` | `float` | The price cap that has been configured for the account and is currently applied to all gas rates |

## Previous Rate

`sensor.edf_energy_gas_{{METER_SERIAL_NUMBER}}_{{MPRN_NUMBER}}_previous_rate`

The previous rate that energy consumption was charged at (including VAT), that differs from the current rate. If there is no previous rate (e.g. rates before now are of the same value as the current rate), then this will be reported as `unknown`/`none`.

| Attribute | Type | Description |
|-----------|------|-------------|
| `mprn` | `string` | The mprn for the associated meter |
| `serial_number` | `string` | The serial for the associated meter |
| `is_smart_meter` | `boolean` | Determines if the meter is considered smart by EDF Energy |
| `start` | `datetime` | The date/time when the rate started |
| `end` | `datetime` | The date/time when the rate ended |

## Next rate

`sensor.edf_energy_gas_{{METER_SERIAL_NUMBER}}_{{MPRN_NUMBER}}_next_rate`

The next/upcoming rate that energy consumption will be charged at (including VAT), that differs from the current rate. If there is no next rate (e.g. rates after now are of the same value as the current rate), then this will be reported as `unknown`/`none`.

| Attribute | Type | Description |
|-----------|------|-------------|
| `mprn` | `string` | The mprn for the associated meter |
| `serial_number` | `string` | The serial for the associated meter |
| `is_smart_meter` | `boolean` | Determines if the meter is considered smart by EDF Energy |
| `start` | `datetime` | The date/time when the rate starts |
| `end` | `datetime` | The date/time when the rate ends |

## Current Day Rates

`event.edf_energy_gas_{{METER_SERIAL_NUMBER}}_{{MPRN_NUMBER}}_current_day_rates`

The state of this sensor states when the current day's rates were last updated. The attributes of this sensor exposes the current day's rates.

| Attribute | Type | Description |
|-----------|------|-------------|
| `rates` | `array` | The list of rates applicable for the current day |
| `tariff_code` | `string` | The tariff code associated with current day's rates |

Each rate item has the following attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `start` | `datetime` | The date/time when the rate starts |
| `end` | `datetime` | The date/time when the rate ends |
| `value_inc_vat` | `float` | The value of the rate including VAT. This is in pounds and pence (e.g. 1.01 = £1.01) |
| `is_capped` | `boolean` | Indicates if the rate has been capped by a [configured price cap](../setup/account.md#pricing-caps) |

## Previous Day Rates

`event.edf_energy_gas_{{METER_SERIAL_NUMBER}}_{{MPRN_NUMBER}}_previous_day_rates`

The state of this sensor states when the previous day's rates were last updated. The attributes of this sensor exposes the previous day's rates.

| Attribute | Type | Description |
|-----------|------|-------------|
| `rates` | `array` | The list of rates applicable for the previous day |
| `tariff_code` | `string` | The tariff code associated with previous day's rates |

Each rate item has the following attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `start` | `datetime` | The date/time when the rate starts |
| `end` | `datetime` | The date/time when the rate ends |
| `value_inc_vat` | `float` | The value of the rate including VAT. This is in pounds and pence (e.g. 1.01 = £1.01) |
| `is_capped` | `boolean` | Indicates if the rate has been capped by a [configured price cap](../setup/account.md#pricing-caps) |

## Next Day Rates

`event.edf_energy_gas_{{METER_SERIAL_NUMBER}}_{{MPRN_NUMBER}}_next_day_rates`

The state of this sensor states when the next day's rates were last updated. The attributes of this sensor exposes the next day's rates.

| Attribute | Type | Description |
|-----------|------|-------------|
| `rates` | `array` | The list of rates applicable for the next day |
| `tariff_code` | `string` | The tariff code associated with today's rates |

Each rate item has the following attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `start` | `datetime` | The date/time when the rate starts |
| `end` | `datetime` | The date/time when the rate ends |
| `value_inc_vat` | `float` | The value of the rate including VAT. This is in pounds and pence (e.g. 1.01 = £1.01) |
| `is_capped` | `boolean` | Indicates if the rate has been capped by a [configured price cap](../setup/account.md#pricing-caps) |

## Smart Meter Entities

If your account information doesn't determine you have a smart meter, then you will have the following entities in a disabled state. If you enable these entities, they might not work correctly in this scenario. 

If you are wishing to use these sensors with the Energy Dashboard, then you can follow this [guide](../setup/energy_dashboard.md).

> By default, it's not possible to include current consumption sensors. This is due to EDF Energy only receive data from the smart meters up to the previous day.

### Previous Accumulative Consumption (m3)

`sensor.edf_energy_gas_{{METER_SERIAL_NUMBER}}_{{MPRN_NUMBER}}_previous_accumulative_consumption_m3`

The total consumption reported by the meter for the previous available full day in m3. If for example data is available up to `01:00` of `2024-09-02`, then this sensor will report the cost between `2024-09-01T00:00:00Z` and `2024-09-02T00:00:00Z`.

If your meter reports in m3, then this will be an accurate value reported by EDF Energy, otherwise it will be a calculated/estimated value.

!!! info

    This retrieves the data reported directly by the meter which is used to calculate your bill.

!!! warning

    This data won't necessarily be available at the stroke of midnight. This integration has no control of this and is at the mercy of when the data is available by EDF Energy. 
    
    Because this sensor only looks at the last complete day, if the data takes longer than 24 hours to populate then the sensor will not update straight away. You can look at the [data_last_retrieved sensor](./diagnostics.md#previous-consumption-and-rates-data-last-retrieved) which indicates when the data was last retrieved.

| Attribute | Type | Description |
|-----------|------|-------------|
| `mprn` | `string` | The mprn for the associated meter |
| `serial_number` | `string` | The serial for the associated meter |
| `is_estimated` | `boolean` | Determines if the consumption was estimated. This can occur if your meter reports in `kwh`. |
| `total_kwh` | `float` | The total energy value for the previous day in `kwh`. If your meter reports in `m3`, then this will be estimated using your set [calorific value](../setup/account.md#calorific-value) |
| `total_m3` | `float` | The total energy value for the previous day in `m3`. If your meter reports in `kwh`, then this will be estimated using your set [calorific value](../setup/account.md#calorific-value) |
| `charges` | `array` | Collection of consumption periods for the previous day broken down into 30 minute periods. |
| `calorific_value` | `float` | The calorific value used for the calculations, as set in your [account](../setup/account.md#calorific-value). |

Each charge item has the following attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `start` | `datetime` | The date/time when the consumption starts |
| `end` | `datetime` | The date/time when the consumption ends |
| `consumption` | `float` | The consumption value of the specified period |

!!! info

    You can use the [data_last_retrieved sensor](./diagnostics.md#previous-consumption-and-rates-data-last-retrieved) to determine when the underlying data was last retrieved from the EDF Energy servers.

### Previous Accumulative Consumption (kWh)

`sensor.edf_energy_gas_{{METER_SERIAL_NUMBER}}_{{MPRN_NUMBER}}_previous_accumulative_consumption_kwh`

The total consumption reported by the meter for the previous available full day in kwh. If for example data is available up to `01:00` of `2024-09-02`, then this sensor will report the cost between `2024-09-01T00:00:00Z` and `2024-09-02T00:00:00Z`.

If your meter reports in kwh, then this will be an accurate value reported by EDF Energy, otherwise it will be a calculated/estimated value.

Due to limitation of HA entities, the data will be updated as a single record, which means the history of the sensor will not be broken down further than once a day. If you want the cost broken down into hourly chunks, you can use the statistic entities used for the [energy dashboard](../setup/energy_dashboard.md#previous-day-consumption).

!!! info

    This retrieves the data reported directly by the meter which is used to calculate your bill.

!!! warning

    This data won't necessarily be available at the stroke of midnight. This integration has no control of this and is at the mercy of when the data is available by EDF Energy. 
    
    Because this sensor only looks at the last complete day, if the data takes longer than 24 hours to populate then the sensor will not update straight away. You can look at the [data_last_retrieved sensor](./diagnostics.md#previous-consumption-and-rates-data-last-retrieved) which indicates when the data was last retrieved.

| Attribute | Type | Description |
|-----------|------|-------------|
| `mprn` | `string` | The mprn for the associated meter |
| `serial_number` | `string` | The serial for the associated meter |
| `is_estimated` | `boolean` | Determines if the consumption was estimated. This can occur if your meter reports in `m3`. |
| `charges` | `array` | Collection of consumption periods for the previous day broken down into 30 minute periods. |
| `calorific_value` | `float` | The calorific value used for the calculations, as set in your [account](../setup/account.md#calorific-value). |

Each charge item has the following attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `start` | `datetime` | The date/time when the consumption starts |
| `end` | `datetime` | The date/time when the consumption ends |
| `consumption` | `float` | The consumption value of the specified period |

!!! info

    You can use the [data_last_retrieved sensor](./diagnostics.md#previous-consumption-and-rates-data-last-retrieved) to determine when the underlying data was last retrieved from the EDF Energy servers.

### Previous Accumulative Cost

`sensor.edf_energy_gas_{{METER_SERIAL_NUMBER}}_{{MPRN_NUMBER}}_previous_accumulative_cost`

The total cost for the previous available full day, including the standing charge. If for example data is available up to `01:00` of `2024-09-02`, then this sensor will report the cost between `2024-09-01T00:00:00Z` and `2024-09-02T00:00:00Z`. 

Due to limitation of HA entities, the data will be updated as a single record, which means the history of the sensor will not be broken down further than once a day. If you want the cost broken down into hourly chunks, you can use the statistic entities used for the [energy dashboard](../setup/energy_dashboard.md#previous-day-consumption).

!!! info

    This retrieves the data reported directly by the meter which is used to calculate your bill.

!!! warning

    This data won't necessarily be available at the stroke of midnight. This integration has no control of this and is at the mercy of when the data is available by EDF Energy. 
    
    Because this sensor only looks at the last complete day, if the data takes longer than 24 hours to populate then the sensor will not update straight away. You can look at the [data_last_retrieved sensor](./diagnostics.md#previous-consumption-and-rates-data-last-retrieved) which indicates when the data was last retrieved.

| Attribute | Type | Description |
|-----------|------|-------------|
| `mprn` | `string` | The mprn for the associated meter |
| `serial_number` | `string` | The serial for the associated meter |
| `tariff_code` | `string` | The tariff that determined the cost |
| `standing_charge` | `float` | The standing charge included in the cost. This is in pounds and pence (e.g. 1.01 = £1.01) |
| `total_without_standing_charge` | `float` | The total cost of the previous day excluding the standing charge. This is in pounds and pence (e.g. 1.01 = £1.01) |
| `total` | `float` | The total cost for the previous day. This is in pounds and pence (e.g. 1.01 = £1.01) |
| `charges` | `array` | Collection of consumption periods and costs for the previous day broken down into 30 minute periods. |
| `calorific_value` | `float` | The calorific value used for the calculations, as set in your [account](../setup/account.md#calorific-value). |

Each charge item has the following attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `start` | `datetime` | The date/time when the consumption starts |
| `end` | `datetime` | The date/time when the consumption ends |
| `rate` | `float` | The rate the consumption is charged at. This is in pounds and pence (e.g. 1.01 = £1.01) |
| `consumption` | `float` | The consumption value of the specified period |
| `cost` | `float` | The cost of the consumption at the specified rate. This is in pounds and pence (e.g. 1.01 = £1.01) |

!!! info

    You can use the [data_last_retrieved sensor](./diagnostics.md#previous-consumption-and-rates-data-last-retrieved) to determine when the underlying data was last retrieved from the EDF Energy servers.

## Previous Consumption Day Rates

`event.edf_energy_gas_{{METER_SERIAL_NUMBER}}_{{MPRN_NUMBER}}_previous_consumption_rates`

The state of this sensor states when the previous consumption's rates were last updated. This is typically the same as the previous available full day's rates, but could differ depending on available data. The attributes of this sensor exposes the previous consumption's rates. 

!!! note
    This is [disabled by default](../faq.md#there-are-entities-that-are-disabled-why-are-they-disabled-and-how-do-i-enable-them).

| Attribute | Type | Description |
|-----------|------|-------------|
| `rates` | `array` | The list of rates applicable for the previous consumption |
| `tariff_code` | `string` | The tariff code associated with previous consumption's rates |

Each rate item has the following attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `start` | `datetime` | The date/time when the rate starts |
| `end` | `datetime` | The date/time when the rate ends |
| `value_inc_vat` | `float` | The value of the rate including VAT. This is in pounds and pence (e.g. 1.01 = £1.01) |
| `is_capped` | `boolean` | Indicates if the rate has been capped by a [configured price cap](../setup/account.md#pricing-caps) |

## Smart Meter Live Entities

!!! warning "Not available with EDF Energy"

    EDF Energy's API does **not** provide a live/current-day consumption feed (unlike Octopus Energy's Home Mini), so this integration does not create any live consumption entities — `current_consumption`, `current_accumulative_consumption` (m3/kWh), `current_total_consumption` (m3/kWh) or `current_accumulative_cost`. Older versions of these docs listed them; they were inherited from upstream and never populated on EDF.

    To feed today's gas usage into the Energy dashboard, use an independent live source such as Hildebrand Bright / Glow. See [Energy Dashboard → Current Consumption](../setup/energy_dashboard.md#current-consumption) for the full setup.
