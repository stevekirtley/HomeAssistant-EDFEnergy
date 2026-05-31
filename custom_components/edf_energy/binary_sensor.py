import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.util.dt import (utcnow)
import homeassistant.helpers.config_validation as cv

from .electricity.off_peak import EDFEnergyElectricityOffPeak
from .intelligent.dispatching import EDFEnergyIntelligentDispatching
from .sunday_saver.binary_sensor import EDFEnergySundaySaverFreeElectricity
from .utils import get_active_tariff
from .api_client.intelligent_device import IntelligentDevice
from .coordinators.intelligent_device import IntelligentDeviceCoordinatorResult
from .intelligent import get_intelligent_features

from .const import (
  CONFIG_DEFAULT_MINIMUM_DISPATCH_DURATION_IN_MINUTES,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  CONFIG_ACCOUNT_ID,
  CONFIG_MAIN_INTELLIGENT_MANUAL_DISPATCHES,
  CONFIG_MAIN_INTELLIGENT_MINIMUM_DISPATCH_DURATION_IN_MINUTES,
  CONFIG_MAIN_INTELLIGENT_RATE_MODE,
  CONFIG_MAIN_INTELLIGENT_RATE_MODE_PLANNED_AND_STARTED_DISPATCHES,
  CONFIG_MAIN_INTELLIGENT_SETTINGS,
  DATA_INTELLIGENT_DEVICES,
  DATA_INTELLIGENT_DISPATCHES_COORDINATOR,
  DATA_SUNDAY_SAVER_COORDINATOR,
  DOMAIN,

  DATA_ELECTRICITY_RATES_COORDINATOR_KEY,
  DATA_ACCOUNT,
  INTELLIGENT_DEVICE_KIND_ELECTRIC_VEHICLE_CHARGERS,
  INTELLIGENT_DEVICE_KIND_ELECTRIC_VEHICLES,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
  """Setup sensors based on our entry"""

  if entry.data[CONFIG_KIND] == CONFIG_KIND_ACCOUNT:
    await async_setup_main_sensors(hass, entry, async_add_entities)

  return True

async def async_setup_main_sensors(hass, entry, async_add_entities):
  _LOGGER.debug('Setting up main sensors')
  config = dict(entry.data)

  account_id = config[CONFIG_ACCOUNT_ID]
  account_result = hass.data[DOMAIN][account_id][DATA_ACCOUNT]
  account_info = account_result.account if account_result is not None else None

  now = utcnow()
  entities = []

  if len(account_info["electricity_meter_points"]) > 0:

    for point in account_info["electricity_meter_points"]:
      # We only care about points that have active agreements
      tariff_code = get_active_tariff(now, point["agreements"])
      if tariff_code is not None:
        for meter in point["meters"]:
          mpan = point["mpan"]
          serial_number = meter["serial_number"]
          electricity_rate_coordinator = hass.data[DOMAIN][account_id][DATA_ELECTRICITY_RATES_COORDINATOR_KEY.format(mpan, serial_number)]

          entities.append(EDFEnergyElectricityOffPeak(hass, electricity_rate_coordinator, meter, point))

  entities.extend(get_intelligent_entities(hass, account_id, config))

  sunday_saver_coordinator = hass.data[DOMAIN][account_id].get(DATA_SUNDAY_SAVER_COORDINATOR.format(account_id))
  if sunday_saver_coordinator is not None:
    entities.append(EDFEnergySundaySaverFreeElectricity(hass, sunday_saver_coordinator, account_id))

  if len(entities) > 0:
    async_add_entities(entities)

def get_intelligent_entities(hass, account_id: str, config: dict):
  entities = []

  intelligent_result: IntelligentDeviceCoordinatorResult = hass.data[DOMAIN][account_id][DATA_INTELLIGENT_DEVICES] if DATA_INTELLIGENT_DEVICES in hass.data[DOMAIN][account_id] else None
  intelligent_devices: list[IntelligentDevice] = (intelligent_result.devices or []) if intelligent_result is not None else []
  intelligent_rate_mode = (config[CONFIG_MAIN_INTELLIGENT_SETTINGS][CONFIG_MAIN_INTELLIGENT_RATE_MODE]
                           if CONFIG_MAIN_INTELLIGENT_SETTINGS in config and CONFIG_MAIN_INTELLIGENT_RATE_MODE in config[CONFIG_MAIN_INTELLIGENT_SETTINGS]
                           else CONFIG_MAIN_INTELLIGENT_RATE_MODE_PLANNED_AND_STARTED_DISPATCHES)
  manually_refresh_dispatches = (config[CONFIG_MAIN_INTELLIGENT_SETTINGS][CONFIG_MAIN_INTELLIGENT_MANUAL_DISPATCHES] == True
                           if CONFIG_MAIN_INTELLIGENT_SETTINGS in config and CONFIG_MAIN_INTELLIGENT_MANUAL_DISPATCHES in config[CONFIG_MAIN_INTELLIGENT_SETTINGS]
                           else False)

  for intelligent_device in intelligent_devices:

    if intelligent_device.device_type == INTELLIGENT_DEVICE_KIND_ELECTRIC_VEHICLES or intelligent_device.device_type == INTELLIGENT_DEVICE_KIND_ELECTRIC_VEHICLE_CHARGERS:

      platform = entity_platform.async_get_current_platform()
      if (manually_refresh_dispatches):
        platform.async_register_entity_service(
          "refresh_intelligent_dispatches",
          vol.All(
            cv.make_entity_service_schema(
              {},
              extra=vol.ALLOW_EXTRA,
            ),
          ),
          "async_refresh_dispatches"
        )

      platform.async_register_entity_service(
        "get_point_in_time_intelligent_dispatch_history",
        vol.All(
          cv.make_entity_service_schema(
          {
            vol.Required("point_in_time"): cv.datetime
          },
          extra=vol.ALLOW_EXTRA,
        ),
        ),
        "async_get_point_in_time_intelligent_dispatch_history",
        supports_response=SupportsResponse.ONLY
      )

      coordinator = hass.data[DOMAIN][account_id][DATA_INTELLIGENT_DISPATCHES_COORDINATOR.format(intelligent_device.id)]
      minimum_dispatch_duration_in_minutes = (config[CONFIG_MAIN_INTELLIGENT_SETTINGS][CONFIG_MAIN_INTELLIGENT_MINIMUM_DISPATCH_DURATION_IN_MINUTES]
                                 if CONFIG_MAIN_INTELLIGENT_SETTINGS in config and CONFIG_MAIN_INTELLIGENT_MINIMUM_DISPATCH_DURATION_IN_MINUTES in config[CONFIG_MAIN_INTELLIGENT_SETTINGS]
                                 else CONFIG_DEFAULT_MINIMUM_DISPATCH_DURATION_IN_MINUTES)
      entities.append(EDFEnergyIntelligentDispatching(hass, coordinator, intelligent_device, account_id, intelligent_rate_mode, manually_refresh_dispatches, minimum_dispatch_duration_in_minutes))

  return entities
