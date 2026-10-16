# Panel Tabs (beta)

With the beta flag on, the EDF Energy panel becomes a small dashboard: the page you already
know becomes the **Overview** tab, and four more sit alongside it.

It is **off by default** while it is being built out. With it off the panel is exactly the
single screen it has always been - no tab bar, nothing moved.

## Turning it on

1. Go to **Settings > Devices & services > EDF Energy**
2. Click **Configure** on your account entry
3. Tick **Show account tab (beta)** and submit

The integration reloads itself, and the panel picks the change up on its own - you should
not need to refresh your browser. Untick it to put the panel back exactly as it was.

## The tabs

| Tab | What is on it |
|-----|---------------|
| **Overview** | Everything that was on the panel before, unchanged: the car controls, the schemes, and the off-peak and dispatch history |
| **Charging** | Just the car: the smart charge controls, the off-peak windows and the dispatch windows |
| **Usage** | The consumption chart |
| **Perks** | The schemes - World Cup, Flextras free hours, free electricity sessions - and your referrals |
| **Account** | The money: balance, statements, transactions, refunds, and your tariffs and meters |

Nothing was taken off the Overview to make room. The Charging and Perks tabs are cuts of
the same cards, so a change in one place shows up in both.

## Account

### At a glance

Balance, the last statement, the next payment and how much EDF would refund. These four are
also published as sensors - see [Billing sensors](#billing-sensors) below.

### Statements

Every statement on the account, newest first, with the period it covers, what it charged
and the balance it closed on. **Open** fetches the PDF from EDF and opens it in a new tab.

!!! info "Statement links are not stored"

    EDF hand out a short-lived signed link rather than a permanent URL. It is fetched at the
    moment you press **Open** and expires within the hour, so nothing is cached, written to
    an attribute, or kept anywhere in Home Assistant. Pressing **Open** again gets a fresh
    one.

### Transactions

The account ledger - charges, payments, credits and refunds - signed so it reads like a
statement rather than a column of positive numbers. EDF report every amount positive and
leave the direction to the entry's type, so the integration applies the sign.

The running balance after each entry is shown underneath the amount, which makes it
possible to check the ledger adds up.

### Refunds

How much of your credit balance EDF will actually refund, any past requests and their
status, and a box to request one.

!!! note "EDF saying no is a caveat, not a block"

    EDF publish an eligibility flag and a reason, and the panel shows the reason when they
    say no - but it still lets you make the request. The flag has proved unreliable: on one
    account it read `HAS_NOT_GIVEN_READINGS_RECENTLY` while EDF went on to accept and pay
    two requests made anyway. Whether to refuse is EDF's decision when the request reaches
    them, and a request they do refuse is simply declined at their end. Progress shows up
    under past requests either way.

!!! warning "The refundable amount is not your balance"

    EDF only refund what has been paid in by direct debit. On an account £1,234 in credit
    the refundable figure was £98.76. The panel will not let you ask for more than EDF
    quote, and neither will the websocket command behind it.

Requesting a refund takes two presses: the first arms the button and tells you what it is
about to do, the second sends it. It is admin-only, and the amount is checked against EDF's
own maximum again on the Home Assistant side before anything leaves. Each request carries
an idempotency key built from the account, the amount and the day, so a double press is the
same request rather than a second refund.

Statuses seen so far run `REQUESTED` → `SUBMITTED` → `PAID`.

### Tariffs and meters

Every electricity and gas meter point on the account, with its MPAN or MPRN, meter serial,
make and firmware, and whether EDF consider it smart.

Underneath each meter point is its tariff history: the agreement in force marked **Live**,
and every agreement that has ended beneath it. This comes out of the account information
the integration already holds, so it costs no extra calls to EDF.

!!! note

    EDF's API gives the integration tariff and product *codes*, not the name the tariff is
    marketed under. `EDF_EV_FIX_GOELEC_18M_HH` is the product EDF call "Go Electric 18m".
    The full tariff code is shown underneath, which is the one to match against a bill.

## Perks

### Referrals

Your referral link and reward amounts, how many people have joined on it, and the list of
them with each one's status - EDF's own wording, so "Paid" and "Switch in progress" appear
as they do in the app.

!!! info "Referral names are not stored"

    These are other people's names. They are fetched from EDF while the tab is open and
    rendered, and that is all - there is no sensor, no attribute and no recorder row holding
    them.

## Usage

One chart covering every meter on the account - electricity import, export and gas together
- in kWh or in pounds, by **Day** (a month at a time), **Month** (a year at a time) or
**Year**.

The cost view uses the
[`_includingsc` statistics](./energy_dashboard.md#previous-day-consumption), so it includes
the standing charge and matches your bill. Export has no standing charge, so it uses the
plain cost statistic.

!!! warning "Today will always look empty"

    The chart is built from the same daily statistics as the energy dashboard, and EDF
    publish readings **one to two days behind**. The current day, and often yesterday, will
    have nothing against them. That is EDF's data arriving late, not a gap in your meter.

    It also means a brand new install has nothing to chart until the first day's statistics
    land. Days from before you installed the integration are filled in on startup, up to a
    fortnight back.

## Billing sensors

Four sensors come with this, and unlike the tabs they are **not** behind the beta flag -
they are created whichever way the flag is set: account balance, last bill amount, next
payment amount and refund status. See [Billing entities](../entities/billing.md) for what
each one carries and how to read it.

## Why it is beta

The layout is expected to change between releases. If something looks wrong, please
[raise an issue](https://github.com/stevekirtley/HomeAssistant-EDFEnergy/issues) with a
screenshot rather than assuming it is meant to look that way.
