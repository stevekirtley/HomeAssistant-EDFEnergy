# Billing

Four sensors covering the money side of the account. They are created whether or not the
[panel's beta tabs](../setup/account_tab.md) are turned on.

| Sensor | What it is |
|--------|------------|
| `sensor.edf_energy_{{ACCOUNT_ID}}_account_balance` | The account balance, positive when in credit |
| `sensor.edf_energy_{{ACCOUNT_ID}}_last_bill_amount` | What the latest statement charged |
| `sensor.edf_energy_{{ACCOUNT_ID}}_next_payment_amount` | The next direct debit collection |
| `sensor.edf_energy_{{ACCOUNT_ID}}_refund_status` | The status of the latest refund request |

## Account balance

The balance as EDF report it: **positive means in credit**, which is the usual state for an
account on direct debit, and is the way round it reads on the bill and in the app.

| Attribute | |
|-----------|---|
| `account_status` | EDF's status for the account, e.g. `ACTIVE` |

!!! warning "The balance is not what you can get refunded"

    EDF only refund what has been paid in by direct debit. See `refund_status` below.

## Last bill amount

The charges on the most recent statement - not the balance it closed on.

| Attribute | |
|-----------|---|
| `bill_id` | EDF's id for the statement |
| `issued_date` | When EDF issued it |
| `period_from`, `period_to` | The period it covers |
| `due_date` | When payment is due |
| `closing_balance` | The balance the statement closed on |

## Next payment amount

The next direct debit collection.

| Attribute | |
|-----------|---|
| `next_payment_date` | The next collection date, worked out from the payment day |
| `payment_day` | The day of the month EDF collect on |
| `frequency` | e.g. `Monthly` |
| `is_variable` | Whether the amount varies |
| `payment_method` | e.g. `DIRECT_DEBIT` |

!!! note "A variable schedule has no amount"

    On a variable schedule EDF collect whatever the period came to, so there is no figure
    until the statement is cut and the sensor reads unknown. `is_variable` says why. EDF
    report the amount as 0 in that case, which would otherwise read as a free month.

    `next_payment_date` is worked out from the payment day EDF give, since they do not
    supply a date. A day beyond the length of the month lands on the last day of it.

## Refund status

The status of the most recent refund request, or `None requested` on an account that has
never asked for one. Statuses seen so far run `REQUESTED` → `SUBMITTED` → `PAID`.

| Attribute | |
|-----------|---|
| `amount` | The amount of the latest request |
| `payment_date` | When it is due to be paid, which moves as the request progresses |
| `reason` | EDF's reason code for it, e.g. `PARTIAL_CREDIT_REFUND` |
| `open_requests` | How many requests have not been settled yet |
| `can_request_refund` | Whether EDF say they will accept a new request right now - advisory, see below |
| `cannot_request_reason` | EDF's reason when they say they will not, e.g. `HAS_NOT_GIVEN_READINGS_RECENTLY` |
| `maximum_refund` | **What EDF will actually refund** |

Treat `can_request_refund` as advice rather than a rule. It read false on a real account,
with `HAS_NOT_GIVEN_READINGS_RECENTLY` as the reason, while EDF accepted and paid two
requests made in spite of it - so the panel shows the reason but does not withhold the
request form, and neither does the websocket command behind it.

`maximum_refund` is the figure to automate against. It tracks what has been paid in by
direct debit and is normally far below the balance - on an account £1,234 in credit it was
£98.76.

## What is deliberately not here

The statement list, the account ledger and the referral list are **not** on any sensor or
attribute. Each is dozens or hundreds of rows, the referrals carry other people's names,
and nothing useful triggers on them - so putting them in attributes would write all of it
into the recorder database every time it changed. The panel asks for them over the
websocket while the tab is open and nothing is persisted. They are visible on the
[Account and Perks tabs](../setup/account_tab.md).

## Diagnostics

A diagnostics download redacts the figures on these four sensors, since diagnostics are
usually attached to a public issue. Whether a sensor has a value, when it last changed, and
EDF's own eligibility reason all survive, which is what is needed to diagnose a fault with
one.
