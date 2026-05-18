from datetime import datetime, timedelta
import logging
from typing import Callable, Any
import asyncio

from homeassistant.util.dt import (utcnow, as_local)
from homeassistant.helpers.update_coordinator import (
  DataUpdateCoordinator
)

from ..const import (
  CONFIG_MAIN_INTELLIGENT_RATE_MODE_PLANNED_AND_STARTED_DISPATCHES,
  CONFIG_MANUAL_TARIFF_PEAK_RATE,
  CONFIG_MANUAL_TARIFF_OFF_PEAK_RATE,
  COORDINATOR_REFRESH_IN_SECONDS,
  DATA_ACCOUNT,
  DATA_PREVIOUS_CONSUMPTION_COORDINATOR_KEY,
  DOMAIN,
  DATA_INTELLIGENT_DISPATCHES,
  EVENT_ELECTRICITY_PREVIOUS_CONSUMPTION_RATES,
  EVENT_GAS_PREVIOUS_CONSUMPTION_RATES,
  MINIMUM_CONSUMPTION_DATA_LENGTH,
  REFRESH_RATE_IN_MINUTES_PREVIOUS_CONSUMPTION
)

from ..api_client import (ApiException, EDFEnergyApiClient)
from ..api_client.intelligent_dispatches import IntelligentDispatches
from ..api_client.intelligent_device import IntelligentDevice
from ..utils import Tariff, private_rates_to_public_rates

from ..intelligent import adjust_intelligent_rates, is_intelligent_product
from ..coordinators.intelligent_dispatches import IntelligentDispatchesCoordinatorResult
from . import BaseCoordinatorResult, get_electricity_meter_tariff, get_gas_meter_tariff
from ..utils.rate_information import get_min_max_average_rates
from ..coordinators.intelligent_device import IntelligentDeviceCoordinatorResult

_LOGGER = logging.getLogger(__name__)

def __get_interval_end(item):
    return (item["end"].timestamp(), item["end"].fold)

def __sort_consumption(consumption_data):
  sorted = consumption_data.copy()
  sorted.sort(key=__get_interval_end)
  return sorted

class PreviousConsumptionCoordinatorResult(BaseCoordinatorResult):
  consumption: list
  rates: list
  standing_charge: float

  def __init__(self,
               last_evaluated: datetime,
               request_attempts: int,
               consumption: list,
               rates: list,
               standing_charge,
               last_error: Exception | None = None):
    super().__init__(last_evaluated, request_attempts, REFRESH_RATE_IN_MINUTES_PREVIOUS_CONSUMPTION, None, last_error)
    self.consumption = consumption
    self.rates = rates
    self.standing_charge = standing_charge

def contains_consumption(consumptions: list, current_consumption):
  for consumption in consumptions:
    if consumption["start"] == current_consumption["start"]:
      return True

  return False

def get_latest_day(consumption_data: list | None):
  if consumption_data is None or len(consumption_data) < 1:
    return None

  current_reduced_consumption_data = []
  latest_reduced_consumption_data = None
  previous_local_start = None
  for consumption in consumption_data:
    local_start = as_local(consumption["start"])
    if (previous_local_start is not None and
        (previous_local_start.day != local_start.day or previous_local_start.month != local_start.month or previous_local_start.year != local_start.year)):

      if len(current_reduced_consumption_data) == 48:
        latest_reduced_consumption_data = current_reduced_consumption_data

      current_reduced_consumption_data = []

    previous_local_start = local_start
    current_reduced_consumption_data.append(consumption)

  if len(current_reduced_consumption_data) == 48:
    latest_reduced_consumption_data = current_reduced_consumption_data

  _LOGGER.debug(f"Latest day: {latest_reduced_consumption_data[-1]['end'] if latest_reduced_consumption_data is not None and len(latest_reduced_consumption_data) > 0 else None}")
  return latest_reduced_consumption_data

