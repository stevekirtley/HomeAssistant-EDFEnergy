# Account Tab (beta)

The EDF Energy panel has a second tab showing your meters, your tariff history and a chart
of what you have used. It is **off by default** while it is being built out.

## Turning it on

1. Go to **Settings > Devices & services > EDF Energy**
2. Click **Configure** on your account entry
3. Tick **Show account tab (beta)** and submit

The integration reloads itself, and the panel picks the change up on its own - you should
not need to refresh your browser. Untick it to put the panel back exactly as it was.

## What it shows

### Meters and tariffs

Every electricity and gas meter point on the account, with its MPAN or MPRN, meter serial,
make and firmware, and whether EDF consider it smart.

Underneath each meter point is its tariff history: the agreement in force marked **Live**,
and every agreement that has ended beneath it. This comes out of the account information
the integration already holds, so it costs no extra calls to EDF.

!!! note

    EDF's API gives the integration tariff and product *codes*, not the name the tariff is
    marketed under. `EDF_EV_FIX_GOELEC_18M_HH` is the product EDF call "Go Electric 18m".
    The full tariff code is shown underneath, which is the one to match against a bill.

### Consumption

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

## Why it is beta

The layout is expected to change between releases, and more is being added - bills,
transactions, referrals and refunds. If something looks wrong, please
[raise an issue](https://github.com/stevekirtley/HomeAssistant-EDFEnergy/issues) with a
screenshot rather than assuming it is meant to look that way.
