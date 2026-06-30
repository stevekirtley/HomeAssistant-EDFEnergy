# Sunday Saver

These sensors are created if your EDF Energy account is eligible for the Sunday Saver programme. Sunday Saver provides a free electricity window on Sunday mornings — typically two hours from a scheduled start time.

## Sunday Saver Start

`sensor.edf_energy_{{ACCOUNT_ID}}_sunday_saver_start`

The start time of the upcoming (or current) Sunday Saver free electricity window, as a timestamp. The state is `unknown` when no window is scheduled for the current week.

### Attributes

| Attribute | Type | Description |
|---|---|---|
| `account_id` | `string` | The EDF Energy account number |
| `has_event` | `boolean` | `true` if a free electricity window is scheduled this week |
| `free_hours` | `float` | Duration of the free window in hours (e.g. `2.0`) |
| `end` | `datetime` | End time of the free window |
| `is_active` | `boolean` | `true` if the free window is currently in progress |
| `is_enrolled` | `boolean` | `true` if the account is enrolled in Sunday Saver |
| `sunday_saver_windows` | `list` | Rolling 60-day history of past free electricity windows |

### `sunday_saver_windows` entries

Each entry in `sunday_saver_windows` contains:

| Field | Type | Description |
|---|---|---|
| `start` | `datetime` | Window start time |
| `end` | `datetime` | Window end time |
| `free_hours` | `float` | Duration of that window |

## Sunday Saver End

`sensor.edf_energy_{{ACCOUNT_ID}}_sunday_saver_end`

The end time of the upcoming (or current) Sunday Saver free electricity window, as a timestamp. The state is `unknown` when no window is scheduled.

### Attributes

| Attribute | Type | Description |
|---|---|---|
| `account_id` | `string` | The EDF Energy account number |
| `has_event` | `boolean` | `true` if a free electricity window is scheduled this week |
| `free_hours` | `float` | Duration of the free window in hours |
| `start` | `datetime` | Start time of the free window |
| `is_active` | `boolean` | `true` if the free window is currently in progress |

## Enrolment

Enrolment status is tracked via the `is_enrolled` attribute on the start sensor. The integration can manage enrolment automatically — see [Sunday Saver setup](../setup/account.md#sunday-saver) and the [`join_sunday_saver`](../services.md#edf_energyjoin_sunday_saver) service.
