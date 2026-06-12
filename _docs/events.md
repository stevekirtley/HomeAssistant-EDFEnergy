# Events

The following events are raised by the integration. These events power various entities and can also be used within automations.

## Rates

### Electricity Current Day Rates

`edf_energy_electricity_current_day_rates`

This is fired when the current day rates are updated.

| Attribute | Type | Description |
|-----------|------|-------------|
| `rates` | `array` | The list of rates applicable for the current day |
| `tariff_code` | `string` | The tariff code associated with current day's rates |
| `mpan` | `string` | The mpan of the meter associated with these rates |
| `serial_number` | `string` | The serial number of the meter associated with these rates |
| `min_rate` | `float` | The minimum/lowest rate in the discovered rates collection |
| `max_rate` | `float` | The maximum/highest rate in the discovered rates collection |
| `average_rate` | `float` | The average rate in the discovered rates collection |

#### Automation Example

```yaml
- trigger:
  - platform: event
    event_type: edf_energy_electricity_current_day_rates
  condition: []
  action:
  - service: persistent_notification.create
    data:
      title: "Rates Updated"
      message: >
        New rates available for {{ trigger.event.data.mpan }}. Starting value is {{ trigger.event.data.rates[0]["value_inc_vat"] }}
```

### Electricity Previous Day Rates

`edf_energy_electricity_previous_day_rates`

This is fired when the previous day rates are updated.

| Attribute | Type | Description |
|-----------|------|-------------|
| `rates` | `array` | The list of rates applicable for the previous day |
| `tariff_code` | `string` | The tariff code associated with previous day's rates |
| `mpan` | `string` | The mpan of the meter associated with these rates |
| `serial_number` | `string` | The serial number of the meter associated with these rates |
| `min_rate` | `float` | The minimum/lowest rate in the discovered rates collection |
| `max_rate` | `float` | The maximum/highest rate in the discovered rates collection |
| `average_rate` | `float` | The average rate in the discovered rates collection |

#### Automation Example

```yaml
- trigger:
  - platform: event
    event_type: edf_energy_electricity_previous_day_rates
  condition: []
  action:
  - service: persistent_notification.create
    data:
      title: "Rates Updated"
      message: >
        New rates available for {{ trigger.event.data.mpan }}. Starting value is {{ trigger.event.data.rates[0]["value_inc_vat"] }}
```

### Electricity Next Day Rates

`edf_energy_electricity_next_day_rates`

This is fired when the next day rates are updated.

| Attribute | Type | Description |
|-----------|------|-------------|
| `rates` | `array` | The list of rates applicable for the next day |
| `tariff_code` | `string` | The tariff code associated with next day's rates |
| `mpan` | `string` | The mpan of the meter associated with these rates |
| `serial_number` | `string` | The serial number of the meter associated with these rates |
| `min_rate` | `float` | The minimum/lowest rate in the discovered rates collection |
| `max_rate` | `float` | The maximum/highest rate in the discovered rates collection |
| `average_rate` | `float` | The average rate in the discovered rates collection |

#### Automation Example

```yaml
- trigger:
  - platform: event
    event_type: edf_energy_electricity_next_day_rates
  condition: []
  action:
  - service: persistent_notification.create
    data:
      title: "Rates Updated"
      message: >
        New rates available for {{ trigger.event.data.mpan }}. Starting value is {{ trigger.event.data.rates[0]["value_inc_vat"] }}
```

### Electricity Previous Consumption Rates

`edf_energy_electricity_previous_consumption_rates`

