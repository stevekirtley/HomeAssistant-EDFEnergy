# Account

Setup is done entirely via the [integration UI](https://my.home-assistant.io/redirect/config_flow_start/?domain=edf_energy).

## Credentials

You will need:

- **Email address** — the email you use to log in to the EDF Energy app or website
- **Password** — your EDF Energy account password
- **Account number** — format `A-AAAA1111`, shown in the EDF Energy app under **Account** or at the top of any bill

On first setup, the integration uses your email and password to generate an **API key**, which is then stored securely in Home Assistant. Your password is used only once and is never stored. All subsequent communication with the EDF Energy API uses the stored key.

If you already have an API key (for example, from a previous setup), you can paste it directly into the **API key** field and leave the email and password blank.

!!! info

    If you upgrade from an earlier version of this integration that stored a refresh token, the migration to an API key happens automatically on the next restart — no action needed.

## Calorific Value

When calculating gas costs, a calorific value is included in the calculation. Unfortunately this changes from region to region and is not provided by the EDF Energy API. The default value of this is `40`, but if you check your latest bill you should be able to find the value for you. This will give you a more accurate consumption and cost calculation when your meter reports in `m3`.

!!! info

    Changing this will change future calculations. It will not change calculations that have been made in the past.

## Pricing Caps

There has been inconsistencies across tariffs on whether government pricing caps are included or not. Therefore the ability to configure pricing caps has been added within you account. This is configured in pounds and pence format (e.g. 0.12 for 12p).

!!! info

    While rates are reflected straight away, consumption based sensors may take up to 24 hours to reflect. This is due to how they look at data and cannot be changed.

## Favour direct debit rates

There are some tariffs where direct debit and non direct debit rates are available. This toggle determines which rate to use in these situations.


!!! info

    It might take a couple of minutes for these changes to reflect once changed.

## Sunday Saver

### Automatically enrol in Sunday Saver

When enabled (the default), the integration will automatically opt your account into the EDF Energy Sunday Saver challenge each month. Sunday Saver provides free electricity for a set window on Sunday mornings.

If you prefer to manage enrolment manually — for example to review the terms before each month's challenge — disable this toggle and use the [`join_sunday_saver`](../services.md#edf_energyjoin_sunday_saver) service instead.

When the integration successfully enrols your account for the first time, a persistent notification will appear in Home Assistant to confirm.

See the [Sunday Saver entities](../entities/sunday_saver.md) for the sensors exposed by this feature.

## Smart Charging Settings

### Manually refresh intelligent dispatches

By default, Smart Charging dispatches are retrieved [periodically](../faq.md#how-often-is-data-refreshed). This is fine for most scenarios, but this can be a little slow depending on what else you're doing off the back of the dispatches. If you have other ways of knowing when new dispatches should be available (e.g. your charger changes to a charging state or a manual button in your HA dashboard), then you can turn on `Manually refresh intelligent dispatches`. This will disable the periodic refreshing and expose a [service](../services.md#edf_energyrefresh_intelligent_dispatches) which can be called to refresh the dispatches.

!!! warning

    This should only be turned on if you know what you're doing. Turning this on and not calling the service/action can result in rate and Smart Charging related sensors not updating correctly.

### Intelligent rates mode

If you are on a Smart Charging tariff then it's possible for you to get cheaper rates outside of your normal off peak periods if EDF Energy schedules the charges and your car accepts the charges. The rate information provided by EDF Energy doesn't take these periods into account, so the integration has to use the planned/completed dispatch information to adjust the rates appropriately. Due to the quality of the available data, this _can_ be off sometimes. This feature allows how the rate information is adjusted in these scenarios.

#### Planned and started dispatches will turn into off peak rates

This is the default behaviour. In this scenario, all planned dispatches will be assumed to be converted into successful off peak charges by the car and therefore all rates during these periods will be converted into the off peak rate. This will be indicated by the `is_intelligent_adjusted` property against the rate. This is useful when planning other devices to turn on in the future during these cheap periods.

Please see the [FAQ](../faq.md#what-are-started-dispatches-and-how-are-they-calculated) for information on what started dispatches are.

!!! warning

    One side effect of this is around cost sensors, where if a planned dispatch does not turn into a started dispatch, the cost sensor can increase in value when the planned dispatch is removed.

#### Only started dispatches will turn into off peak rates

In this scenario only started dispatches will be taken into account for adjustments meaning all rates during only started dispatch periods will be converted into the off peak rate. This will be indicated by the `is_intelligent_adjusted` property. This means no future planning can be made to take advantage of these cheap periods by rates alone.

Please see the [FAQ](../faq.md#what-are-started-dispatches-and-how-are-they-calculated) for information on what started dispatches are.

!!! warning

    One side effect of this is around cost sensors, where when a started dispatch arrives the cost sensor will decrease in value.

### Minimum required minutes for planned dispatches

EDF Energy Smart Charging can be known to provide planned dispatches with small windows (e.g. 3 minutes long). Depending on your charging mechanism, these small windows can result in the charging mechanism not having long enough to react and therefore causing these periods to not be counted as off peak periods. If you are doing other things during dispatch periods, this can result in your home performing tasks that are then counted as off peak tasks, or may not be long enough with the default refresh rate to do anything meaningful.

Therefore, you can use this setting to determine the minimum length in minutes a planned dispatch must be in order to be taken into account by the integration. If a planned dispatch is below this number, then the [is dispatching sensor](../entities/intelligent.md#is-dispatching) and [off peak sensor](../entities/electricity.md#off-peak) will not turn on during these dispatches, nor will the [rate sensors](../entities/electricity.md#current-rate) be adjusted to off peak rates during these periods.

This defaults to zero to include all possible planned dispatches.
