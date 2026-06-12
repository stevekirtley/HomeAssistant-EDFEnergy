# Free Electricity

These entities are for EDF Energy's free electricity promotions, where electricity is free to
use for a limited window. These currently come from more than one source:

- **Sunday Saver** — EDF's own promotion, retrieved from the EDF Energy API.
- **Event-based free electricity** — free windows tied to certain football matches (e.g.
  England/Scotland World Cup games). EDF does not expose these through their API, so the
  integration derives them from a public match schedule.

To make this data easy to consume — including by tools such as
[Predbat](https://springfall2008.github.io/batpred/) — all known free electricity sessions
from every source are aggregated into a single set of entities that match the shape used by
the upstream [Octopus Energy integration](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy).

## Free Electricity Now

`binary_sensor.edf_energy_{{ACCOUNT_ID}}_free_electricity_now`

Binary sensor to indicate if a free electricity session is currently active.

It is `on` while a free electricity window (from any source) is active, and `off` otherwise.
It uses precise point-in-time triggers so it switches exactly at the start and end of each
window. If a Sunday Saver window and an event-based window overlap, Sunday Saver takes
precedence.

## Free Electricity Sessions Calendar

`calendar.edf_energy_{{ACCOUNT_ID}}_free_electricity_session`

Read only [calendar](https://www.home-assistant.io/integrations/calendar) sensor to record
free electricity sessions. Will be `on` when a free electricity session is active. Calendar
events will be automatically added/removed by the integration as sessions are discovered.

Standard calendar attributes will indicate the current/next session.

!!! warning

    The sensor does not store past events indefinitely. Past events could be removed without notice.

#### Automation Example

Below is an example of raising a persistent notification 5 minutes before a free electricity
session starts.

```yaml
triggers:
- trigger: calendar
  entity_id: calendar.edf_energy_{{ACCOUNT_ID}}_free_electricity_session
  event: start
  offset: "-00:05:00"
actions:
- action: persistent_notification.create
  data:
    title: Free Electricity Session Starting
    message: >
      {% set start_time = (state_attr(trigger.entity_id, 'start_time') | as_datetime).strftime('%H:%M') %}
      Free electricity session starts at {{ start_time }}.
```

## Free Electricity Session Events

`event.edf_energy_{{ACCOUNT_ID}}_free_electricity_session_events`

The state of this sensor states when the free electricity session events were last updated. The
attributes of this sensor expose every known upcoming free electricity session, regardless of
which source it came from.

This entity intentionally mirrors the Octopus integration's
`event.octopus_energy_{{ACCOUNT_ID}}_octoplus_free_electricity_session_events` sensor, so any
consumer that already reads the Octopus free electricity session events sensor can read this one
with little or no change.

| Attribute | Type | Description |
|-----------|------|-------------|
| `account_id` | `string` | The account these sessions belong to |
| `events` | `array` | The collection of known free electricity sessions |

Each item in the `events` array will include the following attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `code` | `string` | A unique identifier for the session |
| `source` | `string` | Where the session came from — `sunday_saver` or `football` |
| `start` | `datetime` | The date/time the session starts |
| `end` | `datetime` | The date/time the session ends |
| `duration_in_minutes` | `integer` | The duration of the session in minutes |

!!! note

    The `source` attribute is specific to this integration (EDF surfaces free electricity from
    multiple sources). Consumers expecting the Octopus format can simply ignore it.

### Using with Predbat

Predbat can read this sensor directly via its `octopus_free_session` setting and will treat each
session as a zero-rate import window, planning battery charge/discharge around it in advance.
Because `octopus_free_session` accepts a regular expression, a single configuration can
auto-discover whichever supplier integration is installed (Octopus and/or EDF):

```yaml
octopus_free_session: "re:(event.(octopus_energy_[0-9a-z_]+_octoplus_free_electricity_session_events|edf_energy_[0-9a-z_]+_free_electricity_session_events))"
```

!!! note

    Predbat's `forecast_hours` is measured from midnight UTC, not from the current time, so a
    session that is N hours away needs `forecast_hours` to cover the hours since midnight plus N
    for the zero-rate window to be applied to the plan.

## Event Free Electricity Start / End

`sensor.edf_energy_{{ACCOUNT_ID}}_event_free_start`

`sensor.edf_energy_{{ACCOUNT_ID}}_event_free_end`

Timestamp sensors reporting the start and end of the current or next **event-based** (e.g.
football) free electricity window. These are retained for backwards compatibility; for a unified
view across all sources, prefer the
[Free Electricity Session Events](#free-electricity-session-events) sensor above.

| Attribute | Type | Description |
|-----------|------|-------------|
| `account_id` | `string` | The account the event belongs to |
| `event_name` | `string` | The name of the event (e.g. the football fixture) |
| `start` / `end` | `datetime` | The other end of the window (the opposite sensor's value) |
| `is_active` | `boolean` | Whether the window is currently active |