This is fired when the [previous consumption's](./entities/electricity.md#previous-accumulative-consumption) rates are updated.

| Attribute | Type | Description |
|-----------|------|-------------|
| `rates` | `array` | The list of rates applicable for the previous consumption |
| `tariff_code` | `string` | The tariff code associated with previous consumption's rates |
| `mpan` | `string` | The mpan of the meter associated with these rates |
| `serial_number` | `string` | The serial number of the meter associated with these rates |
| `min_rate` | `float` | The minimum/lowest rate in the discovered rates collection |
| `max_rate` | `float` | The maximum/highest rate in the discovered rates collection |
| `average_rate` | `float` | The average rate in the discovered rates collection |

#### Automation Example

```yaml
- trigger:
  - platform: event
    event_type: edf_energy_electricity_previous_consumption_rates
  condition: []
  action:
  - service: persistent_notification.create
    data:
      title: "Rates Updated"
      message: >
        New rates available for {{ trigger.event.data.mpan }}. Starting value is {{ trigger.event.data.rates[0]["value_inc_vat"] }}
```

### Gas Current Day Rates

`edf_energy_gas_current_day_rates`

This is fired when the current day rates are updated.

| Attribute | Type | Description |
|-----------|------|-------------|
| `rates` | `array` | The list of rates applicable for the current day |
| `tariff_code` | `string` | The tariff code associated with current day's rates |
| `mprn` | `string` | The mprn of the meter associated with these rates |
| `serial_number` | `string` | The serial number of the meter associated with these rates |
| `min_rate` | `float` | The minimum/lowest rate in the discovered rates collection |
| `max_rate` | `float` | The maximum/highest rate in the discovered rates collection |
| `average_rate` | `float` | The average rate in the discovered rates collection |

#### Automation Example

```yaml
- trigger:
  - platform: event
    event_type: edf_energy_gas_current_day_rates
  condition: []
  action:
  - service: persistent_notification.create
    data:
      title: "Rates Updated"
      message: >
        New rates available for {{ trigger.event.data.mprn }}. Starting value is {{ trigger.event.data.rates[0]["value_inc_vat"] }}
```

### Gas Previous Day Rates

`edf_energy_gas_previous_day_rates`

This is fired when the previous day rates are updated.

| Attribute | Type | Description |
|-----------|------|-------------|
| `rates` | `array` | The list of rates applicable for the previous day |
| `tariff_code` | `string` | The tariff code associated with previous day's rates |
| `mprn` | `string` | The mprn of the meter associated with these rates |
| `serial_number` | `string` | The serial number of the meter associated with these rates |
| `min_rate` | `float` | The minimum/lowest rate in the discovered rates collection |
| `max_rate` | `float` | The maximum/highest rate in the discovered rates collection |
| `average_rate` | `float` | The average rate in the discovered rates collection |

#### Automation Example

```yaml
- trigger:
  - platform: event
    event_type: edf_energy_gas_previous_day_rates
  condition: []
  action:
  - service: persistent_notification.create
    data:
      title: "Rates Updated"
      message: >
        New rates available for {{ trigger.event.data.mprn }}. Starting value is {{ trigger.event.data.rates[0]["value_inc_vat"] }}
```

### Gas Next Day Rates

`edf_energy_gas_next_day_rates`

This is fired when the next day rates are updated.

| Attribute | Type | Description |
|-----------|------|-------------|
| `rates` | `array` | The list of rates applicable for the next day |
| `tariff_code` | `string` | The tariff code associated with next day's rates |
| `mprn` | `string` | The mprn of the meter associated with these rates |
| `serial_number` | `string` | The serial number of the meter associated with these rates |
| `min_rate` | `float` | The minimum/lowest rate in the discovered rates collection |
| `max_rate` | `float` | The maximum/highest rate in the discovered rates collection |
| `average_rate` | `float` | The average rate in the discovered rates collection |

#### Automation Example

```yaml
- trigger:
  - platform: event
    event_type: edf_energy_gas_next_day_rates
  condition: []
  action:
  - service: persistent_notification.create
    data:
      title: "Rates Updated"
      message: >
        New rates available for {{ trigger.event.data.mprn }}. Starting value is {{ trigger.event.data.rates[0]["value_inc_vat"] }}
```

### Gas Previous Consumption Rates

`edf_energy_gas_previous_consumption_rates`

This is fired when the [previous consumption's](./entities/gas.md#previous-accumulative-consumption-m3) rates are updated.

| Attribute | Type | Description |
|-----------|------|-------------|
| `rates` | `array` | The list of rates applicable for the previous consumption |
| `tariff_code` | `string` | The tariff code associated with previous consumption's rates |
| `mprn` | `string` | The mprn of the meter associated with these rates |
| `serial_number` | `string` | The serial number of the meter associated with these rates |
| `min_rate` | `float` | The minimum/lowest rate in the discovered rates collection |
| `max_rate` | `float` | The maximum/highest rate in the discovered rates collection |
| `average_rate` | `float` | The average rate in the discovered rates collection |

#### Automation Example

```yaml
- trigger:
  - platform: event
    event_type: edf_energy_gas_previous_consumption_rates
  condition: []
  action:
  - service: persistent_notification.create
    data:
      title: "Rates Updated"
      message: >
        New rates available for {{ trigger.event.data.mprn }}. Starting value is {{ trigger.event.data.rates[0]["value_inc_vat"] }}
```

## Free Electricity

### All Free Electricity Sessions

`edf_energy_all_free_electricity_sessions`

This is fired whenever the set of known free electricity sessions is refreshed. It powers the
[Free Electricity Session Events](./entities/free_electricity.md#free-electricity-session-events)
sensor and aggregates sessions from every source (e.g. Sunday Saver and event-based windows).

| Attribute | Type | Description |
|-----------|------|-------------|
| `account_id` | `string` | The account these sessions belong to |
| `events` | `array` | The collection of known free electricity sessions (each with `code`, `source`, `start`, `end` and `duration_in_minutes`) |

### New Free Electricity Session

`edf_energy_new_free_electricity_session`

This is fired once for each newly discovered free electricity session.

| Attribute | Type | Description |
|-----------|------|-------------|
| `account_id` | `string` | The account the session belongs to |
| `event_code` | `string` | A unique identifier for the session |
| `event_source` | `string` | Where the session came from — `sunday_saver` or `football` |
| `event_start` | `datetime` | The date/time the session starts |
| `event_end` | `datetime` | The date/time the session ends |
| `event_duration_in_minutes` | `integer` | The duration of the session in minutes |

#### Automation Example

```yaml
- trigger:
  - platform: event
    event_type: edf_energy_new_free_electricity_session
  condition: []
  action:
  - service: persistent_notification.create
    data:
      title: "Free Electricity Session"
      message: >
        Free electricity from {{ trigger.event.data.event_start }} to {{ trigger.event.data.event_end }}.
```

## Tariff Comparisons

### Electricity Previous Consumption Tariff Comparison Rates

`edf_energy_elec_previous_consumption_tariff_comparison_rates`

This is fired when the [tariff comparison](./setup/tariff_comparison.md) rates are updated.

| Attribute | Type | Description |
|-----------|------|-------------|
| `rates` | `array` | The list of rates applicable for the previous consumption tariff comparison |
| `product_code` | `string` | The product code associated with previous consumption tariff comparison rates |
| `tariff_code` | `string` | The tariff code associated with previous consumption tariff comparison rates |
| `mprn` | `string` | The mprn of the meter associated with these rates |
| `serial_number` | `string` | The serial number of the meter associated with these rates |

#### Automation Example

```yaml
- trigger:
  - platform: event
    event_type: edf_energy_elec_previous_consumption_tariff_comparison_rates
  condition: []
  action:
  - service: persistent_notification.create
    data:
      title: "Rates Updated"
      message: >
        New rates available for {{ trigger.event.data.mprn }}. Starting value is {{ trigger.event.data.rates[0]["value_inc_vat"] }}
```

### Gas Previous Consumption Tariff Comparison Rates

`edf_energy_gas_previous_consumption_tariff_comparison_rates`

This is fired when the [tariff comparison](./setup/tariff_comparison.md) rates are updated.

| Attribute | Type | Description |
|-----------|------|-------------|
| `rates` | `array` | The list of rates applicable for the previous consumption tariff comparison |
| `product_code` | `string` | The product code associated with previous consumption tariff comparison rates |
| `tariff_code` | `string` | The tariff code associated with previous consumption tariff comparison rates |
| `mprn` | `string` | The mprn of the meter associated with these rates |
| `serial_number` | `string` | The serial number of the meter associated with these rates |

#### Automation Example

```yaml
- trigger:
  - platform: event
    event_type: edf_energy_gas_previous_consumption_tariff_comparison_rates
  condition: []
  action:
  - service: persistent_notification.create
    data:
      title: "Rates Updated"
      message: >
        New rates available for {{ trigger.event.data.mprn }}. Starting value is {{ trigger.event.data.rates[0]["value_inc_vat"] }}
```