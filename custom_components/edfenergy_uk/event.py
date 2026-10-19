import logging

from homeassistant.util.dt import (utcnow)

from .utils import get_active_tariff
from .electricity.rates_previous_day import EDFEnergyElectricityPreviousDayRates
from .electricity.rates_current_day import EDFEnergyElectricityCurrentDayRates
from .electricity.rates_next_day import EDFEnergyElectricityNextDayRates
from .electricity.rates_previous_consumption import EDFEnergyElectricityPreviousConsumptionRates
from .gas.rates_current_day import EDFEnergyGasCurrentDayRates
from .gas.rates_next_day import EDFEnergyGasNextDayRates
from .gas.rates_previous_day import EDFEnergyGasPreviousDayRates
from .gas.rates_previous_consumption import EDFEnergyGasPreviousConsumptionRates

from .free_electricity.free_electricity_sessions_events import EDFEnergyFreeElectricitySessionEvents

from .const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  DOMAIN,
  DATA_ACCOUNT
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
  """Setup event entities based on our entry"""
  if CONFIG_KIND in entry.data and entry.data[CONFIG_KIND] == CONFIG_KIND_ACCOUNT:
    await async_setup_main_sensors(hass, entry, async_add_entities)

  return True

async def async_setup_main_sensors(hass, entry, async_add_entities):
  _LOGGER.debug('Setting up event sensors')
  config = dict(entry.data)

  account_id = config[CONFIG_ACCOUNT_ID]

  account_result = hass.data[DOMAIN][account_id][DATA_ACCOUNT]
  account_info = account_result.account if account_result is not None else None

  now = utcnow()
  entities = [EDFEnergyFreeElectricitySessionEvents(hass, account_id)]

  if len(account_info["electricity_meter_points"]) > 0:
    for point in account_info["electricity_meter_points"]:
      tariff = get_active_tariff(now, point["agreements"])
      if tariff is not None:
        for meter in point["meters"]:
          entities.append(EDFEnergyElectricityPreviousDayRates(hass, meter, point))
          entities.append(EDFEnergyElectricityCurrentDayRates(hass, meter, point))
          entities.append(EDFEnergyElectricityNextDayRates(hass, meter, point))
          entities.append(EDFEnergyElectricityPreviousConsumptionRates(hass, meter, point))

  if len(account_info["gas_meter_points"]) > 0:
    for point in account_info["gas_meter_points"]:
      tariff = get_active_tariff(now, point["agreements"])
      if tariff is not None:
        for meter in point["meters"]:
          entities.append(EDFEnergyGasPreviousDayRates(hass, meter, point))
          entities.append(EDFEnergyGasCurrentDayRates(hass, meter, point))
          entities.append(EDFEnergyGasNextDayRates(hass, meter, point))
          entities.append(EDFEnergyGasPreviousConsumptionRates(hass, meter, point))

  if len(entities) > 0:
    async_add_entities(entities)