async def async_fetch_consumption_and_rates(
  previous_data: PreviousConsumptionCoordinatorResult | None,
  current: datetime,
  account_info,
  client: EDFEnergyApiClient,
  identifier: str,
  serial_number: str,
  is_electricity: bool,
  is_smart_meter: bool,
  fire_event: Callable[[str, "dict[str, Any]"], None],
  dispatches_results: dict[str, IntelligentDispatchesCoordinatorResult] = None,
  tariff_override: Tariff = None,
  intelligent_rate_mode: str = CONFIG_MAIN_INTELLIGENT_RATE_MODE_PLANNED_AND_STARTED_DISPATCHES,
  manual_rates_config: dict | None = None
):
  """Fetch the previous consumption and rates"""

  if (account_info is None):
    return previous_data

  _LOGGER.debug(f"{'electricity' if is_electricity else 'gas'} {identifier}/{serial_number}: next_refresh: {previous_data.next_refresh if previous_data is not None else None}; ")
  if (previous_data == None or
      current >= previous_data.next_refresh):
    rate_data = None
    standing_charge = None

    try:
      if (is_electricity == True):
        consumption_data = await client.async_get_electricity_consumption(identifier, serial_number, page_size=52)
        consumption_data = get_latest_day(consumption_data)

        if consumption_data is not None:
          period_from = consumption_data[0]["start"]
          period_to = consumption_data[-1]["end"]

          tariff = get_electricity_meter_tariff(period_from, account_info, identifier, serial_number) if tariff_override is None else tariff_override
          if tariff is None:
            _LOGGER.error(f"Could not determine tariff code for previous consumption for electricity {identifier}/{serial_number}")
            return previous_data

          # We'll calculate the wrong value if we don't have our intelligent dispatches
          if is_intelligent_product(tariff.product):
            missing_dispatches = False
            if dispatches_results is None:
              missing_dispatches = True
            else:
              for item in dispatches_results.values():
                if item is None or item.dispatches is None:
                  missing_dispatches = True
                  break

            if missing_dispatches:
              _LOGGER.debug("Dispatches not available for intelligent tariff. Using existing rate information")
              return previous_data

          if (previous_data is not None and
              previous_data.rates is not None and
              len(previous_data.rates) > 0 and
              previous_data.rates[0]["start"] == period_from and previous_data.rates[-1]["end"] == period_to):
            _LOGGER.info('Previous rates are for our target consumption, so using previously retrieved rates and standing charges')
            rate_data = previous_data.rates
            standing_charge = { "value_inc_vat": previous_data.standing_charge }
          else:
            [rate_data, standing_charge] = await asyncio.gather(
              client.async_get_electricity_rates(tariff.product, tariff.code, is_smart_meter, period_from, period_to),
              client.async_get_electricity_standing_charge(tariff.product, tariff.code, period_from, period_to)
            )

          manual_tariff_rates = manual_rates_config.get(tariff.code) if manual_rates_config is not None else None
          if (rate_data is None or len(rate_data) == 0) and manual_tariff_rates is not None:
            _LOGGER.debug(f'No rates from API for {identifier}/{serial_number} ({tariff.code}) — generating from manual config')
            slot = period_from
            rate_data = []
            while slot < period_to:
              rate_data.append({
                "value_inc_vat": manual_tariff_rates[CONFIG_MANUAL_TARIFF_PEAK_RATE],
                "start": slot,
                "end": slot + timedelta(minutes=30),
                "tariff_code": tariff.code,
                "is_capped": False,
              })
              slot += timedelta(minutes=30)

          off_peak_rate_value = manual_tariff_rates[CONFIG_MANUAL_TARIFF_OFF_PEAK_RATE] if manual_tariff_rates is not None else None

          if dispatches_results is not None:
            for key, item in dispatches_results.items():
              if item is not None and item.dispatches is not None:
                rate_data = adjust_intelligent_rates(rate_data,
                                                    item.dispatches.planned,
                                                    item.dispatches.started,
                                                    intelligent_rate_mode,
                                                    off_peak_rate_value=off_peak_rate_value)

                _LOGGER.debug(f"Rates adjusted: {rate_data}; device id: {key} dispatches: {item.dispatches.to_dict()}")
      else:
        consumption_data = await client.async_get_gas_consumption(identifier, serial_number, page_size=52)
        consumption_data = get_latest_day(consumption_data)

        if consumption_data is not None:
          period_from = consumption_data[0]["start"]
          period_to = consumption_data[-1]["end"]

          tariff = get_gas_meter_tariff(period_from, account_info, identifier, serial_number) if tariff_override is None else tariff_override
          if tariff is None:
            _LOGGER.error(f"Could not determine tariff code for previous consumption for gas {identifier}/{serial_number}")
            return previous_data

          if (previous_data is not None and
              previous_data.rates is not None and
              len(previous_data.rates) > 0 and
              previous_data.rates[0]["start"] == period_from and previous_data.rates[-1]["end"] == period_to):
            _LOGGER.info('Previous rates are for our target consumption, so using previously retrieved rates and standing charges')
            rate_data = previous_data.rates
            standing_charge = { "value_inc_vat": previous_data.standing_charge }
          else:
            [rate_data, standing_charge] = await asyncio.gather(
              client.async_get_gas_rates(tariff.product, tariff.code, period_from, period_to),
              client.async_get_gas_standing_charge(tariff.product, tariff.code, period_from, period_to)
            )

      _LOGGER.debug(f"{'electricity' if is_electricity else 'gas'} {identifier}/{serial_number}: consumption_data: {len(consumption_data) if consumption_data is not None else None}; rate_data: {len(rate_data) if rate_data is not None else None}; standing_charge: {standing_charge}")
      if consumption_data is not None and len(consumption_data) >= MINIMUM_CONSUMPTION_DATA_LENGTH and rate_data is not None and len(rate_data) > 0 and standing_charge is not None:
        _LOGGER.debug(f"Discovered previous consumption data for {'electricity' if is_electricity else 'gas'} {identifier}/{serial_number}")
        consumption_data = __sort_consumption(consumption_data)

        public_rates = private_rates_to_public_rates(rate_data)
        min_max_average_rates = get_min_max_average_rates(public_rates)

        if (is_electricity == True):
          fire_event(EVENT_ELECTRICITY_PREVIOUS_CONSUMPTION_RATES, { "mpan": identifier, "serial_number": serial_number, "tariff_code": tariff.code, "rates": public_rates, "min_rate": min_max_average_rates["min"], "max_rate": min_max_average_rates["max"], "average_rate": min_max_average_rates["average"] })
        else:
          fire_event(EVENT_GAS_PREVIOUS_CONSUMPTION_RATES, { "mprn": identifier, "serial_number": serial_number, "tariff_code": tariff.code, "rates": public_rates, "min_rate": min_max_average_rates["min"], "max_rate": min_max_average_rates["max"], "average_rate": min_max_average_rates["average"] })

        _LOGGER.debug(f"Fired event for {'electricity' if is_electricity else 'gas'} {identifier}/{serial_number}")

        return PreviousConsumptionCoordinatorResult(
          current,
          1,
          consumption_data,
          rate_data,
          standing_charge["value_inc_vat"]
        )


      return PreviousConsumptionCoordinatorResult(
        current,
        1,
        previous_data.consumption if previous_data is not None else None,
        previous_data.rates if previous_data is not None else None,
        previous_data.standing_charge if previous_data is not None else None
      )
    except Exception as e:
      if isinstance(e, ApiException) == False:
        raise

      result = None
      if previous_data is not None:
        result =  PreviousConsumptionCoordinatorResult(
          previous_data.last_evaluated,
          previous_data.request_attempts + 1,
          previous_data.consumption,
          previous_data.rates,
          previous_data.standing_charge,
          last_error=e
        )

        if (result.request_attempts == 2):
          _LOGGER.warning(f"Failed to retrieve previous consumption data for {'electricity' if is_electricity else 'gas'} {identifier}/{serial_number} - using cached data. See diagnostics sensor for more information.. Exception: {e}")
      else:
        result = PreviousConsumptionCoordinatorResult(
          # We want to force into our fallback mode
          current - timedelta(minutes=REFRESH_RATE_IN_MINUTES_PREVIOUS_CONSUMPTION),
          2,
          None,
          None,
          None,
          last_error=e
        )
        _LOGGER.warning(f"Failed to retrieve previous consumption data for {'electricity' if is_electricity else 'gas'} {identifier}/{serial_number}. See diagnostics sensor for more information.. Exception: {e}")

      return result

  return previous_data

