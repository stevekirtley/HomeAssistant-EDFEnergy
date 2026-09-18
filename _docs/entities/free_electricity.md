# Free Electricity Sessions

Free electricity sessions reach EDF customers through several schemes - Sunday Saver, Power Perks, and one-off events such as the World Cup windows. The entities on this page are the merged view: every session, whatever its source, in one place. Each session carries a `source` of `sunday_saver`, `power_perks`, `football` or `football_et`.

Power Perks sessions come from a relay that parses EDF's announcement text, because EDF publish them nowhere else; see the `register_power_perks_session` action in [services](../services.md#power-perks) for adding one by hand.

## Next Free Electricity Session Start

`sensor.edf_energy_{{ACCOUNT_ID}}_next_free_electricity_session_start`

When the current or next free electricity session starts, from any source. While a session is in progress this is that session's start; otherwise it is the start of the next one to come. `unknown` when nothing is scheduled.

This is the sensor to build automations on when you want to prepare for a free window without caring which scheme is running it - for example, skipping an overnight paid charge when a free window starts within the next 24 hours.

| Attribute | Type | Description |
|-----------|------|-------------|
| `code` | `string` | The session's unique code |
| `source` | `string` | Which scheme the session belongs to |
| `start` | `datetime` | When the session starts |
| `end` | `datetime` | When the session ends |
| `duration_in_minutes` | `float` | The length of the session |
| `is_active` | `boolean` | Whether the session is in progress now |

## Next Free Electricity Session End

`sensor.edf_energy_{{ACCOUNT_ID}}_next_free_electricity_session_end`

When the current or next free electricity session ends. Same selection rule and attributes as the start sensor.

## Free Electricity Session

`calendar.edf_energy_{{ACCOUNT_ID}}_free_electricity_session`

A calendar of every known session, on while one is in progress. Sessions already finished today stay on the calendar until the day rolls over.

## Free Electricity Session Events

`event.edf_energy_{{ACCOUNT_ID}}_free_electricity_session_events`

Fires whenever the set of sessions changes, and hourly as a heartbeat. Its `events` attribute lists today's and upcoming sessions in the same shape as the upstream Octopus Energy integration, so tools built for that, such as Predbat, work unchanged. `free_electricity_windows` carries the last 60 days of history for the panel.
