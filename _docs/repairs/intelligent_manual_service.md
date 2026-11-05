# Repairs - Manual Smart Charging dispatch refresh

This notice is information, not a fault. Nothing is broken and you don't have to do anything
about it.

By default the integration asks EDF for your Smart Charging dispatches every few minutes, so it
notices when a charge is planned or starts. If something else already tells you the moment your
car starts charging, such as your charger's own integration, you can switch that polling off and
ask for the dispatches yourself at the right moment. You'll hear about new dispatches sooner, and
the integration makes fewer calls to EDF.

## Leaving it as it is

If you don't have a reliable way of knowing when charging starts, keep the automatic polling.
Press **Ignore** on the notice to stop it being shown.

## Switching to manual refresh

1. Go to **Settings > Devices & services > EDF Energy (UK)**.
2. On your account entry, press the three dots and choose **Reconfigure**.
3. Open **Smart Charging settings** and turn on **Manually refresh smart charging dispatches**.
4. Submit. The notice goes away.

From then on the dispatches only refresh when the
[`edfenergy_uk.refresh_intelligent_dispatches`](../services.md#edfenergy_ukrefresh_intelligent_dispatches)
action is called, so something has to call it. The quickest way is the
[Manual Smart Charging Dispatch Refreshes](../blueprints.md#manual-smart-charging-dispatch-refreshes)
blueprint. It calls the action when another integration reports your car has been plugged in,
and again whenever the dispatches haven't been refreshed for a while.

!!! warning

    With manual refresh on and nothing calling the action, the dispatches never update. Your
    rates and Smart Charging sensors then stop reflecting new charges. Only turn it on once
    something is in place to call it.

See [Manually refresh intelligent dispatches](../setup/account.md#manually-refresh-intelligent-dispatches)
for more on the setting.