async def async_create_previous_consumption_and_rates_coordinator(
    hass,
    account_id: str,
    client: EDFEnergyApiClient,
    identifier: str,
    serial_number: str,
    is_electricity: bool,
    is_smart_meter: bool,
    intelligent_rate_mode: str,
    tariff_override: Tariff = None,
    manual_rates_config: dict | None = None):
  """Create reading coordinator"""
  previous_consumption_data_key = f'{identifier}_{serial_number}_previous_consumption_and_rates'

  async def async_update_data():
    """Fetch data from API endpoint."""
    account_result = hass.data[DOMAIN][account_id][DATA_ACCOUNT] if DATA_ACCOUNT in hass.data[DOMAIN][account_id] else None
    account_info = account_result.account if account_result is not None else None
    dispatches: dict[str, IntelligentDispatchesCoordinatorResult] = hass.data[DOMAIN][account_id][DATA_INTELLIGENT_DISPATCHES] if DATA_INTELLIGENT_DISPATCHES in hass.data[DOMAIN][account_id] else None
    previous_data = hass.data[DOMAIN][account_id][previous_consumption_data_key] if previous_consumption_data_key in hass.data[DOMAIN][account_id] else None
    current = utcnow()

    result = await async_fetch_consumption_and_rates(
      previous_data,
      current,
      account_info,
      client,
      identifier,
      serial_number,
      is_electricity,
      is_smart_meter,
      hass.bus.async_fire,
      dispatches,
      tariff_override,
      intelligent_rate_mode,
      manual_rates_config
    )

    if (result is not None):
      hass.data[DOMAIN][account_id][previous_consumption_data_key] = result

    if previous_consumption_data_key in hass.data[DOMAIN][account_id]:
      return hass.data[DOMAIN][account_id][previous_consumption_data_key]
    else:
      return None

  coordinator = DataUpdateCoordinator(
    hass,
    _LOGGER,
    name=previous_consumption_data_key,
    update_method=async_update_data,
    # Because of how we're using the data, we'll update every minute, but we will only actually retrieve
    # data every 30 minutes
    update_interval=timedelta(seconds=COORDINATOR_REFRESH_IN_SECONDS),
    always_update=True
  )

  hass.data[DOMAIN][account_id][DATA_PREVIOUS_CONSUMPTION_COORDINATOR_KEY.format(identifier, serial_number)] = coordinator

  return coordinator
