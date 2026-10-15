from datetime import timedelta
import re
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.components import persistent_notification
from homeassistant.const import (
  UnitOfEnergy,
  UnitOfVolume
)

from homeassistant.util.dt import (now, parse_datetime)

from ..api_client import EDFEnergyApiClient
from ..const import DATA_ACCOUNT, DOMAIN, REGEX_DATE
from .consumption import async_import_external_statistics_from_consumption, get_electricity_consumption_statistic_name, get_electricity_consumption_statistic_unique_id, get_gas_consumption_statistic_name, get_gas_consumption_statistic_unique_id
from .cost import (async_import_external_statistics_from_cost,
                  get_electricity_cost_including_standing_charge_statistic_name,
                  get_electricity_cost_including_standing_charge_statistic_unique_id,
                  get_electricity_cost_statistic_name, get_electricity_cost_statistic_unique_id,
                  get_gas_cost_including_standing_charge_statistic_name,
                  get_gas_cost_including_standing_charge_statistic_unique_id,
                  get_gas_cost_statistic_name, get_gas_cost_statistic_unique_id)
from ..electricity import calculate_electricity_consumption_and_cost
from ..gas import calculate_gas_consumption_and_cost
from ..coordinators import get_electricity_meter_tariff, get_gas_meter_tariff

async def async_refresh_previous_electricity_consumption_data(
  hass: HomeAssistant,
  client: EDFEnergyApiClient,
  account_id: str,
  start_date: str,
  mpan: str,
  serial_number: str,
  is_smart_meter: bool,
  is_export: bool,
  notify: bool = True
):
  """Import a day at a time from start_date up to now.

  notify is turned off when the integration starts this itself to fill in days missed while
  it wasn't running (issue #42) - a notification nobody asked for is just noise.
  """
  # Inputs from automations can include quotes, so remove these
  trimmed_date = start_date.strip('\"')
  matches = re.search(REGEX_DATE, trimmed_date)
  if matches is None:
    raise vol.Invalid(f"Date '{trimmed_date}' must match format of YYYY-MM-DD.")
  
  account_result = hass.data[DOMAIN][account_id][DATA_ACCOUNT] if DATA_ACCOUNT in hass.data[DOMAIN][account_id] else None
  account_info = account_result.account if account_result is not None else None
  if account_info is None:
    raise vol.Invalid(f"Failed to find account information")
  
  if notify:
    persistent_notification.async_create(
      hass,
      title="Consumption data refreshing started",
      message=f"Consumption data from {start_date} for electricity meter {serial_number}/{mpan} has started"
    )

  period_from = parse_datetime(f'{trimmed_date}T00:00:00Z')

  previous_consumption_result = None
  previous_cost_result= None
  while period_from < now():
    period_to = period_from + timedelta(days=1)

    tariff = get_electricity_meter_tariff(period_from, account_info, mpan, serial_number)
    if tariff is None:
      persistent_notification.async_create(
        hass,
        title="Failed to find tariff information",
        message=f"Failed to find tariff information for {period_from}-{period_to} for electricity meter {serial_number}/{mpan}. Refreshing has stopped."
      )
      return

    consumption_data = await client.async_get_electricity_consumption(mpan, serial_number, period_from, period_to, is_export=is_export)
    rates = await client.async_get_electricity_rates(tariff.product, tariff.code, is_smart_meter, period_from, period_to)

    # Needed for the cost-including-standing-charge statistic only, so a day EDF cannot
    # price the standing charge for still imports everything else rather than stopping.
    # Export meters have no standing charge of their own, so none is asked for.
    standing_charge = None
    if is_export == False:
      standing_charge_data = await client.async_get_electricity_standing_charge(tariff.product, tariff.code, period_from, period_to)
      standing_charge = standing_charge_data["value_inc_vat"] if standing_charge_data is not None else None

    consumption_and_cost = calculate_electricity_consumption_and_cost(
      consumption_data,
      rates,
      0,
      None
    )
  
    if consumption_and_cost is not None:
      previous_consumption_result = await async_import_external_statistics_from_consumption(
        period_from,
        hass,
        get_electricity_consumption_statistic_unique_id(serial_number, mpan, is_export),
        get_electricity_consumption_statistic_name(serial_number, mpan, is_export),
        consumption_and_cost["charges"],
        rates,
        UnitOfEnergy.KILO_WATT_HOUR,
        "consumption",
        initial_statistics=previous_consumption_result
      )

      previous_cost_result = await async_import_external_statistics_from_cost(
        period_from,
        hass,
        get_electricity_cost_statistic_unique_id(serial_number, mpan, is_export),
        get_electricity_cost_statistic_name(serial_number, mpan, is_export),
        consumption_and_cost["charges"],
        rates,
        "GBP",
        "consumption",
        initial_statistics=previous_cost_result,
        standing_charge_in_pence=standing_charge,
        including_standing_charge_unique_id=get_electricity_cost_including_standing_charge_statistic_unique_id(serial_number, mpan, is_export),
        including_standing_charge_name=get_electricity_cost_including_standing_charge_statistic_name(serial_number, mpan, is_export)
      )

    period_from = period_to

  if notify:
    persistent_notification.async_create(
      hass,
      title="Consumption data refreshed",
      message=f"Consumption data from {start_date} for electricity meter {serial_number}/{mpan} has finished"
    )

async def async_refresh_previous_gas_consumption_data(
  hass: HomeAssistant,
  client: EDFEnergyApiClient,
  account_id: str,
  start_date: str,
  mprn: str,
  serial_number: str,
  consumption_units: str,
  calorific_value: float,
  notify: bool = True
):
  """See async_refresh_previous_electricity_consumption_data for notify."""
  # Inputs from automations can include quotes, so remove these
  trimmed_date = start_date.strip('\"')
  matches = re.search(REGEX_DATE, trimmed_date)
  if matches is None:
    raise vol.Invalid(f"Date '{trimmed_date}' must match format of YYYY-MM-DD.")
  
  account_result = hass.data[DOMAIN][account_id][DATA_ACCOUNT] if DATA_ACCOUNT in hass.data[DOMAIN][account_id] else None
  account_info = account_result.account if account_result is not None else None
  if account_info is None:
    raise vol.Invalid(f"Failed to find account information")
  
  if notify:
    persistent_notification.async_create(
      hass,
      title="Consumption data refreshing started",
      message=f"Consumption data from {start_date} for gas meter {serial_number}/{mprn} has started"
    )
  
  period_from = parse_datetime(f'{trimmed_date}T00:00:00Z')
  previous_m3_consumption_result = None
  previous_kwh_consumption_result = None
  previous_cost_result = None
  while period_from < now():
    period_to = period_from + timedelta(days=1)

    tariff = get_gas_meter_tariff(period_from, account_info, mprn, serial_number)
    if tariff is None:
      persistent_notification.async_create(
        hass,
        title="Failed to find tariff information",
        message=f"Failed to find tariff information for {period_from}-{period_to} for gas meter {serial_number}/{mprn}. Refreshing has stopped."
      )
      return

    consumption_data = await client.async_get_gas_consumption(mprn, serial_number, period_from, period_to)
    rates = await client.async_get_gas_rates(tariff.product, tariff.code, period_from, period_to)

    standing_charge_data = await client.async_get_gas_standing_charge(tariff.product, tariff.code, period_from, period_to)
    standing_charge = standing_charge_data["value_inc_vat"] if standing_charge_data is not None else None

    consumption_and_cost = calculate_gas_consumption_and_cost(
      consumption_data,
      rates,
      0,
      None,
      consumption_units,
      calorific_value
    )
  
    if consumption_and_cost is not None:
      previous_m3_consumption_result =  await async_import_external_statistics_from_consumption(
        period_from,
        hass,
        get_gas_consumption_statistic_unique_id(serial_number, mprn),
        get_gas_consumption_statistic_name(serial_number, mprn),
        consumption_and_cost["charges"],
        rates,
        UnitOfVolume.CUBIC_METERS,
        "consumption_m3",
        initial_statistics=previous_m3_consumption_result
      )

      previous_kwh_consumption_result = await async_import_external_statistics_from_consumption(
        period_from,
        hass,
        get_gas_consumption_statistic_unique_id(serial_number, mprn, True),
        get_gas_consumption_statistic_name(serial_number, mprn, True),
        consumption_and_cost["charges"],
        rates,
        UnitOfEnergy.KILO_WATT_HOUR,
        "consumption_kwh",
        initial_statistics=previous_kwh_consumption_result
      )

      previous_cost_result = await async_import_external_statistics_from_cost(
        period_from,
        hass,
        get_gas_cost_statistic_unique_id(serial_number, mprn),
        get_gas_cost_statistic_name(serial_number, mprn),
        consumption_and_cost["charges"],
        rates,
        "GBP",
        "consumption_kwh",
        previous_cost_result,
        standing_charge_in_pence=standing_charge,
        including_standing_charge_unique_id=get_gas_cost_including_standing_charge_statistic_unique_id(serial_number, mprn),
        including_standing_charge_name=get_gas_cost_including_standing_charge_statistic_name(serial_number, mprn)
      )

    period_from = period_to

  if notify:
    persistent_notification.async_create(
      hass,
      title="Consumption data refreshed",
      message=f"Consumption data from {start_date} for gas meter {serial_number}/{mprn} has finished"
    )